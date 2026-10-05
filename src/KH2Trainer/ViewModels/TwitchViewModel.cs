using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Net.Sockets;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using KH2Trainer.Core;
using KH2Trainer.Twitch;
using Microsoft.Win32;

namespace KH2Trainer;

/// <summary>What the Twitch page needs from the trainer window.</summary>
public interface ITwitchHost
{
    string UserFolder { get; }
    IReadOnlyList<FeatureDefinition> Catalog { get; }
    bool IsConnected { get; }
    /// <summary>Reads the game state now (not the last poll).</summary>
    TrainerSnapshot ReadGameSnapshot();
    Task Execute(int command, IReadOnlyList<double> arguments, string label);
    void Log(string message);
    void Notify(string message, bool isError);
}

/// <summary>
/// Lets Twitch effects use the trainer's game connection. Reads go to a fresh snapshot after each
/// command, because an effect often checks the value it just changed.
/// </summary>
internal sealed class TrainerGameControl(ITwitchHost shell) : IGameControl
{
    private TrainerSnapshot snapshot = TrainerSnapshot.Disconnected;
    private long readAt = long.MinValue;
    private bool dirty = true;

    public bool IsConnected => shell.IsConnected && Current is { Connected: true, Status: >= 1 };
    public bool SceneReady => Current.SceneReady;
    public bool Supports(int capabilitySlot) => Current.Supports(capabilitySlot);

    public bool TryRead(int valueSlot, out double value)
    {
        var current = Current;
        if (current.Connected && current.HasValue(valueSlot)) { value = current.Values[valueSlot]; return true; }
        value = 0;
        return false;
    }

    public async Task ExecuteAsync(int command, IReadOnlyList<double> arguments, string label)
    {
        try { await shell.Execute(command, arguments, label); }
        finally { dirty = true; }
    }

    private TrainerSnapshot Current
    {
        get
        {
            long now = Environment.TickCount64;
            if (!dirty && now - readAt < 50) return snapshot;
            try { snapshot = shell.ReadGameSnapshot(); readAt = now; dirty = false; }
            catch (Exception error) when (error is IOException or InvalidOperationException or ObjectDisposedException) { }
            return snapshot;
        }
    }
}

/// <summary>Encrypts the Twitch login for the current Windows user.</summary>
internal sealed class DpapiProtector : ISecretProtector
{
    private static readonly byte[] Entropy = "KH2Trainer.Twitch"u8.ToArray();
    public byte[] Protect(byte[] data) => System.Security.Cryptography.ProtectedData.Protect(data, Entropy, System.Security.Cryptography.DataProtectionScope.CurrentUser);
    public byte[] Unprotect(byte[] data) => System.Security.Cryptography.ProtectedData.Unprotect(data, Entropy, System.Security.Cryptography.DataProtectionScope.CurrentUser);
}

public sealed record Option<T>(string Label, T Value)
{
    public override string ToString() => Label;
}

/// <summary>Channel point rewards: setup, the reward list and the live queue.</summary>
public sealed class TwitchVm : PageVm, IAsyncDisposable
{
    public const string DeveloperConsoleUrl = "https://dev.twitch.tv/console/apps/create";
    public const int TwitchRewardLimit = 50;
    private static readonly TimeSpan SyncDelay = TimeSpan.FromSeconds(1.2);

    private readonly ITwitchHost shell;
    private readonly string settingsPath;
    private readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(20) };
    private readonly DispatcherTimer syncTimer;
    private readonly HashSet<string> dirty = new(StringComparer.Ordinal);
    private readonly Dictionary<string, RewardVm> byKey = new(StringComparer.Ordinal);
    private OverlayServer? overlay;
    private int selectedTab;
    private string filter = "", overlayStatus = "", syncError = "";
    private bool showEnabledOnly, syncing, shutDown;
    private Task? shutdown;
    private string lastEventKey = "";

    public TwitchVm(ITwitchHost shell)
    {
        this.shell = shell;
        settingsPath = Path.Combine(shell.UserFolder, "twitch.json");
        ImageFolder = Path.Combine(shell.UserFolder, "TwitchImages");
        Settings = TwitchSettings.Load(settingsPath);
        var tokens = new TokenStore(Path.Combine(shell.UserFolder, "twitch-login.bin"), new DpapiProtector());
        Game = new TrainerGameControl(shell);
        Service = new TwitchService(http, tokens, Settings, SaveSettings, redemption => Engine!.Submit(redemption), shell.Log,
            withdraw: id => _ = Engine!.CancelAsync(id, DateTimeOffset.UtcNow));
        Engine = new EffectEngine(Game, new FeatureMap(shell.Catalog), EffectCatalog.All,
            key => RewardResolver.Options(EffectCatalog.Find(key)!, Settings), () => RewardResolver.Engine(Settings), Service, shell.Log);

        foreach (var effect in EffectCatalog.All) byKey[effect.Key] = new RewardVm(this, effect);
        Groups = Enum.GetValues<RewardCategory>()
            .Select(category => new RewardGroupVm(category, byKey.Values.Where(r => r.Effect.Category == category).ToArray())).ToArray();

        LanguageOptions = [new("English", RewardLanguage.English), new("Deutsch", RewardLanguage.German)];
        SameEffectOptions =
        [
            new("Add its time to the running effect", SameEffectBehavior.Extend),
            new("Refund the channel points", SameEffectBehavior.Refund),
            new("Queue it until the running one ends", SameEffectBehavior.Queue),
        ];
        ConflictOptions =
        [
            new("Queue it until the running one ends", ConflictBehavior.Queue),
            new("Replace the running effect", ConflictBehavior.Replace),
            new("Refund the channel points", ConflictBehavior.Refund),
        ];

        ConnectCommand = new AsyncCommand(() => Connect(interactive: true), () => Service.State is not (TwitchConnectionState.Connecting or TwitchConnectionState.WaitingForAuthorization) && HasClientId);
        CancelConnectCommand = new RelayCommand(Service.CancelConnect);
        DisconnectCommand = new AsyncCommand(() => Service.DisconnectAsync(forgetLogin: false), () => Service.IsConnected);
        LogoutCommand = new AsyncCommand(Logout, () => Service.State is TwitchConnectionState.Connected or TwitchConnectionState.Disconnected or TwitchConnectionState.Error);
        OpenDeveloperConsoleCommand = new RelayCommand(() => OpenUrl(DeveloperConsoleUrl));
        OpenActivationCommand = new RelayCommand(() => { if (Service.VerificationUri is { } url) OpenUrl(url); });
        CopyCodeCommand = new RelayCommand(() => { if (Service.UserCode is { } code) CopyText(code, "Code copied."); });
        OpenDashboardCommand = new RelayCommand(() => OpenUrl(Service.RewardsDashboardUrl));
        PauseCommand = new AsyncCommand(() => SafeAsync(() => Service.SetPausedAsync(!Service.RewardsPaused)), () => Service.IsConnected && !syncing);
        ResyncCommand = new AsyncCommand(() => SafeAsync(Service.SyncAllAsync), () => Service.IsConnected && !syncing);
        CopyOverlayCommand = new RelayCommand(() => CopyText(OverlayUrl, "Overlay URL copied. Add it as a Browser Source in OBS."), () => overlay != null);
        OpenOverlayCommand = new RelayCommand(() => OpenUrl(OverlayUrl), () => overlay != null);
        StopAllCommand = new AsyncCommand(() => StopAllAsync("Stopped by the streamer"), () => Engine.ActiveEffects.Count > 0 || Engine.PendingEffects.Count > 0);
        ClearFilterCommand = new RelayCommand(() => Filter = "");

        Service.StateChanged += OnServiceChanged;
        Service.RewardStatusChanged += key => { if (byKey.TryGetValue(key, out var reward)) reward.RefreshStatus(); };
        Service.AuthorizationRequested += OpenUrl;
        Engine.Changed += RefreshLive;

        syncTimer = new DispatcherTimer { Interval = SyncDelay };
        syncTimer.Tick += async (_, _) => { syncTimer.Stop(); await SyncDirtyAsync(); };
        StartOverlay();
        RefreshSummary();
        if (Settings.LoadProblem is { } problem) shell.Log("Twitch: " + problem);
        // With a saved login the rewards go live without visiting this page; nothing is asked if the login expired.
        if (Service.HasSavedLogin) _ = Connect(interactive: false);
    }

    internal TwitchSettings Settings { get; }
    internal TwitchService Service { get; }
    internal EffectEngine Engine { get; }
    internal TrainerGameControl Game { get; }
    internal string ImageFolder { get; }

    public override string Title => "Twitch";
    public override string Icon => "";
    public override string Subtitle => "Viewers spend channel points to help or hinder Sora. Set it up once, then switch rewards on and off.";
    public override string Group => "STREAM";

    // Tabs
    public int SelectedTab
    {
        get => selectedTab;
        set { if (Set(ref selectedTab, Math.Clamp(value, 0, 2))) Changed(nameof(IsSetupTab), nameof(IsRewardsTab), nameof(IsLiveTab)); }
    }
    public bool IsSetupTab => selectedTab == 0;
    public bool IsRewardsTab => selectedTab == 1;
    public bool IsLiveTab => selectedTab == 2;
    public string LiveTabTitle => Engine.ActiveEffects.Count + Engine.PendingEffects.Count is int count and > 0 ? $"Live ({count})" : "Live";

    // Connection
    public bool HasBuiltInClientId => TwitchApp.ClientId.Length > 0;
    public bool ShowClientIdStep => !HasBuiltInClientId;
    public bool HasClientId => Settings.EffectiveClientId.Length > 0;
    public string ConnectStepTitle => HasBuiltInClientId ? "CONNECT YOUR CHANNEL" : "3   CONNECT YOUR CHANNEL";
    public string ClientId
    {
        get => Settings.ClientId;
        set
        {
            string clean = (value ?? "").Trim();
            if (clean == Settings.ClientId) return;
            // Twitch lets only the app that created a reward change or delete it.
            if (Service.RewardsOnTwitch > 0 && MessageBox.Show(
                    $"{Service.RewardsOnTwitch} rewards on your channel were created with the current Twitch app, and only that app can change or delete them. " +
                    "Switch them off first (while connected) to remove them, or delete them in your reward dashboard.\n\nChange the Client ID anyway?",
                    "Twitch", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
            {
                Changed();
                return;
            }
            foreach (var reward in Settings.Rewards.Values) { reward.TwitchRewardId = null; reward.SyncedFingerprint = null; }
            Settings.ClientId = clean;
            SaveSettings();
            Changed();
            _ = SafeAsync(Service.ClientIdChangedAsync);
        }
    }
    public TwitchConnectionState State => Service.State;
    public string ConnectionTitle => Service.State switch
    {
        TwitchConnectionState.NotConfigured => "Not set up",
        TwitchConnectionState.WaitingForAuthorization => "Confirm on Twitch",
        TwitchConnectionState.Connecting => "Connecting…",
        TwitchConnectionState.Connected => $"Connected as {Service.DisplayName}",
        TwitchConnectionState.Error => "Needs attention",
        _ => "Not connected",
    };
    public string StatusText => Service.StatusText;
    public Brush StatusBrush => Service.State switch
    {
        TwitchConnectionState.Connected => Service.EventSubState == EventSubState.Connected ? Brushes.MediumSeaGreen : Brushes.Goldenrod,
        TwitchConnectionState.Error => Brushes.IndianRed,
        TwitchConnectionState.Connecting or TwitchConnectionState.WaitingForAuthorization => Brushes.Goldenrod,
        _ => Brushes.SlateGray,
    };
    public bool IsWaitingForCode => Service.State == TwitchConnectionState.WaitingForAuthorization && Service.UserCode != null;
    public string UserCode => Service.UserCode ?? "";
    public bool IsConnected => Service.IsConnected;
    public bool IsError => Service.State == TwitchConnectionState.Error;
    public bool ShowConnectButton => !Service.IsConnected && !IsWaitingForCode;
    public string ConnectLabel => Service.State == TwitchConnectionState.Connecting ? "Connecting…" : Service.State == TwitchConnectionState.Error ? "Try again" : "Connect to Twitch";
    public string EventSubText => Service.IsConnected ? Service.EventSubText : "";
    public string PauseLabel => Service.RewardsPaused ? "Resume rewards" : "Pause rewards";
    public string? LoadProblem => Settings.LoadProblem;
    public bool HasLoadProblem => Settings.LoadProblem != null;

    // Behaviour
    public IReadOnlyList<Option<RewardLanguage>> LanguageOptions { get; }
    public IReadOnlyList<Option<SameEffectBehavior>> SameEffectOptions { get; }
    public IReadOnlyList<Option<ConflictBehavior>> ConflictOptions { get; }
    public Option<RewardLanguage> Language
    {
        get => LanguageOptions.First(o => o.Value == Settings.Language);
        set
        {
            if (value is null || value.Value == Settings.Language) return;
            Settings.Language = value.Value;
            SaveSettings(); Changed();
            foreach (var reward in byKey.Values) { reward.RefreshTexts(); if (reward.Enabled) dirty.Add(reward.Key); }
            ScheduleSync();
        }
    }
    public Option<SameEffectBehavior> SameEffect
    {
        get => SameEffectOptions.First(o => o.Value == Settings.SameEffect);
        set { if (value != null && value.Value != Settings.SameEffect) { Settings.SameEffect = value.Value; SaveSettings(); Changed(); RefreshDefaults(); } }
    }
    public Option<ConflictBehavior> Conflict
    {
        get => ConflictOptions.First(o => o.Value == Settings.Conflict);
        set { if (value != null && value.Value != Settings.Conflict) { Settings.Conflict = value.Value; SaveSettings(); Changed(); RefreshDefaults(); } }
    }
    public int MaxWaitMinutes
    {
        get => Settings.MaxWaitMinutes;
        set { value = Math.Clamp(value, 1, 120); if (value != Settings.MaxWaitMinutes) { Settings.MaxWaitMinutes = value; SaveSettings(); } Changed(); }
    }
    public int MaxDurationSeconds
    {
        get => Settings.MaxDurationSeconds;
        set
        {
            value = Math.Clamp(value, 10, 3600);
            if (value != Settings.MaxDurationSeconds)
            {
                Settings.MaxDurationSeconds = value;
                SaveSettings();
                // Durations above the new maximum change the reward descriptions.
                foreach (var reward in byKey.Values.Where(r => r.Effect.IsTimed)) { reward.RefreshTexts(); if (reward.Enabled) dirty.Add(reward.Key); }
                ScheduleSync();
            }
            Changed();
        }
    }
    public bool PauseTimersWhileNotReady
    {
        get => Settings.PauseTimersWhileNotReady;
        set { if (value != Settings.PauseTimersWhileNotReady) { Settings.PauseTimersWhileNotReady = value; SaveSettings(); Changed(); } }
    }
    public bool PauseRewardsWhenClosed
    {
        get => Settings.PauseRewardsWhenClosed;
        set { if (value != Settings.PauseRewardsWhenClosed) { Settings.PauseRewardsWhenClosed = value; SaveSettings(); Changed(); } }
    }

    // Overlay
    public bool OverlayEnabled
    {
        get => Settings.OverlayEnabled;
        set { if (value != Settings.OverlayEnabled) { Settings.OverlayEnabled = value; SaveSettings(); Changed(); _ = RestartOverlayAsync(); } }
    }
    public int OverlayPort
    {
        get => Settings.OverlayPort;
        set
        {
            value = Math.Clamp(value, 1024, 65535);
            if (value != Settings.OverlayPort) { Settings.OverlayPort = value; SaveSettings(); _ = RestartOverlayAsync(); }
            Changed();
        }
    }
    public string OverlayUrl => overlay?.Url ?? $"http://127.0.0.1:{Settings.OverlayPort}/";
    public string OverlayStatus { get => overlayStatus; private set => Set(ref overlayStatus, value); }
    public bool IsOverlayRunning => overlay != null;

    // Rewards
    public IReadOnlyList<RewardGroupVm> Groups { get; }
    public IEnumerable<RewardVm> Rewards => byKey.Values;
    public string Filter
    {
        get => filter;
        set { if (Set(ref filter, value ?? "")) ApplyFilter(); }
    }
    public bool ShowEnabledOnly
    {
        get => showEnabledOnly;
        set { if (Set(ref showEnabledOnly, value)) ApplyFilter(); }
    }
    public bool HasNoMatches => Groups.All(g => !g.HasVisible);
    public int EnabledCount => byKey.Values.Count(r => r.Enabled);
    public string RewardSummary => $"{EnabledCount} of {byKey.Count} rewards on" + (Service.IsConnected ? $" · {Service.RewardsOnTwitch} on Twitch" : " · created on Twitch when you connect");
    public bool OverLimit => EnabledCount > TwitchRewardLimit;
    public string LimitText => $"Twitch allows at most {TwitchRewardLimit} custom rewards per channel, including rewards you made yourself. Switch some off.";
    public string SyncError { get => syncError; private set { if (Set(ref syncError, value)) Changed(nameof(HasSyncError)); } }
    public bool HasSyncError => syncError.Length > 0;

    // Live
    public ObservableCollection<ActiveEffectVm> ActiveEffects { get; } = [];
    public ObservableCollection<PendingEffectVm> PendingEffects { get; } = [];
    public ObservableCollection<EffectEventVm> Events { get; } = [];
    public bool HasActive => ActiveEffects.Count > 0;
    public bool HasPending => PendingEffects.Count > 0;
    public bool HasEvents => Events.Count > 0;
    public string GameText => Engine.IsGameReady ? "The game is ready. Redemptions run right away."
        : shell.IsConnected ? "Waiting for gameplay. Redemptions wait and timers pause during loading, menus and cutscenes."
        : "The trainer is not connected to the game. Redemptions wait until it is.";
    public bool GameReady => Engine.IsGameReady;

    public AsyncCommand ConnectCommand { get; }
    public RelayCommand CancelConnectCommand { get; }
    public AsyncCommand DisconnectCommand { get; }
    public AsyncCommand LogoutCommand { get; }
    public RelayCommand OpenDeveloperConsoleCommand { get; }
    public RelayCommand OpenActivationCommand { get; }
    public RelayCommand CopyCodeCommand { get; }
    public RelayCommand OpenDashboardCommand { get; }
    public AsyncCommand PauseCommand { get; }
    public AsyncCommand ResyncCommand { get; }
    public RelayCommand CopyOverlayCommand { get; }
    public RelayCommand OpenOverlayCommand { get; }
    public AsyncCommand StopAllCommand { get; }
    public RelayCommand ClearFilterCommand { get; }

    /// <summary>Called by the main poll loop (5 times per second).</summary>
    internal async void Tick()
    {
        if (shutDown) return;
        try { await Engine.TickAsync(DateTimeOffset.UtcNow); }
        catch (Exception error) { shell.Log("Twitch effects: " + error.Message); }
        RefreshLive();
    }

    /// <summary>Ends every effect and refunds what waits, for example when the game disconnects or the trainer resets.</summary>
    internal async Task StopAllAsync(string reason)
    {
        // Always ask the engine: it waits for an effect that is starting right now, which the lists do not show yet.
        try { await Engine.StopAllAsync(reason, DateTimeOffset.UtcNow); }
        catch (Exception error) { shell.Log("Twitch effects: " + error.Message); }
        RefreshLive();
    }


    internal void Test(RewardVm reward)
    {
        Engine.Submit(new Redemption("test-" + Guid.NewGuid().ToString("N"), reward.Key, "Test", "", DateTimeOffset.UtcNow, IsTest: true));
        shell.Notify($"Testing {reward.DisplayTitle}. It runs like a redemption, without Twitch. Watch the Live tab.", false);
        Tick();
    }

    internal async Task EndAsync(string key)
    {
        try { await Engine.EndEffectAsync(key, DateTimeOffset.UtcNow); }
        catch (Exception error) { shell.Log("Twitch effects: " + error.Message); }
        RefreshLive();
    }

    internal async Task RefundAsync(string redemptionId)
    {
        await Engine.CancelAsync(redemptionId, DateTimeOffset.UtcNow);
        RefreshLive();
    }

    internal void RewardToggled(RewardVm reward)
    {
        SaveSettings();
        RefreshSummary();
        if (showEnabledOnly) ApplyFilter();
        foreach (var group in Groups) group.Refresh();
        dirty.Add(reward.Key);
        // Switching a reward on or off reaches Twitch right away.
        syncTimer.Stop();
        _ = SyncDirtyAsync();
    }

    internal void RewardEdited(RewardVm reward)
    {
        SaveSettings();
        if (reward.Enabled) { dirty.Add(reward.Key); ScheduleSync(); }
    }

    internal string? ChooseImage(RewardVm reward)
    {
        var picker = new OpenFileDialog
        {
            Title = $"Image for {reward.DisplayTitle}",
            Filter = "Images|*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp",
        };
        if (picker.ShowDialog() != true) return null;
        var info = new FileInfo(picker.FileName);
        if (OverlayServer.ImageType(info.FullName) is null) { shell.Notify("Choose a PNG, JPG, GIF, BMP or WebP image.", true); return null; }
        if (info.Length > OverlayServer.MaxImageBytes) { shell.Notify("The image is larger than 8 MB. Choose a smaller one.", true); return null; }
        if (RewardVm.Decode(info.FullName) is null) { shell.Notify("This image cannot be read. Choose another file.", true); return null; }
        string target = Path.Combine(ImageFolder, reward.Key + info.Extension.ToLowerInvariant());
        if (string.Equals(Path.GetFullPath(info.FullName), Path.GetFullPath(target), StringComparison.OrdinalIgnoreCase)) return target; // Already the reward's image.
        string temporary = Path.Combine(ImageFolder, reward.Key + "." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            // A copy keeps working when the original is moved or deleted. Copy first, so a failure keeps the old image.
            Directory.CreateDirectory(ImageFolder);
            File.Copy(info.FullName, temporary, true);
            foreach (string old in Directory.EnumerateFiles(ImageFolder, reward.Key + ".*").Where(f => !f.EndsWith(".tmp", StringComparison.OrdinalIgnoreCase))) File.Delete(old);
            File.Move(temporary, target, true);
            return target;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); } catch (Exception) { }
            shell.Notify("The image could not be copied: " + error.Message, true);
            return null;
        }
    }

    internal void DeleteImage(string? path)
    {
        try { if (path != null && Path.GetDirectoryName(Path.GetFullPath(path)) == Path.GetFullPath(ImageFolder) && File.Exists(path)) File.Delete(path); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
    }

    private async Task Connect(bool interactive)
    {
        try { await Service.ConnectAsync(interactive); }
        finally { RefreshSummary(); foreach (var reward in byKey.Values) reward.RefreshStatus(); }
    }

    private async Task Logout()
    {
        if (MessageBox.Show("Log out of Twitch? Your rewards stay on Twitch until you connect again and switch them off.", "Twitch",
                MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
        await Service.DisconnectAsync(forgetLogin: true);
    }

    private void ScheduleSync()
    {
        syncTimer.Stop();
        syncTimer.Start();
    }

    private async Task SyncDirtyAsync()
    {
        if (syncing) { ScheduleSync(); return; }
        syncing = true;
        RefreshCommands();
        try
        {
            while (dirty.Count > 0)
            {
                string key = dirty.First();
                dirty.Remove(key);
                await SafeAsync(() => Service.SyncRewardAsync(key));
            }
        }
        finally
        {
            syncing = false;
            RefreshSummary();
            RefreshCommands();
        }
    }

    /// <summary>Runs a Twitch call and shows network problems instead of throwing them at the UI.</summary>
    private async Task SafeAsync(Func<Task> action)
    {
        try
        {
            await action();
            SyncError = "";
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or TwitchApiException or TwitchAuthException)
        {
            SyncError = error is HttpRequestException or TaskCanceledException ? "Twitch is not reachable: " + error.Message : error.Message;
            shell.Log("Twitch: " + SyncError);
        }
    }

    private void OnServiceChanged()
    {
        Changed(nameof(State), nameof(ConnectionTitle), nameof(StatusText), nameof(StatusBrush), nameof(IsWaitingForCode), nameof(UserCode),
            nameof(IsConnected), nameof(IsError), nameof(ShowConnectButton), nameof(ConnectLabel), nameof(EventSubText), nameof(PauseLabel), nameof(HasClientId));
        RefreshSummary();
        RefreshCommands();
        // Statuses depend on the connection ("On Twitch" versus "Created when you connect").
        foreach (var reward in byKey.Values) reward.RefreshStatus();
    }

    private void RefreshCommands()
    {
        ConnectCommand.Refresh(); DisconnectCommand.Refresh(); LogoutCommand.Refresh(); PauseCommand.Refresh(); ResyncCommand.Refresh();
        CopyOverlayCommand.Refresh(); OpenOverlayCommand.Refresh(); StopAllCommand.Refresh();
    }

    private void RefreshSummary() => Changed(nameof(EnabledCount), nameof(RewardSummary), nameof(OverLimit));

    private void RefreshDefaults()
    {
        foreach (var reward in byKey.Values) reward.RefreshDefaults();
    }

    private void ApplyFilter()
    {
        string query = filter.Trim();
        foreach (var reward in byKey.Values)
            reward.IsVisible = (!showEnabledOnly || reward.Enabled) && (query.Length == 0
                || reward.DisplayTitle.Contains(query, StringComparison.OrdinalIgnoreCase)
                || reward.Description.Contains(query, StringComparison.OrdinalIgnoreCase)
                || reward.Effect.Title.Contains(query, StringComparison.OrdinalIgnoreCase)
                || reward.Effect.TitleDe.Contains(query, StringComparison.OrdinalIgnoreCase));
        foreach (var group in Groups) group.Refresh();
        Changed(nameof(HasNoMatches));
    }

    private void RefreshLive()
    {
        var active = Engine.ActiveEffects;
        Sync(ActiveEffects, active, a => a.Key, vm => vm.Key, a => new ActiveEffectVm(this, a), (vm, a) => vm.Update(a));
        Sync(PendingEffects, Engine.PendingEffects, p => p.RedemptionId, vm => vm.RedemptionId, p => new PendingEffectVm(this, p), (vm, p) => vm.Update(p));
        var events = Engine.RecentEvents;
        string newest = events.Count > 0 ? EffectEventVm.KeyOf(events[0]) : "";
        if (newest != lastEventKey)
        {
            lastEventKey = newest;
            Sync(Events, events, EffectEventVm.KeyOf, vm => vm.Key, e => new EffectEventVm(e), (_, _) => { });
        }
        Changed(nameof(HasActive), nameof(HasPending), nameof(HasEvents), nameof(GameText), nameof(GameReady), nameof(LiveTabTitle));
        StopAllCommand.Refresh();
    }

    /// <summary>Updates a bound list in place so rows (and their buttons) survive a refresh.</summary>
    private static void Sync<TSource, TItem>(ObservableCollection<TItem> target, IReadOnlyList<TSource> source, Func<TSource, string> key,
        Func<TItem, string> itemKey, Func<TSource, TItem> create, Action<TItem, TSource> update)
    {
        var keys = source.Select(key).ToHashSet(StringComparer.Ordinal);
        for (int i = target.Count - 1; i >= 0; i--) if (!keys.Contains(itemKey(target[i]))) target.RemoveAt(i);
        for (int i = 0; i < source.Count; i++)
        {
            string k = key(source[i]);
            int index = -1;
            for (int j = i; j < target.Count; j++) if (itemKey(target[j]) == k) { index = j; break; }
            if (index < 0) target.Insert(i, create(source[i]));
            else
            {
                if (index != i) target.Move(index, i);
                update(target[i], source[i]);
            }
        }
    }

    private void StartOverlay()
    {
        try
        {
            if (!Settings.OverlayEnabled) { OverlayStatus = "The overlay is off."; return; }
            var server = new OverlayServer(Settings.OverlayPort, () => Overlay(), key => RewardResolver.ImagePath(key, Settings));
            server.Start();
            overlay = server;
            OverlayStatus = "Running. Add the URL as a Browser Source in OBS (for example 500 × 700).";
        }
        catch (SocketException error)
        {
            OverlayStatus = $"Port {Settings.OverlayPort} is in use ({error.Message}). Choose another port.";
        }
        finally
        {
            Changed(nameof(OverlayUrl), nameof(IsOverlayRunning));
            CopyOverlayCommand?.Refresh(); OpenOverlayCommand?.Refresh();
        }
    }

    /// <summary>The overlay reads from a server thread; the engine lives on the UI thread.</summary>
    private OverlayState Overlay()
    {
        try { return Application.Current.Dispatcher.Invoke(() => RewardResolver.Overlay(Engine, Settings), DispatcherPriority.Background, CancellationToken.None, TimeSpan.FromSeconds(2)); }
        catch (Exception) { return new OverlayState([], [], []); }
    }

    private async Task RestartOverlayAsync()
    {
        if (overlay is { } running) { overlay = null; await running.DisposeAsync(); }
        StartOverlay();
    }

    private void SaveSettings()
    {
        try { Settings.Save(settingsPath); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { shell.Log("Twitch: settings could not be saved: " + error.Message); }
    }

    private void CopyText(string text, string confirmation)
    {
        try { Clipboard.SetText(text); shell.Notify(confirmation, false); }
        catch (System.Runtime.InteropServices.ExternalException) { shell.Notify("The clipboard is busy. Try again.", true); }
    }

    internal static void OpenUrl(string url)
    {
        try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); }
        catch (Exception) { /* No browser registered; the URL is shown in the UI. */ }
    }

    /// <summary>Called when the trainer closes: ends effects, pauses rewards (if enabled) and stops the overlay.</summary>
    internal Task ShutdownAsync() => shutdown ??= ShutdownCoreAsync();

    private async Task ShutdownCoreAsync()
    {
        shutDown = true;
        syncTimer.Stop();
        // Stop receiving first, so nothing arrives after the queue was settled.
        try { await Service.StopListeningAsync().WaitAsync(TimeSpan.FromSeconds(12)); } catch (Exception) { }
        try { await Engine.StopAllAsync("The trainer was closed", DateTimeOffset.UtcNow).WaitAsync(TimeSpan.FromSeconds(10)); } catch (Exception) { }
        try { await Service.FlushAsync().WaitAsync(TimeSpan.FromSeconds(6)); } catch (Exception) { }
        if (overlay is { } running) { overlay = null; try { await running.DisposeAsync(); } catch (Exception) { } }
    }

    public async ValueTask DisposeAsync()
    {
        await ShutdownAsync();
        await Service.DisposeAsync();
        http.Dispose();
    }
}

public sealed class RewardGroupVm(RewardCategory category, IReadOnlyList<RewardVm> rewards) : Observable
{
    public RewardCategory Category { get; } = category;
    public IReadOnlyList<RewardVm> Rewards { get; } = rewards;
    public string Title => Category switch
    {
        RewardCategory.Help => "Help Sora",
        RewardCategory.Harm => "Hurt Sora",
        RewardCategory.Funny => "Funny",
        _ => "Annoying",
    };
    public string Description => Category switch
    {
        RewardCategory.Help => "Healing, items, buffs and Drive Forms.",
        RewardCategory.Harm => "Damage, theft, debuffs and room reloads.",
        RewardCategory.Funny => "Silly camera, speed and movement tricks.",
        _ => "Short interruptions that get in the way.",
    };
    public Brush Brush { get; } = RewardVm.BrushOf(EffectDefinition.ColorOf(category));
    public bool HasVisible => Rewards.Any(r => r.IsVisible);
    public string Count => $"{Rewards.Count(r => r.Enabled)} of {Rewards.Count} on";
    public void Refresh() => Changed(nameof(HasVisible), nameof(Count));
}

/// <summary>One reward: on/off, Twitch fields, timing, behaviour and an optional image.</summary>
public sealed class RewardVm : Observable
{
    private readonly TwitchVm owner;
    private bool isExpanded, isVisible = true;
    private ImageSource? image;

    public RewardVm(TwitchVm owner, EffectDefinition effect)
    {
        this.owner = owner;
        Effect = effect;
        Brush = BrushOf(effect.Color);
        TestCommand = new RelayCommand(() => owner.Test(this));
        ChooseImageCommand = new RelayCommand(ChooseImage);
        ClearImageCommand = new RelayCommand(ClearImage, () => HasImage);
        ShowImageCommand = new RelayCommand(() => { if (Reward.ImagePath is { } path && File.Exists(path)) Process.Start("explorer.exe", $"/select,\"{path}\""); }, () => HasImage);
        ResetCommand = new RelayCommand(Reset);
        ToggleCommand = new RelayCommand(() => IsExpanded = !IsExpanded);
        LoadImage();
    }

    public EffectDefinition Effect { get; }
    public string Key => Effect.Key;
    private RewardSettings Reward => owner.Settings.For(Effect.Key);
    public Brush Brush { get; }
    public string Glyph => Effect.Category switch
    {
        RewardCategory.Help => "",
        RewardCategory.Harm => "",
        RewardCategory.Funny => "",
        _ => "",
    };

    public bool Enabled
    {
        get => Reward.Enabled;
        set { if (value == Reward.Enabled) return; Reward.Enabled = value; Changed(); RefreshStatus(); owner.RewardToggled(this); }
    }
    public bool IsExpanded { get => isExpanded; set => Set(ref isExpanded, value); }
    public bool IsVisible { get => isVisible; set => Set(ref isVisible, value); }

    public string DisplayTitle => RewardResolver.Title(Effect, owner.Settings);
    public string DefaultTitle => Effect.TitleFor(owner.Settings.Language);
    public string Description => RewardResolver.Prompt(Effect, owner.Settings);
    public string DefaultPrompt => Effect.PromptFor(owner.Settings.Language);
    public string Info
    {
        get
        {
            var parts = new List<string> { $"{Cost:N0} points" };
            if (Effect.IsTimed) parts.Add($"{RewardResolver.Duration(Effect, owner.Settings)} s");
            if (Effect.Amount > 0) parts.Add($"{RewardResolver.Amount(Effect, owner.Settings):N0} {Effect.AmountLabel}");
            if (Reward.CooldownSeconds > 0) parts.Add($"{Reward.CooldownSeconds} s cooldown");
            return string.Join(" · ", parts);
        }
    }

    public string Title
    {
        get => Reward.Title ?? "";
        set { string? clean = string.IsNullOrWhiteSpace(value) ? null : value.Trim(); if (clean == Reward.Title) return; Reward.Title = clean; Edited(nameof(Title), nameof(DisplayTitle)); }
    }
    public string Prompt
    {
        get => Reward.Prompt ?? "";
        set { string? clean = string.IsNullOrWhiteSpace(value) ? null : value.Trim(); if (clean == Reward.Prompt) return; Reward.Prompt = clean; Edited(nameof(Prompt), nameof(Description)); }
    }
    public int Cost
    {
        get => Reward.Cost ?? Effect.Cost;
        set { value = Math.Clamp(value, 1, 10_000_000); int? stored = value == Effect.Cost ? null : value; if (stored == Reward.Cost) { Changed(); return; } Reward.Cost = stored; Edited(nameof(Cost), nameof(Info)); }
    }
    public bool IsTimed => Effect.IsTimed;
    public int Duration
    {
        get => RewardResolver.Duration(Effect, owner.Settings);
        set
        {
            value = Math.Clamp(value, 1, owner.Settings.MaxDurationSeconds);
            int? stored = value == Effect.DurationSeconds ? null : value;
            if (stored == Reward.DurationSeconds) { Changed(); return; }
            Reward.DurationSeconds = stored;
            Edited(nameof(Duration), nameof(Info), nameof(Description));
        }
    }
    public bool HasAmount => Effect.Amount > 0;
    public string AmountLabel => $"Amount ({Effect.AmountLabel}, {Effect.MinAmount:N0}–{Effect.MaxAmount:N0})";
    public int Amount
    {
        get => RewardResolver.Amount(Effect, owner.Settings);
        set
        {
            value = Math.Clamp(value, Effect.MinAmount, Effect.MaxAmount);
            int? stored = value == Effect.Amount ? null : value;
            if (stored == Reward.Amount) { Changed(); return; }
            Reward.Amount = stored;
            Edited(nameof(Amount), nameof(Info), nameof(Description));
        }
    }
    public int Cooldown
    {
        get => Reward.CooldownSeconds;
        set { value = Math.Clamp(value, 0, RewardSpec.MaxCooldownSeconds); if (value == Reward.CooldownSeconds) { Changed(); return; } Reward.CooldownSeconds = value; Edited(nameof(Cooldown), nameof(Info)); }
    }
    public int MaxPerStream
    {
        get => Reward.MaxPerStream;
        set { value = Math.Clamp(value, 0, 1_000_000); if (value == Reward.MaxPerStream) { Changed(); return; } Reward.MaxPerStream = value; Edited(nameof(MaxPerStream)); }
    }
    public int MaxPerUserPerStream
    {
        get => Reward.MaxPerUserPerStream;
        set { value = Math.Clamp(value, 0, 1_000_000); if (value == Reward.MaxPerUserPerStream) { Changed(); return; } Reward.MaxPerUserPerStream = value; Edited(nameof(MaxPerUserPerStream)); }
    }

    // Per-reward behaviour; null follows the setting on the Setup tab.
    public bool HasGroup => Effect.Group != null;
    public IReadOnlyList<Option<SameEffectBehavior?>> SameEffectOptions =>
        [new($"Default ({owner.SameEffect.Label.ToLowerInvariant()})", null), .. owner.SameEffectOptions.Select(o => new Option<SameEffectBehavior?>(o.Label, o.Value))];
    public IReadOnlyList<Option<ConflictBehavior?>> ConflictOptions =>
        [new($"Default ({owner.Conflict.Label.ToLowerInvariant()})", null), .. owner.ConflictOptions.Select(o => new Option<ConflictBehavior?>(o.Label, o.Value))];
    public Option<SameEffectBehavior?> SameEffect
    {
        get => SameEffectOptions.First(o => o.Value == Reward.SameEffect);
        set { if (value != null && value.Value != Reward.SameEffect) { Reward.SameEffect = value.Value; owner.RewardEdited(this); Changed(); } }
    }
    public Option<ConflictBehavior?> Conflict
    {
        get => ConflictOptions.First(o => o.Value == Reward.Conflict);
        set { if (value != null && value.Value != Reward.Conflict) { Reward.Conflict = value.Value; owner.RewardEdited(this); Changed(); } }
    }
    public string ConflictHint => Effect.Group switch
    {
        "form" => "Another Drive Form is running:",
        _ => "A similar effect is running:",
    };

    // Image
    public ImageSource? Image { get => image; private set { if (Set(ref image, value)) Changed(nameof(HasImage), nameof(HasNoImage)); } }
    public bool HasImage => image != null;
    public bool HasNoImage => image == null;

    // Twitch status
    public string Status => owner.Service.RewardStatus(Effect.Key);
    public bool StatusIsError => Status.StartsWith("Error", StringComparison.Ordinal);
    public bool StatusIsLive => Status.StartsWith("On Twitch", StringComparison.Ordinal);
    /// <summary>Also shown for a switched-off reward that still exists on Twitch (for example a failed delete).</summary>
    public bool ShowStatus => Enabled || StatusIsError || Reward.TwitchRewardId != null;

    public RelayCommand TestCommand { get; }
    public RelayCommand ChooseImageCommand { get; }
    public RelayCommand ClearImageCommand { get; }
    public RelayCommand ShowImageCommand { get; }
    public RelayCommand ResetCommand { get; }
    public RelayCommand ToggleCommand { get; }

    public void RefreshStatus() => Changed(nameof(Status), nameof(StatusIsError), nameof(StatusIsLive), nameof(ShowStatus), nameof(Enabled));
    public void RefreshTexts() => Changed(nameof(DisplayTitle), nameof(DefaultTitle), nameof(Description), nameof(DefaultPrompt), nameof(Duration), nameof(Info));
    public void RefreshDefaults() => Changed(nameof(SameEffectOptions), nameof(ConflictOptions), nameof(SameEffect), nameof(Conflict));

    private void Edited(params string[] names)
    {
        Changed(names);
        owner.RewardEdited(this);
    }

    private void Reset()
    {
        var reward = Reward;
        reward.Title = null; reward.Prompt = null; reward.Cost = null; reward.DurationSeconds = null; reward.Amount = null;
        reward.CooldownSeconds = 0; reward.MaxPerStream = 0; reward.MaxPerUserPerStream = 0; reward.SameEffect = null; reward.Conflict = null;
        Changed(nameof(Title), nameof(Prompt), nameof(Cost), nameof(Duration), nameof(Amount), nameof(Cooldown), nameof(MaxPerStream), nameof(MaxPerUserPerStream),
            nameof(SameEffect), nameof(Conflict), nameof(DisplayTitle), nameof(Description), nameof(Info));
        owner.RewardEdited(this);
    }

    private void ChooseImage()
    {
        if (owner.ChooseImage(this) is not { } path) return;
        Reward.ImagePath = path;
        LoadImage();
        owner.RewardEdited(this);
    }

    private void ClearImage()
    {
        owner.DeleteImage(Reward.ImagePath);
        Reward.ImagePath = null;
        LoadImage();
        owner.RewardEdited(this);
    }

    private void LoadImage()
    {
        string? path = RewardResolver.ImagePath(Effect.Key, owner.Settings);
        Image = path is null ? null : Decode(path);
        RefreshImageCommands();
    }

    /// <summary>Loads an image into memory (the file stays free to replace or delete); null when it cannot be decoded.</summary>
    internal static ImageSource? Decode(string path)
    {
        try
        {
            var bitmap = new BitmapImage();
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.CreateOptions = BitmapCreateOptions.IgnoreImageCache;
            bitmap.DecodePixelWidth = 112;
            bitmap.UriSource = new Uri(path);
            bitmap.EndInit();
            bitmap.Freeze();
            return bitmap;
        }
        catch (Exception) { return null; } // A damaged file must never stop the trainer from starting.
    }

    private void RefreshImageCommands() { ClearImageCommand?.Refresh(); ShowImageCommand?.Refresh(); }

    internal static Brush BrushOf(string color)
    {
        var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(color));
        brush.Freeze();
        return brush;
    }
}

public sealed class ActiveEffectVm : Observable
{
    private readonly TwitchVm owner;
    private ActiveEffectInfo info;

    public ActiveEffectVm(TwitchVm owner, ActiveEffectInfo info)
    {
        this.owner = owner; this.info = info;
        var effect = EffectCatalog.Find(info.Key);
        Brush = RewardVm.BrushOf(effect?.Color ?? "#5B9BFF");
        Image = owner.Rewards.FirstOrDefault(r => r.Key == info.Key)?.Image;
        IsTimed = effect?.IsTimed ?? false;
        EndCommand = new AsyncCommand(() => owner.EndAsync(info.Key));
    }

    public string Key => info.Key;
    public string Title => info.Title;
    public string Viewers => info.Viewers;
    public string? Detail => info.Detail;
    public bool HasDetail => !string.IsNullOrEmpty(info.Detail);
    public bool IsTimed { get; }
    public bool Starting => !info.Established;
    public double Fraction => info.DurationSeconds > 0 ? Math.Clamp(info.RemainingSeconds / info.DurationSeconds, 0, 1) : 0;
    public string RemainingText => Starting ? "starting…" : IsTimed ? $"{Math.Ceiling(info.RemainingSeconds):0} s left" : "";
    public Brush Brush { get; }
    public ImageSource? Image { get; }
    public bool HasImage => Image != null;
    public bool HasNoImage => Image == null;
    public AsyncCommand EndCommand { get; }

    public void Update(ActiveEffectInfo next)
    {
        info = next;
        Changed(nameof(Title), nameof(Viewers), nameof(Detail), nameof(HasDetail), nameof(Starting), nameof(Fraction), nameof(RemainingText));
    }
}

public sealed class PendingEffectVm : Observable
{
    private PendingEffectInfo info;

    public PendingEffectVm(TwitchVm owner, PendingEffectInfo info)
    {
        this.info = info;
        Brush = RewardVm.BrushOf(EffectCatalog.Find(info.Key)?.Color ?? "#5B9BFF");
        RefundCommand = new AsyncCommand(() => owner.RefundAsync(info.RedemptionId));
    }

    public string RedemptionId => info.RedemptionId;
    public string Title => info.Title;
    public string Viewer => info.Viewer;
    public string Status => info.Status;
    public string Waited => info.WaitedSeconds < 60 ? $"{info.WaitedSeconds:0} s" : $"{info.WaitedSeconds / 60:0} min";
    public Brush Brush { get; }
    public AsyncCommand RefundCommand { get; }

    public void Update(PendingEffectInfo next)
    {
        info = next;
        Changed(nameof(Status), nameof(Waited));
    }
}

public sealed class EffectEventVm(EffectEvent e)
{
    public static string KeyOf(EffectEvent e) => $"{e.Time.UtcTicks}|{e.Kind}|{e.Key}|{e.Viewer}|{e.Text}";
    public string Key { get; } = KeyOf(e);
    public string Time { get; } = e.Time.ToLocalTime().ToString("HH:mm:ss");
    public string Text { get; } = e.Text;
    public string Glyph { get; } = e.Kind switch
    {
        EffectEventKind.Redeemed => "",
        EffectEventKind.Started or EffectEventKind.Done => "",
        EffectEventKind.Extended => "",
        EffectEventKind.Ended => "",
        EffectEventKind.Refunded => "",
        _ => "",
    };
    public Brush Brush { get; } = e.Kind switch
    {
        EffectEventKind.Refunded or EffectEventKind.Failed => Brushes.IndianRed,
        EffectEventKind.Started or EffectEventKind.Done or EffectEventKind.Extended => Brushes.MediumSeaGreen,
        _ => Brushes.SlateGray,
    };
}
