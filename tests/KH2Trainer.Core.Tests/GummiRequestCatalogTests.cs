using System.Text.Json;
using KH2Trainer.Core;

internal static class GummiRequestCatalogTests
{
    public static void Run(IReadOnlyList<FeatureDefinition> catalog, string workspace, Action<bool, string> check)
    {
        var feature = catalog.Single(f => f.Id == "gummi.request_special_attack");
        check(feature is { Category: "Gummi controls", Kind: FeatureKind.Action, CommandId: 1485,
            CapabilitySlot: 485, ValueSlot: -1, Minimum: 0, Maximum: 0, DefaultValue: 0,
            RequiresScene: false, ChangesProgression: false, CanSaveInProfile: false } && feature.Arguments.Count == 0,
            "special-weapon request is one parameterless Gummi action with independent native mission gates");
        check(catalog.Count(f => f.CommandId == 1485 || f.CapabilitySlot == 485) == 1,
            "special-weapon request command and capability have one catalog owner");
        var readouts = catalog.Where(f => f.CapabilitySlot is >= 324 and <= 326).OrderBy(f => f.CapabilitySlot).ToArray();
        check(readouts.Select(f => f.Id).SequenceEqual(new[] { "gummi.special_stock", "gummi.special_progress", "gummi.special_phase" }) &&
            readouts.All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0),
            "the action keeps stock, progress and phase as separate observations");
        var store = new ProfileStore(Path.Combine(workspace, "gummi-request-profiles"));
        var profile = new TrainerProfile { Name = "Request", Values = new() { [feature.Id] = 0 } };
        try { store.Save(profile, catalog); check(false, "request cannot be saved in a profile"); }
        catch (InvalidDataException) { check(true, "request cannot be saved in a profile"); }
        string injected = Path.Combine(workspace, "injected-gummi-request.json");
        File.WriteAllText(injected, JsonSerializer.Serialize(profile, FeatureCatalog.JsonOptions));
        try { store.Read(injected, catalog); check(false, "edited profile cannot replay a special request"); }
        catch (InvalidDataException) { check(true, "edited profile cannot replay a special request"); }
    }
}
