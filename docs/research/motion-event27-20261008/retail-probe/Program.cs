using KH2Trainer.Core;
using System.Security.Cryptography;
using System.Text.Json;
if(args.Length!=2)throw new ArgumentException("gameRoot output.json");
string root=Path.GetFullPath(args[0]),name="obj/B_LK120.mdlx";
var reader=new AssetArchiveReader(protectedDirectories:[root]);
static string Hash(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
async Task<byte[]> Read(AssetPayload p) { if(p.Length>16*1024*1024)throw new InvalidDataException(); await using var s=await reader.OpenReadAsync(p);var b=new byte[checked((int)p.Length)];await s.ReadExactlyAsync(b);return b; }
var results=new List<object>();
foreach(var hed in Directory.GetFiles(Path.Combine(root,"Image","dt"),"kh2_*.hed").Order()) {
 var idx=reader.OpenPackageIndex(hed,Path.Combine(root,"Modding","openkh","resources","kh2idx.txt"));
 foreach(var entry in idx.Entries.Where(e=>e.Name==name)) {
  var package=reader.InspectPackageEntry(idx,entry.Ordinal);
  var bytes=await Read(package.Original);
  var loose=File.ReadAllBytes(Path.Combine(root,"Modding","openkh","data","kh2","obj","B_LK120.mdlx"));
  if(!bytes.SequenceEqual(loose))throw new InvalidDataException("Full retail/loose asset mismatch");
  var bar=await reader.ReadBarAsync(package.Original);var children=new List<object>();
  foreach(var child in bar.Entries.Where(e=>e.Type is 3 or 23)) {
   var data=await Read(child.Payload);object? script=null;
   if(child.Type==3){var doc=await BdxInspector.ReadAsync(reader,child.Payload);script=new {header=doc.Header,events=doc.Header.Events.Select(e=>new{e.Id,e.Pc,e.IsFirstForId}),instructions=doc.Instructions.Count,diagnostics=doc.Diagnostics.Count,doc.HitLimit};}
   children.Add(new{child.Ordinal,child.Type,child.RelativeOffset,child.Length,sha256=Hash(data),script});
  }
  using var file=File.OpenRead(idx.PackagePath);file.Position=entry.Offset;byte[] stored=new byte[entry.StoredLength];file.ReadExactly(stored);
  byte[] hedRaw=File.ReadAllBytes(hed);
  results.Add(new{asset=name,hed=Path.GetFileName(hed),hedSha256=Hash(hedRaw),hedRowHex=Convert.ToHexString(hedRaw.AsSpan(entry.Ordinal*32,32)).ToLowerInvariant(),pkg=Path.GetFileName(idx.PackagePath),pkgLength=file.Length,entry.Ordinal,entry.NameHash,entry.Offset,entry.StoredLength,entry.OriginalLength,package.StoredMode,storedEntrySha256=Hash(stored),decodedBytes=bytes.Length,decodedSha256=Hash(bytes),fullLooseIdentical=true,children});
 }
}
if(results.Count!=1)throw new InvalidDataException("Expected exactly one retail witness");
File.WriteAllText(args[1],JsonSerializer.Serialize(new{success=true,scope="Read-only retail HED/PKG selected original payload; entire asset equals loose source; no runtime execution.",results},new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine("PASS: one original retail asset; full loose identity; BDX and BAR23 child hashes.");
