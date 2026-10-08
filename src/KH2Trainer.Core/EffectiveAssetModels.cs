using System.Buffers.Binary;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text.Json;

[assembly: InternalsVisibleTo("KH2Trainer.Core.Tests")]

namespace KH2Trainer.Core;

public enum EffectiveAssetProviderKind { PanaceaRawRecord, PanaceaLooseDev, PanaceaLooseMod, PanaceaLooseExtract, RetailPackage }
public enum EffectiveAssetBindingStrength { OfflineManifestBinding }

/// <summary>Explicit offline inputs. Roots are absolute, already resolved through /kh2.
/// This does not describe or discover a running game's provider state.</summary>
public sealed record EffectiveAssetManifestOptions
{
    public required string RetailExecutablePath { get; init; }
    public string? PanaceaLibraryPath { get; init; }
    public string? ModRoot { get; init; }
    public string? DevRoot { get; init; }
    public string? ExtractRoot { get; init; }
    public bool PlatformTransformEnabled { get; init; } = true;
    public IReadOnlyList<EffectivePackageProvider> Packages { get; init; } = Array.Empty<EffectivePackageProvider>();
    public IReadOnlyList<EffectiveManifestEvidence> ConfigurationEvidence { get; init; } = Array.Empty<EffectiveManifestEvidence>();
}
public sealed record EffectivePackageProvider(string HeaderPath, string PackagePath, bool DecodeEnabled);
public sealed record EffectiveManifestEvidence(string Path, string ExpectedSha256);
public sealed record EffectiveAssetFileIdentity(string Path, long Length, ulong LastWriteTime, uint Volume,
    ulong FileIndex, ulong CreationTime);
public sealed record EffectiveAssetSourceStamp(EffectiveAssetFileIdentity File, string? HeaderSha256,
    string MetadataSha256, string DecodedSha256, int? ProviderOrdinal, int? HedOrdinal, long? RecordOffset);

/// <summary>Owned primary bytes only. No native loader, registration, BAR/model or motion safety is implied.</summary>
public sealed class OwnedAssetBytes
{
    public ReadOnlyMemory<byte> Bytes { get; }
    public EffectiveAssetProviderKind ProviderKind { get; }
    public EffectiveAssetSourceStamp SourceStamp { get; }
    public string RelativeName { get; }
    public ReadOnlyMemory<byte> MatchedNameBytes { get; }
    public string ManifestSha256 { get; }
    public EffectiveAssetBindingStrength BindingStrength => EffectiveAssetBindingStrength.OfflineManifestBinding;
    internal OwnedAssetBytes(byte[] bytes, EffectiveAssetProviderKind kind, EffectiveAssetSourceStamp stamp,
        string relativeName, byte[] matchedName, string manifestHash)
    { Bytes = bytes; ProviderKind = kind; SourceStamp = stamp; RelativeName = relativeName;
      MatchedNameBytes = matchedName; ManifestSha256 = manifestHash; }
}

/// <summary>Factory-verified, immutable offline provider manifest. Neither caller-owned collections
/// nor a caller-supplied "verified" flag can change the selected provider order.</summary>
public sealed class EffectiveAssetManifest
{
    public const string SupportedRetailSha256 = "9002B2DE6A1F91A790BD0673DE125D1CF833F7942BFEC827CDCF6BA64D5849ED";
    public const string SupportedPanaceaSha256 = "055D5032324EAB2ED8F03F2A1B3FF3381642F82B3239A17164C25BEF8815E68D";
    public string? ModRoot { get; }
    public string? DevRoot { get; }
    public string? ExtractRoot { get; }
    public bool PlatformTransformEnabled { get; }
    public bool HasPanacea { get; }
    public string Sha256 { get; }
    public AssetReadLimits Limits { get; }
    public EffectiveAssetBindingStrength BindingStrength => EffectiveAssetBindingStrength.OfflineManifestBinding;
    public IReadOnlyList<EffectivePackageProvider> Packages { get; }
    public IReadOnlyList<EffectiveManifestEvidence> VerifiedEvidence { get; }
    internal sealed record BoundFile(AssetFileStamp Stamp, string? Hash);
    internal sealed record BoundPackage(BoundFile Header, BoundFile Package, bool DecodeEnabled);
    internal IReadOnlyList<BoundFile> Evidence { get; }
    internal IReadOnlyList<BoundPackage> Providers { get; }

    private EffectiveAssetManifest(string? mod, string? dev, string? extract, bool transform, bool panacea,
        AssetReadLimits limits, BoundFile[] evidence, BoundPackage[] packages)
    {
        ModRoot = mod; DevRoot = dev; ExtractRoot = extract; PlatformTransformEnabled = transform;
        HasPanacea = panacea; Limits = limits; Evidence = Array.AsReadOnly(evidence);
        Providers = Array.AsReadOnly(packages);
        VerifiedEvidence = Array.AsReadOnly(evidence.Select(e => new EffectiveManifestEvidence(e.Stamp.Path, e.Hash!)).ToArray());
        Packages = Array.AsReadOnly(packages.Select(p => new EffectivePackageProvider(p.Header.Stamp.Path,
            p.Package.Stamp.Path, p.DecodeEnabled)).ToArray());
        Sha256 = Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(new {
            schema = 1, binding = nameof(EffectiveAssetBindingStrength.OfflineManifestBinding),
            namePolicy = "ASCII-relative-forward-slash;per-provider-final-component-lowercase", mod, dev, extract,
            transform, panacea, limits, evidence, packages })));
    }

    public static Task<EffectiveAssetManifest> VerifyAsync(EffectiveAssetManifestOptions options,
        AssetReadLimits? limits = null, CancellationToken cancellationToken = default) =>
        VerifyWithProfileAsync(options, limits ?? new(), SupportedRetailSha256, SupportedPanaceaSha256, cancellationToken);

    // Test assembly supplies hashes of temporary synthetic binaries; production callers cannot choose a profile.
    internal static async Task<EffectiveAssetManifest> VerifyWithProfileAsync(EffectiveAssetManifestOptions options,
        AssetReadLimits limits, string retailHash, string panaceaHash, CancellationToken token = default)
    {
        ArgumentNullException.ThrowIfNull(options); limits.Validate(); token.ThrowIfCancellationRequested();
        // Copy before any await: input lists, records and roots are never retained from a caller-owned container.
        var packageInputs = CopyInputs(options.Packages); var evidenceInputs = CopyInputs(options.ConfigurationEvidence);
        string exe = EffectiveAssetPaths.Absolute(options.RetailExecutablePath);
        string? dll = string.IsNullOrEmpty(options.PanaceaLibraryPath) ? null : EffectiveAssetPaths.Absolute(options.PanaceaLibraryPath);
        string? mod = EffectiveAssetPaths.Root(options.ModRoot), dev = EffectiveAssetPaths.Root(options.DevRoot),
            extract = EffectiveAssetPaths.Root(options.ExtractRoot);
        if (dll is null && (mod is not null || dev is not null || extract is not null))
            throw new NotSupportedException("Override roots require the verified supported Panacea provider.");
        if (dll is not null && mod is null) throw new InvalidDataException("A Panacea manifest requires its resolved mod root.");
        var evidence = new List<BoundFile>(); var packages = new List<BoundPackage>();
        var held = new List<FileStream>();
        try
        {
            async Task<BoundFile> Bind(string path, string? expectedHash, bool hashContent)
            {
                token.ThrowIfCancellationRequested(); path = EffectiveAssetPaths.Absolute(path);
                var stamp = AssetFileStamp.Capture(path); var file = stamp.Open(); held.Add(file);
                string? hash = null;
                if (hashContent)
                {
                    if (stamp.Length > 1L << 30) throw new InvalidDataException("Manifest evidence exceeds the 1 GiB hashing limit.");
                    hash = Convert.ToHexString(await SHA256.HashDataAsync(file, token).ConfigureAwait(false));
                    if (expectedHash is not null && !hash.Equals(expectedHash, StringComparison.OrdinalIgnoreCase))
                        throw new NotSupportedException("Provider or configuration fingerprint is not the requested verified build: " + path);
                }
                return new(stamp, hash);
            }
            evidence.Add(await Bind(exe, retailHash, true).ConfigureAwait(false));
            if (dll is not null) evidence.Add(await Bind(dll, panaceaHash, true).ConfigureAwait(false));
            foreach (var input in evidenceInputs)
            {
                if (input is null || input.ExpectedSha256 is null || input.ExpectedSha256.Length != 64 ||
                    !input.ExpectedSha256.All(Uri.IsHexDigit)) throw new InvalidDataException("Invalid configuration fingerprint.");
                evidence.Add(await Bind(input.Path, input.ExpectedSha256, true).ConfigureAwait(false));
            }
            long totalMetadata = 0;
            foreach (var input in packageInputs)
            {
                if (input is null) throw new InvalidDataException("Null package descriptor.");
                string hedPath = EffectiveAssetPaths.Absolute(input.HeaderPath), pkgPath = EffectiveAssetPaths.Absolute(input.PackagePath);
                if (!Path.GetExtension(hedPath).Equals(".hed", StringComparison.OrdinalIgnoreCase) ||
                    !Path.GetExtension(pkgPath).Equals(".pkg", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("Explicit HED/PKG descriptors are required.");
                var hedStamp = AssetFileStamp.Capture(hedPath);
                totalMetadata = checked(totalMetadata + hedStamp.Length);
                if (hedStamp.Length % 32 != 0 || totalMetadata > limits.MaximumMetadataBytes ||
                    hedStamp.Length / 32 > limits.MaximumIndexEntries) throw new InvalidDataException("HED metadata limit or row alignment is invalid.");
                var hed = await Bind(hedPath, null, true).ConfigureAwait(false);
                var pkg = await Bind(pkgPath, null, false).ConfigureAwait(false);
                if (hed.Stamp != hedStamp) throw new IOException("HED identity changed during manifest verification.");
                if (packages.Any(p => p.Header.Stamp.Volume == hed.Stamp.Volume && p.Header.Stamp.FileIndex == hed.Stamp.FileIndex))
                    throw new InvalidDataException("Duplicate package provider identity.");
                var file = held[^2]; file.Position = 0; byte[] row = new byte[32];
                for (long i = 0; i < hed.Stamp.Length / 32; i++)
                {
                    token.ThrowIfCancellationRequested(); file.ReadExactly(row);
                    long offset = BinaryPrimitives.ReadInt64LittleEndian(row.AsSpan(16));
                    int stored = BinaryPrimitives.ReadInt32LittleEndian(row.AsSpan(24)), raw = BinaryPrimitives.ReadInt32LittleEndian(row.AsSpan(28));
                    if (raw < 0) throw new InvalidDataException("Negative HED original size.");
                    AssetArchiveReader.RequireSpan(offset, stored, pkg.Stamp.Length);
                }
                packages.Add(new(hed, pkg, input.DecodeEnabled));
            }
            return new(mod, dev, extract, options.PlatformTransformEnabled, dll is not null, limits with { }, evidence.ToArray(), packages.ToArray());
        }
        finally { foreach (var file in held) file.Dispose(); }
    }

    private static T[] CopyInputs<T>(IReadOnlyList<T>? inputs)
    {
        if (inputs is null || inputs.Count is < 0 or > 32) throw new InvalidDataException("Manifest provider/evidence limit exceeded.");
        int declaredCount = inputs.Count; var result = new List<T>();
        foreach (var input in inputs)
        {
            if (result.Count >= 32) throw new InvalidDataException("Manifest input changed or exceeds its declared bound.");
            result.Add(input);
        }
        if (result.Count != declaredCount) throw new InvalidDataException("Manifest input count changed during capture.");
        return result.ToArray();
    }
}

internal static class EffectiveAssetPaths
{
    internal static string Absolute(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path) ||
            (path.Length >= 2 && IsSeparator(path[0]) && IsSeparator(path[1])))
            throw new NotSupportedException("An explicit local absolute path is required; resolve relative roots before creating the manifest.");
        AssetArchiveReader.RejectDevicePath(path);
        string root = Path.GetPathRoot(path)!;
        foreach (string part in path[root.Length..].Split('\\', '/'))
            if (part.Length > 0) Component(part);
        string full = Path.GetFullPath(path);
        // Check canonical spelling before *any* filesystem probe: Win32 also normalizes // and mixed separators to UNC.
        AssetArchiveReader.RejectDevicePath(full);
        if (full.StartsWith(@"\\", StringComparison.Ordinal)) throw new NotSupportedException("Network provider paths are not supported.");
        AssetArchiveReader.RejectReparsePath(full); return full;
    }
    internal static string? Root(string? path)
    {
        if (string.IsNullOrEmpty(path)) return null;
        string full = Path.TrimEndingDirectorySeparator(Absolute(path));
        if (!Path.GetFileName(full).Equals("kh2", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Provider roots must already include the resolved /kh2 suffix.");
        return full;
    }
    internal static byte[] Name(string name)
    {
        if (string.IsNullOrEmpty(name) || name.Length > 1024 || name.Any(c => c < 32 || c > 126 || c == '\\'))
            throw new NotSupportedException("Asset names require 1..1024 strict ASCII characters and forward slashes.");
        foreach (string part in name.Split('/')) Component(part);
        return System.Text.Encoding.ASCII.GetBytes(name);
    }
    private static void Component(string part)
    {
        string stem = part.Split('.')[0].TrimEnd(' ');
        if (part.Length == 0 || part is "." or ".." || part.EndsWith(' ') || part.EndsWith('.') ||
            part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
            new[] { "CON", "PRN", "AUX", "NUL", "CLOCK$" }.Contains(stem, StringComparer.OrdinalIgnoreCase) ||
            (stem.Length == 4 && (stem.StartsWith("COM", StringComparison.OrdinalIgnoreCase) ||
                stem.StartsWith("LPT", StringComparison.OrdinalIgnoreCase)) && (stem[3] is >= '0' and <= '9' or '¹' or '²' or '³')))
            throw new InvalidDataException("Unsafe or ambiguous asset path component.");
    }
    private static bool IsSeparator(char value) => value is '\\' or '/';
}
