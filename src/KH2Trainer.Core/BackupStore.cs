using System.IO.Compression;
using System.Text.Json;

namespace KH2Trainer.Core;

public sealed record BackupEntry(string Path, long Length, string Sha256);
public sealed record BackupManifest(int Version, string SourceFolder, DateTimeOffset CreatedAt, IReadOnlyList<BackupEntry> Files, bool EmptySource = false);
public sealed class BackupStore(string folder)
{
    public string Folder { get; } = Path.GetFullPath(folder);
    public string Create(string sourceFolder, Func<bool>? gameRunning = null) =>
        CreateCore(sourceFolder, gameRunning ?? (() => TargetGame.FindRunning().Count != 0), false);
    private string CreateCore(string sourceFolder, Func<bool> gameRunning, bool allowEmpty)
    {
        if (gameRunning()) throw new InvalidOperationException("Close the game before creating a save backup.");
        string source = Path.TrimEndingDirectorySeparator(Path.GetFullPath(sourceFolder));
        if (!Directory.Exists(source)) throw new DirectoryNotFoundException("Choose an existing save folder first.");
        if (IsInside(Folder, source) || IsInside(source, Folder)) throw new InvalidOperationException("The save folder and backup folder must be separate.");
        var files = EnumerateRegularFiles(source).ToArray();
        if (files.Length == 0 && !allowEmpty) throw new IOException("The selected folder contains no files.");
        if (files.Length > 5000 || files.Sum(p => new FileInfo(p).Length) > 1L << 30) throw new IOException("The selected folder is too large for a KH2 save backup. Choose the save folder itself.");
        Directory.CreateDirectory(Folder);
        string path = Path.Combine(Folder, $"KH2-{DateTime.Now:yyyyMMdd-HHmmss}-{Guid.NewGuid().ToString("N")[..6]}.zip");
        string temporary = path + ".tmp";
        try
        {
            var entries = new List<BackupEntry>();
            using (var archive = ZipFile.Open(temporary, ZipArchiveMode.Create))
            {
                foreach (string file in files)
                {
                    if (gameRunning()) throw new InvalidOperationException("The game started during backup. No completed backup was created.");
                    string relative = Path.GetRelativePath(source, file).Replace('\\', '/');
                    using var input = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read);
                    if (input.Length > 256L << 20) throw new IOException("An individual file is too large for a game-save backup.");
                    using var data = new MemoryStream(); input.CopyTo(data);
                    byte[] bytes = data.ToArray();
                    string hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
                    var entry = archive.CreateEntry("files/" + relative, CompressionLevel.Optimal);
                    using (var output = entry.Open()) output.Write(bytes);
                    entries.Add(new BackupEntry(relative, bytes.Length, hash));
                }
                var manifest = new BackupManifest(1, source, DateTimeOffset.UtcNow, entries, entries.Count == 0);
                using var writer = new StreamWriter(archive.CreateEntry("manifest.json").Open());
                writer.Write(JsonSerializer.Serialize(manifest, FeatureCatalog.JsonOptions));
            }
            if (gameRunning()) throw new InvalidOperationException("The game started during backup. No completed backup was created.");
            File.Move(temporary, path);
            Verify(path);
            return path;
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    public static BackupManifest Verify(string path)
    {
        using var archive = ZipFile.OpenRead(path);
        return Verify(archive);
    }
    private static BackupManifest Verify(ZipArchive archive)
    {
        if (archive.Entries.Count > 5001) throw new InvalidDataException("The backup contains too many files.");
        var manifestEntry = archive.GetEntry("manifest.json") ?? throw new InvalidDataException("The backup has no manifest.");
        if (manifestEntry.Length > 4 << 20) throw new InvalidDataException("The backup manifest is too large.");
        using var manifestStream = manifestEntry.Open();
        var manifest = JsonSerializer.Deserialize<BackupManifest>(manifestStream, FeatureCatalog.JsonOptions) ?? throw new InvalidDataException("The backup manifest is invalid.");
        if (manifest.Version != 1 || manifest.Files == null || manifest.EmptySource != (manifest.Files.Count == 0) || manifest.Files.Count > 5000 || manifest.Files.Any(f => f == null) || manifest.Files.Select(f => f.Path).Distinct(StringComparer.OrdinalIgnoreCase).Count() != manifest.Files.Count)
            throw new InvalidDataException("The backup directory is invalid.");
        if (archive.Entries.Count != manifest.Files.Count + 1 || manifest.Files.Any(f => f.Length < 0 || f.Length > 256L << 20) || manifest.Files.Sum(f => f.Length) > 1L << 30)
            throw new InvalidDataException("The backup has unexpected entries or exceeds the save backup size limit.");
        if (archive.Entries.Select(e => e.FullName).Distinct(StringComparer.OrdinalIgnoreCase).Count() != archive.Entries.Count)
            throw new InvalidDataException("The archive contains duplicate entries.");
        foreach (var file in manifest.Files)
        {
            ValidateRelativePath(file.Path);
            var entry = archive.GetEntry("files/" + file.Path) ?? throw new InvalidDataException($"Missing backup entry: {file.Path}");
            if (entry.Length != file.Length || file.Length < 0 || file.Length > 256L << 20) throw new InvalidDataException($"Invalid length: {file.Path}");
            using var stream = entry.Open();
            string hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(stream)).ToLowerInvariant();
            if (!string.Equals(hash, file.Sha256, StringComparison.Ordinal)) throw new InvalidDataException($"Checksum mismatch: {file.Path}");
        }
        return manifest;
    }
    public string Restore(string archivePath, string targetFolder, Func<bool> gameRunning)
    {
        if (gameRunning()) throw new InvalidOperationException("Close the game before restoring a save backup.");
        using var archive = ZipFile.OpenRead(archivePath);
        var manifest = Verify(archive);
        if (manifest.EmptySource) throw new InvalidOperationException("This backup records an empty previous save folder. It contains no save files to restore; existing files were not removed.");
        string target = Path.TrimEndingDirectorySeparator(Path.GetFullPath(targetFolder));
        if (!Directory.Exists(target)) throw new DirectoryNotFoundException("Choose the existing save folder to restore into.");
        var targets = manifest.Files.Select(e => (Entry: e, Path: ResolveTarget(target, e.Path))).ToArray();
        foreach (var item in targets) EnsureNoReparseParents(target, item.Path);
        string before = CreateCore(target, gameRunning, true);
        if (gameRunning()) throw new InvalidOperationException("The game started before restore. No save files were replaced.");
        var originals = new Dictionary<string, byte[]?>();
        try
        {
            foreach (var item in targets)
            {
                if (gameRunning()) throw new InvalidOperationException("The game started during restore. Previously replaced files will be restored to their prior contents.");
                EnsureNoReparseParents(target, item.Path);
                originals[item.Path] = File.Exists(item.Path) ? File.ReadAllBytes(item.Path) : null;
                Directory.CreateDirectory(Path.GetDirectoryName(item.Path)!);
                string temporary = item.Path + ".kh2trainer-" + Guid.NewGuid().ToString("N") + ".tmp";
                try
                {
                    using (var input = archive.GetEntry("files/" + item.Entry.Path)!.Open())
                    using (var output = new FileStream(temporary, FileMode.CreateNew)) input.CopyTo(output);
                    if (TargetGame.HashFile(temporary) != item.Entry.Sha256) throw new IOException("Restore verification failed.");
                    File.Move(temporary, item.Path, true);
                }
                finally { if (File.Exists(temporary)) File.Delete(temporary); }
            }
        }
        catch (Exception failure)
        {
            var rollbackErrors = new List<Exception>();
            foreach (var original in originals)
            {
                try
                {
                    EnsureNoReparseParents(target, original.Key);
                    if (original.Value == null) File.Delete(original.Key); else File.WriteAllBytes(original.Key, original.Value);
                }
                catch (Exception rollbackError) { rollbackErrors.Add(rollbackError); }
            }
            if (rollbackErrors.Count != 0)
                throw new AggregateException($"Restore failed and {rollbackErrors.Count} files could not be rolled back. The verified pre-restore backup is at: {before}", new[] { failure }.Concat(rollbackErrors));
            throw;
        }
        return before;
    }
    private static bool IsInside(string candidate, string root) => candidate.Equals(root, StringComparison.OrdinalIgnoreCase) || candidate.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    private static void ValidateRelativePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || Path.IsPathRooted(path) || path.Contains('\\') || path.Split('/').Any(p =>
            p is "" or "." or ".." || p.EndsWith('.') || p.EndsWith(' ') || p.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
            IsDeviceName(p)))
            throw new InvalidDataException("An archive entry has an unsafe relative path.");
    }
    private static bool IsDeviceName(string part)
    {
        string name = part.Split('.')[0].ToUpperInvariant();
        return name is "CON" or "PRN" or "AUX" or "NUL" or "CONIN$" or "CONOUT$" ||
            name.Length == 4 && (name.StartsWith("COM") || name.StartsWith("LPT")) && "123456789¹²³".Contains(name[3]);
    }
    private static string ResolveTarget(string root, string relative)
    {
        ValidateRelativePath(relative);
        string full = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!IsInside(full, root)) throw new InvalidDataException("An archive entry leaves the selected folder.");
        return full;
    }
    private static void EnsureNoReparseParents(string root, string path)
    {
        for (string? current = path; current != null && IsInside(current, root); current = Path.GetDirectoryName(current))
            if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Save backup paths cannot contain junctions or symbolic links.");
    }
    private static IEnumerable<string> EnumerateRegularFiles(string root)
    {
        if ((File.GetAttributes(root) & FileAttributes.ReparsePoint) != 0) throw new IOException("Choose the actual save folder, not a link.");
        foreach (var entry in Directory.EnumerateFileSystemEntries(root))
        {
            var attributes = File.GetAttributes(entry);
            if ((attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("The save folder contains a link; choose a folder containing only save data.");
            if ((attributes & FileAttributes.Directory) != 0) { foreach (var file in EnumerateRegularFiles(entry)) yield return file; }
            else yield return entry;
        }
    }
}
