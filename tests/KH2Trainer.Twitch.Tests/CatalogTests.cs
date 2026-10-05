using KH2Trainer.Core;
using KH2Trainer.Twitch;

/// <summary>Every effect is checked against the real trainer catalog and run once on a fake game.</summary>
internal static class CatalogTests
{
    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        var map = new FeatureMap(features);
        var all = EffectCatalog.All;
        check(all.Count >= 50, $"catalog offers many effects ({all.Count})");
        check(all.Select(e => e.Key).Distinct().Count() == all.Count, "effect keys are unique");
        foreach (RewardCategory category in Enum.GetValues<RewardCategory>())
            check(all.Count(e => e.Category == category) >= 5, $"category {category} has at least five effects");

        foreach (var language in new[] { RewardLanguage.English, RewardLanguage.German })
        {
            var settings = new TwitchSettings { Language = language };
            var titles = all.Select(e => RewardResolver.Title(e, settings)).ToArray();
            check(titles.Distinct(StringComparer.OrdinalIgnoreCase).Count() == titles.Length, $"{language} titles are unique (Twitch requires unique titles)");
            foreach (var effect in all)
            {
                var spec = RewardResolver.Spec(effect, settings);
                check(spec.Validate() is null, $"{language} {effect.Key}: Twitch accepts the default reward ({spec.Validate()})");
            }
        }

        foreach (var effect in all)
        {
            check(effect.Cost >= 1, $"{effect.Key}: cost is at least 1");
            check(effect.Features.Count > 0 && effect.Features.All(map.Contains), $"{effect.Key}: every listed feature exists in the trainer catalog");
            check(!effect.Interrupts || effect.Group != null, $"{effect.Key}: an interrupting effect belongs to a group");
            check(effect.Amount == 0 || effect.AmountLabel.Length > 0, $"{effect.Key}: an amount has a label");
        }

        // Run every effect on a fresh fake game: commands must be valid and only use listed features.
        var setByTimed = new Dictionary<string, List<EffectDefinition>>();
        foreach (var effect in all)
        {
            var game = new FakeGame(features);
            game.Stock[1] = 5; game.Stock[2] = 5; game.Stock[3] = 5;
            game.Set("target_lock_mode", 2); game.Set("target_hp", 500); game.Set("target_revenge_threshold", 100);
            game.Set("gummi.hp", 50);
            if (effect.Key == "revert") game.Set("player.form.id", 1);
            if (effect.Key is "heal" or "restore-mp" or "full-restore") { game.Set("player.hp", 10); game.Set("player.mp", 10); }
            var context = new EffectContext(effect, new Redemption("r", effect.Key, "Viewer", "", DateTimeOffset.UtcNow, IsTest: true),
                effect.DurationSeconds, effect.Amount, game, map, new Random(7), _ => Task.CompletedTask);
            var readiness = effect.Check?.Invoke(context) ?? Readiness.Ready;
            check(readiness.Kind == ReadinessKind.Ready, $"{effect.Key}: ready in a normal scene ({readiness.Reason})");
            try
            {
                await effect.Start(context);
                if (effect.IsTimed)
                {
                    context.EndReason = EndReason.Expired;
                    await (effect.End ?? (c => c.RestoreAsync()))(context);
                }
                check(true, $"{effect.Key}: starts and ends with valid commands");
            }
            catch (Exception error) { check(false, $"{effect.Key}: starts and ends with valid commands ({error.Message})"); }
            var allowed = new HashSet<string>(effect.Features, StringComparer.Ordinal);
            var unlisted = game.Commands.Select(c => c.Feature).Where(f => !allowed.Contains(f)).Distinct().ToArray();
            check(unlisted.Length == 0, $"{effect.Key}: uses only its listed features ({string.Join(", ", unlisted)})");
            if (effect.IsTimed)
                foreach (string feature in game.Commands.Select(c => c.Feature).Distinct().Where(f => map.Get(f).Kind != FeatureKind.Action))
                    (setByTimed.TryGetValue(feature, out var list) ? list : setByTimed[feature] = []).Add(effect);
        }
        foreach (var (feature, users) in setByTimed)
        {
            var groups = users.Select(u => u.Group ?? u.Key).Distinct().ToArray();
            check(groups.Length == 1, $"timed effects that change {feature} share one group ({string.Join(", ", users.Select(u => u.Key))})");
        }

        // Restoring: a timed effect leaves the values as they were before it started.
        foreach (var effect in all.Where(e => e.IsTimed && e.Group is not ("form" or "position" or "debug")))
        {
            var game = new FakeGame(features);
            game.Set("target_lock_mode", 2); game.Set("target_hp", 500);
            var before = new Dictionary<int, double>(game.Values);
            var context = new EffectContext(effect, new Redemption("r", effect.Key, "Viewer", "", DateTimeOffset.UtcNow, IsTest: true),
                effect.DurationSeconds, effect.Amount, game, map, new Random(1), _ => Task.CompletedTask);
            await effect.Start(context);
            context.EndReason = EndReason.Expired;
            await (effect.End ?? (c => c.RestoreAsync()))(context);
            var changed = before.Where(p => !game.Values.TryGetValue(p.Key, out double now) || Math.Abs(now - p.Value) > 0.001)
                .Select(p => features.First(f => f.ValueSlot == p.Key).Id)
                // Setting the FOV value re-enables the override, so a disabled override keeps the last value but is off again.
                .Where(id => !(effect.Group == "fov" && id == "camera.fov" && game.Get("camera.fov_enabled") == 0)).ToArray();
            check(changed.Length == 0, $"{effect.Key}: all values are restored at the end ({string.Join(", ", changed)})");
        }

        // German defaults and the duration/amount suffix.
        var german = new TwitchSettings { Language = RewardLanguage.German };
        var regen = EffectCatalog.Find("regen")!;
        check(RewardResolver.Prompt(regen, german).EndsWith("Dauer: 60 s.", StringComparison.Ordinal), "German prompt states the duration");
        german.For("regen").DurationSeconds = 90;
        check(RewardResolver.Options(regen, german).DurationSeconds == 90 && RewardResolver.Prompt(regen, german).Contains("90 s"), "custom duration reaches options and prompt");
        german.For("regen").DurationSeconds = 99999;
        check(RewardResolver.Duration(regen, german) == german.MaxDurationSeconds, "duration is capped by the maximum");
        german.For("regen").Title = "  Mein Titel  ";
        check(RewardResolver.Title(regen, german) == "Mein Titel", "custom titles are trimmed");
        var munny = EffectCatalog.Find("munny-gift")!;
        check(RewardResolver.Prompt(munny, new TwitchSettings()).Contains("1,000 munny") || RewardResolver.Prompt(munny, new TwitchSettings()).Contains("1.000 munny"),
            "amount appears in the prompt");
        check(new RewardSpec(new string('x', 46), 1, "", "#000000", 0, 0, 0).Validate() != null, "titles over 45 characters are rejected");
        check(new RewardSpec("ok", 0, "", "#000000", 0, 0, 0).Validate() != null, "cost 0 is rejected");
    }
}
