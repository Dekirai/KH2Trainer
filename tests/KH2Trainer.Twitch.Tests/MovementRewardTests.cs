using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class MovementRewardTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game; public readonly FakeSink Sink = new(); public readonly EffectEngine Engine;
        public DateTimeOffset Now = new(2026, 10, 7, 16, 0, 0, TimeSpan.Zero);
        public Harness(IReadOnlyList<FeatureDefinition> features, PlayerRole role = PlayerRole.Sora)
        {
            Game = new(features) { Gameplay = new(true, role, GameplayBlockers.None) };
            Engine = new(Game, new(features), EffectCatalog.All, key => new(key, 30, 0, SameEffectBehavior.Extend, ConflictBehavior.Queue),
                () => new(TimeSpan.FromMinutes(10), 600, true), Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Redeem(string key, string id = "a") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public Task Tick(double seconds = .25) { Now = Now.AddSeconds(seconds); return Engine.TickAsync(Now); }
        public async Task Finish(string key) { await Engine.EndEffectAsync(key, Now); for (int i = 0; i < 4; i++) await Tick(1); }
    }
    private static readonly PlayerRole[] Roles = [PlayerRole.Sora, PlayerRole.Roxas, PlayerRole.Mickey];
    private static bool Same(double? a, double? b) => a.HasValue && b.HasValue && BitConverter.SingleToUInt32Bits((float)a.Value) == BitConverter.SingleToUInt32Bits((float)b.Value);

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var map = new FeatureMap(features);
        foreach (string key in new[] { "super-speed", "snail", "moon-jump" })
        {
            var definition = EffectCatalog.Find(key)!;
            check(definition.AllowedRoles == EffectPlayerRoles.FieldPlayers, $"movement typed: {key} admits exactly the three proven roles");
            foreach (var role in Enum.GetValues<PlayerRole>())
            {
                var h = new Harness(features, role); h.Redeem(key); await h.Tick();
                bool allowed = Roles.Contains(role);
                check(h.Sink.IsFulfilled("a") == allowed && (h.Game.MovementWrites == 2) == allowed && h.Game.Commands.Count == 0,
                    $"movement typed: {key}/{role} uses one native cohort and no scalar commands");
                if (!allowed) check(h.Engine.PendingEffects.Count == 1, $"movement typed: unsupported {role} waits");
                else
                {
                    await h.Finish(key);
                    check(h.Engine.PendingCleanupCount == 0 && h.Game.MovementLeaseCount == 0 && h.Game.MovementReceiptCount == 0,
                        $"movement typed: {key}/{role} releases and acknowledges terminal journal records");
                }
            }
            foreach (string feature in definition.Features)
            {
                var policy = map.Get(feature);
                foreach (double? invalid in new double?[] { null, double.NaN, double.PositiveInfinity, policy.Minimum - 1, policy.Maximum + 1,
                    feature == "movement.fall_speed" ? 0 : feature == "movement.base_jump_height" ? 1200 : 100 })
                {
                    var h = new Harness(features); double original = h.Game.Get(feature)!.Value;
                    if (invalid.HasValue) h.Game.Set(feature, invalid.Value); else h.Game.Values.Remove(policy.ValueSlot);
                    h.Redeem(key); await h.Tick();
                    check(h.Game.MovementWrites == 0 && h.Engine.PendingEffects.Count == 1, $"movement typed: {key} rejects missing/out-of-policy {feature}/{invalid}");
                    h.Game.Set(feature, original); await h.Tick(); await h.Finish(key);
                    check(Same(h.Game.Get(feature), original), $"movement typed: {key} restores recovered original {feature}");
                }
                foreach (double boundary in new[] { policy.Minimum, policy.Maximum })
                {
                    var h = new Harness(features); h.Game.Set(feature, boundary); h.Redeem(key); await h.Tick();
                    check(h.Sink.IsFulfilled("a"), $"movement typed: {key} accepts Float32 boundary {feature}/{boundary}");
                    await h.Finish(key); check(Same(h.Game.Get(feature), boundary), $"movement typed: {key} exact-bit boundary restore {feature}/{boundary}");
                }
                {
                    var h = new Harness(features); h.Redeem(key); await h.Tick(); double remaining = h.Engine.ActiveEffects.Single().RemainingSeconds;
                    int writes = h.Game.MovementWrites; h.Game.Set(feature, policy.Maximum + 1);
                    await h.Tick(.5); await h.Tick(.5);
                    check(h.Engine.ActiveEffects.Single().RemainingSeconds == remaining && h.Game.MovementWrites == writes,
                        $"movement typed: {key} invalid script value pauses duration and reapply");
                    await h.Finish(key); check(Same(h.Game.Get(feature), policy.Maximum + 1), $"movement typed: {key} cleanup preserves invalid external {feature}");
                }
                {
                    var h = new Harness(features); h.Redeem(key); await h.Tick(); double remaining = h.Engine.ActiveEffects.Single().RemainingSeconds;
                    h.Game.Set(feature, policy.Maximum + 1); await h.Tick(.5); h.Game.Set(feature, (policy.Minimum + policy.Maximum) / 2);
                    await h.Tick(.5);
                    check(h.Engine.ActiveEffects.Single().RemainingSeconds == remaining, $"movement typed: {key} recapture charges no missing interval");
                    await h.Finish(key); check(Same(h.Game.Get(feature), (policy.Minimum + policy.Maximum) / 2), $"movement typed: {key} reapply keeps that field's new original");
                }
            }
            // Whole-cohort compare protects even the first field when the second changes before native dispatch.
            {
                var h = new Harness(features); string second = definition.Features[1];
                var originals = definition.Features.Select(h.Game.Get).ToArray(); bool once = true;
                h.Game.BeforeMovementDispatch = c => { if (once && c.Operation == MovementOperation.Acquire) { once = false; h.Game.Values.Remove(map.Get(second).ValueSlot); } };
                h.Redeem(key); await h.Tick();
                check(h.Game.MovementWrites == 0 && !h.Sink.IsFulfilled("a"), $"movement typed: {key} missing second value at dispatch writes neither field");
                h.Game.Set(second, originals[1]!.Value); await h.Tick();
                check(h.Sink.IsFulfilled("a"), $"movement typed: {key} deferred cohort starts after resource returns");
            }
            foreach (var role in Roles) foreach (bool retire in new[] { false, true })
            {
                var h = new Harness(features); var oldOriginal = h.Game.Movement.Values; ulong old = h.Game.MovementGeneration;
                h.Redeem(key); await h.Tick(); double remaining = h.Engine.ActiveEffects.Single().RemainingSeconds;
                var coincident = h.Game.Movement.Values;
                h.Game.SwitchMovementActor(role, coincident, retireOld: retire); await h.Tick(.5);
                check(h.Sink.IsFulfilled("a") && h.Engine.ActiveEffects.Single().RemainingSeconds == remaining,
                    $"movement typed: {key}/{role} equal-value replacement/retired={retire} charges no cross-actor interval");
                await h.Finish(key);
                check(h.Game.Movement.Values.Matches(coincident, key == "moon-jump" ? MovementMask.Air : MovementMask.Speed),
                    $"movement typed: {key}/{role} restores replacement's originals, never Sora's");
                if (!retire)
                {
                    check(h.Engine.PendingCleanupCount == 1, $"movement typed: {key} living off-current actor cleanup remains tracked");
                    h.Game.SwitchMovementActor(PlayerRole.Sora, default, existingGeneration: old); for (int i = 0; i < 3; i++) await h.Tick(1);
                    check(h.Game.Movement.Values.Matches(oldOriginal, key == "moon-jump" ? MovementMask.Air : MovementMask.Speed) && h.Engine.PendingCleanupCount == 0,
                        $"movement typed: {key} old actor gets only its own originals when it returns");
                }
                else check(h.Engine.PendingCleanupCount == 0, $"movement typed: {key} retired generation needs no pointer write");
            }
            // A switch during an awaited journal operation must not charge even when both endpoint booleans say useful.
            {
                var h = new Harness(features); h.Redeem(key); await h.Tick(); double remaining = h.Engine.ActiveEffects.Single().RemainingSeconds;
                bool switched = false;
                h.Game.AfterMovementDispatch = c => { if (!switched && c.Operation == MovementOperation.QueryLease) { switched = true; h.Game.SwitchMovementActor(PlayerRole.Mickey, h.Game.Movement.Values, true); } };
                await h.Tick(.5); await h.Tick(.5);
                check(switched && h.Engine.ActiveEffects.Single().RemainingSeconds >= remaining - .5, $"movement typed: {key} await-boundary switch does not consume the transition interval");
            }
            {
                var h = new Harness(features); h.Game.WithholdMovementAck = true; h.Redeem(key); await h.Tick();
                check(!h.Sink.IsFulfilled("a") && h.Game.MovementWrites == 2 && !h.Engine.ActiveEffects.Single().Established,
                    $"movement typed: {key} unknown acknowledgement does not fulfill viewer or guess originals");
                h.Game.SwitchMovementActor(PlayerRole.Roxas, h.Game.Movement.Values, true);
                await h.Tick(.5); check(h.Game.MovementWrites == 2, $"movement typed: {key} unresolved original blocks new actor acquire");
                h.Game.WithholdMovementAck = false; await h.Tick(.5); await h.Tick(.5);
                check(h.Sink.IsFulfilled("a") && h.Game.MovementCommands.Count(c => c.Operation == MovementOperation.Acquire) == 2,
                    $"movement typed: {key} late receipt releases old lease then captures new actor exactly once");
                await h.Finish(key);
            }
            {
                var h = new Harness(features); h.Redeem(key); await h.Tick();
                h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu); int writes = h.Game.MovementWrites;
                await h.Engine.EndEffectAsync(key, h.Now);
                check(h.Engine.PendingCleanupCount == 1 && h.Game.MovementWrites == writes && h.Game.MovementCommands.Any(c => c.Operation == MovementOperation.ReleaseIntent),
                    $"movement typed: {key} menu permits release intent but no restore write");
                h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); for (int i = 0; i < 3; i++) await h.Tick(1);
                check(h.Engine.PendingCleanupCount == 0, $"movement typed: {key} deferred cleanup completes after control returns");
            }
            {
                var h = new Harness(features); h.Game.MovementHold = new(); h.Redeem(key); var starting = h.Tick();
                check(await Wait.ForAsync(() => h.Game.MovementCommands.Count != 0), $"movement typed: {key} request reaches awaited native dispatch");
                h.Game.SwitchMovementActor(PlayerRole.Mickey, h.Game.Movement.Values, true); h.Game.MovementHold.SetResult(); await starting;
                check(h.Game.MovementWrites == 0 && !h.Sink.IsFulfilled("a"), $"movement typed: {key} actor changes during awaited acquire, no stale write");
                h.Game.MovementHold = null; await h.Tick(); await h.Finish(key);
                check(h.Sink.IsFulfilled("a") && h.Engine.PendingCleanupCount == 0, $"movement typed: {key} retries with replacement-specific receipt");
            }
            {
                var h = new Harness(features); h.Game.RejectMovement = c => c.Operation == MovementOperation.Acquire ? MovementReason.ObserverFault : null;
                h.Redeem(key); await h.Tick(); await h.Tick(.5);
                check(h.Game.MovementWrites == 0 && !h.Sink.IsFulfilled("a"), $"movement typed: {key} definite initial no-write refusal remains unpaid");
                h.Game.RejectMovement = null; h.Game.RestartMovementBridge(MovementValues.FromValues(3, 9, 13, 180)); await h.Tick();
                check(h.Sink.IsFulfilled("a"), $"movement typed: {key} definite refusal does not latch forever after fresh bridge");
                await h.Finish(key); check(Same(h.Game.Get("movement.run_speed"), 9), $"movement typed: {key} fresh bridge originals are independent");
            }
            {
                var h = new Harness(features); h.Redeem(key); await h.Tick();
                h.Game.RejectMovement = c => c.Operation == MovementOperation.QueryLease ? MovementReason.LeaseNotFound : null;
                await h.Tick(); int writes = h.Game.MovementWrites; await h.Tick();
                check(h.Game.MovementWrites == writes && h.Engine.ActiveEffects.Single().Paused, $"movement typed: {key} same-instance missing lease latches safely");
                h.Game.RejectMovement = null; h.Game.RestartMovementBridge(MovementValues.FromValues(3, 9, 13, 180)); await h.Tick();
                check(h.Game.MovementWrites == writes + 2 && !h.Engine.ActiveEffects.Single().Paused, $"movement typed: {key} proven replacement bridge clears unreachable old fault");
                await h.Finish(key);
            }
            {
                var h = new Harness(features); h.Redeem(key); await h.Tick(); h.Game.UncertainMovementLease = true;
                await h.Tick(); check(h.Engine.ActiveEffects.Single().Paused && h.Game.PendingMovement == null,
                    $"movement typed: {key} observed uncertain lease is not a pending publication");
                h.Game.UncertainMovementLease = false; h.Game.RestartMovementBridge(MovementValues.FromValues(3, 9, 13, 180)); await h.Tick();
                check(!h.Engine.ActiveEffects.Single().Paused, $"movement typed: {key} new bridge recovers from acknowledged uncertain lease");
                await h.Finish(key);
            }
        }
        // Exact-bit ownership: an externally changed sibling survives; unchanged siblings retain their first original.
        {
            var h = new Harness(features); h.Redeem("super-speed"); await h.Tick(); h.Game.Set("movement.run_speed", 11); await h.Tick(.5); await h.Finish("super-speed");
            check(Same(h.Game.Get("movement.run_speed"), 11) && Same(h.Game.Get("movement.walk_speed"), 2), "movement typed: reapply does not replace unchanged sibling original with its applied value");
        }
        check(EffectCatalog.Find("moon-jump")!.Prompt.Contains("Gravity is unchanged") && EffectCatalog.Find("moon-jump")!.Prompt.Contains("special actions"),
            "movement typed: Moon Jump states native base-value limitations");
        {
            var h = new Harness(features); h.Game.RejectMovement = c => c.Operation == MovementOperation.Acquire ? MovementReason.ObserverFault : null;
            h.Redeem("super-speed"); await h.Tick(); await h.Tick(601);
            check(h.Engine.ActiveEffects.Count == 0 && h.Sink.IsRefunded("a") && h.Game.MovementWrites == 0,
                "movement typed: definite no-write refusal honors configured maximum wait and refunds once");
        }
    }
}
