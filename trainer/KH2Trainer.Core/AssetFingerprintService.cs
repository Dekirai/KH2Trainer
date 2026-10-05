using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace KH2Trainer.Core;

/// <summary>Hashes only explicitly selected payloads. It never scans folders or follows stored locators.</summary>
public sealed class AssetFingerprintService
{
    public AssetFingerprintLimits Limits { get; }
    public AssetFingerprintService(AssetFingerprintLimits? limits = null)
    { Limits = limits ?? new(); Limits.Validate(); }

    public async Task<AssetFingerprint> CaptureAsync(AssetArchiveReader reader, AssetFingerprintSelection selection,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(reader); ArgumentNullException.ThrowIfNull(selection);
        cancellationToken.ThrowIfCancellationRequested();
        ValidateLocator(selection.SourceKey, selection.Path, selection.Payload.Length, Limits);
        await using var stream = await reader.OpenReadAsync(selection.Payload, cancellationToken).ConfigureAwait(false);
        using var md5 = IncrementalHash.CreateHash(HashAlgorithmName.MD5);
        using var sha256 = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[] buffer = new byte[64 * 1024]; long remaining = selection.Payload.Length;
        while (remaining > 0)
        {
            cancellationToken.ThrowIfCancellationRequested();
            int count = await stream.ReadAsync(buffer.AsMemory(0, (int)Math.Min(remaining, buffer.Length)), cancellationToken).ConfigureAwait(false);
            if (count == 0) throw new InvalidDataException("The asset ended before its declared length.");
            md5.AppendData(buffer, 0, count); sha256.AppendData(buffer, 0, count); remaining -= count;
        }
        if (await stream.ReadAsync(buffer.AsMemory(0, 1), cancellationToken).ConfigureAwait(false) != 0)
            throw new InvalidDataException("The asset exceeds its declared length.");
        cancellationToken.ThrowIfCancellationRequested();
        return new(Identity(selection.SourceKey, selection.Path), selection.SourceKey, selection.Path,
            selection.Payload.Length, Convert.ToHexString(md5.GetHashAndReset()), Convert.ToHexString(sha256.GetHashAndReset()));
    }

    internal static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true, PropertyNameCaseInsensitive = false, MaxDepth = 16,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        Converters = { new JsonStringEnumConverter<AssetSourceKind>(allowIntegerValues: false) }
    };

    internal static string Identity(string sourceKey, IReadOnlyList<AssetFingerprintPathPart> path) =>
        Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(new Locator(sourceKey, path), JsonOptions)));
    private sealed record Locator(string SourceKey, IReadOnlyList<AssetFingerprintPathPart> Path);

    internal static bool Hex(string? value, int length) => value is not null && value.Length == length &&
        value.All(c => c is >= '0' and <= '9' or >= 'A' and <= 'F');
    internal static void ValidateSourceKey(string? value)
    {
        // A portable namespace, not a filesystem path. It is never resolved automatically.
        if (string.IsNullOrWhiteSpace(value) || value.Length > 512 || value != value.Trim() ||
            value.Any(c => char.IsControl(c) || c is '/' or '\\' or ':') || value is "." or "..")
            throw new InvalidDataException("Choose a nonempty source label without a directory path (at most512 characters).");
    }
    internal static void ValidateLocator(string sourceKey, IReadOnlyList<AssetFingerprintPathPart>? path,
        long length, AssetFingerprintLimits limits)
    {
        ValidateSourceKey(sourceKey);
        if (length < 0 || length > limits.MaximumPayloadBytes || path is null || path.Count is < 1 || path.Count > limits.MaximumPathParts)
            throw new InvalidDataException("Invalid fingerprint length or path depth.");
        for (int i = 0; i < path.Count; i++)
        {
            var p = path[i];
            if (p is null || !Enum.IsDefined(p.Kind) || p.Name is null || p.Name.Length > 1024 ||
                p.Name.Any(char.IsControl) || p.Length < 0 || p.Offset < 0 || p.StoredOffset < 0 ||
                p.Offset > long.MaxValue - p.Length || p.TagHex is null || p.MetadataSha256 is null)
                throw new InvalidDataException("Invalid fingerprint path component.");
            if (i > 0)
            {
                if (p.Kind != AssetSourceKind.BarEntry || p.Ordinal < 0 || p.RemasteredOrdinal != -1 ||
                    p.BarType is < 0 or > 65535 || !Hex(p.TagHex, 8) || !Hex(p.MetadataSha256, 64) ||
                    p.StoredOffset != 0 || (p.Length != 0 && p.Offset + p.Length > path[i - 1].Length))
                    throw new InvalidDataException("Invalid nested BAR identity.");
            }
            else if (p.Kind == AssetSourceKind.LooseFile)
            {
                if (p.Ordinal != -1 || p.RemasteredOrdinal != -1 || p.Offset != 0 || p.StoredOffset != 0 ||
                    p.BarType != -1 || p.TagHex != "" || p.MetadataSha256 != "")
                    throw new InvalidDataException("Invalid loose-file identity.");
            }
            else if (p.Kind is AssetSourceKind.PackageOriginal or AssetSourceKind.PackageRemastered)
            {
                if (p.Ordinal < 0 || (p.Kind == AssetSourceKind.PackageOriginal ? p.RemasteredOrdinal != -1 : p.RemasteredOrdinal < 0) ||
                    p.BarType != -1 || p.TagHex != "" || p.MetadataSha256.Length != 129 || p.MetadataSha256[64] != ':' ||
                    !Hex(p.MetadataSha256[..64], 64) || !Hex(p.MetadataSha256[65..], 64))
                    throw new InvalidDataException("Invalid package identity.");
            }
            else throw new InvalidDataException("A fingerprint must start with a loose file or package payload.");
        }
        if (path[^1].Length != length) throw new InvalidDataException("Fingerprint length does not match its locator.");
    }
}

/// <summary>Versioned portable data. Loaded fingerprints are claims, not proof that source files still exist.</summary>
public sealed class AssetFingerprintIndex
{
    public const string Format = "KH2Trainer.AssetFingerprintIndex";
    public const int Version = 1;
    public IReadOnlyList<AssetFingerprint> Entries { get; }
    public AssetFingerprintLimits Limits { get; }
    private AssetFingerprintIndex(IEnumerable<AssetFingerprint> entries, AssetFingerprintLimits limits)
    { Entries = Array.AsReadOnly(entries.ToArray()); Limits = limits; }

    public static AssetFingerprintIndex Create(IEnumerable<AssetFingerprint>? entries = null, AssetFingerprintLimits? limits = null)
    {
        var bound = limits ?? new(); bound.Validate();
        var result = new List<AssetFingerprint>(); var identities = new HashSet<string>(StringComparer.Ordinal);
        foreach (var entry in entries ?? [])
        {
            if (result.Count >= bound.MaximumEntries) throw new InvalidDataException("Fingerprint entry limit exceeded.");
            Validate(entry, bound);
            if (!identities.Add(entry.Id)) throw new InvalidDataException("Duplicate fingerprint locator.");
            result.Add(entry);
        }
        return new(result, bound);
    }

    /// <summary>Adds a new locator or explicitly replaces the observation at an existing locator.</summary>
    public AssetFingerprintIndex With(AssetFingerprint entry)
    {
        Validate(entry, Limits);
        var copy = Entries.ToList(); int i = copy.FindIndex(e => e.Id == entry.Id);
        if (i >= 0) copy[i] = entry;
        else { if (copy.Count >= Limits.MaximumEntries) throw new InvalidDataException("Fingerprint entry limit exceeded."); copy.Add(entry); }
        return new(copy, Limits);
    }

    public IReadOnlyList<AssetFingerprintMatch> FindMatches(AssetFingerprint query, bool includeLegacyMd5 = false)
    {
        Validate(query, Limits);
        return Entries.Where(e => e.Length == query.Length && (e.Sha256 == query.Sha256 || (includeLegacyMd5 && e.Md5 == query.Md5)))
            .Select(e => new AssetFingerprintMatch(e, e.Sha256 == query.Sha256 ? AssetFingerprintMatchKind.Sha256AndLength : AssetFingerprintMatchKind.LegacyMd5AndLength))
            .ToArray();
    }

    public async Task SaveAsync(Stream destination, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(destination); cancellationToken.ThrowIfCancellationRequested();
        if (!destination.CanWrite) throw new ArgumentException("A writable destination is required.", nameof(destination));
        // Serialize into a bounded stream before touching the caller's destination.
        using var memory = new LimitedMemoryStream(Limits.MaximumJsonBytes);
        var data = new Document(Format, Version, Entries.Select(ToData).ToArray());
        await JsonSerializer.SerializeAsync(memory, data, AssetFingerprintService.JsonOptions, cancellationToken).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested(); memory.Position = 0;
        await memory.CopyToAsync(destination, 65536, cancellationToken).ConfigureAwait(false);
    }

    public static async Task<AssetFingerprintIndex> LoadAsync(Stream source, AssetFingerprintLimits? limits = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(source); var bound = limits ?? new(); bound.Validate();
        cancellationToken.ThrowIfCancellationRequested();
        if (!source.CanRead) throw new ArgumentException("A readable source is required.", nameof(source));
        using var memory = new LimitedMemoryStream(bound.MaximumJsonBytes); byte[] buffer = new byte[65536];
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            // Read at most one byte beyond the limit, even for non-seekable streams.
            int count = await source.ReadAsync(buffer.AsMemory(0, (int)Math.Min(buffer.Length, bound.MaximumJsonBytes - memory.Length + 1)), cancellationToken).ConfigureAwait(false);
            if (count == 0) break;
            memory.Write(buffer, 0, count);
        }
        cancellationToken.ThrowIfCancellationRequested();
        try
        {
            using var json = JsonDocument.Parse(memory.ToArray(), new JsonDocumentOptions { MaxDepth = 16 });
            RejectDuplicateProperties(json.RootElement, cancellationToken);
            RequireFields(json.RootElement, "Format", "Version", "Entries");
            var rows = json.RootElement.GetProperty("Entries");
            if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > bound.MaximumEntries)
                throw new InvalidDataException("Invalid fingerprint entry count.");
            foreach (var row in rows.EnumerateArray())
            {
                cancellationToken.ThrowIfCancellationRequested();
                RequireFields(row, "Id", "SourceKey", "Path", "Length", "Md5", "Sha256");
                var parts = row.GetProperty("Path");
                if (parts.ValueKind != JsonValueKind.Array || parts.GetArrayLength() is < 1 || parts.GetArrayLength() > bound.MaximumPathParts)
                    throw new InvalidDataException("Invalid fingerprint path depth.");
                foreach (var part in parts.EnumerateArray())
                    RequireFields(part, "Kind", "Ordinal", "RemasteredOrdinal", "Name", "Offset", "Length", "StoredOffset", "BarType", "TagHex", "MetadataSha256");
            }
            var document = json.RootElement.Deserialize<Document>(AssetFingerprintService.JsonOptions)
                ?? throw new InvalidDataException("A fingerprint document is required.");
            if (document.Format != Format || document.Version != Version || document.Entries is null || document.Entries.Length > bound.MaximumEntries)
                throw new InvalidDataException("Unsupported fingerprint format, version or entry count.");
            var entries = new List<AssetFingerprint>(); var identities = new HashSet<string>(StringComparer.Ordinal);
            foreach (var e in document.Entries)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (e is null || e.Path is null) throw new InvalidDataException("Missing fingerprint entry/path.");
                var entry = new AssetFingerprint(e.Id, e.SourceKey, e.Path, e.Length, e.Md5, e.Sha256);
                Validate(entry, bound);
                if (!identities.Add(entry.Id)) throw new InvalidDataException("Duplicate fingerprint locator.");
                entries.Add(entry);
            }
            cancellationToken.ThrowIfCancellationRequested();
            return new(entries, bound);
        }
        catch (JsonException e) { throw new InvalidDataException("Invalid fingerprint JSON.", e); }
    }
    private static void RequireFields(JsonElement node, params string[] fields)
    {
        if (node.ValueKind != JsonValueKind.Object || node.EnumerateObject().Count() != fields.Length ||
            fields.Any(name => !node.TryGetProperty(name, out _)))
            throw new InvalidDataException("Missing or unexpected fingerprint property.");
    }

    private static void Validate(AssetFingerprint entry, AssetFingerprintLimits limits)
    {
        if (entry is null) throw new InvalidDataException("A fingerprint entry is required.");
        AssetFingerprintService.ValidateLocator(entry.SourceKey, entry.Path, entry.Length, limits);
        if (!AssetFingerprintService.Hex(entry.Id, 64) || !AssetFingerprintService.Hex(entry.Md5, 32) ||
            !AssetFingerprintService.Hex(entry.Sha256, 64) || entry.Id != AssetFingerprintService.Identity(entry.SourceKey, entry.Path))
            throw new InvalidDataException("Invalid digest or fingerprint locator identity.");
    }
    private static void RejectDuplicateProperties(JsonElement node, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        if (node.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var p in node.EnumerateObject())
            { if (!names.Add(p.Name)) throw new InvalidDataException("Duplicate JSON property."); RejectDuplicateProperties(p.Value, token); }
        }
        else if (node.ValueKind == JsonValueKind.Array)
            foreach (var e in node.EnumerateArray()) RejectDuplicateProperties(e, token);
    }
    private sealed record Document(string Format, int Version, EntryData[] Entries);
    private sealed record EntryData(string Id, string SourceKey, AssetFingerprintPathPart[] Path, long Length, string Md5, string Sha256);
    private static EntryData ToData(AssetFingerprint e) => new(e.Id, e.SourceKey, e.Path.ToArray(), e.Length, e.Md5, e.Sha256);

    private sealed class LimitedMemoryStream(int maximum) : MemoryStream
    {
        private void Check(int count) { if (count < 0 || Position > maximum - count) throw new InvalidDataException("Fingerprint JSON exceeds the configured byte limit."); }
        public override void Write(byte[] buffer, int offset, int count) { Check(count); base.Write(buffer, offset, count); }
        public override void Write(ReadOnlySpan<byte> buffer) { Check(buffer.Length); base.Write(buffer); }
        public override void WriteByte(byte value) { Check(1); base.WriteByte(value); }
        public override Task WriteAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        { cancellationToken.ThrowIfCancellationRequested(); Write(buffer, offset, count); return Task.CompletedTask; }
        public override ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
        { cancellationToken.ThrowIfCancellationRequested(); Write(buffer.Span); return ValueTask.CompletedTask; }
    }
}
