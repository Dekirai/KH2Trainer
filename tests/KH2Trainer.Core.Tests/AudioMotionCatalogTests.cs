using KH2Trainer.Core;

internal static class AudioMotionCatalogTests
{
    public static void Run(IReadOnlyList<FeatureDefinition> catalog, string workspace, Action<bool, string> check)
    {
        var byId = catalog.ToDictionary(f => f.Id, StringComparer.Ordinal);
        string[] audioIds = ["audio.master", "audio.music", "audio.effects", "audio.voice", "audio.reset", "audio.bus.count",
            "audio.bus.current0", "audio.bus.current1", "audio.bus.current2", "audio.bus.current3", "audio.bus.current4",
            "audio.bus.current5", "audio.bus.current6", "audio.bus.current7", "audio.bus.current8", "audio.available"];
        string[] motionIds = ["motion.speed", "motion.override", "motion.actual_speed", "motion.frame", "motion.duration",
            "motion.logical_id", "motion.resolved_id", "motion.blend_duration", "motion.blend_target", "motion.format", "motion.state"];
        string[] driveIds = ["drive.trigger", "drive.revert", "drive.requested", "drive.phase", "drive.cancel", "drive.result"];
        bool complete = audioIds.Concat(motionIds).Concat(driveIds).All(byId.ContainsKey);
        check(complete, "packaged catalog contains every final Audio, Motion and Forced-Drive feature ID");
        if (!complete) return; // Report missing catalog entries without masking the failure with a lookup exception.

        var audio = audioIds.Select(id => byId[id]).ToArray();
        var motion = motionIds.Select(id => byId[id]).ToArray();
        var drive = driveIds.Select(id => byId[id]).ToArray();
        var domains = audio.Concat(motion).ToArray();
        check(audio.Select(f => f.CapabilitySlot).SequenceEqual(Enumerable.Range(144, 16)) &&
            motion.Select(f => f.CapabilitySlot).SequenceEqual(Enumerable.Range(160, 11)) &&
            domains.All(f => catalog.Count(other => other.CapabilitySlot == f.CapabilitySlot) == 1),
            "Audio and Motion retain their exact non-overlapping native slots 144 through 170");
        check(catalog.Where(f => f.Id.StartsWith("audio.", StringComparison.Ordinal) || f.Id.StartsWith("motion.", StringComparison.Ordinal))
            .Select(f => f.Id).Order().SequenceEqual(audioIds.Concat(motionIds).Order()),
            "packaged Audio and Motion domains contain no unexpected controls outside the supported contract");
        check(domains.All(f => !f.ChangesProgression && f.Arguments.Count == 0) &&
            domains.Where(f => f.Kind != FeatureKind.ReadOnly).All(f => f.CommandId == 1000 + f.CapabilitySlot),
            "Audio and Motion use scalar commands without progression edits or hidden action arguments");

        var mix = audio.Take(4).ToArray();
        check(mix.All(f => f is { Category: "Audio Mix", Kind: FeatureKind.Number, Minimum: 0, Maximum: 100,
            DefaultValue: 100, Step: 1, Unit: "%", RequiresScene: false, CanSaveInProfile: true } && f.ValueSlot == f.CapabilitySlot),
            "all four audio mix controls use scene-independent percentages with a neutral default and profile support");
        check(mix.All(f => f.IsValidValue(0) && f.IsValidValue(100) && !f.IsValidValue(-1) && !f.IsValidValue(101) &&
            !f.IsValidValue(double.NaN) && !f.IsValidValue(double.PositiveInfinity)),
            "audio mix values allow mute and full volume while rejecting out-of-range and non-finite input");
        check(byId["audio.reset"] is { Category: "Audio Mix", Kind: FeatureKind.Action, CommandId: 1148,
            ValueSlot: -1, Minimum: 0, Maximum: 0, RequiresScene: false, CanSaveInProfile: false },
            "audio reset stays an explicit scene-independent action rather than a persistent profile setting");
        check(audio.Skip(5).All(f => f is { Category: "Audio Diagnostics", Kind: FeatureKind.ReadOnly,
            CommandId: 0, RequiresScene: false, CanSaveInProfile: false } && f.ValueSlot == f.CapabilitySlot),
            "audio bus and availability diagnostics cannot issue commands or enter profiles");
        check(Enumerable.Range(0, 9).All(i => byId[$"audio.bus.current{i}"] is { Unit: "%" } f && f.IsValidValue(125)) &&
            byId["audio.available"] is { Minimum: 0, Maximum: 1 },
            "native bus diagnostics can report levels above the trainer mix range and availability remains binary");

        check(motion.All(f => f.Category == "Animation" && !f.CanSaveInProfile),
            "all Motion controls share the Animation category and exclude actor leases from profiles");
        check(byId["motion.speed"] is { Kind: FeatureKind.Number, CommandId: 1160, ValueSlot: 160,
            Minimum: .1, Maximum: 3, DefaultValue: 1, Step: .1, Unit: "x", RequiresScene: false } &&
            byId["motion.speed"].IsValidValue(.1) && byId["motion.speed"].IsValidValue(3) &&
            !byId["motion.speed"].IsValidValue(0) && !byId["motion.speed"].IsValidValue(3.1),
            "requested Motion speed preserves the positive 0.1 to 3 range and its separate native command");
        check(byId["motion.override"] is { Kind: FeatureKind.Toggle, CommandId: 1161, ValueSlot: 161,
            Minimum: 0, Maximum: 1, DefaultValue: 0, RequiresScene: false },
            "Motion override is initially off and its disable control stays available outside a playable scene");
        check(motion.Skip(2).All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0 && f.ValueSlot == f.CapabilitySlot) &&
            motion.Skip(2).Take(8).All(f => f.RequiresScene) && !byId["motion.state"].RequiresScene,
            "Motion frame/resource readouts require a scene while lease-state diagnostics remain visible after actor loss");
        check(byId["motion.actual_speed"].IsValidValue(0) && byId["motion.actual_speed"].IsValidValue(-1) &&
            byId["motion.logical_id"].IsValidValue(-1) && byId["motion.resolved_id"].IsValidValue(-1) &&
            byId["motion.format"] is { Minimum: 0, Maximum: 1 } && byId["motion.state"] is { Minimum: 0, Maximum: 9 },
            "Motion diagnostics retain native unset IDs, native speed values and documented format/state ranges");
        check(new[] { "motion.frame", "motion.duration", "motion.blend_duration", "motion.blend_target" }
            .All(id => byId[id].Unit == "frames"), "Motion timing readouts retain their native frame units");

        check(drive.Select(f => f.CapabilitySlot).SequenceEqual(Enumerable.Range(122, 6)) &&
            drive.Select(f => f.CommandId).SequenceEqual(new[] { 1122, 1123, 0, 0, 1126, 0 }) &&
            drive.Select(f => f.ValueSlot).SequenceEqual(new[] { -1, -1, 124, 125, -1, 127 }) &&
            drive.Select(f => f.Kind).SequenceEqual(new[] { FeatureKind.Action, FeatureKind.Action, FeatureKind.ReadOnly,
                FeatureKind.ReadOnly, FeatureKind.Action, FeatureKind.ReadOnly }) &&
            drive.All(f => f.Category == "Drive and Forms" && !f.CanSaveInProfile &&
                f.ChangesProgression == (f.Id == "drive.trigger")),
            "Drive IDs, commands and profile rules remain fixed; only triggering can initialize saved equipment");
        FeatureChoice[] expectedForms = [new("Valor Form", 1), new("Wisdom Form", 2), new("Limit Form", 3),
            new("Master Form", 4), new("Final Form", 5), new("Antiform", 6)];
        var formArgument = byId["drive.trigger"].Arguments.Single();
        check(formArgument.Minimum == 1 && formArgument.Maximum == 6 && formArgument.DefaultValue == 1 &&
            formArgument.Choices.SequenceEqual(expectedForms),
            "Forced-Drive selector preserves each exact form name and ID, including Limit 3 and Antiform 6");

        // Use the shipped definitions with the real profile serializer. No bridge or game process is accessed.
        var store = new ProfileStore(Path.Combine(workspace, "audio-catalog-profiles"));
        var requested = new Dictionary<string, double>(StringComparer.Ordinal)
        {
            ["audio.master"] = 100, ["audio.music"] = 0, ["audio.effects"] = 25, ["audio.voice"] = 73
        };
        string savedPath = store.Save(new TrainerProfile { Name = "Audio mix regression", Values = requested }, catalog);
        var loaded = store.Read(savedPath, catalog);
        check(loaded.Values.Count == requested.Count && requested.All(p => loaded.Values.TryGetValue(p.Key, out double value) && value == p.Value),
            "real audio profiles round-trip all four chosen levels without adding reset actions, diagnostics or Motion activation");
        check(domains.Where(f => f.CanSaveInProfile).Select(f => f.Id).Order().SequenceEqual(mix.Select(f => f.Id).Order()),
            "exactly the four numeric audio controls can be replayed from an Audio/Motion profile");

        bool ProfileRejected(string id, double value)
        {
            try
            {
                ProfileStore.Validate(new TrainerProfile { Name = "Rejected catalog fixture", Values = new() { [id] = value } }, catalog);
                return false;
            }
            catch (InvalidDataException) { return true; }
        }
        foreach (var excluded in domains.Concat(drive).Where(f => !f.CanSaveInProfile))
            check(ProfileRejected(excluded.Id, excluded.DefaultValue), "profile rejects non-replayable catalog feature: " + excluded.Id);
        foreach (double invalid in new[] { -1d, 101d, double.NaN, double.NegativeInfinity, double.PositiveInfinity })
            check(mix.All(f => ProfileRejected(f.Id, invalid)), "audio profile rejects invalid percentage: " + invalid);
    }
}
