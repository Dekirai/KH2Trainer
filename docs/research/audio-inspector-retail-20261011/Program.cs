using System.Security.Cryptography;
using System.Text.Json;
using KH2Trainer.Core;

if (args.Length != 1) throw new ArgumentException("Read-only game directory required.");
string game = Path.GetFullPath(args[0]);
string here = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../"));
var root = new DirectoryInfo(here);
while (!File.Exists(Path.Combine(root.FullName, "Directory.Build.props"))) root = root.Parent ?? throw new IOException("Repository missing.");
string repo = root.FullName;
string witnessFile = Path.Combine(repo, "docs/research/audio-retail-witness-20261011/witness.json");
string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
if (Hash(File.ReadAllBytes(witnessFile)) != "505642a902467b8eefefb00df5ad14d3ed4b58f7f7cc4e9b8cad6e3f384943f1") throw new IOException("Frozen witness changed.");
using var witness = JsonDocument.Parse(File.ReadAllBytes(witnessFile));
var reader = new AssetArchiveReader(new() { MaximumDecodedBytes = 64 * 1024 * 1024 }, [game]);
var indexes = new Dictionary<string, PackageIndex>();
var samples = new List<object>();
int checks = 0, scds = 0, origins = 0;
void Check(bool ok, string why) { ++checks; if (!ok) throw new InvalidDataException(why); }
long Num(JsonElement e, string key) => e.GetProperty(key).GetInt64();
bool Bool(JsonElement e, string key) => e.GetProperty(key).GetBoolean();
string Text(JsonElement e, string key) => e.GetProperty(key).GetString()!;

async Task CheckScd(AssetPayload payload, JsonElement expected, string label, string context)
{
    var d = await AudioBankInspector.ReadAsync(reader, payload);
    Check(d.Format == AudioBankFormat.Scd && d.Status == AudioInspectionStatus.MetadataRead && !d.HitLimit, label + " metadata status");
    var s = d.Scd ?? throw new InvalidDataException(label + " header missing");
    Check(d.AvailableLength == Num(expected, "physicalLength"), label + " available size");
    Check(s.DeclaredSizeAt16 == Num(expected, "declaredLengthAt16") && d.PhysicalMinusDeclared == Num(expected, "physicalMinusDeclared"), label + " declared size");
    Check(s.Version == Num(expected, "version") && s.HeaderOffset == Num(expected, "headerOffset"), label + " version/header");
    Check(s.ProfileByte12 == Num(expected, "fieldByte12") && s.ProfileByte13 == Num(expected, "fieldByte13"), label + " raw profile");
    Check(s.BankId == Num(expected, "bankId") && s.SequenceCount == Num(expected, "sequenceCount") && s.TableBCount == Num(expected, "tableBCount") && s.TableCCount == Num(expected, "tableCCount"), label + " header counts");
    Check(d.Preview.Count == Math.Min(4096, payload.Length) && d.MetadataBytesRead <= 1024 * 1024, label + " bounded metadata");
    Check(d.Diagnostics.All(x => x.Severity == AudioDiagnosticSeverity.Observation), label + " no structural problems");
    foreach (var (kind, statsName, baseName) in new[] {
        (AudioTableKind.Sequence,"sequenceTableStats","sequenceOffsetsTable"),
        (AudioTableKind.B,"tableBStats","tableBOffset"),
        (AudioTableKind.C,"tableCStats","tableCOffset"),
        (AudioTableKind.Aux,"auxTableStats","auxOffsetsTable") })
    {
        var t = d.Tables.Single(x => x.Kind == kind); var stats = expected.GetProperty(statsName);
        Check(t.Offset == Num(expected, baseName), label + " table base");
        var rows = d.Rows.Where(x => x.TableKind == kind).ToArray();
        if (stats.ValueKind == JsonValueKind.Null) { Check(t.Status == AudioTableStatus.Absent && rows.Length == 0, label + " absent aux"); continue; }
        Check(t.Status == AudioTableStatus.Read && rows.Length == Num(stats, "count") && t.Count == rows.Length && t.InspectedRows == rows.Length, label + " complete table read");
        Check(t.WithinDeclaredSize == Bool(stats, "tableInDeclaredLength"), label + " table declared extent");
        Check(rows.Count(x => x.TargetOffset < 0) == Num(stats, "negativeOffsets") && rows.Count(x => x.TargetOffset == 0) == Num(stats, "zeroOffsets"), label + " signed/zero targets");
        Check(rows.Select(x => x.TargetOffset).Distinct().Count() == Num(stats, "distinctOffsets"), label + " duplicate offsets retained");
        if (rows.Length > 0) Check(rows.Min(x => x.TargetOffset) == Num(stats, "minimumOffset") && rows.Max(x => x.TargetOffset) == Num(stats, "maximumOffset"), label + " offset extrema");
        Check(rows.All(x => x.MinimumTargetBytes == Num(stats, "referentMinimumBytes")), label + " minimum target extent");
        Check(rows.Count(x => x.Status == AudioTargetStatus.Available) == Num(stats, "referentSpansInPhysicalLength"), label + " available extents");
        Check(rows.Count(x => x.WithinDeclaredSize) == Num(stats, "referentSpansInDeclaredLength"), label + " declared extents");
    }
    var seq = d.Rows.Where(x => x.TableKind == AudioTableKind.Sequence).ToArray();
    Check(seq.Count(x => x.SoundId.HasValue) == Num(expected, "interpretedSequenceHeaders"), label + " interpreted headers");
    Check(seq.Select(x => x.SoundId).Distinct().Count() == Num(expected, "uniqueSequenceIds"), label + " unique IDs");
    foreach (var e in expected.GetProperty("sequenceHeaders").EnumerateArray())
    {
        var actual = seq.Single(x => x.Ordinal == Num(e, "index"));
        Check(actual.TargetOffset == Num(e, "relativeOffset") && actual.SoundId == Num(e, "sequenceId") && actual.TrackReferenceCount == Num(e, "tracksInSequence"), label + " stored sequence fields");
        Check(actual.WithinDeclaredSize == Bool(e, "basicHeaderInDeclaredLength"), label + " sequence declared extent");
    }
    ++scds;
    samples.Add(new { label, context, format = "SCD", version = s.Version, s.BankId, d.AvailableLength, s.DeclaredSizeAt16, d.PhysicalMinusDeclared, rows = d.Rows.Count, d.MetadataBytesRead, metadataStatus = d.Status.ToString() });
}

async Task CheckOrigin(AssetPayload payload, JsonElement expected, string label, string context)
{
    var d = await AudioBankInspector.ReadAsync(reader, payload);
    Check(d.Format == AudioBankFormat.Origin && d.Status == AudioInspectionStatus.MetadataRead && !d.HitLimit, label + " origin status");
    var o = d.Origin ?? throw new InvalidDataException(label + " origin missing");
    Check(d.AvailableLength == 48 && o.NameTerminated && o.StoredMetadataAt12 == Num(expected, "fieldU32At12") && o.Name == Text(expected, "nameAt16"), label + " stored origin fields");
    Check(o.NameHex.Length / 2 == Num(expected, "nameByteLength"), label + " bounded origin name");
    Check(d.Rows.Count == 0 && d.Scd is null && d.Preview.Count == 48 && d.MetadataBytesRead == 48, label + " no runtime pointer traversal");
    ++origins; samples.Add(new { label, context, format = "ORIGIN", o.Name, o.StoredMetadataAt12, d.AvailableLength, d.MetadataBytesRead });
}

string Loose(string relative)
{
    string parent = Path.GetFullPath(Path.Combine(game, "Modding/openkh/data/kh2"));
    string result = Path.GetFullPath(Path.Combine(parent, relative));
    Check(result.StartsWith(parent + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase), "bounded explicit loose path");
    return result;
}

foreach (var e in witness.RootElement.GetProperty("results").EnumerateArray())
{
    string hed = Text(e, "hed"), name = Text(e, "asset");
    if (!indexes.TryGetValue(hed, out var index))
    {
        index = reader.OpenPackageIndex(Path.Combine(game, "Image/dt", hed)); indexes.Add(hed, index);
        var expected = witness.RootElement.GetProperty("indices").EnumerateArray().Single(x => Text(x, "hed") == hed);
        Check(index.HeaderSha256.Equals(Text(expected, "sha256"), StringComparison.OrdinalIgnoreCase), "same HED metadata");
    }
    var entry = index.Entries[checked((int)Num(e, "Ordinal"))];
    Check(entry.NameHash == Text(e, "NameHash") && entry.Offset == Num(e, "Offset") && entry.StoredLength == Num(e, "StoredLength"), "same selected package record");
    var package = reader.InspectPackageEntry(index, entry.Ordinal);
    var original = e.GetProperty("original"); var scd = original.GetProperty("scd");
    if (scd.ValueKind != JsonValueKind.Null)
    {
        await CheckScd(package.Original, scd, name, hed + ":original");
        await CheckScd(reader.OpenLooseFile(Loose(name)), scd, name, "loose");
    }
    var children = e.GetProperty("audioChildren").EnumerateArray().ToArray();
    if (children.Length > 0)
    {
        var bar = await reader.ReadBarAsync(package.Original);
        var looseBar = await reader.ReadBarAsync(reader.OpenLooseFile(Loose(name)));
        foreach (var child in children)
        {
            int ordinal = checked((int)Num(child, "Ordinal"));
            Check(bar.Entries[ordinal].Type == Num(child, "Type") && bar.Entries[ordinal].Length == 48, "same bounded BAR child");
            await CheckOrigin(bar.Entries[ordinal].Payload, child, name, hed + ":BAR");
            await CheckOrigin(looseBar.Entries[ordinal].Payload, child, name, "loose BAR");
        }
    }
    foreach (var remaster in e.GetProperty("audioRemasters").EnumerateArray())
    {
        int ordinal = checked((int)Num(remaster, "Ordinal")); var payload = package.Remastered.Single(x => x.Ordinal == ordinal);
        Check(payload.Name == Text(remaster, "Name"), "same audio remaster");
        var expected = remaster.GetProperty("scd");
        await CheckScd(payload.Payload, expected, payload.Name, hed + ":remaster");
        await CheckScd(reader.OpenLooseFile(Loose(Text(remaster.GetProperty("loose"), "relativePath"))), expected, payload.Name, "loose remaster");
    }
}
Check(scds == 26 && origins == 6, "All 13 SCD instances and 3 wrappers checked through package and loose contexts");
string[] names = ["AssetArchiveReader.cs", "AssetPackageCodec.cs", "AssetExplorerModels.cs", "AssetFileAccess.cs", "AudioBankInspection.cs"];
var fuzz = await BoundedInputReview.RunAsync();
var pins = names.ToDictionary(x => "src/KH2Trainer.Core/" + x, x => Hash(File.ReadAllBytes(Path.Combine(repo, "src/KH2Trainer.Core", x))));
var report = new { status = "PASS_BOUNDED_INSPECTOR_RETAIL_COMPARISON", checks, scdReads = scds, originReads = origins, fuzz, comparedWithFrozenWitnessSha256 = Hash(File.ReadAllBytes(witnessFile)), sourcePins = pins, samples,
    scope = "Public inspector API against previously frozen metadata: 12 selected archive records, 13 SCD instances and 3 ORIGIN wrappers, each also read through existing loose locators. Only metadata and inspector prefixes read; underlying package reader may decode an entire selected payload within 64 MiB. No writes to game assets, no payload exports, playback, native game execution or runtime pointer access.",
    limits = "This comparison checks metadata, not every stored byte, codec or track. Existing original witness records establish prior complete package/loose equality. Current source identity and parent metadata are checked by the production reader." };
File.WriteAllText(Path.Combine(here, "review.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"PASS: {checks} retail checks, {scds} SCD reads, {origins} ORIGIN reads; {fuzz.Checks} bounded-input checks across {fuzz.Cases} synthetic inputs.");
