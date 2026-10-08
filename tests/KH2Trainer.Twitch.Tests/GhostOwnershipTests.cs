using KH2Trainer.Core;
using KH2Trainer.Twitch;

/// <summary>Host cleanup must respect a rejected native bookmark, including when the room looks unchanged.</summary>
internal static class GhostOwnershipTests
{
    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var definition = EffectCatalog.Find("ghost-walk")!;
        var map = new FeatureMap(features);
        var now = new DateTimeOffset(2026, 10, 7, 20, 0, 0, TimeSpan.Zero);
        EffectContext Context(FakeGame game) => new(definition, new("ghost", definition.Key, "Viewer", "", now),
            12, 0, game, map, new Random(3), _ => Task.CompletedTask);
        bool NoFallback(FakeGame game) => game.Count("world.reload_room") == 0 &&
            new[] { "x", "y", "z" }.All(axis => game.Count("player.position." + axis) == 0);
        void PopulateCoordinates(FakeGame game)
        {
            game.Set("world.current_world", 2); game.Set("world.current_room", 3);
            game.Set("player.position.x", 100); game.Set("player.position.y", 200); game.Set("player.position.z", 300);
        }
        check(definition.Features.SequenceEqual(["player.position.bookmark", "player.position.return", "combat.movementcollision", "drive.phase"]),
            "ghost: only bookmark, native return, collision and transition capabilities are required");
        {
            var game = new FakeGame(features); PopulateCoordinates(game); var context = Context(game);
            await definition.Start(context); await definition.End!(context);
            check(game.Commands.Select(c => c.Feature).SequenceEqual(["player.position.bookmark", "combat.movementcollision", "player.position.return", "combat.movementcollision"]),
                "ghost: native return precedes collision release and follows native bookmark capture");
            check(game.Get("combat.movementcollision") == 0 && !context.HasPendingRestores && NoFallback(game),
                "ghost: successful native return finishes cleanup without coordinate writes or a reload");
        }
        foreach (bool sameRoom in new[] { false, true })
        foreach (bool haveCoordinates in new[] { false, true })
        {
            var game = new FakeGame(features); if (haveCoordinates) PopulateCoordinates(game);
            var context = Context(game); await definition.Start(context);
            if (!sameRoom) game.Set("world.current_room", 9);
            game.Reject = (id, _) => id == "player.position.return";
            await definition.End!(context);
            check(game.Count("player.position.return") == 1 && NoFallback(game),
                $"ghost: native rejection is final for position (same room={sameRoom}, coordinates={haveCoordinates})");
            check(game.Get("combat.movementcollision") == 0 && !context.HasPendingRestores,
                "ghost: rejected native return still releases the owned collision setting");
            check(context.Detail == "Return skipped: the saved position is no longer available.",
                "ghost: rejected return leaves a clear result message");
        }
        {
            var game = new FakeGame(features); PopulateCoordinates(game); var context = Context(game);
            await definition.Start(context);
            // Model a generation/scene rejection from the native handler; the host must not second-guess it.
            game.Reject = (id, args) => id == "player.position.return" || id == "combat.movementcollision" && args[0] == 0;
            await definition.End!(context);
            check(context.HasPendingRestores && game.Get("combat.movementcollision") == 1 && NoFallback(game),
                "ghost: rejected collision release remains owned for deferred cleanup");
            game.Reject = null; await context.RestoreAsync();
            check(!context.HasPendingRestores && game.Get("combat.movementcollision") == 0 && game.Count("player.position.return") == 1 && NoFallback(game),
                "ghost: deferred collision-only retry never repeats or bypasses the refused return");
        }
        {
            var game = new FakeGame(features); var context = Context(game); await definition.Start(context);
            game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Menu);
            bool deferred = false; try { await definition.End!(context); } catch (EffectDeferredException) { deferred = true; }
            check(deferred && game.Count("player.position.return") == 0 && context.HasPendingRestores && NoFallback(game),
                "ghost: loss of control defers all cleanup rather than treating it as an accepted return");
            game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.None); await definition.End!(context);
            check(!context.HasPendingRestores && game.Count("player.position.return") == 1 && NoFallback(game),
                "ghost: cleanup resumes through the native return after control returns");
        }
        {
            var game = new FakeGame(features); var context = Context(game); await definition.Start(context);
            game.Reject = (id, _) =>
            {
                if (id != "player.position.return") return false;
                game.Gameplay = new(true, PlayerRole.Sora, GameplayBlockers.Transition); return true;
            };
            bool deferred = false; try { await definition.End!(context); } catch (EffectDeferredException) { deferred = true; }
            check(deferred && context.HasPendingRestores && game.Calls("combat.movementcollision").All(a => a[0] == 1) && NoFallback(game),
                "ghost: transition during return acknowledgement leaves cleanup pending without bypass");
        }
        foreach (bool explicitReason in new[] { false, true })
        {
            var game = new FakeGame(features); PopulateCoordinates(game); var sink = new FakeSink();
            var engine = new EffectEngine(game, map, EffectCatalog.All,
                key => new(key, 1, 0, SameEffectBehavior.Extend, ConflictBehavior.Queue),
                () => new(TimeSpan.FromMinutes(10), 600, true), sink, _ => { }, _ => Task.CompletedTask);
            engine.Submit(new("g", "ghost-walk", "Viewer", "", now)); await engine.TickAsync(now);
            game.Reject = (id, _) => id == "player.position.return";
            if (explicitReason) await engine.StopAllAsync("Stopped for a scene change", now.AddSeconds(.25));
            else for (int i = 1; i <= 6; i++) await engine.TickAsync(now.AddSeconds(i * .25));
            var ended = engine.RecentEvents.Last(e => e.Kind == EffectEventKind.Ended && e.Key == "ghost-walk");
            string expected = explicitReason ? "Stopped for a scene change" : "Return skipped: the saved position is no longer available.";
            check(ended.Detail == expected && ended.Text.Contains(expected),
                explicitReason ? "ghost: explicit stop reason takes precedence over cleanup detail" : "ghost: natural end publishes return refusal in the activity detail and text");
            check(NoFallback(game) && game.Get("combat.movementcollision") == 0,
                "ghost: engine cleanup preserves native refusal and restores only collision ownership");
        }
    }
}
