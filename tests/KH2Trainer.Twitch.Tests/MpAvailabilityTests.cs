using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class MpAvailabilityTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game;
        public readonly FakeSink Sink = new();
        public readonly EffectEngine Engine;
        public readonly FeatureMap Map;
        public DateTimeOffset Now = new(2026, 10, 7, 15, 0, 0, TimeSpan.Zero);
        public bool PauseTimers = true;
        public Harness(IReadOnlyList<FeatureDefinition> features, PlayerRole role = PlayerRole.Sora, EffectDefinition? custom = null)
        {
            Map = new(features);
            Game = new(features) { Gameplay = new(true, role, GameplayBlockers.None) };
            Engine = new(Game, Map, custom == null ? EffectCatalog.All : [custom],
                key => new(key, 4, 0, SameEffectBehavior.Extend, ConflictBehavior.Queue),
                () => new(TimeSpan.FromMinutes(10), 60, PauseTimers), Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Maximum(double? value)
        {
            if (value.HasValue) Game.Set("player.mp.max", value.Value);
            else Game.Values.Remove(Map.Get("player.mp.max").ValueSlot);
        }
        public void Redeem(string id = "a", string key = "infinite-mp") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public Task Tick(double seconds = .25) { Now = Now.AddSeconds(seconds); return Engine.TickAsync(Now); }
        public double Remaining => Engine.ActiveEffects.Single().RemainingSeconds;
        public Task Stop() => Engine.EndEffectAsync("infinite-mp", Now);
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        double?[] unavailable = [null, double.NaN, double.PositiveInfinity, double.NegativeInfinity, -1, .5, 256, 0];
        PlayerRole[] roles = [PlayerRole.Sora, PlayerRole.Roxas, PlayerRole.Mickey];
        foreach (var role in roles) foreach (var maximum in unavailable)
        {
            string label = $"MP availability: {role}, maximum {maximum?.ToString() ?? "missing"}";
            var h = new Harness(features, role); h.Redeem(); await h.Tick(); await h.Tick(.5);
            double before = h.Remaining;
            var nextRole = roles[(Array.IndexOf(roles, role) + 1) % roles.Length];
            h.Game.Gameplay = new(true, nextRole, GameplayBlockers.None);
            h.Maximum(maximum); h.Game.Set("combat.fullmp", 0);
            check(h.Engine.ActiveEffects.Single() is { Paused: true, PauseReason: not null }, label + " is visibly paused before the next timer sample");
            for (int i = 0; i < 12; i++) await h.Tick(.5);
            check(h.Remaining == before && h.Game.Count("combat.fullmp") == 1, label + " preserves duration and does not sustain through a role/gauge change");
            h.Redeem("extension"); await h.Tick(.5);
            check(h.Engine.PendingEffects.Count == 1 && !h.Sink.IsFulfilled("extension") && h.Engine.ActiveEffects.Single().DurationSeconds == 4,
                label + " leaves an extension unpaid and queued");
            h.Maximum(100); await h.Tick(.25);
            check(h.Remaining == before + 4 && !h.Engine.ActiveEffects.Single().Paused && h.Game.Get("combat.fullmp") == 1 && h.Game.Count("combat.fullmp") == 2,
                label + " resumes sustain immediately without charging the preceding unavailable interval");
            check(h.Engine.PendingEffects.Count == 0 && h.Sink.Fulfilled.Count(r => r.Id == "extension") == 1,
                label + " accepts the extension only when it is useful again");
            await h.Tick(.5);
            check(h.Remaining == before + 3.5, label + " counts the next fully observed usable interval");
            h.Maximum(maximum); await h.Stop();
            check(h.Engine.ActiveEffects.Count == 0 && h.Engine.PendingCleanupCount == 0 && h.Game.Get("combat.fullmp") == 0,
                label + " can release its owned toggle without an MP gauge");
            check(h.Sink.Fulfilled.Count(r => r.Id == "a") == 1 && h.Sink.Fulfilled.Count(r => r.Id == "extension") == 1 && h.Sink.Refunded.Count == 0,
                label + " never settles paid redemptions twice");
        }

        // Malformed observations are unavailable, not a proof that the character has no gauge.
        foreach (string key in new[] { "infinite-mp", "restore-mp" }) foreach (var maximum in unavailable.Where(v => v != 0))
        {
            var h = new Harness(features); h.Maximum(maximum); h.Redeem(key: key); await h.Tick();
            check(h.Game.Commands.Count == 0 && h.Engine.PendingEffects.Count == 1 && h.Sink.Refunded.Count == 0,
                $"MP availability: {key} waits before dispatch for malformed/missing maximum {maximum}");
            h.Maximum(100); await h.Tick();
            check(h.Sink.IsFulfilled("a"), $"MP availability: {key} can start after that observation recovers");
        }
        foreach (double maximum in new[] { 1d, 255d }) foreach (var role in roles)
        {
            var h = new Harness(features, role); h.Maximum(maximum); h.Game.Set("player.mp", 0); h.Redeem(); await h.Tick(); await h.Tick(.5);
            check(h.Remaining == 3.5 && !h.Engine.ActiveEffects.Single().Paused,
                $"MP availability: native byte boundary {maximum} is usable for {role}");
        }

        foreach (string capability in new[] { "combat.fullmp", "player.mp.max" })
        {
            var h = new Harness(features); h.Redeem(); await h.Tick(); double before = h.Remaining;
            h.Game.Unsupported.Add(h.Map.Get(capability).CapabilitySlot); h.Game.Set("combat.fullmp", 0);
            for (int i = 0; i < 6; i++) await h.Tick(.5);
            check(h.Remaining == before && h.Game.Count("combat.fullmp") == 1 && h.Engine.ActiveEffects.Single().Paused,
                $"MP availability: lost {capability} capability pauses time and sustain");
            h.Game.Unsupported.Clear(); await h.Tick(.25);
            check(h.Remaining == before && h.Game.Get("combat.fullmp") == 1,
                $"MP availability: recovered {capability} capability resumes without retroactive charge");
        }

        await CheckCleanup(features, check);
        await CheckAccounting(features, check);
        await CheckMonitor(features, check);
    }

    private static async Task CheckCleanup(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var h = new Harness(features); h.Redeem(); await h.Tick(); h.Maximum(0);
        h.Game.Gameplay = new(true, PlayerRole.Other, GameplayBlockers.None); await h.Tick(); await h.Stop();
        check(h.Engine.PendingCleanupCount == 1 && h.Game.Count("combat.fullmp") == 1,
            "MP availability: unsupported role defers cleanup even when the gauge is absent");
        h.Game.Gameplay = new(true, PlayerRole.Mickey, GameplayBlockers.Menu); await h.Tick(1);
        check(h.Engine.PendingCleanupCount == 1 && h.Game.Count("combat.fullmp") == 1,
            "MP availability: a menu still blocks cleanup");
        h.Game.Gameplay = new(true, PlayerRole.Mickey, GameplayBlockers.None);
        h.Game.Reject = (id, args) => id == "combat.fullmp" && args[0] == 0;
        await h.Tick(1);
        check(h.Engine.PendingCleanupCount == 1 && h.Game.Get("combat.fullmp") == 1 && h.Game.Count("combat.fullmp") == 2,
            "MP availability: a refused zero-gauge cleanup remains pending");
        h.Maximum(null); h.Game.Reject = null; await h.Tick(1);
        check(h.Engine.PendingCleanupCount == 0 && h.Game.Get("combat.fullmp") == 0 && h.Game.Count("combat.fullmp") == 3,
            "MP availability: deferred cleanup retries successfully with missing maximum");
        check(h.Sink.Fulfilled.Count == 1 && h.Sink.Refunded.Count == 0,
            "MP availability: deferred cleanup does not resettle the reward");

        var missingToggle = new Harness(features); missingToggle.Redeem(); await missingToggle.Tick(); missingToggle.Maximum(0);
        missingToggle.Game.Values.Remove(missingToggle.Map.Get("combat.fullmp").ValueSlot); await missingToggle.Stop();
        check(missingToggle.Engine.PendingCleanupCount == 1 && missingToggle.Game.Count("combat.fullmp") == 1,
            "MP availability: cleanup still requires the owned toggle's readback");
        missingToggle.Game.Set("combat.fullmp", 1); await missingToggle.Tick(1);
        check(missingToggle.Engine.PendingCleanupCount == 0 && missingToggle.Game.Get("combat.fullmp") == 0,
            "MP availability: cleanup needs toggle recovery, not gauge recovery");

        var external = new Harness(features); external.Redeem(); await external.Tick(); external.Maximum(0); external.Game.Set("combat.fullmp", 0);
        await external.Stop();
        check(external.Game.Count("combat.fullmp") == 1 && external.Engine.PendingCleanupCount == 0,
            "MP availability: cleanup preserves an externally disabled toggle");

        var all = new Harness(features); all.Redeem(); await all.Tick(); all.Maximum(double.NaN);
        await all.Engine.StopAllAsync("Test stop", all.Now);
        check(all.Game.Get("combat.fullmp") == 0 && all.Engine.PendingCleanupCount == 0,
            "MP availability: StopAll releases the toggle with an invalid gauge");
    }

    private static async Task CheckAccounting(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var h = new Harness(features) { PauseTimers = false }; h.Redeem(); await h.Tick(); await h.Tick(.5); double before = h.Remaining;
        h.Maximum(0); for (int i = 0; i < 12; i++) await h.Tick(.5);
        check(h.Remaining == before && h.Engine.ActiveEffects.Single().Paused,
            "MP availability: unusable MP never consumes paid duration even with general timer pausing off");
        h.Maximum(100); await h.Tick(.5);
        check(h.Remaining == before, "MP availability: both usable endpoints are required with general timer pausing off");
        await h.Tick(2);
        check(h.Remaining == before, "MP availability: unobserved resource intervals do not consume duration");
        h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); await h.Tick(.5);
        check(h.Remaining == before - .5 && !h.Engine.ActiveEffects.Single().Paused,
            "MP availability: the existing opt-out for control pauses retains its meaning");
        h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None);
        for (int i = 0; i < 6; i++) await h.Tick(.5);
        check(h.Engine.ActiveEffects.Count == 0 && h.Game.Get("combat.fullmp") == 0 && h.Sink.Fulfilled.Count == 1,
            "MP availability: useful duration eventually expires and cleans up once");

        var back = new Harness(features); back.Redeem(); await back.Tick(); await back.Tick(.5); double left = back.Remaining;
        back.Maximum(0); await back.Tick(-.25); back.Maximum(100); await back.Tick(.25);
        check(back.Remaining == left, "MP availability: a backward-clock unavailable sample cannot charge the recovery interval");
        await back.Tick(.5);
        check(back.Remaining == left - .5, "MP availability: timing continues from the monotonic observation watermark");

        var unchanged = new Harness(features) { PauseTimers = false }; unchanged.Redeem(key: "regen"); await unchanged.Tick(); unchanged.Maximum(0); await unchanged.Tick(2);
        check(unchanged.Remaining == 2 && !unchanged.Engine.ActiveEffects.Single().Paused,
            "MP availability: effects without an MP condition retain their existing wall-time behavior");
    }

    private static async Task CheckMonitor(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        int observations = 0;
        var definition = new EffectDefinition
        {
            Key = "observed", Category = RewardCategory.Help, Title = "Observed", TitleDe = "Observed", Prompt = "Test", PromptDe = "Test", Cost = 1,
            DurationSeconds = 4, Features = ["combat.fullmp", "player.mp.max"],
            ActiveCheck = ctx => ctx.Read("player.mp.max") is > 0 ? Readiness.Ready : Readiness.Wait("MP unavailable"),
            Start = ctx => ctx.SetAsync("combat.fullmp", 1),
            Monitor = _ => { observations++; return EffectProgress.Running; }
        };
        var h = new Harness(features, custom: definition); h.Redeem(key: "observed"); await h.Tick(); h.Maximum(0); await h.Tick(.5);
        check(observations == 0 && h.Remaining == 4, "MP availability: established monitors also wait for active usability");
        h.Maximum(100); await h.Tick(.5);
        check(observations == 1 && h.Remaining == 4, "MP availability: monitor resumes without charging its unavailable interval");
    }
}
