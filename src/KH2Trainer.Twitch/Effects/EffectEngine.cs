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

    private static readonly TimeSpan SustainInterval = TimeSpan.FromSeconds(2);
    private readonly IGameControl game;
    private readonly FeatureMap features;
    private readonly Dictionary<string, EffectDefinition> catalog;
    private readonly Func<string, EffectOptions> options;
    private readonly Func<EngineSettings> settings;
    private readonly IRedemptionSink sink;
    private readonly Action<string> log;
    private readonly Func<TimeSpan, Task> delay;
    private readonly Random random;
    private readonly ConcurrentQueue<Redemption> incoming = new();
    private readonly List<Pending> pending = [];
    private readonly List<Active> active = [];
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
    }

    /// <summary>Raised after every tick that changed the queue, the running effects or the event list.</summary>
    public event Action? Changed;

    public bool IsGameReady => game.IsConnected && game.SceneReady;

    /// <summary>Accepts a redemption from any thread. It is handled on the next tick.</summary>
    public void Submit(Redemption redemption) => incoming.Enqueue(redemption);

    public IReadOnlyList<ActiveEffectInfo> ActiveEffects => active.Select(a => new ActiveEffectInfo(
        a.Definition.Key, Title(a.Definition.Key), string.Join(", ", a.Redemptions.Select(r => r.UserName).Distinct()), a.Context.Detail,
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
            while (incoming.TryDequeue(out var redemption))
            {
                changed = true;
                if (!catalog.TryGetValue(redemption.RewardKey, out var definition)) { Refund(redemption, "This reward is not available."); continue; }
                pending.Add(new Pending(redemption, definition, now));
                Record(now, EffectEventKind.Redeemed, definition.Key, redemption.UserName, null, $"{redemption.UserName} redeemed {Title(definition.Key)}.");
            }

            bool ready = IsGameReady;
            double step = lastTick is { } last ? Math.Max(0, (now - last).TotalSeconds) : 0;
            lastTick = now;
            bool becameReady = ready && !wasReady;
            wasReady = ready;

            changed |= await UpdateActiveAsync(now, step, ready, becameReady);
            changed |= await StartPendingAsync(now);
        }
        finally { gate.Release(); }
        if (changed || active.Count > 0 || pending.Count > 0) Changed?.Invoke();
    }

    private async Task<bool> UpdateActiveAsync(DateTimeOffset now, double step, bool ready, bool becameReady)
    {
        bool changed = false;
        var engine = settings();
        foreach (var effect in active.ToArray())
        {
            effect.Context.SinceStart = now - effect.Started;
            if (effect.Definition.Monitor is { } monitor && ready)
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
            if (effect.Context.Established && !effect.Fulfilled) { FulfillAll(effect); changed = true; }
            if (effect.Context.Established && (ready || !engine.PauseTimersWhileNotReady)) effect.ElapsedSeconds += step;
            if (effect.Definition.IsTimed && effect.Context.Established && effect.ElapsedSeconds >= effect.DurationSeconds)
            {
                await EndAsync(effect, EndReason.Expired, now, null);
                changed = true;
                continue;
            }
            if (ready && (becameReady || now - effect.LastSustain >= SustainInterval))
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

            // FIFO within a group: a later redemption never overtakes an earlier one of the same group.
            if (definition.Group is { } group && blockedGroups.Contains(group)) { changed |= SetStatus(item, "Waiting for an earlier redemption"); continue; }

            var same = active.FirstOrDefault(a => a.Definition.Key == definition.Key);
            if (same != null && definition.IsTimed)
            {
                if (config.SameEffect == SameEffectBehavior.Extend)
                {
                    same.DurationSeconds = Math.Min(engine.MaxDurationSeconds, same.DurationSeconds + Math.Max(1, config.DurationSeconds));
                    same.Redemptions.Add(item.Redemption);
                    pending.Remove(item);
                    if (same.Fulfilled) sink.Fulfill(item.Redemption);
                    Record(now, EffectEventKind.Extended, definition.Key, item.Redemption.UserName, $"+{Math.Max(1, config.DurationSeconds)} s", $"{item.Redemption.UserName} extended {Title(definition.Key)} to {same.DurationSeconds} s.");
                    changed = true;
                    continue;
                }
                if (config.SameEffect == SameEffectBehavior.Refund) { Drop(item, $"{Title(definition.Key)} is already running", now); changed = true; continue; }
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

            // Check before touching a running effect, so nothing is replaced while the game is loading.
            var context = new EffectContext(definition, item.Redemption, definition.IsTimed ? Math.Max(1, config.DurationSeconds) : 0,
                config.Amount, game, features, random, delay);
            var readiness = Check(context, includeEffectCheck: !(conflict != null && definition.Interrupts));
            if (readiness.Kind == ReadinessKind.Wait)
            {
                changed |= SetStatus(item, readiness.Reason);
                if (definition.Group != null) blockedGroups.Add(definition.Group);
                continue;
            }
            if (readiness.Kind == ReadinessKind.Reject) { Drop(item, readiness.Reason, now); changed = true; continue; }

            pending.Remove(item);
            changed = true;
            if (conflict != null && definition.Interrupts)
            {
                // Ending the running effect is the whole job (a form's end reverts it).
                await EndAsync(conflict, EndReason.Interrupted, now, $"{item.Redemption.UserName} interrupted it");
                sink.Fulfill(item.Redemption);
                Record(now, EffectEventKind.Done, definition.Key, item.Redemption.UserName, null, $"{item.Redemption.UserName}: {Title(definition.Key)} done.");
                continue;
            }
            if (conflict != null) await EndAsync(conflict, EndReason.Replaced, now, $"replaced by {Title(definition.Key)}");
            try
            {
                await definition.Start(context);
            }
            catch (Exception error)
            {
                await context.RestoreAsync();
                Refund(item.Redemption, error.Message);
                Record(now, EffectEventKind.Failed, definition.Key, item.Redemption.UserName, error.Message, $"{Title(definition.Key)} for {item.Redemption.UserName} did not work: {error.Message} Points refunded.");
                continue;
            }
            if (definition.IsTimed || !context.Established)
            {
                var effect = new Active(context, now, context.DurationSeconds);
                active.Add(effect);
                if (context.Established) FulfillAll(effect);
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

    /// <summary>Refunds one waiting redemption.</summary>
    public async Task CancelAsync(string redemptionId, DateTimeOffset now)
    {
        await gate.WaitAsync();
        try
        {
            var item = pending.FirstOrDefault(p => p.Redemption.Id == redemptionId);
            if (item != null) Drop(item, "Removed by the streamer", now);
        }
        finally { gate.Release(); }
        Changed?.Invoke();
    }

    /// <summary>Ends every running effect and refunds everything still waiting.</summary>
    public async Task StopAllAsync(string reason, DateTimeOffset now)
    {
        await gate.WaitAsync();
        try
        {
            while (incoming.TryDequeue(out var redemption)) Refund(redemption, reason);
            foreach (var item in pending.ToArray()) Drop(item, reason, now);
            foreach (var effect in active.ToArray())
            {
                if (!effect.Fulfilled) foreach (var redemption in effect.Redemptions) Refund(redemption, reason);
                await EndAsync(effect, EndReason.Stopped, now, reason);
            }
        }
        finally { gate.Release(); }
        Changed?.Invoke();
    }

    private async Task EndAsync(Active effect, EndReason reason, DateTimeOffset now, string? why)
    {
        await StopAsync(effect, reason, now);
        if (!effect.Fulfilled && effect.Context.Established) FulfillAll(effect);
        Record(now, EffectEventKind.Ended, effect.Definition.Key, Viewers(effect), why, $"{Title(effect.Definition.Key)} ended{(why is null ? "" : ": " + why)}.");
    }

    private async Task StopAsync(Active effect, EndReason reason, DateTimeOffset now)
    {
        active.Remove(effect);
        effect.Context.EndReason = reason;
        try { await (effect.Definition.End ?? (ctx => ctx.RestoreAsync()))(effect.Context); }
        catch (Exception error) { log($"Twitch: could not fully undo {Title(effect.Definition.Key)}: {error.Message}"); }
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
