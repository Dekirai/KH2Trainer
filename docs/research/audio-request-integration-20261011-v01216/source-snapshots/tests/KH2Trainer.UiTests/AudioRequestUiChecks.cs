using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using KH2Trainer;
using KH2Trainer.Core;

internal static class AudioRequestUiChecks
{
    private sealed class Host : IFeatureHost
    {
        public bool Busy => false;
        public bool ShowDescriptions => true;
        public int Calls { get; private set; }
        public bool IsFavorite(string id) => false;
        public void ToggleFavorite(FeatureVm feature) { }
        public Task Execute(int command, IReadOnlyList<double> arguments, string label)
        {
            ++Calls;
            return Task.CompletedTask;
        }
    }

    public static object Run(string output, Application app)
    {
        Directory.CreateDirectory(output);
        using var source = typeof(FeatureVm).Assembly.GetManifestResourceStream("KH2Trainer.Data.features.json")!;
        var catalog = FeatureCatalog.Load(source);
        var host = new Host();
        var features = catalog.Where(f => f.Id.StartsWith("audio.requests.", StringComparison.Ordinal))
            .Select(f => new FeatureVm(f, host, new Dictionary<string, IReadOnlyList<FeatureChoice>>())).ToArray();
        int checks = 0;
        void Check(bool condition, string message) { ++checks; if (!condition) throw new InvalidDataException(message); }
        Check(features.Length == 3, "The three request observations must be embedded.");
        var section = CategoryLayout.Build(features).Single();
        var tab = section.Tabs.Single();
        Check(section.Key == "audio" && tab.Title == "Requests" && tab.Groups.Single().Controls.Count == 0 &&
            tab.Groups.Single().Readouts.Count == 3, "Audio Requests contains only readouts at its named location.");
        var snapshot = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = false };
        foreach (var f in features)
        {
            f.Update(snapshot);
            Check(!f.IsAvailable && f.LiveValue == "—" && f.Availability.Contains("does not provide"),
                "An older bridge shows unsupported data without inventing a zero.");
            int slot = f.Definition.CapabilitySlot;
            snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
            f.Update(snapshot);
            Check(f.IsAvailable && f.LiveValue == "—" && f.IsReadOnly && !f.IsEditable && !f.ShowApplyButton,
                "A supported request readout needs no playable scene and exposes no edit control.");
            snapshot.Valid[slot / 64] |= 1UL << (slot % 64);
            snapshot.Values[slot] = f.Definition.Maximum;
            f.Update(snapshot);
            Check(f.LiveValue != "—", "A valid endpoint appears as a measured observation.");
        }
        var free = features.Single(f => f.Id == "audio.requests.free");
        Check(free.LiveValue == "80 / 80", "Free request capacity is shown without labeling it voice count.");
        var gates = features.Single(f => f.Id == "audio.requests.gates");
        var renders = new List<string>();
        for (int mask = 0; mask < 8; ++mask)
        {
            snapshot.Values[482] = (mask & 2) != 0 ? 16 : 80;
            snapshot.Values[483] = (mask & 4) != 0 ? 25 : 0;
            snapshot.Values[484] = mask;
            foreach (var f in features) f.Update(snapshot);
            Check((gates.LiveValue.Contains("New requests inhibited") == ((mask & 1) != 0)) &&
                (gates.LiveValue.Contains("reserve reached") == ((mask & 2) != 0)) &&
                (gates.LiveValue.Contains("pass limit reached") == ((mask & 4) != 0)) &&
                (gates.LiveValue == "No sampled admission limit") == (mask == 0),
                "Every gate combination must display all of its observed reasons.");
            var view = new ContentControl { Content = tab.Groups.Single(),
                ContentTemplate = (DataTemplate)app.Resources["FeatureGroupTemplate"] };
            var panel = new Border { Background = (Brush)app.Resources["BackgroundBrush"], Padding = new Thickness(24), Child = view };
            panel.SetValue(TextElement.ForegroundProperty, app.Resources["TextBrush"]);
            panel.SetValue(TextElement.FontFamilyProperty, new FontFamily("Segoe UI"));
            panel.SetValue(TextElement.FontSizeProperty, 14d);
            double height = 0, previous = -1;
            bool stable = false;
            for (int pass = 0; pass < 10; ++pass)
            {
                panel.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
                panel.Measure(new Size(780, double.PositiveInfinity));
                height = Math.Ceiling(panel.DesiredSize.Height);
                panel.Arrange(new Rect(0, 0, 780, height)); panel.UpdateLayout();
                if (height == previous && panel.IsMeasureValid && panel.IsArrangeValid) { stable = true; break; }
                previous = height;
            }
            Check(stable, "Request readout layout must stabilize.");
            var label = Descendants(panel).OfType<TextBlock>().Single(t => t.Name == "FeatureLiveValue" && ReferenceEquals(t.DataContext, gates));
            Check(label.Text == gates.LiveValue && label.TextWrapping == TextWrapping.Wrap && label.TextTrimming == TextTrimming.None,
                "All admission reasons must wrap instead of disappearing behind an ellipsis.");
            var bitmap = new RenderTargetBitmap(780, (int)height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(panel);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            string filename = $"audio-requests-{mask}.png";
            using (var file = File.Create(Path.Combine(output, filename))) encoder.Save(file);
            renders.Add(filename);
        }
        foreach (double invalid in new[] { -1, 8, 0.5, double.NaN, double.PositiveInfinity, double.NegativeInfinity })
            Check(FeatureFormatting.Format(gates.Definition, invalid) == "Unknown", "Invalid gate masks must not imply playback availability.");
        foreach (var f in features)
        {
            int slot = f.Definition.ValueSlot;
            snapshot.Valid[slot / 64] &= ~(1UL << (slot % 64));
            f.Update(snapshot);
            Check(f.LiveValue == "—", "A failed new sample must clear the prior request observation.");
            f.Update(new TrainerSnapshot());
            Check(!f.IsAvailable && f.LiveValue == "—", "Disconnect clears request observations.");
        }
        Check(host.Calls == 0, "Observing audio requests must never invoke transport.");
        return new { success = true, checks, gameAccess = false, renders,
            scope = "Actual embedded catalog, navigation and FeatureVm readouts with synthetic observations; no game process or visible window." };
    }

    private static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); ++i)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            yield return child;
            foreach (var descendant in Descendants(child)) yield return descendant;
        }
    }
}
