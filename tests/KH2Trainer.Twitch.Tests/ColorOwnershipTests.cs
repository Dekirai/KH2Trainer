using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class ColorOwnershipTests
{
    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var definition = EffectCatalog.Find("color-chaos")!;
        var map = new FeatureMap(features);
        var now = new DateTimeOffset(2026, 10, 7, 12, 0, 0, TimeSpan.Zero);
        EffectContext Context(FakeGame game) => new(definition, new("c", definition.Key, "Viewer", "", now), 60, 0,
            game, map, new Random(3), _ => Task.CompletedTask);
        check(definition.Features.SequenceEqual(["display.color_compare_apply", "display.color_state"]),
            "color ownership: no loaded-settings or brightness command is declared");
        for (int mode = 0; mode <= 3; mode++) for (int severity = 0; severity <= 10; severity++)
        {
            if (mode == 0 ? severity != 0 : severity == 0) continue;
            var game = new FakeGame(features); game.Set("display.color_state", mode * 16 + severity); game.Set("display.brightness_preview", 23);
            var context = Context(game); await definition.Start(context);
            double applied = game.Get("display.color_state")!.Value;
            check(applied is >= 26 and <= 58 && applied % 16 == 10 && applied != mode * 16 + severity,
                $"color ownership: {mode}/{severity} starts a different full-strength filter");
            game.Set("display.brightness_preview", -13); await definition.End!(context); await definition.End(context);
            check(game.Get("display.color_state") == mode * 16 + severity && game.ColorWrites == 2 && game.Count("display.color_compare_apply") == 2,
                $"color ownership: exact {mode}/{severity} restored once, repeated end is inert");
            check(game.Get("display.brightness_preview") == -13 && game.Count("display.restore_loaded") == 0 && game.Count("display.brightness_preview") == 0,
                $"color ownership: {mode}/{severity} cleanup preserves an external brightness change");
        }
        foreach (double invalid in new[] { -1d, 1, 10, 16, 27, 32, 43, 48, 59, .5, double.NaN, double.PositiveInfinity })
        {
            var game = new FakeGame(features); game.Set("display.color_state", invalid); var context = Context(game);
            check(definition.Check!(context).Kind == ReadinessKind.Wait, $"color ownership: invalid packed value {invalid} waits");
            bool deferred = false; try { await definition.Start(context); } catch (EffectDeferredException) { deferred = true; }
            check(deferred && game.Commands.Count == 0, "color ownership: invalid packed state cannot send an apply command");
        }
        {
            var game = new FakeGame(features); game.Values.Remove(map.Get("display.color_state").ValueSlot); var context = Context(game);
            bool deferred = false; try { await definition.Start(context); } catch (EffectDeferredException) { deferred = true; }
            check(deferred && game.Commands.Count == 0 && definition.Check!(context).Kind == ReadinessKind.Wait,
                "color ownership: missing coherent readback blocks start before any write");
        }
        foreach (bool severityOnly in new[] { false, true })
        {
            var game = new FakeGame(features); var context = Context(game); await definition.Start(context);
            int applied = (int)game.Get("display.color_state")!.Value;
            int external = severityOnly ? applied - 1 : (applied / 16 % 3 + 1) * 16 + 10;
            game.Set("display.color_state", external); await definition.End!(context); await definition.End(context);
            check(game.Get("display.color_state") == external && game.ColorWrites == 1 && game.Count("display.color_compare_apply") == 2,
                "color ownership: external " + (severityOnly ? "strength" : "mode") + " edit wins and ends ownership");
        }
        {
            var game = new FakeGame(features); game.Set("display.color_state", 21); var context = Context(game);
            game.NativeColorOverride = 39; // Native setting changes after the host's packed observation.
            bool rejected = false; try { await definition.Start(context); } catch (InvalidOperationException) { rejected = true; }
            await definition.End!(context);
            check(rejected && game.NativeColorOverride == 39 && game.ColorWrites == 0 && !context.State.ContainsKey("colorOwned"),
                "color ownership: stale start is rejected without capturing false ownership");
        }
        {
            var game = new FakeGame(features); game.Set("display.color_state", 21); var context = Context(game); await definition.Start(context);
            int applied = (int)game.Get("display.color_state")!.Value;
            game.NativeColorOverride = applied - 1; // Host still reports the owned pair.
            await definition.End!(context);
            check(game.NativeColorOverride == applied - 1 && game.ColorWrites == 1 && context.State["colorOwned"] == 0,
                "color ownership: native restore comparison protects an edit after the host snapshot");
        }
        {
            var game = new FakeGame(features); game.Set("display.color_state", 37); var context = Context(game); await definition.Start(context);
            game.NativeColorOverride = (int)game.Get("display.color_state")!.Value;
            game.Values.Remove(map.Get("display.color_state").ValueSlot); await definition.End!(context);
            check(game.NativeColorOverride == 37 && game.ColorWrites == 2,
                "color ownership: native matching restore works without trusting a missing host readback");
        }
        {
            var game = new FakeGame(features); var context = Context(game); await definition.Start(context);
            game.Gameplay = new(true, PlayerRole.Mickey, GameplayBlockers.Menu);
            bool deferred = false; try { await definition.End!(context); } catch (EffectDeferredException) { deferred = true; }
            check(deferred && game.Commands.Count == 1 && context.State["colorOwned"] == 1,
                "color ownership: paused cleanup sends no command and retains retry state");
            game.Gameplay = new(true, PlayerRole.Mickey, GameplayBlockers.None);
            game.Reject = (f, a) => f == "display.color_compare_apply" && a[0] == 1;
            deferred = false; try { await definition.End!(context); } catch (EffectDeferredException) { deferred = true; }
            check(deferred && context.State["colorOwned"] == 1 && game.ColorWrites == 1,
                "color ownership: failed restore is retained and never silently settled");
            game.Reject = null; await definition.End!(context);
            check(game.Get("display.color_state") == 0 && game.ColorWrites == 2 && context.State["colorOwned"] == 0,
                "color ownership: restore retries after control and native availability recover");
        }
    }
}
