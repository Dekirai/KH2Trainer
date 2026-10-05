using System.IO;
using System.Text.Json;

namespace KH2Trainer;

/// <summary>Small per-user preferences. A missing or damaged file falls back to defaults.</summary>
public sealed class UserSettings
{
    public static readonly string[] DefaultFavorites = ["player.restore", "combat.autoheal", "player_damage_guard", "time.multiplier", "trainer.shortcuts"];
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true, PropertyNameCaseInsensitive = true };

    public int Version { get; set; } = 1;
    public List<string> Favorites { get; set; } = [.. DefaultFavorites];
    public bool ShowDescriptions { get; set; }
    public string SaveFolder { get; set; } = "";

    public static UserSettings Load(string path)
    {
        try
        {
            if (File.Exists(path) && JsonSerializer.Deserialize<UserSettings>(File.ReadAllText(path), Options) is { Version: 1 } settings)
            {
                settings.Favorites = (settings.Favorites ?? []).Where(id => !string.IsNullOrWhiteSpace(id)).Distinct(StringComparer.Ordinal).ToList();
                settings.SaveFolder ??= "";
                return settings;
            }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        catch (JsonException) { }
        return new UserSettings();
    }

    /// <summary>Writes through a temporary file so a crash cannot leave a truncated file behind.</summary>
    public void Save(string path)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try { File.WriteAllText(temporary, JsonSerializer.Serialize(this, Options)); File.Move(temporary, path, true); }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}
