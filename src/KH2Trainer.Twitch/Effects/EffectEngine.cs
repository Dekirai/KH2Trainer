using System.Collections.Concurrent;
using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>Per-reward values the streamer configured.</summary>
public sealed record EffectOptions(string Title, int DurationSeconds, int Amount, SameEffectBehavior SameEffect, ConflictBehavior Conflict);

/// <summary>Engine-wide limits.</summary>
public sealed record EngineSettings(TimeSpan MaxWait, int MaxDurationSeconds, bool PauseTimersWhileNotReady);

public sealed record ActiveEffectInfo(string Key, string Title, string Viewers, string? Detail, double RemainingSeconds, double DurationSeconds,
    bool Established, bool Paused = false, string? PauseReason = null);
public sealed record PendingEffectInfo(string RedemptionId, string Key, string Title, string Viewer, string Status, double WaitedSeconds);
public enum EffectEventKind { Redeemed, Started, Done, Extended, Ended, Refunded, Failed }

/// <summary>Something that happened to a redemption. <see cref="Text"/> is the English log line.</summary>
public sealed record EffectEvent(DateTimeOffset Time, EffectEventKind Kind, string Key, string Viewer, string Title, string? Detail, string Text);

/// <summary>
/// Runs redeemed effects against the game. Call <see cref="TickAsync"/> regularly from one thread.
/// Rules:
/// <list type="bullet">
/// <item>Effects of one group never overlap. A conflicting redemption waits, replaces the running effect or is refunded (per reward).</item>
/// <item>Redeeming a running effect again extends it, is refunded, or waits for it (per reward).</item>
/// <item>A redemption is fulfilled on Twitch only once the effect really happened; anything that never ran is refunded.</item>
/// <item>Timers can pause while the game is disconnected or loading, and values the game resets are re-applied.</item>
/// </list>
/// </summary>
public sealed class EffectEngine
{
    private sealed class Pending(Redemption redemption, EffectDefinition definition, DateTimeOffset received)
    {
        public Redemption Redemption { get; } = redemption;
        public EffectDefinition Definition { get; } = definition;
        public DateTimeOffset Received { get; } = received;
        public string Status { get; set; } = "Waiting";
        /// <summary>Set after the game refused the effect for a moment (menu, transition); the next try waits until then.</summary>
        public DateTimeOffset? RetryAfter { get; set; }
        public DateTimeOffset? FirstFailure { get; set; }
    }

    private sealed class Active(EffectContext context, DateTimeOffset started, int durationSeconds)
    {
        public EffectContext Context { get; } = context;
        public EffectDefinition Definition => Context.Definition;
        public DateTimeOffset Started { get; } = started;
        public int DurationSeconds { get; set; } = durationSeconds;
        public double ElapsedSeconds { get; set; }
        public DateTimeOffset LastSustain { get; set; } = started;
        public List<Redemption> Redemptions { get; } = [context.Redemption];
        public bool Fulfilled { get; set; }
        public bool Settled { get; set; }
        public bool WasControllable { get; set; } = context.ControlReadiness().Kind == ReadinessKind.Ready;
        public bool WasUsable { get; set; } = ActiveReadiness(context).Kind == ReadinessKind.Ready;
        public ActorMovementIdentity ActorLeaseIdentity { get; set; } = context.ActorLeaseIdentity;
    }

    /// <summary>An ended effect whose values the game refused to take back; retried while the game is ready.</summary>
    private sealed class Restoring(EffectContext context, DateTimeOffset now)
    {
        public EffectContext Context { get; } = context;
        public DateTimeOffset ObservedAt { get; set; } = now;
        public bool WasControllable { get; set; }
        public double AvailableSeconds { get; set; }
        public DateTimeOffset LastTry { get; set; }
    }

    private sealed class DeferredEnd(Active effect, EndReason reason, string? why, DateTimeOffset now)
    {
        public Active Effect { get; } = effect;
        public EndReason Reason { get; } = reason;
        public string? Why { get; } = why;
        public DateTimeOffset ObservedAt { get; set; } = now;
        public DateTimeOffset LastTry { get; set; } = now;
        public bool WasControllable { get; set; }
        public double AvailableSeconds { get; set; }
    }

    // The native publication is fresh for one second. Longer gaps contain unobserved gameplay,
    // so endpoint samples cannot prove that this entire interval was playable.
    private const double MaximumObservedIntervalSeconds = GameplayState.MaximumAgeMilliseconds / 1000.0;

    private static readonly TimeSpan SustainInterval = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan RetryInterval = TimeSpan.FromSeconds(3), RetryWindow = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan RestoreInterval = TimeSpan.FromSeconds(1), RestoreWindow = TimeSpan.FromMinutes(3);
    private readonly IGameControl game;
    private readonly FeatureMap features;
    private readonly Dictionary<string, EffectDefinition> catalog;
    private readonly Func<string, EffectOptions> options;
    private readonly Func<EngineSettings> settings;
    private readonly IRedemptionSink sink;
    private readonly Action<string> log;
    private readonly Func<TimeSpan, Task> delay;
    private readonly Random random;
    private readonly int fieldPauseSlot;
    private readonly ConcurrentQueue<Redemption> incoming = new();
    private readonly List<Pending> pending = [];
    private readonly List<Active> active = [];
    private readonly List<Restoring> restoring = [];
    private readonly List<DeferredEnd> deferredEnds = [];
    private readonly LinkedList<EffectEvent> events = new();
    private DateTimeOffset? lastTick;
    /// <summary>Serializes ticks and the streamer's actions; a game command can be awaited in either.</summary>
    private readonly SemaphoreSlim gate = new(1, 1);

    public EffectEngine(IGameControl game, FeatureMap features, IEnumerable<EffectDefinition> catalog,
        Func<string, EffectOptions> options, Func<EngineSettings> settings, IRedemptionSink sink, Action<string> log,
        Func<TimeSpan, Task>? delay = null, Random? random = null)
    {
        this.game = game; this.features = features; this.options = options; this.settings = settings; this.sink = sink; this.log = log;
        this.catalog = catalog.ToDictionary(e => e.Key, StringComparer.Ordinal);
        this.delay = delay ?? (span => Task.Delay(span));
        this.random = random ?? new Random();
        fieldPauseSlot = features.Contains("practice.field_pause") ? features.Get("practice.field_pause").ValueSlot : -1;
    }

    /// <summary>Raised after every tick that changed the queue, the running effects or the event list.</summary>
    public event Action? Changed;

    public bool IsGameReady => game.IsConnected && game.SceneReady && game.Gameplay.IsControllable;

    /// <summary>The trainer's field freeze (Freeze Frame) holds the game; most commands wait until it ends.</summary>
    private bool FieldPaused => fieldPauseSlot >= 0 && game.TryRead(fieldPauseSlot, out double value) && value == 1;

    /// <summary>Accepts a redemption from any thread. It is handled on the next tick.</summary>
    public void Submit(Redemption redemption) => incoming.Enqueue(redemption);

    public IReadOnlyList<ActiveEffectInfo> ActiveEffects => active.Select(a =>
    {
        var control = a.Context.ControlReadiness();
        var usable = ActiveReadiness(a.Context);
        var pause = settings().PauseTimersWhileNotReady && control.Kind != ReadinessKind.Ready ? control : usable;
        bool paused = a.Context.Established && pause.Kind != ReadinessKind.Ready;
        return new ActiveEffectInfo(a.Definition.Key, Title(a.Definition.Key), Viewers(a), a.Context.Detail,
            a.Definition.IsTimed ? Math.Max(0, a.DurationSeconds - a.ElapsedSeconds) : 0, a.DurationSeconds,
            a.Context.Established, paused, paused ? pause.Reason : null);
    }).ToArray();

    /// <summary>Ends/owned values waiting for control to return. They continue blocking their effect group.</summary>
    public int PendingCleanupCount => deferredEnds.Count + restoring.Count;

    public IReadOnlyList<PendingEffectInfo> PendingEffects => pending.Select(p => new PendingEffectInfo(
        p.Redemption.Id, p.Definition.Key, Title(p.Definition.Key), p.Redemption.UserName, p.Status,
        lastTick is { } now ? (now - p.Received).TotalSeconds : 0)).ToArray();

    public IReadOnlyList<EffectEvent> RecentEvents => events.ToArray();

    public async Task TickAsync(DateTimeOffset now)
    {
        if (!gate.Wait(0)) return; // A slow game command is still running; the next tick continues.
        bool changed = false;
        try
        {
            changed |= AcceptIncoming(now);
            // A backwards wall-clock adjustment must not make a later tick charge the same interval twice.
            if (lastTick is { } previous && now < previous) now = previous;
            double step = lastTick is { } last ? Math.Max(0, (now - last).TotalSeconds) : 0;
            lastTick = now;
            changed |= await RetryDeferredEndsAsync(now);
            changed |= await RetryRestoresAsync(now);
            changed |= await UpdateActiveAsync(now, step);
            changed |= await StartPendingAsync(now);
        }
        finally { gate.Release(); }
        if (changed || active.Count > 0 || pending.Count > 0) Changed?.Invoke();
    }

    private async Task<bool> RetryDeferredEndsAsync(DateTimeOffset now)
    {
        bool changed = false;
        foreach (var item in deferredEnds.ToArray())
        {
            bool ready = item.Effect.Context.ControlReadiness().Kind == ReadinessKind.Ready;
            double step = Math.Max(0, (now - item.ObservedAt).TotalSeconds);
            if (ready && item.WasControllable && step <= MaximumObservedIntervalSeconds) item.AvailableSeconds += step;
            item.ObservedAt = now; item.WasControllable = ready;
            if (item.AvailableSeconds > RestoreWindow.TotalSeconds && !item.Effect.Context.HasDurableCleanup)
            {
                deferredEnds.Remove(item);
                item.Effect.Context.AbandonRestores();
                if (!item.Effect.Settled)
                {
                    foreach (var redemption in item.Effect.Redemptions) Refund(redemption, "The end step could not be completed");
                    item.Effect.Settled = true;
                }
                log($"Twitch: could not finish ending {Title(item.Effect.Definition.Key)}. Check its settings in the trainer.");
                changed = true;
                continue;
            }
            // Pending Drive cancellation only removes trainer work; no actor action is permitted here.
            bool mayCancel = !item.Effect.Context.Established && item.Effect.Definition.CancelPending != null && game.IsConnected;
            if ((!ready && !mayCancel && !item.Effect.Context.HasActorLease) || now - item.LastTry < RestoreInterval) continue;
            item.LastTry = now;
            await EndAsync(item.Effect, item.Reason, now, item.Why);
            changed = true;
        }
        return changed;
    }

    private async Task<bool> RetryRestoresAsync(DateTimeOffset now)
    {
        bool changed = false;
        foreach (var item in restoring.ToArray())
        {
            bool ready = item.Context.ControlReadiness().Kind == ReadinessKind.Ready;
            double step = Math.Max(0, (now - item.ObservedAt).TotalSeconds);
            if (ready && item.WasControllable && step <= MaximumObservedIntervalSeconds) item.AvailableSeconds += step;
            item.ObservedAt = now; item.WasControllable = ready;
            if (item.AvailableSeconds > RestoreWindow.TotalSeconds && !item.Context.HasDurableCleanup)
            {
                restoring.Remove(item);
                log($"Twitch: could not undo {Title(item.Context.Definition.Key)} ({string.Join(", ", item.Context.AbandonRestores())}). Set it back in the trainer if needed.");
                changed = true;
                continue;
            }
            // Freeze Frame's own release must be retried while the field is still paused.
            if ((!ready && !item.Context.HasActorLease) || now - item.LastTry < RestoreInterval) continue;
            item.LastTry = now;
            await item.Context.RestoreAsync();
            if (!item.Context.HasPendingRestores) { restoring.Remove(item); changed = true; }
        }
        return changed;
    }

    private async Task<bool> UpdateActiveAsync(DateTimeOffset now, double step)
    {
        bool changed = false;
        var engine = settings();
        foreach (var effect in active.ToArray())
        {
            effect.Context.SinceStart = now - effect.Started;
            var startLimit = effect.Definition.MaxWaitSeconds > 0 ? TimeSpan.FromSeconds(effect.Definition.MaxWaitSeconds) : engine.MaxWait;
            if (effect.Context.HasActorLease && !effect.Context.Established && effect.Context.SinceStart > startLimit)
            {
                await EndAsync(effect, EndReason.Stopped, now, "Native effect ownership could not be established before the waiting limit");
                changed = true; continue;
            }
            bool beforeMaintenanceUsable = ActiveReadiness(effect.Context).Kind == ReadinessKind.Ready;
            var beforeIdentity = effect.Context.ActorLeaseIdentity;
            bool establishedBeforeMaintenance = effect.Context.Established;
            await effect.Context.MaintainActorLeasesAsync();
            var afterIdentity = effect.Context.ActorLeaseIdentity;
            bool sameActorLeaseIdentity = !effect.Context.HasActorLease ||
                beforeIdentity.Known && beforeIdentity == afterIdentity && effect.ActorLeaseIdentity == beforeIdentity;
            effect.ActorLeaseIdentity = afterIdentity;
            bool ready = effect.Context.ControlReadiness().Kind == ReadinessKind.Ready;
            bool usable = ActiveReadiness(effect.Context).Kind == ReadinessKind.Ready;
            bool wasEstablished = establishedBeforeMaintenance, wasControllable = effect.WasControllable, wasUsable = effect.WasUsable && beforeMaintenanceUsable;
            effect.WasControllable = ready;
            effect.WasUsable = usable;
            // Starting monitors may observe native acknowledgements during loading. Established
            // effects do not interpret a paused scene/temporary role as their gameplay ending.
            if (effect.Definition.Monitor is { } monitor && game.IsConnected && (!wasEstablished || ready && usable))
            {
                var progress = monitor(effect.Context);
                if (progress.Status == EffectStatus.Failed && !effect.Context.Established)
                {
                    await EndAsync(effect, EndReason.EndedByGame, now, progress.Reason);
                    Record(now, EffectEventKind.Failed, effect.Definition.Key, Viewers(effect), progress.Reason, $"{Title(effect.Definition.Key)} failed: {progress.Reason} Points refunded.");
                    changed = true;
                    continue;
                }
                if (progress.Status != EffectStatus.Running)
                {
                    await EndAsync(effect, EndReason.EndedByGame, now, progress.Reason);
                    changed = true;
                    continue;
                }
            }
            if (effect.Context.Established && !effect.Fulfilled && !effect.Definition.ChargeAfterEnd) { FulfillAll(effect); changed = true; }
            // The interval belongs to the previous observation. Neither returning control nor
            // a just-confirmed Drive transition may retroactively charge the preceding pause.
            if (effect.Context.Established && wasEstablished &&
                usable && wasUsable && sameActorLeaseIdentity && (effect.Definition.ActiveCheck == null || step <= MaximumObservedIntervalSeconds) &&
                (!engine.PauseTimersWhileNotReady || ready && wasControllable && step <= MaximumObservedIntervalSeconds)) effect.ElapsedSeconds += step;
            if (effect.Definition.IsTimed && effect.Context.Established && effect.ElapsedSeconds >= effect.DurationSeconds)
            {
                await EndAsync(effect, EndReason.Expired, now, null);
                changed = true;
                continue;
            }
            if (ready && usable && (!wasControllable || !wasUsable || now - effect.LastSustain >= SustainInterval))
            {
                effect.LastSustain = now;
                await effect.Context.SustainAsync();
            }
        }
        return changed;
    }

    private async Task<bool> StartPendingAsync(DateTimeOffset now)
    {
        bool changed = false;
        var engine = settings();
        var blockedGroups = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in pending.ToArray())
        {
            var definition = item.Definition;
            var config = options(definition.Key);
            var maxWait = definition.MaxWaitSeconds > 0 ? TimeSpan.FromSeconds(definition.MaxWaitSeconds) : engine.MaxWait;
            if (now - item.Received > maxWait)
            {
                Drop(item, $"Waited longer than {maxWait.TotalMinutes:0.#} minutes ({item.Status})", now);
                changed = true;
                continue;
            }
            if (item.RetryAfter is { } retry && now < retry)
            {
                if (definition.Group != null) blockedGroups.Add(definition.Group);
                continue;
            }

            // A duplicate Kick Out must be rejected before a preceding effect's deferred
            // cleanup blocks the group; otherwise it could attack the next queued form.
            var state = game.Gameplay;
            if (definition.Interrupts && game.IsConnected && game.SceneReady && state.Known &&
                state.Role == PlayerRole.Sora && state.Blockers == GameplayBlockers.Transition &&
                !active.Any(a => a.Definition.Group == definition.Group && !a.Context.Established))
            {
                var observation = new EffectContext(definition, item.Redemption, 0, config.Amount, game, features, random, delay);
                if (definition.Check?.Invoke(observation) is { Kind: ReadinessKind.Reject } rejection)
                { Drop(item, rejection.Reason, now); changed = true; continue; }
            }

            var same = active.FirstOrDefault(a => a.Definition.Key == definition.Key);
            if (same != null && definition.IsTimed && config.SameEffect == SameEffectBehavior.Refund)
            {
                Drop(item, $"{Title(definition.Key)} is already running", now);
                changed = true;
                continue;
            }

            // FIFO within a group: a later redemption never overtakes an earlier one of the same group.
            // An interrupting effect (Kick Out of Drive Form) acts on the running effect instead of waiting in line.
            if (definition.Group is { } group && !definition.Interrupts && blockedGroups.Contains(group)) { changed |= SetStatus(item, "Waiting for an earlier redemption"); continue; }

            if (same != null && definition.IsTimed)
            {
                if (config.SameEffect == SameEffectBehavior.Extend)
                {
                    var control = same.Context.ControlReadiness();
                    if (control.Kind != ReadinessKind.Ready) { Block(item, control.Reason, blockedGroups); changed = true; continue; }
                    var usable = ActiveReadiness(same.Context);
                    if (usable.Kind != ReadinessKind.Ready) { Block(item, usable.Reason, blockedGroups); changed = true; continue; }
                    // The cap limits the time left, so an extension always adds real time or is refunded.
                    int add = Math.Max(1, config.DurationSeconds);
                    int room = (int)Math.Floor(engine.MaxDurationSeconds - (same.DurationSeconds - same.ElapsedSeconds));
                    if (room < 1) { Drop(item, $"{Title(definition.Key)} already runs for the longest allowed time", now); changed = true; continue; }
                    int added = Math.Min(add, room);
                    same.DurationSeconds += added;
                    same.Redemptions.Add(item.Redemption);
                    pending.Remove(item);
                    if (same.Fulfilled) sink.Fulfill(item.Redemption);
                    Record(now, EffectEventKind.Extended, definition.Key, item.Redemption.UserName, $"+{added} s",
                        $"{item.Redemption.UserName} extended {Title(definition.Key)} by {added} s.");
                    changed = true;
                    continue;
                }
                Block(item, $"Waiting for the running {Title(definition.Key)}", blockedGroups);
                changed = true;
                continue;
            }

            var conflict = definition.Group is null ? null : active.FirstOrDefault(a => a.Definition.Group == definition.Group && a.Definition.Key != definition.Key);
            if (conflict != null && !definition.Interrupts)
            {
                if (config.Conflict == ConflictBehavior.Queue)
                {
                    Block(item, $"Waiting for {Title(conflict.Definition.Key)} to end", blockedGroups);
                    changed = true;
                    continue;
                }
                if (config.Conflict == ConflictBehavior.Refund) { Drop(item, $"{Title(conflict.Definition.Key)} is running", now); changed = true; continue; }
            }
            // Replace or interrupt only an effect that has taken hold; one that is still starting (a form loading) finishes first.
            if (conflict != null && !conflict.Context.Established)
            {
                Block(item, $"Waiting for {Title(conflict.Definition.Key)} to finish starting", blockedGroups);
                changed = true;
                continue;
            }
            // An earlier effect of this group still has values to put back; starting now would capture them as originals.
            if (definition.Group != null && (restoring.Any(r => r.Context.Definition.Group == definition.Group) ||
                deferredEnds.Any(r => r.Effect.Definition.Group == definition.Group)))
            {
                Block(item, "Waiting until the previous effect is undone", blockedGroups);
                changed = true;
                continue;
            }

            // Check before touching a running effect, so nothing is replaced while the game is loading.
            var context = new EffectContext(definition, item.Redemption, definition.IsTimed ? Math.Max(1, config.DurationSeconds) : 0,
                config.Amount, game, features, random, delay);
            var readiness = Check(context, includeEffectCheck: !(conflict != null && definition.Interrupts),
                releasing: conflict != null && !definition.Interrupts && config.Conflict == ConflictBehavior.Replace ? conflict.Context : null);
            if (readiness.Kind == ReadinessKind.Wait)
            {
                changed |= SetStatus(item, readiness.Reason);
                if (definition.Group != null && !definition.Interrupts) blockedGroups.Add(definition.Group);
                continue;
            }
            if (readiness.Kind == ReadinessKind.Reject) { Drop(item, readiness.Reason, now); changed = true; continue; }

            int index = pending.IndexOf(item);
            pending.Remove(item);
            changed = true;
            Active? replaced = null;
            if (conflict != null && !definition.Interrupts)
            {
                await EndAsync(conflict, EndReason.Replaced, now, $"replaced by {Title(definition.Key)}");
                replaced = conflict;
                if (deferredEnds.Any(e => e.Effect == conflict) || restoring.Any(r => r.Context == conflict.Context))
                {
                    item.Status = "Waiting until the previous effect is undone";
                    pending.Insert(Math.Min(index, pending.Count), item);
                    if (definition.Group != null) blockedGroups.Add(definition.Group);
                    continue;
                }
            }
            try
            {
                // An interrupting effect (Kick Out) acts first; the running effect ends only once that was accepted.
                await definition.Start(context);
            }
            catch (Exception error)
            {
                await context.RestoreAsync();
                QueueRestore(context, now);
                if (replaced != null) await EndAsync(replaced, EndReason.Stopped, now, "the replacement did not start");
                item.FirstFailure ??= now;
                // A refusal can be momentary (menu, transformation, busy queue): try again for a while before refunding.
                if (error is EffectRejectedException || replaced != null || now - item.FirstFailure.Value >= RetryWindow)
                {
                    Refund(item.Redemption, error.Message);
                    Record(now, EffectEventKind.Failed, definition.Key, item.Redemption.UserName, error.Message,
                        $"{Title(definition.Key)} for {item.Redemption.UserName} did not work: {error.Message} Points refunded.");
                    continue;
                }
                item.RetryAfter = now + RetryInterval;
                item.Status = $"The game refused it for now ({error.Message}). Trying again.";
                pending.Insert(Math.Min(index, pending.Count), item);
                if (definition.Group != null) blockedGroups.Add(definition.Group);
                continue;
            }
            if (conflict != null && definition.Interrupts)
            {
                await EndAsync(conflict, EndReason.Interrupted, now, $"{item.Redemption.UserName} interrupted it");
                sink.Fulfill(item.Redemption);
                Record(now, EffectEventKind.Done, definition.Key, item.Redemption.UserName, null, $"{item.Redemption.UserName}: {Title(definition.Key)} done.");
                continue;
            }
            if (definition.IsTimed || !context.Established)
            {
                var effect = new Active(context, now, context.DurationSeconds);
                active.Add(effect);
                if (context.Established && !definition.ChargeAfterEnd) FulfillAll(effect);
                Record(now, EffectEventKind.Started, definition.Key, item.Redemption.UserName, context.Detail, $"{item.Redemption.UserName} started {Title(definition.Key)}{Suffix(context)}.");
            }
            else
            {
                sink.Fulfill(item.Redemption);
                Record(now, EffectEventKind.Done, definition.Key, item.Redemption.UserName, context.Detail, $"{item.Redemption.UserName}: {Title(definition.Key)}{Suffix(context)}.");
            }
        }
        return changed;
    }

    private Readiness Check(EffectContext context, bool includeEffectCheck, EffectContext? releasing = null)
    {
        var definition = context.Definition;
        var control = releasing == null ? context.ControlReadiness(allowOwnPause: false) : context.ControlAfterRelease(releasing);
        if (control.Kind != ReadinessKind.Ready)
        {
            // An already-running revert can reject a duplicate request without sending any
            // command. It must not wait and accidentally kick the next viewer's form instead.
            var state = game.Gameplay;
            if (includeEffectCheck && definition.Interrupts && game.IsConnected && game.SceneReady &&
                state.Known && state.Role == PlayerRole.Sora && state.Blockers == GameplayBlockers.Transition &&
                definition.Check?.Invoke(context) is { Kind: ReadinessKind.Reject } rejection) return rejection;
            return control;
        }
        if (definition.Group != "freeze" && FieldPaused) return Readiness.Wait("Waiting until the frozen game continues");
        foreach (string id in definition.Features)
        {
            var feature = features.Get(id);
            if (feature.RequiresScene && !game.SceneReady) return Readiness.Wait("Waiting for gameplay (loading, menu or cutscene)");
            if (!game.Supports(feature.CapabilitySlot)) return Readiness.Wait("Waiting until the game allows it");
        }
        return includeEffectCheck ? definition.Check?.Invoke(context) ?? Readiness.Ready : Readiness.Ready;
    }

    /// <summary>Ends a running effect early (for example from the streamer's Live panel).</summary>
    public async Task EndEffectAsync(string key, DateTimeOffset now)
    {
        await gate.WaitAsync();
        try
        {
            foreach (var effect in active.Where(a => a.Definition.Key == key).ToArray())
                await EndAsync(effect, EndReason.Stopped, now, "stopped by the streamer");
        }
        finally { gate.Release(); }
        Changed?.Invoke();
    }

    /// <summary>Refunds one waiting redemption. Returns false when it is not waiting (for example its effect already runs).</summary>
    public async Task<bool> CancelAsync(string redemptionId, DateTimeOffset now)
    {
        bool found;
        await gate.WaitAsync();
        try
        {
            AcceptIncoming(now);
            var item = pending.FirstOrDefault(p => p.Redemption.Id == redemptionId);
            found = item != null;
            if (item != null) Drop(item, "Removed by the streamer", now);
        }
        finally { gate.Release(); }
        Changed?.Invoke();
        return found;
    }

    private bool AcceptIncoming(DateTimeOffset now)
    {
        bool any = false;
        while (incoming.TryDequeue(out var redemption))
        {
            any = true;
            if (!catalog.TryGetValue(redemption.RewardKey, out var definition)) { Refund(redemption, "This reward is not available."); continue; }
            pending.Add(new Pending(redemption, definition, now));
            Record(now, EffectEventKind.Redeemed, definition.Key, redemption.UserName, null, $"{redemption.UserName} redeemed {Title(definition.Key)}.");
        }
        return any;
    }

    /// <summary>Ends every running effect and refunds everything still waiting.</summary>
    public async Task StopAllAsync(string reason, DateTimeOffset now)
    {
        await gate.WaitAsync();
        try
        {
            while (incoming.TryDequeue(out var redemption)) Refund(redemption, reason);
            foreach (var item in pending.ToArray()) Drop(item, reason, now);
            // Effects that never took hold are refunded by EndAsync; the others were already paid for.
            foreach (var effect in active.ToArray()) await EndAsync(effect, EndReason.Stopped, now, reason);
            foreach (var item in restoring.ToArray())
                if (item.Context.ControlReadiness().Kind == ReadinessKind.Ready || item.Context.HasActorLease)
                { await item.Context.RestoreAsync(); if (!item.Context.HasPendingRestores) restoring.Remove(item); }
        }
        finally { gate.Release(); }
        Changed?.Invoke();
    }

    /// <summary>Ends an effect. Returns false when its end step failed (for example the game refused a revert).</summary>
    private async Task<bool> EndAsync(Active effect, EndReason reason, DateTimeOffset now, string? why)
    {
        if (!effect.Context.Established && effect.Definition.CancelPending is { } cancel)
        {
            try { await cancel(effect.Context); }
            catch (Exception error)
            {
                DeferEnd(effect, reason, now, why);
                log($"Twitch: pending work cancellation waits: {error.Message}");
                return false;
            }
        }
        if (effect.Context.ControlReadiness().Kind != ReadinessKind.Ready && !effect.Context.HasActorLease)
        {
            DeferEnd(effect, reason, now, why);
            log($"Twitch: ending {Title(effect.Definition.Key)} waits for player control; no game action was sent.");
            return false;
        }
        bool? ended = await StopAsync(effect, reason, now);
        if (ended is null)
        {
            DeferEnd(effect, reason, now, why);
            return false;
        }
        deferredEnds.RemoveAll(e => e.Effect == effect);
        bool ok = ended.Value;
        if (!effect.Settled)
        {
            if (effect.Context.Established && (ok || !effect.Definition.ChargeAfterEnd)) FulfillAll(effect);
            else
            {
                string refund = why ?? "it ended before it took effect";
                foreach (var redemption in effect.Redemptions) Refund(redemption, refund);
                effect.Settled = true;
                Record(now, EffectEventKind.Refunded, effect.Definition.Key, Viewers(effect), why,
                    $"{Title(effect.Definition.Key)} ended without effect{(why is null ? "" : ": " + why)}. Points refunded.");
                return ok;
            }
        }
        string? detail = why ?? effect.Context.Detail;
        Record(now, EffectEventKind.Ended, effect.Definition.Key, Viewers(effect), detail, $"{Title(effect.Definition.Key)} ended{(detail is null ? "" : ": " + detail)}.");
        return ok;
    }

    private void DeferEnd(Active effect, EndReason reason, DateTimeOffset now, string? why)
    {
        active.Remove(effect);
        if (deferredEnds.All(e => e.Effect != effect)) deferredEnds.Add(new DeferredEnd(effect, reason, why, now));
        if (!effect.Context.Established && !effect.Settled)
        {
            foreach (var redemption in effect.Redemptions) Refund(redemption, why ?? "it ended before it took effect");
            effect.Settled = true;
        }
    }

    // Resource usability is separate from control and cleanup: a vanished MP gauge
    // prevents useful play time, but must never prevent releasing the owned MP toggle.
    private static Readiness ActiveReadiness(EffectContext context) => context.Definition.ActiveCheck?.Invoke(context) ?? Readiness.Ready;

    private async Task<bool?> StopAsync(Active effect, EndReason reason, DateTimeOffset now)
    {
        active.Remove(effect);
        effect.Context.EndReason = reason;
        bool ok = true;
        try { await (effect.Definition.End ?? (ctx => ctx.RestoreAsync()))(effect.Context); }
        catch (EffectDeferredException error)
        {
            log($"Twitch: ending {Title(effect.Definition.Key)} waits: {error.Message}");
            return null;
        }
        catch (Exception error)
        {
            if (effect.Context.ControlReadiness().Kind != ReadinessKind.Ready)
            {
                log($"Twitch: ending {Title(effect.Definition.Key)} waits after a refused command: {error.Message}");
                return null;
            }
            ok = false;
            log($"Twitch: could not fully end {Title(effect.Definition.Key)}: {error.Message}");
        }
        QueueRestore(effect.Context, now);
        return ok;
    }

    private void QueueRestore(EffectContext context, DateTimeOffset now)
    {
        if (context.HasPendingRestores && restoring.All(r => r.Context != context))
            restoring.Add(new Restoring(context, now) { LastTry = now });
    }

    private void FulfillAll(Active effect)
    {
        effect.Fulfilled = true;
        effect.Settled = true;
        foreach (var redemption in effect.Redemptions) sink.Fulfill(redemption);
    }

    private void Block(Pending item, string status, HashSet<string> blockedGroups)
    {
        SetStatus(item, status);
        if (item.Definition.Group != null) blockedGroups.Add(item.Definition.Group);
    }

    private static bool SetStatus(Pending item, string status)
    {
        if (item.Status == status) return false;
        item.Status = status;
        return true;
    }

    private void Drop(Pending item, string reason, DateTimeOffset now)
    {
        pending.Remove(item);
        Refund(item.Redemption, reason);
        Record(now, EffectEventKind.Refunded, item.Definition.Key, item.Redemption.UserName, reason, $"{Title(item.Definition.Key)} for {item.Redemption.UserName} refunded: {reason}.");
    }

    private void Refund(Redemption redemption, string reason) => sink.Refund(redemption, reason);

    private string Title(string key) => options(key).Title;

    private static string Suffix(EffectContext context) => context.Detail is { } detail ? $" ({detail})" : "";

    private static string Viewers(Active effect) => string.Join(", ", effect.Redemptions.Select(r => r.UserName).Distinct());

    private void Record(DateTimeOffset now, EffectEventKind kind, string key, string viewer, string? detail, string text)
    {
        events.AddFirst(new EffectEvent(now, kind, key, viewer, Title(key), detail, text));
        while (events.Count > 50) events.RemoveLast();
        log("Twitch: " + text);
    }
}
