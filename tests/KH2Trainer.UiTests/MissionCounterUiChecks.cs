using System.IO;
using KH2Trainer;
using KH2Trainer.Core;

internal static class MissionCounterUiChecks
{
    private sealed class Host : IFeatureHost
    {
        public bool Busy { get; set; }
        public bool ShowDescriptions => true;
        public bool Fail { get; set; }
        public List<(int Command, double[] Args)> Calls { get; } = [];
        public bool IsFavorite(string id) => false;
        public void ToggleFavorite(FeatureVm feature) { }
        public Task Execute(int command, IReadOnlyList<double> arguments, string label)
        {
            Calls.Add((command, arguments.ToArray()));
            return Fail ? Task.FromException(new IOException("Synthetic uncertain command result")) : Task.CompletedTask;
        }
    }

    public static object Run()
    {
        using var source = typeof(FeatureVm).Assembly.GetManifestResourceStream("KH2Trainer.Data.features.json")!;
        var catalog = FeatureCatalog.Load(source);
        var host = new Host();
        var errors = new List<Exception>();
        AsyncCommand.ReportError = errors.Add;
        var features = catalog.Where(f => f.CapabilitySlot is >= 477 and <= 481)
            .Select(f => new FeatureVm(f, host, new Dictionary<string, IReadOnlyList<FeatureChoice>>())).ToArray();
        int checks = 0;
        void Check(bool condition, string message) { ++checks; if (!condition) throw new InvalidDataException(message); }
        Check(features.Length == 5, "Five mission controls/readouts must be embedded.");
        var add = features.Single(f => f.Id == "mission.counter.add");
        var digit = features.Single(f => f.Id == "mission.counter.digit");
        var snapshot = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = true };
        foreach (var f in features)
        {
            f.Update(snapshot);
            Check(!f.IsAvailable && !f.ApplyCommand.CanExecute(null), "An older bridge cannot enable a new mission command.");
            int slot = f.Definition.CapabilitySlot;
            snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
            f.Update(snapshot);
        }
        add.Arguments[0].SelectedChoice = add.Arguments[0].Choices.Single(c => c.Value == 2);
        foreach (var value in new[] { "-2147483648", "-7", "0", "2147483647" })
        {
            int before = host.Calls.Count;
            add.Arguments[1].ValueText = value;
            add.ApplyCommand.Execute(null);
            Check(host.Calls.Count == before + 1 && host.Calls[^1].Command == 1477 &&
                host.Calls[^1].Args.SequenceEqual(new[] { 2d, double.Parse(value, System.Globalization.CultureInfo.InvariantCulture) }),
                "Delta arguments must retain sign, endpoints and counter order.");
        }
        foreach (var value in new[] { "-2147483649", "2147483648", "NaN", "Infinity", "invalid" })
        {
            int before = host.Calls.Count, priorErrors = errors.Count;
            add.Arguments[1].ValueText = value;
            add.ApplyCommand.Execute(null);
            Check(host.Calls.Count == before && errors.Count == priorErrors + 1, "Invalid delta text must never reach transport.");
        }
        digit.Arguments[0].SelectedChoice = digit.Arguments[0].Choices.Single(c => c.Value == 1);
        digit.Arguments[1].SelectedChoice = digit.Arguments[1].Choices.Single(c => c.Value == 9);
        digit.Arguments[2].SelectedChoice = digit.Arguments[2].Choices.Single(c => c.Value == 2);
        digit.ApplyCommand.Execute(null);
        Check(host.Calls[^1].Command == 1478 && host.Calls[^1].Args.SequenceEqual(new[] { 1d, 9d, 2d }),
            "Digit command sends counter, decimal position, then replacement digit.");
        host.Fail = true;
        int prior = host.Calls.Count, oldErrors = errors.Count;
        digit.ApplyCommand.Execute(null);
        Check(host.Calls.Count == prior + 1 && errors.Count == oldErrors + 1, "An uncertain result is reported once.");
        foreach (var f in features) f.Update(snapshot);
        Check(host.Calls.Count == prior + 1, "A snapshot must not retry an uncertain relative command.");
        host.Fail = false;
        host.Busy = true;
        Check(!digit.ApplyCommand.CanExecute(null), "Concurrent trainer work disables mission actions.");
        host.Busy = false;
        foreach (var f in features.Where(f => f.IsReadOnly))
        {
            Check(f.LiveValue == "—", "Missing combo observations are not measured zero.");
            int slot = f.Definition.ValueSlot;
            snapshot.Valid[slot / 64] |= 1UL << (slot % 64);
            snapshot.Values[slot] = slot == 481 ? -0.5 : 0;
            f.Update(snapshot);
            Check(f.LiveValue != "—" && !f.IsEditable && !f.ShowApplyButton, "Valid combo values must remain read-only.");
            if (slot == 481) Check(f.LiveValue.Contains("-0.5") && f.LiveValue.Contains("native units"), "Allowance retains its sign and units.");
            snapshot.Valid[slot / 64] &= ~(1UL << (slot % 64));
            f.Update(snapshot);
            Check(f.LiveValue == "—", "An invalidated combo observation clears the old displayed value.");
        }
        Check(host.Calls.Count == prior + 1, "Readout updates must not invoke game commands.");
        var absentScene = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = false, Supported = snapshot.Supported };
        foreach (var f in features) f.Update(absentScene);
        Check(!add.ApplyCommand.CanExecute(null) && !digit.ApplyCommand.CanExecute(null), "Scene loss disables both mission actions.");
        return new { success = true, checks, gameAccess = false, scope = "Actual embedded catalog and FeatureVm command arguments, capabilities, failure handling and readouts; synthetic transport only." };
    }
}
