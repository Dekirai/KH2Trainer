using System.IO;
using KH2Trainer;
using KH2Trainer.Core;

internal static class GummiRequestUiChecks
{
    private sealed class Host : IFeatureHost
    {
        public bool Busy { get; set; }
        public bool ShowDescriptions => true;
        public bool Fail { get; set; }
        public List<(int Command, double[] Arguments)> Calls { get; } = [];
        public bool IsFavorite(string id) => false;
        public void ToggleFavorite(FeatureVm feature) { }
        public Task Execute(int command, IReadOnlyList<double> arguments, string label)
        {
            Calls.Add((command, arguments.ToArray()));
            return Fail ? Task.FromException(new IOException("Synthetic uncertain request result")) : Task.CompletedTask;
        }
    }

    public static object Run()
    {
        using var source = typeof(FeatureVm).Assembly.GetManifestResourceStream("KH2Trainer.Data.features.json")!;
        var definition = FeatureCatalog.Load(source).Single(f => f.Id == "gummi.request_special_attack");
        var host = new Host();
        var feature = new FeatureVm(definition, host, new Dictionary<string, IReadOnlyList<FeatureChoice>>());
        var errors = new List<Exception>();
        AsyncCommand.ReportError = errors.Add;
        int checks = 0;
        void Check(bool condition, string message) { ++checks; if (!condition) throw new InvalidDataException(message); }
        var section = CategoryLayout.Build([feature]).Single();
        Check(section.Key == "gummi" && section.Tabs.Single().Title == "Flight" &&
            section.Tabs.Single().Groups.Single().Controls.Single() == feature,
            "The request appears in the existing Gummi Ship Flight controls.");
        var snapshot = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = false };
        feature.Update(snapshot);
        Check(!feature.IsAvailable && !feature.ApplyCommand.CanExecute(null), "Older bridges cannot dispatch the new action.");
        snapshot.Supported[485 / 64] |= 1UL << (485 % 64);
        feature.Update(snapshot);
        Check(feature.IsAvailable && feature.ApplyCommand.CanExecute(null) && feature.IsAction && !feature.HasArguments &&
            !feature.ShowValueInput && !feature.ShowLiveValue,
            "The request uses native Gummi mission gates and exposes a single explicit button.");
        feature.ApplyCommand.Execute(null);
        Check(host.Calls.Count == 1 && host.Calls[0].Command == 1485 && host.Calls[0].Arguments.Length == 0,
            "One click sends one parameterless special-weapon request.");
        feature.Update(snapshot);
        Check(host.Calls.Count == 1, "A new snapshot does not repeat a successful request.");
        host.Fail = true;
        feature.ApplyCommand.Execute(null);
        Check(host.Calls.Count == 2 && errors.Count == 1, "Uncertain acknowledgement is reported after one request.");
        feature.Update(snapshot);
        Check(host.Calls.Count == 2, "Uncertain acknowledgement is never retried by a snapshot.");
        host.Busy = true;
        Check(!feature.ApplyCommand.CanExecute(null), "Concurrent trainer work disables the action.");
        host.Busy = false;
        feature.Update(new TrainerSnapshot());
        Check(!feature.IsAvailable && !feature.ApplyCommand.CanExecute(null) && host.Calls.Count == 2,
            "Disconnect disables the action without replay or restoration.");
        return new { success = true, checks, gameAccess = false,
            scope = "Embedded catalog and actual FeatureVm with synthetic transport: navigation, capabilities, command payload and no automatic retry." };
    }
}
