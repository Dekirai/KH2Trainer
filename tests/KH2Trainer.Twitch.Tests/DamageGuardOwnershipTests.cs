using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class DamageGuardOwnershipTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game;
        public readonly FakeSink Sink = new();
        public readonly EffectEngine Engine;
        public DateTimeOffset Now = new(2026, 10, 7, 12, 0, 0, TimeSpan.Zero);
        public bool PauseTimers = true;
        public double MaxWaitSeconds = 600;
        public Harness(IReadOnlyList<FeatureDefinition> features, PlayerRole role = PlayerRole.Sora)
        {
            Game = new(features) { Gameplay = new(true, role, GameplayBlockers.None) };
            Engine = new(Game, new(features), EffectCatalog.All,
                key => { var d = EffectCatalog.Find(key)!; return new(d.Title, d.DurationSeconds, d.Amount, SameEffectBehavior.Extend, ConflictBehavior.Queue); },
                () => new(TimeSpan.FromSeconds(MaxWaitSeconds), 600, PauseTimers), Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Redeem(string id = "a") => Engine.Submit(new(id, "invincible", "Viewer", "", Now));
        public Task Tick(double elapsed = .25) { Now = Now.AddSeconds(elapsed); return Engine.TickAsync(Now); }
        public Task End() => Engine.EndEffectAsync("invincible", Now);
        public double Remaining => Engine.ActiveEffects.Single().RemainingSeconds;
        public void Switch(PlayerRole role) => Game.SwitchMovementActor(role, Game.Movement.Values, retireOld: true);
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        DecoderChecks(check);
        foreach (var role in new[] { PlayerRole.Sora, PlayerRole.Roxas, PlayerRole.Mickey })
        {
            var h = new Harness(features, role); h.Redeem(); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.DamageGuard.Effective && h.Game.GuardOwner != 0, $"guard: {role} paid only after owned current protection");
            double remain = h.Remaining; await h.Tick(.25);
            check(h.Remaining == remain - .25, $"guard: {role} confirmed same-actor interval counts");
            check(h.Game.Count("player_damage_guard") == 0 && h.Game.Count("combat.damage_guard_owned") == 1, $"guard: {role} never uses scalar toggle ownership");
            foreach (var target in new[] { PlayerRole.Sora, PlayerRole.Roxas, PlayerRole.Mickey })
            {
                remain = h.Remaining; h.Switch(target); await h.Tick(.25);
                check(h.Remaining == remain && h.Game.DamageGuard.Effective, $"guard: {role} to fresh {target} re-establishes without charging crossing");
                await h.Tick(.25); check(h.Remaining == remain - .25, $"guard: new {target} next stable interval counts");
            }
            await h.End(); check(!h.Game.DamageGuard.Effective && h.Engine.PendingCleanupCount == 0, $"guard: {role} ends with acknowledged conditional release");
        }
        foreach (var role in new[] { PlayerRole.Unknown, PlayerRole.Other })
        {
            var h = new Harness(features, role); h.Redeem(); await h.Tick();
            check(h.Engine.PendingEffects.Count == 1 && h.Game.GuardWrites == 0, $"guard: unsupported {role} waits without commands");
        }
        {
            var h = new Harness(features); h.Game.GuardSnapshotAvailable = false; h.Redeem(); await h.Tick();
            check(h.Engine.PendingEffects.Count == 1 && h.Game.Commands.Count == 0, "guard: absent coherent readback blocks initial write");
            h.Game.GuardSnapshotAvailable = true; h.Game.Unsupported.Add(472); await h.Tick();
            check(h.Game.Commands.Count == 0, "guard: legacy bridge without owned capability fails closed");
        }
        {
            var h = new Harness(features); h.Game.SetManualGuard(true); h.Redeem(); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.GuardWrites == 0, "guard: existing manual protection refuses reward without takeover");
        }
        {
            var h = new Harness(features); h.Game.GuardAcceptWithoutApplying = true; h.Redeem(); await h.Tick();
            check(!h.Sink.IsFulfilled("a") && !h.Engine.ActiveEffects.Single().Established && h.Remaining == 30, "guard: successful ACK without effective readback is not paid");
            await h.Tick(); check(h.Remaining == 30, "guard: unconfirmed time is preserved");
            h.Game.GuardAcceptWithoutApplying = false; await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Remaining == 30, "guard: later confirmed application settles without back-charging");
        }
        foreach (bool optOut in new[] { false, true })
        {
            var h = new Harness(features) { PauseTimers = !optOut }; h.Redeem(); await h.Tick(); double remain = h.Remaining;
            h.Game.GuardSnapshotAvailable = false; await h.Tick(.25); await h.Tick(.25);
            check(h.Remaining == remain && h.Engine.ActiveEffects.Single().Paused, $"guard: missing protection pauses even with timer opt-out={optOut}");
            h.Game.GuardSnapshotAvailable = true; await h.Tick(.25);
            check(h.Remaining == remain, $"guard: fresh readback never charges missing interval opt-out={optOut}");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); await h.Tick(.25);
            check(h.Remaining == remain && !h.Game.DamageGuard.Effective, $"guard: native invalidation during menu stops paid time opt-out={optOut}");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); await h.Tick(.25);
            check(h.Remaining == remain && h.Game.DamageGuard.Effective, $"guard: control return can reactivate before usefulness check opt-out={optOut}");
            await h.Tick(5); check(h.Remaining == remain, $"guard: long unobserved gap not charged opt-out={optOut}");
        }
        foreach (ulong foreign in new ulong[] { 0, 0xFEDCBA9876543210 })
        {
            var h = new Harness(features); h.Redeem(); await h.Tick(); double remain = h.Remaining;
            h.Game.SetManualGuard(true, foreign); await h.Tick();
            check(h.Remaining == remain && h.Engine.ActiveEffects.Single().Paused, $"guard: owner takeover {foreign} stops paid time");
            h.Redeem("extension"); await h.Tick(); check(!h.Sink.IsFulfilled("extension"), "guard: foreign protection cannot fulfill an extension");
            await h.End(); check(h.Game.DamageGuard.Effective && h.Game.GuardOwner == foreign && h.Engine.PendingCleanupCount == 0, "guard: conditional cleanup preserves foreign/manual guard");
        }
        {
            var h = new Harness(features); h.Redeem(); await h.Tick(); double remain = h.Remaining;
            ulong owner = h.Game.GuardOwner; int writes = h.Game.GuardWrites;
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.InputBlocked);
            await h.Tick(.25); await h.Tick(.25);
            check(h.Game.DamageGuard.Effective && h.Game.GuardOwner == owner && h.Game.GuardWrites == writes,
                "guard: hit-reaction input lock retains native protection without rearming");
            check(h.Remaining == remain && h.Engine.ActiveEffects.Single().Paused, "guard: effective protection alone does not charge uncontrollable hit-reaction time");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); await h.Tick(.25);
            check(h.Remaining == remain && h.Game.GuardWrites == writes, "guard: hit-reaction resume preserves owner and paused interval");
            await h.Tick(.25); check(h.Remaining == remain - .25, "guard: subsequent controlled protected interval counts");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.InputBlocked); await h.End();
            check(!h.Game.DamageGuard.Effective && h.Engine.PendingCleanupCount == 0, "guard: input lock does not block owner release");
        }
        {
            var h = new Harness(features); h.Redeem(); await h.Tick(); ulong owner = h.Game.GuardOwner;
            ulong wrongBridge = h.Game.MovementInstance + 1; bool rejected = false;
            try { await h.Game.ExecuteAsync(1472, [0, (uint)owner, (uint)(owner >> 32), (uint)wrongBridge, (uint)(wrongBridge >> 32), 0, 0], "fixture stale release"); }
            catch (InvalidOperationException) { rejected = true; }
            check(rejected && h.Game.DamageGuard.Effective && h.Game.GuardOwner == owner, "guard: native rejects wrong-bridge release instead of acknowledging cleanup");
        }
        {
            var h = new Harness(features); h.Redeem(); await h.Tick(); double remain = h.Remaining;
            h.Game.SetManualGuard(false);
            h.Game.BeforeGuardDispatch = a => { if (a[0] == 1) h.Switch(PlayerRole.Mickey); };
            await h.Tick(); check(h.Remaining == remain && !h.Game.DamageGuard.Effective, "guard: actor switch inside awaited ensure rejects old generation");
            h.Game.BeforeGuardDispatch = null; await h.Tick();
            check(h.Remaining == remain && h.Game.DamageGuard.Effective, "guard: new generation is acquired on a later tick with zero crossing time");
        }
        {
            var h = new Harness(features); h.Game.GuardHold = new(); h.Redeem(); Task start = h.Tick();
            check(await Wait.ForAsync(() => h.Game.Commands.Count != 0), "guard: ensure can be held at native dispatch");
            h.Switch(PlayerRole.Roxas); h.Game.GuardHold.SetResult(); await start;
            check(!h.Sink.IsFulfilled("a") && h.Game.GuardWrites == 0, "guard: actor replacement during initial await never captures new actor as old");
            h.Game.GuardHold = null; await h.Tick(); check(h.Sink.IsFulfilled("a"), "guard: later generation can confirm protection");
        }
        {
            var h = new Harness(features); h.Game.GuardLoseNextAck = true; h.Redeem(); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.DamageGuard.Effective, "guard: lost ACK may be confirmed by exact current owner readback");
            h.Game.GuardLoseNextAck = true; await h.End();
            check(!h.Game.DamageGuard.Effective && h.Engine.PendingCleanupCount == 1, "guard: lost release ACK retains intent even after off readback");
            await h.Tick(1); check(h.Engine.PendingCleanupCount == 0, "guard: idempotent release ACK resolves lost cleanup acknowledgement");
        }
        {
            var h = new Harness(features); h.Game.GuardQueueWithoutAck = true; h.Redeem(); await h.Tick();
            check(!h.Sink.IsFulfilled("a") && !h.Game.DamageGuard.Effective, "guard: queued unknown ensure remains unpaid");
            await h.End(); check(h.Sink.IsRefunded("a") && h.Engine.PendingCleanupCount == 1, "guard: stop retains unknown ensure while refunding never-established reward");
            int ensures = h.Game.Calls("combat.damage_guard_owned").Count(a => a[0] == 1);
            await h.Tick(1); check(h.Engine.PendingCleanupCount == 1, "guard: off snapshot cannot settle still-queued ensure");
            h.Game.CompleteQueuedGuard(); check(h.Game.DamageGuard.Effective, "guard: delayed original ensure may still apply");
            await h.Tick(1);
            check(!h.Game.DamageGuard.Effective && h.Engine.PendingCleanupCount == 0 && h.Game.Calls("combat.damage_guard_owned").Count(a => a[0] == 1) == ensures,
                "guard: delayed ensure is released after ACK without any ensure after cleanup began");
        }
        {
            var h = new Harness(features) { MaxWaitSeconds = 1 }; h.Game.GuardAcceptWithoutApplying = true; h.Redeem(); await h.Tick(); await h.Tick(2);
            check(h.Sink.IsRefunded("a") && h.Engine.ActiveEffects.Count == 0 && h.Engine.PendingCleanupCount == 0, "guard: never-confirmed request times out and conditionally cleans up");
        }
        {
            var h = new Harness(features); h.Redeem(); await h.Tick();
            h.Game.Reject = (id, a) => id == "combat.damage_guard_owned" && a[0] == 0; await h.End();
            check(h.Engine.PendingCleanupCount == 1, "guard: refused release retains owner intent");
            await h.Tick(240); check(h.Engine.PendingCleanupCount == 1, "guard: cleanup is not abandoned by scalar restore timeout");
            h.Game.IsConnected = false; await h.Tick(); check(h.Engine.PendingCleanupCount == 1, "guard: disconnect is not a new bridge proof");
            h.Game.IsConnected = true; h.Game.MovementInstance++; h.Game.GuardSnapshotAvailable = false; await h.Tick(1);
            check(h.Engine.PendingCleanupCount == 1, "guard: unreadable replacement bridge cannot clear old intent");
            h.Game.GuardSnapshotAvailable = true; await h.Tick(1);
            check(h.Engine.PendingCleanupCount == 0, "guard: fresh different bridge nonce clears unreachable old intent without release");
        }
        {
            var h = new Harness(features); h.Redeem(); await h.Tick();
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); await h.End();
            check(h.Engine.PendingCleanupCount == 0 && !h.Game.DamageGuard.Effective, "guard: owner release is independent of player control and ActiveCheck");
        }
    }

    private static void DecoderChecks(Action<bool, string> check)
    {
        static void Set(TrainerSnapshot s, int slot, double value)
        { s.Values[slot] = value; s.Valid[slot / 64] |= 1UL << (slot % 64); s.Supported[slot / 64] |= 1UL << (slot % 64); }
        static TrainerSnapshot Fresh()
        {
            var s = new TrainerSnapshot { ProtocolVersion = 4, Connected = true, SceneReady = true, Status = 1 };
            foreach (var (slot, value) in new (int, double)[] { (106, 1), (456, 1), (457, 1), (458, 0), (459, 1), (463, 100),
                (467, 0x87654321), (468, 0x12345678), (469, 0x76543210), (470, 0xFEDCBA98), (471, 1), (472, 1), (473, 0xFEDCBA98), (474, 0x87654321) }) Set(s, slot, value);
            return s;
        }
        var f = Fresh(); var parsed = DamageGuardSnapshot.FromSnapshot(f, 101);
        check(parsed.CanEnsure && parsed.Effective && parsed.Identity == new ActorMovementIdentity(0xFEDCBA9876543210, 0x1234567887654321) && parsed.Owner == 0x87654321FEDCBA98,
            "guard decoder: exact high-bit UInt64 owner/identity from split binary words");
        foreach (int slot in new[] { 106, 467, 468, 469, 470, 471, 473, 474 })
        {
            var s = Fresh(); s.Valid[slot / 64] &= ~(1UL << (slot % 64));
            check(!DamageGuardSnapshot.FromSnapshot(s, 101).Available, $"guard decoder: missing {slot} fails closed");
            foreach (double invalid in new[] { double.NaN, double.PositiveInfinity, -.1, .5, (double)uint.MaxValue + 1 })
            { s = Fresh(); Set(s, slot, invalid); check(!DamageGuardSnapshot.FromSnapshot(s, 101).Available, $"guard decoder: invalid {slot}/{invalid} rejected"); }
        }
        f = Fresh(); f.Supported[472 / 64] &= ~(1UL << (472 % 64)); check(!DamageGuardSnapshot.FromSnapshot(f, 101).Available, "guard decoder: missing owner capability unavailable");
        check(!DamageGuardSnapshot.FromSnapshot(Fresh() with { ProtocolVersion = 3 }, 101).Available, "guard decoder: legacy protocol unavailable");
        check(!DamageGuardSnapshot.FromSnapshot(Fresh(), 1101).Available, "guard decoder: stale publication unavailable");
        check(!DamageGuardSnapshot.FromSnapshot(Fresh(), 99).Available, "guard decoder: future tick unavailable");
        f = Fresh(); Set(f, 463, uint.MaxValue - 20); check(DamageGuardSnapshot.FromSnapshot(f, 20).Available, "guard decoder: clock wrap preserved");
        f = Fresh(); Set(f, 106, 0); check(!DamageGuardSnapshot.FromSnapshot(f, 101).Available, "guard decoder: off with nonzero effective owner is inconsistent");
        Set(f, 473, 0); Set(f, 474, 0); Set(f, 467, 0); Set(f, 468, 0); Set(f, 471, 2);
        parsed = DamageGuardSnapshot.FromSnapshot(f, 101);
        check(parsed.Available && !parsed.CanEnsure && !parsed.Effective && parsed.Identity.BridgeInstance != 0, "guard decoder: observer fault keeps only fresh bridge proof for cleanup");
        Set(f, 106, 1); check(!DamageGuardSnapshot.FromSnapshot(f, 101).Available, "guard decoder: effective guard needs observer and nonzero current generation");
    }
}
