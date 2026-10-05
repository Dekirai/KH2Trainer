using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json;
using System.Windows;
using KH2Trainer.Core;
using Microsoft.Win32;

namespace KH2Trainer;

/// <summary>Start page: live summary, session controls, quick actions and pinned features.</summary>
public sealed class HomeVm(MainViewModel shell) : PageVm
{
    public MainViewModel Shell { get; } = shell;
    public override string Title => "Home";
    public override string Icon => "";
    public override string Subtitle => "Your session at a glance. Pin any feature with its star to keep it here.";
    public override string Group => "TRAINER";
    public FeatureGroupVm Pinned => FeatureGroupVm.Create("Pinned", Shell.FavoriteFeatures);
    public bool HasPinned => Shell.FavoriteFeatures.Count > 0;
    public bool HasNoPinned => !HasPinned;
    public void RefreshPinned() => Changed(nameof(Pinned), nameof(HasPinned), nameof(HasNoPinned));
}

/// <summary>Reusable trainer settings and verified save backups.</summary>
public sealed class ProfilesVm : PageVm
{
    private readonly MainViewModel shell;
    private readonly ProfileStore profiles;
    private readonly BackupStore backups;
    private TrainerProfile? loadedProfile;
    private string profileName = "My training setup", profileSummary = "No profile loaded.", saveFolder,
        backupSummary = "Backups are stored separately from the game and include a SHA-256 manifest.";
    private string? selectedProfileFile;

    public override string Title => "Profiles & Saves";
    public override string Icon => "";
    public override string Subtitle => "Keep useful trainer settings and verified copies of your save files.";
    public override string Group => "TOOLS";
    public override bool UsesGame => false;

    public ObservableCollection<string> SavedProfiles { get; } = [];
    public string? SelectedProfileFile
    {
        get => selectedProfileFile;
        // A page being swapped out pushes null from its list; keep a selection that is still listed.
        set { if (value is null && selectedProfileFile is not null && SavedProfiles.Contains(selectedProfileFile)) return; if (Set(ref selectedProfileFile, value)) LoadSelectedCommand.Refresh(); }
    }
    public bool HasSavedProfiles => SavedProfiles.Count > 0;
    public string ProfileName { get => profileName; set => Set(ref profileName, value); }
    public string ProfileSummary { get => profileSummary; private set => Set(ref profileSummary, value); }
    public string SaveFolder { get => saveFolder; set { if (Set(ref saveFolder, value ?? "")) shell.SaveFolderSetting = saveFolder; } }
    public string BackupSummary { get => backupSummary; private set => Set(ref backupSummary, value); }
    public string StorageFolder => shell.UserFolder;

    public AsyncCommand SaveProfileCommand { get; }
    public AsyncCommand LoadProfileCommand { get; }
    public AsyncCommand LoadSelectedCommand { get; }
    public AsyncCommand ApplyProfileCommand { get; }
    public AsyncCommand OpenProfilesCommand { get; }
    public AsyncCommand ChooseSaveFolderCommand { get; }
    public AsyncCommand BackupCommand { get; }
    public AsyncCommand RestoreBackupCommand { get; }
    public AsyncCommand OpenBackupsCommand { get; }

    public ProfilesVm(MainViewModel shell)
    {
        this.shell = shell;
        profiles = new ProfileStore(Path.Combine(shell.UserFolder, "Profiles"));
        backups = new BackupStore(Path.Combine(shell.UserFolder, "Backups"));
        saveFolder = shell.SaveFolderSetting;
        SaveProfileCommand = new AsyncCommand(SaveProfile, () => !shell.Busy);
        LoadProfileCommand = new AsyncCommand(BrowseProfile, () => !shell.Busy);
        LoadSelectedCommand = new AsyncCommand(() => { if (SelectedProfileFile != null) LoadProfile(SelectedProfileFile); return Task.CompletedTask; }, () => !shell.Busy && SelectedProfileFile != null);
        ApplyProfileCommand = new AsyncCommand(ApplyProfile, () => shell.IsConnected && loadedProfile != null && !shell.Busy);
        OpenProfilesCommand = new AsyncCommand(() => { Directory.CreateDirectory(profiles.Folder); MainViewModel.OpenPath(profiles.Folder); return Task.CompletedTask; });
        ChooseSaveFolderCommand = new AsyncCommand(() => { var d = new OpenFolderDialog { Title = "Choose the KH2 save folder" }; if (d.ShowDialog() == true) SaveFolder = d.FolderName; return Task.CompletedTask; });
        BackupCommand = new AsyncCommand(Backup, () => !shell.Busy && SaveFolder.Length > 0);
        RestoreBackupCommand = new AsyncCommand(RestoreBackup, () => !shell.Busy && SaveFolder.Length > 0);
        OpenBackupsCommand = new AsyncCommand(() => { Directory.CreateDirectory(backups.Folder); MainViewModel.OpenPath(backups.Folder); return Task.CompletedTask; });
        RefreshSavedProfiles();
        PropertyChanged += (_, e) => { if (e.PropertyName == nameof(SaveFolder)) RefreshCommands(); };
    }

    public void RefreshCommands()
    {
        foreach (var command in new[] { SaveProfileCommand, LoadProfileCommand, LoadSelectedCommand, ApplyProfileCommand, BackupCommand, RestoreBackupCommand }) command.Refresh();
    }

    private void RefreshSavedProfiles()
    {
        SavedProfiles.Clear();
        foreach (string file in profiles.List()) SavedProfiles.Add(Path.GetFileNameWithoutExtension(file));
        Changed(nameof(HasSavedProfiles));
    }

    private Task SaveProfile()
    {
        var profile = new TrainerProfile { Name = ProfileName.Trim(), Values = shell.Features.Where(f => f.Definition.CanSaveInProfile).ToDictionary(f => f.Definition.Id, f => f.ReadValue()) };
        string path = profiles.Save(profile, shell.Catalog); loadedProfile = profile;
        ProfileSummary = $"Saved {profile.Values.Count} settings to {path}"; shell.Log("Profile saved: " + profile.Name);
        RefreshSavedProfiles(); RefreshCommands(); return Task.CompletedTask;
    }

    private Task BrowseProfile()
    {
        Directory.CreateDirectory(profiles.Folder);
        var picker = new OpenFileDialog { Filter = "Trainer profile|*.json", InitialDirectory = profiles.Folder };
        if (picker.ShowDialog() == true) LoadProfile(picker.FileName);
        return Task.CompletedTask;
    }

    private void LoadProfile(string nameOrPath)
    {
        string path = Path.IsPathRooted(nameOrPath) ? nameOrPath : Path.Combine(profiles.Folder, nameOrPath + ".json");
        loadedProfile = profiles.Read(path, shell.Catalog); ProfileName = loadedProfile.Name;
        foreach (var pair in loadedProfile.Values) shell.Feature(pair.Key)?.SetInput(pair.Value);
        ProfileSummary = $"Loaded {loadedProfile.Values.Count} settings from “{loadedProfile.Name}”. Numeric and list inputs show them for review (switches keep showing the game's state); choose Apply profile to send them to the game.";
        RefreshCommands();
    }

    private async Task ApplyProfile()
    {
        if (loadedProfile == null) return;
        ProfileStore.Validate(loadedProfile, shell.Catalog);
        var snapshot = shell.Snapshot;
        foreach (var pair in loadedProfile.Values)
        {
            var feature = shell.Catalog.Single(f => f.Id == pair.Key);
            if (!snapshot.Supports(feature.CapabilitySlot) || feature.RequiresScene && !snapshot.SceneReady)
                throw new InvalidOperationException($"{feature.Name} is unavailable. No profile settings were applied.");
        }
        shell.SetBusy(true); int applied = 0;
        try
        {
            foreach (var pair in loadedProfile.Values)
            {
                var feature = shell.Catalog.Single(f => f.Id == pair.Key);
                await shell.Execute(feature.CommandId, [pair.Value], feature.Name); applied++;
                shell.Feature(pair.Key)?.MarkApplied();
            }
            ProfileSummary = $"Applied all {applied} settings from “{loadedProfile.Name}”.";
        }
        catch { ProfileSummary = $"Stopped after {applied} of {loadedProfile.Values.Count} settings. Earlier successful changes remain applied; the activity log shows where it stopped."; throw; }
        finally { shell.SetBusy(false); }
    }

    private async Task Backup()
    {
        shell.SetBusy(true);
        try
        {
            string path = await Task.Run(() => backups.Create(SaveFolder, () => TargetGame.FindRunning().Count != 0));
            BackupSummary = "Created and verified: " + path; shell.Log(BackupSummary);
        }
        finally { shell.SetBusy(false); }
    }

    private async Task RestoreBackup()
    {
        if (TargetGame.FindRunning().Count != 0) throw new InvalidOperationException("Close the game before restoring a save backup.");
        var picker = new OpenFileDialog { Filter = "KH2 backup|*.zip", InitialDirectory = backups.Folder };
        if (picker.ShowDialog() != true) return;
        var manifest = BackupStore.Verify(picker.FileName);
        if (MessageBox.Show($"Restore {manifest.Files.Count} backed-up files into:\n{SaveFolder}\n\nA backup of the current files will be created first.", "Restore save backup", MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
        shell.SetBusy(true);
        try
        {
            string before = await Task.Run(() => backups.Restore(picker.FileName, SaveFolder, () => TargetGame.FindRunning().Count != 0));
            BackupSummary = "Restored successfully. The previous files were backed up to: " + before; shell.Log("Save backup restored.");
        }
        finally { shell.SetBusy(false); }
    }
}

/// <summary>Build information, research evidence and exports.</summary>
public sealed class AboutVm : PageVm
{
    private readonly MainViewModel shell;
    public override string Title => "About";
    public override string Icon => "";
    public override string Subtitle => "Supported game build, research evidence and exports.";
    public override string Group => "TOOLS";
    public string Version => shell.VersionLabel;
    public string GameHash => TargetGame.Sha256;
    public string ResearchSummary => $"The trainer is tied to one verified game build (Steam 1.0.0.2, x64). Every feature in its catalog links to the code or data structure it uses. " +
        $"The current inventory covers 36,451 recognized native functions, 445 managed entries (439 bodies) and 47 shaders. " +
        $"This build contains {shell.Catalog.Count} controls and readouts plus the offline Asset Explorer and Game Messages reference. " +
        "Automatic coverage is tracked separately from confirmed runtime behavior.";
    public AsyncCommand OpenGuideCommand { get; }
    public AsyncCommand OpenAnalysisCommand { get; }
    public AsyncCommand ExportEvidenceCommand { get; }
    public AsyncCommand ExportLogCommand => shell.ExportLogCommand;

    public AboutVm(MainViewModel shell)
    {
        this.shell = shell;
        OpenGuideCommand = new AsyncCommand(() => { MainViewModel.OpenPath(Path.Combine(AppContext.BaseDirectory, "UserGuide.html")); return Task.CompletedTask; });
        OpenAnalysisCommand = new AsyncCommand(OpenAnalysis);
        ExportEvidenceCommand = new AsyncCommand(ExportEvidence);
    }

    private static Task OpenAnalysis()
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
        MainViewModel.OpenPath(local); return Task.CompletedTask;
    }

    private Task ExportEvidence()
    {
        var picker = new SaveFileDialog { Filter = "JSON|*.json", FileName = "KH2_Trainer_Features.json" };
        if (picker.ShowDialog() == true) File.WriteAllText(picker.FileName, JsonSerializer.Serialize(shell.Catalog, FeatureCatalog.JsonOptions));
        return Task.CompletedTask;
    }
}
