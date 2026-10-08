using System.Buffers.Binary;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using KH2Trainer.Core;

internal static class EffectiveAssetReaderTests
{
    private const string Compressed = "a401000000000000300000007b0000008a45ffa3bd47873e5831daefa8341cdb5ef125c1bc591d020c7136551a6678ad7c9cc1213b41833fdea9e7d455ab99dd";
    private const string Transformed17 = "1100000000000000ffffffff7b000000d6bb017b0631df15d8b488ada235f8f910";
    private const string Remastered = "0400000002000000feffffff7b0000002e2e2f434f4e2e64647300000000000000000000000000000000000000000000f0ffffff0000002021000000ffffffff2d312e6464730000000000000000000000000000000000000000000000000000f0ffffff10000020900100001000000062617365cdcdcdcdcdcdcdcdcdcdcdcdec966cd2493cf58ef040e93e40e36051fc867cc2592ce59ee050c3106ec94a6747cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdf568843c365f11ef992aa900a12cc2ec";
    private const string Name = "obj/TEST.mdlx";
    private static void I32(byte[] b, int p, int n) => BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(p), n);
    private static byte[] Record(byte[] bytes, int mode = -2)
    { var b = new byte[16 + bytes.Length]; I32(b, 0, bytes.Length); I32(b, 8, mode); bytes.CopyTo(b, 16); return b; }
    private static string Hash(byte[] b) => Convert.ToHexString(SHA256.HashData(b));

    private sealed class Fixture
    {
        public readonly string Folder, Exe, Dll, Mod, Dev, Extract;
        private int sequence;
        public Fixture(string workspace)
        {
            Folder = Path.Combine(workspace, "effective-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(Folder);
            Exe = Path.Combine(Folder, "game.exe"); Dll = Path.Combine(Folder, "dbghelp.dll");
            File.WriteAllBytes(Exe, "synthetic retail fingerprint"u8.ToArray()); File.WriteAllBytes(Dll, "synthetic Panacea fingerprint"u8.ToArray());
            Mod = Path.Combine(Folder, "mod", "kh2"); Dev = Path.Combine(Folder, "dev", "kh2"); Extract = Path.Combine(Folder, "extract", "kh2");
            foreach (string p in new[] { Mod, Dev, Extract, Path.Combine(Mod, "raw", "obj") }) Directory.CreateDirectory(p);
        }
        public string Write(string root, byte[] bytes, string name = Name)
        { string p = Path.Combine(root, name.Replace('/', Path.DirectorySeparatorChar)); Directory.CreateDirectory(Path.GetDirectoryName(p)!); File.WriteAllBytes(p, bytes); return p; }
        public EffectivePackageProvider Pair((string Name, byte[] Record)[] rows, bool decode = true)
        {
            string h = Path.Combine(Folder, "package" + sequence++ + ".hed"), p = Path.ChangeExtension(h, ".pkg");
            byte[] hed = new byte[32 * rows.Length]; using var package = new FileStream(p, FileMode.CreateNew, FileAccess.Write);
            for (int i = 0; i < rows.Length; i++)
            {
                var (name, record) = rows[i]; MD5.HashData(Encoding.ASCII.GetBytes(name)).CopyTo(hed, i * 32);
                BinaryPrimitives.WriteInt64LittleEndian(hed.AsSpan(i * 32 + 16), package.Position);
                I32(hed, i * 32 + 24, record.Length); I32(hed, i * 32 + 28, record.Length >= 4 ? BinaryPrimitives.ReadInt32LittleEndian(record) : 0);
                package.Write(record);
            }
            File.WriteAllBytes(h, hed); return new(h, p, decode);
        }
        public EffectiveAssetManifestOptions Options(params EffectivePackageProvider[] packages) => new() {
            RetailExecutablePath = Exe, PanaceaLibraryPath = Dll, ModRoot = Mod, DevRoot = Dev, ExtractRoot = Extract, Packages = packages };
        public Task<EffectiveAssetManifest> Verify(EffectiveAssetManifestOptions? options = null, AssetReadLimits? limits = null) =>
            EffectiveAssetManifest.VerifyWithProfileAsync(options ?? Options(), limits ?? new(),
                Hash("synthetic retail fingerprint"u8.ToArray()), Hash("synthetic Panacea fingerprint"u8.ToArray()));
        public string Raw(byte[] record) => Write(Path.Combine(Mod, "raw"), record);
    }

    public static async Task RunAsync(string workspace, Action<bool, string> check)
    {
        void C(bool condition, string label) => check(condition, "effective assets: " + label);
        async Task Reject<T>(Func<Task> f, string label) where T : Exception
        {
            try { await f(); C(false, label); }
            catch (T) { C(true, label); }
            catch (Exception e) { C(false, label + " (unexpected " + e.GetType().Name + ")"); }
        }
        async Task RejectData(Func<Task> f, string label)
        { try { await f(); C(false, label); } catch (Exception e) when (e is IOException or InvalidDataException) { C(true, label); } }
        async Task RejectPath(Func<Task> f, string label)
        { try { await f(); C(false, label); } catch (Exception e) when (e is InvalidDataException or NotSupportedException) { C(true, label); } }
        var f = new Fixture(workspace);
        await Reject<NotSupportedException>(() => EffectiveAssetManifest.VerifyAsync(f.Options()), "public factory rejects a synthetic/unknown retail fingerprint");
        foreach (string remote in new[] { @"\\server\share\kh2", "//server/share/kh2", @"\/server/share/kh2", @"/\server\share\kh2",
            "//?/C:/kh2", "//./pipe/kh2", @"\/C:/kh2" })
            await Reject<NotSupportedException>(() => { EffectiveAssetPaths.Absolute(remote); return Task.CompletedTask; }, "raw/canonical UNC and device spelling rejected before filesystem access: " + remote);
        await Reject<InvalidDataException>(() => f.Verify(f.Options() with { Packages = new MiscountedList<EffectivePackageProvider>(new("a", "b", true)) }), "caller collection cannot bypass input limits through a false Count");
        var basePair = f.Pair([(Name, Record([4]))]); var options = f.Options(basePair); var manifest = await f.Verify(options);
        var reader = new AssetEffectiveByteReader(manifest);
        C(manifest.BindingStrength == EffectiveAssetBindingStrength.OfflineManifestBinding, "manifest can only claim offline binding");
        C(manifest.VerifiedEvidence.Count == 2 && manifest.VerifiedEvidence[0].ExpectedSha256 == Hash(File.ReadAllBytes(f.Exe)), "manifest exposes actual verified binary fingerprints");
        C(manifest.Packages is not EffectivePackageProvider[] && manifest.Packages.Count == 1, "manifest exposes no mutable provider array");
        ((EffectivePackageProvider[])options.Packages)[0] = new("wrong.hed", "wrong.pkg", false);
        C(manifest.Packages[0] == basePair, "caller array replacement cannot change verified order or paths");
        await Reject<NotSupportedException>(() => { ((IList<EffectivePackageProvider>)manifest.Packages)[0] = basePair; return Task.CompletedTask; }, "manifest collection setter rejects mutation");
        var result = await reader.ReadAsync(Name);
        C(result.ProviderKind == EffectiveAssetProviderKind.RetailPackage && result.Bytes.Span.SequenceEqual(new byte[] { 4 }), "retail is used only after four absent overrides");
        C(result.SourceStamp.HedOrdinal == 0 && result.SourceStamp.ProviderOrdinal == 0 && result.SourceStamp.RecordOffset == 0 &&
          result.SourceStamp.DecodedSha256 == Hash([4]) && result.ManifestSha256 == manifest.Sha256 && result.MatchedNameBytes.Span.SequenceEqual(Encoding.ASCII.GetBytes(Name)), "exact provenance includes hashes, ordinal, offset and exact name bytes");
        C(result.BindingStrength == EffectiveAssetBindingStrength.OfflineManifestBinding, "owned result never promises native registration or runtime binding");
        string extract = f.Write(f.Extract, [3]), mod = f.Write(f.Mod, [2]), dev = f.Write(f.Dev, [1]), raw = f.Raw(Record([0]));
        foreach (var expected in new[] { EffectiveAssetProviderKind.PanaceaRawRecord, EffectiveAssetProviderKind.PanaceaLooseDev,
            EffectiveAssetProviderKind.PanaceaLooseMod, EffectiveAssetProviderKind.PanaceaLooseExtract })
        {
            result = await reader.ReadAsync(Name); C(result.ProviderKind == expected && result.Bytes.Span.SequenceEqual(new[] { (byte)expected }), "five-level precedence selects " + expected);
            File.Delete(expected switch { EffectiveAssetProviderKind.PanaceaRawRecord => raw, EffectiveAssetProviderKind.PanaceaLooseDev => dev,
                EffectiveAssetProviderKind.PanaceaLooseMod => mod, _ => extract });
        }
        C(result.Bytes.Span.SequenceEqual(new byte[] { 3 }), "returned bytes remain owned after source deletion and handle disposal");
        byte[] recordLookingLoose = Convert.FromHexString(Transformed17); f.Write(f.Dev, recordLookingLoose);
        C((await reader.ReadAsync(Name)).Bytes.Span.SequenceEqual(recordLookingLoose), "loose content longer than16 remains plain even when it looks like an encoded PKG record");
        File.Delete(dev);
        Directory.CreateDirectory(raw); C((await reader.ReadAsync(Name)).ProviderKind == EffectiveAssetProviderKind.RetailPackage, "directory candidate advances priority");
        Directory.Delete(raw);
        foreach (byte[] bad in new[] { Array.Empty<byte>(), new byte[15], Record([]), Record([9])[..16] })
        {
            f.Raw(bad); await RejectData(() => reader.ReadAsync(Name), "empty/truncated selected raw source never falls through to valid retail"); File.Delete(raw);
        }
        foreach (string root in new[] { f.Dev, f.Mod, f.Extract })
        {
            string empty = f.Write(root, []); await RejectData(() => reader.ReadAsync(Name), "empty loose override never falls through: " + Path.GetFileName(Path.GetDirectoryName(root))); File.Delete(empty);
        }
        f.Raw(Record([7]));
        using (var locked = new FileStream(raw, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            await Reject<IOException>(() => reader.ReadAsync(Name), "unreadable selected override does not become absent");
        File.Delete(raw);
        await Reject<IOException>(() => reader.ReadForTestAsync(Name, () => f.Raw(Record([8]))), "new higher-priority override before publication rejects retail result"); File.Delete(raw);
        result = await reader.ReadAsync(Name);
        await Reject<FileNotFoundException>(() => reader.ReadAsync("obj/missing.bin"), "all providers absent reports not found");
        foreach (string name in new[] { "", "../x", "obj/../x", "/root", "C:/x", "obj\\x", "obj//x", "obj/", "obj/x:stream", "obj/CON.bin", "obj/CON .bin", "obj/COM1", "obj/LPT0.bin", "obj/a.", "obj/a ", "obj/\u00e4", "obj/\0x", "obj/*", new string('x', 1025) })
            await RejectPath(() => reader.ReadAsync(name), "strict ASCII relative path rejects " + name.Replace("\0", "<NUL>"));
        foreach (string root in new[] { "relative/kh2", @"\\server\share\kh2", @"\\?\C:\kh2", Path.Combine(f.Folder, "not-kh2") })
            await RejectPath(() => f.Verify(f.Options() with { ModRoot = root }), "unresolved/remote/device/unsuffixed root rejected");
        await Reject<NotSupportedException>(() => f.Verify(f.Options() with { PanaceaLibraryPath = null }), "retail manifest cannot silently accept mod roots");
        await Reject<InvalidDataException>(() => f.Verify(f.Options() with { ModRoot = null }), "Panacea manifest cannot omit its mandatory mod root");
        var retailOnly = await f.Verify(f.Options(basePair) with { PanaceaLibraryPath = null, ModRoot = null, DevRoot = "", ExtractRoot = null });
        C((await new AssetEffectiveByteReader(retailOnly).ReadAsync(Name)).ProviderKind == EffectiveAssetProviderKind.RetailPackage, "explicit vanilla manifest is supported");
        C(retailOnly.Sha256 != manifest.Sha256, "provider configuration contributes to manifest hash");

        var caseFixture = new Fixture(workspace);
        var first = caseFixture.Pair([("Dir/test.mdlx", Record([1]))]);
        var second = caseFixture.Pair([("Dir/TEST.mdlx", Record([2]))]);
        var cases = new AssetEffectiveByteReader(await caseFixture.Verify(caseFixture.Options(first, second)));
        result = await cases.ReadAsync("Dir/TEST.mdlx");
        C(result.Bytes.Span.SequenceEqual(new byte[] { 1 }) && Encoding.ASCII.GetString(result.MatchedNameBytes.Span) == "Dir/test.mdlx", "basename lowercase within first provider precedes exact second-provider match");
        await Reject<FileNotFoundException>(() => cases.ReadAsync("dir/TEST.mdlx"), "directory bytes remain case-sensitive in digest lookup");
        var both = caseFixture.Pair([("Dir/test.mdlx", Record([1])), ("Dir/TEST.mdlx", Record([2]))]);
        C((await new AssetEffectiveByteReader(await caseFixture.Verify(caseFixture.Options(both))).ReadAsync("Dir/TEST.mdlx")).Bytes.Span.SequenceEqual(new byte[] { 2 }), "exact digest wins over lowercase in same package");
        var duplicate = caseFixture.Pair([(Name, Record([1])), (Name, Record([2]))]);
        var dupReader = new AssetEffectiveByteReader(await caseFixture.Verify(caseFixture.Options(duplicate, second)));
        await Reject<InvalidDataException>(() => dupReader.ReadAsync(Name), "duplicate selected HED digest is rejected as ambiguous");
        await Reject<InvalidDataException>(() => caseFixture.Verify(caseFixture.Options(first, first)), "duplicate provider file identity rejected");
        var selectedCorrupt = caseFixture.Pair([("Dir/test.mdlx", Record([]))]);
        var selectedCorruptReader = new AssetEffectiveByteReader(await caseFixture.Verify(caseFixture.Options(selectedCorrupt, second)));
        await RejectData(() => selectedCorruptReader.ReadAsync("Dir/TEST.mdlx"), "corrupt lowercase match in first provider never falls through to exact second provider");
        var lowerDuplicate = caseFixture.Pair([("Dir/test.mdlx", Record([1])), ("Dir/test.mdlx", Record([2]))]);
        var lowerDuplicateReader = new AssetEffectiveByteReader(await caseFixture.Verify(caseFixture.Options(lowerDuplicate)));
        await RejectData(() => lowerDuplicateReader.ReadAsync("Dir/TEST.mdlx"), "duplicate fallback digest is also ambiguous");
        await RejectData(() => caseFixture.Verify(caseFixture.Options(first, second), new() { MaximumMetadataBytes = 32 }), "aggregate HED metadata budget is bounded across providers");
        await RejectData(() => caseFixture.Verify(caseFixture.Options(both), new() { MaximumIndexEntries = 1 }), "HED entry count limit enforced");
        var shortHedPair = caseFixture.Pair([(Name, Record([1]))]); File.AppendAllText(shortHedPair.HeaderPath, "x");
        await RejectData(() => caseFixture.Verify(caseFixture.Options(shortHedPair)), "unaligned HED table refused before row selection");
        var unicode = new Fixture(Path.Combine(workspace, "\u00dc\u65e5")); unicode.Raw(Record([5]));
        C((await new AssetEffectiveByteReader(await unicode.Verify()).ReadAsync(Name)).Bytes.Span.SequenceEqual(new byte[] { 5 }), "UTF-16 absolute roots preserve non-ASCII directory names");

        var codec = new Fixture(workspace); string codecPath = codec.Raw(Record([1])); var codecManifest = await codec.Verify(); var codecReader = new AssetEffectiveByteReader(codecManifest);
        byte[] sequence17 = Enumerable.Range(0, 17).Select(i => (byte)i).ToArray();
        byte[] expanded = Encoding.ASCII.GetBytes(string.Concat(Enumerable.Repeat("Offline KH2 fixture. ", 20)));
        foreach (var test in new[] { (Record(new byte[16], -1), new byte[16]), (Record(sequence17), sequence17),
            (Convert.FromHexString(Transformed17), sequence17), (Convert.FromHexString(Compressed), expanded),
            (Convert.FromHexString(Remastered), "base"u8.ToArray()) })
        {
            codec.Raw(test.Item1); result = await codecReader.ReadAsync(Name);
            int metadataLength = 16 + 48 * BinaryPrimitives.ReadInt32LittleEndian(test.Item1.AsSpan(4));
            C(result.Bytes.Span.SequenceEqual(test.Item2) && result.SourceStamp.MetadataSha256 == Hash(test.Item1[..metadataLength]) &&
                result.SourceStamp.HedOrdinal is null && result.SourceStamp.RecordOffset == 0,
                "shared standalone parser/decoder and exact full metadata hash: mode, tiny tail or remaster layout");
        }
        var transformOff = new AssetEffectiveByteReader(await codec.Verify(codec.Options() with { PlatformTransformEnabled = false }));
        codec.Raw(Record(sequence17, -1)); C((await transformOff.ReadAsync(Name)).Bytes.Span.SequenceEqual(sequence17), "platform transform disabled still reads raw mode -1");
        byte[] compressedPlain;
        using (var encoded = new MemoryStream()) { using (var z = new ZLibStream(encoded, CompressionLevel.Optimal, true)) z.Write(expanded); compressedPlain = encoded.ToArray(); }
        byte[] plainRecord = Record(compressedPlain, compressedPlain.Length); I32(plainRecord, 0, expanded.Length);
        codec.Raw(plainRecord); C((await transformOff.ReadAsync(Name)).Bytes.Span.SequenceEqual(expanded), "platform transform disabled still inflates positive mode");
        File.Delete(codecPath);
        var decodeOffPair = codec.Pair([(Name, Record(sequence17, 1))], decode: false);
        var decodeOff = new AssetEffectiveByteReader(await codec.Verify(codec.Options(decodeOffPair)));
        C((await decodeOff.ReadAsync(Name)).Bytes.Span.SequenceEqual(sequence17), "provider decode false disables transform and inflation and reads rawSize bytes");
        var decodeOnPair = codec.Pair([(Name, Record(sequence17, 1))], decode: true);
        var decodeOn = new AssetEffectiveByteReader(await codec.Verify(codec.Options(decodeOnPair)));
        await RejectData(() => decodeOn.ReadAsync(Name), "same bytes with decode enabled fail exact zlib decode");

        foreach (var mutation in new (string Label, Action<byte[]> Change)[] {
            ("negative raw", b => I32(b, 0, -1)), ("oversized raw", b => I32(b, 0, int.MaxValue)),
            ("negative count", b => I32(b, 4, -1)), ("overflow table", b => I32(b, 4, int.MaxValue)),
            ("unsupported mode", b => I32(b, 8, -3)), ("zero mode", b => I32(b, 8, 0)),
            ("oversized stored", b => I32(b, 8, int.MaxValue)), ("short table", b => I32(b, 4, 1)) })
        {
            byte[] bad = Record(sequence17); mutation.Change(bad); codec.Raw(bad);
            await RejectData(() => codecReader.ReadAsync(Name), mutation.Label + " rejected before allocation/decoding");
        }
        foreach (var bad in new[] { plainRecord[..^1], plainRecord.Concat(new byte[] { 0x42 }).ToArray(), (byte[])plainRecord.Clone() })
        {
            if (bad.Length > plainRecord.Length) I32(bad, 8, compressedPlain.Length + 1);
            else if (bad.Length == plainRecord.Length) bad[^1] ^= 1;
            codec.Raw(bad); await RejectData(() => transformOff.ReadAsync(Name), "truncated stream/checksum/unsupported tail rejected");
        }
        foreach (int size in new[] { expanded.Length - 1, expanded.Length + 1 })
        { var bad = (byte[])plainRecord.Clone(); I32(bad, 0, size); codec.Raw(bad); await RejectData(() => transformOff.ReadAsync(Name), "decoded output must equal declared length " + size); }
        codec.Raw(Convert.FromHexString(Remastered));
        var limitedCount = new AssetEffectiveByteReader(await codec.Verify(limits: new() { MaximumBarEntries = 1 }));
        await RejectData(() => limitedCount.ReadAsync(Name), "remaster count budget");
        var limitedMeta = new AssetEffectiveByteReader(await codec.Verify(limits: new() { MaximumMetadataBytes = 32 }));
        await RejectData(() => limitedMeta.ReadAsync(Name), "metadata allocation budget");
        codec.Raw(Record(sequence17));
        var limitedBytes = new AssetEffectiveByteReader(await codec.Verify(limits: new() { MaximumDecodedBytes = 16 }));
        await RejectData(() => limitedBytes.ReadAsync(Name), "decoded allocation budget");
        await Reject<ArgumentOutOfRangeException>(() => codec.Verify(limits: new() { MaximumDepth = 0 }), "invalid depth budget refused even though reader does not recurse into BAR");
        byte[] overlap = Convert.FromHexString(Remastered); I32(overlap, 8, 1); codec.Raw(overlap);
        await RejectData(() => codecReader.ReadAsync(Name), "positive tiny physical length cannot overlap remasters");
        byte[] lastShort = Convert.FromHexString(Remastered)[..^1]; codec.Raw(lastShort);
        await RejectData(() => codecReader.ReadAsync(Name), "remaster physical spans bounded even when only primary requested");
        File.Delete(codecPath);

        var change = new Fixture(workspace); var cp = change.Pair([(Name, Record([4]))]);
        string config = Path.Combine(change.Folder, "settings.txt"); File.WriteAllText(config, "mod=offline");
        var cm = await change.Verify(change.Options(cp) with { ConfigurationEvidence = [new(config, Hash(File.ReadAllBytes(config)))] });
        var cr = new AssetEffectiveByteReader(cm); DateTime configTime = File.GetLastWriteTimeUtc(config);
        File.WriteAllText(config, "mod=changed"); File.SetLastWriteTimeUtc(config, configTime);
        await Reject<IOException>(() => cr.ReadAsync(Name), "same-length/same-time configuration edit detected by hash");
        File.WriteAllText(config, "mod=offline"); File.SetLastWriteTimeUtc(config, configTime);
        DateTime hedTime = File.GetLastWriteTimeUtc(cp.HeaderPath); byte[] hedBytes = File.ReadAllBytes(cp.HeaderPath); hedBytes[0] ^= 1;
        File.WriteAllBytes(cp.HeaderPath, hedBytes); File.SetLastWriteTimeUtc(cp.HeaderPath, hedTime);
        await Reject<IOException>(() => cr.ReadAsync(Name), "same-time HED metadata change detected by hash");
        hedBytes[0] ^= 1; File.WriteAllBytes(cp.HeaderPath, hedBytes); File.SetLastWriteTimeUtc(cp.HeaderPath, hedTime);
        DateTime pkgTime = File.GetLastWriteTimeUtc(cp.PackagePath); string replacement = Path.Combine(change.Folder, "replacement.pkg");
        File.WriteAllBytes(replacement, File.ReadAllBytes(cp.PackagePath)); File.SetLastWriteTimeUtc(replacement, pkgTime); File.Move(replacement, cp.PackagePath, true);
        await Reject<IOException>(() => cr.ReadAsync(Name), "replacement PKG with equal length/time fails file identity");
        var fresh = new AssetEffectiveByteReader(await change.Verify(change.Options(cp)));
        await fresh.ReadForTestAsync(Name, () => {
            bool denied = false; try { using var writer = new FileStream(cp.PackagePath, FileMode.Open, FileAccess.Write, FileShare.ReadWrite); } catch (IOException) { denied = true; }
            C(denied, "source read handle denies concurrent ordinary file writers until publication");
        });
        using (var writeAfter = new FileStream(cp.PackagePath, FileMode.Open, FileAccess.Write, FileShare.Read)) C(writeAfter.CanWrite, "source handles released after successful result");
        var mutatedBinary = new Fixture(workspace); var beforeBinaryChange = await mutatedBinary.Verify();
        DateTime binaryTime = File.GetLastWriteTimeUtc(mutatedBinary.Dll); byte[] dll = File.ReadAllBytes(mutatedBinary.Dll); dll[0] ^= 1;
        File.WriteAllBytes(mutatedBinary.Dll, dll); File.SetLastWriteTimeUtc(mutatedBinary.Dll, binaryTime);
        await Reject<IOException>(() => new AssetEffectiveByteReader(beforeBinaryChange).ReadAsync(Name), "same-time provider binary changes invalidate an existing manifest");
        await Reject<NotSupportedException>(() => mutatedBinary.Verify(), "unsupported Panacea fingerprint is never treated as vanilla");
        var optional = new Fixture(workspace); optional.Write(optional.Dev, [8]); optional.Write(optional.Mod, [9]);
        var noDev = new AssetEffectiveByteReader(await optional.Verify(optional.Options() with { DevRoot = "", ExtractRoot = "" }));
        C((await noDev.ReadAsync(Name)).Bytes.Span.SequenceEqual(new byte[] { 9 }), "empty optional roots are disabled without probing a relative path");
        var decodeFlagChange = await f.Verify(f.Options(basePair with { DecodeEnabled = false }));
        C(decodeFlagChange.Sha256 != manifest.Sha256, "provider decode flag participates in manifest hash");
        var orderOne = await caseFixture.Verify(caseFixture.Options(first, second));
        var orderTwo = await caseFixture.Verify(caseFixture.Options(second, first));
        C(orderOne.Sha256 != orderTwo.Sha256, "provider order participates in manifest hash");
        C(orderOne.Sha256 == (await caseFixture.Verify(caseFixture.Options(first, second))).Sha256, "same unchanged offline manifest fingerprints deterministically");
        var invalidHed = change.Pair([(Name, Record([4]))]); byte[] wrongLength = File.ReadAllBytes(invalidHed.HeaderPath); I32(wrongLength, 28, 7); File.WriteAllBytes(invalidHed.HeaderPath, wrongLength);
        var mismatch = new AssetEffectiveByteReader(await change.Verify(change.Options(invalidHed)));
        await RejectData(() => mismatch.ReadAsync(Name), "selected HED/header raw length disagreement rejected");
        foreach (var invalid in new[] { -1L, long.MaxValue })
        {
            var ip = change.Pair([(Name, Record([4]))]); var bytes = File.ReadAllBytes(ip.HeaderPath);
            BinaryPrimitives.WriteInt64LittleEndian(bytes.AsSpan(16), invalid); File.WriteAllBytes(ip.HeaderPath, bytes);
            await RejectData(() => change.Verify(change.Options(ip)), "HED negative/overflow offset fails manifest verification");
        }
        var cancelled = new CancellationToken(true);
        await Reject<OperationCanceledException>(() => fresh.ReadAsync(Name, cancelled), "read cancellation before file acquisition");
        await Reject<OperationCanceledException>(() => EffectiveAssetManifest.VerifyAsync(change.Options(), cancellationToken: cancelled), "manifest cancellation before fingerprint work");
        using (var cancel = new CancellationTokenSource())
            await Reject<OperationCanceledException>(() => fresh.ReadForTestAsync(Name, cancel.Cancel, cancel.Token), "cancellation at publication never returns a result");
        using var tinyStream = new ShortReadStream(Record(sequence17));
        var info = AssetPackageCodec.InspectRecord(tinyStream, 0, tinyStream.Length, new(), default);
        var decoded = await AssetPackageCodec.DecodeBoundedAsync(tinyStream, info.Original.Offset, info.Original.StoredLength,
            info.Original.RawLength, info.Original.Mode, info.Seed, new(), default);
        C(decoded.SequenceEqual(sequence17) && tinyStream.CanRead, "shared parser uses exact reads and decoder leaves caller-owned stream open");
        using var truncated = new ShortReadStream(new byte[7], claimedLength: 17);
        await Reject<EndOfStreamException>(() => AssetPackageCodec.DecodeBoundedAsync(truncated, 0, 17, 17, -2, new byte[16], new(), default), "short source read is rejected despite claimed source length");
    }

    private sealed class ShortReadStream(byte[] bytes, long? claimedLength = null) : MemoryStream(bytes)
    {
        public override long Length => claimedLength ?? base.Length;
        public override int Read(Span<byte> buffer) => base.Read(buffer[..Math.Min(buffer.Length, 1)]);
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken token = default) => base.ReadAsync(buffer[..Math.Min(buffer.Length, 1)], token);
    }
    private sealed class MiscountedList<T>(T item) : IReadOnlyList<T>
    {
        public int Count => 1;
        public T this[int index] => item;
        public IEnumerator<T> GetEnumerator() => Enumerable.Repeat(item, 100).GetEnumerator();
        System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator() => GetEnumerator();
    }
}
