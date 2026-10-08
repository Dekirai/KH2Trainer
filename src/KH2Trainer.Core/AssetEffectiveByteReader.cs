using System.Buffers.Binary;
using System.Security.Cryptography;

namespace KH2Trainer.Core;

/// <summary>Reads primary asset bytes for an explicitly verified offline provider manifest.
/// Rechecking absent overrides improves offline consistency; it cannot bind a future native load.</summary>
public sealed class AssetEffectiveByteReader
{
    private readonly EffectiveAssetManifest manifest;
    public AssetEffectiveByteReader(EffectiveAssetManifest manifest) => this.manifest = manifest ?? throw new ArgumentNullException(nameof(manifest));

    public Task<OwnedAssetBytes> ReadAsync(string relativeName, CancellationToken cancellationToken = default) =>
        ReadCoreAsync(relativeName, cancellationToken, null);

    // Deterministic race injection at the exact pre-publication boundary; inaccessible to production callers.
    internal Task<OwnedAssetBytes> ReadForTestAsync(string name, Action beforePublish, CancellationToken token = default) =>
        ReadCoreAsync(name, token, beforePublish);

    private async Task<OwnedAssetBytes> ReadCoreAsync(string relativeName, CancellationToken token, Action? beforePublish)
    {
        byte[] nameBytes = EffectiveAssetPaths.Name(relativeName); token.ThrowIfCancellationRequested();
        var held = new List<(AssetFileStamp Stamp, FileStream File)>(); var directories = new List<IDisposable>();
        var absent = new List<(string Path, CandidateState State)>();
        try
        {
            FileStream Open(AssetFileStamp stamp)
            {
                // Keep all ancestors and read handles until after final identity/selection checks.
                directories.Add(AssetFileAccess.LockDirectories(Path.GetDirectoryName(stamp.Path)!));
                var file = stamp.Open(); held.Add((stamp, file)); return file;
            }
            async Task<FileStream> OpenBound(EffectiveAssetManifest.BoundFile input)
            {
                var file = Open(input.Stamp);
                if (input.Hash is not null && Convert.ToHexString(await SHA256.HashDataAsync(file, token).ConfigureAwait(false)) != input.Hash)
                    throw new IOException("Manifest evidence or HED content changed; verify a new offline manifest.");
                file.Position = 0; return file;
            }
            foreach (var input in manifest.Evidence) await OpenBound(input).ConfigureAwait(false);
            var providers = new List<(EffectiveAssetManifest.BoundPackage Bound, FileStream Header, FileStream Package)>();
            foreach (var provider in manifest.Providers)
                providers.Add((provider, await OpenBound(provider.Header).ConfigureAwait(false), await OpenBound(provider.Package).ConfigureAwait(false)));

            OwnedAssetBytes? result = null;
            if (manifest.HasPanacea)
            {
                var candidates = new (string? Root, string Prefix, EffectiveAssetProviderKind Kind)[] {
                    (manifest.ModRoot, "raw/", EffectiveAssetProviderKind.PanaceaRawRecord),
                    (manifest.DevRoot, "", EffectiveAssetProviderKind.PanaceaLooseDev),
                    (manifest.ModRoot, "", EffectiveAssetProviderKind.PanaceaLooseMod),
                    (manifest.ExtractRoot, "", EffectiveAssetProviderKind.PanaceaLooseExtract) };
                foreach (var candidate in candidates)
                {
                    token.ThrowIfCancellationRequested(); if (candidate.Root is null) continue;
                    string path = EffectiveAssetPaths.Absolute(Path.Combine(candidate.Root,
                        (candidate.Prefix + relativeName).Replace('/', Path.DirectorySeparatorChar)));
                    var state = Candidate(path);
                    if (state != CandidateState.File) { absent.Add((path, state)); continue; }
                    var stamp = AssetFileStamp.Capture(path); var file = Open(stamp);
                    if (candidate.Kind == EffectiveAssetProviderKind.PanaceaRawRecord)
                        result = await ReadRecord(file, stamp, 0, stamp.Length, true, candidate.Kind,
                            null, null, null, relativeName, nameBytes, null, token).ConfigureAwait(false);
                    else
                    {
                        if (stamp.Length <= 0 || stamp.Length > manifest.Limits.MaximumDecodedBytes)
                            throw new InvalidDataException("Selected loose override is empty or exceeds the decoded byte limit.");
                        byte[] bytes = new byte[(int)stamp.Length]; await file.ReadExactlyAsync(bytes, token).ConfigureAwait(false);
                        result = Make(bytes, candidate.Kind, stamp, null, Convert.ToHexString(SHA256.HashData(Array.Empty<byte>())),
                            null, null, null, relativeName, nameBytes);
                    }
                    break; // No catch-and-fallback for an existing source, including empty/corrupt sources.
                }
            }
            if (result is null)
            {
                byte[] lowerName = (byte[])nameBytes.Clone(); int last = relativeName.LastIndexOf('/') + 1;
                for (int i = last; i < lowerName.Length; i++) if (lowerName[i] is >= (byte)'A' and <= (byte)'Z') lowerName[i] += 32;
                byte[] exact = MD5.HashData(nameBytes), lower = MD5.HashData(lowerName);
                for (int providerOrdinal = 0; providerOrdinal < providers.Count; providerOrdinal++)
                {
                    var provider = providers[providerOrdinal];
                    byte[] hed = new byte[(int)provider.Bound.Header.Stamp.Length]; provider.Header.Position = 0;
                    await provider.Header.ReadExactlyAsync(hed, token).ConfigureAwait(false);
                    if (Convert.ToHexString(SHA256.HashData(hed)) != provider.Bound.Header.Hash)
                        throw new IOException("HED content changed during selection.");
                    int ordinal = FindUnique(hed, exact, token); byte[] matched = nameBytes;
                    if (ordinal < 0 && !exact.AsSpan().SequenceEqual(lower)) { ordinal = FindUnique(hed, lower, token); matched = lowerName; }
                    if (ordinal < 0) continue;
                    int p = ordinal * 32; long offset = BinaryPrimitives.ReadInt64LittleEndian(hed.AsSpan(p + 16));
                    int length = BinaryPrimitives.ReadInt32LittleEndian(hed.AsSpan(p + 24));
                    int raw = BinaryPrimitives.ReadInt32LittleEndian(hed.AsSpan(p + 28));
                    result = await ReadRecord(provider.Package, provider.Bound.Package.Stamp, offset, length,
                        provider.Bound.DecodeEnabled, EffectiveAssetProviderKind.RetailPackage, providerOrdinal,
                        ordinal, provider.Bound.Header.Hash, relativeName, matched, raw, token).ConfigureAwait(false);
                    break;
                }
            }
            if (result is null) throw new FileNotFoundException("No manifest provider contains the requested asset.", relativeName);
            beforePublish?.Invoke(); token.ThrowIfCancellationRequested();
            foreach (var (path, state) in absent)
                if (Candidate(path) != state) throw new IOException("A higher-priority override changed during the offline read; retry with current sources.");
            foreach (var (stamp, file) in held)
            {
                token.ThrowIfCancellationRequested();
                if (AssetFileAccess.Stamp(stamp.Path, file) != stamp) throw new IOException("Source identity changed before publication.");
            }
            return result;
        }
        finally
        {
            foreach (var (_, file) in held) file.Dispose();
            for (int i = directories.Count - 1; i >= 0; i--) directories[i].Dispose();
        }
    }

    private async Task<OwnedAssetBytes> ReadRecord(FileStream file, AssetFileStamp stamp, long offset, long length,
        bool decode, EffectiveAssetProviderKind kind, int? provider, int? ordinal, string? hedHash, string name,
        byte[] matchedName, int? declaredRaw, CancellationToken token)
    {
        var record = AssetPackageCodec.InspectRecord(file, offset, length, manifest.Limits, token, decode);
        if (record.Original.RawLength <= 0 || (declaredRaw is not null && declaredRaw != record.Original.RawLength))
            throw new InvalidDataException("Selected record is empty or its HED and PKG original lengths disagree.");
        var part = record.Original;
        byte[] bytes = await AssetPackageCodec.DecodeBoundedAsync(file, checked(offset + part.Offset), part.StoredLength,
            part.RawLength, part.Mode, record.Seed, manifest.Limits, token, decode, manifest.PlatformTransformEnabled).ConfigureAwait(false);
        file.Position = offset; byte[] recheck = new byte[record.Metadata.Length]; await file.ReadExactlyAsync(recheck, token).ConfigureAwait(false);
        if (!recheck.AsSpan().SequenceEqual(record.Metadata)) throw new IOException("Selected record metadata changed during decoding.");
        return Make(bytes, kind, stamp, hedHash, Convert.ToHexString(SHA256.HashData(record.Metadata)), provider, ordinal, offset, name, matchedName);
    }

    private OwnedAssetBytes Make(byte[] bytes, EffectiveAssetProviderKind kind, AssetFileStamp stamp,
        string? hedHash, string metadataHash, int? provider, int? ordinal, long? offset, string name, byte[] matchedName) =>
        new(bytes, kind, new(new(stamp.Path, stamp.Length, stamp.LastWriteTime, stamp.Volume, stamp.FileIndex, stamp.CreationTime),
            hedHash, metadataHash, Convert.ToHexString(SHA256.HashData(bytes)), provider, ordinal, offset), name,
            (byte[])matchedName.Clone(), manifest.Sha256);

    private static int FindUnique(byte[] hed, byte[] hash, CancellationToken token)
    {
        int found = -1;
        for (int i = 0; i < hed.Length / 32; i++)
        {
            token.ThrowIfCancellationRequested();
            if (!hed.AsSpan(i * 32, 16).SequenceEqual(hash)) continue;
            if (found >= 0) throw new InvalidDataException("Ambiguous duplicate HED rows for the selected asset digest.");
            found = i;
        }
        return found;
    }
    private enum CandidateState { Absent, Directory, File }
    private static CandidateState Candidate(string path)
    {
        // File.Exists swallows access and I/O errors, which would silently select a lower provider.
        for (string? part = path; part is not null; part = Path.GetDirectoryName(part))
        {
            try
            {
                var attributes = File.GetAttributes(part);
                if ((attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("Reparse points are not supported in provider paths.");
            }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
            if (Path.GetPathRoot(part) == part) break;
        }
        try { return (File.GetAttributes(path) & FileAttributes.Directory) != 0 ? CandidateState.Directory : CandidateState.File; }
        catch (FileNotFoundException) { return CandidateState.Absent; }
        catch (DirectoryNotFoundException) { return CandidateState.Absent; }
    }
}
