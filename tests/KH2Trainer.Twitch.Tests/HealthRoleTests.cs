using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class HealthRoleTests
{
    private sealed class Harness
    {
        public readonly FakeGame Game;
        public readonly FakeSink Sink = new();
        public readonly EffectEngine Engine;
        public DateTimeOffset Now = new(2026, 10, 7, 12, 0, 0, TimeSpan.Zero);
        public Harness(IReadOnlyList<FeatureDefinition> features, PlayerRole role)
        {
            Game = new(features) { Gameplay = new(true, role, GameplayBlockers.None) };
            Engine = new(Game, new(features), EffectCatalog.All,
                key => { var d = EffectCatalog.Find(key)!; return new(d.Title, d.DurationSeconds, d.Amount, SameEffectBehavior.Extend, ConflictBehavior.Queue); },
                () => new(TimeSpan.FromMinutes(10), 600, true), Sink, _ => { }, _ => Task.CompletedTask);
        }
        public void Redeem(string key, string id = "a") => Engine.Submit(new(id, key, "Viewer", "", Now));
        public Task Tick(double elapsed = .25) { Now = Now.AddSeconds(elapsed); return Engine.TickAsync(Now); }
    }

    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        string[] keys = ["heal", "full-restore", "one-hp", "regen", "infinite-mp", "restore-mp"];
        var map = new FeatureMap(features);
        foreach (string key in keys)
        {
            var definition = EffectCatalog.Find(key)!;
            check(definition.AllowedRoles == EffectPlayerRoles.FieldPlayers, $"health roles: {key} explicitly allows the three audited roles");
            check(!definition.Prompt.Contains("Sora's", StringComparison.Ordinal) && !definition.PromptDe.Contains("Soras", StringComparison.Ordinal),
                $"health roles: {key} describes the controlled character");
        }
        check(EffectCatalog.Find("heal")!.Title == "Heal Player" && EffectCatalog.Find("heal")!.TitleDe == "Spieler heilen",
            "health roles: healing title no longer excludes Roxas or Mickey");
        foreach (string key in new[] { "slowpoke", "final", "antiform", "exp-gift", "power-boost" })
            check(EffectCatalog.Find(key)!.AllowedRoles == EffectPlayerRoles.Sora, $"health roles: unrelated {key} remains Sora-only");
        check(EffectCatalog.Find("invincible")!.AllowedRoles == EffectPlayerRoles.FieldPlayers,
            "health roles: separately verified owned damage guard supports all three roles");
        check(EffectCatalog.Find("infinite-mp")!.Features.Contains("player.mp.max"), "health roles: unlimited MP declares its gauge observation");

        foreach (var role in Enum.GetValues<PlayerRole>()) foreach (string key in keys)
        {
            var h = new Harness(features, role); h.Redeem(key); await h.Tick();
            bool supported = role is PlayerRole.Sora or PlayerRole.Roxas or PlayerRole.Mickey;
            check((h.Game.Commands.Count > 0) == supported && h.Sink.IsFulfilled("a") == supported,
                $"health roles: {role}/{key} admission uses the explicit role matrix");
            if (!supported)
                check(h.Engine.PendingEffects.Count == 1 && !h.Sink.IsRefunded("a"), $"health roles: {role}/{key} waits for a supported character");
        }
        foreach (var role in new[] { PlayerRole.Sora, PlayerRole.Roxas, PlayerRole.Mickey })
        {
            foreach (string key in keys)
            {
                var h = new Harness(features, role); h.Game.Gameplay = new(true, role, GameplayBlockers.Menu);
                h.Redeem(key); await h.Tick(); await h.Tick(1);
                check(h.Game.Commands.Count == 0 && !h.Sink.IsFulfilled("a"), $"health roles: {role}/{key} waits during a menu");
                h.Game.Gameplay = new(true, role, GameplayBlockers.None); await h.Tick();
                check(h.Sink.IsFulfilled("a"), $"health roles: {role}/{key} starts after control returns");
            }
            foreach (string key in new[] { "restore-mp", "infinite-mp" })
            {
                var zero = new Harness(features, role); zero.Game.Set("player.mp", 0); zero.Game.Set("player.mp.max", 0);
                zero.Redeem(key); await zero.Tick();
                check(zero.Sink.IsRefunded("a") && zero.Game.Commands.Count == 0 && zero.Engine.ActiveEffects.Count == 0,
                    $"health roles: {role}/{key} with no MP gauge refunds before a command");
                var missing = new Harness(features, role); missing.Game.Values.Remove(map.Get("player.mp.max").ValueSlot);
                missing.Redeem(key); await missing.Tick();
                check(missing.Engine.PendingEffects.Count == 1 && missing.Game.Commands.Count == 0 && !missing.Sink.IsRefunded("a"),
                    $"health roles: {role}/{key} missing MP maximum waits instead of assuming zero");
                missing.Game.Set("player.mp.max", 100); await missing.Tick();
                check(missing.Sink.IsFulfilled("a"), $"health roles: {role}/{key} starts after a usable MP gauge appears");
            }
            var full = new Harness(features, role); full.Game.Set("player.hp", 120); full.Game.Set("player.mp", 0); full.Game.Set("player.mp.max", 0);
            full.Redeem("full-restore"); await full.Tick();
            check(full.Sink.IsRefunded("a") && full.Game.Commands.Count == 0, $"health roles: {role} with full HP and no MP has nothing to restore");
            full.Game.Set("player.hp", 60); full.Redeem("full-restore", "damaged"); await full.Tick();
            check(full.Sink.IsFulfilled("damaged") && full.Game.Get("player.hp") == 120 && full.Game.Get("player.mp") == 0,
                $"health roles: {role} can restore damaged HP without an MP gauge");
            var already = new Harness(features, role); already.Game.Set("player.hp", 120); already.Redeem("heal"); await already.Tick();
            check(already.Sink.IsRefunded("a") && already.Game.Count("player.heal") == 0, $"health roles: full-health {role} receives a healing refund");
            var regen = new Harness(features, role); regen.Game.Set("combat.autoheal", 1); regen.Redeem("one-hp"); await regen.Tick();
            check(regen.Engine.PendingEffects.Count == 1 && regen.Game.Count("player.hp") == 0, $"health roles: {role} one-HP waits for regeneration");
        }
        foreach (string key in new[] { "regen", "infinite-mp" })
        {
            string toggle = key == "regen" ? "combat.autoheal" : "combat.fullmp";
            var h = new Harness(features, PlayerRole.Roxas); h.Redeem(key); await h.Tick(); await h.Tick();
            double remaining = h.Engine.ActiveEffects.Single().RemainingSeconds;
            h.Game.Gameplay = new(true, PlayerRole.Mickey, GameplayBlockers.Cutscene); h.Game.Set(toggle, 0);
            for (int i = 0; i < 6; i++) await h.Tick(1);
            check(h.Engine.ActiveEffects.Single().RemainingSeconds == remaining && h.Game.Count(toggle) == 1,
                $"health roles: {key} pauses timer and sustain across an uncontrolled role transition");
            h.Game.Gameplay = new(true, PlayerRole.Mickey, GameplayBlockers.None); await h.Tick();
            check(h.Game.Get(toggle) == 1 && h.Game.Count(toggle) == 2 && h.Engine.ActiveEffects.Single().RemainingSeconds == remaining,
                $"health roles: {key} resumes for controlled Mickey without charging the preceding cutscene");
            h.Game.Gameplay = new(true, PlayerRole.Other, GameplayBlockers.None); await h.Tick();
            await h.Engine.EndEffectAsync(key, h.Now);
            check(h.Game.Get(toggle) == 1 && h.Engine.PendingCleanupCount == 1,
                $"health roles: {key} does not restore against an unsupported player");
            h.Game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); await h.Tick(1);
            check(h.Game.Get(toggle) == 0 && h.Engine.PendingCleanupCount == 0,
                $"health roles: {key} restores once a supported controlled player returns");
        }
    }
}
