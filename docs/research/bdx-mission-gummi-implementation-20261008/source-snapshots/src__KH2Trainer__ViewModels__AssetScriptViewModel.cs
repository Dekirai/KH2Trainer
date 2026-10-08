using System.IO;
using KH2Trainer.Core;

namespace KH2Trainer;

public sealed record BdxInstructionRow(BdxInstruction Instruction)
{
    public BdxInstruction Instruction { get; } = Instruction;
    public BdxNativeCallInfo? NativeInfo { get; } = Instruction.TrapBank is int bank && Instruction.TrapIndex is int index
        ? BdxNativeCallCatalog.Default.Lookup(bank,index) : null;
    public string PcText => Instruction.Pc.ToString();
    public string OffsetText => $"0x{Instruction.FileOffset:X}";
    public string Words => string.Join(" ",Instruction.Words.Select(w=>$"{w:X4}"));
    public string Operation => Instruction.Operation;
    public string Operands => Instruction.Operands;
    public string NativeCall => NativeInfo is {} info ? $"{info.Bank}:{info.Index}"+(info.HasAnnotation?$" · {info.DisplayName}":"") : "";
    public string SearchText => $"{PcText} {OffsetText} {Words} {Operation} {Operands} {NativeCall} {NativeInfo?.SearchText}";
    public string Edges => string.Join("\n",Instruction.Edges.Select(e=>e.Kind switch {
        BdxEdgeKind.Next=>$"Next: PC {e.TargetPc}",
        BdxEdgeKind.Branch=>$"Branch target: PC {e.TargetPc}",
        BdxEdgeKind.Call=>$"Call target: PC {e.TargetPc}",
        BdxEdgeKind.CallContinuation=>$"If the call returns: PC {e.TargetPc}",
        BdxEdgeKind.YieldResume=>$"If execution resumes after this yield: PC {e.TargetPc}",
        BdxEdgeKind.NativeContinuation=>$"If the native call returns without changing the PC: PC {e.TargetPc}",
        _=>"Return target comes from native VM stack state; PC 0 ends the invocation."
    }));
    public string Details
    {
        get {
            return $"PC {PcText} · file {OffsetText} · {Instruction.WidthInWords} words\n{Words}\n{Operation}\n{Operands}\n\n"+
                (Edges.Length>0?Edges:"No statically followed successor. See diagnostics for invalid or unresolved operations.")+
                (NativeInfo is {} info?"\n\n"+info.Details:"");
        }
    }
}
public sealed record BdxEventRow(BdxEvent Event)
{
    public string Label=>$"Event {Event.Id} → PC {Event.Pc}"+(Event.IsFirstForId?"":" (shadowed by first entry)");
}

public sealed partial class AssetExplorerViewModel
{
    private BdxDocument? script;
    private IReadOnlyList<BdxInstructionRow> allScriptRows=[],scriptRows=[];
    private IReadOnlyList<BdxEventRow> scriptEvents=[];
    private BdxInstructionRow? selectedScriptInstruction;
    private BdxEventRow? selectedScriptEvent;
    private string scriptTitle="",scriptFilter="";
    private int selectedAssetTab;
    private int scriptGeneration;
    public AsyncCommand InspectScriptCommand { get; }
    public int SelectedAssetTab { get=>selectedAssetTab; set=>Set(ref selectedAssetTab,value); }
    public bool HasScript=>script!=null;
    public string ScriptTitle=>script==null?"Inspect a BDX script":scriptTitle;
    public string ScriptSummary=>script==null?"Choose an asset, then use Inspect BDX. Loose .bdx files and BAR type 3 entries open here automatically.":
        $"{script.Header.Name} · {script.ByteLength:N0} bytes · {script.Header.Events.Count:N0} event entries\n"+
        $"Work {script.Header.WorkBytes:N0} · stack {script.Header.StackBytes:N0} · temporary {script.Header.TemporaryBytes:N0} bytes\n"+
        $"{script.Instructions.Count:N0} decoded instructions · {script.UndecodedBytes:N0} bytes not decoded"+
        (script.HitLimit?" · inspection limit reached":"");
    public string ScriptScope=>BdxDocument.Scope+" Literal values shown here are the stored values; the game can apply compatibility adjustments at runtime.";
    public string ScriptCountText=>$"{scriptRows.Count:N0} of {allScriptRows.Count:N0} instructions";
    public string ScriptDiagnostics=>script==null?"":script.Diagnostics.Count==0?"No structural issues found in the followed paths. This does not validate runtime objects, stack values or native calls.":
        string.Join("\n",script.Diagnostics.Select(d=>$"{d.Code}"+(d.Pc is int pc?$" · PC {pc}":"")+": "+d.Message))+
        (script.SuppressedDiagnostics>0?$"\n{script.SuppressedDiagnostics:N0} additional diagnostics suppressed.":"");
    public IReadOnlyList<BdxInstructionRow> ScriptRows=>scriptRows;
    public IReadOnlyList<BdxEventRow> ScriptEvents=>scriptEvents;
    public string ScriptFilter { get=>scriptFilter; set {if(Set(ref scriptFilter,value))RefreshScriptRows();} }
    public BdxInstructionRow? SelectedScriptInstruction {get=>selectedScriptInstruction;set {
        if(value==null&&selectedScriptInstruction!=null&&scriptRows.Contains(selectedScriptInstruction))return;
        if(Set(ref selectedScriptInstruction,value))Changed(nameof(ScriptInstructionDetails));
    }}
    public string ScriptInstructionDetails=>selectedScriptInstruction?.Details??"Choose an instruction to see its raw words and control-flow edges.";
    public BdxEventRow? SelectedScriptEvent {get=>selectedScriptEvent;set {
        if(value==null&&selectedScriptEvent!=null&&scriptEvents.Contains(selectedScriptEvent))return;
        if(Set(ref selectedScriptEvent,value)&&value!=null) {
            ScriptFilter="";
            selectedScriptInstruction=value.Event.IsFirstForId?allScriptRows.FirstOrDefault(r=>r.Instruction.Pc==value.Event.Pc):null;
            Changed(nameof(SelectedScriptInstruction));Changed(nameof(ScriptInstructionDetails));
        }
    }}
    private void RefreshScriptRows()
    {
        string query=scriptFilter.Trim();scriptRows=query.Length==0?allScriptRows:allScriptRows.Where(r=>r.SearchText.Contains(query,StringComparison.OrdinalIgnoreCase)).ToArray();
        if(selectedScriptInstruction!=null&&!scriptRows.Contains(selectedScriptInstruction))selectedScriptInstruction=null;
        Changed(nameof(ScriptRows));Changed(nameof(ScriptCountText));Changed(nameof(SelectedScriptInstruction));Changed(nameof(ScriptInstructionDetails));
    }
    private void ClearScript()
    {
        ++scriptGeneration;
        script=null;scriptTitle="";scriptFilter="";allScriptRows=scriptRows=[];scriptEvents=[];selectedScriptInstruction=null;selectedScriptEvent=null;
        NotifyScript();
    }
    private void NotifyScript()
    {
        foreach(string name in new[]{nameof(HasScript),nameof(ScriptTitle),nameof(ScriptSummary),nameof(ScriptRows),nameof(ScriptEvents),nameof(ScriptFilter),
            nameof(ScriptCountText),nameof(ScriptDiagnostics),nameof(SelectedScriptInstruction),nameof(SelectedScriptEvent),nameof(ScriptInstructionDetails)})Changed(name);
    }
    private async Task LoadScript(AssetPayload payload,string name,CancellationToken token,int? expectedGeneration=null)
    {
        int generation=expectedGeneration??scriptGeneration;
        if(disposed||generation!=scriptGeneration)throw new OperationCanceledException("Script selection changed.");
        var parsed=await Task.Run(()=>BdxInspector.ReadAsync(reader,payload,cancellationToken:token),token);
        token.ThrowIfCancellationRequested();
        if(disposed||generation!=scriptGeneration)throw new OperationCanceledException("Script selection changed.");
        script=parsed;scriptTitle=name;scriptFilter="";
        allScriptRows=scriptRows=parsed.Instructions.Select(i=>new BdxInstructionRow(i)).ToArray();
        scriptEvents=parsed.Header.Events.Select(e=>new BdxEventRow(e)).ToArray();
        selectedScriptEvent=scriptEvents.FirstOrDefault();
        selectedScriptInstruction=selectedScriptEvent!=null?allScriptRows.FirstOrDefault(i=>i.Instruction.Pc==selectedScriptEvent.Event.Pc):null;
        NotifyScript();SelectedAssetTab=2;
        Status=$"Inspected {parsed.Instructions.Count:N0} stored BDX instructions. {parsed.Diagnostics.Count:N0} structural diagnostics. No script was executed.";
    }
    public Task InspectScriptAsync()
    {
        var row=selection;var index=package;if(row==null)return Task.CompletedTask;
        return Run("Reading BDX script…",async token=>{
            ClearScript();int generation=scriptGeneration;SelectedAssetTab=2;AssetPayload? payload=row.Payload;
            if(row.PackageEntry is {} entry&&index!=null)
                payload=(await Task.Run(()=>reader.InspectPackageEntry(index,entry.Ordinal,token),token)).Original;
            if(payload==null)throw new InvalidDataException("Choose a payload before inspecting a BDX script.");
            await LoadScript(payload,row.Name,token,generation);
        });
    }
}
