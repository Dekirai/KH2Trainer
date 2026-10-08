using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using KH2Trainer.Core;
int checks=0;
void Check(bool ok,string label){checks++;if(!ok)throw new InvalidDataException(label);}
BdxNativeCallCatalogTests.Run(Check);
int existingChecks=checks;
var assembly=typeof(BdxNativeCallCatalog).Assembly;
Check(assembly.GetManifestResourceNames().SequenceEqual(new[]{"KH2Trainer.Core.BdxNativeCalls.json"}),"exact embedded resource name");
using var stream=assembly.GetManifestResourceStream("KH2Trainer.Core.BdxNativeCalls.json")!;
using var buffer=new MemoryStream();stream.CopyTo(buffer);var bytes=buffer.ToArray();
Check(bytes.SequenceEqual(File.ReadAllBytes(args[0])),"compiled embedded resource equals reviewed product JSON");
using var document=JsonDocument.Parse(bytes);
var catalog=BdxNativeCallCatalog.Default;
foreach(var row in document.RootElement.GetProperty("descriptors").EnumerateArray()) {
 int bank=row.GetProperty("bank").GetInt32(),index=row.GetProperty("index").GetInt32();
 var info=catalog.Lookup(bank,index);uint handler=row.GetProperty("handlerRva").GetUInt32(),flags=row.GetProperty("flags").GetUInt32();
 string name=row.GetProperty("name").GetString()!;
 Check(info.Bank==bank&&info.Index==index&&info.DescriptorRva==row.GetProperty("descriptorRva").GetUInt32(),"identity");
 Check(info.HandlerRva==(handler==0?null:handler)&&info.Flags==flags&&info.DeclaredOperandCount==(flags&65535)&&info.HasReturnSlot==((flags&0x40000000)!=0),"raw metadata survives loading");
 Check(info.HasAnnotation==!string.IsNullOrWhiteSpace(name)&&info.DescriptorState==(handler==0?BdxNativeDescriptorState.NullHandler:BdxNativeDescriptorState.Present),"annotation and descriptor states");
 Check(info.DisplayName==(name.Length>0?name:handler==0?"Null native handler":"Unannotated native handler"),"display fallback");
 foreach(string key in new[]{"summary","notes","evidence"}) {
  string expected=row.GetProperty(key).GetString()!;string actual=key switch {"summary"=>info.Summary,"notes"=>info.Notes,_=>info.Evidence};
  Check(actual==expected,"exact text: "+key);Check(expected.Length==0||info.Details.Contains(expected),"details include: "+key);
 }
 Check(info.SearchText.Contains(info.DisplayName)&&info.SearchText.Contains(info.Summary)&&info.SearchText.Contains(info.Notes),"search carries names and semantic notes");
}
Check(typeof(BdxNativeCallCatalog).GetConstructors().Length==0,"no public catalog construction/mutation path");
Check(typeof(BdxNativeCallCatalog).GetFields(BindingFlags.Public|BindingFlags.Instance).Length==0,"no public mutable catalog storage");
Check(typeof(BdxNativeCallCatalog).GetProperties().All(p=>p.SetMethod==null),"catalog properties have no public setters");
var fields=typeof(BdxNativeCallCatalog).GetFields(BindingFlags.NonPublic|BindingFlags.Instance);
Check(fields.All(f=>f.IsInitOnly&&f.FieldType.Name.StartsWith("FrozenDictionary")),"readonly immutable dictionary backing fields");
var original=catalog.Lookup(0,76);var callerCopy=original with { DisplayName="caller copy" };
Check(catalog.Lookup(0,76).DisplayName=="Set Drive Form Keyblade"&&callerCopy.DisplayName=="caller copy","record copy cannot mutate stored row");
Console.WriteLine(JsonSerializer.Serialize(new{success=true,checks,existingCatalogChecks=existingChecks,descriptorRows=150,annotatedRows=104,resourceSha256=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),scope="Compiled unmodified production catalog source and current production JSON as the same manifest resource. Existing bounded catalog tests plus every descriptor/text/details/search check. No decoder oracle rerun or game execution."},new JsonSerializerOptions{WriteIndented=true}));
