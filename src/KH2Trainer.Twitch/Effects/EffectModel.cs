using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>The trainer's live game connection as seen by the effect engine.</summary>
public interface IGameControl
{
    bool IsConnected { get; }
    bool SceneReady { get; }
    bool Supports(int capabilitySlot);
    bool TryRead(int valueSlot, out double value);
    /// <summary>Sends a trainer command. Throws when the bridge rejects it.</summary>
    Task ExecuteAsync(int command, IReadOnlyList<double> arguments, string label);
}

/// <summary>Twitch side of a redemption: fulfil it or give the points back.</summary>
public interface IRedemptionSink
{
    void Fulfill(Redemption redemption);
    void Refund(Redemption redemption, string reason);
}

/// <summary>A channel point redemption, or a local test run (IsTest) that never touches Twitch.</summary>
public sealed record Redemption(string Id, string RewardKey, string UserName, string UserInput, DateTimeOffset RedeemedAt,
    string TwitchRewardId = "", bool IsTest = false);

/// <summary>Looks up trainer features by catalog ID.</summary>
public sealed class FeatureMap
{
    private readonly Dictionary<string, FeatureDefinition> features;
    public FeatureMap(IEnumerable<FeatureDefinition> catalog) => features = catalog.ToDictionary(f => f.Id, StringComparer.Ordinal);
    public bool Contains(string id) => features.ContainsKey(id);
    public FeatureDefinition Get(string id) => features.TryGetValue(id, out var feature) ? feature
        : throw new InvalidOperationException($"The trainer catalog has no feature '{id}'.");
}

public enum ReadinessKind { Ready, Wait, Reject }

/// <summary>Whether an effect can start now, should wait, or cannot work at all (refund).</summary>
public readonly record struct Readiness(ReadinessKind Kind, string Reason)
{
    public static readonly Readiness Ready = new(ReadinessKind.Ready, "");
    public static Readiness Wait(string reason) => new(ReadinessKind.Wait, reason);
    public static Readiness Reject(string reason) => new(ReadinessKind.Reject, reason);
}

public enum EffectStatus { Running, Ended, Failed }

/// <summary>Reported by a running effect's monitor on every tick.</summary>
public readonly record struct EffectProgress(EffectStatus Status, string Reason)
{
    public static readonly EffectProgress Running = new(EffectStatus.Running, "");
    public static EffectProgress Ended(string reason) => new(EffectStatus.Ended, reason);
    public static EffectProgress Failed(string reason) => new(EffectStatus.Failed, reason);
}

public enum EndReason { Expired, Replaced, Interrupted, EndedByGame, Stopped }

/// <summary>Thrown by an effect that cannot do anything useful right now; the viewer is refunded.</summary>
public sealed class EffectRejectedException(string reason) : Exception(reason);

/// <summary>One redeemable effect. Durations and amounts are defaults the streamer can change.</summary>
public sealed class EffectDefinition
{
    public required string Key { get; init; }
    public required RewardCategory Category { get; init; }
    public required string Title { get; init; }
    public required string TitleDe { get; init; }
    public required string Prompt { get; init; }
    public required string PromptDe { get; init; }
    public required int Cost { get; init; }
    /// <summary>0 for one-time effects.</summary>
    public int DurationSeconds { get; init; }
    /// <summary>0 when the effect has no adjustable amount.</summary>
    public int Amount { get; init; }
    public string AmountLabel { get; init; } = "";
    public int MinAmount { get; init; } = 1;
    public int MaxAmount { get; init; } = 999999;
    /// <summary>Effects of one group change the same part of the game and never run at the same time.</summary>
    public string? Group { get; init; }
    /// <summary>Ends the running effect of its group instead of waiting for it (for example Revert).</summary>
    public bool Interrupts { get; init; }
    /// <summary>Changes the loaded save (inventory, munny, EXP, room) and stays after the effect.</summary>
    public bool ChangesSaveData { get; init; }
    /// <summary>Overrides the global maximum waiting time when the effect waits for a game situation.</summary>
    public int MaxWaitSeconds { get; init; }
    /// <summary>Trainer features the effect uses; all must be available for it to start.</summary>
    public required IReadOnlyList<string> Features { get; init; }
    public Func<EffectContext, Readiness>? Check { get; init; }
    public required Func<EffectContext, Task> Start { get; init; }
    /// <summary>Runs when a timed effect ends. Defaults to restoring every value the effect changed.</summary>
    public Func<EffectContext, Task>? End { get; init; }
    public Func<EffectContext, EffectProgress>? Monitor { get; init; }

    public bool IsTimed => DurationSeconds > 0;
    public string TitleFor(RewardLanguage language) => language == RewardLanguage.German ? TitleDe : Title;
    public string PromptFor(RewardLanguage language) => language == RewardLanguage.German ? PromptDe : Prompt;
    public string Color => ColorOf(Category);

    public static string ColorOf(RewardCategory category) => category switch
    {
        RewardCategory.Help => "#1F8B4C",
        RewardCategory.Harm => "#C0392B",
        RewardCategory.Funny => "#8E44AD",
        _ => "#D68910",
    };
}

/// <summary>
/// State of one running effect. Values changed with <see cref="SetAsync"/> remember their original
/// and are restored at the end only while the game still shows the value this effect applied, so a
/// form change, a script or the streamer's own edit is never overwritten with a stale original.
/// </summary>
public sealed class EffectContext
{
    private sealed class OwnedValue(FeatureDefinition feature, double applied, double? original, bool restore, bool sustain)
    {
        public FeatureDefinition Feature { get; } = feature;
        public double Applied { get; set; } = applied;
        public double? Original { get; set; } = original;
        public bool Restore { get; } = restore;
        public bool Sustain { get; } = sustain;
    }

    private readonly IGameControl game;
    private readonly FeatureMap features;
    private readonly Func<TimeSpan, Task> delay;
    private readonly List<OwnedValue> owned = [];

    public EffectContext(EffectDefinition definition, Redemption redemption, int durationSeconds, int amount,
        IGameControl game, FeatureMap features, Random random, Func<TimeSpan, Task> delay)
    {
        Definition = definition; Redemption = redemption; DurationSeconds = durationSeconds; Amount = amount;
        this.game = game; this.features = features; Random = random; this.delay = delay;
    }

    public EffectDefinition Definition { get; }
    public Redemption Redemption { get; }
    public int DurationSeconds { get; }
    public int Amount { get; }
    public Random Random { get; }
    /// <summary>False while an effect still waits for the game to confirm it (for example a Drive Form loading).</summary>
    public bool Established { get; set; } = true;
    /// <summary>Real time since the effect started.</summary>
    public TimeSpan SinceStart { get; internal set; }
    public EndReason EndReason { get; internal set; }
    /// <summary>Scratch values an effect keeps between its start, monitor and end.</summary>
    public Dictionary<string, double> State { get; } = new(StringComparer.Ordinal);
    /// <summary>A short result shown to viewers, for example the item a mystery gift produced.</summary>
    public string? Detail { get; set; }

    public bool Supports(string featureId) => game.Supports(features.Get(featureId).CapabilitySlot);

    public double? Read(string featureId)
    {
        var feature = features.Get(featureId);
        return feature.ValueSlot >= 0 && game.TryRead(feature.ValueSlot, out double value) ? value : null;
    }

    public Task RunAsync(string featureId, params double[] arguments)
    {
        var feature = features.Get(featureId);
        return game.ExecuteAsync(feature.CommandId, arguments, "Twitch · " + Definition.Title);
    }

    /// <summary>Applies a value and takes ownership of it for the effect's lifetime.</summary>
    /// <param name="restore">Restore the original value when the effect ends.</param>
    /// <param name="sustain">Re-apply the value if the game resets it while the effect runs (scene or form change).</param>
    public async Task SetAsync(string featureId, double value, bool restore = true, bool sustain = true)
    {
        var feature = features.Get(featureId);
        value = Math.Clamp(value, feature.Minimum, feature.Maximum);
        double? original = Read(featureId);
        await game.ExecuteAsync(feature.CommandId, [value], "Twitch · " + Definition.Title);
        var existing = owned.Find(o => o.Feature.Id == featureId);
        if (existing != null) existing.Applied = value;
        else owned.Add(new OwnedValue(feature, value, original, restore, sustain));
    }

    /// <summary>Re-applies owned values the game has reset. The new game value becomes the value to restore.</summary>
    public async Task SustainAsync()
    {
        foreach (var value in owned.Where(o => o.Sustain))
        {
            if (!game.Supports(value.Feature.CapabilitySlot) || !game.TryRead(value.Feature.ValueSlot, out double live) || Near(live, value.Applied)) continue;
            value.Original = live;
            try { await game.ExecuteAsync(value.Feature.CommandId, [value.Applied], "Twitch · " + Definition.Title); }
            catch (Exception) { /* The game is not ready yet; the next tick retries. */ }
        }
    }

    /// <summary>Restores owned values in reverse order. Returns how many restores the game rejected.</summary>
    public async Task<int> RestoreAsync()
    {
        int failures = 0;
        for (int i = owned.Count - 1; i >= 0; i--)
        {
            var value = owned[i];
            if (!value.Restore) continue;
            double? original = value.Original ?? (value.Feature.Kind == FeatureKind.Toggle ? 0 : null);
            if (original is null) continue;
            if (value.Feature.ValueSlot >= 0 && game.TryRead(value.Feature.ValueSlot, out double live) && !Near(live, value.Applied)) continue;
            try { await game.ExecuteAsync(value.Feature.CommandId, [original.Value], "Twitch · end " + Definition.Title); }
            catch (Exception) { failures++; }
        }
        owned.Clear();
        return failures;
    }

    /// <summary>Waits for the next game snapshots until the condition holds.</summary>
    public async Task<bool> WaitUntilAsync(Func<bool> condition, TimeSpan timeout)
    {
        for (var waited = TimeSpan.Zero; waited <= timeout; waited += TimeSpan.FromMilliseconds(100))
        {
            if (condition()) return true;
            await delay(TimeSpan.FromMilliseconds(100));
        }
        return condition();
    }

    /// <summary>Reads an item's bag stock through the trainer's item inspector.</summary>
    public async Task<int> ReadItemStockAsync(int itemId)
    {
        await RunAsync("inspect-item", itemId);
        if (!await WaitUntilAsync(() => Read("inspect-item") == itemId && Read("selected-item-stock") is not null, TimeSpan.FromSeconds(3)))
            throw new InvalidOperationException("The game did not report the item stock.");
        return (int)Read("selected-item-stock")!.Value;
    }

    /// <summary>Adds (or with a negative delta removes) bag stock and returns the change actually made.</summary>
    public async Task<int> AdjustItemAsync(int itemId, int delta)
    {
        int stock = await ReadItemStockAsync(itemId);
        int target = Math.Clamp(stock + delta, 0, 99);
        if (target != stock) await RunAsync("set-item-stock", itemId, target);
        return target - stock;
    }

    internal static bool Near(double a, double b) => Math.Abs(a - b) <= Math.Max(0.01, Math.Abs(b) * 0.001);
}
