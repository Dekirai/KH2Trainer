using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
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
        public bool IsConnected { get; set; }
        public TrainerSnapshot Snapshot { get; set; } = TrainerSnapshot.Disconnected;
        public List<string> Logs { get; } = [];
        public List<(string Message, bool Error)> Notifications { get; } = [];
        // A connected fixture publishes a fresh native tick on every read, like the running bridge.
        public TrainerSnapshot ReadGameSnapshot()
        {
            if (Snapshot.Connected) Snapshot.Values[GameplayState.PublicationTickSlot] = unchecked((uint)Environment.TickCount);
            return Snapshot;
        }
        // Value commands write their own slot (command 1000 + slot).
        public Task Execute(int command, IReadOnlyList<double> arguments, string label)
        {
            if (!IsConnected) return Task.FromException(new InvalidOperationException("Not connected."));
            Snapshot.Values[command - 1000] = arguments[0];
            return Task.CompletedTask;
        }
        public void Log(string message) => Logs.Add(message);
        public void Notify(string message, bool isError) => Notifications.Add((message, isError));
    }

    /// <summary>Fresh controllable Sora (or the given blockers) with the music level readable.</summary>
    private static TrainerSnapshot Playable(GameplayBlockers blockers, double music)
    {
        var snapshot = new TrainerSnapshot { Connected = true, SceneReady = true, Status = 1, ProtocolVersion = 4 };
        foreach (var (slot, value) in new (int, double)[] { (GameplayState.KnownSlot, 1), (GameplayState.RoleSlot, (int)PlayerRole.Sora),
            (GameplayState.BlockersSlot, (uint)blockers), (GameplayState.ControllableSlot, blockers == GameplayBlockers.None ? 1 : 0),
            (GameplayState.PublicationTickSlot, 0), (145, music) })
        {
            snapshot.Values[slot] = value;
            snapshot.Valid[slot / 64] |= 1UL << (slot % 64); snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
        }
        return snapshot;
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
        var pausedInfo = new ActiveEffectInfo("regen", "Regeneration", "Fixture", null, 29, 30, true, true, "Menu");
        var pausedVm = new ActiveEffectVm(vm, pausedInfo);
        Check(pausedVm.RemainingText == "paused · 29 s left" && pausedVm.PauseReason == "Menu",
            "A paused reward must show its remaining time and explain its pause.");
        pausedVm.Update(pausedInfo with { Paused = false, PauseReason = null });
        Check(pausedVm.RemainingText == "29 s left" && pausedVm.PauseReason is null,
            "Resuming a reward must clear the pause explanation without spending time.");
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
        vm.PendingCleanups.Add(new PendingCleanupVm(new PendingCleanupInfo("silence", "Silence!", "Waiting for player control (Menu)")));

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
            var shown = Descendants<TextBlock>(root).Where(t => Shown(t)).ToArray();
            // A TextBlock composed of bound Runs keeps Text empty, so its Runs are compared as well.
            var texts = shown.Select(t => t.Text).Concat(shown.Select(t => string.Concat(t.Inlines.OfType<Run>().Select(r => r.Text)))).ToHashSet();
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
                Check(texts.Contains("Still being undone") && texts.Contains("Silence! · Waiting for player control (Menu)"),
                    "Rewards that are not undone yet must be listed with what they wait for.");
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
        Check(vm.PendingEffects.Count == 0 && !vm.IsOverlayRunning && !vm.HasCleanup, "Shutting down must clear the queue and stop the overlay.");

        // The real adapter reports the bridge's developer-desktop status (Hacker Mode never hides the streamer's own desktop).
        var adapterHost = new FakeHost(folder, catalog);
        var adapter = (IGameControl)Activator.CreateInstance(typeof(TwitchVm).Assembly.GetType("KH2Trainer.TrainerGameControl", throwOnError: true)!,
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic, binder: null, args: [adapterHost], culture: null)!;
        Check(adapter.BridgeStatus == -1, "A disconnected adapter must not claim a developer-desktop status.");
        adapterHost.IsConnected = true; adapterHost.Snapshot = Playable(GameplayBlockers.None, 80) with { Status = 3 };
        Check(adapter.BridgeStatus == 3, "The adapter must report the bridge status of the current snapshot.");

        // Closing while an ended reward is not undone: asked once, and a chosen wait finishes the restore within its bound.
        string closeFolder = Path.Combine(output, "close");
        if (Directory.Exists(closeFolder)) Directory.Delete(closeFolder, true);
        Directory.CreateDirectory(closeFolder);
        new TwitchSettings { OverlayEnabled = false }.Save(Path.Combine(closeFolder, "twitch.json"));
        var live = new FakeHost(closeFolder, catalog) { IsConnected = true, Snapshot = Playable(GameplayBlockers.None, 80) };
        var closing = new TwitchVm(live);
        closing.Rewards.Single(r => r.Key == "silence").TestCommand.Execute(null);
        Pump();
        Check(closing.ActiveEffects.Count == 1 && live.Snapshot.Values[145] == 0, "A connected test run must start Silence.");
        Become(live.Snapshot, Playable(GameplayBlockers.Menu, 0));
        IReadOnlyList<PendingCleanupInfo>? asked = null;
        Func<IReadOnlyList<PendingCleanupInfo>, bool> waitForCleanup = cleanups =>
        {
            asked = cleanups;
            live.Snapshot = Playable(GameplayBlockers.None, live.Snapshot.Values[145]); // The streamer closes the menu.
            return true;
        };
        var shutdown = (Task)typeof(TwitchVm).GetMethod("ShutdownAsync", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(closing, [waitForCleanup])!;
        var waited = Stopwatch.StartNew();
        Wait(shutdown);
        Check(asked is [{ Key: "silence", Title: "Silence!" }] && asked[0].Reason.Contains("Menu", StringComparison.Ordinal),
            "Closing must ask once and name the reward that is not undone yet.");
        Check(!closing.HasCleanup && live.Snapshot.Values[145] == 80 && waited.Elapsed < TwitchVm.CleanupWaitLimit,
            "Waiting must finish the restore within the bounded close wait.");
        Wait(closing.DisposeAsync().AsTask());

        // An exited game cannot take anything back: closing then never offers the futile wait.
        var gone = StartSilence(output, "close-gone", catalog, Check);
        gone.Host.IsConnected = false; gone.Host.Snapshot = TrainerSnapshot.Disconnected;
        bool askedWhileGone = false;
        waited.Restart();
        Wait(Shutdown(gone.Vm, _ => { askedWhileGone = true; return false; }));
        Check(!askedWhileGone && PendingCleanupCount(gone.Vm) == 1 && waited.Elapsed < TwitchVm.CleanupWaitLimit,
            "Closing after the game exited must not ask to wait for cleanups it cannot finish.");
        Wait(gone.Vm.DisposeAsync().AsTask());

        // The game exits during a chosen wait: the wait ends at once instead of running out its limit.
        var exiting = StartSilence(output, "close-exit", catalog, Check);
        Become(exiting.Host.Snapshot, Playable(GameplayBlockers.Menu, 0));
        var exit = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(600) };
        exit.Tick += (_, _) => { exit.Stop(); exiting.Host.IsConnected = false; exiting.Host.Snapshot = TrainerSnapshot.Disconnected; };
        bool askedBeforeExit = false;
        waited.Restart();
        Wait(Shutdown(exiting.Vm, _ => { askedBeforeExit = true; exit.Start(); return true; }));
        Check(askedBeforeExit && PendingCleanupCount(exiting.Vm) == 1 && waited.Elapsed < TwitchVm.CleanupWaitLimit / 2,
            "A chosen close wait must stop as soon as the game disconnects.");
        Wait(exiting.Vm.DisposeAsync().AsTask());
        Check(errors.Count == 0, "Commands reported errors: " + string.Join(" | ", errors.Select(e => e.Message)));
        return new { success = true, checks, rewards = rewards.Count, renders };
    }

    /// <summary>Changes a fixture snapshot in place, so the adapter's short snapshot cache already holds the new state.</summary>
    private static void Become(TrainerSnapshot target, TrainerSnapshot source)
    {
        source.Values.CopyTo(target.Values, 0);
        source.Valid.CopyTo(target.Valid, 0);
        source.Supported.CopyTo(target.Supported, 0);
        target.Values[GameplayState.PublicationTickSlot] = unchecked((uint)Environment.TickCount); // Still a fresh publication.
    }

    /// <summary>A separate connected view model whose Silence! test run has muted the music (80 to 0).</summary>
    private static (FakeHost Host, TwitchVm Vm) StartSilence(string output, string name, IReadOnlyList<FeatureDefinition> catalog, Action<bool, string> check)
    {
        string folder = Path.Combine(output, name);
        if (Directory.Exists(folder)) Directory.Delete(folder, true);
        Directory.CreateDirectory(folder);
        new TwitchSettings { OverlayEnabled = false }.Save(Path.Combine(folder, "twitch.json"));
        var host = new FakeHost(folder, catalog) { IsConnected = true, Snapshot = Playable(GameplayBlockers.None, 80) };
        var vm = new TwitchVm(host);
        vm.Rewards.Single(r => r.Key == "silence").TestCommand.Execute(null);
        Pump();
        check(vm.ActiveEffects.Count == 1 && host.Snapshot.Values[145] == 0, $"A connected test run must start Silence ({name}).");
        return (host, vm);
    }

    private static Task Shutdown(TwitchVm vm, Func<IReadOnlyList<PendingCleanupInfo>, bool> waitForCleanup) =>
        (Task)typeof(TwitchVm).GetMethod("ShutdownAsync", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(vm, [waitForCleanup])!;

    private static int PendingCleanupCount(TwitchVm vm) =>
        ((EffectEngine)typeof(TwitchVm).GetProperty("Engine", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(vm)!).PendingCleanupCount;

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
