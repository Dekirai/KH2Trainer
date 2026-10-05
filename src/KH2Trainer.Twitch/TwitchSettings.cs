using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace KH2Trainer.Twitch;

public enum RewardCategory { Help, Harm, Funny, Annoying }

/// <summary>What happens when an effect that is already running is redeemed again.</summary>
public enum SameEffectBehavior { Extend, Refund, Queue }

/// <summary>What happens when another effect of the same group (for example another Drive Form) is running.</summary>
public enum ConflictBehavior { Queue, Replace, Refund }

public enum RewardLanguage { English, German }

/// <summary>The streamer's choices for one reward. Null means "use the catalog default".</summary>
public sealed class RewardSettings
{
    public bool Enabled { get; set; }
    public string? Title { get; set; }
    public string? Prompt { get; set; }
    public int? Cost { get; set; }
    public int? DurationSeconds { get; set; }
    public int? Amount { get; set; }
    public int CooldownSeconds { get; set; }
    public int MaxPerStream { get; set; }
    public int MaxPerUserPerStream { get; set; }
    public string? ImagePath { get; set; }
    public SameEffectBehavior? SameEffect { get; set; }
    public ConflictBehavior? Conflict { get; set; }
    /// <summary>ID of the reward this app created on Twitch.</summary>
    public string? TwitchRewardId { get; set; }
    /// <summary>Fingerprint of the reward fields last sent to Twitch.</summary>
    public string? SyncedFingerprint { get; set; }
}

/// <summary>The Twitch application this build ships with.</summary>
public static class TwitchApp
{
    /// <summary>
    /// Client ID of a "Public" Twitch application registered for this trainer. When it is set,
    /// streamers only press Connect; when it is empty, each streamer enters the Client ID of their own app.
    /// </summary>
    public const string ClientId = "";
}

public sealed class TwitchSettings
{
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
        Converters = { new JsonStringEnumConverter() },
    };

    public int Version { get; set; } = 1;
    public string ClientId { get; set; } = "";
    public RewardLanguage Language { get; set; } = RewardLanguage.English;
    public SameEffectBehavior SameEffect { get; set; } = SameEffectBehavior.Extend;
    public ConflictBehavior Conflict { get; set; } = ConflictBehavior.Queue;
    public int MaxWaitMinutes { get; set; } = 10;
    public int MaxDurationSeconds { get; set; } = 600;
    public bool PauseTimersWhileNotReady { get; set; } = true;
    public bool PauseRewardsWhenClosed { get; set; } = true;
    public bool OverlayEnabled { get; set; } = true;
    public int OverlayPort { get; set; } = 17290;
    public Dictionary<string, RewardSettings> Rewards { get; set; } = new(StringComparer.Ordinal);

    /// <summary>The streamer's own Client ID, or the built-in one when none is entered.</summary>
    [JsonIgnore]
    public string EffectiveClientId => string.IsNullOrWhiteSpace(ClientId) ? TwitchApp.ClientId.Trim() : ClientId.Trim();

    public RewardSettings For(string key)
    {
        if (!Rewards.TryGetValue(key, out var reward)) Rewards[key] = reward = new RewardSettings();
        return reward;
    }

    /// <summary>
    /// Set when the settings file existed but could not be read. The damaged file is kept next to it, and
    /// reward IDs are unknown, so rewards found on Twitch are adopted instead of deleted.
    /// </summary>
    [JsonIgnore]
    public string? LoadProblem { get; private set; }

    /// <summary>Loads settings; a missing or damaged file yields defaults so the trainer always starts.</summary>
    public static TwitchSettings Load(string path)
    {
        if (!File.Exists(path)) return new TwitchSettings();
        try
        {
            if (JsonSerializer.Deserialize<TwitchSettings>(File.ReadAllText(path), Options) is { Version: 1 } settings)
            {
                settings.ClientId ??= "";
                settings.Rewards = new Dictionary<string, RewardSettings>(
                    (settings.Rewards ?? new()).Where(p => p.Value != null), StringComparer.Ordinal);
                settings.MaxWaitMinutes = Math.Clamp(settings.MaxWaitMinutes, 1, 120);
                settings.MaxDurationSeconds = Math.Clamp(settings.MaxDurationSeconds, 10, 3600);
                settings.OverlayPort = Math.Clamp(settings.OverlayPort, 1024, 65535);
                return settings;
            }
            return Damaged(path, "it was written by a different trainer version");
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException or NotSupportedException)
        {
            return Damaged(path, error.Message);
        }
    }

    private static TwitchSettings Damaged(string path, string reason)
    {
        string backup = $"{path}.bad-{DateTime.Now:yyyyMMdd-HHmmss}";
        try { File.Copy(path, backup, true); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { backup = path; }
        return new TwitchSettings { LoadProblem = $"The Twitch settings could not be read ({reason}). Defaults are in use; the old file was kept as {Path.GetFileName(backup)}." };
    }

    public void Save(string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllText(temporary, JsonSerializer.Serialize(this, Options)); File.Move(temporary, path, true); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}

/// <summary>A reward as it is sent to Twitch.</summary>
public sealed record RewardSpec(string Title, int Cost, string Prompt, string BackgroundColor,
    int GlobalCooldownSeconds, int MaxPerStream, int MaxPerUserPerStream)
{
    public const int MaxTitleLength = 45, MaxPromptLength = 200, MaxCooldownSeconds = 604800;

    /// <summary>Returns a problem description, or null when Twitch will accept the reward.</summary>
    public string? Validate()
    {
        if (string.IsNullOrWhiteSpace(Title)) return "The title is empty.";
        if (Title.Length > MaxTitleLength) return $"The title is longer than {MaxTitleLength} characters.";
        if (Prompt.Length > MaxPromptLength) return $"The description is longer than {MaxPromptLength} characters.";
        if (Cost < 1) return "The cost must be at least 1 channel point.";
        if (GlobalCooldownSeconds is < 0 or > MaxCooldownSeconds) return "The cooldown must be between 0 seconds and 7 days.";
        if (MaxPerStream < 0 || MaxPerUserPerStream < 0) return "Limits cannot be negative.";
        return null;
    }

    public string Fingerprint() => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
        string.Join('\u001f', Title, Cost, Prompt, BackgroundColor, GlobalCooldownSeconds, MaxPerStream, MaxPerUserPerStream))))[..16];
}
