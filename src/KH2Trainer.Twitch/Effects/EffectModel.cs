using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>The trainer's live game connection as seen by the effect engine.</summary>
public interface IGameControl
{
    bool IsConnected { get; }
    bool SceneReady { get; }
    GameplayState Gameplay { get; }
    bool Supports(int capabilitySlot);
    bool TryRead(int valueSlot, out double value);
    /// <summary>Sends a trainer command. Throws when the bridge rejects it.</summary>
    Task ExecuteAsync(int command, IReadOnlyList<double> arguments, string label);
    /// <summary>One coherent actor-generation publication. Older adapters fail closed.</summary>
    MovementSnapshot Movement => MovementSnapshot.Unavailable;
    /// <summary>Effective guard and owner decoded together with its actor identity.</summary>
    DamageGuardSnapshot DamageGuard => DamageGuardSnapshot.Unavailable;
    /// <summary>Exact targeting pair captured together; older adapters fail closed.</summary>
    LockOnPairSnapshot LockOnPair => LockOnPairSnapshot.Unavailable;
    MovementOperationHandle? PendingMovement => null;
    Task<MovementCommandResult> ExecuteMovementAsync(MovementCommand command, CancellationToken cancellation = default) =>
        throw new NotSupportedException("Typed movement ownership is unavailable.");
    Task<MovementCommandResult> ResolveMovementAsync(MovementOperationHandle handle, CancellationToken cancellation = default) =>
        throw new NotSupportedException("Typed movement ownership is unavailable.");
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

[Flags]
public enum EffectPlayerRoles { None = 0, Sora = 1, Roxas = 2, Mickey = 4, FieldPlayers = Sora | Roxas | Mickey }

/// <summary>Thrown by an effect that cannot do anything useful right now; the viewer is refunded.</summary>
public sealed class EffectRejectedException(string reason) : Exception(reason);

/// <summary>The end step must wait for control or a required observation; it has not succeeded.</summary>
public sealed class EffectDeferredException(string reason) : Exception(reason);

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
    public string AmountLabelDe { get; init; } = "";
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
    /// <summary>The viewer pays only when the effect's end succeeded (for example Déjà Vu's pull back); otherwise the points are refunded.</summary>
    public bool ChargeAfterEnd { get; init; }
    /// <summary>Only roles whose native feature path has been verified. Unknown roles always wait.</summary>
    public EffectPlayerRoles AllowedRoles { get; init; } = EffectPlayerRoles.Sora;
    /// <summary>False only for effects with their own independently validated non-field context (Gummi).</summary>
    public bool RequiresPlayerControl { get; init; } = true;
    /// <summary>The sole control blocker this effect may create itself; external blockers still pause it.</summary>
    public GameplayBlockers SelfPauseBlocker { get; init; }
    public string? SelfPauseFeature { get; init; }
    /// <summary>Trainer features the effect uses; all must be available for it to start.</summary>
    public required IReadOnlyList<string> Features { get; init; }
    public Func<EffectContext, Readiness>? Check { get; init; }
    /// <summary>Read-only ongoing usefulness check. Unavailable samples pause time, sustain and extensions;
    /// unlike the start check, this must allow the effect's own applied values. Cleanup does not use it.</summary>
    public Func<EffectContext, Readiness>? ActiveCheck { get; init; }
    public required Func<EffectContext, Task> Start { get; init; }
    /// <summary>Runs when a timed effect ends. Defaults to restoring every value the effect changed.</summary>
    public Func<EffectContext, Task>? End { get; init; }
    /// <summary>Optional cancellation of trainer-owned pending work; never changes the active actor.</summary>
    public Func<EffectContext, Task>? CancelPending { get; init; }
    public Func<EffectContext, EffectProgress>? Monitor { get; init; }

    public bool IsTimed => DurationSeconds > 0;
    public string TitleFor(RewardLanguage language) => language == RewardLanguage.German ? TitleDe : Title;
    public string PromptFor(RewardLanguage language) => language == RewardLanguage.German ? PromptDe : Prompt;
    public string AmountLabelFor(RewardLanguage language) => language == RewardLanguage.German && AmountLabelDe.Length > 0 ? AmountLabelDe : AmountLabel;
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
/// and use a conditional value comparison at the end. Actor-bound movement and damage protection
/// use separate native ownership contracts; ordinary scalar values have no actor-generation proof.
/// </summary>
public sealed class EffectContext
{
    private sealed class OwnedValue(FeatureDefinition feature, double applied, double? original, bool restore, bool sustain, bool written)
    {
        public FeatureDefinition Feature { get; } = feature;
        public double Applied { get; set; } = applied;
        public double? Original { get; set; } = original;
        public bool Restore { get; } = restore;
        public bool Sustain { get; } = sustain;
        public bool Written { get; set; } = written;
    }

    private readonly IGameControl game;
    private readonly FeatureMap features;
    private readonly Func<TimeSpan, Task> delay;
    private readonly List<OwnedValue> owned = [];
    private MovementEffectLease? movementLease;
    private DamageGuardEffectLease? damageGuardLease;
    private LockOnPairEffectLease? lockOnPairLease;

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
    /// <summary>The game is in a playable scene (not loading).</summary>
    public bool SceneReady => game.IsConnected && game.SceneReady;
    public GameplayState Gameplay => game.Gameplay;

    /// <summary>Resource readiness and actual player control are separate requirements.</summary>
    public Readiness ControlReadiness(bool allowOwnPause = true) => ControlReadinessCore(allowOwnPause, null);

    // Only an admission preview: commands still use ControlReadiness with their own ownership.
    internal Readiness ControlAfterRelease(EffectContext releasing) => ControlReadinessCore(false, releasing);

    private GameplayBlockers OwnedPauseBlocker => Definition.SelfPauseFeature is { } id &&
        owned.Any(o => o.Feature.Id == id && o.Written && Near(o.Applied, 1)) && Read(id) == 1
            ? Definition.SelfPauseBlocker : GameplayBlockers.None;

    private Readiness ControlReadinessCore(bool allowOwnPause, EffectContext? releasing)
    {
        if (!game.IsConnected) return Readiness.Wait("Waiting for the trainer to connect to the game");
        if (!Definition.RequiresPlayerControl) return Readiness.Ready;
        if (!game.SceneReady) return Readiness.Wait("Waiting for gameplay (loading, menu or cutscene)");
        var state = game.Gameplay;
        if (!state.Known) return Readiness.Wait("Waiting for fresh player-control information");
        var role = state.Role switch
        {
            PlayerRole.Sora => EffectPlayerRoles.Sora, PlayerRole.Roxas => EffectPlayerRoles.Roxas,
            PlayerRole.Mickey => EffectPlayerRoles.Mickey, _ => EffectPlayerRoles.None
        };
        if (role == EffectPlayerRoles.None || (Definition.AllowedRoles & role) == 0)
            return Readiness.Wait($"Waiting for a supported character ({Definition.AllowedRoles})");
        var blockers = state.Blockers;
        if (allowOwnPause) blockers &= ~OwnedPauseBlocker;
        if (releasing != null) blockers &= ~releasing.OwnedPauseBlocker;
        if (blockers == GameplayBlockers.None) return Readiness.Ready;
        if ((blockers & (GameplayBlockers.TrainerFieldPause | GameplayBlockers.TrainerActorFreeze)) != 0)
            return Readiness.Wait("Waiting until the frozen game continues");
        return Readiness.Wait("Waiting for player control (" + blockers + ")");
    }
    /// <summary>Values this effect still has to put back because an earlier restore was rejected.</summary>
    public bool HasPendingRestores => owned.Any(o => o.Restore) || movementLease?.PendingCleanup == true || damageGuardLease?.PendingCleanup == true || lockOnPairLease?.PendingCleanup == true;
    internal bool HasActorLease => movementLease != null || damageGuardLease != null;
    internal bool HasDurableCleanup => HasActorLease || lockOnPairLease?.PendingCleanup == true;
    internal Readiness LockOnStartReadiness(float scale) => game.LockOnPair.CanApply(scale) ? Readiness.Ready :
        Readiness.Wait("Waiting for both current lock-on settings and their native default");
    // A fresh foreign pair reaches the read-only monitor before any duration is charged.
    // While control is blocked it is unavailable even with the timer-pause preference off.
    internal Readiness LockOnActiveReadiness => lockOnPairLease?.Readiness(game.LockOnPair,
        ControlReadiness().Kind == ReadinessKind.Ready) ?? Readiness.Wait("Waiting for lock-on settings");
    internal EffectProgress LockOnProgress => lockOnPairLease?.Progress(game.LockOnPair) ?? EffectProgress.Running;
    internal async Task StartLockOnPairAsync(float scale)
    {
        RequireControl();
        var original = game.LockOnPair;
        if (!original.CanApply(scale)) throw new EffectDeferredException("Waiting for a restorable lock-on pair");
        lockOnPairLease = new(original, scale);
        await lockOnPairLease.ApplyAsync(this);
    }
    internal ActorMovementIdentity ActorLeaseIdentity => movementLease != null ? game.Movement.Identity : damageGuardLease?.Identity ?? default;
    internal Readiness DamageGuardStartReadiness => DamageGuardEffectLease.StartReadiness(game);
    internal Readiness DamageGuardActiveReadiness => damageGuardLease?.Readiness ?? Readiness.Wait("Waiting for damage protection");
    internal async Task StartDamageGuardAsync()
    {
        RequireControl(); Established = false;
        damageGuardLease = new(game);
        await MaintainActorLeasesAsync();
    }
    internal async Task MaintainActorLeasesAsync()
    {
        await MaintainMovementAsync();
        if (damageGuardLease == null) return;
        await damageGuardLease.MaintainAsync(ControlReadiness().Kind == ReadinessKind.Ready);
        if (damageGuardLease.EverApplied) Established = true;
        Detail = damageGuardLease.Detail;
    }
    internal Readiness MovementStartReadiness(MovementMask mask) => game.Movement.CanUse(mask) ? Readiness.Ready :
        Readiness.Wait("Waiting for movement identity and values within the supported range so they can be restored.");
    internal Readiness MovementActiveReadiness => movementLease?.Readiness ?? Readiness.Wait("Waiting for movement ownership");
    internal async Task StartMovementAsync(MovementMask mask, Func<MovementValues, MovementValues> transform)
    {
        RequireControl(); Established = false;
        movementLease = new(game, mask, transform);
        await MaintainMovementAsync();
    }
    internal async Task MaintainMovementAsync()
    {
        if (movementLease == null) return;
        await movementLease.MaintainAsync();
        if (movementLease.EverApplied) Established = true;
    }

    public double? Read(string featureId)
    {
        var feature = features.Get(featureId);
        return feature.ValueSlot >= 0 && game.TryRead(feature.ValueSlot, out double value) && double.IsFinite(value) ? value : null;
    }

    /// <summary>A starting original must be accepted by the same feature when restored later.</summary>
    internal double? ReadRestorableValue(string featureId) =>
        Read(featureId) is double value && features.Get(featureId).IsValidValue(value) ? value : null;

    public Task RunAsync(string featureId, params double[] arguments)
    {
        var feature = features.Get(featureId);
        RequireControl();
        return game.ExecuteAsync(feature.CommandId, arguments, "Twitch · " + Definition.Title);
    }

    private void RequireControl()
    {
        var readiness = ControlReadiness();
        if (readiness.Kind != ReadinessKind.Ready) throw new EffectDeferredException(readiness.Reason);
    }

    /// <summary>Slot 126 only cancels the bridge's queued Drive steps. An existing native transition finishes normally.</summary>
    internal async Task CancelDriveQueueAsync()
    {
        if (Established || State.ContainsKey("driveQueueCancelled")) return;
        if (!game.IsConnected || !Supports("drive.cancel")) throw new EffectDeferredException("Waiting to cancel pending Drive steps");
        await game.ExecuteAsync(features.Get("drive.cancel").CommandId, [], "Twitch · cancel pending Drive steps");
        State["driveQueueCancelled"] = 1;
    }

    /// <summary>Applies a value and takes ownership of it for the effect's lifetime.</summary>
    /// <param name="restore">Restore the original value when the effect ends.</param>
    /// <param name="sustain">Re-apply the value if the game resets it while the effect runs (scene or form change).</param>
    public async Task SetAsync(string featureId, double value, bool restore = true, bool sustain = true)
    {
        var feature = features.Get(featureId);
        RequireControl();
        value = Math.Clamp(value, feature.Minimum, feature.Maximum);
        double? original = Read(featureId);
        await game.ExecuteAsync(feature.CommandId, [value], "Twitch · " + Definition.Title);
        var existing = owned.Find(o => o.Feature.Id == featureId);
        if (existing != null) { existing.Applied = value; existing.Written = true; }
        else owned.Add(new OwnedValue(feature, value, original, restore, sustain, written: true));
    }

    /// <summary>Takes ownership of a value without sending it now; <see cref="SustainAsync"/> applies it when the game allows.</summary>
    public void Own(string featureId, double value, bool restore = true, bool sustain = true)
    {
        var feature = features.Get(featureId);
        if (owned.Any(o => o.Feature.Id == featureId)) return;
        owned.Add(new OwnedValue(feature, Math.Clamp(value, feature.Minimum, feature.Maximum), Read(featureId), restore, sustain, written: false));
    }

    /// <summary>Re-applies owned values the game has reset. The new game value becomes the value to restore.</summary>
    public async Task SustainAsync()
    {
        foreach (var value in owned.Where(o => o.Sustain))
        {
            if (ControlReadiness().Kind != ReadinessKind.Ready) return;
            if (!game.Supports(value.Feature.CapabilitySlot) || !game.TryRead(value.Feature.ValueSlot, out double live) || !double.IsFinite(live) || Near(live, value.Applied)) continue;
            // A script can change a later value while an earlier command is awaited.
            // Never overwrite an original that this feature could not restore.
            if (value.Restore && !value.Feature.IsValidValue(live)) continue;
            try
            {
                await game.ExecuteAsync(value.Feature.CommandId, [value.Applied], "Twitch · " + Definition.Title);
                value.Original = live; value.Written = true;
            }
            catch (Exception) { /* The game is not ready yet; the next tick retries. */ }
        }
    }

    /// <summary>
    /// Restores owned values in reverse order. A value the game rejected stays owned, so a later
    /// call (the engine retries while the game is ready) can put it back. Returns how many restores were rejected.
    /// </summary>
    public async Task<int> RestoreAsync()
    {
        int failures = 0;
        if (lockOnPairLease != null)
        {
            try { await lockOnPairLease.RestoreAsync(this); }
            catch (Exception error) { Detail = "Lock-on settings restore is still pending: " + error.Message; failures++; }
        }
        if (damageGuardLease != null)
        {
            await damageGuardLease.MaintainAsync(mayEnsure: false, release: true);
            Detail = damageGuardLease.Detail;
            if (damageGuardLease.PendingCleanup) failures++;
        }
        if (movementLease != null)
        {
            await movementLease.MaintainAsync(release: true);
            if (movementLease.PendingCleanup) failures++;
        }
        for (int i = owned.Count - 1; i >= 0; i--)
        {
            var value = owned[i];
            if (!value.Restore) { owned.RemoveAt(i); continue; }
            if (!value.Written) { owned.RemoveAt(i); continue; }
            if (ControlReadiness().Kind != ReadinessKind.Ready) { failures++; break; }
            double? original = value.Original ?? (value.Feature.Kind == FeatureKind.Toggle ? 0 : null);
            double? live = Read(value.Feature.Id);
            if (value.Feature.ValueSlot >= 0 && live is null) { failures++; break; }
            // Not owned any more: the game, a script or the streamer changed it since.
            if (original is null || live is double observed && !Near(observed, value.Applied))
            {
                owned.RemoveAt(i);
                continue;
            }
            try
            {
                await game.ExecuteAsync(value.Feature.CommandId, [original.Value], "Twitch · end " + Definition.Title);
                owned.RemoveAt(i);
            }
            // Preserve reverse order when restores depend on one another (for example a FOV
            // setter enables its switch). A later retry resumes at this value first.
            catch (Exception) { failures++; break; }
        }
        return failures;
    }

    /// <summary>Gives up on values that could not be restored (logged by the engine).</summary>
    internal IReadOnlyList<string> AbandonRestores()
    {
        var names = owned.Where(o => o.Restore).Select(o => o.Feature.Name).ToArray();
        owned.Clear();
        return names;
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
