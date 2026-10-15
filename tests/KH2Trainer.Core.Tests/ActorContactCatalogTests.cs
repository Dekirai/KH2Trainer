using KH2Trainer.Core;

internal static class ActorContactCatalogTests
{
    public static void Run(IReadOnlyList<FeatureDefinition> catalog, Action<bool, string> check)
    {
        var rows = catalog.Where(f => f.CapabilitySlot is >= 493 and <= 498).OrderBy(f => f.CapabilitySlot).ToArray();
        check(rows.Select(f => f.Id).SequenceEqual(new[] {
            "actor.sora.reference_count", "actor.sora.retirement_requested", "actor.sora.retirement_marked",
            "actor.target.reference_count", "actor.target.retirement_requested", "actor.target.retirement_marked" }),
            "Actor reference observations use the six assigned independent Sora/target slots");
        check(rows.All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0 && f.ValueSlot == f.CapabilitySlot &&
            f.Arguments.Count == 0 && f.Category == "Actor reference diagnostics" && f.RequiresScene &&
            !f.ChangesProgression && !f.CanSaveInProfile), "Actor reference observations are visible readouts with no action or profile replay");
        foreach (var row in rows)
        {
            bool counter = row.CapabilitySlot is 493 or 496;
            check(row.Minimum == 0 && row.Maximum == (counter ? uint.MaxValue : 1) && row.Step == 1 && row.DefaultValue == 0,
                "Actor reference field range preserves unsigned counter or distinct flag: " + row.Id);
            if (counter) check(row.Description.Contains("Scripts, commands and attacks can contribute") && row.Description.Contains("not a count of attacks or unique objects") && row.IsValidValue(uint.MaxValue),
                "Multiple reference sources and full UInt32 range are explicit: " + row.Id);
            bool rejected = false;
            try { ProfileStore.Validate(new TrainerProfile { Name = "Actor reference diagnostic replay", Values = new() { [row.Id] = 1 } }, catalog); }
            catch (InvalidDataException) { rejected = true; }
            check(rejected, "Actor readout cannot issue a command through a profile: " + row.Id);
        }
    }
}
