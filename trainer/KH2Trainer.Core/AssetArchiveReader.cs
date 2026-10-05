using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;

namespace KH2Trainer.Core;

/// <summary>Read-only parsers for disk BAR files and retail KH2 package pairs.</summary>
public sealed class AssetArchiveReader
{
    public AssetReadLimits Limits { get; }
    private readonly string[] protectedDirectories;
    public AssetArchiveReader(AssetReadLimits? limits = null, IEnumerable<string>? protectedDirectories = null)
    {
        Limits = limits ?? new(); Limits.Validate();
        this.protectedDirectories = protectedDirectories?.Select(Path.GetFullPath).ToArray() ?? [];
    }

    public AssetPayload OpenLooseFile(string path)
    {
        var stamp = AssetFileStamp.Capture(path);
        return new(Path.GetFileName(stamp.Path), stamp.Length, AssetSourceKind.LooseFile, stamp);
    }

    public PackageIndex OpenPackageIndex(string hedPath, string? namesFile = null, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!Path.GetExtension(hedPath).Equals(".hed", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Select a .hed package index.");
        var header = AssetFileStamp.Capture(hedPath);
        var package = AssetFileStamp.Capture(Path.ChangeExtension(header.Path, ".pkg"));
        if (header.Length % 32 != 0 || header.Length > Limits.MaximumMetadataBytes || header.Length / 32 > Limits.MaximumIndexEntries)
            throw new InvalidDataException("Invalid or oversized HED table.");
        using var source = header.Open();
        byte[] bytes = new byte[checked((int)header.Length)]; source.ReadExactly(bytes);
        var names = ReadNames(namesFile, cancellationToken);
        var entries = new List<PackageEntryInfo>(bytes.Length / 32);
        for (int i = 0; i < bytes.Length / 32; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var row = bytes.AsSpan(i * 32, 32);
            string hash = Convert.ToHexString(row[..16]).ToLowerInvariant();
            long offset = BinaryPrimitives.ReadInt64LittleEndian(row[16..]);
            int stored = BinaryPrimitives.ReadInt32LittleEndian(row[24..]);
            int original = BinaryPrimitives.ReadInt32LittleEndian(row[28..]);
            if (original < 0 || stored < 0) throw new InvalidDataException("Negative HED length.");
            RequireSpan(offset, stored, package.Length);
            bool resolved = names.TryGetValue(hash, out string? name);
            entries.Add(new(i, name ?? hash + ".dat", hash, resolved, offset, stored, original));
        }
        return new(header, package, Convert.ToHexString(SHA256.HashData(bytes)), entries.AsReadOnly());
    }

    public PackageAssetInfo InspectPackageEntry(PackageIndex index, int ordinal, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(index);
        if ((uint)ordinal >= (uint)index.Entries.Count) throw new ArgumentOutOfRangeException(nameof(ordinal));
        cancellationToken.ThrowIfCancellationRequested();
        using var hed = index.Header.Open();
        // The small index is fingerprinted in addition to its file identity.
        if (!Convert.ToHexString(SHA256.HashData(hed)).Equals(index.HeaderSha256, StringComparison.Ordinal))
            throw new IOException("The package index changed. Reopen it.");
        using var file = index.Package.Open();
        return AssetPackageCodec.Inspect(index, index.Entries[ordinal], file, Limits, cancellationToken);
    }

    public async Task<Stream> OpenReadAsync(AssetPayload payload, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(payload);
        cancellationToken.ThrowIfCancellationRequested();
        if (payload.Depth > Limits.MaximumDepth) throw new InvalidDataException("Container depth limit exceeded.");
        if (payload.Parent is not null)
        {
            var parent = await OpenReadAsync(payload.Parent, cancellationToken).ConfigureAwait(false);
            try
            {
                if (payload.ParentMetadataLength > Limits.MaximumMetadataBytes)
                    throw new InvalidDataException("Parent metadata exceeds this reader's limit.");
                if (payload.ParentMetadataHash is not null)
                {
                    byte[] current = new byte[payload.ParentMetadataLength];
                    await parent.ReadExactlyAsync(current, cancellationToken).ConfigureAwait(false);
                    if (!CryptographicOperations.FixedTimeEquals(SHA256.HashData(current), payload.ParentMetadataHash))
                        throw new IOException("The parent BAR table changed. Reopen its entries.");
                }
                return new AssetSliceStream(parent, payload.Offset, payload.Length);
            }
            catch { await parent.DisposeAsync().ConfigureAwait(false); throw; }
        }
        if (payload.PackageData is not null)
            return await AssetPackageCodec.DecodeAsync(payload, Limits, cancellationToken).ConfigureAwait(false);
        var file = payload.Source.Open();
        try { return new AssetSliceStream(file, payload.Offset, payload.Length); }
        catch { file.Dispose(); throw; }
    }

    public async Task<BarDocument> ReadBarAsync(AssetPayload payload, CancellationToken cancellationToken = default)
    {
        if (payload.Depth >= Limits.MaximumDepth) throw new InvalidDataException("Container depth limit exceeded.");
        await using var stream = await OpenReadAsync(payload, cancellationToken).ConfigureAwait(false);
        if (stream.Length < 16) throw new InvalidDataException("BAR header is truncated.");
        byte[] head = new byte[16]; await stream.ReadExactlyAsync(head, cancellationToken).ConfigureAwait(false);
        if (head[0] != 'B' || head[1] != 'A' || head[2] != 'R' || head[3] != 1)
            throw new InvalidDataException("Unsupported BAR signature/version. Disk BAR version 1 is required.");
        int count = BinaryPrimitives.ReadInt32LittleEndian(head.AsSpan(4));
        long tableEnd = 16L + 16L * count;
        if (count < 0 || count > Limits.MaximumBarEntries || tableEnd > Limits.MaximumMetadataBytes || tableEnd > stream.Length)
            throw new InvalidDataException("Invalid or oversized BAR table.");
        if (BinaryPrimitives.ReadUInt32LittleEndian(head.AsSpan(8)) != 0)
            throw new InvalidDataException("This BAR appears relocated; disk-relative offsets are required.");
        byte[] table = new byte[count * 16]; await stream.ReadExactlyAsync(table, cancellationToken).ConfigureAwait(false);
        byte[] metadataHash;
        using (var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256))
        { hash.AppendData(head); hash.AppendData(table); metadataHash = hash.GetHashAndReset(); }
        var entries = new List<BarEntryInfo>(count);
        var spans = new Dictionary<(uint Offset, uint Length), int>();
        for (int i = 0; i < count; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            int p = i * 16;
            ushort type = BinaryPrimitives.ReadUInt16LittleEndian(table.AsSpan(p));
            ushort link = BinaryPrimitives.ReadUInt16LittleEndian(table.AsSpan(p + 2));
            uint offset = BinaryPrimitives.ReadUInt32LittleEndian(table.AsSpan(p + 8));
            uint length = BinaryPrimitives.ReadUInt32LittleEndian(table.AsSpan(p + 12));
            if (length != 0)
            {
                RequireSpan(offset, length, stream.Length);
                if (offset < tableEnd) throw new InvalidDataException("BAR payload overlaps its entry table.");
            }
            string tagHex = Convert.ToHexString(table.AsSpan(p + 4, 4));
            string tag = DisplayBytes(table.AsSpan(p + 4, 4), false);
            int? alias = null;
            if (length != 0)
            {
                if (spans.TryGetValue((offset, length), out int previous)) alias = previous;
                else spans.Add((offset, length), i);
            }
            var child = new AssetPayload($"{i:D5}_{type:X4}_{tagHex}.bin", length, AssetSourceKind.BarEntry,
                payload.Source, length == 0 ? 0 : offset, payload, description: $"BAR entry {i}: {tag} ({TypeName(type)})",
                parentMetadataHash: metadataHash, parentMetadataLength: (int)tableEnd,
                entryOrdinal: i, barRawOffset: offset, barType: type, barTagHex: tagHex);
            entries.Add(new(i, type, TypeName(type), link, tagHex, tag, offset, length, alias, child));
        }
        return new(head[3], BinaryPrimitives.ReadUInt32LittleEndian(head.AsSpan(8)),
            BinaryPrimitives.ReadUInt32LittleEndian(head.AsSpan(12)), entries.AsReadOnly());
    }

    public async Task<byte[]> ReadPrefixAsync(AssetPayload payload, int maximumBytes = 65536, CancellationToken cancellationToken = default)
    {
        if (maximumBytes is < 0 or > 1048576) throw new ArgumentOutOfRangeException(nameof(maximumBytes));
        await using var stream = await OpenReadAsync(payload, cancellationToken).ConfigureAwait(false);
        var bytes = new byte[(int)Math.Min(payload.Length, maximumBytes)];
        await stream.ReadExactlyAsync(bytes, cancellationToken).ConfigureAwait(false); return bytes;
    }

    public static string Recognize(ReadOnlySpan<byte> data)
    {
        if (data.Length >= 4 && data[..4].SequenceEqual("BAR\x01"u8)) return "BAR container";
        if (data.Length >= 8 && data[..8].SequenceEqual(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 })) return "PNG image";
        if (data.Length >= 4 && data[..4].SequenceEqual("DDS "u8)) return "DDS texture";
        if (data.Length >= 4 && data[..4].SequenceEqual("TIM2"u8)) return "TIM2 texture";
        if (data.Length >= 4 && data[..4].SequenceEqual("IMGD"u8)) return "IMGD image";
        if (data.Length >= 4 && data[..4].SequenceEqual("IMGZ"u8)) return "IMGZ image collection";
        if (data.Length >= 8 && data[..8].SequenceEqual("SeBlock\0"u8)) return "SeBlock audio";
        return "Binary data";
    }

    public async Task ExportAsync(AssetPayload payload, string destinationFile, CancellationToken cancellationToken = default)
    {
        string destination = ValidateDestination(payload, destinationFile);
        string directory = Path.GetDirectoryName(destination)!;
        if (!Directory.Exists(directory)) throw new DirectoryNotFoundException("Select an existing destination folder.");
        using var directoryLocks = AssetFileAccess.LockDirectories(directory);
        ValidateDestination(payload, destination);
        cancellationToken.ThrowIfCancellationRequested();
        if (File.Exists(destination) || Directory.Exists(destination)) throw new IOException("The destination already exists. Choose a new filename.");
        string temporary = Path.Combine(directory, ".kh2-extract-" + Guid.NewGuid().ToString("N") + ".tmp");
        bool created = false;
        try
        {
            await using var input = await OpenReadAsync(payload, cancellationToken).ConfigureAwait(false);
            await using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 65536, FileOptions.Asynchronous))
            {
                created = true;
                await input.CopyToAsync(output, 65536, cancellationToken).ConfigureAwait(false);
                if (output.Length != payload.Length) throw new InvalidDataException("The extracted length does not match its descriptor.");
                await output.FlushAsync(cancellationToken).ConfigureAwait(false);
            }
            cancellationToken.ThrowIfCancellationRequested();
            ValidateDestination(payload, destination); // Recheck folder/path before publishing.
            File.Move(temporary, destination, overwrite: false); created = false;
        }
        finally { if (created && File.Exists(temporary)) File.Delete(temporary); }
    }

    private Dictionary<string, string> ReadNames(string? path, CancellationToken cancellationToken)
    {
        var names = new Dictionary<string, string>(StringComparer.Ordinal);
        if (path is null) return names;
        var stamp = AssetFileStamp.Capture(path);
        if (stamp.Length > Limits.MaximumMetadataBytes) throw new InvalidDataException("Name dictionary is oversized.");
        using var file = stamp.Open(); using var reader = new StreamReader(file, new UTF8Encoding(false, true));
        while (reader.ReadLine() is { } name)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (name.Length == 0) continue;
            if (name.Length > 1024 || names.Count >= Limits.MaximumIndexEntries) throw new InvalidDataException("Name dictionary limit exceeded.");
            string hash = Convert.ToHexString(MD5.HashData(Encoding.UTF8.GetBytes(name))).ToLowerInvariant();
            if (names.TryGetValue(hash, out var old) && old != name) throw new InvalidDataException("Conflicting names for a package hash.");
            names[hash] = name;
        }
        return names;
    }

    private string ValidateDestination(AssetPayload payload, string path)
    {
        // Win32 normalization can discard trailing spaces before validation.
        // Validate the spelling supplied by the caller first.
        if (path.StartsWith(@"\\?\", StringComparison.Ordinal) || path.StartsWith(@"\\.\", StringComparison.Ordinal) ||
            path.Split('\\', '/').Any(part => part.Length > 0 && (part.EndsWith(' ') || part.EndsWith('.'))))
            throw new IOException("Unsafe Windows destination filename.");
        string full = Path.GetFullPath(path);
        RejectReparsePath(full);
        foreach (string part in full[Path.GetPathRoot(full)!.Length..].Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))
        {
            string stem = part.Split('.')[0].TrimEnd(' ');
            if (part.Length == 0 || part.EndsWith(' ') || part.EndsWith('.') || part.Contains(':') ||
                part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
                new[] { "CON", "PRN", "AUX", "NUL", "CLOCK$" }.Contains(stem, StringComparer.OrdinalIgnoreCase) ||
                (stem.Length == 4 && (stem.StartsWith("COM", StringComparison.OrdinalIgnoreCase) || stem.StartsWith("LPT", StringComparison.OrdinalIgnoreCase)) && (stem[3] is >= '0' and <= '9' or '¹' or '²' or '³')))
                throw new IOException("Unsafe Windows destination filename.");
        }
        if (full.Equals(payload.SourcePath, StringComparison.OrdinalIgnoreCase) ||
            (payload.Kind != AssetSourceKind.LooseFile && full.Equals(Path.ChangeExtension(payload.SourcePath, ".hed"), StringComparison.OrdinalIgnoreCase)))
            throw new IOException("Cannot extract onto an asset source.");
        IEnumerable<string> roots = protectedDirectories;
        for (var parent = Directory.GetParent(payload.SourcePath); parent is not null; parent = parent.Parent)
            if (File.Exists(Path.Combine(parent.FullName, "KINGDOM HEARTS II FINAL MIX.exe")))
            { roots = roots.Append(parent.FullName); break; }
        if (roots.Any(root => IsWithin(full, root))) throw new IOException("Extract outside the game installation/protected source folder.");
        return full;
    }
    private static bool IsWithin(string path, string folder) => path.Equals(folder, StringComparison.OrdinalIgnoreCase) ||
        path.StartsWith(Path.TrimEndingDirectorySeparator(folder) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    internal static void RejectReparsePath(string path)
    {
        RejectDevicePath(path);
        for (string? item = Path.GetFullPath(path); item is not null; item = Path.GetDirectoryName(item))
        {
            if ((File.Exists(item) || Directory.Exists(item)) && (File.GetAttributes(item) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Symbolic links and reparse points are not supported for asset paths.");
            if (Path.GetPathRoot(item) == item) break;
        }
    }
    internal static void RejectDevicePath(string path)
    {
        if (path.StartsWith(@"\\?\", StringComparison.Ordinal) || path.StartsWith(@"\\.\", StringComparison.Ordinal))
            throw new IOException("Windows device paths are not asset files.");
    }
    internal static void RequireSpan(long offset, long length, long total)
    {
        if (offset < 0 || length < 0 || offset > total || length > total - offset)
            throw new InvalidDataException("Asset span lies outside its bounded source.");
    }
    internal static string DisplayBytes(ReadOnlySpan<byte> value, bool trimAtZero)
    {
        var text = new StringBuilder();
        foreach (byte b in value)
        {
            if (b == 0 && trimAtZero) break;
            if (b is >= 32 and <= 126 && b != '\\') text.Append((char)b);
            else text.Append($"\\x{b:X2}");
        }
        return text.ToString();
    }
    public static string TypeName(ushort type) => type switch
    {
        0 => "Dummy", 1 => "Binary/container", 2 => "List (context dependent)", 3 => "BDX script",
        4 => "Model", 7 => "Model texture", 8 => "DPX effects", 9 => "Motion", 10 => "TIM2 texture",
        17 => "Animation container", 18 => "PAX effects", 20 => "Motion set", 22 => "Event",
        24 => "IMGD image", 25 => "SEQD sequence", 28 => "Layout", 29 => "IMGZ images",
        30 => "Animation map", 31 => "SEB audio", 32 => "WD audio", 34 => "IOP voice",
        46 => "BAR container (type 46)", 48 => "VAG audio", _ => $"Type {type} (0x{type:X4})"
    };
}

internal sealed class AssetSliceStream : Stream
{
    private readonly Stream source;
    private readonly long start, length;
    private long position;
    internal AssetSliceStream(Stream source, long start, long length)
    {
        AssetArchiveReader.RequireSpan(start, length, source.Length);
        this.source = source; this.start = start; this.length = length;
    }
    public override bool CanRead => source.CanRead;
    public override bool CanSeek => source.CanSeek;
    public override bool CanWrite => false;
    public override long Length => length;
    public override long Position { get => position; set { AssetArchiveReader.RequireSpan(value, 0, length); position = value; } }
    public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));
    public override int Read(Span<byte> buffer)
    {
        source.Position = start + position;
        int read = source.Read(buffer[..(int)Math.Min(buffer.Length, length - position)]); position += read; return read;
    }
    public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken token = default)
    {
        token.ThrowIfCancellationRequested(); source.Position = start + position;
        int read = await source.ReadAsync(buffer[..(int)Math.Min(buffer.Length, length - position)], token).ConfigureAwait(false);
        position += read; return read;
    }
    public override long Seek(long offset, SeekOrigin origin)
    { Position = checked((origin switch { SeekOrigin.Begin => 0, SeekOrigin.Current => position, SeekOrigin.End => length, _ => throw new ArgumentOutOfRangeException(nameof(origin)) }) + offset); return position; }
    protected override void Dispose(bool disposing) { if (disposing) source.Dispose(); base.Dispose(disposing); }
    public override async ValueTask DisposeAsync() { await source.DisposeAsync().ConfigureAwait(false); GC.SuppressFinalize(this); }
    public override void Flush() { }
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
}
