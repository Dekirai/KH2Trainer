using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using KH2Trainer;
using KH2Trainer.Core;

internal static class ChaosComfortUiChecks
{
    private sealed class Host : IFeatureHost
    {
        public bool Busy { get; set; }
        public bool ShowDescriptions { get; set; }
        public bool Fail { get; set; }
        public List<(int Command, double[] Arguments)> Calls { get; } = [];
        public bool IsFavorite(string id) => false;
        public void ToggleFavorite(FeatureVm feature) { }
        public Task Execute(int command, IReadOnlyList<double> arguments, string label)
        {
            Calls.Add((command, arguments.ToArray()));
            return Fail ? Task.FromException(new IOException("Synthetic uncertain action result")) : Task.CompletedTask;
        }
    }

    public static object Run(string output, Application app)
    {
        Directory.CreateDirectory(output);
        using var stream = typeof(FeatureVm).Assembly.GetManifestResourceStream("KH2Trainer.Data.features.json")
            ?? throw new InvalidDataException("Embedded feature catalog missing.");
        var catalog = FeatureCatalog.Load(stream);
        var host = new Host();
        var features = new[] { "target_reduce_hp_percent", "movement.heavy_jumps", "display.brightness_preview" }
            .Select(id => new FeatureVm(catalog.Single(f => f.Id == id), host, new Dictionary<string, IReadOnlyList<FeatureChoice>>())).ToArray();
        var hp = features[0]; var heavy = features[1]; var brightness = features[2];
        int checks = 0;
        void Check(bool condition, string message) { ++checks; if (!condition) throw new InvalidDataException(message); }
        var errors = new List<Exception>();
        var previousErrorHandler = AsyncCommand.ReportError;
        AsyncCommand.ReportError = errors.Add;
        try
        {
            var sections = CategoryLayout.Build(features);
            bool Placed(FeatureVm feature, string section, string tab) => sections.Single(s => s.Key == section)
                .Tabs.Single(t => t.Title == tab).Groups.SelectMany(g => g.Controls).Count(f => ReferenceEquals(f, feature)) == 1;
            Check(Placed(hp, "combat", "Practice"), "Percentage HP action must appear in Combat > Practice.");
            Check(Placed(heavy, "sora", "Movement"), "Heavy jumps must appear in Sora > Movement.");
            Check(Placed(brightness, "display", "Display"), "Expanded brightness remains in the existing Display tab.");
            Check(hp.IsAction && hp.HasArguments && hp.Arguments.Count == 1 && !hp.ShowValueInput && !hp.ShowLiveValue &&
                hp.Arguments[0].ValueText == "25" && hp.Arguments[0].Definition.Minimum == 1 && hp.Arguments[0].Definition.Maximum == 99,
                "Percentage HP uses one explicit action argument with default25 and bounds1..99.");
            Check(heavy.IsAction && !heavy.HasArguments && !heavy.ShowValueInput && !heavy.ShowLiveValue,
                "Heavy jumps uses a parameterless action button without a fictitious live value.");
            Check(!hp.Definition.CanSaveInProfile && !heavy.Definition.CanSaveInProfile,
                "Relative manual actions must not enter automatic profile application.");
            Check(brightness.Definition.Minimum == -50 && brightness.Definition.Maximum == 5000,
                "Embedded brightness catalog must expose the extended runtime range.");
            var snapshot = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = true };
            foreach (var feature in features)
            {
                feature.Update(snapshot);
                Check(!feature.IsAvailable && !feature.ApplyCommand.CanExecute(null), "Missing bridge capability disables " + feature.Id);
                int slot = feature.Definition.CapabilitySlot;
                snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
                feature.Update(snapshot);
                Check(feature.IsAvailable && feature.ApplyCommand.CanExecute(null), "Supported feature remains manually available: " + feature.Id);
            }
            hp.ApplyCommand.Execute(null);
            Check(host.Calls.Count == 1 && host.Calls[0].Command == 1486 && host.Calls[0].Arguments.SequenceEqual(new[] { 25d }),
                "Default25 percent sends exactly command1486 and one argument.");
            foreach (string input in new[] { "1", "99" })
            {
                hp.Arguments[0].ValueText = input;
                int before = host.Calls.Count;
                hp.ApplyCommand.Execute(null);
                Check(host.Calls.Count == before + 1 && host.Calls[^1].Command == 1486 &&
                    host.Calls[^1].Arguments.SequenceEqual(new[] { double.Parse(input, CultureInfo.InvariantCulture) }),
                    "Valid HP argument endpoint retains its value and order.");
            }
            foreach (string input in new[] { "0", "100", "-1", "NaN", "Infinity", "invalid" })
            {
                hp.Arguments[0].ValueText = input;
                int before = host.Calls.Count, priorErrors = errors.Count;
                hp.ApplyCommand.Execute(null);
                Check(host.Calls.Count == before && errors.Count == priorErrors + 1,
                    "Invalid HP argument boundary/text must not reach transport: " + input);
            }
            hp.Arguments[0].ValueText = "25";
            heavy.ApplyCommand.Execute(null);
            Check(host.Calls[^1].Command == 1487 && host.Calls[^1].Arguments.Length == 0,
                "Heavy jumps sends command1487 with no arguments.");
            brightness.ValueText = "5000";
            brightness.ApplyCommand.Execute(null);
            Check(host.Calls[^1].Command == 1304 && host.Calls[^1].Arguments.SequenceEqual(new[] { 5000d }),
                "Brightness5000 is accepted and dispatched unchanged.");
            foreach (string input in new[] { "-51", "5001", "NaN", "Infinity" })
            {
                brightness.ValueText = input;
                int before = host.Calls.Count, priorErrors = errors.Count;
                brightness.ApplyCommand.Execute(null);
                Check(host.Calls.Count == before && errors.Count == priorErrors + 1,
                    "Invalid extended brightness must not reach transport: " + input);
            }
            brightness.ValueText = "5000";
            int sent = host.Calls.Count;
            foreach (var feature in features) feature.Update(snapshot);
            Check(host.Calls.Count == sent, "Snapshot refresh cannot replay relative actions or brightness commands.");
            host.Fail = true;
            foreach (var feature in new[] { hp, heavy })
            {
                int before = host.Calls.Count, priorErrors = errors.Count;
                feature.ApplyCommand.Execute(null);
                feature.Update(snapshot);
                Check(host.Calls.Count == before + 1 && errors.Count == priorErrors + 1,
                    "Uncertain relative action acknowledgement is reported once and never retried: " + feature.Id);
            }
            host.Fail = false;
            host.Busy = true;
            Check(features.All(f => !f.ApplyCommand.CanExecute(null)), "Busy trainer disables all three commands.");
            host.Busy = false;
            var noScene = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = false, Supported = snapshot.Supported };
            foreach (var feature in features) feature.Update(noScene);
            Check(!hp.ApplyCommand.CanExecute(null) && !heavy.ApplyCommand.CanExecute(null) && brightness.ApplyCommand.CanExecute(null),
                "Scene loss disables gameplay actions while preserving renderer preview availability.");
            foreach (var feature in features) feature.Update(snapshot);
            var renders = new List<object>();
            foreach (bool descriptions in new[] { false, true })
            {
                host.ShowDescriptions = descriptions;
                foreach (var feature in features) feature.RefreshPresentation();
                foreach (int width in new[] { 780, 1000 })
                    renders.Add(Render(features, app, output, width, descriptions, Check));
            }
            int beforeDisconnect = host.Calls.Count;
            foreach (var feature in features) feature.Update(new TrainerSnapshot());
            Check(features.All(f => !f.IsAvailable && !f.ApplyCommand.CanExecute(null)) && host.Calls.Count == beforeDisconnect,
                "Disconnect disables all controls without replay or automatic restoration.");
            Check(app.Windows.Count == 0 && app.MainWindow is null, "Focused WPF checks must not create a window.");
            return new { success = true, checks, renders, commands = new[] { 1486, 1487, 1304 }, gameAccess = false,
                scope = "Actual embedded catalog, FeatureVm and WPF row templates; synthetic transport, offscreen rendering and finite range checks. Integer-only HP validation remains in the native command." };
        }
        finally { AsyncCommand.ReportError = previousErrorHandler; }
    }

    private static object Render(FeatureVm[] features, Application app, string output, int width, bool descriptions, Action<bool, string> check)
    {
        var rows = new ItemsControl { ItemsSource = features, ItemTemplate = (DataTemplate)app.Resources["FeatureControlTemplate"] };
        var root = new Border { Background = (Brush)app.Resources["BackgroundBrush"], Padding = new Thickness(24), Child = rows };
        root.SetValue(TextElement.ForegroundProperty, app.Resources["TextBrush"]);
        root.SetValue(TextElement.FontFamilyProperty, new FontFamily("Segoe UI"));
        root.SetValue(TextElement.FontSizeProperty, 13.5);
        double height = 0, priorHeight = -1;
        for (int pass = 0; pass < 10; ++pass)
        {
            root.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
            root.Measure(new Size(width, double.PositiveInfinity));
            height = Math.Ceiling(root.DesiredSize.Height);
            root.Arrange(new Rect(0, 0, width, height)); root.UpdateLayout();
            if (height == priorHeight && root.IsMeasureValid && root.IsArrangeValid) break;
            priorHeight = height;
        }
        check(root.IsMeasureValid && root.IsArrangeValid && double.IsFinite(height) && height > 100 && height < 1600,
            "Focused rows must settle to a bounded layout.");
        var all = Descendants<FrameworkElement>(root).ToArray();
        Rect Bounds(FrameworkElement e) => e.TransformToAncestor(root).TransformBounds(new Rect(0, 0, e.ActualWidth, e.ActualHeight));
        void LabelFits(TextBlock label)
        {
            var text = new FormattedText(label.Text, CultureInfo.InvariantCulture, label.FlowDirection,
                new Typeface(label.FontFamily, label.FontStyle, label.FontWeight, label.FontStretch), label.FontSize,
                label.Foreground, VisualTreeHelper.GetDpi(label).PixelsPerDip);
            var bounds = Bounds(label);
            check(label.Visibility == Visibility.Visible && text.WidthIncludingTrailingWhitespace <= label.ActualWidth + 1 &&
                bounds.Left >= 0 && bounds.Right <= width && bounds.Bottom <= height,
                "Visible feature/argument label must fit without trimming or page clipping: " + label.Text);
        }
        foreach (var feature in features)
        {
            var mine = all.Where(e => ReferenceEquals(e.DataContext, feature)).ToArray();
            var name = mine.OfType<TextBlock>().Single(t => t.Name == "FeatureName");
            check(name.Text == feature.Name, "Feature row retains the embedded feature name.");
            LabelFits(name);
            var button = mine.OfType<Button>().Single(b => b.Visibility == Visibility.Visible && ReferenceEquals(b.Command, feature.ApplyCommand));
            check(button.IsEnabled && button.Content?.ToString() == feature.ApplyLabel && Bounds(name).Right < Bounds(button).Left,
                "Action label and feature name fit separate usable row regions.");
            var description = mine.OfType<TextBlock>().Single(t => t.Name == "FeatureDescription");
            check(description.Text == feature.Description && description.Visibility == (descriptions ? Visibility.Visible : Visibility.Collapsed),
                "Detailed row text follows the existing description toggle.");
            foreach (var argument in feature.Arguments)
            {
                var label = all.OfType<TextBlock>().Single(t => ReferenceEquals(t.DataContext, argument) && t.Text == argument.Name);
                LabelFits(label);
                check(all.OfType<TextBox>().Any(t => ReferenceEquals(t.DataContext, argument) && t.Visibility == Visibility.Visible && t.IsEnabled && t.Text == "25"),
                    "HP argument is a usable visible input retaining25 percent.");
            }
            if (feature.IsNumber)
                check(mine.OfType<TextBox>().Any(t => t.Visibility == Visibility.Visible && t.IsEnabled && t.Text == "5000"),
                    "Extended brightness remains visible in the existing number input.");
        }
        var bitmap = new RenderTargetBitmap(width, (int)height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(root);
        byte[] pixels = new byte[bitmap.PixelWidth * bitmap.PixelHeight * 4]; bitmap.CopyPixels(pixels, bitmap.PixelWidth * 4, 0);
        int bright = 0; for (int i = 0; i < pixels.Length; i += 4) if (pixels[i] > 240 && pixels[i + 1] > 240 && pixels[i + 2] > 240) ++bright;
        check(bright < bitmap.PixelWidth * bitmap.PixelHeight * .02, "New rows retain the existing dark background.");
        string fileName = $"chaos-comfort-{width}-{(descriptions ? "details" : "compact")}.png";
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using (var file = File.Create(Path.Combine(output, fileName))) encoder.Save(file);
        return new { width, height, descriptions, file = fileName };
    }

    private static IEnumerable<T> Descendants<T>(DependencyObject root) where T : DependencyObject
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); ++i)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            if (child is T value) yield return value;
            foreach (var descendant in Descendants<T>(child)) yield return descendant;
        }
    }
}
