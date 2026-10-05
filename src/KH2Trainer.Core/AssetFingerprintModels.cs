namespace KH2Trainer.Core;

public sealed record AssetFingerprintLimits
{
    public long MaximumPayloadBytes { get; init; } = 512L * 1024 * 1024;
    public int MaximumEntries { get; init; } = 10_000;
    public int MaximumJsonBytes { get; init; } = 16 * 1024 * 1024;
    public int MaximumPathParts { get; init; } = 32;
    internal void Validate()
    {
        if (MaximumPayloadBytes is < 0 or > 16L * 1024 * 1024 * 1024 ||
            MaximumEntries is < 1 or > 100_000 || MaximumJsonBytes is < 256 or > 64 * 1024 * 1024 ||
            MaximumPathParts is < 1 or > 64)
            throw new ArgumentOutOfRangeException(nameof(AssetFingerprintLimits));
    }
}

/// <summary>Portable descriptive identity. These values are never used to open files.</summary>
public sealed record AssetFingerprintPathPart(AssetSourceKind Kind, int Ordinal, int RemasteredOrdinal,
    string Name, long Offset, long Length, long StoredOffset, int BarType, string TagHex,
    string MetadataSha256);

/// <summary>A selected live locator plus a caller-chosen portable source namespace.</summary>
public sealed class AssetFingerprintSelection
{
    public AssetPayload Payload { get; }
    public string SourceKey { get; }
    public IReadOnlyList<AssetFingerprintPathPart> Path { get; }
    private AssetFingerprintSelection(AssetPayload payload, string sourceKey, IEnumerable<AssetFingerprintPathPart> path)
    {
        Payload = payload; SourceKey = sourceKey; Path = Array.AsReadOnly(path.ToArray());
        AssetFingerprintService.ValidateSourceKey(sourceKey);
    }

    public static AssetFingerprintSelection FromLoose(AssetPayload payload, string sourceKey)
    {
        ArgumentNullException.ThrowIfNull(payload);
        if (payload.Kind != AssetSourceKind.LooseFile || payload.Parent is not null || payload.PackageData is not null)
            throw new ArgumentException("Select a loose root file.", nameof(payload));
        return new(payload, sourceKey, [new(payload.Kind, -1, -1, payload.Name, 0, payload.Length, 0, -1, "", "")]);
    }

    public static AssetFingerprintSelection FromPackage(PackageIndex index, PackageAssetInfo asset,
        string sourceKey, int? remasteredOrdinal = null)
    {
        ArgumentNullException.ThrowIfNull(index); ArgumentNullException.ThrowIfNull(asset);
        int ordinal = asset.Entry.Ordinal;
        if ((uint)ordinal >= (uint)index.Entries.Count || !ReferenceEquals(index.Entries[ordinal], asset.Entry))
            throw new ArgumentException("The inspected entry does not belong to this index.", nameof(asset));
        AssetPayload payload;
        if (remasteredOrdinal is int n)
        {
            if ((uint)n >= (uint)asset.Remastered.Count || asset.Remastered[n].Ordinal != n)
                throw new ArgumentOutOfRangeException(nameof(remasteredOrdinal));
            payload = asset.Remastered[n].Payload;
        }
        else payload = asset.Original;
        var data = payload.PackageData;
        if (data is null || payload.Source != index.Package || data.HeaderFile != index.Header ||
            data.HeaderHash != index.HeaderSha256 || data.RecordOffset != asset.Entry.Offset ||
            data.EntryOrdinal != ordinal || data.RemasteredOrdinal != (remasteredOrdinal ?? -1) ||
            payload.Kind != (remasteredOrdinal.HasValue ? AssetSourceKind.PackageRemastered : AssetSourceKind.PackageOriginal))
            throw new ArgumentException("The payload does not belong to this package entry.", nameof(asset));
        return new(payload, sourceKey, [new(payload.Kind, ordinal, remasteredOrdinal ?? -1, payload.Name,
            data.RecordOffset, payload.Length, data.StoredOffset, -1, "",
            index.HeaderSha256 + ":" + Convert.ToHexString(data.MetadataHash))]);
    }

    public AssetFingerprintSelection Child(BarEntryInfo entry)
    {
        ArgumentNullException.ThrowIfNull(entry);
        var child = entry.Payload;
        if (entry.Ordinal < 0 || child.Kind != AssetSourceKind.BarEntry || !ReferenceEquals(child.Parent, Payload) ||
            child.EntryOrdinal != entry.Ordinal || child.BarRawOffset != entry.RelativeOffset ||
            child.BarType != entry.Type || child.BarTagHex != entry.TagHex ||
            child.Length != entry.Length || child.Offset != (entry.Length == 0 ? 0 : entry.RelativeOffset) ||
            child.Name != entry.SuggestedFileName || child.ParentMetadataHash is null)
            throw new ArgumentException("The BAR entry does not belong to this selection.", nameof(entry));
        if (Path.Count >= 64) throw new InvalidDataException("Fingerprint path depth exceeded.");
        return new(child, SourceKey, Path.Append(new(AssetSourceKind.BarEntry, entry.Ordinal, -1, child.Name,
            entry.RelativeOffset, child.Length, 0, entry.Type, entry.TagHex,
            Convert.ToHexString(child.ParentMetadataHash))));
    }

    public AssetFingerprintSelection WithSourceKey(string sourceKey) => new(Payload, sourceKey, Path);
}

public sealed class AssetFingerprint
{
    public string Id { get; }
    public string SourceKey { get; }
    public IReadOnlyList<AssetFingerprintPathPart> Path { get; }
    public long Length { get; }
    public string Md5 { get; }
    public string Sha256 { get; }
    public string DisplayName => Path[^1].Name;
    internal AssetFingerprint(string id, string sourceKey, IEnumerable<AssetFingerprintPathPart> path,
        long length, string md5, string sha256)
    {
        Id = id; SourceKey = sourceKey; Path = Array.AsReadOnly(path.ToArray());
        Length = length; Md5 = md5; Sha256 = sha256;
    }
}

public enum AssetFingerprintMatchKind { Sha256AndLength, LegacyMd5AndLength }
public sealed record AssetFingerprintMatch(AssetFingerprint Entry, AssetFingerprintMatchKind Kind);
