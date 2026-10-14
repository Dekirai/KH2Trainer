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
        public ConflictBehavior Conflict = ConflictBehavior.Queue;
        public Harness(IReadOnlyList<FeatureDefinition> features, PlayerRole role = PlayerRole.Sora)
        {
            Game = new(features) { Gameplay = new(true, role, GameplayBlockers.None) };
            Engine = new(Game, new(features), EffectCatalog.All,
                key => { var d = EffectCatalog.Find(key)!; return new(d.Title, d.DurationSeconds, d.Amount, SameEffectBehavior.Extend, Conflict); },
                () => new(TimeSpan.FromSeconds(MaxWaitSeconds), 600, PauseTimers), Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Redeem(string id = "a", string key = "invincible") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public Task Tick(double elapsed = .25) { Now = Now.AddSeconds(elapsed); return Engine.TickAsync(Now); }
        public Task End(string key = "invincible") => Engine.EndEffectAsync(key, Now);
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
            try { await h.Game.ExecuteAsync(1472, [0, (uint)owner, (uint)(owner >> 32), (uint)wrongBridge, (uint)(wrongBridge >> 32), 0, 0, 0], "fixture stale release"); }
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
        await LethalOnlyAsync(features, check);
    }

    // Guardian Angel uses the same owner contract; only its requested and published mode differ.
    private static async Task LethalOnlyAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        const ulong foreign = 0xFEDCBA9876543210;
        foreach (var role in new[] { PlayerRole.Sora, PlayerRole.Roxas, PlayerRole.Mickey })
        {
            var h = new Harness(features, role); h.Redeem("a", "guardian-angel"); await h.Tick();
            var ensure = h.Game.Calls("combat.damage_guard_owned").Single();
            check(h.Sink.IsFulfilled("a") && h.Game.DamageGuard.Mode == DamageGuardMode.LethalOnly && ensure[0] == 1 && ensure[7] == 1,
                $"lethal guard: {role} paid only after owned lethal-only protection");
            check(h.Game.Get("player_damage_guard_lethal") == 1 && h.Game.Get("player_damage_guard") == 0 && h.Game.Get("combat.damage_guard_mode") == 2,
                $"lethal guard: {role} publishes the lethal-only mode, not the full guard");
            double remain = h.Remaining; await h.Tick(.25);
            check(h.Remaining == remain - .25, $"lethal guard: {role} confirmed interval counts");
            await h.End("guardian-angel");
            check(!h.Game.DamageGuard.Effective && h.Engine.PendingCleanupCount == 0 && h.Game.Calls("combat.damage_guard_owned").Last() is [0, .., 0],
                $"lethal guard: {role} releases only its own owner");
        }
        {
            var h = new Harness(features); h.Redeem(); await h.Tick();
            check(h.Game.Calls("combat.damage_guard_owned").Single()[7] == 0 && h.Game.DamageGuard.Mode == DamageGuardMode.Full,
                "lethal guard: Invincibility still requests the full mode");
            h.Redeem("b", "guardian-angel"); await h.Tick();
            check(!h.Sink.IsFulfilled("b") && h.Engine.PendingEffects.Count == 1 && h.Game.DamageGuard.Mode == DamageGuardMode.Full,
                "lethal guard: the shared defense group queues Guardian Angel behind Invincibility");
            await h.End(); await h.Tick();
            check(h.Sink.IsFulfilled("b") && !h.Sink.IsRefunded("b") && h.Game.DamageGuard.Mode == DamageGuardMode.LethalOnly,
                "lethal guard: the queued Guardian Angel starts once Invincibility released its guard");
        }
        await ReplaceAsync(features, check);
        foreach (var (key, manual) in new[] { ("guardian-angel", DamageGuardMode.Full), ("guardian-angel", DamageGuardMode.LethalOnly), ("invincible", DamageGuardMode.LethalOnly) })
        {
            var h = new Harness(features); h.Game.SetManualGuard(true, mode: manual); h.Redeem("a", key); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.GuardWrites == 0, $"lethal guard: manual {manual} protection refunds {key} without takeover");
        }
        {
            var h = new Harness(features); h.Redeem("a", "guardian-angel"); await h.Tick(); double remain = h.Remaining;
            h.Game.SetGuardMode(DamageGuardMode.Full); await h.Tick(.25);
            check(h.Remaining == remain && h.Game.DamageGuard.Mode == DamageGuardMode.LethalOnly && h.Game.Calls("combat.damage_guard_owned").Last()[7] == 1,
                "lethal guard: a full-mode publication for this owner is not paid and is switched back in place");
            await h.Tick(.25); check(h.Remaining == remain - .25, "lethal guard: the restored mode counts again");
        }
        {
            var h = new Harness(features); h.Redeem("a", "guardian-angel"); await h.Tick(); double remain = h.Remaining;
            h.Game.SetManualGuard(true, foreign, DamageGuardMode.LethalOnly); await h.Tick();
            check(h.Remaining == remain && h.Engine.ActiveEffects.Single().Paused, "lethal guard: another owner's lethal-only guard does not pay this reward");
            await h.End("guardian-angel");
            check(h.Game.DamageGuard.Mode == DamageGuardMode.LethalOnly && h.Game.GuardOwner == foreign && h.Engine.PendingCleanupCount == 0,
                "lethal guard: release preserves the other owner's guard");
        }
        var guardian = EffectCatalog.Find("guardian-angel")!;
        check(guardian.AllowedRoles == EffectPlayerRoles.FieldPlayers && guardian.Group == "defense" && guardian.Category == RewardCategory.Help &&
            guardian.Prompt.Contains("falls", StringComparison.Ordinal) && guardian.Prompt.Contains("HP stays", StringComparison.Ordinal),
            "lethal guard: Guardian Angel is a field-player defense Help reward that states what still counts");
    }

    // Conflict = Replace: the two defense rewards take over from each other. Only the replaced reward's own
    // owner is ignored by the start check; the new owner is ensured only after that owner was released.
    private static async Task ReplaceAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        static ulong OwnerOf(double[] a) => (uint)a[1] | ((ulong)(uint)a[2] << 32);
        foreach (var (first, second, mode) in new[] { ("invincible", "guardian-angel", DamageGuardMode.LethalOnly), ("guardian-angel", "invincible", DamageGuardMode.Full) })
        {
            var h = new Harness(features) { Conflict = ConflictBehavior.Replace }; h.Redeem("a", first); await h.Tick();
            ulong previous = h.Game.GuardOwner;
            h.Redeem("b", second); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Sink.IsFulfilled("b") && h.Sink.Refunded.Count == 0 && h.Engine.ActiveEffects.Single().Key == second &&
                h.Game.DamageGuard.Mode == mode && h.Game.GuardOwner is not 0 && h.Game.GuardOwner != previous && h.Engine.PendingCleanupCount == 0,
                $"guard replace: {second} replaces a running {first} instead of refunding");
            var calls = h.Game.Calls("combat.damage_guard_owned").ToArray();
            check(calls.Length == 3 && calls[1][0] == 0 && OwnerOf(calls[1]) == previous && calls[2][0] == 1 && OwnerOf(calls[2]) == h.Game.GuardOwner,
                $"guard replace: {first}'s owner is released before {second}'s owner is ensured");
        }
        foreach (var (first, second, mode) in new[] { ("invincible", "guardian-angel", DamageGuardMode.LethalOnly), ("guardian-angel", "invincible", DamageGuardMode.Full) })
        {
            var h = new Harness(features) { Conflict = ConflictBehavior.Replace }; h.Redeem("a", first); await h.Tick();
            ulong previous = h.Game.GuardOwner;
            h.Game.Reject = (id, a) => id == "combat.damage_guard_owned" && a[0] == 0;
            h.Redeem("b", second); await h.Tick(); await h.Tick(1); await h.Tick(1);
            check(h.Game.GuardOwner == previous && h.Engine.ActiveEffects.Count == 0 && h.Engine.PendingEffects.Single().Status == "Waiting until the previous effect is undone" &&
                h.Engine.PendingCleanupCount == 1 && !h.Sink.IsRefunded("b") && h.Game.Calls("combat.damage_guard_owned").Count(a => a[0] == 1) == 1,
                $"guard replace: {second} waits without an ensure while {first}'s owner still holds protection");
            h.Game.Reject = null; await h.Tick(1);
            check(h.Sink.IsFulfilled("b") && h.Engine.ActiveEffects.Single().Key == second && h.Game.DamageGuard.Mode == mode &&
                h.Game.GuardOwner is not 0 && h.Game.GuardOwner != previous && h.Engine.PendingCleanupCount == 0,
                $"guard replace: {second} starts once {first}'s owner was released");
        }
        foreach (ulong manual in new ulong[] { 0, 0xFEDCBA9876543210 })
        {
            // The running reward lost its guard to manual or foreign protection; replacing it would not release that.
            var h = new Harness(features) { Conflict = ConflictBehavior.Replace }; h.Redeem("a", "invincible"); await h.Tick();
            h.Game.SetManualGuard(true, manual); await h.Tick();
            int ensures = h.Game.Calls("combat.damage_guard_owned").Count(a => a[0] == 1);
            h.Redeem("b", "guardian-angel"); await h.Tick();
            check(h.Sink.Refunded.SingleOrDefault(r => r.Redemption.Id == "b").Reason == "Damage protection is already active outside this reward." &&
                h.Engine.ActiveEffects.Single().Key == "invincible" && h.Game.GuardOwner == manual && h.Game.DamageGuard.Mode == DamageGuardMode.Full &&
                h.Game.Calls("combat.damage_guard_owned").Count(a => a[0] == 1) == ensures && h.Game.Calls("combat.damage_guard_owned").All(a => a[0] == 1),
                $"guard replace: protection held by owner {manual:X} is not the replaced reward's and still refunds without takeover");
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
                (467, 0x87654321), (468, 0x12345678), (469, 0x76543210), (470, 0xFEDCBA98), (471, 1), (472, 1), (473, 0xFEDCBA98), (474, 0x87654321),
                (483, 1) }) Set(s, slot, value);
            return s;
        }
        var f = Fresh(); var parsed = DamageGuardSnapshot.FromSnapshot(f, 101);
        check(parsed.CanEnsure && parsed.Effective && parsed.Mode == DamageGuardMode.Full &&
            parsed.Identity == new ActorMovementIdentity(0xFEDCBA9876543210, 0x1234567887654321) && parsed.Owner == 0x87654321FEDCBA98,
            "guard decoder: exact high-bit UInt64 owner/identity from split binary words");
        // Slot 106 may show either only the full guard or any guard; a lethal-only mode is decoded from slot 483 alone.
        foreach (double full in new double[] { 0, 1 })
        {
            f = Fresh(); Set(f, 483, 2); Set(f, 106, full); parsed = DamageGuardSnapshot.FromSnapshot(f, 101);
            check(parsed.Available && parsed.Effective && parsed.Mode == DamageGuardMode.LethalOnly && parsed.Owner == 0x87654321FEDCBA98,
                $"guard decoder: lethal-only mode with full toggle {full} keeps its owner");
        }
        foreach (var (mode, full) in new (double, double)[] { (0, 1), (1, 0), (3, 1) })
        {
            f = Fresh(); Set(f, 483, mode); Set(f, 106, full);
            check(!DamageGuardSnapshot.FromSnapshot(f, 101).Available, $"guard decoder: mode {mode} with full toggle {full} is inconsistent");
        }
        foreach (int slot in new[] { 106, 467, 468, 469, 470, 471, 473, 474, 483 })
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
        f = Fresh(); Set(f, 106, 0); Set(f, 483, 0); check(!DamageGuardSnapshot.FromSnapshot(f, 101).Available, "guard decoder: off with nonzero effective owner is inconsistent");
        Set(f, 473, 0); Set(f, 474, 0); Set(f, 467, 0); Set(f, 468, 0); Set(f, 471, 2);
        parsed = DamageGuardSnapshot.FromSnapshot(f, 101);
        check(parsed.Available && !parsed.CanEnsure && !parsed.Effective && parsed.Identity.BridgeInstance != 0, "guard decoder: observer fault keeps only fresh bridge proof for cleanup");
        foreach (double mode in new double[] { 1, 2 })
        {
            Set(f, 106, 1); Set(f, 483, mode);
            check(!DamageGuardSnapshot.FromSnapshot(f, 101).Available, $"guard decoder: effective mode {mode} needs observer and nonzero current generation");
        }
    }
}
