using System.Buffers.Binary;
using System.Text;
using KH2Trainer.Core;

internal static class AudioBankInspectionTests
{
    private static void U16(byte[] b, int p, ushort v) => BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(p), v);
    private static void U32(byte[] b, int p, uint v) => BinaryPrimitives.WriteUInt32LittleEndian(b.AsSpan(p), v);
    private static void I32(byte[] b, int p, int v) => BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(p), v);
    private static byte[] Scd(uint version = 3, int length = 512, params int[] sequences)
    {
        byte[] b = new byte[length]; "SEDBSSCF"u8.CopyTo(b); U32(b, 8, version); b[13] = 4; U16(b, 14, 32); U32(b, 16, (uint)length);
        if (length >= 64)
        {
            U16(b, 32, checked((ushort)sequences.Length)); U16(b, 38, 5100);
            for (int i = 0; i < sequences.Length; i++)
            {
                int p = sequences[i]; I32(b, 64 + 4 * i, p);
                if (p > 80 && p + 32 <= length) { b[p] = (byte)(i + 1); U16(b, p + 12, (ushort)(71 + i)); }
            }
        }
        return b;
    }
    private static byte[] Origin(byte[]? name = null)
    {
        byte[] b = new byte[48]; "ORIGIN\0"u8.CopyTo(b); U32(b, 12, 0xFEDCBA98);
        (name ?? "voice/battle/test"u8.ToArray()).CopyTo(b, 16); return b;
    }
    private static byte[] Bar(byte[] child)
    {
        byte[] b = new byte[32 + child.Length]; "BAR\x01"u8.CopyTo(b); I32(b, 4, 1); U16(b, 16, 34);
        "snd0"u8.CopyTo(b.AsSpan(20)); U32(b, 24, 32); U32(b, 28, (uint)child.Length); child.CopyTo(b, 32); return b;
    }
    public static async Task RunAsync(string workspace, Action<bool, string> check)
    {
        string folder = Path.Combine(workspace, "audio-inspection"); Directory.CreateDirectory(folder); int serial = 0;
        var reader = new AssetArchiveReader();
        string Save(byte[] bytes, string extension = ".bin")
        { string path = Path.Combine(folder, $"synthetic-{serial++}{extension}"); File.WriteAllBytes(path, bytes); return path; }
        Task<AudioBankDocument> Inspect(byte[] b, AudioBankReadLimits? limits = null, CancellationToken token = default) =>
            AudioBankInspector.InspectStreamAsync(new MemoryStream(b, writable: false), limits, token);
        async Task Reject<T>(Func<Task> action, string message) where T : Exception
        { try { await action(); check(false, "Audio: " + message); } catch (T) { check(true, "Audio: " + message); } }
        void Check(bool value, string message) => check(value, "Audio: " + message);

        Check(AssetArchiveReader.Recognize("ORIGIN\0"u8) == "ORIGIN audio reference" &&
            AssetArchiveReader.Recognize("SEDBSSCF"u8) == "SCD audio bank", "complete magic is recognized without claiming structural validity");
        Check(AssetArchiveReader.Recognize("ORIGINX"u8) == "Binary data" && AssetArchiveReader.Recognize("SEDBSSC"u8) == "Binary data", "near magic is not recognized");
        byte[] origin = Origin();
        for (int n = 0; n < 48; n++)
        {
            var d = await Inspect(origin[..n]);
            Check(n < 7 ? d.Format == AudioBankFormat.Unknown : d.Format == AudioBankFormat.Origin && d.Status == AudioInspectionStatus.Truncated && d.Origin is null,
                $"ORIGIN prefix length {n} retains signature/structure separation");
        }
        var normal = await Inspect(origin);
        Check(normal.Origin is { StoredMetadataAt12: 0xFEDCBA98, Name: "voice/battle/test", NameTerminated: true } && normal.Status == AudioInspectionStatus.MetadataRead,
            "ORIGIN stored metadata and bounded name decoded");
        var control = await Inspect(Origin([0x41, 0x0a, 0xff, 0x5c, 0]));
        Check(control.Origin is { Name: "A\\x0A\\xFF\\\\", NameHex: "410AFF5C" }, "byte escapes are lossless and backslash is unambiguous");
        var emptyName = await Inspect(Origin([0])); Check(emptyName.Origin is { Name: "", NameHex: "", NameTerminated: true }, "empty stored name is retained");
        byte[] longName = Enumerable.Repeat((byte)'q', 32).ToArray();
        var fullName = await Inspect(Origin(longName));
        Check(fullName.Origin is { NameTerminated: false } && fullName.Origin.Name.Length == 32 && fullName.Diagnostics.Any(x => x.Code == "OriginNameUnterminated"),
            "unterminated name stays in 16..47 including bytes at runtime pointer locations");
        longName[31] = 0; var endName = await Inspect(Origin(longName));
        Check(endName.Origin is { NameTerminated: true } && endName.Origin.Name.Length == 31, "last name-region byte can terminate");
        var longOrigin = await Inspect(origin.Concat(new byte[17]).ToArray());
        Check(longOrigin.Origin == normal.Origin && longOrigin.Diagnostics.Any(x => x.Code == "OriginLength"), "longer payload reports an observation without extending name bounds");

        byte[] scd = Scd(3, 512, 128, 160, 192); U16(scd, 160 + 12, 71); U16(scd, 192 + 12, 71);
        for (int n = 0; n < 20; n++)
        {
            var d = await Inspect(scd[..n]);
            Check(n < 8 ? d.Format == AudioBankFormat.Unknown : d.Status == AudioInspectionStatus.Truncated && d.Scd is null,
                $"SCD prefix length {n} never reads missing header fields");
        }
        foreach (uint version in new uint[] { 1, 2, 5, 0x03000000, uint.MaxValue })
        {
            var d = await Inspect(Scd(version));
            Check(d.Status == AudioInspectionStatus.Unsupported && d.Scd?.Version == version && d.Rows.Count == 0, $"version {version} remains raw and unsupported");
        }
        foreach (var profile in new[] { (1, 4), (0, 8), (255, 255) })
        {
            byte[] b = (byte[])scd.Clone(); b[12] = (byte)profile.Item1; b[13] = (byte)profile.Item2;
            var d = await Inspect(b); Check(d.Status == AudioInspectionStatus.Unsupported && d.Scd?.ProfileByte12 == profile.Item1 && d.Rows.Count == 0,
                $"profile {profile} does not infer endian semantics");
        }
        var metadata = await Inspect(scd);
        Check(metadata.Scd is { BankId: 5100, SequenceCount: 3, TableBCount: 0, TableCCount: 0 } && metadata.Rows.Select(x => x.SoundId).SequenceEqual(new ushort?[] { 71, 71, 71 }) &&
            metadata.Rows.All(x => x.DuplicateSoundId) && metadata.Rows.Select(x => x.TrackReferenceCount).SequenceEqual(new byte?[] { 1, 2, 3 }), "all duplicate IDs and their ordinal track counts are retained");
        Check(metadata.Tables[3].Status == AudioTableStatus.Absent && metadata.Tables[1].Status == AudioTableStatus.Read && metadata.Tables[1].InspectedRows == 0,
            "absent Aux and empty B table are distinct");
        foreach (uint declared in new uint[] { 0, 140, 512, 1000 })
        {
            byte[] b = (byte[])scd.Clone(); U32(b, 16, declared); var d = await Inspect(b);
            Check(d.Rows.Count == 3 && d.Rows.All(x => x.Status == AudioTargetStatus.Available) && d.PhysicalMinusDeclared == 512L - declared &&
                d.Rows[0].WithinDeclaredSize == (declared >= 144), $"declared size {declared} never replaces available length");
        }
        foreach (uint version in new uint[] { 3, 4 })
        {
            int size = version == 3 ? 16 : 32;
            foreach (int target in new[] { -1, int.MinValue, 0, 1, 512 - size, 513 - size, 512, int.MaxValue })
            {
                byte[] b = Scd(version, 512, 128); I32(b, 64, target); U32(b, 16, uint.MaxValue); var d = await Inspect(b); var row = d.Rows.Single();
                var expected = target < 0 ? AudioTargetStatus.NegativeOffset : target == 0 ? AudioTargetStatus.NullOffset : target <= 512 - size ? AudioTargetStatus.Available : AudioTargetStatus.OutsideAvailableLength;
                Check(row.TargetOffset == target && row.Status == expected && row.MinimumTargetBytes == size && (row.SoundId.HasValue == (expected == AudioTargetStatus.Available)),
                    $"v{version} target {target} is checked before complete {size}-byte header read");
            }
        }
        foreach (ushort h in new ushort[] { 480, 481, 512, ushort.MaxValue })
        {
            byte[] b = Scd(); U16(b, 14, h); var d = await Inspect(b);
            Check(h == 480 ? d.Scd?.SequenceCount == 0 && d.Tables.Count == 4 : d.Status == AudioInspectionStatus.Truncated && d.Tables.Count == 0,
                $"header offset {h} has exact 32-byte bound");
        }
        byte[] sameTarget = Scd(3, 512, 128, 128);
        var alias = await Inspect(sameTarget); Check(alias.Rows.Count == 2 && alias.Rows.All(x => x.SharesTarget && x.DuplicateSoundId), "shared sequence target preserves both ordinals");
        byte[] overlap = Scd(3, 512, 64); var overlapDoc = await Inspect(overlap);
        Check(overlapDoc.Rows.Single().OverlapsMetadata && overlapDoc.Rows.Single().Status == AudioTargetStatus.Available,
            "metadata overlap is observed without inventing a format prohibition");
        byte[] bc = Scd(3, 512, 128); U16(bc, 34, 1); U16(bc, 36, 1); U32(bc, 40, 80); U32(bc, 44, 84); U32(bc, 48, 88);
        I32(bc, 80, 511); I32(bc, 84, 512); I32(bc, 88, 384);
        var all = await Inspect(bc);
        Check(all.Rows.Single(x => x.TableKind == AudioTableKind.B) is { MinimumTargetBytes: 1, Status: AudioTargetStatus.Available, SoundId: null } &&
            all.Rows.Single(x => x.TableKind == AudioTableKind.C).Status == AudioTargetStatus.OutsideAvailableLength &&
            all.Rows.Single(x => x.TableKind == AudioTableKind.Aux) is { MinimumTargetBytes: 128, Status: AudioTargetStatus.Available },
            "B/C one-byte and Aux 128-byte extent observations are separate from sequence decoding");
        I32(bc, 88, 385); var shortAux = await Inspect(bc);
        Check(shortAux.Rows.Single(x => x.TableKind == AudioTableKind.Aux).Status == AudioTargetStatus.OutsideAvailableLength, "Aux one byte short is outside available payload");
        foreach (uint at in new uint[] { 0, 508, 509, 0x80000000, uint.MaxValue })
        {
            byte[] b = Scd(); U16(b, 34, 1); U32(b, 40, at); var d = await Inspect(b); var table = d.Tables.Single(x => x.Kind == AudioTableKind.B);
            Check(table.Offset == (long)at && (table.Status == AudioTableStatus.Read) == (at <= 508), $"unsigned table base {at} and four-byte table span checked");
        }
        byte[] zeroTable = Scd(); U32(zeroTable, 40, uint.MaxValue); var zeroTableDoc = await Inspect(zeroTable);
        Check(zeroTableDoc.Tables[1].Status == AudioTableStatus.Read && zeroTableDoc.Rows.Count == 0, "zero count does not seek arbitrary base");
        byte[] badB = Scd(3, 512, 128); U16(badB, 34, 1); U32(badB, 40, uint.MaxValue);
        var independent = await Inspect(badB); Check(independent.Status == AudioInspectionStatus.InvalidStructure && independent.Rows.Single().SoundId == 71,
            "invalid B table does not hide independently readable sequence metadata");

        foreach (ushort count in new ushort[] { 4096, 4097, ushort.MaxValue })
        {
            byte[] b = Scd(3, 20000); U16(b, 34, count); U32(b, 40, 128); var d = await Inspect(b);
            Check(count == 4096 ? d.Rows.Count == 4096 && !d.HitLimit : d.HitLimit && d.Rows.Count == 0 && d.Tables.All(t => t.Status is AudioTableStatus.NotInspected or AudioTableStatus.Absent),
                $"per-table count {count} checked before enumeration/allocation");
        }
        byte[] totalLimit = Scd(); U16(totalLimit, 32, 4096); U16(totalLimit, 34, 1); U32(totalLimit, 48, 80);
        var limitedRows = await Inspect(totalLimit); Check(limitedRows.HitLimit && limitedRows.Rows.Count == 0 && limitedRows.Scd?.SequenceCount == 4096,
            "total-row preflight counts Aux and retains only header summary");
        byte[] exactRows = Scd(3, 40000); U16(exactRows, 34, 4096); U16(exactRows, 36, 4096); U32(exactRows, 40, 128); U32(exactRows, 44, 17000);
        var rowBoundary = await Inspect(exactRows); Check(rowBoundary.Rows.Count == 8192 && !rowBoundary.HitLimit, "exact total-row budget is accepted");
        byte[] negatives = Scd(3, 512, 128, 160, 192); I32(negatives, 64, -1); I32(negatives, 68, -2); I32(negatives, 72, -3);
        var diagnosticLimit = await Inspect(negatives, new() { MaximumDiagnostics = 1 });
        Check(diagnosticLimit.Diagnostics.Count == 1 && diagnosticLimit.SuppressedDiagnostics == 2 && diagnosticLimit.Rows.Count == 3,
            "diagnostic cap counts suppressed entries without suppressing data rows");
        foreach (AudioBankReadLimits invalid in new[] { new AudioBankReadLimits { MaximumRows = 0 }, new() { MaximumTableEntries = 65536 },
            new() { MaximumMetadataBytes = 0 }, new() { MaximumDiagnostics = 0 }, new() { MaximumDecodedSourceBytes = 0 } })
            await Reject<ArgumentOutOfRangeException>(() => Inspect(scd, invalid), "invalid configurable limit rejected");

        byte[] outsidePrefix = Scd(4, 6000, 5000, 5100);
        using (var tracked = new ProbeStream(outsidePrefix))
        {
            var d = await AudioBankInspector.InspectStreamAsync(tracked, new() { MaximumMetadataBytes = 4096 + 32 });
            Check(d.HitLimit && d.Rows.Count == 2 && d.Rows[0].SoundId == 71 && d.Rows[1].Status == AudioTargetStatus.NotInspected &&
                d.Tables[0].Status == AudioTableStatus.NotInspected && d.MetadataBytesRead == 4128 && tracked.BytesReturned == 4128 && tracked.Reads.Count == 2,
                "read budget stops before second sequence read; retained and uninspected rows are explicit");
            Check(!tracked.Disposed, "internal bounded-stream seam retains caller ownership");
        }
        using (var shortReads = new ProbeStream(outsidePrefix) { MaximumChunk = 1 })
        {
            var d = await AudioBankInspector.InspectStreamAsync(shortReads);
            Check(d.Rows.Count == 2 && d.Rows[1].SoundId == 72 && d.MetadataBytesRead == shortReads.BytesReturned, "ReadExactly handles repeated one-byte reads");
        }
        using (var exactReadBudget = new ProbeStream(Scd(4, 6000, 5000)))
        {
            var d = await AudioBankInspector.InspectStreamAsync(exactReadBudget, new() { MaximumMetadataBytes = 4128 });
            Check(!d.HitLimit && d.MetadataBytesRead == 4128 && d.Rows.Single().SoundId == 71,
                "using exactly the read budget is complete when no additional read is needed");
            Check(exactReadBudget.Reads.All(x => x.Position >= 0 && x.Count <= exactReadBudget.Length - x.Position),
                "all requested read spans stay inside available payload");
        }
        byte[] remoteHeader = Scd(4, 6000); U16(remoteHeader, 14, 4200); U16(remoteHeader, 4200, 1);
        U16(remoteHeader, 4206, 600); I32(remoteHeader, 4232, 5000); U16(remoteHeader, 5012, 321);
        using (var remote = new ProbeStream(remoteHeader))
        {
            var d = await AudioBankInspector.InspectStreamAsync(remote);
            Check(d.Rows.Single().SoundId == 321 && d.MetadataBytesRead == 4096 + 32 + 4 + 32 && remote.Reads.Count == 4,
                "out-of-prefix tables header, offsets and sequence are independently bounded reads");
        }
        using (var limitedTable = new ProbeStream(remoteHeader))
        {
            var d = await AudioBankInspector.InspectStreamAsync(limitedTable, new() { MaximumMetadataBytes = 4128 });
            Check(d.HitLimit && d.Scd?.BankId == 600 && d.Rows.Count == 0 && d.Tables[0].Status == AudioTableStatus.NotInspected && limitedTable.Reads.Count == 2,
                "offset-table budget stops before table read/allocation and preserves header summary");
        }
        foreach (int stopAfter in new[] { 1, 2, 3 })
        {
            using var cancellation = new CancellationTokenSource(); using var stream = new ProbeStream(remoteHeader);
            stream.AfterRead = () => { if (stream.Reads.Count == stopAfter) cancellation.Cancel(); };
            await Reject<OperationCanceledException>(() => AudioBankInspector.InspectStreamAsync(stream, cancellationToken: cancellation.Token),
                $"cancel after stream phase {stopAfter} remains an exception");
            Check(stream.Reads.Count == stopAfter, $"cancel at phase {stopAfter} prevents next metadata read");
        }
        using (var sparse = new ProbeStream(Scd()) { VirtualLength = (1L << 32) + 32 })
        {
            U16(sparse.Data, 34, 1); U32(sparse.Data, 40, uint.MaxValue);
            var d = await AudioBankInspector.InspectStreamAsync(sparse);
            Check(d.AvailableLength == (1L << 32) + 32 && d.Tables[1].Offset == uint.MaxValue && d.Tables[1].Status == AudioTableStatus.Read &&
                sparse.Reads.Any(x => x.Position == uint.MaxValue && x.Count == 4), "unsigned high table base is read with 64-bit seek in sparse logical stream");
        }
        var cancelled = new CancellationToken(true);
        await Reject<OperationCanceledException>(() => Inspect(scd, token: cancelled), "pre-cancelled stream parse throws");
        using (var cancel = new CancellationTokenSource())
        using (var tracked = new ProbeStream(outsidePrefix))
        {
            tracked.AfterRead = () => { if (tracked.Reads.Count == 2) cancel.Cancel(); };
            await Reject<OperationCanceledException>(() => AudioBankInspector.InspectStreamAsync(tracked, cancellationToken: cancel.Token), "cancellation during first sequence read throws");
            Check(tracked.Reads.Count == 2, "cancelled reader performs no subsequent stream reads");
        }
        using (var eof = new ProbeStream(outsidePrefix) { EofAt = 5001 })
            await Reject<EndOfStreamException>(() => AudioBankInspector.InspectStreamAsync(eof), "actual EOF after advertised span check remains exception");
        using (var fault = new ProbeStream(outsidePrefix) { FailAt = 5000 })
            await Reject<IOException>(() => AudioBankInspector.InspectStreamAsync(fault), "actual I/O fault is not a format success");
        var tinyBudget = await Inspect(scd, new() { MaximumMetadataBytes = 7 });
        Check(tinyBudget.HitLimit && tinyBudget.Format == AudioBankFormat.Unknown && tinyBudget.MetadataBytesRead == 7, "signature read budget is distinct from unknown file format");
        var headerBudget = await Inspect(origin, new() { MaximumMetadataBytes = 7 });
        Check(headerBudget.HitLimit && headerBudget.Format == AudioBankFormat.Origin && headerBudget.Origin is null, "recognized magic does not bypass header budget");
        await Reject<NotSupportedException>(() => { ((IList<byte>)metadata.Preview)[0] = 0; return Task.CompletedTask; }, "result preview is read-only");
        await Reject<NotSupportedException>(() => { ((IList<AudioOffsetRow>)metadata.Rows).Clear(); return Task.CompletedTask; }, "result rows are read-only");

        // Actual retained locators: identity checks, package metadata and nested child bounds.
        string loose = Save(scd); var payload = reader.OpenLooseFile(loose);
        var looseDoc = await AudioBankInspector.ReadAsync(reader, payload);
        Check(looseDoc.Rows.SequenceEqual(metadata.Rows) && File.ReadAllBytes(loose).SequenceEqual(scd), "public loose path preserves source bytes and parsed metadata");
        await Reject<OperationCanceledException>(() => AudioBankInspector.ReadAsync(reader, payload, cancellationToken: cancelled), "public reader cancels before opening");
        using (var exclusive = new FileStream(loose, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            Check(exclusive.Length == scd.Length, "public inspector releases source handle after success");
        string nestedPath = Save(Bar(Bar(scd))); var root = reader.OpenLooseFile(nestedPath);
        var outer = await reader.ReadBarAsync(root); var inner = await reader.ReadBarAsync(outer.Entries[0].Payload);
        var childDoc = await AudioBankInspector.ReadAsync(reader, inner.Entries[0].Payload);
        Check(childDoc.Rows.SequenceEqual(metadata.Rows) && childDoc.AvailableLength == scd.Length, "nested BAR offsets remain relative to selected child");
        byte[] outsideChild = Scd(3, 128); U16(outsideChild, 32, 1); I32(outsideChild, 64, 128);
        byte[] rootWithTail = Bar(outsideChild).Concat(new byte[100]).ToArray();
        var bounded = await reader.ReadBarAsync(reader.OpenLooseFile(Save(rootWithTail)));
        Check((await AudioBankInspector.ReadAsync(reader, bounded.Entries[0].Payload)).Rows.Single().Status == AudioTargetStatus.OutsideAvailableLength,
            "target beyond child is rejected even when parent has backing bytes");

        (string Hed, string Pkg, PackageIndex Index) Package(byte[] original, byte[]? remaster = null)
        {
            int meta = remaster is null ? 16 : 64; int storedOriginal = (original.Length + 15) & ~15;
            int storedRemaster = remaster is null ? 0 : (remaster.Length + 15) & ~15;
            byte[] record = new byte[meta + storedOriginal + storedRemaster]; I32(record, 0, original.Length); I32(record, 4, remaster is null ? 0 : 1); I32(record, 8, -2);
            original.CopyTo(record, meta);
            if (remaster is not null)
            {
                "sound.scd\0"u8.CopyTo(record.AsSpan(16)); I32(record, 56, remaster.Length); I32(record, 60, -2); remaster.CopyTo(record, meta + storedOriginal);
            }
            byte[] hed = new byte[64]; for (int i = 0; i < 2; i++) { I32(hed, 32 * i + 24, record.Length); I32(hed, 32 * i + 28, original.Length); }
            string path = Save(hed, ".hed"), pkg = Path.ChangeExtension(path, ".pkg"); File.WriteAllBytes(pkg, record);
            return (path, pkg, reader.OpenPackageIndex(path));
        }
        var package = Package(Bar(scd), scd); var info = reader.InspectPackageEntry(package.Index, 0);
        var packageBar = await reader.ReadBarAsync(info.Original); var packageChild = packageBar.Entries[0].Payload;
        Check((await AudioBankInspector.ReadAsync(reader, packageChild)).Rows.SequenceEqual(metadata.Rows), "package to BAR selected payload reads the same bounded metadata");
        Check((await AudioBankInspector.ReadAsync(reader, info.Remastered.Single().Payload)).Rows.SequenceEqual(metadata.Rows), "explicit remastered payload reads without resolving ORIGIN name");
        var aliasPayload = reader.InspectPackageEntry(package.Index, 1).Original;
        Check(info.Original.EntryOrdinal != aliasPayload.EntryOrdinal || info.Original.PackageData!.EntryOrdinal != aliasPayload.PackageData!.EntryOrdinal,
            "same-span package aliases retain separate locator ordinals");
        var budget = new AudioBankReadLimits { MaximumDecodedSourceBytes = scd.Length };
        // A locked package proves the ancestor budget is checked before opening/decoding.
        using (var held = new FileStream(package.Pkg, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            var d = await AudioBankInspector.ReadAsync(reader, packageChild, budget);
            Check(d.HitLimit && d.MetadataBytesRead == 0 && d.Preview.Count == 0 && d.AvailableLength == scd.Length,
                "large package ancestor is rejected before OpenRead even for a smaller BAR child");
        }
        var exactPackage = Package(scd); var exactPayload = reader.InspectPackageEntry(exactPackage.Index, 0).Original;
        Check((await AudioBankInspector.ReadAsync(reader, exactPayload, budget)).Rows.Count == 3, "exact decode budget is accepted");
        var smallerReader = new AssetArchiveReader(new() { MaximumDecodedBytes = scd.Length - 1 });
        Check((await AudioBankInspector.ReadAsync(smallerReader, exactPayload)).Diagnostics.Single().Code == "DecodedSourceLimit",
            "stricter caller reader decode limit participates in preflight");
        string changed = Save(scd); var stale = reader.OpenLooseFile(changed); File.WriteAllBytes(changed, new byte[scd.Length + 1]);
        await Reject<IOException>(() => AudioBankInspector.ReadAsync(reader, stale), "changed source length invalidates retained locator");
        changed = Save(scd); stale = reader.OpenLooseFile(changed); DateTime time = File.GetLastWriteTimeUtc(changed);
        string replacement = Save(scd); File.SetLastWriteTimeUtc(replacement, time); File.Move(replacement, changed, true);
        await Reject<IOException>(() => AudioBankInspector.ReadAsync(reader, stale), "same-length/time replacement is rejected by file identity");
        var changedHed = Package(scd); var hedPayload = reader.InspectPackageEntry(changedHed.Index, 0).Original;
        time = File.GetLastWriteTimeUtc(changedHed.Hed); byte[] hedBytes = File.ReadAllBytes(changedHed.Hed); hedBytes[0] ^= 1; File.WriteAllBytes(changedHed.Hed, hedBytes); File.SetLastWriteTimeUtc(changedHed.Hed, time);
        await Reject<IOException>(() => AudioBankInspector.ReadAsync(reader, hedPayload), "same-timestamp HED mutation is rejected through public audio API");
        var changedRecord = Package(scd); var recordPayload = reader.InspectPackageEntry(changedRecord.Index, 0).Original;
        time = File.GetLastWriteTimeUtc(changedRecord.Pkg); byte[] recordBytes = File.ReadAllBytes(changedRecord.Pkg); recordBytes[12] ^= 1;
        File.WriteAllBytes(changedRecord.Pkg, recordBytes); File.SetLastWriteTimeUtc(changedRecord.Pkg, time);
        await Reject<IOException>(() => AudioBankInspector.ReadAsync(reader, recordPayload), "same-timestamp record mutation is rejected through public audio API");
        time = File.GetLastWriteTimeUtc(nestedPath); byte[] rootBytes = File.ReadAllBytes(nestedPath); rootBytes[20] ^= 1;
        File.WriteAllBytes(nestedPath, rootBytes); File.SetLastWriteTimeUtc(nestedPath, time);
        await Reject<IOException>(() => AudioBankInspector.ReadAsync(reader, inner.Entries[0].Payload), "changed parent BAR metadata is rejected through public audio API");
        using (var exclusive = new FileStream(nestedPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            Check(exclusive.Length == rootBytes.Length, "failed public inspection also releases parent handles");
    }

    private sealed class ProbeStream(byte[] data) : Stream
    {
        public byte[] Data { get; } = data;
        public long? VirtualLength { get; set; }
        public long EofAt { get; init; } = long.MaxValue;
        public long FailAt { get; init; } = long.MaxValue;
        public int MaximumChunk { get; init; } = int.MaxValue;
        public List<(long Position, int Count)> Reads { get; } = [];
        public long BytesReturned { get; private set; }
        public Action? AfterRead { get; set; }
        public bool Disposed { get; private set; }
        public override long Length => VirtualLength ?? Data.Length;
        public override long Position { get; set; }
        public override bool CanRead => true;
        public override bool CanSeek => true;
        public override bool CanWrite => false;
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested(); Reads.Add((Position, buffer.Length));
            if (Position >= FailAt) throw new IOException("Synthetic I/O failure.");
            int n = (int)Math.Max(0, Math.Min(Math.Min(buffer.Length, MaximumChunk), Math.Min(Length - Position, EofAt - Position)));
            buffer.Span[..n].Clear();
            if (Position < Data.Length && n > 0) Data.AsSpan((int)Position, (int)Math.Min(n, Data.Length - Position)).CopyTo(buffer.Span);
            Position += n; BytesReturned += n; AfterRead?.Invoke(); return ValueTask.FromResult(n);
        }
        public override int Read(byte[] buffer, int offset, int count) => ReadAsync(buffer.AsMemory(offset, count)).GetAwaiter().GetResult();
        public override long Seek(long offset, SeekOrigin origin) => Position = checked((origin switch { SeekOrigin.Begin => 0, SeekOrigin.Current => Position, SeekOrigin.End => Length, _ => throw new ArgumentOutOfRangeException(nameof(origin)) }) + offset);
        public override void Flush() { }
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        protected override void Dispose(bool disposing) { Disposed = true; base.Dispose(disposing); }
    }
}
