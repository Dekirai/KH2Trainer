using System.IO;
using System.Text;
using KH2Trainer.Core;
using Microsoft.Win32;

namespace KH2Trainer;

public sealed record AssetRow(string Name, string Kind, long Length, string Detail,
    AssetPayload? Payload = null, PackageEntryInfo? PackageEntry = null, string? ExportName = null,
    AssetFingerprintSelection? FingerprintSelection = null)
{
    public string SizeText => $"{Length:N0} bytes";
    public bool Available => PackageEntry?.IsAvailable ?? true;
}

public sealed record AssetFingerprintRow(AssetFingerprint Fingerprint)
{
    public string Name => Fingerprint.DisplayName;
    public string Location => Fingerprint.SourceKey + " / " + string.Join(" / ", Fingerprint.Path.Select(p =>
        p.Kind == AssetSourceKind.BarEntry ? $"entry {p.Ordinal} ({p.TagHex})" :
        p.Kind == AssetSourceKind.PackageRemastered ? $"package entry {p.Ordinal}, remaster {p.RemasteredOrdinal}" :
        p.Kind == AssetSourceKind.PackageOriginal ? $"package entry {p.Ordinal}" : p.Name));
    public string Summary => $"{Fingerprint.Length:N0} bytes · SHA256 {Fingerprint.Sha256[..16]}…";
    public string Details => $"{Location}\n{Fingerprint.Length:N0} bytes\nSHA256: {Fingerprint.Sha256}\nMD5 (legacy): {Fingerprint.Md5}\nLocator ID: {Fingerprint.Id}";
}

public sealed class AssetExplorerViewModel : Observable, IDisposable
{
    private readonly AssetArchiveReader reader = new(protectedDirectories:
        new[] { Path.GetDirectoryName(TargetGame.DefaultPath)! });
    private readonly Action<string> log;
    private readonly Stack<BrowsePage> history = new();
    private sealed record BrowsePage(string Title, string Description, IReadOnlyList<AssetRow> Rows,
        PackageIndex? Index, AssetPayload? Container, AssetRow? Selection, string Filter,
        AssetFingerprintSelection? ContainerFingerprint, string SourceLabel);
    private IReadOnlyList<AssetRow> allRows = [], rows = [];
    private PackageIndex? package;
    private AssetPayload? container;
    private AssetFingerprintSelection? containerFingerprint;
    private readonly AssetFingerprintService fingerprints = new();
    private AssetFingerprintIndex fingerprintIndex = AssetFingerprintIndex.Create();
    private readonly HashSet<string> protectedIndexDirectories = new(StringComparer.OrdinalIgnoreCase)
        { Path.GetDirectoryName(TargetGame.DefaultPath)! };
    private IReadOnlyList<AssetFingerprintRow> fingerprintRows = [], fingerprintMatches = [];
    private AssetFingerprintRow? selectedFingerprint;
    private string sourceLabel = "My assets", fingerprintStatus = "Add selected assets to compare their exact payload content.", fingerprintDetails = "";
    private CancellationTokenSource? operation;
    private bool busy, disposed;
    private string title = "Open a loose asset or a retail package index", description = "",
        status = "Browse and extract assets without connecting to the game.", filter = "", preview = "", namesFile = "";
    private AssetRow? selection;
    public IReadOnlyList<AssetRow> Rows => rows;
    public string Title { get => title; private set => Set(ref title, value); }
    public string Description { get => description; private set => Set(ref description, value); }
    public string Status { get => status; private set => Set(ref status, value); }
    public string Preview { get => preview; private set => Set(ref preview, value); }
    public string SourceLabel { get => sourceLabel; set => Set(ref sourceLabel, value); }
    public string FingerprintStatus { get => fingerprintStatus; private set => Set(ref fingerprintStatus, value); }
    public string FingerprintDetails { get => fingerprintDetails; private set => Set(ref fingerprintDetails, value); }
    public IReadOnlyList<AssetFingerprintRow> FingerprintRows => fingerprintRows;
    public IReadOnlyList<AssetFingerprintRow> FingerprintMatches => fingerprintMatches;
    public string FingerprintCountText => $"{fingerprintIndex.Entries.Count:N0} fingerprints in memory";
    public AssetFingerprintRow? SelectedFingerprint { get => selectedFingerprint; set {
        // A view being swapped out pushes null; keep a selection that is still listed.
        if(value==null&&selectedFingerprint!=null&&fingerprintRows.Contains(selectedFingerprint))return;
        if(Set(ref selectedFingerprint,value)&&value!=null)FingerprintDetails=value.Details; } }
    public string Filter { get => filter; set { if(Set(ref filter,value)) RefreshRows(); } }
    public string CountText => $"{rows.Count:N0} of {allRows.Count:N0} entries";
    public string NamesFileLabel => string.IsNullOrEmpty(namesFile) ? "Optional name list: none" : "Name list: " + namesFile;
    public bool Busy { get => busy; private set { if(Set(ref busy,value)) { Changed(nameof(Idle)); RefreshCommands(); } } }
    public bool Idle => !Busy;
    public AssetRow? SelectedRow { get => selection; set {
        if(value==null&&selection!=null&&rows.Contains(selection))return; // see SelectedFingerprint
        if(Set(ref selection,value)) { Preview=""; Changed(nameof(SelectionDetails)); RefreshCommands(); } } }
    public string SelectionDetails => selection is null ? "Choose an entry to inspect or export." :
        $"{selection.Name}\n{selection.Kind} · {selection.SizeText}\n{selection.Detail}";
    public AsyncCommand OpenLooseCommand { get; }
    public AsyncCommand OpenPackageCommand { get; }
    public AsyncCommand ChooseNamesCommand { get; }
    public AsyncCommand ClearNamesCommand { get; }
    public AsyncCommand BackCommand { get; }
    public AsyncCommand InspectCommand { get; }
    public AsyncCommand ExportCommand { get; }
    public AsyncCommand ExportContainerCommand { get; }
    public AsyncCommand CancelCommand { get; }
    public AsyncCommand CaptureFingerprintCommand { get; }
    public AsyncCommand CaptureContainerFingerprintCommand { get; }
    public AsyncCommand CompareFingerprintCommand { get; }
    public AsyncCommand LoadFingerprintIndexCommand { get; }
    public AsyncCommand SaveFingerprintIndexCommand { get; }
    public AsyncCommand ClearFingerprintIndexCommand { get; }
    private IEnumerable<AsyncCommand> Commands => new[] { OpenLooseCommand,OpenPackageCommand,ChooseNamesCommand,
        ClearNamesCommand,BackCommand,InspectCommand,ExportCommand,ExportContainerCommand,CancelCommand,
        CaptureFingerprintCommand,CaptureContainerFingerprintCommand,CompareFingerprintCommand,
        LoadFingerprintIndexCommand,SaveFingerprintIndexCommand,ClearFingerprintIndexCommand };
    public AssetExplorerViewModel(Action<string> log)
    {
        this.log=log;
        OpenLooseCommand=new(OpenLoose,()=>Idle);
        OpenPackageCommand=new(OpenPackage,()=>Idle);
        ChooseNamesCommand=new(()=>{
            var dialog=new OpenFileDialog { Title="Choose a list of asset paths, one per line",Filter="Text files|*.txt|All files|*.*" };
            if(dialog.ShowDialog()==true) { namesFile=dialog.FileName; Changed(nameof(NamesFileLabel)); RefreshCommands(); }
            return Task.CompletedTask;
        },()=>Idle);
        ClearNamesCommand=new(()=>{namesFile="";Changed(nameof(NamesFileLabel));RefreshCommands();return Task.CompletedTask;},()=>Idle&&namesFile.Length>0);
        BackCommand=new(Back,()=>Idle&&history.Count>0);
        InspectCommand=new(InspectSelectedAsync,()=>Idle&&selection?.Available==true);
        ExportCommand=new(()=>Export(false),()=>Idle&&selection?.Available==true);
        ExportContainerCommand=new(()=>Export(true),()=>Idle&&container!=null);
        CancelCommand=new(()=>{operation?.Cancel();return Task.CompletedTask;},()=>Busy);
        CaptureFingerprintCommand=new(()=>CaptureSelectedFingerprintAsync(),()=>Idle&&selection?.Available==true);
        CaptureContainerFingerprintCommand=new(()=>CaptureSelectedFingerprintAsync(true),()=>Idle&&containerFingerprint!=null);
        CompareFingerprintCommand=new(()=>CompareSelectedFingerprintAsync(),()=>Idle&&selection?.Available==true&&fingerprintIndex.Entries.Count>0);
        LoadFingerprintIndexCommand=new(()=>{
            var dialog=new OpenFileDialog { Title="Load a fingerprint index (replaces the in-memory list)",Filter="Fingerprint index|*.json" };
            return dialog.ShowDialog()==true?LoadFingerprintIndexAsync(dialog.FileName):Task.CompletedTask;
        },()=>Idle);
        SaveFingerprintIndexCommand=new(()=>{
            var dialog=new SaveFileDialog { Title="Save fingerprint index to a new file",FileName="asset-fingerprints.json",Filter="Fingerprint index|*.json",OverwritePrompt=false };
            return dialog.ShowDialog()==true?SaveFingerprintIndexAsync(dialog.FileName):Task.CompletedTask;
        },()=>Idle&&fingerprintIndex.Entries.Count>0);
        ClearFingerprintIndexCommand=new(()=>{
            fingerprintIndex=AssetFingerprintIndex.Create();RefreshFingerprintRows();FingerprintDetails="";
            FingerprintStatus="Cleared the in-memory index. Saved files are unchanged.";return Task.CompletedTask;
        },()=>Idle&&fingerprintIndex.Entries.Count>0);
    }
    private void RefreshCommands() { foreach(var command in Commands) command?.Refresh(); }
    private void RefreshRows()
    {
        string query=filter.Trim();
        rows=query.Length==0?allRows:allRows.Where(r=>r.Name.Contains(query,StringComparison.OrdinalIgnoreCase)||
            r.Detail.Contains(query,StringComparison.OrdinalIgnoreCase)||r.Kind.Contains(query,StringComparison.OrdinalIgnoreCase)).ToArray();
        if(selection!=null&&!rows.Contains(selection))SelectedRow=null;
        Changed(nameof(Rows));Changed(nameof(CountText));
    }
    private void PushPage()
    {
        if(allRows.Count>0||container!=null||package!=null)
            history.Push(new(Title,Description,allRows,package,container,selection,filter,containerFingerprint,SourceLabel));
    }
    private void ShowPage(string pageTitle,string pageDescription,IReadOnlyList<AssetRow> entries,PackageIndex? index,AssetPayload? payload,
        AssetFingerprintSelection? fingerprintSelection=null)
    {
        Title=pageTitle;Description=pageDescription;allRows=entries;package=index;container=payload;
        containerFingerprint=fingerprintSelection;
        selection=null;filter="";Preview="";Changed(nameof(Filter));Changed(nameof(SelectedRow));Changed(nameof(SelectionDetails));
        RefreshRows();RefreshCommands();
    }
    private Task Back()
    {
        if(history.TryPop(out var page)) {
            ShowPage(page.Title,page.Description,page.Rows,page.Index,page.Container,page.ContainerFingerprint);
            SourceLabel=page.SourceLabel;
            Filter=page.Filter;SelectedRow=page.Selection;Status="Returned to the previous container.";
        }
        return Task.CompletedTask;
    }
    private async Task Run(string message,Func<CancellationToken,Task> action)
    {
        if(disposed) return;
        if(Busy)throw new InvalidOperationException("Wait for the current asset operation or cancel it first.");
        using var current=new CancellationTokenSource();operation=current;Busy=true;Status=message;
        try { await action(current.Token); }
        catch(OperationCanceledException) { Status="Operation cancelled. No new result was published."; }
        catch(Exception e) { Status=e.Message;log("Asset Explorer: "+e.Message);throw; }
        finally { operation=null;Busy=false; }
    }
    private Task OpenLoose()
    {
        var dialog=new OpenFileDialog { Title="Open a loose KH2 asset",Filter="KH2 assets|*.bin;*.bar;*.mdlx;*.mset;*.ard;*.anb;*.a.fm;*.map;*.2dd;*.2ld;*.tm2;*.bdx;*.vag|All files|*.*" };
        if(dialog.ShowDialog()!=true)return Task.CompletedTask;
        return OpenFileAsync(dialog.FileName);
    }
    public Task OpenFileAsync(string path)
    {
        return Run("Reading asset…",async token=>{
            var payload=await Task.Run(()=>reader.OpenLooseFile(path),token);
            var locator=AssetFingerprintSelection.FromLoose(payload,DefaultSourceLabel(path));
            await OpenPayload(payload,false,token,fingerprintSelection:locator);
            SourceLabel=locator.SourceKey;ProtectGameDirectory(payload.SourcePath);history.Clear();RefreshCommands();
        });
    }
    private Task OpenPackage()
    {
        var dialog=new OpenFileDialog { Title="Open a retail HED index (paired PKG in the same folder)",Filter="Retail package index|*.hed" };
        if(dialog.ShowDialog()!=true)return Task.CompletedTask;
        return OpenPackageIndexAsync(dialog.FileName);
    }
    public Task OpenPackageIndexAsync(string path)
    {
        string? names=namesFile.Length==0?null:namesFile;
        return Run("Reading package index…",async token=>{
            var index=await Task.Run(()=>reader.OpenPackageIndex(path,names,token),token);
            var entries=index.Entries.Select(e=>new AssetRow(e.Name,e.IsAvailable?"Package entry":"Unavailable",e.OriginalLength,
                $"#{e.Ordinal} · MD5 {e.NameHash} · stored {e.StoredLength:N0} bytes · offset {e.Offset:N0}",PackageEntry:e)).ToArray();
            token.ThrowIfCancellationRequested();history.Clear();
            SourceLabel=DefaultSourceLabel(index.HeaderPath);ProtectGameDirectory(index.PackagePath);
            ShowPage(Path.GetFileName(index.HeaderPath),index.PackagePath,entries,index,null);
            Status=$"Indexed {entries.Length:N0} entries. Unresolved names are shown as hashes; a name list applies when opening an index.";
            log("Asset Explorer indexed "+index.HeaderPath);
        });
    }
    public Task InspectSelectedAsync()
    {
        var row=selection;var index=package;
        if(row==null)return Task.CompletedTask;
        return Run("Inspecting selected asset…",async token=>{
            if(row.PackageEntry is {} entry&&index!=null) {
                var info=await Task.Run(()=>reader.InspectPackageEntry(index,entry.Ordinal,token),token);
                var entries=new List<AssetRow> { PayloadRow(info.Original,"Original asset",$"Stored mode {info.StoredMode}",
                    fingerprintSelection:AssetFingerprintSelection.FromPackage(index,info,DefaultSourceLabel(index.HeaderPath))) };
                entries.AddRange(info.Remastered.Select(r=>PayloadRow(r.Payload,"Remastered asset",
                    $"#{r.Ordinal} · logical offset {r.LogicalOffset:N0} · original offset {r.OriginalAssetOffset:N0} · stored mode {r.StoredMode}",
                    fingerprintSelection:AssetFingerprintSelection.FromPackage(index,info,DefaultSourceLabel(index.HeaderPath),r.Ordinal))));
                token.ThrowIfCancellationRequested();PushPage();
                ShowPage(entry.Name,"Original payload and remastered assets",entries,null,null);
                Status=$"{entries.Count:N0} payloads. Choose one to inspect or export.";
            } else if(row.Payload is {} payload) await OpenPayload(payload,true,token,row.Name,row.FingerprintSelection);
        });
    }
    private static AssetRow PayloadRow(AssetPayload p,string kind,string detail,string? exportName=null,
        AssetFingerprintSelection? fingerprintSelection=null) =>
        new(p.Name,kind,p.Length,detail,p,ExportName:exportName,FingerprintSelection:fingerprintSelection);
    private async Task OpenPayload(AssetPayload payload,bool push,CancellationToken token,string? displayName=null,
        AssetFingerprintSelection? fingerprintSelection=null)
    {
        byte[] prefix=await Task.Run(()=>reader.ReadPrefixAsync(payload,4096,token),token);
        string kind=AssetArchiveReader.Recognize(prefix);
        bool isBar=prefix.Length>=4&&prefix[0]==0x42&&prefix[1]==0x41&&prefix[2]==0x52&&prefix[3]==1;
        BarDocument? bar=isBar?await Task.Run(()=>reader.ReadBarAsync(payload,token),token):null;
        var entries=bar is null ? new[]{PayloadRow(payload,kind,payload.Description,fingerprintSelection:fingerprintSelection)} : bar.Entries.Select(e=>
            new AssetRow($"{e.Tag} · entry {e.Ordinal}",e.TypeName,e.Payload.Length,$"#{e.Ordinal} · tag {e.Tag} ({e.TagHex}) · type {e.Type} · link {e.LinkIndex} · offset {e.RelativeOffset:N0}"+
                (e.AliasOf is {} alias?$" · alias of #{alias}":""),e.Payload,ExportName:e.SuggestedFileName,
                FingerprintSelection:fingerprintSelection?.Child(e))).ToArray();
        token.ThrowIfCancellationRequested();
        if(push&&!ReferenceEquals(container,payload))PushPage();
        ShowPage(displayName??payload.Name,$"{kind} · {payload.Length:N0} bytes · {payload.SourcePath}",entries,null,payload,fingerprintSelection);
        if(bar is null)SelectedRow=entries[0];
        // Selecting a row clears its old preview, so assign the new bytes last.
        Preview=Hex(prefix);
        Status=bar is null ? $"Showing the first {prefix.Length:N0} bytes. Export preserves the full payload." :
            $"BAR contains {bar.Entries.Count:N0} entries. Select an entry to open nested BARs or export its bytes.";
    }
    private static string DefaultSourceLabel(string path)
    {
        string value = new(Path.GetFileName(path).Select(c => char.IsControl(c) || c is ':' or '/' or '\\' ? '_' : c).ToArray());
        value=value.Trim();return value.Length==0?"My assets":value[..Math.Min(value.Length,512)];
    }
    private void ProtectGameDirectory(string sourcePath)
    {
        for(var parent=Directory.GetParent(sourcePath);parent!=null;parent=parent.Parent)
            if(File.Exists(Path.Combine(parent.FullName,"KINGDOM HEARTS II FINAL MIX.exe")))
            { protectedIndexDirectories.Add(parent.FullName);break; }
    }
    private void RefreshFingerprintRows()
    {
        fingerprintRows=fingerprintIndex.Entries.Select(e=>new AssetFingerprintRow(e)).ToArray();
        fingerprintMatches=[];selectedFingerprint=null;
        Changed(nameof(FingerprintRows));Changed(nameof(FingerprintMatches));Changed(nameof(SelectedFingerprint));
        Changed(nameof(FingerprintCountText));RefreshCommands();
    }
    private async Task<AssetFingerprintSelection> ResolveFingerprint(AssetRow? row,PackageIndex? index,
        AssetFingerprintSelection? current,string label,bool wholeContainer,CancellationToken token)
    {
        AssetFingerprintSelection? locator=wholeContainer?current:row?.FingerprintSelection;
        if(!wholeContainer&&row?.PackageEntry is {} entry&&index!=null)
        {
            var info=await Task.Run(()=>reader.InspectPackageEntry(index,entry.Ordinal,token),token);
            locator=AssetFingerprintSelection.FromPackage(index,info,label);
        }
        if(locator==null)throw new InvalidOperationException("Select a payload or open a container first.");
        return locator.WithSourceKey(label);
    }
    public Task CaptureSelectedFingerprintAsync(bool wholeContainer=false)
    {
        var row=selection;var index=package;var current=containerFingerprint;string label=SourceLabel;
        return Run("Hashing selected payload…",async token=>{
            var locator=await ResolveFingerprint(row,index,current,label,wholeContainer,token);
            var record=await Task.Run(()=>fingerprints.CaptureAsync(reader,locator,token),token);
            token.ThrowIfCancellationRequested();
            bool replacing=fingerprintIndex.Entries.Any(e=>e.Id==record.Id);
            fingerprintIndex=fingerprintIndex.With(record);RefreshFingerprintRows();
            SelectedFingerprint=fingerprintRows.Single(r=>r.Fingerprint.Id==record.Id);
            FingerprintStatus=$"{(replacing?"Updated":"Added")} {record.DisplayName} · {record.Length:N0} bytes. Only this payload was read.";
            Status=FingerprintStatus;
        });
    }
    public Task CompareSelectedFingerprintAsync(bool wholeContainer=false)
    {
        var row=selection;var index=package;var current=containerFingerprint;string label=SourceLabel;
        return Run("Comparing selected payload…",async token=>{
            var locator=await ResolveFingerprint(row,index,current,label,wholeContainer,token);
            var record=await Task.Run(()=>fingerprints.CaptureAsync(reader,locator,token),token);
            token.ThrowIfCancellationRequested();
            fingerprintMatches=fingerprintIndex.FindMatches(record).Select(m=>new AssetFingerprintRow(m.Entry)).ToArray();
            Changed(nameof(FingerprintMatches));FingerprintDetails=new AssetFingerprintRow(record).Details;
            FingerprintStatus=$"{fingerprintMatches.Count:N0} matching fingerprints by SHA256 and byte length (including this location if indexed).";
            Status=FingerprintStatus;
        });
    }
    public Task LoadFingerprintIndexAsync(string path)
    {
        return Run("Loading fingerprint index…",async token=>{
            var loaded=await Task.Run(()=>AssetFingerprintFiles.LoadAsync(path,cancellationToken:token),token);
            token.ThrowIfCancellationRequested();fingerprintIndex=loaded;RefreshFingerprintRows();FingerprintDetails="";
            FingerprintStatus=$"Loaded {loaded.Entries.Count:N0} fingerprints. Stored asset paths were not opened; saved hashes are unverified observations.";
            Status=FingerprintStatus;
        });
    }
    public Task SaveFingerprintIndexAsync(string path)
    {
        var snapshot=fingerprintIndex;string[] roots=protectedIndexDirectories.ToArray();
        return Run("Saving fingerprint index…",async token=>{
            await Task.Run(()=>AssetFingerprintFiles.SaveNewAsync(snapshot,path,roots,token),token);
            FingerprintStatus=$"Saved {snapshot.Entries.Count:N0} fingerprints to a new file: {path}";
            Status=FingerprintStatus;
        });
    }
    private Task Export(bool wholeContainer)
    {
        var row=selection;var index=package;var current=container;
        if(wholeContainer?current is null:row is null)return Task.CompletedTask;
        string suggested=wholeContainer?current!.Name:row!.ExportName??row.Name;
        suggested=SafeFileName(suggested);
        var dialog=new SaveFileDialog { Title="Export asset to a new file",FileName=suggested,
            Filter="Binary asset|*.*",OverwritePrompt=false,AddExtension=false };
        if(dialog.ShowDialog()!=true)return Task.CompletedTask;
        if(File.Exists(dialog.FileName))throw new IOException("Choose a new filename. Existing files are kept.");
        return Run("Extracting asset…",async token=>{
            AssetPayload? payload=wholeContainer?current:row!.Payload;
            if(payload is null&&row?.PackageEntry is {} entry&&index!=null)
                payload=(await Task.Run(()=>reader.InspectPackageEntry(index,entry.Ordinal,token),token)).Original;
            if(payload is null)throw new InvalidOperationException("Select a payload first.");
            await Task.Run(()=>reader.ExportAsync(payload,dialog.FileName,token),token);
            Status=$"Exported {payload.Length:N0} bytes to {dialog.FileName}";log("Asset export: "+dialog.FileName);
        });
    }
    private static string SafeFileName(string value)
    {
        value=Path.GetFileName(value.Replace('\\','/'));
        foreach(char c in Path.GetInvalidFileNameChars())value=value.Replace(c,'_');
        value=value.TrimEnd(' ','.');return value.Length==0?"asset.bin":value;
    }
    private static string Hex(byte[] bytes)
    {
        var output=new StringBuilder();
        for(int start=0;start<bytes.Length;start+=16) {
            output.Append(start.ToString("X8")).Append("  ");
            for(int i=0;i<16;++i)output.Append(start+i<bytes.Length?bytes[start+i].ToString("X2")+" ":"   ");
            output.Append(" ");
            for(int i=start;i<Math.Min(start+16,bytes.Length);++i)output.Append(bytes[i] is >=32 and <=126?(char)bytes[i]:'.');
            output.AppendLine();
        }
        return output.ToString();
    }
    public void Dispose(){disposed=true;operation?.Cancel();}
}
