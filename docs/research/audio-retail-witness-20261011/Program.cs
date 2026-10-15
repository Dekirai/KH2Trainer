using KH2Trainer.Core;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

if (args.Length != 2) throw new ArgumentException("gameRoot output.json");
string root = Path.GetFullPath(args[0]);
string output = Path.GetFullPath(args[1]);
string here = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../.."));
if (!output.StartsWith(here + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
    throw new ArgumentException("Output must stay in this isolated artifact directory.");
string[] names = ["se/se000.win32.scd", "se/se001.win32.scd", "se/se999.win32.scd", "bgm/music050.win32.scd", "bgm/music051.win32.scd", "bgm/music530.win32.scd", "voice/us/gumibattle/gumi.win32.scd", "voice/us/battle/al0_sora.win32.scd", "obj/B_EX120.a.us", "obj/M_EX950.a.us"];
var selectedNames = names.ToDictionary(n => Convert.ToHexString(MD5.HashData(Encoding.UTF8.GetBytes(n))).ToLowerInvariant());
var limits = new AssetReadLimits { MaximumDecodedBytes = 64 * 1024 * 1024, MaximumDepth = 4 };
var reader = new AssetArchiveReader(limits, [root]);
string looseRoot = Path.Combine(root, "Modding", "openkh", "data", "kh2");
int scdSamples = 0, wrapperSamples = 0, looseComparisons = 0;
var found = new HashSet<string>();
string Hash(byte[] b) => Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();
async Task<byte[]> Read(AssetPayload payload)
{
    if (payload.Length > limits.MaximumDecodedBytes) throw new InvalidDataException("Selected payload exceeds bounded probe limit.");
    await using var stream = await reader.OpenReadAsync(payload);
    byte[] data = new byte[checked((int)stream.Length)]; await stream.ReadExactlyAsync(data); return data;
}
async Task<object> CompareLoose(string relative, byte[] expected)
{
    string path = Path.GetFullPath(Path.Combine(looseRoot, relative));
    if (!path.StartsWith(looseRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Loose comparison path escapes source.");
    var loose = await Read(reader.OpenLooseFile(path));
    bool identical = expected.AsSpan().SequenceEqual(loose);
    if (!identical) throw new InvalidDataException("Retail/loose mismatch: " + relative);
    looseComparisons++;
    return new { relativePath = relative.Replace('\\', '/'), physicalLength = loose.Length, sha256 = Hash(loose), fullByteEquality = identical };
}
async Task<string> StoredHash(PackageIndex index, PackageEntryInfo entry)
{
    if (entry.StoredLength > limits.MaximumDecodedBytes) throw new InvalidDataException("Stored record limit.");
    await using var stream = new FileStream(index.PackagePath, FileMode.Open, FileAccess.Read, FileShare.Read);
    stream.Position = entry.Offset; byte[] buffer = new byte[65536]; int left = entry.StoredLength;
    using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    while (left > 0) { int n = Math.Min(left, buffer.Length); await stream.ReadExactlyAsync(buffer.AsMemory(0, n)); hash.AppendData(buffer.AsSpan(0, n)); left -= n; }
    return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
}
var results = new List<object>(); var indices = new List<object>();
foreach (string hed in Directory.GetFiles(Path.Combine(root, "Image", "dt"), "kh2_*.hed").Order())
{
    var index = reader.OpenPackageIndex(hed);
    indices.Add(new { hed = Path.GetFileName(hed), sha256 = index.HeaderSha256.ToLowerInvariant(), indexEntries = index.Entries.Count, packageLength = new FileInfo(index.PackagePath).Length });
    foreach (var entry in index.Entries.Where(e => selectedNames.ContainsKey(e.NameHash)))
    {
        string name = selectedNames[entry.NameHash]; found.Add(name);
        if (!entry.IsAvailable) throw new InvalidDataException("Selected HED placeholder: " + name);
        var package = reader.InspectPackageEntry(index, entry.Ordinal);
        var original = await Read(package.Original);
        object originalLoose = await CompareLoose(name, original);
        object? scd = null;
        if (Metadata.IsScd(original)) { scd = Metadata.Scd(original); scdSamples++; }
        var audioChildren = new List<object>(); var referenced = new HashSet<string>();
        if (original.AsSpan(0, Math.Min(4, original.Length)).SequenceEqual("BAR\x01"u8))
        {
            var bar = await reader.ReadBarAsync(package.Original);
            foreach (var child in bar.Entries.Where(c => c.Type is 31 or 34 or 48))
            {
                var bytes = await Read(child.Payload);
                if (bytes.Length != 48 || !bytes.AsSpan(0, 6).SequenceEqual("ORIGIN"u8)) throw new InvalidDataException("Selected BAR audio child is not expected ORIGIN48.");
                int n = Array.IndexOf(bytes, (byte)0, 16, 32); if (n < 0) n = 48;
                string replacementName = Encoding.ASCII.GetString(bytes, 16, n - 16);
                if (package.Remastered.Count(r => r.Name == replacementName) != 1) throw new InvalidDataException("ORIGIN must name exactly one remaster in selected record.");
                referenced.Add(replacementName); wrapperSamples++;
                audioChildren.Add(new { child.Ordinal, child.Type, child.Tag, child.RelativeOffset, child.Length, sha256 = Hash(bytes), signatureFirst8Hex = Convert.ToHexString(bytes.AsSpan(0, 8)), fieldU16At8 = Metadata.U16(bytes, 8), fieldU16At10 = Metadata.U16(bytes, 10), fieldU32At12 = Metadata.U32(bytes, 12), nameAt16 = replacementName, nameByteLength = n - 16, nameReachesRuntimeFieldAt32 = n > 32, note = "Disk wrapper name can overlap later runtime fields. No disk bytes are treated as runtime pointers." });
            }
        }
        var audioRemasters = new List<object>();
        foreach (var remaster in package.Remastered.Where(r => referenced.Contains(r.Name)))
        {
            var data = await Read(remaster.Payload);
            if (!Metadata.IsScd(data)) throw new InvalidDataException("Named selected audio replacement lacks SEDBSSCF.");
            scdSamples++;
            audioRemasters.Add(new { remaster.Ordinal, remaster.Name, remaster.LogicalOffset, remaster.OriginalAssetOffset, remaster.StoredOffset, remaster.StoredMode, physicalLength = data.Length, sha256 = Hash(data), loose = await CompareLoose(Path.Combine("remastered", name, remaster.Name), data), scd = Metadata.Scd(data) });
        }
        byte[] hedBytes = File.ReadAllBytes(hed);
        results.Add(new { asset = name, hed = Path.GetFileName(hed), entry.Ordinal, entry.NameHash, entry.Offset, entry.StoredLength, entry.OriginalLength, package.StoredMode, package.CreationValue, storedEntrySha256 = await StoredHash(index, entry), hedRowSha256 = Hash(hedBytes.AsSpan(entry.Ordinal * 32, 32).ToArray()), original = new { physicalLength = original.Length, sha256 = Hash(original), loose = originalLoose, scd }, remasteredPartCount = package.Remastered.Count, uninspectedNonAudioRemasteredParts = package.Remastered.Count - audioRemasters.Count, audioChildren, audioRemasters });
    }
}
if (found.Count != names.Length || results.Count != 12 || wrapperSamples != 3 || scdSamples != 13 || looseComparisons != 15) throw new InvalidDataException("Unexpected bounded sample cardinality.");
string[] sources = ["AssetArchiveReader.cs", "AssetPackageCodec.cs", "AssetExplorerModels.cs", "AssetFileAccess.cs"];
var repo = new DirectoryInfo(here);
while (!File.Exists(Path.Combine(repo.FullName, "src", "KH2Trainer.Core", "AssetArchiveReader.cs")))
    repo = repo.Parent ?? throw new DirectoryNotFoundException("Cannot locate repository source root.");
string core = Path.Combine(repo.FullName, "src", "KH2Trainer.Core");
var sourcePins = sources.Select(s => new { path = "src/KH2Trainer.Core/" + s, sha256 = Hash(File.ReadAllBytes(Path.Combine(core, s))) });
var document = new { status = "PASS_BOUNDED_READ_ONLY_RETAIL_WITNESS", selectedNames = names, archiveRecords = results.Count, scdSamples, wrapperSamples, fullLooseComparisons = looseComparisons, scope = "12 selected archive records only. Reads complete selected payloads in memory for equality/hashes; writes metadata only. No payload exports, runtime pointers, importer, native game calls, codec decoding or playback.", limitations = new[] { "Declared and physical file lengths are distinct; differences are reported without assuming corruption.", "Table spans and basic sequence headers are bounded against both lengths; this does not prove codec, track bytecode, stream, playback or semantic validity.", "Name MD5 matches are locators for explicit selected names, not a global archive inventory.", "ORIGIN disk names overlap fields overwritten during runtime preparation; this probe follows no runtime pointers.", "No package precedence or effective mod override is inferred from duplicate selected entries." }, linkedSourcePins = sourcePins, indices, results };
File.WriteAllText(output, JsonSerializer.Serialize(document, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"PASS: {results.Count} archive records, {wrapperSamples} ORIGIN wrappers, {scdSamples} SCD samples, {looseComparisons} full loose comparisons.");
