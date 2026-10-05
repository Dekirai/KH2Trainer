using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;
using KH2Trainer.Core;

internal static class AssetFingerprintTests
{
    public static async Task RunAsync(string workspace, Action<bool, string> check)
    {
        string folder = Path.Combine(workspace, "fingerprints-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder); int serial = 0;
        var reader = new AssetArchiveReader(); var service = new AssetFingerprintService();
        string Save(byte[] bytes, string extension = ".bin")
        { string path = Path.Combine(folder, $"source-{serial++}{extension}"); File.WriteAllBytes(path, bytes); return path; }
        AssetFingerprintSelection Loose(byte[] bytes, string label) => AssetFingerprintSelection.FromLoose(reader.OpenLooseFile(Save(bytes)), label);
        async Task Reject<T>(Func<Task> action, string name) where T : Exception
        { try { await action(); check(false, name); } catch (T) { check(true, name); } }
        async Task<string> Json(AssetFingerprintIndex index)
        { using var output = new MemoryStream(); await index.SaveAsync(output); return Encoding.UTF8.GetString(output.ToArray()); }
        async Task<AssetFingerprintIndex> Load(string json, AssetFingerprintLimits? limits = null)
        { using var input = new MemoryStream(Encoding.UTF8.GetBytes(json)); return await AssetFingerprintIndex.LoadAsync(input, limits); }

        var selected = Loose("abc"u8.ToArray(), "Original assets");
        var abc = await service.CaptureAsync(reader, selected);
        check(abc.Length == 3 && abc.Md5 == "900150983CD24FB0D6963F7D28E17F72" &&
            abc.Sha256 == "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD", "known independent abc MD5/SHA256 vectors");
        var empty = await service.CaptureAsync(reader, Loose([], "Empty assets"));
        check(empty.Md5 == "D41D8CD98F00B204E9800998ECF8427E" && empty.Sha256 == "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855", "empty payload hashes");
        var same = await service.CaptureAsync(reader, selected);
        check(abc.Id == same.Id && abc.Sha256 == same.Sha256, "same selected locator has stable identity");
        var otherLabel = await service.CaptureAsync(reader, AssetFingerprintSelection.FromLoose(selected.Payload, "Modified assets"));
        check(otherLabel.Id != abc.Id && otherLabel.Sha256 == abc.Sha256, "caller namespaces distinguish same payload observations");
        byte[] multiChunk = Enumerable.Range(0, 200_003).Select(i => (byte)(i * 31)).ToArray();
        var large = await service.CaptureAsync(reader, Loose(multiChunk, "Large fixture"));
        check(large.Md5 == Convert.ToHexString(MD5.HashData(multiChunk)) && large.Sha256 == Convert.ToHexString(SHA256.HashData(multiChunk)), "multiple streaming chunks hash every byte once");
        await Reject<InvalidDataException>(async () => await new AssetFingerprintService(new() { MaximumPayloadBytes = 2 }).CaptureAsync(reader, selected), "payload byte limit applies before read");
        await Reject<OperationCanceledException>(async () => await service.CaptureAsync(reader, selected, new(true)), "capture honors pre-cancellation");
        foreach (string bad in new[] { "", " ", "../x", @"\\server\share", "C:drive", "x\ny", "..", new string('x', 513) })
            await Reject<InvalidDataException>(() => { AssetFingerprintSelection.FromLoose(selected.Payload, bad); return Task.CompletedTask; }, "source label is descriptive and bounded: " + bad.Length);

        byte[] nested = Bar([("DUPL", "abc"u8.ToArray()), ("DUPL", "abc"u8.ToArray())]);
        // Turn the second entry into an alias of the first without changing its ordinal.
        Write32(nested, 40, Read32(nested, 24));
        byte[] outer = Bar([("same", nested), ("same", nested)]);
        var root = Loose(outer, "Nested archive"); var outerBar = await reader.ReadBarAsync(root.Payload);
        var first = root.Child(outerBar.Entries[0]); var second = root.Child(outerBar.Entries[1]);
        var firstBar = await reader.ReadBarAsync(first.Payload); var secondBar = await reader.ReadBarAsync(second.Payload);
        var a = await service.CaptureAsync(reader, first.Child(firstBar.Entries[0]));
        var alias = await service.CaptureAsync(reader, first.Child(firstBar.Entries[1]));
        var b = await service.CaptureAsync(reader, second.Child(secondBar.Entries[0]));
        check(a.Path.Count == 3 && a.Path[1].Ordinal == 0 && a.Path[2].Ordinal == 0, "all nested BAR ancestors retained");
        check(a.Id != alias.Id && a.Sha256 == alias.Sha256 && firstBar.Entries[1].AliasOf == 0, "same-span BAR aliases remain distinct identities");
        check(a.Id != b.Id && a.Sha256 == b.Sha256, "same nested tag/ordinal in different parents remains distinct");
        check(a.Sha256 == abc.Sha256 && a.Length == 3, "only selected payload bytes are hashed, not container bytes");
        await Reject<ArgumentException>(() => { first.Child(secondBar.Entries[0]); return Task.CompletedTask; }, "child from another parent rejected");
        await Reject<ArgumentException>(() => { first.Child(firstBar.Entries[0] with { Ordinal = 99 }); return Task.CompletedTask; }, "forged BAR ordinal rejected");
        await Reject<ArgumentException>(() => { AssetFingerprintSelection.FromLoose(first.Payload, "child"); return Task.CompletedTask; }, "BAR child cannot be mislabeled as a loose root");
        await Reject<InvalidDataException>(async () => await new AssetFingerprintService(new() { MaximumPathParts = 2 }).CaptureAsync(reader, first.Child(firstBar.Entries[0])), "configured nested path limit");
        byte[] zeroBar = Bar([("ZERO", Array.Empty<byte>())]); Write32(zeroBar, 24, -1);
        var zeroSelection = Loose(zeroBar, "Empty entry"); var zero = await reader.ReadBarAsync(zeroSelection.Payload);
        var zeroHash = await service.CaptureAsync(reader, zeroSelection.Child(zero.Entries[0]));
        check(zeroHash.Length == 0 && zeroHash.Path[^1].Offset == uint.MaxValue && zeroHash.Sha256 == empty.Sha256, "empty BAR sentinel preserved without reading outside source");
        await Reject<ArgumentException>(() => { zeroSelection.Child(zero.Entries[0] with { RelativeOffset = 123 }); return Task.CompletedTask; }, "forged empty BAR raw offset rejected");

        // Two HED aliases to one record and two empty remasters with equal stored offsets/names.
        byte[] record = new byte[128]; Write32(record, 0, 4); Write32(record, 4, 2); Write32(record, 8, -2);
        Encoding.ASCII.GetBytes("same").CopyTo(record, 16); Write32(record, 60, -2);
        Encoding.ASCII.GetBytes("same").CopyTo(record, 64); Write32(record, 108, -2);
        "base"u8.CopyTo(record.AsSpan(112));
        byte[] hed = new byte[64];
        for (int offset = 0; offset < 64; offset += 32)
        { MD5.HashData("test.bin"u8).CopyTo(hed, offset); Write32(hed, offset + 24, record.Length); Write32(hed, offset + 28, 4); }
        string hedPath = Save(hed, ".hed"); File.WriteAllBytes(Path.ChangeExtension(hedPath, ".pkg"), record);
        var package = reader.OpenPackageIndex(hedPath); var pa = reader.InspectPackageEntry(package, 0); var pb = reader.InspectPackageEntry(package, 1);
        var original = await service.CaptureAsync(reader, AssetFingerprintSelection.FromPackage(package, pa, "Retail package"));
        var hedAlias = await service.CaptureAsync(reader, AssetFingerprintSelection.FromPackage(package, pb, "Retail package"));
        var remaster0 = await service.CaptureAsync(reader, AssetFingerprintSelection.FromPackage(package, pa, "Retail package", 0));
        var remaster1 = await service.CaptureAsync(reader, AssetFingerprintSelection.FromPackage(package, pa, "Retail package", 1));
        check(original.Sha256 == Convert.ToHexString(SHA256.HashData("base"u8)) && original.Path[0].Kind == AssetSourceKind.PackageOriginal, "retail original hashes decoded payload only");
        check(original.Id != hedAlias.Id && original.Sha256 == hedAlias.Sha256, "HED alias ordinals remain distinct");
        check(remaster0.Id != remaster1.Id && remaster0.Sha256 == empty.Sha256 && remaster0.Path[0].StoredOffset == remaster1.Path[0].StoredOffset, "equal empty remaster spans/names remain distinct by ordinal");
        check(original.Id != remaster0.Id, "original and remastered identities differ");
        var forged = pa with { Remastered = [pa.Remastered[1] with { Ordinal = 0 }] };
        await Reject<ArgumentException>(() => { AssetFingerprintSelection.FromPackage(package, forged, "forged", 0); return Task.CompletedTask; }, "forged remaster ordinal rejected by immutable payload ordinal");
        await Reject<ArgumentException>(() => { AssetFingerprintSelection.FromPackage(package, pa with { Original = pb.Original }, "forged"); return Task.CompletedTask; }, "same-span HED alias cannot be substituted for another entry");
        await Reject<ArgumentOutOfRangeException>(() => { AssetFingerprintSelection.FromPackage(package, pa, "bad", 2); return Task.CompletedTask; }, "invalid remaster ordinal rejected");
        var otherIndex = reader.OpenPackageIndex(hedPath);
        await Reject<ArgumentException>(() => { AssetFingerprintSelection.FromPackage(otherIndex, pa, "bad"); return Task.CompletedTask; }, "entry from another index object rejected");

        var index = AssetFingerprintIndex.Create([abc, otherLabel, a, alias, b, empty, original, remaster0, remaster1]);
        check(index.FindMatches(abc).Count == 5 && index.FindMatches(abc).All(m => m.Kind == AssetFingerprintMatchKind.Sha256AndLength), "normal matching preserves every equal-content locator");
        check(index.With(same).Entries.Count == index.Entries.Count, "With replaces an existing identity explicitly");
        check(index.With(large).Entries.Count == index.Entries.Count + 1 && index.Entries.Count == 9, "With returns a new immutable index");
        await Reject<InvalidDataException>(() => { AssetFingerprintIndex.Create([abc, same]); return Task.CompletedTask; }, "duplicate locator on creation rejected");
        await Reject<InvalidDataException>(() => { AssetFingerprintIndex.Create([abc, otherLabel], new() { MaximumEntries = 1 }); return Task.CompletedTask; }, "index creation count bound");
        await Reject<InvalidDataException>(() => { AssetFingerprintIndex.Create([abc], new() { MaximumEntries = 1 }).With(otherLabel); return Task.CompletedTask; }, "With count bound");

        string json = await Json(index); var loaded = await Load(json);
        check(loaded.Entries.Count == index.Entries.Count && loaded.Entries[2].Id == a.Id && loaded.Entries[2].Path.SequenceEqual(a.Path), "portable JSON round trip preserves nested identity");
        check(!json.Contains(folder.Replace("\\", "\\\\"), StringComparison.OrdinalIgnoreCase) && !json.Contains("SourcePath"), "portable index contains no local filesystem locator");
        check(loaded.FindMatches(abc).Count == 5, "matching after load is unchanged");
        using (var memory = new MemoryStream()) { await index.SaveAsync(memory); check(memory.CanWrite, "save leaves caller stream open"); memory.Position = 0; await AssetFingerprintIndex.LoadAsync(memory); check(memory.CanRead, "load leaves caller stream open"); }
        var legacy = JsonNode.Parse(await Json(AssetFingerprintIndex.Create([otherLabel])))!;
        legacy["Entries"]![0]!["Sha256"] = new string('0', 64);
        var legacyIndex = await Load(legacy.ToJsonString());
        check(legacyIndex.FindMatches(abc).Count == 0 && legacyIndex.FindMatches(abc, true).Single().Kind == AssetFingerprintMatchKind.LegacyMd5AndLength, "MD5-only match is explicitly optional and distinctly labeled");

        foreach (var mutation in new (string Name, Action<JsonNode> Change)[]
        {
            ("unknown version", n => n["Version"] = 99), ("unknown format", n => n["Format"] = "Other"),
            ("missing version", n => n.AsObject().Remove("Version")), ("unknown root property", n => n["Extra"] = true),
            ("null entries", n => n["Entries"] = null), ("entries wrong type", n => n["Entries"] = 3),
            ("null entry", n => n["Entries"]![0] = null), ("negative length", n => n["Entries"]![0]!["Length"] = -1),
            ("missing length", n => n["Entries"]![0]!.AsObject().Remove("Length")),
            ("missing zero offset", n => n["Entries"]![0]!["Path"]![0]!.AsObject().Remove("Offset")),
            ("wrong MD5", n => n["Entries"]![0]!["Md5"] = "not a digest"), ("null SHA256", n => n["Entries"]![0]!["Sha256"] = null),
            ("wrong identity", n => n["Entries"]![0]!["Id"] = new string('F', 64)), ("null source", n => n["Entries"]![0]!["SourceKey"] = null),
            ("UNC source", n => n["Entries"]![0]!["SourceKey"] = @"\\server\share"),
            ("null path", n => n["Entries"]![0]!["Path"] = null), ("empty path", n => n["Entries"]![0]!["Path"] = new JsonArray()),
            ("null path part", n => n["Entries"]![0]!["Path"]![0] = null), ("wrong enum", n => n["Entries"]![0]!["Path"]![0]!["Kind"] = "Other"),
            ("numeric enum", n => n["Entries"]![0]!["Path"]![0]!["Kind"] = 0),
            ("null metadata hash", n => n["Entries"]![0]!["Path"]![0]!["MetadataSha256"] = null),
            ("oversized name", n => n["Entries"]![0]!["Path"]![0]!["Name"] = new string('n', 1025)),
            ("invalid loose ordinal", n => n["Entries"]![0]!["Path"]![0]!["Ordinal"] = 1),
            ("duplicate identity", n => n["Entries"]!.AsArray().Add(n["Entries"]![0]!.DeepClone())),
        })
        { var node = JsonNode.Parse(json)!; mutation.Change(node); await Reject<InvalidDataException>(async () => await Load(node.ToJsonString()), "malformed JSON rejected: " + mutation.Name); }
        await Reject<InvalidDataException>(async () => await Load(json.Replace("\"Version\": 1", "\"Version\": 1, \"Version\": 1")), "duplicate JSON property rejected");
        await Reject<InvalidDataException>(async () => await Load(json[..^2]), "truncated JSON rejected");
        await Reject<InvalidDataException>(async () => await Load("null"), "null JSON root rejected");
        await Reject<InvalidDataException>(async () => await Load(json, new() { MaximumEntries = 1 }), "load count bound before record materialization");
        await Reject<InvalidDataException>(async () => await Load(json, new() { MaximumPathParts = 2 }), "load nesting bound");
        using (var output = new MemoryStream())
        {
            var small = AssetFingerprintIndex.Create([abc], new() { MaximumJsonBytes = 256 });
            await Reject<InvalidDataException>(() => small.SaveAsync(output), "save bound rejects before writing destination");
            check(output.Length == 0, "failed bounded serialization leaves destination untouched");
        }
        using (var input = new ObservedReadStream(Encoding.UTF8.GetBytes(json)))
        {
            await Reject<InvalidDataException>(async () => await AssetFingerprintIndex.LoadAsync(input, new() { MaximumJsonBytes = 256 }), "nonseekable oversized input rejected");
            check(input.BytesRead == 257, "oversized read consumes at most one byte past its limit");
        }
        using (var cancelled = new CancellationTokenSource())
        using (var input = new ObservedReadStream(Encoding.UTF8.GetBytes(json), () => cancelled.Cancel()))
        { await Reject<OperationCanceledException>(async () => await AssetFingerprintIndex.LoadAsync(input, cancellationToken: cancelled.Token), "load mid-stream cancellation"); check(input.CanRead, "cancellation leaves caller input open"); }
        using (var output = new MemoryStream())
        { await Reject<OperationCanceledException>(() => index.SaveAsync(output, new(true)), "save pre-cancellation"); check(output.Length == 0, "cancelled save wrote no bytes"); }
        File.AppendAllText(selected.Payload.SourcePath, "changed");
        await Reject<IOException>(async () => await service.CaptureAsync(reader, selected), "stale source identity is rejected by existing asset reader");
        check((await Load(json)).Entries.Count == 9, "loading saved locators does not open modified/deleted source files");
        string exports = Path.Combine(folder, "exports"); Directory.CreateDirectory(exports);
        string indexPath = Path.Combine(exports, "new-index.json");
        await AssetFingerprintFiles.SaveNewAsync(index, indexPath, []);
        check((await AssetFingerprintFiles.LoadAsync(indexPath)).Entries.Count == 9, "explicit local file index save/load");
        byte[] saved = File.ReadAllBytes(indexPath);
        await Reject<IOException>(() => AssetFingerprintFiles.SaveNewAsync(index, indexPath, []), "existing index file is not overwritten");
        check(saved.SequenceEqual(File.ReadAllBytes(indexPath)), "existing destination bytes remain unchanged");
        await Reject<IOException>(() => AssetFingerprintFiles.SaveNewAsync(index, Path.Combine(exports, "protected.json"), [exports]), "protected destination folder rejected");
        var shortBuffer = new StringBuilder(4096); uint shortLength = GetShortPathName(exports, shortBuffer, (uint)shortBuffer.Capacity);
        if (shortLength > 0 && shortLength < shortBuffer.Capacity && !shortBuffer.ToString().Equals(exports, StringComparison.OrdinalIgnoreCase))
        {
            await Reject<IOException>(() => AssetFingerprintFiles.SaveNewAsync(index, Path.Combine(shortBuffer.ToString(), "alias-index.json"), [exports]), "8.3 alias cannot bypass protected destination folder");
            check(!File.Exists(Path.Combine(exports, "alias-index.json")), "short-path alias created no protected file");
        }
        await Reject<IOException>(() => AssetFingerprintFiles.SaveNewAsync(index, Path.Combine(exports, "NUL.json"), []), "device basename rejected");
        await Reject<IOException>(() => AssetFingerprintFiles.SaveNewAsync(index, Path.Combine(exports, "trailing. "), []), "trailing Windows filename alias rejected");
        await Reject<IOException>(() => AssetFingerprintFiles.SaveNewAsync(index, @"\\server\share\index.json", []), "network destination rejected without opening it");
        await Reject<IOException>(async () => await AssetFingerprintFiles.LoadAsync(@"\\server\share\index.json"), "network index source rejected without opening it");
        await Reject<OperationCanceledException>(() => AssetFingerprintFiles.SaveNewAsync(index, Path.Combine(exports, "cancelled.json"), [], new(true)), "file save cancellation before publication");
        var tiny = AssetFingerprintIndex.Create([abc], new() { MaximumJsonBytes = 256 });
        await Reject<InvalidDataException>(() => AssetFingerprintFiles.SaveNewAsync(tiny, Path.Combine(exports, "too-large.json"), []), "failed serialization has no published file");
        check(Directory.GetFiles(exports).Length == 1 && !Directory.GetFiles(exports, "*.tmp").Any(), "cancelled/failed file saves clean up only their own temp files");
    }

    public static async Task RunRealAsync(string sourcePath, Action<bool, string> check)
    {
        var reader = new AssetArchiveReader(); var service = new AssetFingerprintService();
        var root = AssetFingerprintSelection.FromLoose(reader.OpenLooseFile(sourcePath), Path.GetFileName(sourcePath));
        var bar = await reader.ReadBarAsync(root.Payload);
        foreach (var entry in bar.Entries.Where(e => e.Length > 0).Take(3))
        {
            var result = await service.CaptureAsync(reader, root.Child(entry));
            byte[] original = File.ReadAllBytes(sourcePath);
            byte[] slice = original.AsSpan(checked((int)entry.RelativeOffset), checked((int)entry.Length)).ToArray();
            check(result.Length == slice.Length && result.Md5 == Convert.ToHexString(MD5.HashData(slice)) &&
                result.Sha256 == Convert.ToHexString(SHA256.HashData(slice)), "real BAR independent raw byte slice: " + entry.Tag);
        }
    }

    private static int Read32(byte[] bytes, int offset) => BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(offset));
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "GetShortPathNameW")]
    private static extern uint GetShortPathName(string path, StringBuilder output, uint capacity);
    private static void Write32(byte[] bytes, int offset, int value) => BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(offset), value);
    private static byte[] Bar((string Tag, byte[] Bytes)[] entries)
    {
        int dataOffset = 16 + entries.Length * 16; byte[] result = new byte[dataOffset + entries.Sum(e => e.Bytes.Length)];
        "BAR\x01"u8.CopyTo(result); Write32(result, 4, entries.Length);
        for (int i = 0; i < entries.Length; i++)
        {
            int p = 16 + i * 16; BinaryPrimitives.WriteUInt16LittleEndian(result.AsSpan(p), 9);
            Encoding.ASCII.GetBytes(entries[i].Tag).CopyTo(result, p + 4); Write32(result, p + 8, dataOffset); Write32(result, p + 12, entries[i].Bytes.Length);
            entries[i].Bytes.CopyTo(result, dataOffset); dataOffset += entries[i].Bytes.Length;
        }
        return result;
    }
    private sealed class ObservedReadStream(byte[] bytes, Action? afterRead = null) : Stream
    {
        public int BytesRead { get; private set; }
        public override bool CanRead => true; public override bool CanSeek => false; public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count)
        { int n = Math.Min(count, bytes.Length - BytesRead); bytes.AsSpan(BytesRead, n).CopyTo(buffer.AsSpan(offset)); BytesRead += n; afterRead?.Invoke(); return n; }
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        { cancellationToken.ThrowIfCancellationRequested(); int n = Math.Min(buffer.Length, bytes.Length - BytesRead); bytes.AsMemory(BytesRead, n).CopyTo(buffer); BytesRead += n; afterRead?.Invoke(); return ValueTask.FromResult(n); }
        public override void Flush() => throw new NotSupportedException(); public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException(); public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
}
