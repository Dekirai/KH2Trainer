using KH2Trainer.Core;
using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
if(args.Length!=2) throw new ArgumentException("gameRoot output.json");
string root=Path.GetFullPath(args[0]);
string[] names=["00objentry.bin","obj/N_EX650_BTL10.mdlx"];
var reader=new AssetArchiveReader(protectedDirectories:[root]);
static string Hash(byte[] data)=>Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();
async Task<byte[]> Read(AssetPayload payload){if(payload.Length>16*1024*1024)throw new InvalidDataException();await using var stream=await reader.OpenReadAsync(payload);var bytes=new byte[checked((int)payload.Length)];await stream.ReadExactlyAsync(bytes);return bytes;}
var results=new List<object>();var found=new HashSet<string>();
foreach(var hed in Directory.GetFiles(Path.Combine(root,"Image","dt"),"kh2_*.hed").Order()){
 var index=reader.OpenPackageIndex(hed,Path.Combine(root,"Modding","openkh","resources","kh2idx.txt"));
 foreach(var entry in index.Entries.Where(e=>names.Contains(e.Name))){
  string name=entry.Name!;if(!found.Add(name))throw new InvalidDataException("Duplicate selected original name");
  var package=reader.InspectPackageEntry(index,entry.Ordinal);var bytes=await Read(package.Original);
  var loose=File.ReadAllBytes(Path.Combine(root,"Modding","openkh","data","kh2",name));if(!bytes.SequenceEqual(loose))throw new InvalidDataException("Retail/loose mismatch");
  object selected;
  if(name=="00objentry.bin"){
   int version=BinaryPrimitives.ReadInt32LittleEndian(bytes),count=BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(4));
   if(count<0||8L+96L*count>bytes.Length)throw new InvalidDataException("Objentry range");
   var matches=new List<object>();int last=-1;
   for(int row=0;row<count;row++){
    int offset=8+96*row;var record=bytes.AsSpan(offset,96).ToArray();int id=BinaryPrimitives.ReadInt32LittleEndian(record);if(id<=last)throw new InvalidDataException("Objentry not strictly sorted");last=id;
    string model=Encoding.ASCII.GetString(record,8,32).Split('\0')[0];
    if(model=="N_EX650_BTL10")matches.Add(new{row,offset,id,type=record[4],model,flags72=BinaryPrimitives.ReadUInt32LittleEndian(record.AsSpan(72)),rowHex=Convert.ToHexString(record).ToLowerInvariant()});
   }
   if(matches.Count!=1)throw new InvalidDataException("Unique audience record");
   selected=new{version,count,recordBytes=96,headerBytes=8,trailingBytes=bytes.Length-(8+96*count),strictlySorted=true,matches};
  }else{
   var bar=await reader.ReadBarAsync(package.Original);var entries=new List<object>();
   foreach(var child in bar.Entries){var childBytes=await Read(child.Payload);entries.Add(new{child.Ordinal,child.Type,child.RelativeOffset,child.Length,sha256=Hash(childBytes)});}
   selected=new{barEntries=entries};
  }
  using var pkg=File.OpenRead(index.PackagePath);pkg.Position=entry.Offset;var stored=new byte[entry.StoredLength];pkg.ReadExactly(stored);var hedBytes=File.ReadAllBytes(hed);
  results.Add(new{asset=name,hed=Path.GetFileName(hed),hedSha256=Hash(hedBytes),hedRowHex=Convert.ToHexString(hedBytes.AsSpan(entry.Ordinal*32,32)).ToLowerInvariant(),pkg=Path.GetFileName(index.PackagePath),pkgLength=pkg.Length,entry.Ordinal,entry.NameHash,entry.Offset,entry.StoredLength,entry.OriginalLength,package.StoredMode,storedEntrySha256=Hash(stored),decodedBytes=bytes.Length,decodedSha256=Hash(bytes),fullLooseIdentical=true,selected});
 }
}
if(found.Count!=names.Length)throw new InvalidDataException("Missing selected original assets");
File.WriteAllText(args[1],JsonSerializer.Serialize(new{success=true,scope="Original HED/PKG payloads read and fully compared with loose source; no script or native game execution.",results},new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine($"PASS: {found.Count} original assets; complete loose equality, sorted objentry and selected audience row.");
