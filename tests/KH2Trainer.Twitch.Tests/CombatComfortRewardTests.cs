using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class CombatComfortRewardTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game;
        public readonly FakeSink Sink = new();
        public readonly TwitchSettings Settings = new();
        public readonly EffectEngine Engine;
        public DateTimeOffset Now = new(2026, 10, 11, 12, 0, 0, TimeSpan.Zero);
        public Harness(IReadOnlyList<FeatureDefinition> features)
        {
            Game = new(features);
            Game.Set("target_lock_mode", 2); Game.Set("target_hp", 500);
            Game.Set("target_revenge", 25); Game.Set("target_revenge_threshold", 100);
            Game.Set("player.gauge.mode", 2); Game.Set("player.gauge.remaining", 20); Game.Set("player.gauge.maximum", 100);
            Game.Set("gummi.hp", 50); Game.Set("gummi.special_stock", 2); Game.Set("gummi.special_progress", 50);
            Engine = new(Game, new(features), EffectCatalog.All,
                key => RewardResolver.Options(EffectCatalog.Find(key)!, Settings), () => RewardResolver.Engine(Settings),
                Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Redeem(string key, string id = "a") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public Task Tick(double seconds = .25) { Now = Now.AddSeconds(seconds); return Engine.TickAsync(Now); }
        public async Task End(string key) { await Engine.EndEffectAsync(key, Now); for (int i = 0; i < 4; i++) await Tick(1); }
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var map = new FeatureMap(features);
        (string Key, string Command, double[] Args)[] actions =
        [
            ("enemy-hp-cut", "target_reduce_hp_percent", [25]), ("calm-enemy", "target_reset_revenge", []),
            ("timer-refill", "player.gauge.fill", []), ("gummi-special-charge", "gummi.add_special_charge", [100]),
            ("enemy-armor", "damage.target.general", [50])
        ];
        foreach (var (key, command, arguments) in actions)
        {
            var d = EffectCatalog.Find(key)!;
            check(!d.IsTimed && !d.ChangesSaveData, $"new rewards: {key} is an explicit one-time runtime action");
            var h = new Harness(features); h.Redeem(key); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.Calls(command).Single().SequenceEqual(arguments),
                $"new rewards: {key} dispatches exactly its default native arguments");
            h.Game.Set("target_lock_mode", 0); h.Game.Set("damage.target.general", 120);
            await h.Tick(10); await h.End(key);
            check(h.Game.Count(command) == 1 && h.Engine.PendingCleanupCount == 0 && h.Game.Get("damage.target.general") == 120,
                $"new rewards: {key} never replays or restores into a later target");
            foreach (string feature in d.Features)
            {
                var missing = new Harness(features); missing.Game.Unsupported.Add(map.Get(feature).CapabilitySlot);
                missing.Redeem(key); await missing.Tick();
                check(missing.Game.Commands.Count == 0 && missing.Engine.PendingEffects.Count == 1 && !missing.Sink.IsFulfilled("a"),
                    $"new rewards: {key} waits for unsupported {feature}");
            }
            var rejected = new Harness(features); rejected.Game.Reject = (id, _) => id == command;
            rejected.Redeem(key); await rejected.Tick();
            check(!rejected.Sink.IsFulfilled("a") && rejected.Engine.PendingEffects.Count == 1,
                $"new rewards: {key} native refusal cannot charge the viewer");
            await rejected.Tick(61);
            check(rejected.Sink.IsRefunded("a") && rejected.Engine.PendingEffects.Count == 0,
                $"new rewards: {key} persistent native refusal refunds within the retry limit");
            var disconnected = new Harness(features); disconnected.Game.IsConnected = false;
            disconnected.Redeem(key); await disconnected.Tick();
            check(disconnected.Game.Commands.Count == 0 && disconnected.Engine.PendingEffects.Count == 1,
                $"new rewards: {key} waits while disconnected");
        }
        foreach (string key in new[] { "enemy-hp-cut", "calm-enemy", "enemy-armor", "timer-refill" })
        {
            foreach (var role in Enum.GetValues<PlayerRole>())
            {
                var h = new Harness(features); h.Game.Gameplay = new(true, role, GameplayBlockers.None);
                h.Redeem(key); await h.Tick();
                check(h.Sink.IsFulfilled("a") == (role == PlayerRole.Sora) && (h.Game.Commands.Count > 0) == (role == PlayerRole.Sora),
                    $"new rewards: {key}/{role} keeps its native Sora admission");
            }
            foreach (var blocker in new[] { GameplayBlockers.Menu, GameplayBlockers.Loading, GameplayBlockers.Cutscene, GameplayBlockers.Transition, GameplayBlockers.Dead })
            {
                var h = new Harness(features); h.Game.Gameplay = new(true, PlayerRole.Sora, blocker);
                h.Redeem(key); await h.Tick();
                check(h.Game.Commands.Count == 0 && h.Engine.PendingEffects.Count == 1, $"new rewards: {key} waits under {blocker}");
            }
        }
        foreach (string key in new[] { "enemy-hp-cut", "calm-enemy", "enemy-armor" })
        {
            foreach (double mode in new[] { 0d, 1, 3 })
                await Waits(key, "target_lock_mode", mode);
            await Waits(key, "target_lock_mode", null);
            await Waits(key, "target_hp", null);
            await Waits(key, "target_hp", 0);
        }
        await Refunds("enemy-hp-cut", "target_hp", 1);
        foreach (double hp in new[] { 1.5, 1000001, double.PositiveInfinity }) await Waits("enemy-hp-cut", "target_hp", hp);
        await Refunds("calm-enemy", "target_revenge", 0);
        foreach (double? rv in new double?[] { null, -1, 1000001, double.NaN }) await Waits("calm-enemy", "target_revenge", rv);
        foreach (double? threshold in new double?[] { null, 0, 1000001, double.PositiveInfinity }) await Waits("calm-enemy", "target_revenge_threshold", threshold);
        foreach (double factor in new[] { 0d, 25, 50 }) await Refunds("enemy-armor", "damage.target.general", factor);
        foreach (double? factor in new double?[] { null, -1, 256, 50.5, double.NaN }) await Waits("enemy-armor", "damage.target.general", factor);

        foreach (double? mode in new double?[] { null, 0, 1, 4, double.NaN }) await Waits("timer-refill", "player.gauge.mode", mode);
        foreach (double mode in new[] { 2d, 3 })
        {
            var h = new Harness(features); h.Game.Set("player.gauge.mode", mode); h.Redeem("timer-refill"); await h.Tick();
            check(h.Sink.IsFulfilled("a") && h.Game.Count("player.gauge.fill") == 1 && h.Game.Count("drive.trigger") == 0,
                $"new rewards: timer mode {mode} refills without transformation");
        }
        await Refunds("timer-refill", "player.gauge.remaining", 100);
        foreach (double? current in new double?[] { null, -1, 101, double.NaN }) await Waits("timer-refill", "player.gauge.remaining", current);
        foreach (double? maximum in new double?[] { null, 0, 1000001, double.PositiveInfinity }) await Waits("timer-refill", "player.gauge.maximum", maximum);

        foreach (double? stock in new double?[] { null, -1, 10, 1.5, double.NaN }) await Waits("gummi-special-charge", "gummi.special_stock", stock);
        foreach (double? progress in new double?[] { null, -1, 101, .5, double.PositiveInfinity }) await Waits("gummi-special-charge", "gummi.special_progress", progress);
        await Waits("gummi-special-charge", "gummi.hp", 0);
        {
            var h = new Harness(features); h.Game.Values.Remove(map.Get("gummi.hp").ValueSlot);
            h.Redeem("gummi-special-charge"); await h.Tick();
            check(h.Sink.IsRefunded("a") && h.Game.Commands.Count == 0, "new rewards: Gummi charge outside a Gummi mission refunds");
        }
        foreach (int progress in new[] { 0, 99, 100 })
        {
            var h = new Harness(features); h.Game.Set("gummi.special_stock", 9); h.Game.Set("gummi.special_progress", progress);
            h.Game.Gameplay = new(false, PlayerRole.Unknown, GameplayBlockers.NoPlayer);
            h.Redeem("gummi-special-charge"); await h.Tick();
            check(h.Sink.IsRefunded("a") == (progress == 100) && h.Sink.IsFulfilled("a") == (progress != 100),
                $"new rewards: Gummi stock9/progress{progress} uses independent context and exact capacity");
        }
        foreach (var (key, command, low, high) in new[] { ("enemy-hp-cut", "target_reduce_hp_percent", 1, 99), ("gummi-special-charge", "gummi.add_special_charge", 1, 900) })
        {
            foreach (int amount in new[] { -1, low, high, high + 1 })
            {
                var h = new Harness(features); h.Settings.For(key).Amount = amount; h.Redeem(key); await h.Tick();
                check(h.Game.Calls(command).Single().Single() == Math.Clamp(amount, low, high),
                    $"new rewards: {key} configured amount {amount} respects native bounds");
            }
        }

        foreach (float fall in new[] { .1f, 20, 75, 100 })
        {
            var h = new Harness(features); h.Game.Set("movement.fall_speed", fall); h.Game.Set("movement.base_jump_height", 123);
            h.Redeem("heavy-jumps"); await h.Tick();
            var command = h.Game.MovementCommands.Single(c => c.Operation == MovementOperation.Acquire);
            check(command.Mask == MovementMask.Air && command.Desired.Walk == 0 && command.Desired.Run == 0 &&
                h.Game.Get("movement.fall_speed") == Math.Min(100, fall * 2) && h.Game.Get("movement.base_jump_height") == 61.5 &&
                h.Game.Get("movement.run_speed") == 8 && h.Game.Get("movement.walk_speed") == 2,
                $"new rewards: heavy jumps applies exact Air cohort for fall {fall}");
            await h.End("heavy-jumps");
            check(h.Game.Get("movement.fall_speed") == fall && h.Game.Get("movement.base_jump_height") == 123 && h.Engine.PendingCleanupCount == 0,
                $"new rewards: heavy jumps restores captured originals for fall {fall}");
        }
        {
            var h = new Harness(features); h.Game.RejectMovement = c => c.Operation == MovementOperation.Acquire ? MovementReason.JournalFull : null;
            h.Redeem("heavy-jumps"); await h.Tick();
            check(h.Game.MovementWrites == 0 && !h.Sink.IsFulfilled("a"), "new rewards: heavy jumps with full native journal writes nothing and stays unpaid");
            h.Game.RejectMovement = null; await h.Tick(); await h.End("heavy-jumps");
            check(h.Sink.IsFulfilled("a") && h.Game.MovementLeaseCount == 0, "new rewards: heavy jumps recovers after journal capacity returns");
        }
        {
            var h = new Harness(features); h.Redeem("moon-jump"); await h.Tick(); h.Redeem("heavy-jumps", "heavy"); await h.Tick();
            check(h.Engine.ActiveEffects.Single().Key == "moon-jump" && h.Engine.PendingEffects.Single().Key == "heavy-jumps",
                "new rewards: heavy jumps queues behind Moon Jump's Air ownership");
            await h.End("moon-jump");
            check(h.Sink.IsFulfilled("heavy") && h.Game.Get("movement.base_jump_height") == 80,
                "new rewards: heavy jumps starts from restored base values after Moon Jump");
            await h.End("heavy-jumps");
        }
        foreach (double original in new[] { -50d, 17, 2500 })
        {
            var h = new Harness(features); h.Game.Set("display.brightness_preview", original); h.Game.Set("display.color_state", 42);
            h.Redeem("flashbang"); await h.Tick();
            check(h.Game.Get("display.brightness_preview") == 5000 && h.Game.Get("display.color_state") == 42,
                $"new rewards: Flashbang5000 changes only brightness from {original}");
            await h.End("flashbang");
            check(h.Game.Get("display.brightness_preview") == original && h.Game.Get("display.color_state") == 42 && h.Game.Count("display.restore_loaded") == 0,
                $"new rewards: Flashbang restores exact {original} without resetting colors");
        }
        foreach (double external in new[] { 600d, 4999, 4995 })
        {
            var h = new Harness(features); h.Redeem("flashbang"); await h.Tick(); h.Game.Set("display.brightness_preview", external);
            await h.End("flashbang");
            check(h.Game.Get("display.brightness_preview") == external && h.Game.Count("display.brightness_preview") == 1,
                $"new rewards: Flashbang cleanup preserves external brightness {external} without a restore write");

            var sustained = new Harness(features); sustained.Redeem("flashbang"); await sustained.Tick();
            sustained.Game.Set("display.brightness_preview", external); await sustained.Tick(2);
            check(sustained.Game.Get("display.brightness_preview") == 5000 && sustained.Game.Count("display.brightness_preview") == 2,
                $"new rewards: Flashbang sustain recognizes exact external brightness {external} and captures it");
            await sustained.End("flashbang");
            check(sustained.Game.Get("display.brightness_preview") == external && sustained.Game.Count("display.brightness_preview") == 3,
                $"new rewards: Flashbang restores external brightness {external} captured during sustain");
        }
        {
            // Other continuous float features retain their existing tolerance.
            var h = new Harness(features); h.Redeem("slow-mo"); await h.Tick(); h.Game.Set("time.multiplier", .501);
            await h.Tick(2); check(h.Game.Count("time.multiplier") == 1, "brightness ownership fix keeps other feature sustain tolerance");
            await h.End("slow-mo"); check(h.Game.Get("time.multiplier") == 1, "brightness ownership fix keeps other feature restore tolerance");
        }
        check(EffectCatalog.Find("heavy-jumps")!.Prompt.Contains("Gravity is unchanged") && EffectCatalog.Find("heavy-jumps")!.Prompt.Contains("High Jump"),
            "new rewards: heavy jumps states fallback height and gravity limits");
        check(EffectCatalog.Find("flashbang")!.Group == "display" && EffectCatalog.Find("flashbang")!.Prompt.Contains("depends on the scene"),
            "new rewards: Flashbang retains display conflict group and states its visual limit");

        async Task Waits(string key, string feature, double? value)
        {
            var h = new Harness(features);
            if (value.HasValue) h.Game.Set(feature, value.Value); else h.Game.Values.Remove(map.Get(feature).ValueSlot);
            h.Redeem(key); await h.Tick();
            check(h.Game.Commands.Count == 0 && h.Engine.PendingEffects.Count == 1 && !h.Sink.IsRefunded("a"),
                $"new rewards: {key} waits without write for {feature}={value}");
        }
        async Task Refunds(string key, string feature, double value)
        {
            var h = new Harness(features); h.Game.Set(feature, value); h.Redeem(key); await h.Tick();
            check(h.Game.Commands.Count == 0 && h.Sink.IsRefunded("a"), $"new rewards: {key} refunds no-op {feature}={value}");
        }
    }
}
