using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class DriveRevertOwnershipTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game;
        public readonly FakeSink Sink = new();
        public readonly TwitchSettings Settings = new();
        public readonly EffectEngine Engine;
        public DateTimeOffset Now = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
        public Harness(IReadOnlyList<FeatureDefinition> features)
        {
            Game = new(features);
            Engine = new(Game, new(features), EffectCatalog.All,
                key => RewardResolver.Options(EffectCatalog.Find(key)!, Settings), () => RewardResolver.Engine(Settings),
                Sink, _ => { }, _ => Task.CompletedTask, new Random(3));
        }
        public void Redeem(string key = "final", string id = "a") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public async Task Tick(double seconds = .25) { Now = Now.AddSeconds(seconds); Game.Pump(); await Engine.TickAsync(Now); }
        public async Task Start(string key = "final") { Redeem(key); await Tick(); await Tick(); }
        public Task End(string key = "final") => Engine.EndEffectAsync(key, Now);
        public double Remaining => Engine.ActiveEffects.Single().RemainingSeconds;
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        DecoderChecks(check);
        foreach (string key in new[] { "valor", "wisdom", "limit", "master", "final", "antiform", "roulette" })
        {
            var h = new Harness(features); await h.Start(key);
            check(h.Sink.IsFulfilled("a") && h.Game.DriveRevertLock.Effective && h.Game.RevertLockOwner != 0, $"Revert lock: {key} establishes a native owner before charging");
            check(h.Game.Commands[0].Feature == "drive.revert_lock" && h.Game.Commands[0].Arguments[0] == 1 &&
                h.Game.Commands.FindIndex(c => c.Feature == "drive.trigger") > 0, $"Revert lock: {key} acquires before the timer and transition");
            check(!h.Game.TryVoluntaryRevert() && h.Game.Get("player.form.id") is > 0, $"Revert lock: {key} blocks the fixture's voluntary command");
            var args = h.Game.Calls("drive.revert_lock").Single();
            check(args.Length == 5 && args.All(v => double.IsFinite(v) && v >= 0 && v <= uint.MaxValue && v == Math.Truncate(v)) &&
                ((uint)args[3] | ((ulong)(uint)args[4] << 32)) == h.Game.RevertLockBridge, $"Revert lock: {key} uses exact split UInt64 command arguments");
            await h.End(key);
            check(h.Game.RevertLockOwner == 0 && h.Engine.PendingCleanupCount == 0 && h.Game.Count("drive.revert") == 1 &&
                h.Game.Get("combat.formtimer") == 0, $"Revert lock: {key} releases and directly reverts on streamer stop");
        }
        {
            var h = new Harness(features); h.Settings.For("final").DurationSeconds = 1; await h.Start();
            for (int i = 0; i < 5; i++) await h.Tick();
            check(h.Engine.ActiveEffects.Count == 0 && h.Game.RevertLockOwner == 0 && h.Game.Count("drive.revert") == 1,
                "Revert lock: expiry releases before one direct revert");
        }
        {
            var h = new Harness(features); await h.Start(); ulong owner = h.Game.RevertLockOwner;
            h.Redeem("final", "b"); await h.Tick();
            check(h.Game.RevertLockOwner == owner && h.Game.Calls("drive.revert_lock").Count(a => a[0] == 1) == 1 && h.Sink.IsFulfilled("b"),
                "Revert lock: extension reuses the original owner without reacquiring");
            h.Redeem("valor", "c"); await h.Tick();
            check(h.Engine.PendingEffects.Count == 1 && h.Game.RevertLockOwner == owner, "Revert lock: queued form leaves the running owner alone");
            await h.Engine.CancelAsync("c", h.Now);
            check(h.Sink.IsRefunded("c") && h.Game.RevertLockOwner == owner, "Revert lock: cancelling a queued redemption cannot release the running owner");
        }
        {
            var h = new Harness(features); h.Settings.Conflict = ConflictBehavior.Replace; await h.Start(); ulong owner = h.Game.RevertLockOwner;
            h.Redeem("valor", "b"); await h.Tick(); await h.Tick();
            var commands = h.Game.Calls("drive.revert_lock").ToArray();
            check(h.Sink.IsFulfilled("b") && h.Game.Get("player.form.id") == 1 && h.Game.RevertLockOwner != owner &&
                commands.Select(a => a[0]).SequenceEqual([1.0, 0.0, 1.0]) && h.Game.Count("drive.revert") == 0,
                "Revert lock: replacement admits only the releasing owner and acquires a new token after release");
        }
        {
            var h = new Harness(features); h.Settings.Conflict = ConflictBehavior.Replace; await h.Start();
            h.Game.Reject = (id, a) => id == "drive.revert_lock" && a[0] == 0;
            h.Redeem("valor", "b"); await h.Tick();
            check(h.Engine.PendingEffects.Any(p => p.RedemptionId == "b") && h.Game.Count("drive.trigger") == 1 && h.Engine.PendingCleanupCount == 1,
                "Revert lock: replacement waits for unresolved release, with no new trigger");
            h.Game.Reject = null; await h.Tick(1); await h.Tick();
            check(h.Sink.IsFulfilled("b") && h.Game.Count("drive.trigger") == 2, "Revert lock: replacement resumes after acknowledged cleanup");
        }
        {
            var h = new Harness(features); await h.Start(); ulong owner = h.Game.RevertLockOwner;
            h.Game.Reject = (id, _) => id == "drive.revert";
            h.Redeem("revert", "b"); await h.Tick();
            check(h.Game.RevertLockOwner == owner && h.Engine.ActiveEffects.Any(e => e.Key == "final") &&
                !h.Game.Calls("drive.revert_lock").Any(a => a[0] == 0), "Revert lock: rejected Kick Out retains the running reward and lock");
            h.Game.Reject = null; await h.Tick(3.1);
            check(h.Game.RevertLockOwner == 0 && h.Sink.IsFulfilled("b") && h.Engine.ActiveEffects.Count == 0,
                "Revert lock: accepted Kick Out bypasses voluntary lock and then releases it");
        }
        foreach (var blockers in new[] { GameplayBlockers.Menu, GameplayBlockers.Loading, GameplayBlockers.NoPlayer, GameplayBlockers.TrainerFieldPause })
        {
            var h = new Harness(features); await h.Start();
            h.Game.Gameplay = new(true, PlayerRole.Sora, blockers); h.Game.SceneReady = blockers != GameplayBlockers.Loading;
            await h.End();
            check(h.Game.RevertLockOwner == 0 && h.Game.Count("drive.revert") == 0 && h.Engine.ActiveEffects.Count == 0,
                $"Revert lock: {blockers} does not delay owner release or permit an actor action");
            h.Game.SceneReady = true; h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); await h.Tick(1);
            check(h.Game.Count("drive.revert") == 1 && h.Engine.PendingCleanupCount == 0, $"Revert lock: {blockers} deferred form cleanup completes later");
        }
        {
            var h = new Harness(features); h.Game.DriveSteps = 5; h.Redeem(); await h.Tick();
            h.Game.SceneReady = false; h.Game.Reject = (id, _) => id == "drive.cancel";
            await h.End();
            check(h.Game.RevertLockOwner == 0 && h.Sink.IsRefunded("a") && h.Engine.PendingCleanupCount == 1,
                "Revert lock: failed pending-Drive cancellation cannot block owner release or the unestablished refund");
            h.Game.Reject = null; await h.Tick(1); h.Game.SceneReady = true; await h.Tick(1);
            check(h.Game.Count("drive.revert") == 0 && h.Game.Get("combat.formtimer") == 0 && h.Engine.PendingCleanupCount == 0,
                "Revert lock: cancelled transition cleans up without a late revert");
        }
        foreach (string rejected in new[] { "drive.revert_lock", "combat.formtimer", "drive.trigger" })
        {
            var h = new Harness(features); h.Game.Reject = (id, a) => id == rejected && (id != "drive.revert_lock" || a[0] == 1);
            h.Redeem(); await h.Tick();
            check(h.Game.RevertLockOwner == 0 && h.Engine.ActiveEffects.Count == 0 && !h.Sink.IsFulfilled("a") && h.Engine.PendingCleanupCount == 0,
                $"Revert lock: start failure at {rejected} releases intent without charging");
        }
        {
            var h = new Harness(features); h.Game.RevertLockAcceptWithoutApplying = true; h.Redeem(); await h.Tick();
            check(h.Game.Count("drive.trigger") == 0 && !h.Sink.IsFulfilled("a") && h.Engine.PendingCleanupCount == 0,
                "Revert lock: Acquire ACK without an effective own readback never triggers or charges a form");
        }
        {
            var h = new Harness(features); h.Game.RevertLockLoseNextAck = true; h.Redeem(); await h.Tick();
            check(h.Game.RevertLockOwner == 0 && h.Game.Count("drive.trigger") == 0 && h.Engine.PendingCleanupCount == 0,
                "Revert lock: applied Acquire with lost ACK is released by start-error cleanup");
        }
        {
            var h = new Harness(features); h.Game.RevertLockQueueWithoutAck = true; h.Redeem(); await h.Tick();
            check(h.Engine.PendingCleanupCount == 1 && h.Game.Count("drive.trigger") == 0, "Revert lock: unknown queued Acquire preserves cleanup intent");
            await h.Engine.StopAllAsync("fixture shutdown", h.Now); await h.Tick(4);
            check(h.Sink.IsRefunded("a") && h.Engine.PendingCleanupCount == 1 && h.Game.Calls("drive.revert_lock").Count(a => a[0] == 1) == 1,
                "Revert lock: stopping a queued Acquire never rearms or starts a form");
            h.Game.CompleteQueuedRevertLock(); await h.Tick(1);
            check(h.Game.RevertLockOwner == 0 && h.Engine.PendingCleanupCount == 0, "Revert lock: late original Acquire is released once transport can acknowledge it");
        }
        {
            var h = new Harness(features); await h.Start(); h.Game.RevertLockReleasePending = true; await h.End();
            check(h.Game.RevertLockState == 2 && h.Engine.PendingCleanupCount == 1 && h.Game.Count("drive.revert") == 0,
                "Revert lock: release ACK with state2 retains cleanup intent and delays the direct revert");
            h.Game.RevertLockReleasePending = false; await h.Tick(1);
            check(h.Game.RevertLockOwner == 0 && h.Engine.PendingCleanupCount == 0, "Revert lock: state2 cleanup is retried to confirmed release");
        }
        {
            var h = new Harness(features); await h.Start(); h.Game.RevertLockLoseNextAck = true;
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); await h.End();
            check(h.Game.RevertLockOwner == 0 && h.Engine.PendingCleanupCount == 1, "Revert lock: lost release ACK while paused retains the pending end");
            await h.Tick(1); int releaseCount = h.Game.Calls("drive.revert_lock").Count(a => a[0] == 0);
            await h.Tick(1);
            check(releaseCount == 2 && h.Game.Calls("drive.revert_lock").Count(a => a[0] == 0) == releaseCount,
                "Revert lock: idempotent retry settles lost release ACK while player control remains absent");
        }
        {
            var h = new Harness(features); await h.Start(); double remaining = h.Remaining;
            h.Settings.PauseTimersWhileNotReady = false; h.Game.RevertLockSnapshotAvailable = false;
            await h.Tick(); await h.Tick(); h.Redeem("final", "b"); await h.Tick();
            check(h.Remaining == remaining && h.Engine.ActiveEffects.Single().Paused && !h.Sink.IsFulfilled("b"),
                "Revert lock: unavailable ownership pauses time and extensions even with pause preference disabled");
            h.Game.RevertLockSnapshotAvailable = true; await h.Tick();
            check(h.Game.Calls("drive.revert_lock").Count(a => a[0] == 1) == 1 && h.Sink.IsFulfilled("b"),
                "Revert lock: a fresh own observation resumes without reacquiring");
        }
        foreach (int state in new[] { 0, 1, 2 })
        {
            var h = new Harness(features); await h.Start();
            ulong foreign = state == 0 ? 0UL : 0x1234567887654321UL;
            h.Game.RevertLockState = state; h.Game.RevertLockOwner = foreign;
            await h.Tick();
            check(h.Engine.ActiveEffects.Count == 0 && h.Game.RevertLockOwner == foreign && h.Game.Count("drive.revert") == 0 &&
                h.Game.Calls("drive.revert_lock").Count(a => a[0] == 1) == 1,
                $"Revert lock: fresh lost ownership in state{state} reaches the loss monitor without overwriting or reverting a foreign form");
            check(h.Game.Get("combat.formtimer") == (state == 0 ? 0 : 1),
                $"Revert lock: state{state} distinguishes ordinary lost owner zero from proven foreign timer ownership");
        }
        {
            var h = new Harness(features); await h.Start(); h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu);
            h.Game.RevertLockOwner = 77; await h.Tick();
            check(h.Engine.ActiveEffects.Count == 0 && h.Engine.PendingCleanupCount == 1 && h.Game.RevertLockOwner == 77 && h.Game.Count("drive.revert") == 0,
                "Revert lock: loss monitor runs before player-control and usability gates, preserving the foreign owner");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); await h.Tick(1);
            check(h.Engine.PendingCleanupCount == 0 && h.Game.Count("drive.revert") == 0,
                "Revert lock: loss cleanup cannot later revert the foreign form when control returns");
        }
        {
            var h = new Harness(features);
            h.Game.AfterExecute = (id, _) => { if (id == "drive.trigger") h.Game.RevertLockSnapshotAvailable = false; };
            h.Redeem(); await h.Tick(); await h.Tick();
            check(h.Game.Get("player.form.id") == 5 && !h.Sink.IsFulfilled("a") && !h.Engine.ActiveEffects.Single().Established,
                "Revert lock: desired form without current owned-lock observation cannot establish or settle");
            h.Game.RevertLockSnapshotAvailable = true; await h.Tick();
            check(h.Sink.IsFulfilled("a"), "Revert lock: desired form and confirmed own lock together establish the reward");
        }
        {
            var h = new Harness(features); await h.Start();
            h.Game.Reject = (id, a) => id == "drive.revert_lock" && a[0] == 0; await h.End();
            for (int i = 0; i < 190; i++) await h.Tick(1);
            check(h.Engine.PendingCleanupCount == 1 && h.Game.RevertLockOwner != 0 && h.Game.Count("drive.revert") == 0,
                "Revert lock: cleanup survives over three minutes of observed controllable time and does not revert prematurely");
            h.Game.Reject = null; await h.Tick(1);
            check(h.Engine.PendingCleanupCount == 0 && h.Game.RevertLockOwner == 0 && h.Game.Count("drive.revert") == 1,
                "Revert lock: a later successful release completes the deferred end");
        }
        {
            var h = new Harness(features); h.Game.BeforeRevertLockDispatch = a => { if (a[0] == 1) h.Game.RevertLockBridge++; };
            h.Redeem(); await h.Tick();
            check(h.Game.Count("drive.trigger") == 0 && h.Game.RevertLockOwner == 0 && h.Engine.PendingCleanupCount == 0,
                "Revert lock: bridge replacement during Acquire rejects the old nonce without targeting the replacement");
        }
        {
            var h = new Harness(features); h.Game.DriveSteps = 5; h.Redeem(); await h.Tick();
            h.Game.RevertLockState = 0; h.Game.RevertLockOwner = 0; await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.Count("drive.cancel") == 1 && h.Game.Count("drive.revert") == 0,
                "Revert lock: loss before form establishment cancels queued work and refunds");
        }
        {
            var h = new Harness(features); await h.Start(); h.Game.Set("player.form.id", 0); await h.Tick();
            check(h.Game.RevertLockOwner == 0 && h.Engine.ActiveEffects.Count == 0 && h.Game.Count("drive.revert") == 0,
                "Revert lock: a game-ended form releases the owner without issuing another revert");
        }
        {
            var h = new Harness(features); await h.Start(); h.Game.IsConnected = false;
            await h.Engine.StopAllAsync("fixture game disconnected", h.Now); await h.Tick(240);
            check(h.Engine.PendingCleanupCount == 1, "Revert lock: disconnect does not prove owner cleanup or permit abandonment");
            h.Game.RevertLockBridge++; h.Game.RevertLockOwner = 0x1111222233334444; h.Game.IsConnected = true;
            h.Game.RevertLockSnapshotAvailable = false; h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); await h.Tick(1);
            check(h.Engine.PendingCleanupCount == 1, "Revert lock: unreadable replacement bridge cannot retire old intent");
            int commands = h.Game.Count("drive.revert_lock"); h.Game.RevertLockSnapshotAvailable = true; await h.Tick(1);
            check(h.Game.RevertLockOwner == 0x1111222233334444 && h.Game.Count("drive.revert_lock") == commands,
                "Revert lock: fresh different bridge retires old lock intent without sending a command to its new owner");
        }
        foreach (bool releaseConfirmed in new[] { false, true })
        foreach (bool newBridge in new[] { false, true })
        {
            var h = new Harness(features); await h.Start();
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu);
            if (!releaseConfirmed) h.Game.Reject = (id, a) => id == "drive.revert_lock" && a[0] == 0;
            await h.End();
            if (newBridge) h.Game.RevertLockBridge++;
            h.Game.RevertLockOwner = newBridge ? 0UL : 0x1111222233334444UL;
            h.Game.RevertLockState = newBridge ? 0 : 1;
            h.Game.Reject = null;
            int timerCommands = h.Game.Count("combat.formtimer");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None);
            await h.Tick(1);
            check(h.Game.Count("drive.revert") == 0 && h.Game.Get("player.form.id") == 5 &&
                h.Game.RevertLockOwner == (newBridge ? 0UL : 0x1111222233334444UL) && h.Engine.PendingCleanupCount == 0,
                $"Revert lock: deferred end after releaseConfirmed={releaseConfirmed} preserves same-ID form under newBridge={newBridge} or foreign owner when control returns");
            check(h.Game.Get("combat.formtimer") == 1 && h.Game.Count("combat.formtimer") == timerCommands,
                $"Revert lock: deferred foreign identity preserves timer hold without commands after control returns (releaseConfirmed={releaseConfirmed}, newBridge={newBridge})");
        }
        foreach (bool takeoverDuringRelease in new[] { false, true })
        {
            var h = new Harness(features); await h.Start();
            if (takeoverDuringRelease)
                h.Game.AfterExecute = (id, a) => { if (id == "drive.revert_lock" && a[0] == 0) { h.Game.RevertLockOwner = 77; h.Game.RevertLockState = 1; } };
            else { h.Game.RevertLockOwner = 77; h.Game.RevertLockState = 1; }
            int timerCommands = h.Game.Count("combat.formtimer");
            await h.End();
            check(h.Game.Count("drive.revert") == 0 && h.Game.Get("player.form.id") == 5 && h.Game.RevertLockOwner == 77 && h.Engine.PendingCleanupCount == 0,
                $"Revert lock: foreign owner observed {(takeoverDuringRelease ? "after" : "before")} release prevents a direct revert");
            check(h.Game.Get("combat.formtimer") == 1 && h.Game.Count("combat.formtimer") == timerCommands,
                $"Revert lock: foreign owner observed {(takeoverDuringRelease ? "after" : "before")} release preserves the newer timer hold");
        }
        foreach (int slot in Enumerable.Range(488, 5))
        {
            var h = new Harness(features); h.Game.Unsupported.Add(slot); h.Redeem(); await h.Tick();
            check(h.Game.Commands.Count == 0 && h.Engine.PendingEffects.Count == 1 && !h.Sink.IsFulfilled("a"),
                $"Revert lock: missing capability{slot} waits before any form side effect");
        }
        {
            var h = new Harness(features); h.Game.RevertLockOwner = 77; h.Game.RevertLockState = 1; h.Redeem(); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.Commands.Count == 0 && h.Game.RevertLockOwner == 77, "Revert lock: foreign preexisting owner rejects the reward unchanged");
        }
        {
            var h = new Harness(features); h.Game.Set("player.form.id", 5); h.Redeem("revert"); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.Count("drive.revert_lock") == 0 && h.Game.Get("player.form.id") == 0,
                "Revert lock: standalone Kick Out and manually entered forms need no Twitch lock");
        }
    }

    private static void DecoderChecks(Action<bool, string> check)
    {
        static void Set(TrainerSnapshot s, int slot, double value)
        { s.Values[slot] = value; s.Valid[slot / 64] |= 1UL << (slot % 64); s.Supported[slot / 64] |= 1UL << (slot % 64); }
        static TrainerSnapshot Fresh()
        {
            var s = new TrainerSnapshot { ProtocolVersion = 4, Connected = true, Status = 1, SceneReady = false };
            Set(s, 463, 100); Set(s, 488, 1); Set(s, 489, 0xFEDCBA98); Set(s, 490, 0x87654321); Set(s, 491, 0x12345678); Set(s, 492, 0xABCDEF01);
            return s;
        }
        var parsed = DriveRevertLockSnapshot.FromSnapshot(Fresh(), 101);
        check(parsed.Available && parsed.Effective && parsed.Owner == 0x87654321FEDCBA98 && parsed.BridgeInstance == 0xABCDEF0112345678,
            "Revert decoder: exact high-bit identities with no scene or actor-hook dependency");
        foreach (int slot in new[] { 463, 488, 489, 490, 491, 492 })
        {
            var s = Fresh(); s.Valid[slot / 64] &= ~(1UL << (slot % 64));
            check(!DriveRevertLockSnapshot.FromSnapshot(s, 101).Available, $"Revert decoder: missing value{slot} unavailable");
            s = Fresh(); s.Supported[slot / 64] &= ~(1UL << (slot % 64));
            check(!DriveRevertLockSnapshot.FromSnapshot(s, 101).Available, $"Revert decoder: missing capability{slot} unavailable");
            foreach (double invalid in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity, -.1, .5, (double)uint.MaxValue + 1 })
            {
                s = Fresh(); Set(s, slot, invalid);
                check(!DriveRevertLockSnapshot.FromSnapshot(s, 101).Available, $"Revert decoder: invalid slot{slot} value{invalid} rejected");
            }
        }
        foreach (int state in new[] { 0, 1, 2, 3 })
        foreach (bool owner in new[] { false, true })
        {
            var s = Fresh(); Set(s, 488, state); Set(s, 489, owner ? 1 : 0); Set(s, 490, 0);
            parsed = DriveRevertLockSnapshot.FromSnapshot(s, 101);
            bool valid = state <= 2 && ((state != 0) == owner);
            check(parsed.Available == valid && (!valid || parsed.Effective == (state == 1) && parsed.CleanupPending == (state == 2)),
                $"Revert decoder: state{state}/owner{owner} consistency");
        }
        foreach (var s in new[] { Fresh() with { ProtocolVersion = 3 }, Fresh() with { Connected = false }, Fresh() with { Status = 0 }, Fresh() with { ErrorCode = 1 } })
            check(!DriveRevertLockSnapshot.FromSnapshot(s, 101).Available, "Revert decoder: disconnected, errored or incompatible publication unavailable");
        var zero = Fresh(); Set(zero, 491, 0); Set(zero, 492, 0);
        check(!DriveRevertLockSnapshot.FromSnapshot(zero, 101).Available, "Revert decoder: zero bridge identity rejected");
        check(!DriveRevertLockSnapshot.FromSnapshot(Fresh(), 1101).Available && !DriveRevertLockSnapshot.FromSnapshot(Fresh(), 99).Available,
            "Revert decoder: stale or future publication rejected");
        var wrapped = Fresh(); Set(wrapped, 463, uint.MaxValue - 20);
        check(DriveRevertLockSnapshot.FromSnapshot(wrapped, 20).Available, "Revert decoder: shared uptime wrap is accepted");
    }
}
