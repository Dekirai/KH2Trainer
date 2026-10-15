using System.Globalization;
using System.IO;
using KH2Trainer.Core;

namespace KH2Trainer;

public sealed record ContactDefinitionRow(ContactDefinition Definition)
{
    public string OrdinalText => Definition.Ordinal.ToString(CultureInfo.InvariantCulture);
    public string OffsetText => $"0x{Definition.Offset:X}";
    public string GroupText => Definition.Group.ToString(CultureInfo.InvariantCulture);
    public string TypeText => Definition.Type.ToString(CultureInfo.InvariantCulture);
    public string JointText => Definition.JointId?.ToString(CultureInfo.InvariantCulture) ?? "";
    public string HeightText => Definition.Height?.ToString(CultureInfo.InvariantCulture) ?? "";
    public string EnabledText => Definition.EnabledByStoredDefaultMask ? "yes" : "no";
    public string RawText => string.Join(" ", Enumerable.Range(0, Definition.RawHex.Length / 2).Select(i => Definition.RawHex.Substring(2 * i, 2)));
}

/// <summary>Offline BAR type 9 root motion and type 23 definition views. Nothing here reads or writes the game.</summary>
public sealed partial class AssetExplorerViewModel
{
    private const int MotionTab = 3, ContactsTab = 4;
    private MotionPayload? motion;
    private MotionRootSample? motionSample;
    private string motionTitle = "", motionError = "", motionSampleError = "";
    private double motionFrame;
    private int motionGeneration;
    private ContactDefinitionDocument? contacts;
    private IReadOnlyList<ContactDefinitionRow> allContactRows = [], contactRows = [];
    private string contactsTitle = "", contactsError = "";
    private bool showOnlyContacts;
    /// <summary>The model's first type 3 entry, kept when empty so <see cref="ContactScriptText"/> can name it.</summary>
    private AssetRow? contactScript;
    /// <summary>A BDX script needs its 28-byte header and an 8-byte event terminator. A shorter type 3 entry stores no script.</summary>
    private const int MinimumScriptBytes = 36;
    private AssetRow? ContactHandlerScript => contactScript is { Length: >= MinimumScriptBytes } script ? script : null;
    private int contactGeneration;
    public AsyncCommand OpenContactHandlerCommand { get; }

    public bool HasMotion => motion != null;
    public string MotionTitle => motion == null && motionError.Length == 0 ? "Inspect a motion" : motionTitle;
    public string MotionSummary => motion is { } m
        ? $"{(m.Kind == MotionPayloadKind.Raw ? "RAW" : "Prototype")} format · " + (m.HasRoot
            ? $"root motion present · {m.TimeCount:N0} time keys · {m.RawFrameCount:N0} RAW matrix frames"
            : "no root motion; every frame evaluates to the identity matrix")
        : motionError.Length > 0 ? "This type 9 entry could not be read as a root motion."
        : "Open a BAR type 9 (Motion) entry to evaluate its root motion. Nothing is read from or sent to the game.";
    public string MotionError => motionError;
    public bool HasMotionError => motionError.Length > 0;
    public string MotionScope => "Offline projection, not native safety (OfflineMotionProjection). Only the root path is decoded; skeletal, IK, attachments, resource lifetime and native binding are excluded. MathF results are not promised bit-identical to the game.";
    /// <summary>Slider bound in native 60-per-second frame input units. Outside its stored range the evaluator clamps RAW frames and applies each curve's own extrapolation.</summary>
    public double MotionFrameMaximum => 600;
    public double MotionFrame { get => motionFrame; set {
        if(!double.IsFinite(value))return;
        if(Set(ref motionFrame,Math.Clamp(value,0,MotionFrameMaximum)))EvaluateMotion();
    } }
    public string MotionFrameText => $"Frame {motionFrame.ToString("0.##",CultureInfo.InvariantCulture)} of {MotionFrameMaximum.ToString(CultureInfo.InvariantCulture)}";
    public string MotionSampleText
    {
        get {
            string frame=motionFrame.ToString("0.##",CultureInfo.InvariantCulture);
            if(motionSampleError.Length>0)return $"Frame {frame}: evaluation stopped. {motionSampleError}";
            if(motionSample is not { } s)return "";
            string head=$"Frame input {frame} · effective frame {s.EffectiveFrame.ToString("G7",CultureInfo.InvariantCulture)}"+
                (s.FirstRawFrame is int first?$" · RAW frames {first} → {s.SecondRawFrame}, fraction {s.RawFraction?.ToString("G7",CultureInfo.InvariantCulture)}":"")+
                (s.HasRoot?"":" · no root motion");
            var rows=Enumerable.Range(0,4).Select(r=>(r==3?"row 3 (translation)":$"row {r}").PadRight(21)+
                string.Concat(Enumerable.Range(0,4).Select(c=>s.Matrix[r,c].ToString("G7",CultureInfo.InvariantCulture).PadLeft(15))));
            return head+"\nRoot matrix, row-vector convention:\n"+string.Join("\n",rows);
        }
    }

    public bool HasContacts => contacts != null;
    public string ContactsTitle => contacts == null && contactsError.Length == 0 ? "Inspect contact definitions" : contactsTitle;
    public string ContactsSummary => contacts is { } d
        ? $"{d.Count:N0} stored definitions · {d.ContactCount:N0} type 10/11 contact definitions · {d.TrailingBytes:N0} trailing bytes\n"+
          $"Stored default group mask 0x{d.DefaultGroupMask:X8} enables groups {MaskGroups(d.DefaultGroupMask)}"
        : contactsError.Length > 0 ? "This type 23 entry could not be read as definitions."
        : "Open a BAR type 23 (Collision/contact definitions) entry from a model to list its stored definitions.";
    public string ContactsError => contactsError;
    public bool HasContactsError => contactsError.Length > 0;
    public string ContactsScope => ContactDefinitionDocument.Scope;
    public IReadOnlyList<ContactDefinitionRow> ContactRows => contactRows;
    public string ContactCountText => $"{contactRows.Count:N0} of {allContactRows.Count:N0} definitions";
    public bool ShowOnlyContacts { get => showOnlyContacts; set { if(Set(ref showOnlyContacts,value))RefreshContactRows(); } }
    public string ContactScriptText => contactScript is { } script
        ? "Event 27 delivers new type 10/11 contact IDs to the Actor script. " + (ContactHandlerScript != null
            ? $"This model's first script is {script.Name}."
            : $"This model's type 3 entry {script.Name} is {(script.Length == 0 ? "empty" : $"only {script.Length:N0} bytes, too short for a BDX script")}, so it stores no Event 27 handler.")
        : contacts == null ? "" : "No BAR type 3 script was found next to these definitions.";

    private static string MaskGroups(uint mask)
    {
        var groups=Enumerable.Range(0,32).Where(bit=>((mask>>bit)&1)!=0).ToArray();
        return groups.Length==0?"none":string.Join(", ",groups);
    }
    private void EvaluateMotion()
    {
        // Parsing runs off the UI thread; one sample is bounded by MotionReadLimits.MaxEvaluationSteps.
        motionSample=null;motionSampleError="";
        if(motion!=null)
            try { motionSample=motion.Evaluate((float)motionFrame); }
            catch(MotionPayloadException e) { motionSampleError=e.Message; }
        Changed(nameof(MotionFrameText));Changed(nameof(MotionSampleText));
    }
    private void RefreshContactRows()
    {
        contactRows=showOnlyContacts?allContactRows.Where(r=>r.Definition.IsContact).ToArray():allContactRows;
        Changed(nameof(ContactRows));Changed(nameof(ContactCountText));
    }
    private void ClearInspection() { ClearScript(); ClearMotion(); ClearContacts(); }
    private void ClearMotion()
    {
        ++motionGeneration;
        motion=null;motionSample=null;motionTitle=motionError=motionSampleError="";motionFrame=0;
        NotifyMotion();
    }
    private void NotifyMotion()
    {
        foreach(string name in new[]{nameof(HasMotion),nameof(MotionTitle),nameof(MotionSummary),nameof(MotionError),nameof(HasMotionError),
            nameof(MotionFrame),nameof(MotionFrameText),nameof(MotionSampleText)})Changed(name);
    }
    private void ClearContacts()
    {
        ++contactGeneration;
        contacts=null;allContactRows=contactRows=[];contactsTitle=contactsError="";contactScript=null;
        NotifyContacts();
    }
    private void NotifyContacts()
    {
        foreach(string name in new[]{nameof(HasContacts),nameof(ContactsTitle),nameof(ContactsSummary),nameof(ContactsError),nameof(HasContactsError),
            nameof(ContactRows),nameof(ContactCountText),nameof(ContactScriptText)})Changed(name);
        OpenContactHandlerCommand.Refresh();
    }
    private async Task LoadMotion(AssetPayload payload,string name,CancellationToken token)
    {
        int generation=motionGeneration;
        long maximum=(long)new MotionReadLimits().MaxPayloadBytes+MotionPayloadReader.RuntimePrefixBytes;
        if(payload.Length>maximum)throw new InvalidDataException($"Motion inspection reads at most {maximum:N0} bytes.");
        var (parsed,error)=await Task.Run<(MotionPayload?,string)>(async()=>{
            await using var stream=await reader.OpenReadAsync(payload,token);
            byte[] bytes=new byte[payload.Length];
            await stream.ReadExactlyAsync(bytes,token);
            try { return (MotionPayloadReader.ReadType9Entry(bytes),""); }
            catch(MotionPayloadException e) { return (null,e.Message); }
        },token);
        token.ThrowIfCancellationRequested();
        if(disposed||generation!=motionGeneration)throw new OperationCanceledException("Motion selection changed.");
        motion=parsed;motionError=error;motionTitle=name;motionFrame=0;
        NotifyMotion();EvaluateMotion();SelectedAssetTab=MotionTab;
        Status=parsed==null?"The type 9 entry is not a readable root motion. See the Motion tab for the reason.":
            "Read the stored root motion offline. Nothing was read from or sent to the game.";
    }
    private async Task LoadContacts(AssetPayload payload,string name,AssetRow? script,CancellationToken token)
    {
        int generation=contactGeneration;ContactDefinitionDocument? parsed=null;string error="";
        try { parsed=await Task.Run(()=>ContactDefinitionReader.ReadAsync(reader,payload,token),token); }
        catch(InvalidDataException e) { error=e.Message; }
        token.ThrowIfCancellationRequested();
        if(disposed||generation!=contactGeneration)throw new OperationCanceledException("Contact selection changed.");
        contacts=parsed;contactsError=error;contactsTitle=name;contactScript=parsed==null?null:script;
        allContactRows=parsed?.Definitions.Select(d=>new ContactDefinitionRow(d)).ToArray()??[];
        RefreshContactRows();NotifyContacts();SelectedAssetTab=ContactsTab;
        Status=parsed==null?"The type 23 entry is not readable as definitions. See the Contact definitions tab for the reason.":
            $"Read {parsed.Count:N0} stored definitions offline. Runtime group overrides are not visible.";
    }
    public Task OpenContactHandlerAsync()
    {
        var script=ContactHandlerScript;if(script?.Payload is not { } payload)return Task.CompletedTask;
        return Run("Reading BDX script…",async token=>{
            ClearScript();
            await LoadScript(payload,script.Name,token,scriptGeneration);
            var handler=ScriptEvents.FirstOrDefault(e=>e.Event.Id==27&&e.Event.IsFirstForId);
            if(handler!=null)SelectedScriptEvent=handler;
            Status=handler==null?"This script declares no Event 27 entry, so it stores no contact handler.":
                $"Event 27 starts at PC {handler.Event.Pc}. This is the stored handler, not proof that it runs.";
        });
    }
}
