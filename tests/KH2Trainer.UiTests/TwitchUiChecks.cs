using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using KH2Trainer;
using KH2Trainer.Core;
using KH2Trainer.Twitch;

/// <summary>The Twitch page offscreen with the real view model: setup, the reward list with an expanded reward, and the live queue.</summary>
internal static class TwitchUiChecks
{
    private sealed class FakeHost(string folder, IReadOnlyList<FeatureDefinition> catalog) : ITwitchHost
    {
        public string UserFolder => folder;
        public IReadOnlyList<FeatureDefinition> Catalog => catalog;
        public bool IsConnected => false;
        public List<string> Logs { get; } = [];
        public List<(string Message, bool Error)> Notifications { get; } = [];
        public TrainerSnapshot ReadGameSnapshot() => TrainerSnapshot.Disconnected;
        public Task Execute(int command, IReadOnlyList<double> arguments, string label) => Task.FromException(new InvalidOperationException("Not connected."));
        public void Log(string message) => Logs.Add(message);
        public void Notify(string message, bool isError) => Notifications.Add((message, isError));
    }

    public static object Run(string output, Application app)
    {
        Directory.CreateDirectory(output);
        var previous = SynchronizationContext.Current;
        // Async work in the view model continues on the UI thread, as in the trainer.
        SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(Dispatcher.CurrentDispatcher));
        try { return RunChecks(output, app); }
        finally { SynchronizationContext.SetSynchronizationContext(previous); }
    }

    private static object RunChecks(string output, Application app)
    {
        int checks = 0;
        void Check(bool value, string message) { ++checks; if (!value) throw new InvalidDataException(message); }
        var errors = new List<Exception>();
        AsyncCommand.ReportError = errors.Add;

        using var source = typeof(FeatureVm).Assembly.GetManifestResourceStream("KH2Trainer.Data.features.json")
            ?? throw new InvalidDataException("Embedded feature catalog missing.");
        var catalog = FeatureCatalog.Load(source);
        string folder = Path.Combine(output, "user");
        if (Directory.Exists(folder)) Directory.Delete(folder, true);
        Directory.CreateDirectory(folder);
        var probe = new TcpListener(IPAddress.Loopback, 0);
        probe.Start(); int port = ((IPEndPoint)probe.LocalEndpoint).Port; probe.Stop();
        string image = Path.Combine(folder, "valor.png");
        File.WriteAllBytes(image, Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="));
        var stored = new TwitchSettings { OverlayPort = port };
        stored.For("heal").Enabled = true;
        stored.For("valor").Enabled = true;
        stored.For("valor").ImagePath = image;
        stored.For("valor").Title = "Valor time!";
        string settingsPath = Path.Combine(folder, "twitch.json");
        stored.Save(settingsPath);

        var host = new FakeHost(folder, catalog);
        var vm = new TwitchVm(host);
        var rewards = vm.Rewards.ToDictionary(r => r.Key);
        Check(vm.Groups.Count == 4 && vm.Groups.Sum(g => g.Rewards.Count) == EffectCatalog.All.Count && rewards.Count == EffectCatalog.All.Count,
            "Every effect must appear once in the reward groups.");
        Check(vm.EnabledCount == 2 && rewards["heal"].Enabled && rewards["valor"].Enabled, "Enabled rewards must load from twitch.json.");
        Check(rewards["heal"].Status == "Created when you connect" && rewards["regen"].Status == "Off", "Offline reward status must explain what happens.");
        Check(rewards["valor"].HasImage && rewards["valor"].DisplayTitle == "Valor time!" && !rewards["heal"].HasImage, "Images and custom titles must load.");
        Check(vm.IsOverlayRunning && vm.OverlayUrl == $"http://127.0.0.1:{port}/", "The overlay must start on the configured port.");
        if (!vm.HasBuiltInClientId)
        {
            Check(vm.State == TwitchConnectionState.NotConfigured && vm.ShowClientIdStep && !vm.ConnectCommand.CanExecute(null),
                "Without a Client ID the page must ask for one and not offer Connect.");
            vm.ClientId = "  testclientid  ";
            Pump();
            Check(vm.ClientId == "testclientid" && vm.State == TwitchConnectionState.Disconnected && vm.ConnectCommand.CanExecute(null),
                "Entering a Client ID must enable Connect.");
        }

        // Filters.
        vm.Filter = "valor";
        Check(rewards["valor"].IsVisible && !rewards["heal"].IsVisible && !vm.HasNoMatches, "The filter must match titles.");
        vm.Filter = "___no_reward___";
        Check(vm.HasNoMatches && vm.Groups.All(g => !g.HasVisible), "An empty filter result needs the empty state.");
        vm.Filter = "";
        vm.ShowEnabledOnly = true;
        Check(vm.Rewards.Count(r => r.IsVisible) == 2, "Only switched-on rewards must show when filtered.");
        vm.ShowEnabledOnly = false;
        Check(vm.Rewards.All(r => r.IsVisible), "Clearing the filters must show every reward.");

        // Editing saves at once; values are clamped and defaults are not stored.
        rewards["regen"].Enabled = true;
        Pump();
        Check(TwitchSettings.Load(settingsPath).For("regen").Enabled && vm.EnabledCount == 3, "Switching a reward on must be saved.");
        rewards["regen"].Cost = 0;
        Check(rewards["regen"].Cost == 1, "The cost must be at least 1.");
        rewards["regen"].Cost = 1234;
        rewards["regen"].Duration = 99999;
        Check(TwitchSettings.Load(settingsPath).For("regen") is { Cost: 1234 } saved && saved.DurationSeconds == vm.MaxDurationSeconds,
            "Edits must be saved and durations capped.");
        rewards["regen"].Cost = EffectCatalog.Find("regen")!.Cost;
        Check(TwitchSettings.Load(settingsPath).For("regen").Cost is null, "A default value must not be stored as a custom one.");
        rewards["regen"].ResetCommand.Execute(null);
        Check(TwitchSettings.Load(settingsPath).For("regen").DurationSeconds is null, "Reset must restore the defaults.");
        Check(rewards["regen"].Description.Contains(" s.", StringComparison.Ordinal), "Timed rewards state their duration.");

        // A test run waits for the game like a redemption.
        rewards["heal"].TestCommand.Execute(null);
        rewards["final"].TestCommand.Execute(null);
        Pump();
        Check(vm.PendingEffects.Count == 2 && vm.LiveTabTitle == "Live (2)" && host.Notifications.Count == 2, "Test runs must queue while the game is not connected.");
        Check(vm.PendingEffects.All(p => p.Status.Contains("connect", StringComparison.OrdinalIgnoreCase)), "Waiting rows must say why they wait.");
        rewards["valor"].IsExpanded = true;

        var renders = new List<object>();
        foreach (var (tab, name) in new[] { (0, "setup"), (1, "rewards"), (2, "live") })
        {
            vm.SelectedTab = tab;
            var view = new TwitchView { DataContext = vm };
            var root = new Border { Background = (Brush)app.Resources["BackgroundBrush"], Padding = new Thickness(24), Child = view };
            root.SetValue(TextElement.ForegroundProperty, app.Resources["TextBrush"]);
            root.SetValue(TextElement.FontFamilyProperty, new FontFamily("Segoe UI")); root.SetValue(TextElement.FontSizeProperty, 13.5);
            double height = Layout(root, 1000);
            Check(height > 200 && height < 16000, $"Invalid Twitch {name} height {height}.");
            var texts = Descendants<TextBlock>(root).Where(t => Shown(t)).Select(t => t.Text).ToHashSet();
            if (tab == 0)
            {
                Check(texts.Contains("How redemptions behave") && texts.Contains("Stream overlay"), "The setup tab must show behaviour and overlay settings.");
                Check(Descendants<ComboBox>(root).Count(c => Shown(c)) == 3, "Setup needs the two behaviour choices and the language.");
            }
            if (tab == 1)
            {
                foreach (var reward in vm.Rewards) Check(texts.Contains(reward.DisplayTitle), "A reward is missing from the list: " + reward.Key);
                var switches = Descendants<CheckBox>(root).Where(c => Shown(c) && c.DataContext is RewardVm).ToArray();
                Check(switches.Length == rewards.Count && switches.All(s => s.IsChecked == ((RewardVm)s.DataContext).Enabled), "Every reward needs one switch showing its state.");
                Check(Descendants<TextBox>(root).Count(t => Shown(t) && t.DataContext == rewards["valor"]) >= 6, "The expanded reward must show its fields.");
                Check(Descendants<TextBox>(root).All(t => t.DataContext != rewards["heal"]), "Collapsed rewards must not create their fields.");
            }
            if (tab == 2)
            {
                Check(texts.Contains("Running now") && texts.Contains("Waiting") && texts.Contains("Nothing is running."), "The live tab must show both lists.");
                Check(Descendants<Button>(root).Count(b => Shown(b) && b.DataContext is PendingEffectVm) == 2, "Every waiting redemption needs a refund button.");
            }
            var bitmap = new RenderTargetBitmap(1000, (int)height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(root);
            var pixels = new byte[bitmap.PixelWidth * bitmap.PixelHeight * 4]; bitmap.CopyPixels(pixels, bitmap.PixelWidth * 4, 0);
            int bright = 0; for (int i = 0; i < pixels.Length; i += 4) if (pixels[i] > 240 && pixels[i + 1] > 240 && pixels[i + 2] > 240) ++bright;
            Check(bright < bitmap.PixelWidth * bitmap.PixelHeight * .02, "Unexpected white background on the Twitch " + name + " tab.");
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            using (var file = File.Create(Path.Combine(output, $"twitch-{name}.png"))) encoder.Save(file);
            renders.Add(new { tab = name, width = 1000, height });
        }

        // Refunding from the queue, then shutting down cleanly.
        vm.PendingEffects[0].RefundCommand.Execute(null);
        Pump();
        Check(vm.PendingEffects.Count == 1, "Refund must remove the waiting redemption.");
        Wait(vm.DisposeAsync().AsTask());
        Check(vm.PendingEffects.Count == 0 && !vm.IsOverlayRunning, "Shutting down must clear the queue and stop the overlay.");
        Check(errors.Count == 0, "Commands reported errors: " + string.Join(" | ", errors.Select(e => e.Message)));
        return new { success = true, checks, rewards = rewards.Count, renders };
    }

    /// <summary>Visible in the offscreen tree (IsVisible needs a window).</summary>
    private static bool Shown(DependencyObject element)
    {
        for (var current = element; current != null; current = VisualTreeHelper.GetParent(current))
            if (current is UIElement { Visibility: not Visibility.Visible }) return false;
        return true;
    }

    private static void Pump() => Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);

    private static void Wait(Task task)
    {
        var frame = new DispatcherFrame();
        task.ContinueWith(_ => frame.Continue = false, TaskScheduler.Default);
        Dispatcher.PushFrame(frame);
        task.GetAwaiter().GetResult();
    }

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
        throw new InvalidDataException("Twitch layout did not stabilize.");
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
