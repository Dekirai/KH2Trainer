using System.Buffers.Binary;
using System.Text;

namespace KH2Trainer.Core;

public sealed record AudioBankReadLimits
{
    public int MaximumTableEntries { get; init; } = 4096;
    public int MaximumRows { get; init; } = 8192;
    public int MaximumMetadataBytes { get; init; } = 1024 * 1024;
    public int MaximumDiagnostics { get; init; } = 128;
    public int MaximumDecodedSourceBytes { get; init; } = 64 * 1024 * 1024;
    internal void Validate()
    {
        if (MaximumTableEntries is < 1 or > 65535 || MaximumRows is < 1 or > 262140 ||
            MaximumMetadataBytes is < 1 or > 16 * 1024 * 1024 || MaximumDiagnostics is < 1 or > 10000 ||
            MaximumDecodedSourceBytes is < 1 or > 512 * 1024 * 1024)
            throw new ArgumentOutOfRangeException(nameof(AudioBankReadLimits));
    }
}

public enum AudioBankFormat { Unknown, Origin, Scd }
public enum AudioInspectionStatus { Unrecognized, MetadataRead, Unsupported, Truncated, InvalidStructure, LimitReached }
public enum AudioTableKind { Sequence, B, C, Aux }
public enum AudioTableStatus { Read, Absent, OutsideAvailableLength, NotInspected }
public enum AudioTargetStatus { Available, NegativeOffset, NullOffset, OutsideAvailableLength, NotInspected }
public enum AudioDiagnosticSeverity { Observation, Problem, Limit }

public sealed record OriginBankMetadata(uint StoredMetadataAt12, string Name, string NameHex, bool NameTerminated);
public sealed record ScdBankMetadata(uint Version, byte ProfileByte12, byte ProfileByte13,
    ushort HeaderOffset, uint DeclaredSizeAt16, ushort? BankId = null, ushort? SequenceCount = null,
    ushort? TableBCount = null, ushort? TableCCount = null);
public sealed record AudioOffsetTable(AudioTableKind Kind, long Offset, int Count, AudioTableStatus Status,
    bool WithinDeclaredSize, int InspectedRows);
public sealed record AudioOffsetRow(AudioTableKind TableKind, int Ordinal, long EntryOffset, int TargetOffset,
    AudioTargetStatus Status, int MinimumTargetBytes, bool WithinDeclaredSize, ushort? SoundId = null,
    byte? TrackReferenceCount = null, bool SharesTarget = false, bool DuplicateSoundId = false,
    bool OverlapsMetadata = false);
public sealed record AudioInspectionDiagnostic(string Code, string Message, AudioDiagnosticSeverity Severity,
    long? FileOffset = null, AudioTableKind? Table = null, int? Ordinal = null);
public sealed record AudioBankDocument(AudioBankFormat Format, AudioInspectionStatus Status, long AvailableLength,
    OriginBankMetadata? Origin, ScdBankMetadata? Scd, IReadOnlyList<AudioOffsetTable> Tables,
    IReadOnlyList<AudioOffsetRow> Rows, IReadOnlyList<AudioInspectionDiagnostic> Diagnostics,
    IReadOnlyList<byte> Preview, long MetadataBytesRead, bool HitLimit, int SuppressedDiagnostics)
{
    public long? PhysicalMinusDeclared => Scd is null ? null : AvailableLength - Scd.DeclaredSizeAt16;
    public const string Scope = "Stored ORIGIN and selected PC SCD metadata only. Available length is the bounded " +
        "payload length. Declared size is a separate stored field. Table and header spans do not establish " +
        "complete object validity, playable audio, runtime ownership or safe replay.";
}

/// <summary>Bounded offline metadata reader. See docs/research/audio-bank-format-20261011 and
/// audio-retail-witness-20261011. The 0/4 header profile and versions 3/4 are product limits;
/// no endian-flag semantics are inferred from the two observed profile bytes.</summary>
public static class AudioBankInspector
{
    public static async Task<AudioBankDocument> ReadAsync(AssetArchiveReader reader, AssetPayload payload,
        AudioBankReadLimits? limits = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(reader); ArgumentNullException.ThrowIfNull(payload);
        limits ??= new(); limits.Validate(); cancellationToken.ThrowIfCancellationRequested();
        for (AssetPayload? ancestor = payload; ancestor is not null; ancestor = ancestor.Parent)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (ancestor.PackageData is not null && ancestor.Length > Math.Min(limits.MaximumDecodedSourceBytes, reader.Limits.MaximumDecodedBytes))
                return new(AudioBankFormat.Unknown, AudioInspectionStatus.LimitReached, payload.Length, null, null,
                    Array.AsReadOnly(Array.Empty<AudioOffsetTable>()), Array.AsReadOnly(Array.Empty<AudioOffsetRow>()),
                    Array.AsReadOnly(new[] { new AudioInspectionDiagnostic("DecodedSourceLimit",
                        "A package payload or ancestor exceeds the audio inspection decode limit. No source was opened.", AudioDiagnosticSeverity.Limit) }),
                    Array.AsReadOnly(Array.Empty<byte>()), 0, true, 0);
        }
        await using var stream = await reader.OpenReadAsync(payload, cancellationToken).ConfigureAwait(false);
        return await InspectStreamAsync(stream, limits, cancellationToken).ConfigureAwait(false);
    }

    // The caller owns this already bounded stream. This seam permits deterministic short-read,
    // cancellation and sparse-address tests without bypassing locators in the public file API.
    internal static Task<AudioBankDocument> InspectStreamAsync(Stream stream, AudioBankReadLimits? limits = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(stream); limits ??= new(); limits.Validate();
        cancellationToken.ThrowIfCancellationRequested();
        if (!stream.CanRead || !stream.CanSeek) throw new ArgumentException("A readable, seekable bounded stream is required.", nameof(stream));
        if (stream.Length < 0) throw new ArgumentException("A nonnegative stream length is required.", nameof(stream));
        return new Reader(stream, limits, cancellationToken).ReadAsync();
    }

    private sealed class Reader(Stream stream, AudioBankReadLimits limits, CancellationToken token)
    {
        private readonly long length = stream.Length;
        private readonly List<AudioInspectionDiagnostic> diagnostics = [];
        private readonly List<AudioOffsetTable> tables = [];
        private readonly List<AudioOffsetRow> rows = [];
        private byte[] prefix = [];
        private long bytesRead;
        private int suppressed;
        private bool hitLimit, problem;
        private AudioBankFormat format;
        private OriginBankMetadata? origin;
        private ScdBankMetadata? scd;
        private static bool Span(long p, long n, long available) => p >= 0 && n >= 0 && p <= available && n <= available - p;
        private static ushort U16(byte[] bytes, int at) => BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(at, 2));
        private static uint U32(byte[] bytes, int at) => BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(at, 4));
        private static int I32(byte[] bytes, int at) => BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(at, 4));
        private void Diagnostic(string code, string message, AudioDiagnosticSeverity severity, long? at = null,
            AudioTableKind? table = null, int? ordinal = null)
        {
            if (severity == AudioDiagnosticSeverity.Problem) problem = true;
            if (diagnostics.Count < limits.MaximumDiagnostics) diagnostics.Add(new(code, message, severity, at, table, ordinal));
            else suppressed++;
        }
        private void Limit(string code, string message, long? at = null)
        {
            hitLimit = true; Diagnostic(code, message, AudioDiagnosticSeverity.Limit, at);
        }
        private AudioBankDocument Result(AudioInspectionStatus status)
        {
            token.ThrowIfCancellationRequested();
            return new(format, hitLimit ? AudioInspectionStatus.LimitReached : status, length, origin, scd,
                tables.AsReadOnly(), rows.AsReadOnly(), diagnostics.AsReadOnly(), Array.AsReadOnly(prefix), bytesRead, hitLimit, suppressed);
        }
        private async Task<byte[]?> ReadAt(long at, int count)
        {
            token.ThrowIfCancellationRequested();
            if (!Span(at, count, length)) throw new InvalidOperationException("Inspector attempted an unchecked span.");
            if (Span(at, count, prefix.Length)) return prefix.AsSpan((int)at, count).ToArray();
            if (hitLimit) return null;
            if (count > limits.MaximumMetadataBytes - bytesRead)
            {
                Limit("MetadataReadLimit", "The metadata read budget was reached; remaining metadata was not inspected.", at);
                return null;
            }
            var bytes = new byte[count]; stream.Position = at;
            await stream.ReadExactlyAsync(bytes, token).ConfigureAwait(false);
            bytesRead += count; token.ThrowIfCancellationRequested(); return bytes;
        }
        public async Task<AudioBankDocument> ReadAsync()
        {
            token.ThrowIfCancellationRequested();
            int count = (int)Math.Min(4096, Math.Min(length, limits.MaximumMetadataBytes));
            prefix = new byte[count]; stream.Position = 0;
            await stream.ReadExactlyAsync(prefix, token).ConfigureAwait(false);
            bytesRead = count; token.ThrowIfCancellationRequested();
            if (prefix.Length >= 7 && prefix.AsSpan(0, 7).SequenceEqual("ORIGIN\0"u8))
            {
                format = AudioBankFormat.Origin;
                if (length < 48)
                {
                    Diagnostic("OriginHeaderTruncated", "Stored ORIGIN metadata requires 48 available bytes.", AudioDiagnosticSeverity.Problem);
                    return Result(AudioInspectionStatus.Truncated);
                }
                byte[]? head = await ReadAt(0, 48).ConfigureAwait(false);
                if (head is null) return Result(AudioInspectionStatus.LimitReached);
                int end = Array.IndexOf(head, (byte)0, 16, 32); bool terminated = end >= 0;
                byte[] name = head.AsSpan(16, terminated ? end - 16 : 32).ToArray();
                origin = new(U32(head, 12), Escape(name), Convert.ToHexString(name), terminated);
                if (!terminated) Diagnostic("OriginNameUnterminated", "No NUL terminator occurs in the 32-byte stored name region.", AudioDiagnosticSeverity.Problem, 16);
                if (length != 48) Diagnostic("OriginLength", "The available payload is longer than the observed 48-byte serializer form.", AudioDiagnosticSeverity.Observation);
                return Result(problem ? AudioInspectionStatus.InvalidStructure : AudioInspectionStatus.MetadataRead);
            }
            if (prefix.Length >= 8 && prefix.AsSpan(0, 8).SequenceEqual("SEDBSSCF"u8))
            {
                format = AudioBankFormat.Scd;
                return await ReadScd().ConfigureAwait(false);
            }
            if (prefix.Length < Math.Min(length, 8)) Limit("SignatureReadLimit", "The budget did not allow a complete signature probe.");
            return Result(AudioInspectionStatus.Unrecognized);
        }
        private static string Escape(byte[] value)
        {
            var text = new StringBuilder();
            foreach (byte b in value)
                if (b == '\\') text.Append("\\\\");
                else if (b is >= 32 and <= 126) text.Append((char)b);
                else text.Append("\\x").Append(b.ToString("X2"));
            return text.ToString();
        }
        private async Task<AudioBankDocument> ReadScd()
        {
            if (length < 20)
            {
                Diagnostic("ScdHeaderTruncated", "SCD metadata requires at least 20 available header bytes.", AudioDiagnosticSeverity.Problem);
                return Result(AudioInspectionStatus.Truncated);
            }
            byte[]? head = await ReadAt(0, 20).ConfigureAwait(false);
            if (head is null) return Result(AudioInspectionStatus.LimitReached);
            scd = new(U32(head, 8), head[12], head[13], U16(head, 14), U32(head, 16));
            if (scd.Version is not (3 or 4))
            {
                Diagnostic("UnsupportedVersion", "Only stored little-endian version values 3 and 4 are inspected.", AudioDiagnosticSeverity.Observation, 8);
                return Result(AudioInspectionStatus.Unsupported);
            }
            if (scd.ProfileByte12 != 0 || scd.ProfileByte13 != 4)
            {
                Diagnostic("UnsupportedHeaderProfile", "Only the observed PC profile bytes +12=0 and +13=4 are inspected. Their meaning is not inferred.", AudioDiagnosticSeverity.Observation, 12);
                return Result(AudioInspectionStatus.Unsupported);
            }
            if (length != scd.DeclaredSizeAt16)
                Diagnostic("DeclaredSizeDiffers", "The stored size at +16 differs from the available payload length. Both bounds are reported separately.", AudioDiagnosticSeverity.Observation, 16);
            long h = scd.HeaderOffset;
            if (!Span(h, 32, length))
            {
                Diagnostic("TableHeaderTruncated", "The complete 32-byte tables header is outside the available payload.", AudioDiagnosticSeverity.Problem, h);
                return Result(AudioInspectionStatus.Truncated);
            }
            byte[]? header = await ReadAt(h, 32).ConfigureAwait(false);
            if (header is null) return Result(AudioInspectionStatus.LimitReached);
            scd = scd with { SequenceCount = U16(header, 0), TableBCount = U16(header, 2), TableCCount = U16(header, 4), BankId = U16(header, 6) };
            AddTable(AudioTableKind.Sequence, h + 32, scd.SequenceCount.Value);
            AddTable(AudioTableKind.B, U32(header, 8), scd.TableBCount.Value);
            AddTable(AudioTableKind.C, U32(header, 12), scd.TableCCount.Value);
            uint aux = U32(header, 16);
            AddTable(AudioTableKind.Aux, aux, scd.SequenceCount.Value, aux == 0);
            long total = tables.Where(t => t.Status != AudioTableStatus.Absent).Sum(t => (long)t.Count);
            if (tables.Any(t => t.Status != AudioTableStatus.Absent && t.Count > limits.MaximumTableEntries) || total > limits.MaximumRows)
            {
                Limit("TableEntryLimit", "The table-entry or total-row limit was exceeded. Header fields are shown; tables were not enumerated.");
                return Result(AudioInspectionStatus.LimitReached);
            }
            // Only these observed metadata spans are compared. Referent overlap is not forbidden.
            var metadata = new List<(long At, long Bytes)> { (0, 20), (h, 32) };
            metadata.AddRange(tables.Where(t => t.Status != AudioTableStatus.Absent && t.Count > 0 && Span(t.Offset, 4L * t.Count, length))
                .Select(t => (t.Offset, 4L * t.Count)));
            for (int ti = 0; ti < tables.Count; ti++)
            {
                token.ThrowIfCancellationRequested(); var table = tables[ti];
                if (table.Status == AudioTableStatus.Absent) continue;
                if (hitLimit) break;
                if (table.Count == 0) { tables[ti] = table with { Status = AudioTableStatus.Read }; continue; }
                if (!Span(table.Offset, 4L * table.Count, length))
                {
                    tables[ti] = table with { Status = AudioTableStatus.OutsideAvailableLength };
                    Diagnostic("TableOutsidePayload", "The complete offset table is outside the available payload.", AudioDiagnosticSeverity.Problem, table.Offset, table.Kind);
                    continue;
                }
                byte[]? offsets = await ReadAt(table.Offset, checked(table.Count * 4)).ConfigureAwait(false);
                if (offsets is null) break;
                int inspected = 0;
                for (int i = 0; i < table.Count; i++)
                {
                    token.ThrowIfCancellationRequested(); int target = I32(offsets, i * 4);
                    int minimum = table.Kind == AudioTableKind.Sequence ? (scd.Version == 3 ? 16 : 32) : table.Kind == AudioTableKind.Aux ? 128 : 1;
                    var state = target < 0 ? AudioTargetStatus.NegativeOffset : target == 0 ? AudioTargetStatus.NullOffset :
                        !Span(target, minimum, length) ? AudioTargetStatus.OutsideAvailableLength : AudioTargetStatus.Available;
                    bool declared = target > 0 && Span(target, minimum, scd.DeclaredSizeAt16);
                    bool overlap = target > 0 && Span(target, minimum, length) && metadata.Any(m => target < m.At + m.Bytes && m.At < (long)target + minimum);
                    ushort? id = null; byte? tracks = null;
                    if (state is AudioTargetStatus.NegativeOffset or AudioTargetStatus.OutsideAvailableLength)
                        Diagnostic(state.ToString(), "The stored target cannot be read within the available payload.", AudioDiagnosticSeverity.Problem, target, table.Kind, i);
                    else if (state == AudioTargetStatus.NullOffset)
                        Diagnostic("NullTarget", "The stored zero target was retained and not interpreted.", AudioDiagnosticSeverity.Observation, target, table.Kind, i);
                    if (state == AudioTargetStatus.Available && table.Kind == AudioTableKind.Sequence)
                    {
                        byte[]? sequence = await ReadAt(target, minimum).ConfigureAwait(false);
                        if (sequence is null) state = AudioTargetStatus.NotInspected;
                        else { id = U16(sequence, 12); tracks = sequence[0]; }
                    }
                    rows.Add(new(table.Kind, i, table.Offset + 4L * i, target, state, minimum, declared, id, tracks, OverlapsMetadata: overlap));
                    if (state != AudioTargetStatus.NotInspected) inspected++;
                    if (hitLimit) break;
                }
                tables[ti] = table with { Status = hitLimit ? AudioTableStatus.NotInspected : AudioTableStatus.Read, InspectedRows = inspected };
            }
            var targets = rows.Where(r => r.TargetOffset > 0).GroupBy(r => r.TargetOffset).ToDictionary(g => g.Key, g => g.Count());
            var ids = rows.Where(r => r.SoundId.HasValue).GroupBy(r => r.SoundId!.Value).ToDictionary(g => g.Key, g => g.Count());
            for (int i = 0; i < rows.Count; i++)
            {
                token.ThrowIfCancellationRequested(); var row = rows[i];
                rows[i] = row with { SharesTarget = row.TargetOffset > 0 && targets[row.TargetOffset] > 1,
                    DuplicateSoundId = row.SoundId is ushort id && ids[id] > 1 };
            }
            return Result(problem ? AudioInspectionStatus.InvalidStructure : AudioInspectionStatus.MetadataRead);
        }
        private void AddTable(AudioTableKind kind, long offset, int count, bool absent = false) =>
            tables.Add(new(kind, offset, count, absent ? AudioTableStatus.Absent : AudioTableStatus.NotInspected,
                !absent && Span(offset, 4L * count, scd!.DeclaredSizeAt16), 0));
    }
}
