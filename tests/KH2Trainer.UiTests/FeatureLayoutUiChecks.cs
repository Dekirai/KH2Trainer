using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using KH2Trainer;
using KH2Trainer.Core;

/// <summary>
/// Checks the redesigned feature pages: every catalog entry is reachable from the
/// sidebar sections, rows and readouts render the right controls, switches apply
/// immediately and roll back on failure, and every tab renders on a dark background.
/// Synthetic snapshots only; no game process, window or input.
/// </summary>
internal static class FeatureLayoutUiChecks
{
    private sealed class FakeHost : IFeatureHost
    {
        public bool Busy { get; set; }
        public bool ShowDescriptions { get; set; }
        public HashSet<string> Favorites { get; } = new(StringComparer.Ordinal);
        public List<(int Command, double[] Arguments)> Calls { get; } = [];
        public bool Fail { get; set; }
        public bool IsFavorite(string featureId) => Favorites.Contains(featureId);
        public void ToggleFavorite(FeatureVm feature) { if (!Favorites.Remove(feature.Id)) Favorites.Add(feature.Id); feature.RefreshPresentation(); }
        public Task Execute(int command, IReadOnlyList<double> arguments, string label)
        {
            Calls.Add((command, arguments.ToArray()));
            return Fail ? Task.FromException(new InvalidOperationException("Synthetic rejection")) : Task.CompletedTask;
        }
    }

    public static object Run(string output, Application app)
    {
        Directory.CreateDirectory(output);
        int checks = 0;
        void Check(bool value, string message) { ++checks; if (!value) throw new InvalidDataException(message); }

        using var source = typeof(FeatureVm).Assembly.GetManifestResourceStream("KH2Trainer.Data.features.json")
            ?? throw new InvalidDataException("Embedded feature catalog missing.");
        var catalog = FeatureCatalog.Load(source);
        var host = new FakeHost();
        var errors = new List<Exception>();
        AsyncCommand.ReportError = errors.Add;
        var features = catalog.Select(f => new FeatureVm(f, host, new Dictionary<string, IReadOnlyList<FeatureChoice>>())).ToArray();

        // Navigation: a few sections with tabs, and nothing lost in the regrouping.
        var sections = CategoryLayout.Build(features);
        var placed = sections.SelectMany(s => s.Tabs).SelectMany(t => t.Groups).SelectMany(g => g.Controls.Concat(g.Readouts)).ToArray();
        Check(placed.Length == features.Length && placed.Distinct().Count() == features.Length, "Every catalog feature must appear exactly once in the sections.");
        Check(sections.All(s => s.Key != "more"), "Unmapped categories: " + string.Join(", ", sections.Where(s => s.Key == "more").SelectMany(s => s.Tabs).Select(t => t.Title)));
        Check(sections.Count <= 9, $"Too many sidebar sections ({sections.Count}).");
        Check(sections.All(s => s.Tabs.Count <= 7), "A section has more than seven tabs.");
        Check(sections.SelectMany(s => s.Tabs).SelectMany(t => t.Groups).All(g => g.Controls.All(f => f.IsEditable) && g.Readouts.All(f => f.IsReadOnly)), "Controls and readouts must be separated.");
        Check(sections.SelectMany(s => s.Tabs).All(t => t.Groups.All(g => g.ShowTitle == (t.Groups.Count > 1))), "Group titles appear only in shared tabs.");

        // Readable live values (renderer, audio, editor, window and MSAA readouts).
        var formatted = features.Where(f => f.Definition.CapabilitySlot is >= 392 and <= 418 or >= 424 and <= 438 or >= 447 and <= 455).ToArray();
        Check(formatted.Length == 51, "The renderer, audio, editor, window and MSAA features are incomplete.");
        var snapshot = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = true };
        foreach (var feature in formatted)
        {
            int slot = feature.Definition.CapabilitySlot;
            snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
            feature.Update(snapshot);
            Check(feature.LiveValue == "—", "Unavailable values must not appear as measured zero: " + feature.Name);
            if (feature.Definition.ValueSlot >= 0)
            {
                int valueSlot = feature.Definition.ValueSlot;
                snapshot.Valid[valueSlot / 64] |= 1UL << (valueSlot % 64);
                feature.Update(snapshot);
                Check(feature.LiveValue != "—", "A valid zero disappeared: " + feature.Name);
                snapshot.Valid[valueSlot / 64] &= ~(1UL << (valueSlot % 64));
            }
            Check(feature.IsEditable == (slot is 424 or 425 or 431 or 432 or 447 or 448), "Unexpected feature editability: " + feature.Name);
        }
        foreach (var feature in formatted.Where(f => f.Definition.ValueSlot >= 0))
        {
            int slot = feature.Definition.ValueSlot;
            snapshot.Valid[slot / 64] |= 1UL << (slot % 64);
            snapshot.Values[slot] = slot switch
            {
                392 => 8.456, 393 => 0.032, 394 => 0.004, 395 => 11.67,
                396 => 4, 397 => 8, 398 or 400 => 3840, 399 or 401 => 2160,
                402 => 512, 403 => 2048, 404 => 2,
                405 or 406 or 407 => 64, 408 => 1, 409 => 3, 410 => 16,
                411 => 5, 412 => 2, 413 => 4294967295, 414 => 3, 415 => 4294967295,
                416 => -12345.678, 417 => 0, 418 => 98765.432,
                425 or 427 => 60, 426 => 4, 428 => -30, 429 => 180, 430 => 0,
                433 => 1920, 434 => 1080, 435 => 2, 436 => 1, 437 => 1600, 438 => 900,
                449 => 1, 450 => 4, 451 => 8, 452 => 4, 453 => 2, 454 => 4, 455 => 1, _ => 0
            };
            feature.Update(snapshot);
        }
        string Live(int slot) => formatted.Single(f => f.Definition.CapabilitySlot == slot).LiveValue;
        Check(Live(408) == "Available", "Audio readiness needs a readable label.");
        Check(Live(414) == "Line", "Listener kind needs a readable label.");
        Check(Live(426) == "Preview", "Editor phase needs a readable label.");
        Check(Live(435) == "Maximized", "Window mode needs a readable label.");
        Check(Live(436) == "Pending", "Queued resize must be distinguished from completion.");
        Check(Live(449) == "Fixed", "MSAA policy mode needs a readable label.");
        Check(Live(455) == "Resident", "Installed MSAA dispatch needs a readable status.");
        Check(Live(415).StartsWith("4294967295", StringComparison.Ordinal), "Unsigned listener priority must not become negative or lose precision.");

        // Switches apply as soon as they are flipped and snap back when the game rejects them.
        var toggle = features.First(f => f.IsToggle && f.Definition.ValueSlot >= 0 && !f.Definition.RequiresScene);
        int toggleSlot = toggle.Definition.ValueSlot, toggleCapability = toggle.Definition.CapabilitySlot;
        var toggleSnapshot = new TrainerSnapshot { Connected = true, Status = 1 };
        toggleSnapshot.Supported[toggleCapability / 64] |= 1UL << (toggleCapability % 64);
        toggleSnapshot.Valid[toggleSlot / 64] |= 1UL << (toggleSlot % 64);
        toggle.Update(toggleSnapshot);
        Check(toggle.IsAvailable && toggle.CanToggle && !toggle.ToggleValue, "The test switch must start available and off.");
        toggle.ToggleValue = true;
        Check(host.Calls.Count == 1 && host.Calls[0].Command == toggle.Definition.CommandId && host.Calls[0].Arguments.SequenceEqual([1.0]), "Flipping a switch must send exactly one command with value 1.");
        host.Fail = true;
        toggleSnapshot.Values[toggleSlot] = 1; toggle.Update(toggleSnapshot);
        toggle.ToggleValue = false;
        Check(errors.Count == 1 && host.Calls.Count == 2, "A rejected switch must report one error.");
        toggle.Update(toggleSnapshot);
        Check(toggle.ToggleValue, "A rejected switch must return to the game's state on the next snapshot.");
        host.Fail = false; errors.Clear();
        host.Busy = true; toggle.Update(toggleSnapshot);
        Check(!toggle.CanToggle && !toggle.ApplyCommand.CanExecute(null), "Switches lock while the trainer is busy.");
        host.Busy = false; toggle.Update(toggleSnapshot);

        // Number inputs keep a typed value until it is applied.
        var number = features.First(f => f.IsNumber && f.Definition.ValueSlot >= 0 && !f.HasArguments);
        number.ValueText = "12345";
        var numberSnapshot = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = true };
        int numberSlot = number.Definition.ValueSlot; numberSnapshot.Valid[numberSlot / 64] |= 1UL << (numberSlot % 64); numberSnapshot.Values[numberSlot] = 7;
        number.Update(numberSnapshot);
        Check(number.ValueText == "12345" && number.LiveValue.StartsWith('7'), "A typed value must survive live updates until applied.");

        // Profile review: numbers keep the loaded value; switches keep mirroring the game; applying resumes mirroring.
        int callsBeforeReview = host.Calls.Count;
        toggle.Update(toggleSnapshot); bool liveSwitch = toggle.ToggleValue;
        toggle.SetInput(liveSwitch ? 0 : 1);
        Check(toggle.ToggleValue == liveSwitch && host.Calls.Count == callsBeforeReview, "Reviewing a profile must neither flip nor send a switch.");
        number.SetInput(42); number.Update(numberSnapshot);
        Check(number.ValueText == "42", "A reviewed profile value must survive live updates until applied.");
        number.MarkApplied(); number.Update(numberSnapshot);
        Check(number.ValueText == "7", "An applied profile value must resume mirroring the game.");

        // Search spans every section.
        var locations = sections.SelectMany(s => s.Tabs.SelectMany(t => t.Groups.Select(g => (g.Title, Location: s.Title + " › " + t.Title))))
            .ToDictionary(x => x.Title, x => x.Location);
        var search = new SearchResultsVm("hp", features.Where(f => f.Matches("hp")).ToArray(), locations, 150);
        Check(search.Count > 3 && search.Groups.All(g => g.ShowTitle) && search.Groups.Any(g => g.Controls.Any(f => f.Id == "player.hp")), "Search must find HP controls across sections.");
        Check(new SearchResultsVm("___nothing___", [], locations, 150).IsEmpty, "An empty search needs an empty state.");

        // Render every tab with the real templates and verify the controls each row shows.
        host.Favorites.Add(features[0].Id);
        var fullSnapshot = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = true };
        foreach (var feature in features)
        {
            int capability = feature.Definition.CapabilitySlot, value = feature.Definition.ValueSlot;
            if (capability >= 0) fullSnapshot.Supported[capability / 64] |= 1UL << (capability % 64);
            if (value >= 0) fullSnapshot.Valid[value / 64] |= 1UL << (value % 64);
            feature.RefreshPresentation(); feature.Update(fullSnapshot);
        }
        var groupTemplate = (DataTemplate)app.Resources["FeatureGroupTemplate"];
        var renders = new List<object>();
        foreach (var descriptions in new[] { false, true })
        {
            host.ShowDescriptions = descriptions;
            foreach (var feature in features) feature.RefreshPresentation();
            foreach (var section in sections)
                foreach (var tab in section.Tabs)
                {
                    if (descriptions && !ReferenceEquals(tab, sections[0].Tabs[0])) continue; // One detailed render is enough.
                    var items = new ItemsControl { ItemsSource = tab.Groups, ItemTemplate = groupTemplate };
                    var root = new Border { Background = (Brush)app.Resources["BackgroundBrush"], Padding = new Thickness(24), Child = items };
                    root.SetValue(TextElement.ForegroundProperty, app.Resources["TextBrush"]);
                    root.SetValue(TextElement.FontFamilyProperty, new FontFamily("Segoe UI")); root.SetValue(TextElement.FontSizeProperty, 13.5);
                    double height = Layout(root, 1000);
                    Check(height > 60 && height < 12000, "Invalid tab height: " + section.Title + " › " + tab.Title);
                    var all = Descendants<FrameworkElement>(root).ToArray();
                    foreach (var feature in tab.Groups.SelectMany(g => g.Controls.Concat(g.Readouts)))
                    {
                        var mine = all.Where(e => ReferenceEquals(e.DataContext, feature)).ToArray();
                        var texts = mine.OfType<TextBlock>().ToArray();
                        Check(texts.Any(t => t.Name == "FeatureName" && t.Text == feature.Name), "A feature lost its name: " + feature.Name);
                        Check(texts.Any(t => t.Name == "FeatureLiveValue" && t.Text == feature.LiveValue) || !feature.ShowLiveValue && feature.IsEditable,
                            "A feature lost its live value: " + feature.Name);
                        var description = texts.Single(t => t.Name == "FeatureDescription");
                        Check(description.Text == feature.Description && description.Visibility == (descriptions ? Visibility.Visible : Visibility.Collapsed),
                            "Descriptions must follow the Descriptions switch: " + feature.Name);
                        var buttons = mine.OfType<Button>().Where(b => b.Visibility == Visibility.Visible).ToArray();
                        Check(buttons.Count(b => ReferenceEquals(b.Command, feature.ToggleFavoriteCommand)) == 1, "Every feature needs one pin button: " + feature.Name);
                        Check(buttons.Count(b => ReferenceEquals(b.Command, feature.ApplyCommand)) == (feature.ShowApplyButton ? 1 : 0),
                            (feature.IsReadOnly ? "Readouts must have no action button: " : "Controls need exactly one apply button: ") + feature.Name);
                        Check(mine.OfType<CheckBox>().Count(c => c.Visibility == Visibility.Visible) == (feature.IsToggle ? 1 : 0), "Only switches show a toggle: " + feature.Name);
                        if (feature.HasArguments)
                            Check(all.Count(e => e is TextBlock t && feature.Arguments.Any(a => ReferenceEquals(t.DataContext, a) && t.Text == a.Name)) == feature.Arguments.Count,
                                "Every command argument needs a labelled input: " + feature.Name);
                    }
                    var bitmap = new RenderTargetBitmap(1000, (int)height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(root);
                    var pixels = new byte[bitmap.PixelWidth * bitmap.PixelHeight * 4]; bitmap.CopyPixels(pixels, bitmap.PixelWidth * 4, 0);
                    int bright = 0; for (int i = 0; i < pixels.Length; i += 4) if (pixels[i] > 240 && pixels[i + 1] > 240 && pixels[i + 2] > 240) ++bright;
                    Check(bright < bitmap.PixelWidth * bitmap.PixelHeight * .02, "Unexpected white background: " + section.Title + " › " + tab.Title);
                    string name = Slug(section.Title) + "-" + Slug(tab.Title) + (descriptions ? "-descriptions" : "") + ".png";
                    var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
                    using (var file = File.Create(Path.Combine(output, name))) encoder.Save(file);
                    renders.Add(new { section = section.Title, tab = tab.Title, width = 1000, height, file = name });
                }
        }
        Check(features[0].IsFavorite && !features[1].IsFavorite, "Pin state must come from the host.");

        foreach (var feature in features)
        {
            feature.Update(TrainerSnapshot.Disconnected);
            Check(feature.LiveValue == "—" && !feature.ApplyCommand.CanExecute(null) && !feature.CanToggle, "Disconnect retained a live value or action: " + feature.Name);
        }

        // Adaptive columns follow the available width.
        var grid = new AdaptiveGrid { MinColumnWidth = 320, MaxColumns = 3 };
        for (int i = 0; i < 5; i++) grid.Children.Add(new Border { Height = 20 });
        grid.Measure(new Size(1000, double.PositiveInfinity)); Check(grid.DesiredSize.Height == 40, "Five tiles at 1000 px need two rows of three.");
        grid.Measure(new Size(500, double.PositiveInfinity)); Check(grid.DesiredSize.Height == 100, "Five tiles at 500 px need one column.");

        // Preferences survive a round trip and a damaged file falls back to defaults.
        string settingsPath = Path.Combine(output, "settings.json");
        var settings = new UserSettings { ShowDescriptions = true, SaveFolder = "C:\\Saves", Favorites = ["a", "b", "a"] };
        settings.Save(settingsPath);
        var loaded = UserSettings.Load(settingsPath);
        Check(loaded.ShowDescriptions && loaded.SaveFolder == "C:\\Saves" && loaded.Favorites.SequenceEqual(["a", "b"]), "Preferences must round-trip without duplicates.");
        File.WriteAllText(settingsPath, "{\"Version\":1,\"Favorites\":null}");
        Check(UserSettings.Load(settingsPath).Favorites.Count == 0, "A null favorites list must load as empty instead of crashing.");
        File.WriteAllText(settingsPath, "{ not json");
        Check(UserSettings.Load(settingsPath).Favorites.SequenceEqual(UserSettings.DefaultFavorites), "A damaged preferences file must fall back to defaults.");

        return new { success = true, checks, features = features.Length, sections = sections.Count, tabs = sections.Sum(s => s.Tabs.Count), renders,
            source = "Compiled FeatureGroupTemplate, navigation layout and embedded catalog; synthetic snapshots only" };
    }

    private static string Slug(string value) => new string(value.ToLowerInvariant().Select(c => char.IsLetterOrDigit(c) ? c : '-').ToArray()).Trim('-');

    private static double Layout(FrameworkElement element, double width)
    {
        double previous = -1;
        for (int pass = 0; pass < 10; ++pass)
        {
            element.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
            element.Measure(new Size(width, double.PositiveInfinity));
            double height = Math.Ceiling(element.DesiredSize.Height);
            element.Arrange(new Rect(0, 0, width, height)); element.UpdateLayout();
            if (height == previous && element.IsMeasureValid && element.IsArrangeValid) return height;
            previous = height;
        }
        throw new InvalidDataException("Feature layout did not stabilize.");
    }

    private static IEnumerable<T> Descendants<T>(DependencyObject root) where T : DependencyObject
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); ++i)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            if (child is T match) yield return match;
            foreach (var descendant in Descendants<T>(child)) yield return descendant;
        }
    }
}
