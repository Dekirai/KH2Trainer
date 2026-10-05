using KH2Trainer.Core;

internal static class Round5CatalogTests
{
    public static void Run(IReadOnlyList<FeatureDefinition> catalog, Action<bool, string> check)
    {
        var renderer = catalog.Where(f => f.CapabilitySlot is >= 392 and <= 407).OrderBy(f => f.CapabilitySlot).ToArray();
        var audio = catalog.Where(f => f.CapabilitySlot is >= 408 and <= 418).OrderBy(f => f.CapabilitySlot).ToArray();
        var editor = catalog.Where(f => f.CapabilitySlot is >= 424 and <= 430).OrderBy(f => f.CapabilitySlot).ToArray();
        check(renderer.Length == 16 && audio.Length == 11 && editor.Length == 7,
            "Renderer, spatial audio and editor contracts occupy their complete distinct slot ranges");
        var all = renderer.Concat(audio).Concat(editor).ToArray();
        check(all.Length == 34 && all.All(f => !f.RequiresScene && !f.CanSaveInProfile && !f.ChangesProgression),
            "Round5 features use their own subsystem readiness and cannot persist through profiles or progression");
        check(renderer.Concat(audio).All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0 &&
            f.ValueSlot == f.CapabilitySlot && f.Arguments.Count == 0),
            "Renderer and listener diagnostics cannot issue mutations");
        check(!catalog.Any(f => f.CapabilitySlot is >= 419 and <= 423), "Reserved listener slots are not advertised");
        if (editor.Length == 7)
        {
            check(editor[0].Kind == FeatureKind.Action && editor[0].CommandId == 1424 && editor[0].ValueSlot == -1 &&
                editor[0].Arguments.Count == 0, "Editor reset invokes one parameterless native action");
            check(editor[1].Kind == FeatureKind.Number && editor[1].CommandId == 1425 && editor[1].ValueSlot == -1 && editor[1].Minimum == 20 &&
                editor[1].Maximum == 90 && editor[1].IsValidValue(20) && editor[1].IsValidValue(90) &&
                !editor[1].IsValidValue(19.99) && !editor[1].IsValidValue(90.01) && !editor[1].IsValidValue(double.NaN),
                "Editor preview FOV preserves the native projection policy at both bounds");
            check(editor.Skip(2).All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0 && f.ValueSlot == f.CapabilitySlot),
                "Editor pose, transition and phase controls are diagnostics");
        }
        foreach (var feature in all)
        {
            bool rejected = false;
            try { ProfileStore.Validate(new TrainerProfile { Name = "Nonreplayable subsystem fixture", Values = new() { [feature.Id] = feature.DefaultValue } }, catalog); }
            catch (InvalidDataException) { rejected = true; }
            check(rejected, "Profiles reject " + feature.Id);
        }
    }
}
