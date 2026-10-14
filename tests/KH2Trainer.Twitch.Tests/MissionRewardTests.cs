using KH2Trainer.Core;
using KH2Trainer.Twitch;

/// <summary>Mission clock and score rewards against the bridge's mission readouts (slots 209-212, 225, 229 and 233).</summary>
internal static class MissionRewardTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game; public readonly FakeSink Sink = new(); public readonly EffectEngine Engine;
        public DateTimeOffset Now = new(2026, 10, 14, 12, 0, 0, TimeSpan.Zero);
        public Harness(IReadOnlyList<FeatureDefinition> features, PlayerRole role = PlayerRole.Sora)
        {
            Game = new(features) { Gameplay = new(true, role, GameplayBlockers.None) };
            Engine = new(Game, new(features), EffectCatalog.All,
                key => { var d = EffectCatalog.Find(key)!; return new(d.Title, d.DurationSeconds, d.Amount, SameEffectBehavior.Extend, ConflictBehavior.Queue); },
                () => new(TimeSpan.FromMinutes(10), 600, true), Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Redeem(string key, string id = "a") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public Task Tick(double seconds = .25) { Now = Now.AddSeconds(seconds); return Engine.TickAsync(Now); }
        public async Task Observe(double seconds) { for (double done = 0; done < seconds; done += .5) await Tick(.5); }
        public double[] Restarts => Game.Calls("mission.timer.countdown").Select(a => a[0]).ToArray();
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var map = new FeatureMap(features);
        check(map.Get("mission.timer.countdown").CommandId == 1226 && map.Get("mission.timer.freeze") is { CommandId: 1233, ValueSlot: 233, CapabilitySlot: 233, Kind: FeatureKind.Toggle } &&
            new[] { "mission.phase", "mission.timer.seconds", "mission.timer.direction", "mission.timer.phase", "mission.timer.paused" }.Select(id => map.Get(id).ValueSlot).SequenceEqual([209, 210, 211, 212, 229]),
            "mission: rewards use the native restart 1226, the freeze toggle 1233 and readouts 209-212/229");
        foreach (string key in new[] { "overtime", "time-crunch", "time-out", "score-bonus" })
        {
            var definition = EffectCatalog.Find(key)!;
            check(definition.AllowedRoles == (EffectPlayerRoles.Sora | EffectPlayerRoles.Roxas) && (key == "score-bonus" || definition.Group == "mission-clock"),
                $"mission: {key} admits Sora and Roxas and shares the mission clock group");
        }
        foreach (string key in new[] { "overtime", "time-crunch" })
            check(EffectCatalog.Find(key)!.Prompt.Contains("depends on the mission", StringComparison.Ordinal), $"mission: {key} describes expiry neutrally");

        // Overtime: whole seconds plus 30, only on a running countdown below the one-hour HUD range.
        foreach (var (seconds, target) in new[] { (75.5, 105.0), (0.4, 30.0), (3568.9, 3598.0) })
        {
            var h = new Harness(features); h.Game.StartMission(seconds); h.Redeem("overtime"); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Restarts.SequenceEqual([target]) && h.Game.Get("mission.timer.seconds") == target,
                $"overtime: {seconds} s restarts the countdown at {target} s");
        }
        foreach (var (name, setup) in new (string, Action<FakeGame>)[]
        {
            ("near the maximum", g => g.StartMission(3569)), ("count-up", g => g.StartMission(80, countdown: false)),
            ("no mission", _ => { }), ("intro phase", g => { g.StartMission(80); g.Set("mission.phase", 0); }),
            ("finished mission", g => { g.StartMission(80); g.EndMission(); }), ("stopped clock", g => { g.StartMission(80); g.Set("mission.timer.phase", 0); }),
        })
        {
            var h = new Harness(features); setup(h.Game); h.Redeem("overtime"); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.Commands.Count == 0, $"overtime: {name} refunds without a restart");
        }
        foreach (var (name, pause, resume) in new (string, Action<FakeGame>, Action<FakeGame>)[]
        {
            ("paused by a native owner", g => g.NativeClockPause = true, g => g.NativeClockPause = false),
            ("armed", g => g.Set("mission.timer.phase", 1), g => g.Set("mission.timer.phase", 2)),
        })
        {
            var h = new Harness(features); h.Game.StartMission(90); pause(h.Game); h.Redeem("overtime"); await h.Tick(); await h.Tick(5);
            check(h.Engine.PendingEffects.Count == 1 && h.Game.Commands.Count == 0, $"overtime: a clock {name} waits");
            resume(h.Game); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Restarts.SequenceEqual([120.0]), $"overtime: a clock {name} restarts once it runs");
        }
        foreach (var role in new[] { PlayerRole.Roxas, PlayerRole.Mickey })
        {
            var h = new Harness(features, role); h.Game.StartMission(90); h.Redeem("overtime"); await h.Tick();
            check(h.Sink.IsFulfilled("a") == (role == PlayerRole.Roxas) && h.Engine.PendingEffects.Count == (role == PlayerRole.Roxas ? 0 : 1),
                $"overtime: {role} follows the mission role list");
        }

        // Time Crunch: a 30 s floor that never converts a count-up.
        {
            var h = new Harness(features); h.Game.StartMission(46); h.Redeem("time-crunch"); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Restarts.SequenceEqual([30.0]) && h.Game.Count("mission.timer.countup") == 0, "time crunch: restarts at 30 s");
        }
        foreach (var (name, setup) in new (string, Action<FakeGame>)[]
            { ("45 s left", g => g.StartMission(45)), ("count-up", g => g.StartMission(600, countdown: false)), ("no mission", _ => { }) })
        {
            var h = new Harness(features); setup(h.Game); h.Redeem("time-crunch"); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.Commands.Count == 0, $"time crunch: {name} refunds without a command");
        }
        {
            var h = new Harness(features); h.Game.StartMission(300); h.Game.NativeClockPause = true; h.Redeem("time-crunch"); await h.Tick();
            check(h.Engine.PendingEffects.Count == 1 && h.Game.Commands.Count == 0, "time crunch: a paused clock waits");
            // The clock may pause between the check and the command; the bridge refuses and nothing is charged.
            h.Game.NativeClockPause = false;
            h.Game.Reject = (f, _) => f == "mission.timer.countdown"; await h.Tick();
            check(!h.Sink.IsFulfilled("a") && !h.Sink.IsRefunded("a") && h.Engine.PendingEffects.Count == 1, "time crunch: a refused restart is retried, not charged");
            h.Game.Reject = null; await h.Tick(4);
            check(h.Sink.IsFulfilled("a") && h.Game.Get("mission.timer.seconds") == 30, "time crunch: the retry restarts the clock");
        }

        // Time Out: paid once the bridge publishes its own freeze bit; released at the end without native owners.
        foreach (bool countdown in new[] { true, false })
        {
            var h = new Harness(features); h.Game.StartMission(120, countdown); h.Redeem("time-out"); await h.Tick();
            check(h.Game.Get("mission.timer.freeze") == 1 && h.Game.Get("mission.timer.paused") == 1 && !h.Sink.IsFulfilled("a"),
                $"time out: countdown={countdown} freezes the clock but waits for the published hold before charging");
            await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Engine.ActiveEffects.Single().Established, $"time out: countdown={countdown} is paid once the hold is observed");
            h.Redeem("overtime", "b"); await h.Observe(10);
            check(h.Engine.PendingEffects.Count == 1 && h.Restarts.Length == 0, $"time out: countdown={countdown} keeps other clock rewards waiting");
            await h.Observe(25);
            check(h.Engine.ActiveEffects.All(a => a.Key != "time-out") && h.Game.Get("mission.timer.freeze") == 0 && h.Game.Get("mission.timer.paused") == 0 &&
                h.Game.Calls("mission.timer.freeze").Select(a => a[0]).SequenceEqual([1.0, 0.0]), $"time out: countdown={countdown} releases its own bit when it expires");
            check(countdown ? h.Sink.IsFulfilled("b") && h.Restarts.SequenceEqual([150.0]) : h.Sink.IsRefunded("b"),
                $"time out: countdown={countdown} lets the queued Overtime decide afterwards");
        }
        {
            var h = new Harness(features); h.Game.StartMission(120); h.Game.NativeClockPause = true; h.Redeem("time-out"); await h.Tick(); await h.Tick(5);
            check(h.Engine.PendingEffects.Count == 1 && h.Game.Commands.Count == 0, "time out: a clock held by a native owner waits");
            h.Game.NativeClockPause = false; h.Game.Set("mission.timer.freeze", 1); h.Game.Set("mission.timer.paused", 1); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.Commands.Count == 0, "time out: an already frozen clock refunds without taking over the streamer's freeze");
        }
        {
            var h = new Harness(features); h.Game.StartMission(120); h.Redeem("time-out"); await h.Tick(); await h.Tick(); double remaining = h.Engine.ActiveEffects.Single().RemainingSeconds;
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); await h.Observe(5);
            check(h.Engine.ActiveEffects.Single().RemainingSeconds == remaining && h.Game.Get("mission.timer.freeze") == 1, "time out: a menu pauses the reward and keeps the hold");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); await h.Tick();
            h.Game.EndMission(); await h.Tick();
            check(h.Engine.ActiveEffects.Count == 0 && h.Engine.PendingCleanupCount == 0 && h.Game.Count("mission.timer.freeze") == 1,
                "time out: a finished mission ends the reward; the bridge already dropped its bit");
            h.Game.StartMission(60); await h.Observe(3);
            check(h.Game.Count("mission.timer.freeze") == 1 && h.Game.Get("mission.timer.freeze") == 0, "time out: the next mission is never frozen again");
        }
        {
            // A native clock reset clears the whole mask while the mission continues.
            var h = new Harness(features); h.Game.StartMission(120); h.Redeem("time-out"); await h.Tick(); await h.Tick();
            h.Game.Set("mission.timer.freeze", 0); h.Game.Set("mission.timer.paused", 0); await h.Observe(3);
            check(h.Engine.ActiveEffects.Count == 0 && h.Sink.IsFulfilled("a") && h.Game.Count("mission.timer.freeze") == 1,
                "time out: a dropped hold ends the reward and is not re-applied");
        }
        {
            var h = new Harness(features); h.Game.StartMission(120);
            h.Game.AfterExecute = (f, a) => { if (f == "mission.timer.freeze" && a[0] == 1) { h.Game.Set("mission.timer.freeze", 0); h.Game.Set("mission.timer.paused", 0); } };
            h.Redeem("time-out"); await h.Tick(); await h.Observe(12);
            check(h.Sink.IsRefunded("a") && !h.Sink.IsFulfilled("a") && h.Engine.ActiveEffects.Count == 0 && h.Engine.PendingCleanupCount == 0,
                "time out: an acknowledged freeze that is never published is refunded");
        }
        {
            var h = new Harness(features); h.Game.StartMission(120); h.Redeem("time-out"); await h.Tick(); await h.Tick();
            await h.Engine.StopAllAsync("stopped", h.Now);
            check(h.Game.Get("mission.timer.freeze") == 0 && h.Engine.PendingCleanupCount == 0, "time out: Stop all releases the hold");
        }
        foreach (var role in new[] { PlayerRole.Roxas, PlayerRole.Mickey })
        {
            var h = new Harness(features, role); h.Game.StartMission(120); h.Redeem("time-out"); await h.Tick(); await h.Tick();
            check(h.Sink.IsFulfilled("a") == (role == PlayerRole.Roxas) && h.Game.Count("mission.timer.freeze") == (role == PlayerRole.Roxas ? 1 : 0),
                $"time out: {role} follows the mission role list");
        }

        // Score Bonus: one native score write, capped at the score object's maximum.
        foreach (var (score, target) in new[] { (500.0, 600.0), (9950.0, 9999.0) })
        {
            var h = new Harness(features); h.Game.StartMission(60); h.Game.Set("mission.score", score); h.Redeem("score-bonus"); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.Calls("mission.score.set").Single().SequenceEqual([target]) &&
                h.Engine.RecentEvents.First().Detail == $"+{target - score:0} points", $"score bonus: {score} becomes {target}");
        }
        foreach (var (name, setup) in new (string, Action<FakeGame>)[]
        {
            ("full score", g => { g.StartMission(60); g.Set("mission.score", 9999); }), ("no score object", g => g.StartMission(60)),
            ("finished mission", g => { g.StartMission(60); g.Set("mission.score", 10); g.EndMission(); }),
        })
        {
            var h = new Harness(features); setup(h.Game); h.Redeem("score-bonus"); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.Commands.Count == 0, $"score bonus: {name} refunds without a write");
        }
    }
}
