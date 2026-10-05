using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using KH2Trainer.Core;
using Microsoft.Win32;

namespace KH2Trainer;

public abstract class Observable : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;
    protected void Changed([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    protected bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null) { if (EqualityComparer<T>.Default.Equals(field, value)) return false; field = value; Changed(name); return true; }
}
public sealed class AsyncCommand(Func<Task> execute, Func<bool>? canExecute = null) : ICommand
{
    private bool busy;
    public event EventHandler? CanExecuteChanged;
    public bool CanExecute(object? parameter) => !busy && (canExecute?.Invoke() ?? true);
    public async void Execute(object? parameter)
    {
        if (!CanExecute(parameter)) return;
        busy = true; Refresh();
        try { await execute(); } catch (Exception e) { MessageBox.Show(e.Message, "KH2 Trainer", MessageBoxButton.OK, MessageBoxImage.Information); }
        finally { busy = false; Refresh(); }
    }
    public void Refresh() => CanExecuteChanged?.Invoke(this, EventArgs.Empty);
}
public sealed record ProcessChoice(GameProcess Process) { public string Label => $"{Process.Name} · PID {Process.Pid}"; }

public sealed class ArgumentVm : Observable
{
    public FeatureArgument Definition { get; }
    public string Name => Definition.Name;
    public IReadOnlyList<FeatureChoice> Choices { get; }
    public bool IsChoice => Choices.Count > 0;
    public bool IsNumber => !IsChoice;
    private string valueText;
    public string ValueText { get => valueText; set => Set(ref valueText, value); }
    private FeatureChoice? choice;
    public FeatureChoice? SelectedChoice { get => choice; set => Set(ref choice, value); }
    public ArgumentVm(FeatureArgument definition, IReadOnlyDictionary<string, IReadOnlyList<FeatureChoice>> catalogs)
    {
        Definition = definition; valueText = definition.DefaultValue.ToString(CultureInfo.InvariantCulture);
        Choices = (definition.Choices.Count > 0 ? definition.Choices : catalogs.GetValueOrDefault(definition.Catalog) ?? [])
            .Where(c => c.Value >= definition.Minimum && c.Value <= definition.Maximum).ToArray();
        choice = Choices.FirstOrDefault(c => c.Value == definition.DefaultValue) ?? Choices.FirstOrDefault();
    }
    public double Read()
    {
        double value = IsChoice ? SelectedChoice?.Value ?? throw new ArgumentException($"Choose {Name}.") :
            double.TryParse(ValueText, NumberStyles.Float, CultureInfo.InvariantCulture, out double parsed) ? parsed : throw new ArgumentException($"Enter a number for {Name}.");
        if (!double.IsFinite(value) || value < Definition.Minimum || value > Definition.Maximum) throw new ArgumentException($"{Name} must be between {Definition.Minimum} and {Definition.Maximum}.");
        return value;
    }
}

public sealed class FeatureVm : Observable
{
    private readonly MainViewModel owner;
    public FeatureDefinition Definition { get; }
    public string Name => Definition.Name;
    public string Description => Definition.Description;
    public bool IsNumber => Definition.Kind == FeatureKind.Number;
    public bool IsToggle => Definition.Kind == FeatureKind.Toggle;
    public bool IsChoice => Definition.Kind == FeatureKind.Choice;
    public bool IsEditable => Definition.Kind != FeatureKind.ReadOnly;
    public string ApplyLabel => Definition.Id switch
    {
        "drive.trigger" => "Trigger Drive Form",
        "drive.revert" => "Revert",
        "drive.cancel" => "Cancel pending switch",
        "audio.reset" => "Apply game audio settings",
        _ => Definition.Kind == FeatureKind.Action ? "Run action" : "Apply"
    };
    public string RangeText => $"{Definition.Minimum:g}–{Definition.Maximum:g} {Definition.Unit}";
    public IReadOnlyList<FeatureChoice> Choices => Definition.Choices;
    public IReadOnlyList<ArgumentVm> Arguments { get; }
    private string valueText, liveValue = "—", availability = "Connect to inspect this feature.";
    public string ValueText { get => valueText; set { if (Set(ref valueText, value)) dirty = true; } }
    public string LiveValue { get => liveValue; private set => Set(ref liveValue, value); }
    public string Availability { get => availability; private set => Set(ref availability, value); }
    private bool toggleValue, available, dirty;
    public bool ToggleValue { get => toggleValue; set { if (Set(ref toggleValue, value)) dirty = true; } }
    private FeatureChoice? choice;
    public FeatureChoice? SelectedChoice { get => choice; set { if (Set(ref choice, value)) dirty = true; } }
    public AsyncCommand ApplyCommand { get; }
    public FeatureVm(FeatureDefinition definition, MainViewModel owner, IReadOnlyDictionary<string, IReadOnlyList<FeatureChoice>> catalogs)
    {
        Definition = definition; this.owner = owner; valueText = definition.DefaultValue.ToString(CultureInfo.InvariantCulture);
        choice = Choices.FirstOrDefault(c => c.Value == definition.DefaultValue) ?? Choices.FirstOrDefault();
        Arguments = definition.Arguments.Select(a => new ArgumentVm(a, catalogs)).ToArray();
        ApplyCommand = new AsyncCommand(Apply, () => available && !owner.Busy);
    }
    public double ReadValue()
    {
        double value = IsToggle ? ToggleValue ? 1 : 0 : IsChoice ? SelectedChoice?.Value ?? throw new ArgumentException($"Choose a value for {Name}.") :
            double.TryParse(ValueText, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) ? number : throw new ArgumentException($"Enter a number for {Name}.");
        if (!Definition.IsValidValue(value)) throw new ArgumentException($"{Name}: use a value between {Definition.Minimum} and {Definition.Maximum}.");
        return value;
    }
    public void SetInput(double value)
    {
        ValueText = value.ToString(CultureInfo.InvariantCulture); ToggleValue = value != 0;
        SelectedChoice = Choices.FirstOrDefault(c => c.Value == value); dirty = true;
    }
    public void Update(TrainerSnapshot snapshot)
    {
        available = snapshot.Connected && snapshot.Status >= 1 && snapshot.Supports(Definition.CapabilitySlot) && (!Definition.RequiresScene || snapshot.SceneReady);
        LiveValue = snapshot.HasValue(Definition.ValueSlot) ? FormatLiveValue(snapshot.Values[Definition.ValueSlot]) : "—";
        if (!dirty && snapshot.HasValue(Definition.ValueSlot))
        {
            double current = snapshot.Values[Definition.ValueSlot];
            valueText = current.ToString("0.###", CultureInfo.InvariantCulture); toggleValue = current != 0; choice = Choices.FirstOrDefault(c => c.Value == current);
            Changed(nameof(ValueText)); Changed(nameof(ToggleValue)); Changed(nameof(SelectedChoice));
        }
        Availability = !snapshot.Connected ? "Connect to the game to use this feature." : !snapshot.Supports(Definition.CapabilitySlot) ? "This bridge does not provide this feature." : Definition.RequiresScene && !snapshot.SceneReady ? "Load a playable scene first." : Definition.ChangesProgression ? "Changes the loaded game state. Saving can make it permanent." : Definition.RestoreBehavior;
        ApplyCommand.Refresh();
    }
    private string FormatLiveValue(double value)
    {
        if (Definition.CapabilitySlot == 124)
            return value switch { 0 => "None", 1 => "Valor", 2 => "Wisdom", 3 => "Limit", 4 => "Master", 5 => "Final", 6 => "Antiform", _ => "Unknown" };
        if (Definition.CapabilitySlot == 125)
            return value switch { 0 => "Idle", 1 => "Reverting to switch", 2 => "Transforming", 3 => "Reverting", _ => "Unknown" };
        if (Definition.CapabilitySlot == 127)
            return value switch { 0 => "—", 1 => "Queued", 2 => "Completed", 3 => "Cancelled", 4 => "Scene changed", 5 => "Disconnected", 6 => "Timed out", 7 => "Conditions changed", 8 => "Transition not started", _ => "Unknown" };
        if (Definition.CapabilitySlot is 159 or 408)
            return value == 1 ? "Available" : "Unavailable or busy";
        if (Definition.CapabilitySlot == 414)
            return value switch { 1 => "Base", 2 => "Point", 3 => "Line", _ => "Unknown" };
        if (Definition.CapabilitySlot == 426)
            return value switch { 1 => "Edit", 4 => "Preview", _ => "Unknown" };
        if (Definition.CapabilitySlot == 435)
            return value switch { 0 => "Windowed", 1 => "Fullscreen", 2 => "Maximized", _ => "Unknown" };
        if (Definition.CapabilitySlot == 436)
            return value == 1 ? "Pending" : "Idle";
        if (Definition.CapabilitySlot == 449)
            return value switch { 0 => "Native", 1 => "Fixed", 2 => "Maximum", _ => "Unknown" };
        if (Definition.CapabilitySlot == 455)
            return value switch { 0 => "Not installed", 1 => "Resident", 2 => "Restart required", _ => "Unknown" };
        if (Definition.CapabilitySlot == 169)
            return value switch { 0 => "Prototype", 1 => "RAW", _ => "Unknown" };
        if (Definition.CapabilitySlot == 170)
            return value switch { 0 => "Off", 1 => "Active", 2 => "Disabled", 3 => "Changed by game script", 4 => "Changed externally", 5 => "Player or scene changed", 6 => "Disconnected", 7 => "Game or mod took control", 8 => "Animation data unavailable", 9 => "Animation override unavailable", _ => "Unknown" };
        if (Definition.CapabilitySlot is 179 or 183 or 229 or 246)
            return value == 1 ? "Yes" : "No";
        if (Definition.CapabilitySlot == 180)
            return value == 1 ? "Active" : "Inactive";
        if (Definition.CapabilitySlot == 211)
            return value switch { 0 => "Count up", 1 => "Count down", _ => "Unknown" };
        if (Definition.CapabilitySlot == 212)
            return value switch { 0 => "Stopped", 1 => "Armed", 2 => "Running", _ => "Unknown" };
        if (Definition.CapabilitySlot == 241)
            return value switch { 0 => "Follow", 1 => "Script", 2 => "Minigame", _ => "Unknown" };
        if (Definition.CapabilitySlot == 245)
            return value switch { 0 => "None", 1 => "Recenter queued", 2 => "Snap queued", _ => "Unknown" };
        if (Definition.Id == "player.form.id")
            return value switch { 0 => "Base Sora", 1 => "Valor", 2 => "Wisdom", 3 => "Limit", 4 => "Master", 5 => "Final", 6 => "Antiform", _ => value.ToString("0.###", CultureInfo.InvariantCulture) };
        return value.ToString("0.###", CultureInfo.InvariantCulture) + (Definition.Unit.Length > 0 ? " " + Definition.Unit : "");
    }
    private async Task Apply()
    {
        var arguments = Arguments.Count > 0 ? Arguments.Select(a => a.Read()).ToArray() : Definition.Kind == FeatureKind.Action ? Array.Empty<double>() : [ReadValue()];
        await owner.Execute(Definition.CommandId, arguments, Name); dirty = false;
    }
}

public sealed class MainViewModel : Observable, IDisposable
{
    private readonly GameSession session = new();
    private readonly DispatcherTimer timer;
    private readonly string userFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "KH2Trainer");
    private readonly ProfileStore profiles;
    private readonly BackupStore backups;
    private readonly List<FeatureVm> features = [];
    private readonly IReadOnlyList<FeatureDefinition> catalog;
    private TrainerSnapshot snapshot = TrainerSnapshot.Disconnected;
    private TrainerProfile? loadedProfile;
    private int pollCount;
    private double? lastShortcutSequence;
    private bool busy;
    public bool Busy { get => busy; private set { if (Set(ref busy, value)) RefreshCommands(); } }
    public string BuildLabel => "Development build · 0.11";
    public AssetExplorerViewModel Assets { get; }
    public RuntimeDiagnosticsViewModel Diagnostics { get; }
    public ObservableCollection<string> Categories { get; } = ["Overview"];
    public ObservableCollection<FeatureVm> VisibleFeatures { get; } = [];
    public ObservableCollection<ProcessChoice> Processes { get; } = [];
    public ObservableCollection<string> RecentActivity { get; } = [];
    private readonly List<string> activity = [];
    private ProcessChoice? selectedProcess;
    public ProcessChoice? SelectedProcess { get => selectedProcess; set { Set(ref selectedProcess, value); ConnectCommand.Refresh(); } }
    private string category = "Overview", search = "", statusMessage = "Start the game, then connect to begin.";
    public string SelectedCategory { get => category; set { if (Set(ref category, value)) { Changed(nameof(PageSubtitle)); Changed(nameof(IsOverview)); Changed(nameof(IsFeaturePage)); Changed(nameof(IsProfiles)); Changed(nameof(IsSaves)); Changed(nameof(IsResearch)); Changed(nameof(IsAssets)); Changed(nameof(IsDiagnostics)); Filter(); } } }
    public string Search { get => search; set { if (Set(ref search, value)) Filter(); } }
    public bool IsOverview => SelectedCategory == "Overview";
    public bool IsProfiles => SelectedCategory == "Profiles";
    public bool IsSaves => SelectedCategory == "Save Manager";
    public bool IsResearch => SelectedCategory == "Research";
    public bool IsAssets => SelectedCategory == "Asset Explorer";
    public bool IsDiagnostics => SelectedCategory == "Game Messages";
    public bool IsFeaturePage => !IsOverview && !IsProfiles && !IsSaves && !IsResearch && !IsAssets && !IsDiagnostics;
    public string PageSubtitle => IsOverview ? "Live inspection, training tools and control over your current session." : IsProfiles ? "Keep useful combinations of trainer settings." : IsSaves ? "Verified copies of your original save files." : IsResearch ? "The findings behind the trainer." : IsAssets ? "Explore game files and extract selected assets." : IsDiagnostics ? "Look up the game's original messages and what their buttons do." : "Inspect values and apply the changes you choose.";
    public string StatusMessage { get => statusMessage; private set => Set(ref statusMessage, value); }
    public Brush StatusBrush => snapshot.Connected ? snapshot.ErrorCode != 0 ? Brushes.Orange : Brushes.MediumAquamarine : Brushes.SlateGray;
    public string ConnectionDetail => snapshot.Connected ? $"PID {session.ProcessId} · {snapshot.FrameCount:N0} frames" : "Disconnected";
    public string ConnectLabel => session.Connected ? "Disconnect" : Busy ? "Connecting…" : "Connect";
    public string HealthText => ValuePair(0, 1);
    public string MagicText => ValuePair(2, 3);
    public string DriveText => ValuePair(7, 8);
    public string SessionSummary => $"{catalog.Count} features in the current catalog. " + (snapshot.Connected ? snapshot.SceneReady ? "A playable scene is ready." : "Waiting for a playable scene." : "The executable and supported mod loader are checked before the bridge is loaded.");
    public string FeatureCountText => $"{VisibleFeatures.Count} features";
    private string profileName = "My training setup", profileSummary = "No profile loaded.";
    public string ProfileName { get => profileName; set => Set(ref profileName, value); }
    public string ProfileSummary { get => profileSummary; private set => Set(ref profileSummary, value); }
    private string saveFolder = "", backupSummary = "Backups are stored separately from the game and include a SHA-256 manifest.";
    public string SaveFolder { get => saveFolder; set => Set(ref saveFolder, value); }
    public string BackupSummary { get => backupSummary; private set => Set(ref backupSummary, value); }
    public string ResearchSummary => $"Current inventory: 36,451 recognized native functions, 445 managed entries (439 bodies) and 47 shaders.\nTrainer catalog: {catalog.Count} controls and readouts, plus the offline Asset Explorer and Game Messages reference. Feature evidence and the analysis report describe the confirmed behavior and remaining questions. Automatic export does not establish complete behavioral understanding.\n\nSupported executable SHA-256:\n{TargetGame.Sha256}";
    public AsyncCommand ConnectCommand { get; }
    public AsyncCommand StartGameCommand { get; }
    public AsyncCommand ShowDebugCommand { get; }
    public AsyncCommand DisableEffectsCommand { get; }
    public AsyncCommand OpenResearchCommand { get; }
    public AsyncCommand SaveProfileCommand { get; }
    public AsyncCommand LoadProfileCommand { get; }
    public AsyncCommand ApplyProfileCommand { get; }
    public AsyncCommand ChooseSaveFolderCommand { get; }
    public AsyncCommand BackupCommand { get; }
    public AsyncCommand RestoreBackupCommand { get; }
    public AsyncCommand OpenBackupsCommand { get; }
    public AsyncCommand OpenAnalysisCommand { get; }
    public AsyncCommand OpenGuideCommand { get; }
    public AsyncCommand ExportEvidenceCommand { get; }
    public AsyncCommand ExportLogCommand { get; }
    public MainViewModel()
    {
        profiles = new ProfileStore(Path.Combine(userFolder, "Profiles")); backups = new BackupStore(Path.Combine(userFolder, "Backups"));
        using (var stream = DataResources.Open("features.json")) catalog = FeatureCatalog.Load(stream);
        var lookups = LoadLookups();
        features.AddRange(catalog.Select(f => new FeatureVm(f, this, lookups)));
        foreach (string name in catalog.Select(f => f.Category).Distinct()) Categories.Add(name);
        Categories.Add("Asset Explorer"); Categories.Add("Game Messages"); Categories.Add("Profiles"); Categories.Add("Save Manager"); Categories.Add("Research");
        Assets = new AssetExplorerViewModel(Log);
        Diagnostics = new RuntimeDiagnosticsViewModel();
        ConnectCommand = new AsyncCommand(Connect, () => !Busy && (session.Connected || SelectedProcess != null));
        StartGameCommand = new AsyncCommand(StartGame, () => !Busy);
        ShowDebugCommand = new AsyncCommand(() => Execute(1112, [], "Show developer tools"), () => session.Connected && !Busy);
        DisableEffectsCommand = new AsyncCommand(() => Execute(1114, [], "Disable all effects"), () => session.Connected && !Busy);
        OpenResearchCommand = new AsyncCommand(() => { SelectedCategory = "Research"; return Task.CompletedTask; });
        SaveProfileCommand = new AsyncCommand(SaveProfile, () => !Busy);
        LoadProfileCommand = new AsyncCommand(LoadProfile, () => !Busy);
        ApplyProfileCommand = new AsyncCommand(ApplyProfile, () => session.Connected && loadedProfile != null && !Busy);
        ChooseSaveFolderCommand = new AsyncCommand(() => { var d = new OpenFolderDialog { Title = "Choose the KH2 save folder" }; if (d.ShowDialog() == true) SaveFolder = d.FolderName; return Task.CompletedTask; });
        BackupCommand = new AsyncCommand(Backup, () => !Busy);
        RestoreBackupCommand = new AsyncCommand(RestoreBackup, () => !Busy);
        OpenBackupsCommand = new AsyncCommand(() => { Directory.CreateDirectory(backups.Folder); OpenPath(backups.Folder); return Task.CompletedTask; });
        OpenAnalysisCommand = new AsyncCommand(OpenAnalysis);
        OpenGuideCommand = new AsyncCommand(() => { OpenPath(Path.Combine(AppContext.BaseDirectory, "UserGuide.html")); return Task.CompletedTask; });
        ExportEvidenceCommand = new AsyncCommand(ExportEvidence);
        ExportLogCommand = new AsyncCommand(ExportLog);
        timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(200) }; timer.Tick += (_, _) => Poll(); timer.Start();
        RefreshProcesses(); Log("Trainer opened. No game changes have been applied.");
    }
    private string ValuePair(int value, int max) => snapshot.HasValue(value) ? $"{snapshot.Values[value]:0.##} / {(snapshot.HasValue(max) ? snapshot.Values[max].ToString("0.##") : "—")}" : "—";
    private Dictionary<string, IReadOnlyList<FeatureChoice>> LoadLookups()
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
    private void Filter()
    {
        VisibleFeatures.Clear(); foreach (var f in features.Where(f => f.Definition.Category == SelectedCategory && (Search.Length == 0 || f.Name.Contains(Search, StringComparison.OrdinalIgnoreCase) || f.Description.Contains(Search, StringComparison.OrdinalIgnoreCase)))) VisibleFeatures.Add(f);
        Changed(nameof(FeatureCountText));
    }
    private void RefreshProcesses()
    {
        var found = TargetGame.FindRunning();
        if (found.Select(p => p.Pid).SequenceEqual(Processes.Select(p => p.Process.Pid))) return;
        int? prior = SelectedProcess?.Process.Pid;
        Processes.Clear(); foreach (var item in found) Processes.Add(new ProcessChoice(item));
        SelectedProcess = Processes.FirstOrDefault(p => p.Process.Pid == prior) ?? Processes.FirstOrDefault();
    }
    private void Poll()
    {
        try
        {
            if (++pollCount % 10 == 0) RefreshProcesses();
            if (!session.Connected && snapshot.Connected) { session.Dispose(); Log("Game process exited. Session disconnected."); }
            snapshot = session.ReadSnapshot();
            if (snapshot.HasValue(121))
            {
                double currentSequence = snapshot.Values[121];
                if (lastShortcutSequence.HasValue && lastShortcutSequence != currentSequence && snapshot.HasValue(119) && snapshot.HasValue(120))
                {
                    string action = catalog.FirstOrDefault(f => f.CommandId == snapshot.Values[119])?.Name ?? "Training action";
                    Log($"Game shortcut · {action}: " + (snapshot.Values[120] == 0 ? "completed." : $"rejected (code {snapshot.Values[120]:0}). {snapshot.Message}"));
                }
                lastShortcutSequence = currentSequence;
            }
            else lastShortcutSequence = null;
            if (!Busy) StatusMessage = snapshot.Message;
            foreach (var feature in features) feature.Update(snapshot);
            foreach (string property in new[] { nameof(StatusBrush), nameof(ConnectionDetail), nameof(ConnectLabel), nameof(HealthText), nameof(MagicText), nameof(DriveText), nameof(SessionSummary) }) Changed(property);
            RefreshCommands();
        }
        catch (IOException e) { StatusMessage = e.Message; }
        catch (InvalidOperationException e) { StatusMessage = e.Message; }
    }
    private void RefreshCommands()
    {
        foreach (var command in new[] { ConnectCommand, StartGameCommand, ShowDebugCommand, DisableEffectsCommand, SaveProfileCommand, LoadProfileCommand, ApplyProfileCommand, BackupCommand, RestoreBackupCommand }) command?.Refresh();
        foreach (var feature in features) feature.ApplyCommand.Refresh(); Changed(nameof(ConnectLabel));
    }
    private async Task Connect()
    {
        Busy = true;
        try
        {
            if (session.Connected) { await session.DisconnectAsync(); Log("Disconnected; persistent effects disabled."); return; }
            int pid = SelectedProcess?.Process.Pid ?? throw new InvalidOperationException("Start KH2 first.");
            using var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("KH2Trainer.Bridge") ?? throw new InvalidOperationException("This development build does not contain a native bridge yet.");
            using var bytes = new MemoryStream(); resource.CopyTo(bytes);
            await session.ConnectAsync(pid, bytes.ToArray(), new Progress<string>(s => StatusMessage = s));
            Log($"Connected to KH2 process {pid}. Build checks passed.");
        }
        catch (Exception e) { Log("Connection failed: " + e.Message); throw; }
        finally { Busy = false; Poll(); }
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
        try { var result = await session.ExecuteAsync(command, arguments); Log($"{label}: {result.Message}"); if (!result.Success) throw new InvalidOperationException(result.Message); }
        catch (Exception e) { Log($"{label} failed: {e.Message}"); throw; }
    }
    private Task SaveProfile()
    {
        var profile = new TrainerProfile { Name = ProfileName.Trim(), Values = features.Where(f => f.Definition.CanSaveInProfile).ToDictionary(f => f.Definition.Id, f => f.ReadValue()) };
        string path = profiles.Save(profile, catalog); loadedProfile = profile; ProfileSummary = $"Saved {profile.Values.Count} settings to {path}"; Log("Profile saved: " + profile.Name); ApplyProfileCommand.Refresh(); return Task.CompletedTask;
    }
    private Task LoadProfile()
    {
        Directory.CreateDirectory(profiles.Folder); var picker = new OpenFileDialog { Filter = "Trainer profile|*.json", InitialDirectory = profiles.Folder };
        if (picker.ShowDialog() != true) return Task.CompletedTask;
        loadedProfile = profiles.Read(picker.FileName, catalog); ProfileName = loadedProfile.Name;
        foreach (var pair in loadedProfile.Values) features.Single(f => f.Definition.Id == pair.Key).SetInput(pair.Value);
        ProfileSummary = $"Loaded {loadedProfile.Values.Count} settings. Review them, then apply the profile."; ApplyProfileCommand.Refresh(); return Task.CompletedTask;
    }
    private async Task ApplyProfile()
    {
        if (loadedProfile == null) return;
        ProfileStore.Validate(loadedProfile, catalog);
        foreach (var pair in loadedProfile.Values)
        {
            var feature = catalog.Single(f => f.Id == pair.Key);
            if (!snapshot.Supports(feature.CapabilitySlot) || feature.RequiresScene && !snapshot.SceneReady)
                throw new InvalidOperationException($"{feature.Name} is unavailable. No profile settings were applied.");
        }
        Busy = true; int applied = 0;
        try
        {
            foreach (var pair in loadedProfile.Values) { var feature = catalog.Single(f => f.Id == pair.Key); await Execute(feature.CommandId, [pair.Value], feature.Name); applied++; }
            ProfileSummary = $"Applied all {applied} settings from {loadedProfile.Name}.";
        }
        catch { ProfileSummary = $"Application stopped after {applied} of {loadedProfile.Values.Count} settings. Check the activity log; earlier successful changes remain applied."; throw; }
        finally { Busy = false; }
    }
    private async Task Backup()
    {
        Busy = true;
        try { string path = await Task.Run(() => backups.Create(SaveFolder, () => TargetGame.FindRunning().Count != 0)); BackupSummary = "Created and verified: " + path; Log(BackupSummary); }
        finally { Busy = false; }
    }
    private async Task RestoreBackup()
    {
        if (TargetGame.FindRunning().Count != 0) throw new InvalidOperationException("Close the game before restoring a save backup.");
        var picker = new OpenFileDialog { Filter = "KH2 backup|*.zip", InitialDirectory = backups.Folder };
        if (picker.ShowDialog() != true) return;
        var manifest = BackupStore.Verify(picker.FileName);
        if (MessageBox.Show($"Restore {manifest.Files.Count} backed-up files into:\n{SaveFolder}\n\nA backup of the current files will be created first.", "Restore save backup", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
        Busy = true;
        try { string before = await Task.Run(() => backups.Restore(picker.FileName, SaveFolder, () => TargetGame.FindRunning().Count != 0)); BackupSummary = "Restored successfully. Previous state backed up to: " + before; Log("Save backup restored."); }
        finally { Busy = false; }
    }
    private Task OpenAnalysis()
    {
        string local = Path.Combine(AppContext.BaseDirectory, "Analysis", "KH2_Analyse.html");
        if (!File.Exists(local)) local = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "KH2_Analyse.html"));
        if (!File.Exists(local))
        {
            DirectoryInfo? directory = new(AppContext.BaseDirectory);
            for (int depth = 0; depth < 7 && directory != null; depth++, directory = directory.Parent)
            {
                string candidate = Path.Combine(directory.FullName, "outputs", "KH2_Analyse.html");
                if (File.Exists(candidate)) { local = candidate; break; }
            }
        }
        if (!File.Exists(local)) throw new FileNotFoundException("The analysis report is not included in this development output yet.");
        OpenPath(local); return Task.CompletedTask;
    }
    private Task ExportEvidence()
    {
        var picker = new SaveFileDialog { Filter = "JSON|*.json", FileName = "KH2_Trainer_Features.json" };
        if (picker.ShowDialog() == true) File.WriteAllText(picker.FileName, JsonSerializer.Serialize(catalog, FeatureCatalog.JsonOptions)); return Task.CompletedTask;
    }
    private Task ExportLog()
    {
        var picker = new SaveFileDialog { Filter = "Text log|*.txt", FileName = "KH2_Trainer_Log.txt" };
        if (picker.ShowDialog() == true) File.WriteAllLines(picker.FileName, activity); return Task.CompletedTask;
    }
    private static void OpenPath(string path) => Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
    private void Log(string message)
    {
        string entry = $"{DateTime.Now:HH:mm:ss}   {message}"; activity.Add(entry); RecentActivity.Insert(0, entry);
        while (RecentActivity.Count > 3) RecentActivity.RemoveAt(RecentActivity.Count - 1);
    }
    public void Dispose() { timer.Stop(); Assets.Dispose(); session.Dispose(); }
}
