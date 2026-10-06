using System.Collections.Concurrent;

namespace KH2Trainer.Twitch;

/// <summary>Per-reward values the streamer configured.</summary>
public sealed record EffectOptions(string Title, int DurationSeconds, int Amount, SameEffectBehavior SameEffect, ConflictBehavior Conflict);

/// <summary>Engine-wide limits.</summary>
public sealed record EngineSettings(TimeSpan MaxWait, int MaxDurationSeconds, bool PauseTimersWhileNotReady);

public sealed record ActiveEffectInfo(string Key, string Title, string Viewers, string? Detail, double RemainingSeconds, double DurationSeconds, bool Established);
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
    }

    /// <summary>An ended effect whose values the game refused to take back; retried while the game is ready.</summary>
    private sealed class Restoring(EffectContext context, DateTimeOffset deadline)
    {
        public EffectContext Context { get; } = context;
        public DateTimeOffset Deadline { get; } = deadline;
        public DateTimeOffset LastTry { get; set; }
    }

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
    private readonly LinkedList<EffectEvent> events = new();
    private DateTimeOffset? lastTick;
    private bool wasReady;
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

    public bool IsGameReady => game.IsConnected && game.SceneReady;

    /// <summary>The trainer's field freeze (Freeze Frame) holds the game; most commands wait until it ends.</summary>
    private bool FieldPaused => fieldPauseSlot >= 0 && game.TryRead(fieldPauseSlot, out double value) && value == 1;

    /// <summary>Accepts a redemption from any thread. It is handled on the next tick.</summary>
    public void Submit(Redemption redemption) => incoming.Enqueue(redemption);

    public IReadOnlyList<ActiveEffectInfo> ActiveEffects => active.Select(a => new ActiveEffectInfo(
        a.Definition.Key, Title(a.Definition.Key), Viewers(a), a.Context.Detail,
        a.Definition.IsTimed ? Math.Max(0, a.DurationSeconds - a.ElapsedSeconds) : 0, a.DurationSeconds, a.Context.Established)).ToArray();

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

            bool ready = IsGameReady;
            double step = lastTick is { } last ? Math.Max(0, (now - last).TotalSeconds) : 0;
            lastTick = now;
            bool becameReady = ready && !wasReady;
            wasReady = ready;

            changed |= await RetryRestoresAsync(now, ready);
            changed |= await UpdateActiveAsync(now, step, ready, becameReady);
            changed |= await StartPendingAsync(now);
        }
        finally { gate.Release(); }
        if (changed || active.Count > 0 || pending.Count > 0) Changed?.Invoke();
    }

    private async Task<bool> RetryRestoresAsync(DateTimeOffset now, bool ready)
    {
        bool changed = false;
        foreach (var item in restoring.ToArray())
        {
            if (now > item.Deadline)
            {
                restoring.Remove(item);
                log($"Twitch: could not undo {Title(item.Context.Definition.Key)} ({string.Join(", ", item.Context.AbandonRestores())}). Set it back in the trainer if needed.");
                changed = true;
                continue;
            }
            // Freeze Frame's own release must be retried while the field is still paused.
            if (!ready || FieldPaused && item.Context.Definition.Group != "freeze" || now - item.LastTry < RestoreInterval) continue;
            item.LastTry = now;
            await item.Context.RestoreAsync();
            if (!item.Context.HasPendingRestores) { restoring.Remove(item); changed = true; }
        }
        return changed;
    }

    private async Task<bool> UpdateActiveAsync(DateTimeOffset now, double step, bool ready, bool becameReady)
    {
        bool changed = false;
        var engine = settings();
        foreach (var effect in active.ToArray())
        {
            effect.Context.SinceStart = now - effect.Started;
            // Monitors also run during loading: a Drive Form transition loads its model.
            if (effect.Definition.Monitor is { } monitor && game.IsConnected)
            {
                var progress = monitor(effect.Context);
                if (progress.Status == EffectStatus.Failed && !effect.Context.Established)
                {
                    await StopAsync(effect, EndReason.EndedByGame, now);
                    foreach (var redemption in effect.Redemptions) Refund(redemption, progress.Reason);
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
            if (effect.Context.Established && (ready || !engine.PauseTimersWhileNotReady)) effect.ElapsedSeconds += step;
            if (effect.Definition.IsTimed && effect.Context.Established && effect.ElapsedSeconds >= effect.DurationSeconds)
            {
                await EndAsync(effect, EndReason.Expired, now, null);
                changed = true;
                continue;
            }
            if (ready && !FieldPaused && (becameReady || now - effect.LastSustain >= SustainInterval))
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
            if (definition.Group != null && restoring.Any(r => r.Context.Definition.Group == definition.Group))
            {
                Block(item, "Waiting until the previous effect is undone", blockedGroups);
                changed = true;
                continue;
            }

            // Check before touching a running effect, so nothing is replaced while the game is loading.
            var context = new EffectContext(definition, item.Redemption, definition.IsTimed ? Math.Max(1, config.DurationSeconds) : 0,
                config.Amount, game, features, random, delay);
            var readiness = Check(context, includeEffectCheck: !(conflict != null && definition.Interrupts));
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
                if (replaced != null) await CleanUpAsync(replaced.Context);
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

    private Readiness Check(EffectContext context, bool includeEffectCheck)
    {
        var definition = context.Definition;
        if (!game.IsConnected) return Readiness.Wait("Waiting for the trainer to connect to the game");
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
            if (IsGameReady) foreach (var item in restoring.ToArray()) { await item.Context.RestoreAsync(); if (!item.Context.HasPendingRestores) restoring.Remove(item); }
        }
        finally { gate.Release(); }
        Changed?.Invoke();
    }

    /// <summary>Ends an effect. Returns false when its end step failed (for example the game refused a revert).</summary>
    private async Task<bool> EndAsync(Active effect, EndReason reason, DateTimeOffset now, string? why)
    {
        bool ok = await StopAsync(effect, reason, now);
        if (!effect.Fulfilled)
        {
            if (effect.Context.Established && (ok || !effect.Definition.ChargeAfterEnd)) FulfillAll(effect);
            else
            {
                string refund = why ?? "it ended before it took effect";
                foreach (var redemption in effect.Redemptions) Refund(redemption, refund);
                Record(now, EffectEventKind.Refunded, effect.Definition.Key, Viewers(effect), why,
                    $"{Title(effect.Definition.Key)} ended without effect{(why is null ? "" : ": " + why)}. Points refunded.");
                return ok;
            }
        }
        Record(now, EffectEventKind.Ended, effect.Definition.Key, Viewers(effect), why, $"{Title(effect.Definition.Key)} ended{(why is null ? "" : ": " + why)}.");
        return ok;
    }

    private async Task<bool> StopAsync(Active effect, EndReason reason, DateTimeOffset now)
    {
        active.Remove(effect);
        effect.Context.EndReason = reason;
        bool ok = true;
        try { await (effect.Definition.End ?? (ctx => ctx.RestoreAsync()))(effect.Context); }
        catch (Exception error)
        {
            ok = false;
            log($"Twitch: could not fully end {Title(effect.Definition.Key)}: {error.Message}");
        }
        QueueRestore(effect.Context, now);
        return ok;
    }

    /// <summary>After a replacement failed to start: end the replaced effect properly (for example revert its Drive Form).</summary>
    private async Task CleanUpAsync(EffectContext replaced)
    {
        replaced.EndReason = EndReason.Stopped;
        try { await (replaced.Definition.End ?? (ctx => ctx.RestoreAsync()))(replaced); }
        catch (Exception error) { log($"Twitch: could not fully end {Title(replaced.Definition.Key)}: {error.Message}"); }
    }

    private void QueueRestore(EffectContext context, DateTimeOffset now)
    {
        if (context.HasPendingRestores && restoring.All(r => r.Context != context)) restoring.Add(new Restoring(context, now + RestoreWindow) { LastTry = now });
    }

    private void FulfillAll(Active effect)
    {
        effect.Fulfilled = true;
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
