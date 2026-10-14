using KH2Trainer.Core;
using KH2Trainer.Twitch;

/// <summary>No write without a restorable original, the streamer's own developer desktop, and visible pending cleanup.</summary>
internal static class RewardSafetyTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game; public readonly FakeSink Sink = new(); public readonly EffectEngine Engine;
        public DateTimeOffset Now = new(2026, 10, 14, 18, 0, 0, TimeSpan.Zero);
        public Harness(IReadOnlyList<FeatureDefinition> features)
        {
            Game = new(features);
            Engine = new(Game, new(features), EffectCatalog.All,
                key => { var d = EffectCatalog.Find(key)!; return new(d.Title, d.DurationSeconds, d.Amount, SameEffectBehavior.Extend, ConflictBehavior.Queue); },
                () => new(TimeSpan.FromMinutes(10), 600, true), Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Redeem(string key, string id = "a") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public Task Tick(double seconds = .25) { Now = Now.AddSeconds(seconds); return Engine.TickAsync(Now); }
        public async Task Observe(int seconds) { for (int i = 0; i < seconds; i++) await Tick(1); }
        public Task End(string key) => Engine.EndEffectAsync(key, Now);
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var map = new FeatureMap(features);
        EffectContext Context(FakeGame game, string key) => new(EffectCatalog.Find(key)!, new Redemption("r", key, "Viewer", "", DateTimeOffset.UtcNow, IsTest: true),
            EffectCatalog.Find(key)!.DurationSeconds, EffectCatalog.Find(key)!.Amount, game, map, new Random(1), _ => Task.CompletedTask);

        // Lucky Streak used to add to an unreadable value and store a missing original that was never restored.
        foreach (string missing in new[] { "loot.jackpot", "loot.lucky" })
        {
            var h = new Harness(features); h.Game.Values.Remove(map.Get(missing).ValueSlot); h.Redeem("lucky-streak"); await h.Tick(); await h.Observe(5);
            check(h.Engine.PendingEffects.Count == 1 && h.Game.Commands.Count == 0 && !h.Sink.IsRefunded("a"),
                $"restorable: Lucky Streak waits without any write while {missing} is unreadable");
            h.Game.Set(missing, 1); double jackpot = h.Game.Get("loot.jackpot")!.Value, lucky = h.Game.Get("loot.lucky")!.Value; await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.Get("loot.jackpot") == jackpot + 3 && h.Game.Get("loot.lucky") == lucky + 20,
                $"restorable: Lucky Streak boosts both values once {missing} is readable");
            await h.End("lucky-streak");
            check(h.Game.Get("loot.jackpot") == jackpot && h.Game.Get("loot.lucky") == lucky && h.Engine.PendingCleanupCount == 0,
                $"restorable: Lucky Streak restores both originals after {missing} recovered");
        }
        {
            var h = new Harness(features); h.Game.Set("loot.jackpot", 12); h.Redeem("lucky-streak"); await h.Tick();
            check(h.Engine.PendingEffects.Count == 1 && h.Game.Commands.Count == 0, "restorable: an original outside the settable range is not restorable either");
        }
        {
            var h = new Harness(features); h.Game.Reject = (f, _) => f == "loot.lucky"; h.Redeem("lucky-streak"); await h.Tick();
            check(!h.Sink.IsFulfilled("a") && h.Game.Get("loot.jackpot") == 0 && h.Game.Calls("loot.jackpot").Select(a => a[0]).SequenceEqual([3.0, 0.0]) &&
                h.Engine.PendingCleanupCount == 0, "restorable: a refused second boost undoes the first before retrying");
        }
        {
            // The second value disappears after the first write: no write is computed from it, and the first is undone.
            var h = new Harness(features); int lucky = map.Get("loot.lucky").ValueSlot;
            h.Game.AfterExecute = (f, a) => { if (f == "loot.jackpot" && a[0] == 3) h.Game.Values.Remove(lucky); };
            h.Redeem("lucky-streak"); await h.Tick();
            check(h.Game.Count("loot.lucky") == 0 && h.Game.Get("loot.jackpot") == 0 && !h.Sink.IsFulfilled("a"), "restorable: an original lost between the two writes defers and rolls back");
        }
        foreach (var (key, feature, applied) in new[] { ("magnet", "loot.draw", 1500.0), ("glass-cannon", "damage.player.general", 250.0) })
        {
            var h = new Harness(features); h.Game.Values.Remove(map.Get(feature).ValueSlot); h.Redeem(key); await h.Tick(); await h.Observe(5);
            check(h.Engine.PendingEffects.Count == 1 && h.Game.Commands.Count == 0, $"restorable: {key} waits for a readable {feature}");
            h.Game.Set(feature, 100); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.Get(feature) == applied, $"restorable: {key} starts once {feature} is readable");
            await h.End(key); check(h.Game.Get(feature) == 100, $"restorable: {key} restores the recovered original");
        }
        {
            var game = new FakeGame(features); game.Values.Remove(map.Get("audio.music").ValueSlot); game.Values.Remove(map.Get("render.hide_captions").ValueSlot);
            var context = Context(game, "silence");
            bool deferred = false;
            try { await context.SetAsync("audio.music", 0); } catch (EffectDeferredException) { deferred = true; }
            check(deferred && game.Commands.Count == 0, "restorable: SetAsync never writes a number without a restorable original");
            await context.SetAsync("render.hide_captions", 1); await context.RestoreAsync();
            check(game.Get("render.hide_captions") == 0, "restorable: a toggle without a readback still restores to off");
        }
        foreach (var (key, read) in new[] { ("munny-gift", "munny"), ("pickpocket", "munny"), ("refill-drive", "player.drive.max"), ("enrage-enemy", "target_revenge_threshold") })
        {
            var game = new FakeGame(features); game.Values.Remove(map.Get(read).ValueSlot);
            bool deferred = false;
            try { await EffectCatalog.Find(key)!.Start(Context(game, key)); } catch (EffectDeferredException) { deferred = true; }
            check(deferred && game.Commands.Count == 0, $"restorable: {key} never computes its write from an unreadable {read}");
        }

        // Hacker Mode: never charges for or hides a desktop the streamer opened.
        {
            var h = new Harness(features); h.Game.BridgeStatus = 3; h.Redeem("hacker-mode"); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.Commands.Count == 0, "hacker mode: an open developer desktop refunds without a command");
        }
        {
            var h = new Harness(features); h.Redeem("hacker-mode"); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.BridgeStatus == 3, "hacker mode: opens the developer desktop");
            await h.Observe(11);
            check(h.Engine.ActiveEffects.Count == 0 && h.Game.Count("developer.hide") == 1 && h.Game.BridgeStatus == 2, "hacker mode: hides the desktop it opened");
        }
        {
            var h = new Harness(features); h.Redeem("hacker-mode"); await h.Tick();
            h.Game.BridgeStatus = 2; await h.Observe(11);
            check(h.Engine.ActiveEffects.Count == 0 && h.Game.Count("developer.hide") == 0, "hacker mode: a desktop that is already hidden is left alone");
        }
        {
            var h = new Harness(features); h.Game.Reject = (f, _) => f == "developer.show"; h.Redeem("hacker-mode"); await h.Tick();
            h.Game.BridgeStatus = 3; h.Game.Reject = null; await h.Tick(4);
            check(h.Sink.IsRefunded("a") && h.Game.Count("developer.hide") == 0, "hacker mode: a refused show never hides the streamer's desktop opened meanwhile");
        }

        // Pending cleanup is visible with what each cleanup waits for.
        {
            var h = new Harness(features); h.Redeem("silence"); await h.Tick();
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); await h.End("silence");
            var pending = h.Engine.PendingCleanups.Single();
            check(h.Engine.PendingCleanupCount == 1 && pending.Key == "silence" && pending.Title == "Silence!" && pending.Reason.Contains("Menu", StringComparison.Ordinal),
                "cleanup list: a deferred end names its reward and what it waits for");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); h.Game.Reject = (f, _) => f == "audio.music"; await h.Tick(1);
            check(h.Engine.PendingCleanups.Single() is { Key: "silence", Reason: "Changed values are restored when the game accepts them" },
                "cleanup list: a refused restore stays listed while control is available");
            h.Game.Reject = null; await h.Tick(1);
            check(h.Engine.PendingCleanups.Count == 0 && h.Game.Get("audio.music") == 80, "cleanup list: empties once the value is restored");
        }
        {
            var h = new Harness(features); h.Redeem("super-speed"); await h.Tick();
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); await h.End("super-speed");
            check(h.Engine.PendingCleanups.Single().Reason == "Waiting for the game to release native ownership",
                "cleanup list: native ownership cleanup does not claim to wait for player control");
        }
    }
}
