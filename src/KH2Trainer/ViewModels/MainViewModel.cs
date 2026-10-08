using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows.Media;
using System.Windows.Threading;
using KH2Trainer.Core;
using Microsoft.Win32;

namespace KH2Trainer;

public sealed record ProcessChoice(GameProcess Process) { public string Label => $"{Process.Name} · PID {Process.Pid}"; }

public enum ConnectionState { NoGame, GameFound, Connecting, WaitingForScene, Ready, Warning }

/// <summary>The application shell: navigation, game connection, search, favorites and activity.</summary>
public sealed class MainViewModel : Observable, IFeatureHost, ITwitchHost, ITwitchMovementHost, IDisposable
{
    private static readonly string[] QuickActionIds = ["player.restore", "player.position.bookmark", "player.position.return", "trainer.reset", "developer.show", "developer.hide"];
    private const int MaxSearchResults = 150;

    private readonly GameSession session = new();
    private readonly DispatcherTimer timer, notificationTimer;
    private readonly string settingsPath;
    private readonly UserSettings settings;
    private readonly List<FeatureVm> features = [];
    private readonly Dictionary<string, FeatureVm> byId;
    private readonly Dictionary<string, string> categoryLocations = new(StringComparer.Ordinal);
    private readonly List<string> activity = [];
    private TrainerSnapshot snapshot = TrainerSnapshot.Disconnected;
    private int pollCount;
    private double? lastShortcutSequence;
    private bool busy, connecting, isActivityOpen, notificationIsError, wasConnected;
    private readonly int resetCommand;
    private string search = "", statusMessage = "Start the game, then connect to begin.", notification = "";
    private PageVm selectedPage;
    private SearchResultsVm? searchResults;
    private ProcessChoice? selectedProcess;

    public string UserFolder { get; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "KH2Trainer");
    public IReadOnlyList<FeatureDefinition> Catalog { get; }
    public IReadOnlyList<FeatureVm> Features => features;
    internal GameSession Session => session;
    public MovementOperationHandle? PendingMovement => session.PendingMovement;
    public Task<MovementCommandResult> ExecuteMovementAsync(MovementCommand command, CancellationToken cancellation = default) => session.ExecuteMovementAsync(command, cancellation);
    public Task<MovementCommandResult> ResolveMovementAsync(MovementOperationHandle handle, CancellationToken cancellation = default) => session.ResolveMovementAsync(handle, cancellation);
    internal TrainerSnapshot Snapshot => snapshot;
    public TrainerSnapshot ReadGameSnapshot() => session.ReadSnapshot();
    public string VersionLabel { get; } = "Version " + (Assembly.GetExecutingAssembly().GetName().Version?.ToString(2) ?? "dev");

    // Navigation
    public ObservableCollection<PageVm> Pages { get; } = [];
    public HomeVm Home { get; }
    public ProfilesVm Profiles { get; }
    public AboutVm About { get; }
    public AssetExplorerViewModel Assets { get; }
    public RuntimeDiagnosticsViewModel Diagnostics { get; }
    public TwitchVm Twitch { get; }
    public PageVm SelectedPage
    {
        get => selectedPage;
        set { if (value != null && Set(ref selectedPage, value)) { Search = ""; RefreshContent(); } }
    }
    public string Search
    {
        get => search;
        set
        {
            if (!Set(ref search, value ?? "")) return;
            string query = search.Trim();
            // Name matches first, so "hp" lists HP controls before descriptions that mention it.
            searchResults = query.Length == 0 ? null : new SearchResultsVm(query,
                features.Where(f => f.Matches(query)).OrderBy(f => f.Name.Contains(query, StringComparison.OrdinalIgnoreCase) ? 0 : 1).ToArray(),
                categoryLocations, MaxSearchResults);
            RefreshContent();
        }
    }
    public bool IsSearching => searchResults != null;
    public object CurrentContent => (object?)searchResults ?? (selectedPage is ToolPageVm tool ? tool.Content : selectedPage);
    public string CurrentTitle => searchResults != null ? "Search" : selectedPage.Title;
    public string CurrentSubtitle => searchResults?.Summary ?? selectedPage.Subtitle;
    private void RefreshContent()
    {
        Changed(nameof(IsSearching), nameof(CurrentContent), nameof(CurrentTitle), nameof(CurrentSubtitle), nameof(ShowBanner));
    }

    // Presentation preferences
    public bool ShowDescriptions
    {
        get => settings.ShowDescriptions;
        set
        {
            if (settings.ShowDescriptions == value) return;
            settings.ShowDescriptions = value; settings.Save(settingsPath); Changed();
            foreach (var feature in features) feature.RefreshPresentation();
        }
    }
    public bool IsFavorite(string featureId) => settings.Favorites.Contains(featureId);
    public void ToggleFavorite(FeatureVm feature)
    {
        if (!settings.Favorites.Remove(feature.Id)) settings.Favorites.Add(feature.Id);
        settings.Save(settingsPath); feature.RefreshPresentation(); Home.RefreshPinned();
    }
    public IReadOnlyList<FeatureVm> FavoriteFeatures => settings.Favorites.Select(id => byId.GetValueOrDefault(id)).OfType<FeatureVm>().ToArray();
    public IReadOnlyList<FeatureVm> QuickActions { get; }
    internal string SaveFolderSetting { get => settings.SaveFolder; set { settings.SaveFolder = value; settings.Save(settingsPath); } }

    // Connection
    public bool Busy { get => busy; private set { if (!Set(ref busy, value)) return; RefreshCommands(); foreach (var feature in features) feature.RefreshCanToggle(); } }
    public ObservableCollection<ProcessChoice> Processes { get; } = [];
    public ProcessChoice? SelectedProcess
    {
        get => selectedProcess;
        // A page being swapped out pushes null from its ComboBox; only an empty list clears the choice.
        set { if (value is null && Processes.Count > 0) return; if (Set(ref selectedProcess, value)) RefreshConnection(); }
    }
    public bool HasMultipleProcesses => Processes.Count > 1;
    public bool IsConnected => session.Connected;
    public ConnectionState State =>
        connecting && !session.Connected ? ConnectionState.Connecting :
        !snapshot.Connected ? SelectedProcess != null ? ConnectionState.GameFound : ConnectionState.NoGame :
        snapshot.ErrorCode != 0 ? ConnectionState.Warning :
        snapshot.SceneReady ? ConnectionState.Ready : ConnectionState.WaitingForScene;
    public Brush StatusBrush => State switch
    {
        ConnectionState.Ready => Brushes.MediumSeaGreen,
        ConnectionState.WaitingForScene or ConnectionState.Warning or ConnectionState.Connecting => Brushes.Goldenrod,
        ConnectionState.GameFound => Brushes.SteelBlue,
        _ => Brushes.SlateGray
    };
    public string ConnectionTitle => State switch
    {
        ConnectionState.Ready => "Connected",
        ConnectionState.WaitingForScene => "Connected · no scene",
        ConnectionState.Warning => "Connected · attention",
        ConnectionState.Connecting => "Connecting…",
        ConnectionState.GameFound => "Game running",
        _ => "Game not running"
    };
    public string ConnectionDetail => snapshot.Connected ? $"PID {session.ProcessId} · {snapshot.FrameCount:N0} frames"
        : SelectedProcess != null ? $"PID {SelectedProcess.Process.Pid} · ready to connect" : "Start KH2 Final Mix to begin";
    public string ConnectLabel => session.Connected ? "Disconnect" : connecting ? "Connecting…" : "Connect";
    public bool ShowConnectButton => session.Connected || SelectedProcess != null || connecting;
    public bool ShowStartButton => !ShowConnectButton;
    public string StatusMessage { get => statusMessage; private set => Set(ref statusMessage, value); }

    /// <summary>Explains locked controls on pages that talk to the game.</summary>
    public bool ShowBanner => (IsSearching || selectedPage.UsesGame) && State != ConnectionState.Ready && State != ConnectionState.Warning;
    public string BannerText => State switch
    {
        ConnectionState.WaitingForScene => "Waiting for a playable scene. Controls that need the field unlock once you are in control of Sora.",
        ConnectionState.Connecting => "Connecting to the game…",
        ConnectionState.GameFound => "The game is running. Connect to unlock the controls.",
        _ => "Not connected. Start the game and connect to unlock the controls. Live values show — until then."
    };
    public bool BannerIsWarning => State == ConnectionState.WaitingForScene;

    // Live summary for Home
    public string HealthText => Pair("player.hp", "player.hp.max");
    public string MagicText => Pair("player.mp", "player.mp.max");
    public string DriveText => Pair("player.drive.bars", "player.drive.max");
    public double HealthFraction => Fraction("player.hp", "player.hp.max");
    public double MagicFraction => Fraction("player.mp", "player.mp.max");
    public double DriveFraction => Fraction("player.drive.bars", "player.drive.max");
    public string LevelText => Single("player.level");
    public string MunnyText => Single("munny", "N0");
    public string SessionSummary => $"{Catalog.Count} features in this build. " + (snapshot.Connected
        ? snapshot.SceneReady ? "A playable scene is ready." : "Waiting for a playable scene."
        : "The executable and mod loader are verified before the bridge is loaded.");

    // Notifications and activity
    public string Notification { get => notification; private set { if (Set(ref notification, value)) Changed(nameof(HasNotification)); } }
    public bool HasNotification => notification.Length > 0;
    public bool NotificationIsError { get => notificationIsError; private set => Set(ref notificationIsError, value); }
    public ObservableCollection<string> Activity { get; } = [];
    public string LastActivity => Activity.FirstOrDefault() ?? "No activity yet.";
    public bool IsActivityOpen { get => isActivityOpen; set => Set(ref isActivityOpen, value); }

    public AsyncCommand ConnectCommand { get; }
    public AsyncCommand StartGameCommand { get; }
    public AsyncCommand ExportLogCommand { get; }
    public RelayCommand ClearSearchCommand { get; }
    public RelayCommand DismissNotificationCommand { get; }
    public RelayCommand ToggleActivityCommand { get; }

    public MainViewModel()
    {
        settingsPath = Path.Combine(UserFolder, "settings.json");
        settings = UserSettings.Load(settingsPath);
        using (var stream = DataResources.Open("features.json")) Catalog = FeatureCatalog.Load(stream);
        var lookups = LoadLookups();
        features.AddRange(Catalog.Select(f => new FeatureVm(f, this, lookups)));
        byId = features.ToDictionary(f => f.Id, StringComparer.Ordinal);
        QuickActions = QuickActionIds.Select(id => byId.GetValueOrDefault(id)).OfType<FeatureVm>().ToArray();
        resetCommand = byId.GetValueOrDefault("trainer.reset")?.Definition.CommandId ?? -1;

        ConnectCommand = new AsyncCommand(Connect, () => !Busy && (session.Connected || SelectedProcess != null));
        StartGameCommand = new AsyncCommand(StartGame, () => !Busy);
        ExportLogCommand = new AsyncCommand(ExportLog);
        ClearSearchCommand = new RelayCommand(() => Search = "");
        DismissNotificationCommand = new RelayCommand(() => Notification = "");
        ToggleActivityCommand = new RelayCommand(() => IsActivityOpen = !IsActivityOpen);

        Home = new HomeVm(this);
        Profiles = new ProfilesVm(this);
        About = new AboutVm(this);
        Assets = new AssetExplorerViewModel(Log);
        Diagnostics = new RuntimeDiagnosticsViewModel();
        Twitch = new TwitchVm(this);
        Pages.Add(Home);
        foreach (var section in CategoryLayout.Build(features))
        {
            Pages.Add(section);
            foreach (var tab in section.Tabs)
                foreach (var group in tab.Groups)
                    categoryLocations[group.Title] = section.Title + " › " + tab.Title + (tab.Groups.Count > 1 ? " · " + group.Title : "");
        }
        Pages.Add(Twitch);
        Pages.Add(new ToolPageVm("Asset Explorer", "", "Browse game archives and extract selected assets. Works without a game connection.", Assets));
        Pages.Add(new ToolPageVm("Game Messages", "", "Look up the game's original messages and what their buttons do.", Diagnostics));
        Pages.Add(Profiles);
        Pages.Add(About);
        selectedPage = Home;

        notificationTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(8) };
        notificationTimer.Tick += (_, _) => { notificationTimer.Stop(); if (!NotificationIsError) Notification = ""; };
        timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(200) };
        timer.Tick += (_, _) => Poll();
        timer.Start();
        RefreshProcesses();
        Log("Trainer opened. No game changes have been applied.");
    }

    public FeatureVm? Feature(string id) => byId.GetValueOrDefault(id);

    private string Pair(string valueId, string maxId)
    {
        int value = byId.GetValueOrDefault(valueId)?.Definition.ValueSlot ?? -1, max = byId.GetValueOrDefault(maxId)?.Definition.ValueSlot ?? -1;
        return snapshot.HasValue(value) ? $"{snapshot.Values[value]:0.##} / {(snapshot.HasValue(max) ? snapshot.Values[max].ToString("0.##") : "—")}" : "—";
    }
    private double Fraction(string valueId, string maxId)
    {
        int value = byId.GetValueOrDefault(valueId)?.Definition.ValueSlot ?? -1, max = byId.GetValueOrDefault(maxId)?.Definition.ValueSlot ?? -1;
        return snapshot.HasValue(value) && snapshot.HasValue(max) && snapshot.Values[max] > 0 ? Math.Clamp(snapshot.Values[value] / snapshot.Values[max], 0, 1) : 0;
    }
    private string Single(string id, string format = "0.##")
    {
        int slot = byId.GetValueOrDefault(id)?.Definition.ValueSlot ?? -1;
        return snapshot.HasValue(slot) ? snapshot.Values[slot].ToString(format) : "—";
    }

    private static Dictionary<string, IReadOnlyList<FeatureChoice>> LoadLookups()
    {
        var result = new Dictionary<string, IReadOnlyList<FeatureChoice>>();
        foreach (string name in new[] { "items", "abilities", "characters" })
        {
            using var stream = DataResources.Open(name + ".json");
            using var document = JsonDocument.Parse(stream);
            var array = document.RootElement.ValueKind == JsonValueKind.Array ? document.RootElement : document.RootElement.GetProperty("items");
            result[name] = array.EnumerateArray().Select(e => new FeatureChoice($"{e.GetProperty("name").GetString()} [{e.GetProperty("id").GetInt32()}]", e.GetProperty("id").GetInt32())).OrderBy(e => e.Label).ToArray();
            if (name == "items")
            {
                foreach (var type in new[] { (Key: "armor", Type: "Armor"), (Key: "accessories", Type: "Accessory") })
                    result[type.Key] = new[] { new FeatureChoice("Unequip [0]", 0) }.Concat(array.EnumerateArray()
                        .Where(e => e.GetProperty("type_name").GetString() == type.Type)
                        .Select(e => new FeatureChoice($"{e.GetProperty("name").GetString()} [{e.GetProperty("id").GetInt32()}]", e.GetProperty("id").GetInt32()))
                        .OrderBy(e => e.Label)).ToArray();
            }
        }
        return result;
    }

    private void RefreshProcesses()
    {
        var found = TargetGame.FindRunning();
        if (found.Select(p => p.Pid).SequenceEqual(Processes.Select(p => p.Process.Pid))) return;
        int? prior = SelectedProcess?.Process.Pid;
        Processes.Clear(); foreach (var item in found) Processes.Add(new ProcessChoice(item));
        SelectedProcess = Processes.FirstOrDefault(p => p.Process.Pid == prior) ?? Processes.FirstOrDefault();
        Changed(nameof(HasMultipleProcesses));
    }

    private void Poll()
    {
        try
        {
            if (++pollCount % 10 == 0) RefreshProcesses();
            if (!session.Connected && snapshot.Connected) { session.Dispose(); Log("Game process exited. Session disconnected."); }
            snapshot = session.ReadSnapshot();
            // Twitch effects cannot outlive the game connection; waiting redemptions are refunded.
            if (wasConnected && !session.Connected) _ = Twitch.StopAllAsync("The game was disconnected");
            wasConnected = session.Connected;
            if (snapshot.HasValue(121))
            {
                double currentSequence = snapshot.Values[121];
                if (lastShortcutSequence.HasValue && lastShortcutSequence != currentSequence && snapshot.HasValue(119) && snapshot.HasValue(120))
                {
                    string action = Catalog.FirstOrDefault(f => f.CommandId == snapshot.Values[119])?.Name ?? "Training action";
                    Log($"Game shortcut · {action}: " + (snapshot.Values[120] == 0 ? "completed." : $"rejected (code {snapshot.Values[120]:0}). {snapshot.Message}"));
                }
                lastShortcutSequence = currentSequence;
            }
            else lastShortcutSequence = null;
            if (!Busy) StatusMessage = snapshot.Message;
            foreach (var feature in features) feature.Update(snapshot);
            Twitch.Tick();
            Changed(nameof(HealthText), nameof(MagicText), nameof(DriveText), nameof(HealthFraction), nameof(MagicFraction), nameof(DriveFraction),
                nameof(LevelText), nameof(MunnyText), nameof(SessionSummary));
            RefreshConnection();
        }
        catch (IOException e) { StatusMessage = e.Message; }
        catch (InvalidOperationException e) { StatusMessage = e.Message; }
    }

    private void RefreshConnection()
    {
        Changed(nameof(IsConnected), nameof(State), nameof(StatusBrush), nameof(ConnectionTitle), nameof(ConnectionDetail), nameof(ConnectLabel),
            nameof(ShowConnectButton), nameof(ShowStartButton), nameof(ShowBanner), nameof(BannerText), nameof(BannerIsWarning));
        RefreshCommands();
    }

    private void RefreshCommands()
    {
        foreach (var command in new[] { ConnectCommand, StartGameCommand }) command?.Refresh();
        Profiles?.RefreshCommands();
        foreach (var feature in features) feature.ApplyCommand.Refresh();
        Changed(nameof(ConnectLabel), nameof(State));
    }

    internal void SetBusy(bool value) => Busy = value;

    private async Task Connect()
    {
        Busy = true; connecting = !session.Connected; RefreshConnection();
        try
        {
            if (session.Connected)
            {
                // End Twitch effects first so their values can still be restored.
                await Twitch.StopAllAsync("The trainer disconnected from the game");
                await session.DisconnectAsync(); Log("Disconnected; persistent effects disabled."); return;
            }
            int pid = SelectedProcess?.Process.Pid ?? throw new InvalidOperationException("Start KH2 first.");
            using var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("KH2Trainer.Bridge") ?? throw new InvalidOperationException("This development build does not contain a native bridge yet.");
            using var bytes = new MemoryStream(); resource.CopyTo(bytes);
            await session.ConnectAsync(pid, bytes.ToArray(), new Progress<string>(s => StatusMessage = s));
            Log($"Connected to KH2 process {pid}. Build checks passed.");
        }
        catch (Exception e) { Log("Connection failed: " + e.Message); throw; }
        finally { connecting = false; Busy = false; Poll(); }
    }

    private async Task StartGame()
    {
        string path = TargetGame.DefaultPath;
        if (!File.Exists(path)) { var picker = new OpenFileDialog { Filter = "KH2 executable|KINGDOM HEARTS II FINAL MIX.exe" }; if (picker.ShowDialog() != true) return; path = picker.FileName; }
        await Task.Run(() => TargetGame.Validate(path));
        Process.Start(new ProcessStartInfo(path) { UseShellExecute = true, WorkingDirectory = Path.GetDirectoryName(path) }); Log("Game launch requested.");
    }

    public async Task Execute(int command, IReadOnlyList<double> arguments, string label)
    {
        // A full reset also ends Twitch effects, so they do not re-apply their values afterwards.
        if (command == resetCommand) await Twitch.StopAllAsync("All trainer changes were reset");
        try { var result = await session.ExecuteAsync(command, arguments); Log($"{label}: {result.Message}"); if (!result.Success) throw new BridgeCommandRejectedException(result.Code, result.Message); }
        catch (Exception e) { Log($"{label} failed: {e.Message}"); throw; }
    }

    private Task ExportLog()
    {
        var picker = new SaveFileDialog { Filter = "Text log|*.txt", FileName = "KH2_Trainer_Log.txt" };
        if (picker.ShowDialog() == true) File.WriteAllLines(picker.FileName, activity); return Task.CompletedTask;
    }
    internal IReadOnlyList<string> ActivityLog => activity;

    public void Notify(string message, bool isError)
    {
        NotificationIsError = isError; Notification = message;
        notificationTimer.Stop(); notificationTimer.Start();
    }

    public void Log(string message)
    {
        string entry = $"{DateTime.Now:HH:mm:ss}   {message}";
        activity.Add(entry); Activity.Insert(0, entry);
        while (Activity.Count > 200) Activity.RemoveAt(Activity.Count - 1);
        Changed(nameof(LastActivity));
    }

    internal static void OpenPath(string path) => Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });

    /// <summary>Runs before the window closes: ends Twitch effects while the game is still connected.</summary>
    public async Task ShutdownAsync()
    {
        timer.Stop();
        await Twitch.ShutdownAsync();
    }

    public void Dispose() { timer.Stop(); notificationTimer.Stop(); Assets.Dispose(); _ = Twitch.DisposeAsync(); session.Dispose(); }
}

/// <summary>Search across every feature, grouped by category.</summary>
public sealed class SearchResultsVm
{
    public string Query { get; }
    public IReadOnlyList<FeatureGroupVm> Groups { get; }
    public int Count { get; }
    public bool IsEmpty => Count == 0;
    public bool IsTruncated { get; }
    public string Summary => Count == 0 ? $"No features match “{Query}”." :
        IsTruncated ? $"Showing the first {Groups.Sum(g => g.Controls.Count + g.Readouts.Count)} of {Count} matches for “{Query}”. Refine the search to narrow it down." :
        $"{Count} {(Count == 1 ? "match" : "matches")} for “{Query}”.";
    public SearchResultsVm(string query, IReadOnlyList<FeatureVm> matches, IReadOnlyDictionary<string, string> locations, int limit)
    {
        Query = query; Count = matches.Count; IsTruncated = matches.Count > limit;
        Groups = matches.Take(limit).GroupBy(f => f.Category).Select(g =>
        {
            var group = FeatureGroupVm.Create(locations.GetValueOrDefault(g.Key) ?? g.Key, g);
            group.ShowTitle = true; return group;
        }).ToArray();
    }
}
