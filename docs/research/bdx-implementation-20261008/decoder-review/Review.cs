using System.Buffers.Binary;
using System.Text.Json;
using KH2Trainer.Core;
byte[] oracle=File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory,"..","..","..","oracle.bin"));
if(oracle.Length!=65536*3)throw new Exception("Oracle length");
int checks=0;
for(int op=0;op<65536;op++)
{
 byte[] b=new byte[52];b[0]=(byte)'x';
 BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(16),64);
 BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(20),512);
 BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(24),64);
 BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(32),14);
 BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(44),(ushort)op);
 BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(46),0xFFFE);
 BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(48),0x8000);
 BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(50),0x0049);
 var d=BdxInspector.Inspect(b,new(){MaximumInstructions=1});
 var x=d.Instructions.Single();
 void Check(bool ok,string what){checks++;if(!ok)throw new Exception($"Opcode {op:X4}: {what}");}
 Check(x.WidthInWords==oracle[3*op],"width");
 Check(d.Diagnostics.Any(z=>z.Code=="invalid-opcode")== (oracle[3*op+1]!=0),"status5");
 int mask=0;
 foreach(var e in x.Edges)
 {
  mask|=e.Kind switch{BdxEdgeKind.Next=>1,BdxEdgeKind.Branch=>2,BdxEdgeKind.Call=>4,BdxEdgeKind.CallContinuation=>8,BdxEdgeKind.YieldResume=>16,BdxEdgeKind.NativeContinuation=>32,BdxEdgeKind.DynamicReturn=>64,_=>throw new Exception("kind")};
  if(e.TargetPc is int target)
  {
   int next=14+x.WidthInWords;int expected=e.Kind is BdxEdgeKind.Branch or BdxEdgeKind.Call ? unchecked(next+((op&15)==11?unchecked((int)0x8000FFFE):-2)) : next;
   Check(target==expected,"signed target");
  }
 }
 Check(mask==oracle[3*op+2],"edge classes");
 if((op&15)==10){Check(x.TrapBank==op>>6 && x.TrapIndex==65534,"bank/index");}
}
Console.WriteLine(JsonSerializer.Serialize(new{status="PASS",opcodeCases=65536,checks,scope="Actual linked BdxInspection.cs in isolated process; Asset IO stub never called."},new JsonSerializerOptions{WriteIndented=true}));
namespace KH2Trainer.Core
{
 public sealed record AssetPayload(long Length);
 public sealed class AssetArchiveReader
 {
  public Task<Stream> OpenReadAsync(AssetPayload payload,CancellationToken token)=>throw new NotSupportedException("No IO in structural review");
 }
}
