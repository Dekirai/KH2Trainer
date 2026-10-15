using KH2Trainer.Core;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

if (args.Length != 2) throw new ArgumentException("gameRoot output.json");
string root = Path.GetFullPath(args[0]);
const string name = "obj/N_HB040_BTL.mdlx";
string target = Convert.ToHexString(MD5.HashData(Encoding.UTF8.GetBytes(name))).ToLowerInvariant();
var reader = new AssetArchiveReader(new AssetReadLimits { MaximumDecodedBytes = 4 * 1024 * 1024 }, [root]);
string Hash(byte[] data) => Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();
var indices = new List<object>(); var hits = new List<object>();
foreach (string hed in Directory.GetFiles(Path.Combine(root, "Image", "dt"), "kh2_*.hed").Order())
{
    var index = reader.OpenPackageIndex(hed);
    indices.Add(new { hed = Path.GetFileName(hed), index.HeaderSha256, entries = index.Entries.Count });
    foreach (var entry in index.Entries.Where(x => x.NameHash == target))
    {
        if (!entry.IsAvailable) throw new InvalidDataException("Selected entry unavailable");
        var package = reader.InspectPackageEntry(index, entry.Ordinal);
        if (package.Original.Length > 4 * 1024 * 1024) throw new InvalidDataException("Bound exceeded");
        await using var stream = await reader.OpenReadAsync(package.Original);
        byte[] bytes = new byte[checked((int)stream.Length)]; await stream.ReadExactlyAsync(bytes);
        byte[] loose = await File.ReadAllBytesAsync(Path.Combine(root, "Modding", "openkh", "data", "kh2", name));
        if (!bytes.AsSpan().SequenceEqual(loose)) throw new InvalidDataException("Retail differs from loose file");
        hits.Add(new { name, hed = Path.GetFileName(hed), entry.Ordinal, entry.Offset, entry.StoredLength, length = bytes.Length, sha256 = Hash(bytes), byteEquality = true });
    }
}
if (hits.Count != 1) throw new InvalidDataException("Expected one selected retail entry");
await File.WriteAllTextAsync(args[1], JsonSerializer.Serialize(new { scope = "One selected original package payload decoded read-only in memory; no assets exported; static equality, no execution evidence.", indices, hits }, new JsonSerializerOptions { WriteIndented = true }) + "\n");
Console.WriteLine("PASS: one selected package payload equals loose asset; metadata only.");
