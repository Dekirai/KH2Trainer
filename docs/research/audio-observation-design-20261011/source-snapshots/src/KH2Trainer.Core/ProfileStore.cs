using System.Text.Json;

namespace KH2Trainer.Core;

public sealed class ProfileStore(string folder)
{
    public string Folder { get; } = Path.GetFullPath(folder);
    public IReadOnlyList<string> List() => Directory.Exists(Folder) ? Directory.GetFiles(Folder, "*.json").OrderBy(Path.GetFileName).ToArray() : [];
    public string Save(TrainerProfile profile, IReadOnlyList<FeatureDefinition> catalog)
    {
        Validate(profile, catalog);
        if (string.IsNullOrWhiteSpace(profile.Name) || profile.Name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || profile.Name is "." or "..")
            throw new ArgumentException("Use a profile name without path separators or reserved filename characters.");
        Directory.CreateDirectory(Folder);
        string path = Path.GetFullPath(Path.Combine(Folder, profile.Name + ".json"));
        if (!string.Equals(Path.GetDirectoryName(path), Folder, StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Invalid profile path.");
        string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temporary, JsonSerializer.Serialize(profile, FeatureCatalog.JsonOptions));
            File.Move(temporary, path, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
        return path;
    }
    public TrainerProfile Read(string path, IReadOnlyList<FeatureDefinition> catalog)
    {
        var profile = JsonSerializer.Deserialize<TrainerProfile>(File.ReadAllText(path), FeatureCatalog.JsonOptions) ?? throw new InvalidDataException("Empty profile.");
        Validate(profile, catalog); return profile;
    }
    public static void Validate(TrainerProfile profile, IReadOnlyList<FeatureDefinition> catalog)
    {
        if (profile.Version != 1 || profile.GameHash != TargetGame.Sha256) throw new InvalidDataException("The profile belongs to a different trainer format or game build.");
        var byId = catalog.ToDictionary(f => f.Id, StringComparer.Ordinal);
        foreach (var pair in profile.Values)
        {
            if (!byId.TryGetValue(pair.Key, out var feature) || !feature.CanSaveInProfile || feature.Kind is FeatureKind.Action or FeatureKind.ReadOnly)
                throw new InvalidDataException($"{pair.Key} cannot be applied from a profile.");
            if (!feature.IsValidValue(pair.Value)) throw new InvalidDataException($"The value for {pair.Key} is outside its supported range.");
        }
    }
}
