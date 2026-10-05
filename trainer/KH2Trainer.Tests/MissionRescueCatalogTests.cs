using KH2Trainer.Core;

internal static class MissionRescueCatalogTests
{
    public static void Run(IReadOnlyList<FeatureDefinition> catalog, string workspace, Action<bool, string> check)
    {
        var byId = catalog.ToDictionary(f => f.Id, StringComparer.Ordinal);
        string[] actions = ["mission.timer.countdown", "mission.timer.countup", "rescue.use_count"];
        bool complete = actions.All(byId.ContainsKey);
        check(complete, "packaged catalog contains native mission restarts and the separate rescue-use counter");
        if (!complete) return;

        var mission = catalog.Where(f => f.Id.StartsWith("mission.", StringComparison.Ordinal) && f.CapabilitySlot <= 229).OrderBy(f => f.CapabilitySlot).ToArray();
        check(mission.Select(f => f.CapabilitySlot).SequenceEqual(Enumerable.Range(208, 22)) &&
            mission.All(f => catalog.Count(other => other.CapabilitySlot == f.CapabilitySlot) == 1),
            "Mission slots208..229 are complete and have no cross-domain collision");
        check(mission.Where(f => f.CapabilitySlot is not (226 or 227)).All(f =>
            f.Kind == FeatureKind.ReadOnly && f.CommandId == 0 && f.ValueSlot == f.CapabilitySlot && f.Arguments.Count == 0),
            "Mission counters, gauges and lifecycle diagnostics issue no commands");
        var countdown = byId[actions[0]];
        check(countdown is { Kind: FeatureKind.Action, CapabilitySlot: 226, CommandId: 1226, ValueSlot: -1,
            Minimum: 1, Maximum: 3599, Step: 1, RequiresScene: true, CanSaveInProfile: false } &&
            countdown.Arguments.Count == 1 && countdown.Arguments[0] is { Minimum: 1, Maximum: 3599, DefaultValue: 120 },
            "Countdown action sends one bounded whole-seconds argument to the native timer route");
        var countup = byId[actions[1]];
        check(countup is { Kind: FeatureKind.Action, CapabilitySlot: 227, CommandId: 1227, ValueSlot: -1,
            Minimum: 0, Maximum: 0, RequiresScene: true, CanSaveInProfile: false } && countup.Arguments.Count == 0,
            "Count-up action has no invented timer-limit argument and uses the existing mission configuration");
        var rescue = byId[actions[2]];
        check(rescue is { Kind: FeatureKind.Number, CapabilitySlot: 176, ValueSlot: 176, CommandId: 1176,
            Minimum: 0, Maximum: 999, Step: 1, ChangesProgression: true, CanSaveInProfile: false } &&
            catalog.Where(f => f.Id.StartsWith("rescue.", StringComparison.Ordinal) && f.Id != rescue.Id)
                .All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0),
            "Only the recorded rescue-use counter is editable; appearance/probability diagnostics remain read-only");

        bool Rejected(string id, double value)
        {
            try
            {
                ProfileStore.Validate(new TrainerProfile { Name = "Mission/rescue non-replayable fixture", Values = new() { [id] = value } }, catalog);
                return false;
            }
            catch (InvalidDataException) { return true; }
        }
        check(mission.All(f => !f.CanSaveInProfile) && actions.All(id => Rejected(id, byId[id].DefaultValue)),
            "Profiles cannot replay one-time mission restarts or saved rescue-counter edits");
        var events = catalog.Where(f => f.CapabilitySlot is >= 230 and <= 232).OrderBy(f=>f.CapabilitySlot).ToArray();
        check(events.Select(f=>f.CapabilitySlot).SequenceEqual(new[]{230,231,232}) && events.All(f=>
            f.Kind==FeatureKind.Action && f.ChangesProgression && !f.CanSaveInProfile && f.RequiresScene && f.ValueSlot==-1),
            "native mission event setters disclose progression effects and stay explicit one-time actions");
        check(events.Where(f=>f.CapabilitySlot!=232).All(f=>f.Arguments.Count==2 && f.Arguments[0].Minimum==0 && f.Arguments[0].Maximum==2) &&
            events.Single(f=>f.CapabilitySlot==232).Arguments.Count==1,
            "counter/gauge send index plus value while score sends exactly one value");
        check(events.All(f=>Rejected(f.Id,f.DefaultValue)),"profiles cannot replay mission boundary events or score changes");
    }
}
