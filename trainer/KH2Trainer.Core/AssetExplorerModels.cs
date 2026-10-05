namespace KH2Trainer.Core;

public enum AssetSourceKind { LooseFile, PackageOriginal, PackageRemastered, BarEntry }

public sealed record AssetReadLimits
{
    public int MaximumIndexEntries { get; init; } = 1_000_000;
    public int MaximumBarEntries { get; init; } = 65_536;
    public int MaximumMetadataBytes { get; init; } = 32 * 1024 * 1024;
    public int MaximumDecodedBytes { get; init; } = 512 * 1024 * 1024;
    public int MaximumDepth { get; init; } = 16;
    internal void Validate()
    {
        if (MaximumIndexEntries < 1 || MaximumBarEntries < 1 || MaximumMetadataBytes < 16 ||
            MaximumDecodedBytes < 16 || MaximumDepth is < 1 or > 64)
            throw new ArgumentOutOfRangeException(nameof(AssetReadLimits));
    }
}

/// <summary>An immutable, bounded locator. Constructed only by AssetArchiveReader.</summary>
public sealed class AssetPayload
{
    public string Name { get; }
    public long Length { get; }
    public AssetSourceKind Kind { get; }
    public string SourcePath => Source.Path;
    public string Description { get; }
    internal AssetFileStamp Source { get; }
    internal AssetPayload? Parent { get; }
    internal long Offset { get; }
    internal AssetPackageCodec.PayloadInfo? PackageData { get; }
    internal byte[]? ParentMetadataHash { get; }
    internal int ParentMetadataLength { get; }
    internal int Depth { get; }
    internal int EntryOrdinal { get; }
    internal uint BarRawOffset { get; }
    internal ushort BarType { get; }
    internal string? BarTagHex { get; }
    internal AssetPayload(string name, long length, AssetSourceKind kind, AssetFileStamp source,
        long offset = 0, AssetPayload? parent = null, AssetPackageCodec.PayloadInfo? packageData = null,
        string? description = null, byte[]? parentMetadataHash = null, int parentMetadataLength = 0,
        int entryOrdinal = -1, uint barRawOffset = 0, ushort barType = 0, string? barTagHex = null)
    {
        Name = name; Length = length; Kind = kind; Source = source; Offset = offset;
        Parent = parent; PackageData = packageData; Depth = parent is null ? 0 : parent.Depth + 1;
        Description = description ?? kind.ToString();
        ParentMetadataHash = parentMetadataHash; ParentMetadataLength = parentMetadataLength;
        EntryOrdinal = entryOrdinal; BarRawOffset = barRawOffset; BarType = barType; BarTagHex = barTagHex;
    }
}

public sealed record BarEntryInfo(int Ordinal, ushort Type, string TypeName, ushort LinkIndex,
    string TagHex, string Tag, uint RelativeOffset, uint Length, int? AliasOf, AssetPayload Payload)
{
    public string SuggestedFileName => $"{Ordinal:D5}_{Type:X4}_{TagHex}.bin";
}
public sealed record BarDocument(byte VersionFlags, uint RuntimeBase, uint Auxiliary,
    IReadOnlyList<BarEntryInfo> Entries);

public sealed class PackageEntryInfo
{
    public int Ordinal { get; }
    public string Name { get; }
    public string NameHash { get; }
    public bool HasResolvedName { get; }
    public long Offset { get; }
    public int StoredLength { get; }
    public int OriginalLength { get; }
    public bool IsAvailable => StoredLength != 0;
    internal PackageEntryInfo(int ordinal, string name, string hash, bool resolved, long offset, int stored, int original)
    { Ordinal = ordinal; Name = name; NameHash = hash; HasResolvedName = resolved; Offset = offset; StoredLength = stored; OriginalLength = original; }
}
public sealed class PackageIndex
{
    public string HeaderPath => Header.Path;
    public string PackagePath => Package.Path;
    public string HeaderSha256 { get; }
    public IReadOnlyList<PackageEntryInfo> Entries { get; }
    internal AssetFileStamp Header { get; }
    internal AssetFileStamp Package { get; }
    internal PackageIndex(AssetFileStamp header, AssetFileStamp package, string hash, IReadOnlyList<PackageEntryInfo> entries)
    { Header = header; Package = package; HeaderSha256 = hash; Entries = entries; }
}
public sealed record RemasteredAssetInfo(int Ordinal, string Name, string NameBytesHex,
    uint LogicalOffset, uint OriginalAssetOffset, long StoredOffset, int StoredMode, AssetPayload Payload);
public sealed record PackageAssetInfo(PackageEntryInfo Entry, int StoredMode, int CreationValue,
    AssetPayload Original, IReadOnlyList<RemasteredAssetInfo> Remastered);

internal sealed record AssetFileStamp(string Path, long Length, ulong LastWriteTime, uint Volume,
    ulong FileIndex, ulong CreationTime)
{
    internal static AssetFileStamp Capture(string path)
    {
        AssetArchiveReader.RejectDevicePath(path);
        path = System.IO.Path.GetFullPath(path);
        AssetArchiveReader.RejectReparsePath(path);
        using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return AssetFileAccess.Stamp(path, file);
    }
    internal FileStream Open()
    {
        AssetArchiveReader.RejectReparsePath(Path);
        var file = new FileStream(Path, FileMode.Open, FileAccess.Read, FileShare.Read, 65536,
            FileOptions.Asynchronous | FileOptions.RandomAccess);
        try
        {
            var current = AssetFileAccess.Stamp(Path, file);
            if (file.Length != Length || current != this)
                throw new IOException("The asset source changed. Reopen it before inspecting or extracting.");
            return file;
        }
        catch { file.Dispose(); throw; }
    }
}
