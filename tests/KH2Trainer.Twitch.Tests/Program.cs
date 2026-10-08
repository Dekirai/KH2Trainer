using System.Globalization;
using KH2Trainer.Core;

// Run under a locale with different number formatting: texts must not depend on the PC's regional settings.
CultureInfo.DefaultThreadCurrentCulture = CultureInfo.DefaultThreadCurrentUICulture = CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("fr-FR");

int passed = 0, failed = 0;
var gate = new object();
void Check(bool condition, string name)
{
    lock (gate)
    {
        Console.WriteLine((condition ? "PASS " : "FAIL ") + name);
        if (condition) passed++; else failed++;
    }
}

if (args.Length < 1 || !File.Exists(args[0]))
{
    Console.Error.WriteLine("Usage: KH2Trainer.Twitch.Tests <path to features.json>");
    return 2;
}
IReadOnlyList<FeatureDefinition> features;
using (var stream = File.OpenRead(args[0])) features = FeatureCatalog.Load(stream);

await Run("catalog", () => CatalogTests.RunAsync(features, Check));
await Run("engine", () => EngineTests.RunAsync(features, Check));
await Run("gameplay readiness", () => GameplayReadinessTests.RunAsync(features, Check));
await Run("color ownership", () => ColorOwnershipTests.RunAsync(features, Check));
await Run("health roles", () => HealthRoleTests.RunAsync(features, Check));
await Run("MP availability", () => MpAvailabilityTests.RunAsync(features, Check));
await Run("movement rewards", () => MovementRewardTests.RunAsync(features, Check));
await Run("ghost return ownership", () => GhostOwnershipTests.RunAsync(features, Check));
await Run("damage guard ownership", () => DamageGuardOwnershipTests.RunAsync(features, Check));
await Run("lock-on pair ownership", () => LockOnPairOwnershipTests.RunAsync(features, Check));
await Run("api", () => ApiTests.RunAsync(Check));
await Run("service", () => ServiceTests.RunAsync(Check));
await Run("overlay", () => OverlayTests.RunAsync(features, Check));

Console.WriteLine($"{passed} passed, {failed} failed");
return failed == 0 ? 0 : 1;

async Task Run(string name, Func<Task> suite)
{
    try { await suite().WaitAsync(TimeSpan.FromMinutes(2)); }
    catch (Exception error) { Check(false, $"{name} suite crashed: {error}"); }
}
