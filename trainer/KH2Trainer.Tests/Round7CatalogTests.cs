using KH2Trainer.Core;

internal static class Round7CatalogTests
{
    public static void Run(IReadOnlyList<FeatureDefinition> catalog, Action<bool, string> check)
    {
        var window = catalog.Where(f => f.CapabilitySlot is >= 431 and <= 438).OrderBy(f => f.CapabilitySlot).ToArray();
        check(window.Select(f => f.CapabilitySlot).SequenceEqual(Enumerable.Range(431, 8)),
            "Window requests and diagnostics occupy their complete assigned range");
        check(window.All(f => !f.RequiresScene && !f.CanSaveInProfile && !f.ChangesProgression),
            "Window requests use renderer readiness and cannot replay through profiles");
        if (window.Length == 8)
        {
            check(window[0].Kind == FeatureKind.Action && window[0].CommandId == 1431 && window[0].ValueSlot == -1 &&
                window[0].Arguments.Select(a => (a.Minimum, a.Maximum)).SequenceEqual(new[] { (640.0, 7680.0), (360.0, 4320.0) }),
                "Window sizing sends two bounded dimensions in native width/height order");
            check(window[1].Kind == FeatureKind.Action && window[1].CommandId == 1432 && window[1].ValueSlot == -1 && window[1].Arguments.Count == 0,
                "Maximize issues one parameterless action");
            check(window.Skip(2).All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0 && f.ValueSlot == f.CapabilitySlot && f.Arguments.Count == 0),
                "Actual window state is exposed only as diagnostics");
        }
        check(!catalog.Any(f => f.CapabilitySlot is >= 439 and <= 446),
            "Unfinished Gummi history operations have no public commands");
        var aa = catalog.Where(f => f.CapabilitySlot is >= 447 and <= 455).OrderBy(f => f.CapabilitySlot).ToArray();
        check(aa.Select(f => f.CapabilitySlot).SequenceEqual(Enumerable.Range(447, 9)) &&
            aa.All(f => !f.RequiresScene && !f.CanSaveInProfile && !f.ChangesProgression),
            "MSAA policy has nine distinct controls with no automatic profile replay");
        if (aa.Length == 9)
        {
            check(aa[0].Kind == FeatureKind.Action && aa[0].CommandId == 1447 && aa[0].ValueSlot == -1 && aa[0].Arguments.Count == 2,
                "Apply MSAA sends a single paired mode/sample request");
            if (aa[0].Arguments.Count == 2)
            {
                check(aa[0].Arguments[0].Choices.Select(c => c.Value).SequenceEqual(new[] { 1.0, 2.0 }) &&
                    aa[0].Arguments[1].Choices.Select(c => c.Value).SequenceEqual(new[] { 1.0, 2.0, 4.0, 8.0 }),
                    "MSAA choices use fixed/maximum modes and powers-of-two sample counts");
            }
            check(aa[1].Kind == FeatureKind.Action && aa[1].CommandId == 1448 && aa[1].Arguments.Count == 0,
                "Restore native MSAA requires no replacement policy arguments");
            check(aa.Skip(2).All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0 && f.ValueSlot == f.CapabilitySlot),
                "MSAA decision history and status are readouts");
        }
        foreach (var feature in window.Concat(aa))
        {
            bool rejected = false;
            try { ProfileStore.Validate(new TrainerProfile { Name = "Window replay fixture", Values = new() { [feature.Id] = feature.DefaultValue } }, catalog); }
            catch (InvalidDataException) { rejected = true; }
            check(rejected, "Profiles reject " + feature.Id);
        }
    }
}
