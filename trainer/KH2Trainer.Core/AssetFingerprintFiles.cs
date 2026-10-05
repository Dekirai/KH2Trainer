namespace KH2Trainer.Core;

/// <summary>Explicit local index file operations. Stored locators are never resolved.</summary>
public static class AssetFingerprintFiles
{
    public static async Task<AssetFingerprintIndex> LoadAsync(string path, AssetFingerprintLimits? limits = null,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        RejectNetwork(path);
        var bound = limits ?? new(); bound.Validate();
        var stamp = AssetFileStamp.Capture(path);
        if (stamp.Length > bound.MaximumJsonBytes) throw new InvalidDataException("Fingerprint JSON exceeds the byte limit.");
        await using var input = stamp.Open();
        return await AssetFingerprintIndex.LoadAsync(input, bound, cancellationToken).ConfigureAwait(false);
    }

    public static async Task SaveNewAsync(AssetFingerprintIndex index, string destinationFile,
        IEnumerable<string> protectedDirectories, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(index); ArgumentNullException.ThrowIfNull(protectedDirectories);
        string[] roots = protectedDirectories.Select(Path.GetFullPath).ToArray();
        string path = Validate(destinationFile, roots);
        string directory = Path.GetDirectoryName(path)!;
        if (!Directory.Exists(directory)) throw new DirectoryNotFoundException("Choose an existing destination folder.");
        using var directoryLocks = AssetFileAccess.LockDirectories(directory);
        Validate(path, roots); cancellationToken.ThrowIfCancellationRequested();
        if (File.Exists(path) || Directory.Exists(path)) throw new IOException("Choose a new filename. Existing files are kept.");
        string temporary = Path.Combine(directory, ".kh2-fingerprints-" + Guid.NewGuid().ToString("N") + ".tmp");
        bool owned = false;
        try
        {
            await using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 65536, FileOptions.Asynchronous))
            {
                owned = true;
                await index.SaveAsync(output, cancellationToken).ConfigureAwait(false);
                await output.FlushAsync(cancellationToken).ConfigureAwait(false);
            }
            cancellationToken.ThrowIfCancellationRequested(); Validate(path, roots);
            File.Move(temporary, path, overwrite: false); owned = false;
        }
        finally { if (owned && File.Exists(temporary)) File.Delete(temporary); }
    }

    private static void RejectNetwork(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        AssetArchiveReader.RejectDevicePath(path);
        if (Path.GetFullPath(path).StartsWith(@"\\", StringComparison.Ordinal))
            throw new IOException("Choose a local index file.");
    }
    private static string Validate(string path, IReadOnlyList<string> roots)
    {
        RejectNetwork(path);
        if (path.Split('\\', '/').Any(p => p.Length > 0 && (p.EndsWith(' ') || p.EndsWith('.'))))
            throw new IOException("Unsafe Windows destination filename.");
        string full = Path.GetFullPath(path); AssetArchiveReader.RejectReparsePath(full);
        foreach (string part in full[Path.GetPathRoot(full)!.Length..].Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))
        {
            string stem = part.Split('.')[0].TrimEnd(' ');
            if (part.Length == 0 || part.Contains(':') || part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
                new[] { "CON", "PRN", "AUX", "NUL", "CLOCK$" }.Contains(stem, StringComparer.OrdinalIgnoreCase) ||
                (stem.Length == 4 && (stem.StartsWith("COM", StringComparison.OrdinalIgnoreCase) || stem.StartsWith("LPT", StringComparison.OrdinalIgnoreCase)) &&
                 (stem[3] is >= '0' and <= '9' or '¹' or '²' or '³')))
                throw new IOException("Unsafe Windows destination filename.");
        }
        foreach (var root in roots)
        {
            string prefix = root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (full.Equals(prefix, StringComparison.OrdinalIgnoreCase) || full.StartsWith(prefix + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new IOException("Save the index outside game/protected source folders.");
        }
        return full;
    }
}
