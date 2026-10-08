using System.Buffers.Binary;
using System.Globalization;
using System.Text;
using KH2Trainer.Core;

internal static class BdxInspectionTests
{
    private static byte[] Script(params ushort[] words) => ScriptWithEvents([(0, 14)], words, 14);
    private static byte[] ScriptWithEvents((int Id,int Pc)[] events, ushort[] words, int startPc, int terminatorId=0)
    {
        int headerEnd=28+8*(events.Length+1);
        byte[] data=new byte[Math.Max(headerEnd,16+2*(startPc+words.Length))];
        Encoding.ASCII.GetBytes("fixture").CopyTo(data,0);
        Write(data,16,64);Write(data,20,512);Write(data,24,16);
        for(int i=0;i<events.Length;++i) {Write(data,28+8*i,events[i].Id);Write(data,32+8*i,events[i].Pc);}
        Write(data,28+8*events.Length,terminatorId);
        for(int i=0;i<words.Length;++i)BinaryPrimitives.WriteUInt16LittleEndian(data.AsSpan(16+2*(startPc+i)),words[i]);
        return data;
    }
    private static void Write(byte[] b,int at,int value)=>BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(at),value);

    public static async Task RunAsync(string workspace,Action<bool,string> check)
    {
        void Reject<T>(Action action,string text) where T:Exception
        {try {action();check(false,text);}catch(T) {check(true,text);}}
        var d=BdxInspector.Inspect(Script(0x0000,0x008A,0x005F,0x0049,0x008A,0x005F));
        check(d.Header.Name=="fixture"&&d.Header.HeaderEnd==44&&d.Header.Events.Single().Pc==14&&d.Header.Events[0].FileOffset==44,
            "BDX event PC uses signed words from byte16 and ID0 is a regular event");
        check(d.Instructions.Select(i=>i.Pc).SequenceEqual(new[]{14,17})&&d.Instructions[0].Operation=="Push integer"&&d.Instructions[0].WidthInWords==3,
            "BDX immediate bytes and trailing unvisited data are not scanned for traps");
        check(!d.Instructions.Any(i=>i.TrapIndex!=null)&&d.DecodedBytes==8&&d.UndecodedBytes==4,"BDX byte accounting excludes header and counts operands once");
        check(d.Header.NameHex.Length==32&&d.Header.WorkBytes==64&&d.Header.StackBytes==512&&d.Header.TemporaryBytes==16,"BDX raw name and three signed sizes preserved");
        byte[] empty=ScriptWithEvents([], [0x008A,95],10,terminatorId:123);
        d=BdxInspector.Inspect(empty);
        check(d.Header.Events.Count==0&&d.Header.TerminatorId==123&&d.Instructions.Count==0,"BDX terminates on PC0 even with nonzero ID and never invents a code root");
        byte[] duplicate=ScriptWithEvents([(7,18),(7,19)], [0x0049,0x008A,95,0x0049],18);
        d=BdxInspector.Inspect(duplicate);
        check(d.Header.Events.Count==2&&!d.Header.Events[1].IsFirstForId&&d.Instructions.Count==1&&d.Diagnostics.Any(x=>x.Code=="duplicate-event"),"BDX duplicate event IDs retain metadata but only first native lookup becomes a root");

        foreach(var (opcode,width) in new (ushort,int)[]{(0x0000,3),(0x0010,3),(0x0020,2),(0x0030,2),(0x0001,2),(0x0002,3),(0x0003,2),(0x0004,1),
            (0x0085,1),(0x0006,1),(0x0047,2),(0x0088,2),(0x00C9,1),(0x008A,2),(0x008B,3)})
        {
            var words=new ushort[width+1];words[0]=opcode;words[width]=0x0049;
            d=BdxInspector.Inspect(Script(words));
            check(d.Instructions[0].WidthInWords==width,$"BDX native operand width: {opcode:X4}");
        }
        foreach(ushort modeBits in new ushort[]{0,0x10,0x20,0x30})
        {
            d=BdxInspector.Inspect(Script((ushort)(0x008A|modeBits),0xFFFF,0x0049));
            check(d.Instructions[0].TrapBank==2&&d.Instructions[0].TrapIndex==65535&&d.Instructions.Count==2,"BDX trap ignores type bits and keeps unsigned16 index");
            d=BdxInspector.Inspect(Script((ushort)(0x00C9|modeBits),0x0049));
            check(d.Instructions[0].Operation=="Pop"&&d.Instructions.Count==2,"BDX control group ignores type bits");
        }
        d=BdxInspector.Inspect(Script(0xFFCA,0xFFFF,0x0049));
        check(d.Instructions[0].TrapBank==1023,"BDX maximum unsigned opcode bank is preserved without native table assumptions");
        d=BdxInspector.Inspect(Script(0x0007,0xFFFE));
        check(d.Instructions.Count==1&&d.Instructions[0].Edges.Single().TargetPc==14&&!d.HitLimit,"BDX backward loop terminates traversal through visited identities");
        d=BdxInspector.Inspect(Script(0x0047,1,0x0049,0x0049));
        check(d.Instructions.Select(i=>i.Pc).SequenceEqual(new[]{14,16,17})&&d.Instructions[0].Edges.Select(e=>e.Kind).SequenceEqual(new[]{BdxEdgeKind.Branch,BdxEdgeKind.Next}),"BDX conditional branch includes both bounded successors");
        d=BdxInspector.Inspect(Script(0x0088,1,0x0049,0x0089));
        check(d.Instructions.Select(i=>i.Pc).SequenceEqual(new[]{14,16,17})&&d.Instructions[0].Edges[1].Kind==BdxEdgeKind.CallContinuation&&
              d.Instructions.Single(i=>i.Pc==17).Edges.Single()==new BdxFlowEdge(BdxEdgeKind.DynamicReturn,null),"BDX call continuation remains conditional and return has no invented static target");
        d=BdxInspector.Inspect(Script(0x0009,0x0049,0x008A,95));
        check(d.Instructions.Count==2&&d.Instructions[0].Edges.Single().Kind==BdxEdgeKind.YieldResume,"BDX yield has a resume edge while stop has none");
        var farWords=new ushort[65540];farWords[0]=0x008B;farWords[1]=0;farWords[2]=1;farWords[3]=0x0049;farWords[65539]=0x0049;
        d=BdxInspector.Inspect(Script(farWords));
        check(d.Instructions.Select(i=>i.Pc).SequenceEqual(new[]{14,17,65553})&&d.Instructions[0].Edges[0].TargetPc==65553,"BDX 32-bit call target is not truncated to ushort");
        d=BdxInspector.Inspect(Script(0x008B,0xFFFF,0x7FFF,0x0049));
        check(d.Instructions[0].Edges[0].TargetPc==unchecked(17+int.MaxValue)&&d.Diagnostics.Any(x=>x.Code=="target-outside-code"),"BDX far relative addition matches DWORD wrap then signed PC interpretation");
        d=BdxInspector.Inspect(Script(0x008B,0xFFFF,0xFFFF,0x0049));
        check(d.Diagnostics.Any(x=>x.Code=="target-inside-operand")&&d.Instructions.Count==2,"BDX a far-call target inside its own immediate is diagnosed");
        d=BdxInspector.Inspect(Script(0x0007,0xFFF0,0x008A,95));
        check(d.Instructions.Count==1&&d.Diagnostics.Any(x=>x.FileOffset<headerOrZero(d))&&d.Diagnostics.Any(x=>x.Code=="target-outside-code"),"BDX branches into the event header do not decode header bytes");
        static int headerOrZero(BdxDocument doc)=>doc.Header.HeaderEnd;

        foreach(ushort op in new ushort[]{0x0045,0x000C,0x000F,0x0109,0x00C7,0x0156,0x0026,0x0025})
        {
            ushort[] words=(op&15)==7?[op,0,0x008A,95]:[op,0x008A,95];
            d=BdxInspector.Inspect(Script(words));
            check(d.Instructions.Count==1&&d.Instructions[0].Edges.Count==0&&d.Diagnostics.Any(x=>x.Code=="invalid-opcode"),$"BDX native status5 path stops traversal: {op:X4}");
        }
        d=BdxInspector.Inspect(Script(0x0306,0x0049));
        check(d.Instructions[0].Operation=="Keep left operand"&&d.Instructions.Count==2&&d.Diagnostics.Count==0,"BDX integer binary subopcode12 follows native non-error default");
        d=BdxInspector.Inspect(Script(0x0336,0x0049));
        check(d.Instructions.Count==1&&d.Diagnostics.Any(x=>x.Code=="invalid-opcode"),"BDX binary mode3 default is distinct from integer default");
        d=BdxInspector.Inspect(Script(0x0100,0,0,0x0049));
        check(d.Instructions.Count==2&&d.Diagnostics.Count==0,"BDX high bits are ignored for literal immediate group0");
        d=BdxInspector.Inspect(Script(0x0120,0,0x0049));
        check(d.Instructions.Count==2&&d.Diagnostics.Any(x=>x.Code=="invalid-address-selector"),"BDX invalid address selector has a known width and is not silently reinterpreted");
        foreach(ushort op in new ushort[]{0x0130,0x0101,0x0102})
        {
            ushort[] words=(op&15)==2?[op,0,0,0x008A,95,0x0049]:[op,0,0x008A,95,0x0049];
            d=BdxInspector.Inspect(Script(words));
            check(d.Instructions.Count==1&&d.Instructions[0].Edges.Count==0&&d.Diagnostics.Count==1,
                $"BDX null source or destination conservatively ends traversal without claiming a VM status5: {op:X4}");
            check(!d.Diagnostics.Any(x=>x.Code=="invalid-opcode")&&!d.Instructions.Any(x=>x.TrapIndex!=null),
                "BDX invalid native address does not invent a successful continuation or a guaranteed failure for zero-length copy");
        }
        d=BdxInspector.Inspect(Script(0x00C2,4,0,0x0049));
        check(d.Instructions[0].Operands.Contains("retained")&&d.Diagnostics.Any(x=>x.Code=="context-dependent-destination")&&d.Instructions.Count==2,
            "BDX memcpy selector3 preserves native retained-destination distinction and possible continuation");

        var overlap=ScriptWithEvents([(1,18),(2,19)], [0x0000,0x008A,95,0x0049],18);
        d=BdxInspector.Inspect(overlap);
        check(d.Instructions.Count==2&&d.Diagnostics.Any(x=>x.Code=="target-inside-operand")&&!d.Instructions.Any(x=>x.TrapIndex!=null),"BDX cross-entry operand overlap produces a diagnostic instead of a fake trap");
        overlap=ScriptWithEvents([(1,19),(2,18)], [0x0000,0x0049,0,0x0049],18);
        d=BdxInspector.Inspect(overlap);
        check(d.Instructions.Count==1&&d.Diagnostics.Any(x=>x.Code=="overlapping-instructions"),"BDX reverse traversal order detects an instruction covering an existing root");
        d=BdxInspector.Inspect(Script(0x0000,0x1234));
        check(d.Instructions.Count==0&&d.Diagnostics.Single().Code=="truncated-instruction","BDX truncated operand is not a complete instruction");
        byte[] negative=Script(0x0049);Write(negative,16,-1);negative[0]=1;
        d=BdxInspector.Inspect(negative);
        check(d.Header.WorkBytes==-1&&d.Header.Name.StartsWith("\\x01")&&d.Diagnostics.Any(x=>x.Code=="negative-size")&&d.Instructions.Count==1,"BDX invalid execution sizes and raw name bytes remain inspectable");
        d=BdxInspector.Inspect([..Script(0x0049),0xAA]);
        check(d.Diagnostics.Any(x=>x.Code=="odd-length")&&d.UndecodedBytes==1,"BDX odd tail byte remains unvisited");

        Reject<InvalidDataException>(()=>BdxInspector.Inspect(new byte[35]),"BDX incomplete minimum header rejected");
        byte[] noTerminator=Script(0x0049);Write(noTerminator,40,14);
        Reject<InvalidDataException>(()=>BdxInspector.Inspect(noTerminator),"BDX missing event-table terminator rejected");
        Reject<InvalidDataException>(()=>BdxInspector.Inspect(duplicate,new(){MaximumEvents=1}),"BDX event limit bounds hostile metadata");
        Reject<InvalidDataException>(()=>BdxInspector.Inspect(Script(0x0049),new(){MaximumBytes=36}),"BDX file bound enforced before copying input");
        Reject<ArgumentOutOfRangeException>(()=>BdxInspector.Inspect(Script(0x0049),new(){MaximumInstructions=0}),"BDX nonsensical limits rejected");
        using(var cancelled=new CancellationTokenSource()) { cancelled.Cancel();Reject<OperationCanceledException>(()=>BdxInspector.Inspect(Script(0x0049),cancellationToken:cancelled.Token),"BDX pre-cancellation observed"); }
        d=BdxInspector.Inspect(Script(0x00C9,0x00C9,0x0049),new(){MaximumInstructions=1});
        check(d.Instructions.Count==1&&d.HitLimit&&d.Diagnostics.Single().Code=="instruction-limit","BDX traversal limit produces explicit partial result");
        var badRoots=ScriptWithEvents([(0,-1),(1,-2),(2,int.MaxValue)],[],0);
        d=BdxInspector.Inspect(badRoots,new(){MaximumDiagnostics=1});
        check(d.Diagnostics.Count==1&&d.SuppressedDiagnostics==2&&d.Instructions.Count==0,"BDX diagnostic cap accounts for suppressed invalid roots");
        var priorCulture=CultureInfo.CurrentCulture;
        try { CultureInfo.CurrentCulture=CultureInfo.GetCultureInfo("de-DE");d=BdxInspector.Inspect(Script(0x0010,0,0x3FA0,0x0049));
            check(d.Instructions[0].Operands.StartsWith("1.25 (0x3FA00000)"),"BDX float formatting is invariant and preserves original bits"); }
        finally {CultureInfo.CurrentCulture=priorCulture;}

        string path=Path.Combine(workspace,"fixture.bdx");byte[] source=Script(0x008A,95,0x0049);await File.WriteAllBytesAsync(path,source);
        var reader=new AssetArchiveReader();var payload=reader.OpenLooseFile(path);
        d=await BdxInspector.ReadAsync(reader,payload);
        check(d.Instructions[0].TrapIndex==95&&File.ReadAllBytes(path).SequenceEqual(source),"BDX bounded asset reader opens file without changing content");
        File.AppendAllText(path,"changed");
        try {await BdxInspector.ReadAsync(reader,payload);check(false,"BDX stale source identity rejected");}
        catch(IOException) {check(true,"BDX stale source identity rejected");}
    }
}
