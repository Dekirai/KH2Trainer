using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class GameplayReadinessTests
{
    private sealed class Harness
    {
        public DateTimeOffset Now = new(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);
        public readonly FakeGame Game;
        public readonly FakeSink Sink = new();
        public readonly EffectEngine Engine;
        public bool PauseTimers = true;
        public ConflictBehavior Conflict = ConflictBehavior.Queue;
        public Harness(IReadOnlyList<FeatureDefinition> features, EffectDefinition? custom = null)
        {
            Game = new FakeGame(features);
            var catalog = custom is null ? EffectCatalog.All : new[] { custom };
            Engine = new(Game, new(features), catalog,
                key => { var d = catalog.Single(e => e.Key == key); return new(d.Title, d.DurationSeconds, d.Amount, SameEffectBehavior.Extend, Conflict); },
                () => new(TimeSpan.FromMinutes(10), 600, PauseTimers), Sink, _ => { }, _ => Task.CompletedTask, new Random(4));
        }
        public void State(GameplayBlockers blockers = GameplayBlockers.None, PlayerRole role = PlayerRole.Sora, bool known = true)
            => Game.Gameplay = new(known, role, blockers);
        public void Redeem(string key, string id = "a") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public async Task Tick(double seconds = 0) { Now = Now.AddSeconds(seconds); await Engine.TickAsync(Now); }
        public async Task Observe(int seconds) { for (int i = 0; i < seconds; i++) await Tick(1); }
        public double Remaining => Engine.ActiveEffects.Single().RemainingSeconds;
        public Task End(string key) => Engine.EndEffectAsync(key, Now);
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var map = new FeatureMap(features);
        var blockers = new[] { GameplayBlockers.Unknown, GameplayBlockers.Loading, GameplayBlockers.Menu,
            GameplayBlockers.Cutscene, GameplayBlockers.Transition, GameplayBlockers.NoPlayer, GameplayBlockers.Dead,
            GameplayBlockers.InputBlocked, GameplayBlockers.TrainerFieldPause, GameplayBlockers.TrainerActorFreeze };
        foreach (var blocker in blockers)
        {
            var h = new Harness(features); h.State(blocker); h.Redeem("heal"); await h.Tick();
            check(h.Game.Commands.Count == 0 && h.Engine.PendingEffects.Count == 1 && !h.Engine.IsGameReady,
                $"control: {blocker} prevents admission and all commands");
            h.State(); await h.Tick(.25);
            check(h.Sink.IsFulfilled("a"), $"control: admission resumes after {blocker}");
        }
        foreach (var role in Enum.GetValues<PlayerRole>())
        {
            foreach (string key in new[] { "restore-mp", "silence", "flashbang", "color-chaos", "final", "heal", "slowpoke", "super-speed", "invincible" })
            {
                var h = new Harness(features); h.State(role: role); h.Redeem(key); await h.Tick();
                bool expected = role == PlayerRole.Sora || role is PlayerRole.Roxas or PlayerRole.Mickey &&
                    key is "restore-mp" or "silence" or "flashbang" or "color-chaos" or "heal" or "super-speed" or "invincible";
                check((h.Game.Commands.Count > 0 || h.Game.MovementWrites > 0) == expected, $"role: {role}/{key} respects verified allowlist");
            }
        }
        {
            var h = new Harness(features); h.State(known: false); h.Redeem("silence"); await h.Tick();
            check(h.Game.Commands.Count == 0 && !h.Engine.IsGameReady, "control: unknown/stale publication fails closed");
            h.State(role: PlayerRole.Mickey); h.Game.Set("player.mp.max", 0); h.Redeem("restore-mp", "mp"); await h.Tick();
            check(h.Sink.IsRefunded("mp") && h.Game.Count("player.mp.restore") == 0, "role: zero-MP Mickey receives a refund without a command");
            h.Game.Values.Remove(map.Get("player.mp.max").ValueSlot); h.Redeem("restore-mp", "unknown-mp"); await h.Tick();
            check(!h.Sink.IsFulfilled("unknown-mp") && !h.Sink.IsRefunded("unknown-mp"), "role: unknown maximum MP waits");
            var gummi = new Harness(features); gummi.State(GameplayBlockers.NoPlayer, PlayerRole.Other);
            gummi.Game.Set("gummi.hp", 20); gummi.Redeem("gummi-repair"); await gummi.Tick();
            check(gummi.Sink.IsFulfilled("a"), "role: Gummi uses its independent context");
        }
        {
            var h = new Harness(features); h.Redeem("silence"); await h.Tick(); await h.Tick(.25);
            double remaining = h.Remaining;
            h.State(GameplayBlockers.Menu); await h.Tick(.25); await h.Observe(20);
            check(h.Remaining == remaining && h.Engine.ActiveEffects.Single().Paused, "timer: menus preserve duration and publish paused state");
            h.State(); await h.Tick(.25);
            check(h.Remaining == remaining, "timer: resume does not charge the preceding paused interval");
            await h.Tick(.25); remaining -= .25;
            check(h.Remaining == remaining, "timer: observed controllable interval is charged");
            await h.Tick(20);
            check(h.Remaining == remaining, "timer: long unknown gap is preserved even with ready endpoints");
            await h.Tick(-5); await h.Tick(4); await h.Tick(1);
            check(h.Remaining == remaining, "timer: backward clock and catch-up cannot charge an interval twice");
            await h.Tick(.25);
            check(h.Remaining == remaining - .25, "timer: charging resumes beyond the previous clock watermark");
            h.State(role: PlayerRole.Other); await h.Tick(.25); remaining = h.Remaining; await h.Observe(5);
            check(h.Remaining == remaining, "timer: unsupported role pauses an established effect");
        }
        foreach (string key in new[] { "freeze-frame", "time-stop" })
        {
            var h = new Harness(features); h.Redeem(key); await h.Tick(); await h.Observe(2);
            check(!h.Engine.ActiveEffects.Single().Paused && h.Remaining == 3, $"self-pause: {key} counts its own duration");
            h.State(GameplayBlockers.Menu); await h.Observe(10);
            check(h.Remaining == 3 && h.Engine.ActiveEffects.Single().Paused, $"self-pause: {key} never ignores an external menu");
            h.State(); await h.Tick(1); await h.Observe(3);
            check(h.Engine.ActiveEffects.Count == 0 && h.Game.Get(key == "freeze-frame" ? "practice.field_pause" : "time.actor_effect_freeze") == 0,
                $"self-pause: {key} releases itself after control resumes");
        }
        foreach (var (first, next, firstFeature, nextFeature) in new[]
        {
            ("freeze-frame", "time-stop", "practice.field_pause", "time.actor_effect_freeze"),
            ("time-stop", "freeze-frame", "time.actor_effect_freeze", "practice.field_pause")
        })
        {
            var h = new Harness(features) { Conflict = ConflictBehavior.Replace };
            h.Redeem(first); await h.Tick(); h.State(GameplayBlockers.Menu); h.Redeem(next, "b"); await h.Tick(.25);
            check(h.Game.Count(nextFeature) == 0 && h.Game.Get(firstFeature) == 1,
                $"replace freeze: {first} never masks an external blocker");
            h.State(); h.Game.Reject = (f, a) => f == firstFeature && a[0] == 0; await h.Tick(.25);
            check(h.Game.Count(nextFeature) == 0 && h.Engine.PendingCleanupCount == 1,
                $"replace freeze: failed {first} release blocks {next}");
            h.Game.Reject = null; await h.Tick(1);
            check(h.Game.Get(firstFeature) == 0 && h.Game.Get(nextFeature) == 1 && h.Sink.IsFulfilled("b"),
                $"replace freeze: {first} releases before {next} starts");
        }
        {
            var h = new Harness(features); h.Redeem("silence"); await h.Tick();
            h.Game.Set("audio.music", 30); h.State(GameplayBlockers.Cutscene); await h.Observe(5);
            check(h.Game.Count("audio.music") == 1, "sustain: cutscenes prevent reapplication");
            h.State(); await h.Tick(.25);
            check(h.Game.Get("audio.music") == 0, "sustain: reapplication resumes after control returns");
            h.State(GameplayBlockers.Menu); int count = h.Game.Commands.Count; await h.End("silence"); await h.Observe(200);
            check(h.Game.Commands.Count == count && h.Engine.PendingCleanupCount == 1, "cleanup: menu does not send restoration or consume retry budget");
            h.State(); await h.Tick(1);
            check(h.Game.Get("audio.music") == 30 && h.Engine.PendingCleanupCount == 0, "cleanup: latest successful sustain original is restored");
        }
        {
            var h = new Harness(features); h.Redeem("silence"); await h.Tick();
            h.Game.Set("audio.music", 20); h.Game.Reject = (f, _) => f == "audio.music"; await h.Tick(1);
            h.Game.Set("audio.music", 0); h.Game.Reject = null; await h.End("silence");
            check(h.Game.Get("audio.music") == 80, "sustain: refused write does not replace the original value");
            var missing = new Harness(features); missing.Redeem("flashbang"); await missing.Tick();
            missing.Game.Values.Remove(map.Get("display.brightness_preview").ValueSlot); await missing.End("flashbang");
            check(missing.Game.Count("display.brightness_preview") == 1 && missing.Engine.PendingCleanupCount == 1,
                "restore: missing readback is not permission to overwrite");
            missing.Game.Set("display.brightness_preview", 50); await missing.Tick(1);
            check(missing.Game.Get("display.brightness_preview") == 0, "restore: readback recovery allows the pending restore");
        }
        {
            var h = new Harness(features); h.Game.Set("display.brightness_preview", 17); h.Redeem("flashbang"); await h.Tick(); await h.End("flashbang");
            check(h.Game.Get("display.brightness_preview") == 17 && h.Game.Count("display.restore_loaded") == 0,
                "brightness: restores exact original without changing color settings");
            var fov = new Harness(features); fov.Redeem("fisheye"); await fov.Tick();
            fov.Game.Values.Remove(map.Get("camera.fov").ValueSlot); int count = fov.Game.Commands.Count;
            await fov.End("fisheye"); await fov.Tick(1);
            check(fov.Game.Commands.Count == count && fov.Engine.PendingCleanupCount == 1, "FOV: missing readback defers the custom end");
            fov.Game.Set("camera.fov", 95); await fov.Tick(1);
            check(fov.Game.Get("camera.fov_enabled") == 1 && fov.Game.Get("camera.fov") == 95 && fov.Engine.PendingCleanupCount == 0,
                "FOV: new external setting is respected after readback recovers");
            var retry = new Harness(features); retry.Redeem("fisheye"); await retry.Tick();
            retry.Game.Reject = (f, a) => f == "camera.fov_enabled" && a[0] == 0; await retry.End("fisheye");
            check(retry.Engine.PendingCleanupCount == 1, "FOV: rejected custom end is not swallowed");
            retry.Game.Reject = null; await retry.Tick(1);
            check(retry.Game.Get("camera.fov_enabled") == 0 && retry.Engine.PendingCleanupCount == 0, "FOV: rejected end retries with fresh ownership checks");
        }
        {
            // A pause can appear after the first awaited statement of a custom end. Its
            // continuation must not silently settle a ChargeAfterEnd redemption.
            var d = new EffectDefinition
            {
                Key = "staged-end", Title = "Staged end", TitleDe = "Staged end", Prompt = "Test", PromptDe = "Test", Cost = 1, Category = RewardCategory.Funny,
                DurationSeconds = 1, ChargeAfterEnd = true, Group = "music", Features = ["audio.music", "audio.voice"],
                Start = _ => Task.CompletedTask,
                End = async c =>
                {
                    if (!c.State.ContainsKey("first")) { await c.RunAsync("audio.music", 70); c.State["first"] = 1; }
                    await c.RunAsync("audio.voice", 80);
                }
            };
            var h = new Harness(features, d); h.Redeem(d.Key); await h.Tick();
            h.Game.AfterExecute = (f, _) => { if (f == "audio.music") h.State(GameplayBlockers.Menu); };
            await h.Tick(1);
            check(h.Engine.PendingCleanupCount == 1 && h.Sink.Fulfilled.Count == 0 && h.Sink.Refunded.Count == 0 && h.Game.Count("audio.voice") == 0,
                "custom end: pause between statements defers without false success or refund");
            await h.Observe(200); h.State(); await h.Tick(1); await h.Tick(1);
            check(h.Sink.Fulfilled.Count == 1 && h.Game.Count("audio.music") == 1 && h.Game.Count("audio.voice") == 1 && h.Engine.PendingCleanupCount == 0,
                "custom end: continuation runs once when control returns");
        }
        {
            var h = new Harness(features); h.Game.DriveSteps = 9; h.Redeem("final"); await h.Tick();
            h.Game.SceneReady = false; int count = h.Game.Commands.Count; await h.End("final");
            check(h.Game.Commands.Skip(count).Select(c => c.Feature).SequenceEqual(["drive.cancel"]) && h.Sink.IsRefunded("a"),
                "Drive: loading permits only pending-queue cancellation, with immediate refund");
            await h.Observe(5); h.Game.SceneReady = true; await h.Tick(1); await h.Tick(1);
            check(h.Game.Count("drive.cancel") == 1 && h.Game.Count("drive.revert") == 0 && h.Sink.Refunded.Count == 1 && h.Game.Get("combat.formtimer") == 0,
                "Drive: deferred value cleanup neither cancels twice nor charges a failed transformation");
        }
    }
}
