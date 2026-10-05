using System.Buffers.Binary;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using KH2Trainer.Core;
using Microsoft.Win32.SafeHandles;

internal static class AssetExplorerTests
{
    // Fixed, independently generated synthetic vectors. These contain no game assets.
    private const string Compressed = "a401000000000000300000007b0000008a45ffa3bd47873e5831daefa8341cdb5ef125c1bc591d020c7136551a6678ad7c9cc1213b41833fdea9e7d455ab99dd";
    private const string Transformed17 = "1100000000000000ffffffff7b000000d6bb017b0631df15d8b488ada235f8f910";
    private const string Remastered = "0400000002000000feffffff7b0000002e2e2f434f4e2e64647300000000000000000000000000000000000000000000f0ffffff0000002021000000ffffffff2d312e6464730000000000000000000000000000000000000000000000000000f0ffffff10000020900100001000000062617365cdcdcdcdcdcdcdcdcdcdcdcdec966cd2493cf58ef040e93e40e36051fc867cc2592ce59ee050c3106ec94a6747cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdf568843c365f11ef992aa900a12cc2ec";

    public static async Task RunAsync(string workspace, Action<bool, string> check)
    {
        string folder = Path.Combine(workspace, "assets"); Directory.CreateDirectory(folder);
        string outputs = Path.Combine(folder, "exports"); Directory.CreateDirectory(outputs);
        var reader = new AssetArchiveReader();
        var cancelled = new CancellationToken(canceled: true);
        int serial = 0;
        string Save(byte[] bytes, string extension = ".bin")
        { string path = Path.Combine(folder, $"fixture-{serial++}{extension}"); File.WriteAllBytes(path, bytes); return path; }
        async Task Reject<T>(Func<Task> action, string message) where T : Exception
        {
            try { await action(); check(false, message); }
            catch (T) { check(true, message); }
        }
        async Task RejectData(Func<Task> action, string message)
        {
            try { await action(); check(false, message); }
            catch (Exception e) when (e is InvalidDataException or EndOfStreamException) { check(true, message); }
        }
        async Task<byte[]> Read(AssetPayload payload)
        { await using var input = await reader.OpenReadAsync(payload); using var output = new MemoryStream(); await input.CopyToAsync(output); return output.ToArray(); }
        (string Path, PackageIndex Index) Pair(byte[] record, string name = "folder/test.bin", long offset = 0)
        {
            string path = Save(Hed(name, offset, record.Length, I32(record, 0)), ".hed");
            using (var pkg = new FileStream(Path.ChangeExtension(path, ".pkg"), FileMode.CreateNew, FileAccess.Write))
            {
                if (offset > 1024 * 1024) MakeSparse(pkg);
                pkg.Position = offset; pkg.Write(record);
            }
            return (path, reader.OpenPackageIndex(path));
        }

        byte[] leaf = Bar([(9, 0, "MOTN", new byte[] { 0, 1, 2, 3 })]);
        byte[] outer = Bar([(17, 0, "ANB\0", leaf), (2, 0, "LIST", new byte[] { 5, 6, 7 })]);
        var payload = reader.OpenLooseFile(Save(outer, ".mset"));
        var bar = await reader.ReadBarAsync(payload);
        check(bar.VersionFlags == 1 && bar.RuntimeBase == 0 && bar.Entries.Count == 2, "BAR disk header and two entries parsed");
        check(bar.Entries[0].Type == 17 && bar.Entries[0].TagHex == "414E4200" && bar.Entries[0].Tag == "ANB\\x00", "BAR tag bytes remain exact, including NUL");
        var inner = await reader.ReadBarAsync(bar.Entries[0].Payload);
        check((await Read(inner.Entries[0].Payload)).SequenceEqual(new byte[] { 0, 1, 2, 3 }), "nested BAR offsets are relative to the nested container");
        check((await reader.ReadPrefixAsync(payload, 4)).SequenceEqual("BAR\x01"u8.ToArray()), "prefix reads return only the requested bounded range");
        check(AssetArchiveReader.Recognize(await reader.ReadPrefixAsync(payload, 4)) == "BAR container", "BAR signature recognizer");
        check(AssetArchiveReader.Recognize("DDS "u8) == "DDS texture" && AssetArchiveReader.Recognize("TIM2"u8) == "TIM2 texture" &&
              AssetArchiveReader.Recognize(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 }) == "PNG image", "texture signature recognition is distinct from payload validation");
        check(AssetArchiveReader.Recognize("B"u8) == "Binary data", "short/unknown signatures stay generic");
        check(AssetArchiveReader.TypeName(2).Contains("context") && AssetArchiveReader.TypeName(60000).Contains("60000"), "generic and unknown BAR types are preserved honestly");
        await using (var stream = await reader.OpenReadAsync(inner.Entries[0].Payload))
        {
            stream.Position = stream.Length - 1; byte[] bytes = new byte[8];
            check(await stream.ReadAsync(bytes) == 1 && bytes[0] == 3 && await stream.ReadAsync(bytes) == 0, "payload stream cannot cross its declared boundary");
            await Reject<InvalidDataException>(() => { stream.Position = stream.Length + 1; return Task.CompletedTask; }, "seek beyond payload boundary rejected");
            await Reject<NotSupportedException>(() => { stream.WriteByte(1); return Task.CompletedTask; }, "payload streams are read-only");
            await Reject<OperationCanceledException>(async () => { await stream.ReadAsync(bytes, cancelled); }, "bounded stream honors cancellation");
        }

        byte[] aliases = Bar([(9, 0, "same", new byte[] { 7, 8 }), (9, 1, "same", new byte[] { 7, 8 })]);
        Write32(aliases, 40, I32(aliases, 24));
        var aliasBar = await reader.ReadBarAsync(reader.OpenLooseFile(Save(aliases)));
        check(aliasBar.Entries[1].AliasOf == 0 && aliasBar.Entries[1].LinkIndex == 1 &&
              (await Read(aliasBar.Entries[1].Payload)).SequenceEqual(new byte[] { 7, 8 }), "linked BAR spans and duplicate tags are accepted and identified");
        byte[] empty = Bar([(0, 1, "none", Array.Empty<byte>())]); Write32(empty, 24, -1);
        var emptyBar = await reader.ReadBarAsync(reader.OpenLooseFile(Save(empty)));
        check((await Read(emptyBar.Entries[0].Payload)).Length == 0 && emptyBar.Entries[0].RelativeOffset == uint.MaxValue, "empty BAR sentinel is preserved without seeking");
        byte[] weirdTag = Bar([(65535, 0, "abcd", new byte[] { 9 })]); weirdTag[20] = 0xff; weirdTag[21] = (byte)'/';
        var weird = (await reader.ReadBarAsync(reader.OpenLooseFile(Save(weirdTag)))).Entries[0];
        check(weird.TagHex.StartsWith("FF2F") && !weird.SuggestedFileName.Contains('/') && !weird.SuggestedFileName.Contains('\\'), "untrusted tag bytes cannot become extraction paths");
        foreach (var test in new (string Label, Action<byte[]> Mutate)[]
        {
            ("negative count", b => Write32(b, 4, -1)), ("huge count", b => Write32(b, 4, int.MaxValue)),
            ("span beyond file", b => Write32(b, 24, int.MaxValue)), ("overflowing span", b => { Write32(b, 24, -16); Write32(b, 28, -1); }),
            ("table overlap", b => Write32(b, 24, 16)), ("nonempty sentinel", b => Write32(b, 24, -1)),
            ("unsupported version", b => b[3] = 2), ("relocated runtime base", b => Write32(b, 8, 1))
        })
        {
            byte[] bad = (byte[])leaf.Clone(); test.Mutate(bad);
            await Reject<InvalidDataException>(async () => { await reader.ReadBarAsync(reader.OpenLooseFile(Save(bad))); }, "BAR rejects " + test.Label);
        }
        foreach (int length in new[] { 0, 3, 15, 17, 31 })
            await Reject<InvalidDataException>(async () => { await reader.ReadBarAsync(reader.OpenLooseFile(Save(leaf[..length]))); }, "BAR rejects truncation at " + length);
        var shallow = new AssetArchiveReader(new() { MaximumDepth = 1 });
        var shallowBar = await shallow.ReadBarAsync(payload);
        await Reject<InvalidDataException>(async () => { await shallow.ReadBarAsync(shallowBar.Entries[0].Payload); }, "nested BAR depth budget enforced");
        var small = new AssetArchiveReader(new() { MaximumBarEntries = 1 });
        await Reject<InvalidDataException>(async () => { await small.ReadBarAsync(payload); }, "BAR entry budget enforced");
        await Reject<OperationCanceledException>(async () => { await reader.ReadBarAsync(payload, cancelled); }, "BAR cancellation before opening");
        await Reject<ArgumentOutOfRangeException>(async () => { await reader.ReadPrefixAsync(payload, 1048577); }, "preview size budget enforced");

        var rawPair = Pair(RawRecord(outer));
        var rawInfo = reader.InspectPackageEntry(rawPair.Index, 0);
        check((await Read(rawInfo.Original)).SequenceEqual(outer) && rawInfo.Remastered.Count == 0, "raw retail record decodes exactly");
        check((await reader.ReadBarAsync(rawInfo.Original)).Entries.Count == 2, "retail original opens through the same BAR API");
        check(!rawPair.Index.Entries[0].HasResolvedName && rawPair.Index.Entries[0].Name.EndsWith(".dat"), "unknown name hashes remain visible");
        string names = Save(Encoding.UTF8.GetBytes("folder/test.bin\nwrong/name\n"), ".txt");
        var named = reader.OpenPackageIndex(rawPair.Path, names);
        check(named.Entries[0].HasResolvedName && named.Entries[0].Name == "folder/test.bin", "only exact MD5-matched dictionary names are resolved");
        var encrypted = Pair(Convert.FromHexString(Transformed17));
        check((await Read(reader.InspectPackageEntry(encrypted.Index, 0).Original)).SequenceEqual(Enumerable.Range(0, 17).Select(i => (byte)i)), "prefix transform preserves the incomplete final block");
        var compressed = Pair(Convert.FromHexString(Compressed));
        byte[] expected = Encoding.ASCII.GetBytes(string.Concat(Enumerable.Repeat("Offline KH2 fixture. ", 20)));
        check((await Read(reader.InspectPackageEntry(compressed.Index, 0).Original)).SequenceEqual(expected), "fixed transformed zlib vector decodes with exact length and checksum");
        foreach (var broken in new (string Label, string Hex)[]
        {
            ("decoded output exceeds declared length", "a301000000000000220000007b0000008defff07d1a52b714ad3daa03d3a5244595b2565d0bbb14d1e93361a8f6836328e45"),
            ("decoded output shorter than declared length", "a501000000000000220000007b0000008b72ffadb3a52bdb4ad3da0af0f285735fc625cfb2bbb1e71e9336b042a0e1058e45"),
            ("truncated zlib trailer despite complete decoded bytes", "a4010000000000001e0000007b0000008a7cffee824375bb7635da6a7d55d3cfac28292d4ad553f01f151c4c8200"),
            ("padding larger than alignment allowance", "a401000000000000320000007b0000008a44ff47b719a3175a6fdac63da42ea15ef02525b607392b0e2f367c8ff64ad77c9dc1c5311fa716dcf7e7fdc03baba7cdcd"),
        })
        {
            var info = reader.InspectPackageEntry(Pair(Convert.FromHexString(broken.Hex)).Index, 0);
            await RejectData(async () => { await Read(info.Original); }, broken.Label);
        }
        var unpadded = Pair(Convert.FromHexString("a401000000000000220000007b0000008a67ff3ed7a52b484ad3da9991c66dd95ed3255cd6bbb1741e933623239409af8e45"));
        check((await Read(reader.InspectPackageEntry(unpadded.Index, 0).Original)).SequenceEqual(expected), "non-aligned compressed payload supports an untouched partial transform tail");
        byte[] tiny = RawRecord(Enumerable.Range(0, 16).Select(i => (byte)i).ToArray()); Write32(tiny, 8, -1);
        check((await Read(reader.InspectPackageEntry(Pair(tiny).Index, 0).Original)).SequenceEqual(tiny[16..]), "native small-payload transform bypass is preserved");
        var extras = reader.InspectPackageEntry(Pair(Convert.FromHexString(Remastered)).Index, 0);
        check(extras.Remastered.Count == 2 && extras.Remastered[0].LogicalOffset == 0xfffffff0 && extras.Remastered[0].StoredOffset == 128, "remaster physical offsets are recomputed rather than taken from disk logical offsets");
        check((await Read(extras.Original)).SequenceEqual("base"u8.ToArray()) &&
              (await Read(extras.Remastered[0].Payload)).SequenceEqual(Encoding.ASCII.GetBytes("abcdefghijklmnopqrstuvwxyzABCDEFG")), "raw original plus transformed padded remaster use distinct lengths");
        check((await Read(extras.Remastered[1].Payload)).SequenceEqual(Enumerable.Repeat((byte)'Z', 400)), "compressed remaster shares the original record's key seed");

        foreach (var test in new (string Label, Action<byte[]> Mutate)[]
        {
            ("negative decoded length", b => Write32(b, 0, -1)), ("oversized decoded length", b => Write32(b, 0, int.MaxValue)),
            ("negative remaster count", b => Write32(b, 4, -1)), ("oversized remaster count", b => Write32(b, 4, int.MaxValue)),
            ("unknown negative mode", b => Write32(b, 8, -3)), ("ambiguous zero mode", b => Write32(b, 8, 0)),
            ("stored span beyond record", b => Write32(b, 8, int.MaxValue)),
        })
        {
            byte[] bad = Convert.FromHexString(Compressed); test.Mutate(bad);
            await Reject<InvalidDataException>(() => { var p = Pair(bad); reader.InspectPackageEntry(p.Index, 0); return Task.CompletedTask; }, "package rejects " + test.Label);
        }
        byte[] truncatedMeta = Convert.FromHexString(Remastered)[..100];
        await Reject<InvalidDataException>(() => { reader.InspectPackageEntry(Pair(truncatedMeta).Index, 0); return Task.CompletedTask; }, "truncated remaster table rejected");
        byte[] badRemaster = Convert.FromHexString(Remastered); Write32(badRemaster, 56, int.MaxValue);
        await Reject<InvalidDataException>(() => { reader.InspectPackageEntry(Pair(badRemaster).Index, 0); return Task.CompletedTask; }, "oversized remaster rejected before allocation");
        var limited = new AssetArchiveReader(new() { MaximumDecodedBytes = 128 });
        await Reject<InvalidDataException>(() => { limited.InspectPackageEntry(compressed.Index, 0); return Task.CompletedTask; }, "package decoded allocation limit enforced");
        for (int i = 16; i < 24; i++)
        {
            byte[] corrupt = Convert.FromHexString(Compressed); corrupt[i] ^= 0x80;
            var info = reader.InspectPackageEntry(Pair(corrupt).Index, 0);
            await RejectData(async () => { await Read(info.Original); }, "corrupt transformed compressed data rejected at byte " + i);
        }
        byte[] badPadding = Convert.FromHexString(Compressed); badPadding[^1] ^= 1;
        await Reject<InvalidDataException>(async () => { await Read(reader.InspectPackageEntry(Pair(badPadding).Index, 0).Original); }, "non-padding data after zlib stream rejected");
        await Reject<OperationCanceledException>(() => { reader.OpenPackageIndex(rawPair.Path, cancellationToken: cancelled); return Task.CompletedTask; }, "index cancellation honored");
        await Reject<OperationCanceledException>(() => { reader.InspectPackageEntry(rawPair.Index, 0, cancelled); return Task.CompletedTask; }, "package inspection cancellation honored");
        await Reject<OperationCanceledException>(async () => { await reader.OpenReadAsync(rawInfo.Original, cancelled); }, "decode cancellation honored");

        foreach (var test in new (string Label, Action<byte[]> Mutate)[]
        {
            ("negative offset", b => BinaryPrimitives.WriteInt64LittleEndian(b.AsSpan(16), -1)),
            ("offset overflow", b => BinaryPrimitives.WriteInt64LittleEndian(b.AsSpan(16), long.MaxValue)),
            ("negative stored length", b => Write32(b, 24, -1)),
            ("negative original length", b => Write32(b, 28, -1)),
            ("stored span outside package", b => Write32(b, 24, int.MaxValue)),
        })
        {
            var pair = Pair(RawRecord(new byte[16])); byte[] bad = File.ReadAllBytes(pair.Path); test.Mutate(bad); File.WriteAllBytes(pair.Path, bad);
            await Reject<InvalidDataException>(() => { reader.OpenPackageIndex(pair.Path); return Task.CompletedTask; }, "HED rejects " + test.Label);
        }
        var shortHed = Pair(RawRecord(new byte[16])); File.AppendAllText(shortHed.Path, "x");
        await Reject<InvalidDataException>(() => { reader.OpenPackageIndex(shortHed.Path); return Task.CompletedTask; }, "HED length must be a multiple of32");
        var missing = Pair(RawRecord(new byte[16])); File.Delete(Path.ChangeExtension(missing.Path, ".pkg"));
        await Reject<FileNotFoundException>(() => { reader.OpenPackageIndex(missing.Path); return Task.CompletedTask; }, "missing companion PKG rejected");
        var placeholder = Pair(RawRecord(new byte[16])); byte[] zero = File.ReadAllBytes(placeholder.Path); Write32(zero, 24, 0); File.WriteAllBytes(placeholder.Path, zero);
        var placeholderIndex = reader.OpenPackageIndex(placeholder.Path);
        check(!placeholderIndex.Entries[0].IsAvailable, "zero stored-size placeholder remains in index");
        await Reject<InvalidDataException>(() => { reader.InspectPackageEntry(placeholderIndex, 0); return Task.CompletedTask; }, "placeholder cannot decode");
        var high = Pair(RawRecord(new byte[] { 1, 2, 3, 4 }), offset: (1L << 32) + 4096);
        check(high.Index.Entries[0].Offset > uint.MaxValue && (await Read(reader.InspectPackageEntry(high.Index, 0).Original)).SequenceEqual(new byte[] { 1, 2, 3, 4 }), "HED offsets beyond4GiB remain64-bit through actual payload reading");

        string mutablePath = Save(leaf); var stale = reader.OpenLooseFile(mutablePath);
        File.WriteAllBytes(mutablePath, new byte[leaf.Length + 1]);
        await Reject<IOException>(async () => { await reader.ReadPrefixAsync(stale); }, "changed source length invalidates locators");
        mutablePath = Save(leaf); stale = reader.OpenLooseFile(mutablePath); DateTime time = File.GetLastWriteTimeUtc(mutablePath);
        string replacement = Save(leaf); File.SetLastWriteTimeUtc(replacement, time); File.Move(replacement, mutablePath, true);
        await Reject<IOException>(async () => { await reader.ReadPrefixAsync(stale); }, "replacement with same length and timestamp is rejected by Windows file identity");
        var changedHed = Pair(RawRecord(leaf)); var stalePkg = reader.InspectPackageEntry(changedHed.Index, 0).Original;
        time = File.GetLastWriteTimeUtc(changedHed.Path); byte[] hedBytes = File.ReadAllBytes(changedHed.Path); hedBytes[0] ^= 1;
        File.WriteAllBytes(changedHed.Path, hedBytes); File.SetLastWriteTimeUtc(changedHed.Path, time);
        await Reject<IOException>(async () => { await reader.ReadPrefixAsync(stalePkg); }, "HED digest detects same-file same-timestamp metadata modification");
        var changedHeader = Pair(RawRecord(leaf)); var staleHeader = reader.InspectPackageEntry(changedHeader.Index, 0).Original;
        string pkgPath = Path.ChangeExtension(changedHeader.Path, ".pkg"); time = File.GetLastWriteTimeUtc(pkgPath);
        byte[] pkgBytes = File.ReadAllBytes(pkgPath); pkgBytes[12] ^= 1; File.WriteAllBytes(pkgPath, pkgBytes); File.SetLastWriteTimeUtc(pkgPath, time);
        await Reject<IOException>(async () => { await reader.ReadPrefixAsync(staleHeader); }, "package metadata digest detects changed record seed");
        string changedBarPath = Save(leaf); var changedBar = await reader.ReadBarAsync(reader.OpenLooseFile(changedBarPath));
        time = File.GetLastWriteTimeUtc(changedBarPath); byte[] changedTable = (byte[])leaf.Clone(); changedTable[20] ^= 1;
        File.WriteAllBytes(changedBarPath, changedTable); File.SetLastWriteTimeUtc(changedBarPath, time);
        await Reject<IOException>(async () => { await Read(changedBar.Entries[0].Payload); }, "BAR child locators revalidate the exact parent table even with restored timestamps");
        await Reject<IOException>(() => { reader.OpenLooseFile(@"\\.\pipe\kh2-test-must-not-open"); return Task.CompletedTask; }, "device and named-pipe sources rejected before opening");
        await using (var held = await reader.OpenReadAsync(payload))
            await Reject<IOException>(() => { using var write = new FileStream(payload.SourcePath, FileMode.Open, FileAccess.Write, FileShare.ReadWrite); return Task.CompletedTask; }, "open asset streams deny concurrent source writes");
        using (var released = new FileStream(payload.SourcePath, FileMode.Open, FileAccess.ReadWrite, FileShare.Read))
            check(released.Length == outer.Length, "disposing a payload stream releases its source handle");

        string destination = Path.Combine(outputs, "selected.bin");
        await reader.ExportAsync(inner.Entries[0].Payload, destination);
        check(File.ReadAllBytes(destination).SequenceEqual(new byte[] { 0, 1, 2, 3 }), "selected nested entry exported exactly to new destination");
        await Reject<IOException>(async () => { await reader.ExportAsync(payload, destination); }, "export never overwrites an existing destination");
        check(File.ReadAllBytes(destination).SequenceEqual(new byte[] { 0, 1, 2, 3 }), "failed overwrite preserves destination bytes");
        await Reject<IOException>(async () => { await reader.ExportAsync(payload, payload.SourcePath); }, "source file cannot be overwritten");
        foreach (string bad in new[] { "CON.bin", "aux", "COM1.txt", "COM¹.txt", "CON .txt", "slot.bin ", "slot.bin.", "slot.bin:stream" })
            await Reject<IOException>(async () => { await reader.ExportAsync(payload, Path.Combine(outputs, bad)); }, "unsafe extraction filename rejected: " + bad);
        var protectedReader = new AssetArchiveReader(protectedDirectories: [outputs]);
        await Reject<IOException>(async () => { await protectedReader.ExportAsync(payload, Path.Combine(outputs, "protected.bin")); }, "explicit protected directory prevents export");
        string fakeGame = Path.Combine(folder, "fake-game"); Directory.CreateDirectory(fakeGame);
        File.WriteAllBytes(Path.Combine(fakeGame, "KINGDOM HEARTS II FINAL MIX.exe"), []);
        File.WriteAllBytes(Path.Combine(fakeGame, "asset.bar"), leaf);
        await Reject<IOException>(async () => { await reader.ExportAsync(reader.OpenLooseFile(Path.Combine(fakeGame, "asset.bar")), Path.Combine(fakeGame, "new.bin")); }, "actual source game root is protected automatically");
        string cancelOut = Path.Combine(outputs, "cancelled.bin");
        await Reject<OperationCanceledException>(async () => { await reader.ExportAsync(payload, cancelOut, cancelled); }, "cancelled export creates no output");
        check(!File.Exists(cancelOut) && !Directory.EnumerateFiles(outputs, ".kh2-extract-*.tmp").Any(), "cancelled/error exports leave no owned temporary files");
        string bigPath = Path.Combine(folder, "large-sparse.bin");
        using (var big = new FileStream(bigPath, FileMode.CreateNew, FileAccess.Write)) { MakeSparse(big); big.SetLength(1L << 30); }
        using (var cancellation = new CancellationTokenSource())
        {
            cancellation.CancelAfter(10);
            await Reject<OperationCanceledException>(async () => { await reader.ExportAsync(reader.OpenLooseFile(bigPath), cancelOut, cancellation.Token); }, "in-flight large export observes cancellation");
        }
        check(!File.Exists(cancelOut) && !Directory.EnumerateFiles(outputs, ".kh2-extract-*.tmp").Any(), "in-flight cancellation removes only its temporary file");
        File.Delete(bigPath);
    }

    /// <summary>Optional read-only smoke tests. Never bundled with the shipped app.</summary>
    public static async Task RunRetailAsync(string gameRoot, Action<bool, string> check)
    {
        string looseRoot = Path.Combine(gameRoot, "Modding", "openkh", "data", "kh2");
        string names = Path.Combine(gameRoot, "Modding", "openkh", "resources", "kh2idx.txt");
        var reader = new AssetArchiveReader(protectedDirectories: [gameRoot]);
        string[] wanted = ["00battle.bin", "03system.bin", "00common.bdx", "00effect.bar", "00font.bar", "obj/P_EX100.mdlx", "obj/P_EX100.mset", "msg/us/sys.bar", "ard/us/tt00.ard"];
        foreach (string hed in Directory.EnumerateFiles(Path.Combine(gameRoot, "Image", "dt"), "kh2_*.hed").Order())
        {
            var index = reader.OpenPackageIndex(hed, names);
            check(index.Entries.Count > 0 && index.Entries.All(e => e.Offset >= 0), "retail index: " + Path.GetFileName(hed));
            foreach (var entry in index.Entries.Where(e => e.Ordinal < 3 || wanted.Contains(e.Name)))
            {
                var info = reader.InspectPackageEntry(index, entry.Ordinal);
                string loose = Path.Combine(looseRoot, entry.Name.Replace('/', Path.DirectorySeparatorChar));
                if (!File.Exists(loose)) throw new FileNotFoundException("Required private comparison asset is missing.", loose);
                await using var stream = await reader.OpenReadAsync(info.Original);
                await using var other = File.OpenRead(loose);
                check(await SameBytes(stream, other), "retail original equals loose bytes: " + entry.Name);
                foreach (var extra in info.Remastered)
                {
                    string remaster = Path.Combine(looseRoot, "remastered", entry.Name.Replace('/', Path.DirectorySeparatorChar), extra.Name);
                    if (!File.Exists(remaster)) throw new FileNotFoundException("Required private remaster comparison asset is missing.", remaster);
                    await using var decoded = await reader.OpenReadAsync(extra.Payload);
                    await using var original = File.OpenRead(remaster);
                    check(await SameBytes(decoded, original, extra.StoredMode is -1 or -2), "retail remaster equals logical loose bytes (separate optional alignment padding): " + entry.Name + "/" + extra.Name);
                }
            }
        }
    }
    private static async Task<bool> SameBytes(Stream a, Stream b, bool allowLoosePadding = false)
    {
        if (a.Length != b.Length && (!allowLoosePadding || b.Length != ((a.Length + 15) & ~15L))) return false;
        byte[] x = new byte[65536], y = new byte[65536];
        for (long offset = 0; offset < a.Length; offset += x.Length)
        {
            int count = (int)Math.Min(x.Length, a.Length - offset);
            await a.ReadExactlyAsync(x.AsMemory(0, count)); await b.ReadExactlyAsync(y.AsMemory(0, count));
            if (!x.AsSpan(0, count).SequenceEqual(y.AsSpan(0, count))) return false;
        }
        for (long i = a.Length; i < b.Length; i++) if (b.ReadByte() is not (0 or 0xCD)) return false;
        return true;
    }
    private static byte[] Bar((ushort Type, ushort Link, string Tag, byte[] Data)[] rows)
    {
        using var stream = new MemoryStream(); using var writer = new BinaryWriter(stream);
        writer.Write("BAR\x01"u8); writer.Write(rows.Length); writer.Write(0); writer.Write(0);
        int offset = 16 + 16 * rows.Length;
        foreach (var row in rows)
        { writer.Write(row.Type); writer.Write(row.Link); writer.Write(Encoding.ASCII.GetBytes(row.Tag)); writer.Write(offset); writer.Write(row.Data.Length); offset += row.Data.Length; }
        foreach (var row in rows) writer.Write(row.Data);
        return stream.ToArray();
    }
    private static byte[] RawRecord(byte[] bytes)
    { byte[] record = new byte[16 + bytes.Length]; Write32(record, 0, bytes.Length); Write32(record, 8, -2); bytes.CopyTo(record, 16); return record; }
    private static byte[] Hed(string name, long offset, int stored, int actual)
    { byte[] hed = new byte[32]; MD5.HashData(Encoding.UTF8.GetBytes(name)).CopyTo(hed, 0); BinaryPrimitives.WriteInt64LittleEndian(hed.AsSpan(16), offset); Write32(hed, 24, stored); Write32(hed, 28, actual); return hed; }
    private static int I32(byte[] bytes, int offset) => BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(offset));
    private static void Write32(byte[] bytes, int offset, int value) => BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(offset), value);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool DeviceIoControl(SafeFileHandle file, uint code, nint input, uint inputSize, nint output, uint outputSize, out uint bytes, nint overlapped);
    private static void MakeSparse(FileStream stream)
    {
        if (!DeviceIoControl(stream.SafeFileHandle, 0x900C4, 0, 0, 0, 0, out _, 0))
            throw new IOException("The test filesystem must support sparse files for bounded large-offset/cancellation fixtures.");
    }
}
