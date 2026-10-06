using KH2Trainer.Core;
using KH2Trainer.Twitch;

/// <summary>Queue, conflict, stacking, readiness and restore rules of the effect engine.</summary>
internal static class EngineTests
{
    private sealed class Clock { public DateTimeOffset Now = new(2026, 1, 1, 12, 0, 0, TimeSpan.Zero); }

    private sealed record Harness(EffectEngine Engine, FakeGame Game, FakeSink Sink, TwitchSettings Settings, Clock Clock)
    {
        public async Task TickAsync(double seconds = 0, double step = 1)
        {
            if (seconds <= 0) { await Engine.TickAsync(Clock.Now); return; }
            for (double done = 0; done < seconds - 1e-9; done += step)
            {
                Clock.Now = Clock.Now.AddSeconds(Math.Min(step, seconds - done));
                Game.Pump();
                await Engine.TickAsync(Clock.Now);
            }
        }

        public void Redeem(string id, string key, string user = "Viewer") =>
            Engine.Submit(new Redemption(id, key, user, "", Clock.Now, "reward-" + key));

        public bool IsActive(string key) => Engine.ActiveEffects.Any(a => a.Key == key);
        public bool IsWaiting(string id) => Engine.PendingEffects.Any(p => p.RedemptionId == id);
    }

    private static Harness Create(IReadOnlyList<FeatureDefinition> features, Action<TwitchSettings>? configure = null)
    {
        var game = new FakeGame(features);
        var sink = new FakeSink();
        var settings = new TwitchSettings();
        configure?.Invoke(settings);
        var engine = new EffectEngine(game, new FeatureMap(features), EffectCatalog.All,
            key => RewardResolver.Options(EffectCatalog.Find(key)!, settings), () => RewardResolver.Engine(settings),
            sink, _ => { }, _ => Task.CompletedTask, new Random(3));
        return new Harness(engine, game, sink, settings, new Clock());
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        // The streamer's example: Final Form is running, Valor Form waits until Final Form has ended.
        {
            var h = Create(features);
            h.Redeem("a", "final"); await h.TickAsync(); await h.TickAsync(1);
            check(h.Game.Get("player.form.id") == 5 && h.Sink.IsFulfilled("a"), "queue: Final Form starts and is fulfilled once Sora transformed");
            check(h.Game.Get("combat.formtimer") == 1, "queue: the form timer is held so the form lasts as long as the reward");
            h.Redeem("b", "valor"); await h.TickAsync(1);
            check(h.IsWaiting("b") && h.Game.Get("player.form.id") == 5 && !h.Sink.IsFulfilled("b"), "queue: Valor Form waits while Final Form runs");
            check(h.Engine.PendingEffects.Single().Status.Contains("Final Form"), "queue: the waiting reason names the running form");
            await h.TickAsync(40);
            check(h.IsActive("final") && h.IsWaiting("b"), "queue: Valor still waits before Final's 45 s are over");
            await h.TickAsync(6);
            check(!h.IsActive("final") && h.Game.Get("player.form.id") == 1, "queue: Valor Form starts right after Final Form ends");
            check(h.Game.Calls("drive.trigger").Select(a => a[0]).SequenceEqual([5.0, 1.0]) && h.Game.Count("drive.revert") == 1,
                "queue: Final is reverted, then Valor is triggered");
            await h.TickAsync(1);
            check(h.Sink.IsFulfilled("b") && h.Sink.Refunded.Count == 0, "queue: both viewers are charged, nobody refunded");
        }

        // FIFO inside a group, parallel across groups.
        {
            var h = Create(features);
            h.Redeem("a", "final"); await h.TickAsync(); await h.TickAsync(1);
            h.Redeem("b", "valor"); h.Redeem("c", "wisdom"); h.Redeem("d", "slow-mo"); h.Redeem("e", "fisheye");
            await h.TickAsync(1);
            check(h.IsActive("slow-mo") && h.IsActive("fisheye") && h.IsActive("final"), "groups: effects of different groups run at the same time");
            await h.TickAsync(45);
            check(h.Game.Get("player.form.id") == 1 && h.IsWaiting("c"), "fifo: the earlier redemption (Valor) starts first, Wisdom keeps waiting");
            check(h.Engine.PendingEffects.Single(p => p.RedemptionId == "c").Status.Length > 0, "fifo: the later one shows why it waits");
        }

        // Conflict setting: replace the running form, or refund the new one.
        {
            var h = Create(features, s => s.Conflict = ConflictBehavior.Replace);
            h.Redeem("a", "final"); await h.TickAsync(); await h.TickAsync(1);
            h.Redeem("b", "valor"); await h.TickAsync(1);
            check(h.Game.Get("player.form.id") == 1 && !h.IsActive("final") && h.Game.Count("drive.revert") == 0,
                "replace: Valor replaces Final at once without an extra revert");
            var r = Create(features, s => s.Conflict = ConflictBehavior.Refund);
            r.Redeem("a", "final"); await r.TickAsync(); await r.TickAsync(1);
            r.Redeem("b", "valor"); await r.TickAsync(1);
            check(r.Sink.IsRefunded("b") && r.IsActive("final"), "refund: a conflicting redemption is refunded and Final keeps running");
            var o = Create(features, s => { s.Conflict = ConflictBehavior.Refund; s.For("valor").Conflict = ConflictBehavior.Queue; });
            o.Redeem("a", "final"); await o.TickAsync(); await o.TickAsync(1);
            o.Redeem("b", "valor"); await o.TickAsync(1);
            check(o.IsWaiting("b"), "per-reward conflict setting overrides the global one");
        }

        // Same effect redeemed again: extend, refund or queue.
        {
            var h = Create(features);
            h.Redeem("a", "regen"); await h.TickAsync();
            h.Redeem("b", "regen"); await h.TickAsync(1);
            check(h.Engine.ActiveEffects.Single().DurationSeconds == 120 && h.Sink.IsFulfilled("a") && h.Sink.IsFulfilled("b"),
                "extend: a second Regeneration adds its 60 s and both viewers are charged");
            await h.TickAsync(70);
            check(h.IsActive("regen") && h.Game.Get("combat.autoheal") == 1, "extend: still running after the first 60 s");
            await h.TickAsync(51);
            check(!h.IsActive("regen") && h.Game.Get("combat.autoheal") == 0, "extend: ends after the combined time and restores");
            check(h.Engine.ActiveEffects.Count == 0 && h.Engine.RecentEvents.Any(e => e.Kind == EffectEventKind.Extended), "extend: recorded as an extension");

            var capped = Create(features, s => s.MaxDurationSeconds = 90);
            capped.Redeem("a", "regen"); await capped.TickAsync(); capped.Redeem("b", "regen"); capped.Redeem("c", "regen"); await capped.TickAsync(1);
            check(Math.Abs(capped.Engine.ActiveEffects.Single().RemainingSeconds - 90) < 0.01 && capped.Sink.IsFulfilled("b") && capped.Sink.IsRefunded("c"),
                "extend: capped by the maximum; an extension that adds nothing is refunded");
            await capped.TickAsync(50);
            capped.Redeem("d", "regen"); await capped.TickAsync(1);
            check(capped.Engine.ActiveEffects.Single().RemainingSeconds is > 85 and <= 90 && capped.Sink.IsFulfilled("d"),
                "extend: the cap limits the time left, so a later extension still adds time");

            var refund = Create(features, s => s.SameEffect = SameEffectBehavior.Refund);
            refund.Redeem("a", "regen"); await refund.TickAsync(); refund.Redeem("b", "regen"); await refund.TickAsync(1);
            check(refund.Sink.IsRefunded("b") && refund.Engine.ActiveEffects.Single().DurationSeconds == 60, "refund: a duplicate is refunded");

            var queue = Create(features, s => s.SameEffect = SameEffectBehavior.Queue);
            queue.Redeem("a", "regen"); await queue.TickAsync(); queue.Redeem("b", "regen"); await queue.TickAsync(1);
            check(queue.IsWaiting("b"), "queue: a duplicate waits");
            await queue.TickAsync(60);
            check(queue.IsActive("regen") && !queue.IsWaiting("b") && queue.Sink.IsFulfilled("b") && queue.Game.Get("combat.autoheal") == 1,
                "queue: the duplicate runs after the first one");

            var form = Create(features);
            form.Redeem("a", "final"); await form.TickAsync(); await form.TickAsync(1);
            form.Redeem("b", "final"); await form.TickAsync(1);
            check(form.Engine.ActiveEffects.Single().DurationSeconds == 90 && form.Game.Count("drive.trigger") == 1, "extend: the same form is extended, not re-triggered");
        }

        // Game readiness: wait for gameplay, pause timers, re-apply after a scene change, give up after the maximum wait.
        {
            var h = Create(features);
            h.Game.SceneReady = false;
            h.Redeem("a", "heal"); await h.TickAsync(1);
            check(h.IsWaiting("a") && h.Game.Count("player.heal") == 0, "readiness: waits during loading screens and menus");
            h.Game.SceneReady = true; await h.TickAsync(1);
            check(h.Sink.IsFulfilled("a") && h.Game.Get("player.hp") == 120, "readiness: runs once gameplay resumes");

            h.Redeem("b", "regen"); await h.TickAsync(1); await h.TickAsync(10);
            double before = h.Engine.ActiveEffects.Single().RemainingSeconds;
            h.Game.SceneReady = false; h.Game.Set("combat.autoheal", 0); // The scene change ended the toggle.
            await h.TickAsync(100);
            check(Math.Abs(h.Engine.ActiveEffects.Single().RemainingSeconds - before) < 0.01, "readiness: the timer pauses while the game is not ready");
            h.Game.SceneReady = true; await h.TickAsync(1);
            check(h.Game.Get("combat.autoheal") == 1, "readiness: values the scene change reset are applied again");

            var noPause = Create(features, s => s.PauseTimersWhileNotReady = false);
            noPause.Redeem("a", "regen"); await noPause.TickAsync();
            noPause.Game.IsConnected = false; await noPause.TickAsync(61);
            check(!noPause.IsActive("regen") && noPause.Sink.IsFulfilled("a"), "readiness: without pausing, an effect can expire while disconnected without errors");

            var wait = Create(features);
            wait.Game.IsConnected = false;
            wait.Redeem("a", "heal"); await wait.TickAsync(9 * 60, 30);
            check(wait.IsWaiting("a") && wait.Engine.PendingEffects.Single().Status.Contains("connect"), "readiness: explains that the trainer is not connected");
            await wait.TickAsync(2 * 60, 30);
            check(wait.Sink.IsRefunded("a") && !wait.IsWaiting("a"), "readiness: refunded after the maximum waiting time");

            var unsupported = Create(features);
            unsupported.Game.Unsupported.Add(new FeatureMap(features).Get("player.heal").CapabilitySlot);
            unsupported.Redeem("a", "heal"); await unsupported.TickAsync(1);
            check(unsupported.IsWaiting("a"), "readiness: waits while the bridge does not offer a feature");
        }

        // Effects that cannot do anything are refunded; failures restore what they changed.
        {
            var h = Create(features);
            h.Game.Set("player.hp", 120);
            h.Redeem("a", "heal"); await h.TickAsync();
            check(h.Sink.IsRefunded("a") && h.Sink.Refunded.Single().Reason.Contains("full HP"), "reject: Heal at full HP is refunded with a reason");
            h.Redeem("b", "revert"); await h.TickAsync();
            check(h.Sink.IsRefunded("b"), "reject: Revert without a Drive Form is refunded");
            h.Game.Reject = (feature, _) => feature == "player.hp";
            h.Redeem("c", "one-hp"); await h.TickAsync();
            check(h.IsWaiting("c") && h.Engine.PendingEffects.Single().Status.Contains("Trying again") && !h.Sink.IsRefunded("c"),
                "failure: a refused command is retried for a while (menus and transitions refuse briefly)");
            await h.TickAsync(61);
            check(h.Sink.IsRefunded("c") && !h.Sink.IsFulfilled("c"), "failure: a command the game keeps refusing refunds the viewer");
            h.Game.Reject = (feature, _) => feature == "movement.walk_speed";
            h.Redeem("d", "super-speed"); await h.TickAsync();
            check(h.IsWaiting("d") && h.Game.Get("movement.run_speed") == 8, "failure: a half-applied effect restores what it already changed");
            h.Game.Reject = null; await h.TickAsync(4);
            check(h.IsActive("super-speed") && h.Sink.IsFulfilled("d") && !h.Sink.IsRefunded("d"), "failure: the retry succeeds once the game allows it");
            await h.TickAsync(46);
            h.Redeem("e", "no-such-reward"); await h.TickAsync();
            check(h.Sink.IsRefunded("e"), "an unknown reward is refunded");
            h.Game.Set("player.drive.bars", 5);
            h.Redeem("f", "refill-drive"); await h.TickAsync();
            check(h.Sink.IsRefunded("f"), "reject: a full Drive gauge is refunded");
            h.Game.Set("player.drive.bars", 1); h.Game.Set("player.form.id", 2);
            h.Redeem("g", "refill-drive"); await h.TickAsync();
            check(h.IsWaiting("g"), "refill waits until the Drive Form ends");
            h.Game.Set("player.form.id", 0); await h.TickAsync(1);
            check(h.Sink.IsFulfilled("g") && h.Game.Get("player.drive.bars") == 5, "refill runs after the form");
        }

        // Drive Forms that fail to load are refunded; Revert interrupts a running form.
        {
            var h = Create(features);
            h.Game.FormsComplete = false;
            h.Redeem("a", "master"); await h.TickAsync(); await h.TickAsync(29);
            check(h.IsActive("master") && !h.Sink.IsFulfilled("a"), "form: waits for the transformation before charging");
            await h.TickAsync(2);
            check(h.Sink.IsRefunded("a") && !h.IsActive("master") && h.Game.Get("combat.formtimer") == 0, "form: refunded and restored when Sora never transforms");

            var failed = Create(features);
            failed.Game.FormResult = 7; failed.Game.DriveSteps = 1;
            failed.Redeem("a", "wisdom"); await failed.TickAsync(); await failed.TickAsync(3);
            check(failed.Sink.IsRefunded("a"), "form: a transformation the game rejected is refunded quickly");

            var revert = Create(features);
            revert.Redeem("a", "final"); await revert.TickAsync(); await revert.TickAsync(1);
            revert.Redeem("b", "revert"); await revert.TickAsync(1);
            check(!revert.IsActive("final") && revert.Game.Get("player.form.id") == 0 && revert.Sink.IsFulfilled("b") && revert.Game.Count("drive.revert") == 1,
                "interrupt: Revert ends the viewer's Final Form at once (one revert)");

            var early = Create(features);
            early.Redeem("a", "limit"); await early.TickAsync(); await early.TickAsync(1);
            early.Game.Set("player.form.id", 0); await early.TickAsync(1);
            check(!early.IsActive("limit") && early.Sink.IsFulfilled("a") && early.Game.Count("drive.revert") == 0, "form: ends without a revert when the game ended it");

            var roulette = Create(features);
            roulette.Redeem("a", "roulette"); await roulette.TickAsync(); await roulette.TickAsync(1);
            var active = roulette.Engine.ActiveEffects.Single();
            check(roulette.Game.Get("player.form.id") is >= 1 and <= 6 && active.Detail is { Length: > 0 }, "roulette: picks a form and names it");
        }

        // Ownership: values changed by someone else are respected.
        {
            var h = Create(features);
            h.Redeem("a", "slow-mo"); await h.TickAsync();
            h.Game.Set("time.multiplier", 0.8); // The streamer changed it in the trainer meanwhile.
            await h.TickAsync(3);
            check(h.Game.Get("time.multiplier") == 0.5, "sustain: the effect keeps its value while it runs");
            await h.TickAsync(30);
            check(h.Game.Get("time.multiplier") == 0.8, "restore: the newer outside value is restored, not the stale original");

            var camera = Create(features);
            camera.Redeem("a", "camera-glitch"); await camera.TickAsync();
            camera.Game.Set("camera.roll", 45);
            await camera.TickAsync(16);
            check(camera.Game.Count("camera.roll") == 1 && camera.Game.Get("camera.free") == 0, "restore: a value someone else changed is not overwritten");
        }

        // Inventory and munny effects.
        {
            var h = Create(features);
            h.Game.Stock[1] = 98; h.Game.Stock[2] = 0; h.Game.Stock[3] = 99;
            h.Redeem("a", "care-package"); await h.TickAsync();
            check(h.Game.Stock[1] == 99 && h.Game.Stock[2] == 2 && h.Game.Stock[3] == 99 && h.Sink.IsFulfilled("a"), "items: the care package fills up to 99");
            check(h.Engine.RecentEvents.First().Detail == "+1 Potion, +2 Hi-Potion", "items: viewers see what was actually added");
            h.Game.Stock[1] = 0; h.Game.Stock[2] = 0; h.Game.Stock[3] = 0;
            h.Redeem("b", "potion-thief"); await h.TickAsync();
            check(h.Sink.IsRefunded("b"), "items: the thief is refunded when there is nothing to steal");
            h.Game.Stock[1] = 2;
            h.Redeem("c", "potion-thief"); await h.TickAsync();
            check(h.Game.Stock[1] == 0 && h.Sink.IsFulfilled("c"), "items: the thief takes what is there");
            h.Redeem("d", "mystery-gift"); await h.TickAsync();
            check(h.Sink.IsFulfilled("d") && h.Engine.RecentEvents.First().Detail is { Length: > 0 }, "items: the mystery gift names the item");
            h.Redeem("e", "munny-gift"); await h.TickAsync();
            check(h.Game.Get("munny") == 2000, "munny: the gift adds the configured amount");
            h.Settings.For("pickpocket").Amount = 5000;
            h.Redeem("f", "pickpocket"); await h.TickAsync();
            check(h.Game.Get("munny") == 0 && h.Engine.RecentEvents.First().Detail is "-2,000 munny" or "-2.000 munny",
                "munny: the thief never goes below zero");
            h.Redeem("g", "pickpocket"); await h.TickAsync();
            check(h.Sink.IsRefunded("g"), "munny: nothing to steal is refunded");
        }

        // Enemy effects wait for a lock-on, Gummi effects only work in Gummi missions.
        {
            var h = Create(features);
            h.Redeem("a", "heal-enemy"); await h.TickAsync(1);
            check(h.IsWaiting("a"), "enemy: waits for a manual lock-on");
            h.Game.Set("target_lock_mode", 2); h.Game.Set("target_hp", 100); await h.TickAsync(1);
            check(h.Sink.IsFulfilled("a") && h.Game.Count("target_refill_hp") == 1, "enemy: runs once Sora locks on");
            h.Redeem("b", "gummi-repair"); await h.TickAsync();
            check(h.Sink.IsRefunded("b"), "gummi: refunded outside Gummi missions");
            var wait = Create(features);
            wait.Redeem("a", "enrage-enemy"); await wait.TickAsync(100, 10);
            check(wait.IsWaiting("a") && !wait.Sink.IsRefunded("a"), "enemy: keeps waiting within its waiting time");
            await wait.TickAsync(31, 10);
            check(wait.Sink.IsRefunded("a"), "enemy: uses its own shorter waiting time");
        }

        // Stopping everything restores values and refunds what never ran.
        {
            var h = Create(features);
            h.Game.DriveSteps = 5; // Final Form is still loading when everything stops.
            h.Redeem("a", "regen"); h.Redeem("b", "final"); await h.TickAsync();
            h.Game.SceneReady = false; h.Redeem("c", "heal"); await h.TickAsync(1);
            await h.Engine.StopAllAsync("Stopped by the streamer", h.Clock.Now);
            check(h.Engine.ActiveEffects.Count == 0 && h.Engine.PendingEffects.Count == 0, "stop: nothing runs or waits afterwards");
            check(h.Game.Get("combat.autoheal") == 0 && h.Sink.IsRefunded("c") && h.Sink.IsRefunded("b"), "stop: restores values and refunds unstarted redemptions");

            var cancel = Create(features);
            cancel.Game.SceneReady = false; cancel.Redeem("a", "heal"); await cancel.TickAsync(1);
            await cancel.Engine.CancelAsync("a", cancel.Clock.Now);
            check(cancel.Sink.IsRefunded("a") && cancel.Engine.PendingEffects.Count == 0, "cancel: the streamer can refund one waiting redemption");
            var end = Create(features);
            end.Redeem("a", "fisheye"); await end.TickAsync();
            await end.Engine.EndEffectAsync("fisheye", end.Clock.Now);
            check(!end.IsActive("fisheye") && end.Game.Get("camera.fov_enabled") == 0 && end.Sink.IsFulfilled("a"), "end: the streamer can end one effect early");
        }

        // The streamer's actions wait for a tick that is in the middle of a game command.
        {
            var h = Create(features);
            var hold = new TaskCompletionSource();
            h.Game.Hold = hold;
            h.Redeem("a", "slow-mo"); h.Redeem("b", "fisheye");
            var tick = h.TickAsync();
            var stop = h.Engine.StopAllAsync("Stopped by the streamer", h.Clock.Now);
            var skipped = h.Engine.TickAsync(h.Clock.Now);
            check(!stop.IsCompleted && skipped.IsCompleted, "concurrency: stopping waits for the running tick, a second tick is skipped");
            h.Game.Hold = null; hold.SetResult();
            await tick; await stop;
            var fulfilled = h.Sink.Fulfilled.Select(r => r.Id).ToHashSet();
            check(h.Engine.ActiveEffects.Count == 0 && h.Engine.PendingEffects.Count == 0 && !h.Sink.Refunded.Any(r => fulfilled.Contains(r.Redemption.Id)),
                "concurrency: nothing is both charged and refunded");
            check(h.Game.Get("time.multiplier") == 1 && h.Game.Get("camera.fov_enabled") == 0, "concurrency: effects started by that tick are undone");
        }

        // Drive switches take time in the bridge: the queued form waits for the revert instead of being refused.
        {
            var h = Create(features);
            h.Game.DriveSteps = 3;
            h.Redeem("a", "final"); await h.TickAsync(); await h.TickAsync(4);
            check(h.Game.Get("player.form.id") == 5 && h.Sink.IsFulfilled("a"), "handoff: Final Form establishes after its transformation");
            h.Redeem("b", "valor"); await h.TickAsync(46);
            check(h.Game.Get("drive.phase") is > 0 || h.Game.Calls("drive.trigger").Count() == 1, "handoff: Final is reverting");
            await h.TickAsync(10);
            check(h.Game.Get("player.form.id") == 1 && h.Sink.IsFulfilled("b") && h.Sink.Refunded.Count == 0,
                "handoff: Valor Form starts after Final's revert finished; nobody is refunded");

            var same = Create(features);
            same.Game.DriveSteps = 3; same.Game.Set("player.form.id", 1); // The streamer is already in Valor Form.
            same.Redeem("a", "valor"); await same.TickAsync(); await same.TickAsync(1);
            check(!same.Sink.IsFulfilled("a") && same.Engine.ActiveEffects.Single().Established == false, "same form: not counted while the bridge re-enters the form");
            await same.TickAsync(4);
            check(same.Sink.IsFulfilled("a"), "same form: counted once the switch finished");
            await same.TickAsync(30);
            check(same.IsActive("valor"), "same form: the reward's full time is kept");

            var loading = Create(features);
            loading.Game.DriveSteps = 5;
            loading.Redeem("a", "final"); await loading.TickAsync(); await loading.TickAsync(1);
            loading.Redeem("b", "revert"); await loading.TickAsync(1);
            check(loading.IsWaiting("b") && loading.Engine.PendingEffects.Single().Status.Contains("finish starting"), "interrupt: Kick Out waits while the form is still loading");
            await loading.TickAsync(6);
            check(loading.Sink.IsFulfilled("a") && loading.Sink.IsFulfilled("b") && !loading.IsActive("final") && loading.Game.Count("drive.revert") == 1,
                "interrupt: Kick Out reverts once the form has loaded; both viewers got what they paid for");

            var fifo = Create(features);
            fifo.Redeem("a", "final"); await fifo.TickAsync(); await fifo.TickAsync(1);
            fifo.Redeem("b", "valor"); fifo.Redeem("c", "revert"); await fifo.TickAsync(1);
            check(fifo.Sink.IsFulfilled("c") && !fifo.IsActive("final") && fifo.Game.Count("drive.revert") == 1, "interrupt: Kick Out acts at once instead of waiting behind a queued form");
            await fifo.TickAsync(1);
            check(fifo.Game.Get("player.form.id") == 1, "interrupt: the queued Valor Form follows");

            var refused = Create(features);
            refused.Redeem("a", "final"); await refused.TickAsync(); await refused.TickAsync(1);
            refused.Game.Reject = (feature, _) => feature == "drive.revert";
            refused.Redeem("b", "revert"); await refused.TickAsync(1);
            check(refused.IsWaiting("b") && refused.IsActive("final") && refused.Game.Get("combat.formtimer") == 1,
                "interrupt: a refused revert is retried and the viewer's Final Form keeps running meanwhile");
            refused.Game.Reject = null; await refused.TickAsync(4);
            check(refused.Sink.IsFulfilled("b") && !refused.IsActive("final") && refused.Game.Get("player.form.id") == 0, "interrupt: the retry kicks Sora out");
            refused.Redeem("c", "final"); await refused.TickAsync(1);
            refused.Game.Reject = (feature, _) => feature == "drive.revert";
            refused.Redeem("d", "revert"); await refused.TickAsync(62);
            check(refused.Sink.IsRefunded("d") && !refused.Sink.IsFulfilled("d"), "interrupt: Kick Out is refunded when the game keeps refusing the revert");
            refused.Game.Reject = null;

            var twice = Create(features);
            twice.Game.DriveSteps = 2;
            twice.Redeem("a", "final"); await twice.TickAsync(); await twice.TickAsync(3);
            twice.Redeem("b", "valor"); twice.Redeem("c", "revert"); twice.Redeem("d", "revert"); await twice.TickAsync(1);
            check(twice.Sink.IsFulfilled("c") && twice.Sink.IsRefunded("d") && twice.Sink.Refunded.Single(r => r.Redemption.Id == "d").Reason.Contains("already leaving"),
                "interrupt: a second Kick Out while Sora is already leaving the form is refunded");
            await twice.TickAsync(8);
            check(twice.IsActive("valor") && twice.Sink.IsFulfilled("b") && !twice.Sink.IsRefunded("b"), "interrupt: it does not kick the next viewer's form instead");

            var native = Create(features);
            native.Game.Set("player.form.id", 6); // The streamer is in Antiform on their own.
            native.Game.Reject = (feature, _) => feature == "drive.trigger";
            native.Redeem("a", "valor"); await native.TickAsync(); await native.TickAsync(10);
            check(native.Game.Count("combat.formtimer") == 0 && native.IsWaiting("a"), "form: a refused switch from another form never refills that form's timer");
            native.Game.Reject = null; await native.TickAsync(4);
            check(native.Game.Get("player.form.id") == 1 && native.Game.Get("combat.formtimer") == 1, "form: the hold is set once the switch was accepted");

            var end = Create(features);
            end.Game.DriveSteps = 5;
            end.Redeem("a", "master"); await end.TickAsync(); await end.TickAsync(1);
            await end.Engine.EndEffectAsync("master", end.Clock.Now);
            check(end.Sink.IsRefunded("a") && end.Game.Count("drive.cancel") == 1 && end.Game.Get("combat.formtimer") == 0,
                "end: ending a form that is still loading refunds the viewer and cancels the switch");

            var replace = Create(features, s => s.Conflict = ConflictBehavior.Replace);
            replace.Game.DriveSteps = 5;
            replace.Redeem("a", "final"); await replace.TickAsync(); await replace.TickAsync(1);
            replace.Redeem("b", "valor"); await replace.TickAsync(1);
            check(replace.IsWaiting("b") && replace.IsActive("final"), "replace: a form that is still loading is not replaced");
            await replace.TickAsync(12);
            check(replace.Sink.IsFulfilled("a") && replace.Sink.IsFulfilled("b") && replace.Game.Get("player.form.id") == 1, "replace: it is replaced once it has loaded");
        }

        // Restores the game refused are retried, and the group waits for them.
        {
            var h = Create(features);
            h.Redeem("a", "snail"); await h.TickAsync();
            h.Game.Reject = (feature, args) => feature == "movement.run_speed" && args[0] == 8;
            await h.TickAsync(31);
            check(!h.IsActive("snail") && h.Game.Get("movement.run_speed") == 2 && h.Game.Get("movement.walk_speed") == 2, "restore: a refused restore leaves the value for now");
            h.Redeem("b", "super-speed"); await h.TickAsync(1);
            check(h.IsWaiting("b") && h.Engine.PendingEffects.Single().Status.Contains("undone"), "restore: the next effect of the group waits for it");
            h.Game.Reject = null; await h.TickAsync(2);
            check(h.Game.Get("movement.run_speed") == 20 && h.Sink.IsFulfilled("b"), "restore: retried, then the next effect starts from the real original");
            await h.TickAsync(46);
            check(h.Game.Get("movement.run_speed") == 8, "restore: everything is back to normal");

            var giveUp = Create(features);
            giveUp.Redeem("a", "glass-cannon"); await giveUp.TickAsync();
            giveUp.Game.Reject = (feature, _) => feature == "damage.player.general";
            await giveUp.TickAsync(31); await giveUp.TickAsync(181, 10);
            giveUp.Game.Reject = null;
            giveUp.Redeem("b", "invincible"); await giveUp.TickAsync(1);
            check(giveUp.Game.Get("damage.player.general") == 250 && giveUp.Sink.IsFulfilled("b"), "restore: gives up after a few minutes and stops blocking the group");
        }

        // The trainer's field freeze holds the game: other effects wait for it instead of failing.
        {
            var stuck = Create(features);
            stuck.Redeem("a", "freeze-frame"); await stuck.TickAsync();
            stuck.Game.Reject = (feature, args) => feature == "practice.field_pause" && args[0] == 0;
            await stuck.TickAsync(6);
            check(stuck.Game.Get("practice.field_pause") == 1, "freeze: a refused release leaves the game frozen for now");
            stuck.Game.Reject = null; await stuck.TickAsync(2);
            check(stuck.Game.Get("practice.field_pause") == 0, "freeze: the release is retried while the game is still frozen");

            var h = Create(features);
            h.Redeem("a", "freeze-frame"); await h.TickAsync();
            h.Redeem("b", "heal"); await h.TickAsync(1);
            check(h.IsWaiting("b") && h.Engine.PendingEffects.Single().Status.Contains("frozen"), "freeze: redemptions wait during Freeze Frame");
            await h.TickAsync(5);
            check(h.Sink.IsFulfilled("b") && h.Game.Get("practice.field_pause") == 0, "freeze: they run when it ends");
        }

        // Redemptions that would change nothing are refunded; One HP Left waits for Regeneration.
        {
            var h = Create(features);
            h.Game.Set("combat.autoheal", 1); // The streamer's own setting.
            h.Redeem("a", "regen"); await h.TickAsync();
            check(h.Sink.IsRefunded("a") && h.Sink.Refunded.Single().Reason.Contains("already active"), "values: refunded when it is already on");
            h.Redeem("b", "one-hp"); await h.TickAsync(1);
            check(h.IsWaiting("b") && h.Engine.PendingEffects.Single().Status.Contains("Regeneration"), "one hp: waits while HP refills by itself");
            h.Game.Set("combat.autoheal", 0); await h.TickAsync(1);
            check(h.Sink.IsFulfilled("b") && h.Game.Get("player.hp") == 1, "one hp: runs afterwards");
        }

        // Déjà Vu charges only when the pull back worked.
        {
            var h = Create(features);
            h.Redeem("a", "deja-vu"); await h.TickAsync(); await h.TickAsync(1);
            check(h.IsActive("deja-vu") && !h.Sink.IsFulfilled("a"), "deja vu: not charged before the pull back");
            await h.TickAsync(10);
            check(h.Sink.IsFulfilled("a") && h.Game.Count("player.position.return") == 1, "deja vu: charged after it pulled Sora back");
            h.Redeem("b", "deja-vu"); await h.TickAsync();
            h.Game.Reject = (feature, _) => feature == "player.position.return";
            await h.TickAsync(11);
            check(h.Sink.IsRefunded("b") && !h.Sink.IsFulfilled("b"), "deja vu: refunded when the pull back was not possible");
        }

        // A local test run behaves exactly like a redemption.
        {
            var h = Create(features);
            h.Engine.Submit(new Redemption("t", "flashbang", "Test", "", h.Clock.Now, IsTest: true));
            await h.TickAsync();
            check(h.IsActive("flashbang") && h.Game.Get("display.brightness_preview") == 50, "test runs start the effect");
            await h.TickAsync(9);
            check(h.Game.Get("display.brightness_preview") == 0 && h.Game.Count("display.restore_loaded") == 1, "test runs restore the display settings");
        }
    }
}
