using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using KH2Trainer.Core;

int checks=0;
void Check(bool ok,string label){checks++;if(!ok)throw new InvalidDataException(label);}
void OutOfRange(int bank,int index){bool threw=false;try{BdxNativeCallCatalog.Default.Lookup(bank,index);}catch(ArgumentOutOfRangeException){threw=true;}Check(threw,"stored-width boundary");}
var assembly=typeof(BdxNativeCallCatalog).Assembly;
Check(assembly.GetManifestResourceNames().SequenceEqual(new[]{"KH2Trainer.Core.BdxNativeCalls.json"}),"exact manifest resource name");
using var stream=assembly.GetManifestResourceStream("KH2Trainer.Core.BdxNativeCalls.json")!;
using var buffer=new MemoryStream();stream.CopyTo(buffer);var bytes=buffer.ToArray();
Check(bytes.SequenceEqual(File.ReadAllBytes(args[0])),"embedded resource exactly equals reviewed JSON");
using var document=JsonDocument.Parse(bytes);
var catalog=BdxNativeCallCatalog.Default;
Check(catalog.DescriptorCount==1063&&catalog.AnnotatedCount==158,"record/annotation totals");
var banks=document.RootElement.GetProperty("banks").EnumerateArray().ToDictionary(b=>b.GetProperty("bank").GetInt32());
int rows=0,annotated=0,nulls=0;
foreach(var row in document.RootElement.GetProperty("descriptors").EnumerateArray()){
 rows++;
 int bank=row.GetProperty("bank").GetInt32(),index=row.GetProperty("index").GetInt32();
 var info=catalog.Lookup(bank,index);var bankRow=banks[bank];
 uint handler=row.GetProperty("handlerRva").GetUInt32(),flags=row.GetProperty("flags").GetUInt32();
 string name=row.GetProperty("name").GetString()!;
 if(name.Length>0)annotated++;if(handler==0)nulls++;
 Check(info.Bank==bank&&info.Index==index&&info.DescriptorRva==row.GetProperty("descriptorRva").GetUInt32(),"descriptor identity");
 Check(info.BankState==(BdxNativeBankState)bankRow.GetProperty("state").GetInt32()&&info.TableRva==bankRow.GetProperty("tableRva").GetUInt32(),"bank metadata");
 Check(info.HandlerRva==(handler==0?null:handler)&&info.Flags==flags&&info.DeclaredOperandCount==(flags&65535)&&info.HasReturnSlot==((flags&0x40000000)!=0),"numeric metadata");
 Check(info.DescriptorState==(handler==0?BdxNativeDescriptorState.NullHandler:BdxNativeDescriptorState.Present),"nonnull distinction");
 Check(info.HasAnnotation==(name.Length>0)&&info.DisplayName==(name.Length>0?name:handler==0?"Null native handler":"Unannotated native handler"),"annotation/fallback");
 foreach(string field in new[]{"summary","notes","evidence"}){
  string expected=row.GetProperty(field).GetString()!;
  string actual=field switch{"summary"=>info.Summary,"notes"=>info.Notes,_=>info.Evidence};
  Check(actual==expected,"exact text "+field);
  Check(expected.Length==0||info.Details.Contains(expected),"details include "+field);
 }
 Check(info.SearchText.Contains(info.DisplayName)&&info.SearchText.Contains(info.Summary)&&info.SearchText.Contains(info.Notes),"search semantic text");
 Check(info.Details.Contains(BdxNativeCallCatalog.Scope),"bounded scope shown");
}
Check(rows==1063&&annotated==158&&nulls==15,"loaded row totals");
var extents=new Dictionary<int,int>{{0,105},{1,368},{2,98},{3,179},{4,59},{5,35},{6,72},{7,37},{8,9},{9,41},{10,60}};
foreach(var (bank,count) in extents){
 Check(catalog.Lookup(bank,count-1).DescriptorState!=BdxNativeDescriptorState.Uncatalogued,"last observed descriptor retained");
 var missing=catalog.Lookup(bank,count);
 Check(missing.DescriptorState==BdxNativeDescriptorState.Uncatalogued&&!missing.HasAnnotation&&missing.HandlerRva==null&&missing.DeclaredOperandCount==null,"extent is unknown metadata");
 Check(missing.BankState==(BdxNativeBankState)banks[bank].GetProperty("state").GetInt32(),"unknown descriptor retains bank state");
}
foreach(var bank in new[]{11,1023}){
 var unknown=catalog.Lookup(bank,65535);
 Check(unknown.BankState==BdxNativeBankState.Uncatalogued&&unknown.DescriptorState==BdxNativeDescriptorState.Uncatalogued&&unknown.TableRva==null,"unrecorded bank");
}
OutOfRange(-1,0);OutOfRange(1024,0);OutOfRange(0,-1);OutOfRange(0,65536);
foreach(var (bank,index) in new[]{(1,103),(1,122),(1,163),(1,240),(1,246),(2,36)}){
 var info=catalog.Lookup(bank,index);
 Check(info.DescriptorState==BdxNativeDescriptorState.Present&&info.HandlerRva!=null&&info.HasReturnSlot==false&&info.DisplayName=="Empty native handler","RET-only remains nonnull");
 Check(info.Details.Contains("RET 0")&&info.Notes.Contains("VM still consumes"),"RET-only boundary notes");
}
Check(catalog.Lookup(1,16).DescriptorState==BdxNativeDescriptorState.NullHandler&&catalog.Lookup(1,17).DescriptorState==BdxNativeDescriptorState.Present,"NULL hole does not hide later row");
Check(catalog.Lookup(1,157).HandlerRva==catalog.Lookup(1,219).HandlerRva&&catalog.Lookup(1,157).Index!=catalog.Lookup(1,219).Index,"aliases preserve distinct indices");
var target=catalog.Lookup(2,97);
Check(target.Summary.Contains("+3384")&&target.Summary.Contains("+3392")&&target.Notes.Contains("+3392 is left unchanged")&&target.Notes.Contains("stable lifetime"),"target links conditional/lifetime notes");
var query=catalog.Lookup(1,367);
Check(query.Notes.Contains("Actor memory is read before")&&query.Notes.Contains("relevant SSE exceptions masked")&&query.Notes.Contains("2^31")&&query.Notes.Contains("fresh result"),"query failure/progress notes");
Check(catalog.Lookup(3,0).BankState==BdxNativeBankState.ContextInstalled&&catalog.Lookup(9,0).BankState==BdxNativeBankState.ContextInstalled,"observed descriptors do not imply installed banks");
Check(typeof(BdxNativeCallCatalog).GetConstructors().Length==0,"no public catalog constructor");
Check(typeof(BdxNativeCallCatalog).GetFields(BindingFlags.Public|BindingFlags.Instance).Length==0,"no public mutable storage");
Check(typeof(BdxNativeCallCatalog).GetProperties().All(p=>p.SetMethod==null),"catalog properties readonly");
var fields=typeof(BdxNativeCallCatalog).GetFields(BindingFlags.NonPublic|BindingFlags.Instance);
Check(fields.All(f=>f.IsInitOnly&&f.FieldType.Name.StartsWith("FrozenDictionary")),"immutable dictionary storage");
var original=catalog.Lookup(0,76);var callerCopy=original with{DisplayName="caller copy"};
Check(catalog.Lookup(0,76).DisplayName=="Set Drive Form Keyblade"&&callerCopy.DisplayName=="caller copy","record copy leaves stored entry unchanged");
Console.WriteLine(JsonSerializer.Serialize(new{success=true,checks,descriptorRows=rows,annotatedRows=annotated,nullRows=nulls,resourceSha256=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),scope="Compiled unchanged production catalog source and embedded current product JSON. All descriptors and exact text/details/search verified; unknown/NULL/context/RET-only/alias boundaries and encapsulation checked. No original code, scripts or game execution."},new JsonSerializerOptions{WriteIndented=true}));
