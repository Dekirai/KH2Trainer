using System.Text.Json;
using KH2Trainer.Core;

using var oracle=JsonDocument.Parse(File.ReadAllText(args[0]));
var rows=oracle.RootElement.GetProperty("descriptors").EnumerateArray().ToDictionary(
    x=>(x.GetProperty("bank").GetInt32(),x.GetProperty("index").GetInt32()),x=>x.Clone());
var banks=oracle.RootElement.GetProperty("banks").EnumerateArray().ToDictionary(x=>x.GetProperty("bank").GetInt32(),x=>x.Clone());
var c=BdxNativeCallCatalog.Default;int checks=0;
void Check(bool ok,string why){++checks;if(!ok)throw new InvalidDataException(why);}
Check(c.DescriptorCount==rows.Count,"descriptor count");
Check(c.AnnotatedCount==44,"annotation count");
foreach(var ((bank,index),row) in rows){
    var actual=c.Lookup(bank,index);var b=banks[bank];
    uint flags=row.GetProperty("flags").GetUInt32(),handler=row.GetProperty("handlerRva").GetUInt32();
    Check(actual.Bank==bank&&actual.Index==index,"key");
    Check(actual.BankState==(BdxNativeBankState)b.GetProperty("state").GetInt32()&&actual.TableRva==b.GetProperty("tableRva").GetUInt32(),"bank identity");
    Check(actual.DescriptorRva==row.GetProperty("descriptorRva").GetUInt32()&&actual.HandlerRva==(handler==0?null:handler),"descriptor identity");
    Check(actual.Flags==flags&&actual.DeclaredOperandCount==(flags&0xffff)&&actual.HasReturnSlot==((flags&0x40000000)!=0),"flags");
    Check(actual.DescriptorState==(handler==0?BdxNativeDescriptorState.NullHandler:BdxNativeDescriptorState.Present),"descriptor state");
    Check(actual.Details.Contains($"Native call {bank}:{index}")&&actual.Details.Contains("not native bounds"),"details identity/scope");
    var modified=actual with { Bank=1023,Index=65535,Notes="private copy" };
    Check(!ReferenceEquals(actual,modified)&&c.Lookup(bank,index).Bank==bank&&c.Lookup(bank,index).Index==index&&c.Lookup(bank,index).Notes!="private copy","public record copy does not mutate catalog");
}
var testedBanks=Enumerable.Range(0,12).Append(1023);
foreach(int bank in testedBanks)for(int index=0;index<=65535;index++){
    var a=c.Lookup(bank,index);bool known=rows.ContainsKey((bank,index));
    Check(a.Bank==bank&&a.Index==index&&(a.DescriptorState!=BdxNativeDescriptorState.Uncatalogued)==known,"full index-space lookup");
    if(!known)Check(a.HandlerRva is null&&a.DescriptorRva is null&&a.DeclaredOperandCount is null&&a.Flags is null&&a.HasReturnSlot is null&&!a.HasAnnotation,"unknown does not fabricate metadata");
    bool bankKnown=banks.ContainsKey(bank);
    Check((a.BankState!=BdxNativeBankState.Uncatalogued)==bankKnown,"bank status survives missing descriptor");
}
for(int bank=0;bank<=1023;bank++)foreach(int index in new[]{0,1,65535}){
    var a=c.Lookup(bank,index);Check(a.Bank==bank&&a.Index==index,"all representable banks");
}
foreach(var key in new[]{(-1,0),(1024,0),(0,-1),(0,65536),(int.MinValue,0),(int.MaxValue,0),(0,int.MinValue),(0,int.MaxValue)}){
    bool rejected=false;try{c.Lookup(key.Item1,key.Item2);}catch(ArgumentOutOfRangeException){rejected=true;}Check(rejected,"representation rejection");
}
foreach(int bank in new[]{3,9})Check(c.Lookup(bank,0).Details.Contains("original registry slot is NULL")&&c.Lookup(bank,0).Details.Contains("teardown clears it"),"dynamic state honesty");
Check(c.Lookup(0,10).Details.Contains("does not terminate")&&c.Lookup(0,11).DescriptorState==BdxNativeDescriptorState.Present,"interior NULL hole");
var discrepancy=c.Lookup(1,6);Check(discrepancy.DeclaredOperandCount==12&&discrepancy.Summary.Contains("12, 13, 14 and 15")&&discrepancy.Notes.Contains("16-slot scratch"),"declared/read discrepancy preserved");
var result=new{success=true,checks,knownDescriptors=rows.Count,allIndicesTestedPerBank=65536,banksWithAllIndices=testedBanks.ToArray(),allRepresentableBanksSampled=1024,gameOrNativeExecution=false};
string json=JsonSerializer.Serialize(result,new JsonSerializerOptions{WriteIndented=true});File.WriteAllText(args[1],json);Console.WriteLine(json);
