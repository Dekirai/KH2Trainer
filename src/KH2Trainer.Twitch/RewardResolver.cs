using System.Globalization;

namespace KH2Trainer.Twitch;

/// <summary>Combines catalog defaults with the streamer's settings.</summary>
public static class RewardResolver
{
    public static string Title(EffectDefinition effect, TwitchSettings settings) =>
        Clean(settings.Rewards.GetValueOrDefault(effect.Key)?.Title) ?? effect.TitleFor(settings.Language);

    public static int Duration(EffectDefinition effect, TwitchSettings settings) => effect.IsTimed
        ? Math.Clamp(settings.Rewards.GetValueOrDefault(effect.Key)?.DurationSeconds ?? effect.DurationSeconds, 1, settings.MaxDurationSeconds)
        : 0;

    public static int Amount(EffectDefinition effect, TwitchSettings settings) => effect.Amount > 0
        ? Math.Clamp(settings.Rewards.GetValueOrDefault(effect.Key)?.Amount ?? effect.Amount, effect.MinAmount, effect.MaxAmount)
        : 0;

    /// <summary>The description viewers see. Default texts state the duration and amount.</summary>
    public static string Prompt(EffectDefinition effect, TwitchSettings settings)
    {
        if (Clean(settings.Rewards.GetValueOrDefault(effect.Key)?.Prompt) is { } custom) return custom;
        bool german = settings.Language == RewardLanguage.German;
        string text = effect.PromptFor(settings.Language);
        if (effect.IsTimed) text += german ? $" Dauer: {Duration(effect, settings)} s." : $" Duration: {Duration(effect, settings)} s.";
        // Numbers follow the reward language, not the PC's regional settings.
        var culture = CultureInfo.GetCultureInfo(german ? "de-DE" : "en-US");
        if (effect.Amount > 0) text += $" ({Amount(effect, settings).ToString("N0", culture)} {effect.AmountLabelFor(settings.Language)})";
        return text.Length <= RewardSpec.MaxPromptLength ? text : text[..RewardSpec.MaxPromptLength];
    }

    public static RewardSpec Spec(EffectDefinition effect, TwitchSettings settings)
    {
        var reward = settings.Rewards.GetValueOrDefault(effect.Key) ?? new RewardSettings();
        return new RewardSpec(Title(effect, settings), reward.Cost ?? effect.Cost, Prompt(effect, settings), effect.Color,
            reward.CooldownSeconds, reward.MaxPerStream, reward.MaxPerUserPerStream);
    }

    public static EffectOptions Options(EffectDefinition effect, TwitchSettings settings)
    {
        var reward = settings.Rewards.GetValueOrDefault(effect.Key);
        return new EffectOptions(Title(effect, settings), Duration(effect, settings), Amount(effect, settings),
            reward?.SameEffect ?? settings.SameEffect, reward?.Conflict ?? settings.Conflict);
    }

    public static EngineSettings Engine(TwitchSettings settings) =>
        new(TimeSpan.FromMinutes(settings.MaxWaitMinutes), settings.MaxDurationSeconds, settings.PauseTimersWhileNotReady);

    /// <summary>The reward's image when it is a supported image file that exists.</summary>
    public static string? ImagePath(string key, TwitchSettings settings) =>
        settings.Rewards.GetValueOrDefault(key)?.ImagePath is { Length: > 0 } path && OverlayServer.ImageType(path) != null && File.Exists(path) ? path : null;

    /// <summary>What the stream overlay shows right now.</summary>
    public static OverlayState Overlay(EffectEngine engine, TwitchSettings settings)
    {
        string Color(string key) => EffectCatalog.Find(key)?.Color ?? "#5B9BFF";
        bool Image(string key) => ImagePath(key, settings) != null;
        return new OverlayState(
            engine.ActiveEffects.Select(a => new OverlayEffect(a.Key, a.Title, a.Viewers, a.Detail, a.RemainingSeconds, a.DurationSeconds, Color(a.Key), Image(a.Key), !a.Established)).ToArray(),
            engine.PendingEffects.Select(p => new OverlayQueued(p.RedemptionId, p.Key, p.Title, p.Viewer, p.Status, Color(p.Key), Image(p.Key))).ToArray(),
            engine.RecentEvents.Where(e => e.Kind is EffectEventKind.Started or EffectEventKind.Done or EffectEventKind.Extended).Take(5)
                .Select(e => new OverlayEvent(e.Time.ToUnixTimeMilliseconds(), e.Key,
                    $"{e.Viewer}: {e.Title}{(e.Detail is { } detail ? " · " + detail : "")}", Color(e.Key), Image(e.Key))).ToArray());
    }

    private static string? Clean(string? text) => string.IsNullOrWhiteSpace(text) ? null : text.Trim();
}
