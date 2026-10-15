using System.Buffers.Binary;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using KH2Trainer;
using KH2Trainer.Core;

internal static class BdxInspectionUiChecks
{
    private static int checks;
    private static void Check(bool condition,string message)
    { checks++;if(!condition)throw new InvalidDataException(message); }
    private static void Await(Task task)
    {
        if(!task.IsCompleted) {
            var dispatcher=Dispatcher.CurrentDispatcher;var frame=new DispatcherFrame();
            _=task.ContinueWith(_=>dispatcher.BeginInvoke(new Action(()=>frame.Continue=false)),TaskScheduler.Default);
            Dispatcher.PushFrame(frame);
        }
        task.GetAwaiter().GetResult();
    }
    private static void Reject<T>(Func<Task> action,string message) where T:Exception
    { try {Await(action());throw new InvalidOperationException("Expected rejection: "+message);}catch(T){checks++;} }
    public static object Run(string output,Application app)
    {
        checks=0;output=Path.GetFullPath(output);Directory.CreateDirectory(output);
        var log=new StringWriter();var listener=new TextWriterTraceListener(log);
        PresentationTraceSources.DataBindingSource.Listeners.Add(listener);
        var previous=SynchronizationContext.Current;
        SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext());
        try {
            byte[] script=Script();string loose=Path.Combine(output,"sample.bdx"),unknown=Path.Combine(output,"unknown.bin"),bar=Path.Combine(output,"scripts.bar");
            File.WriteAllBytes(loose,script);File.WriteAllBytes(unknown,script);
            File.WriteAllBytes(bar,Bar([(3,"scpt",script),(1,"data",new byte[24])]));
            using var vm=new AssetExplorerViewModel(_=>{});
            Check(!vm.InspectScriptCommand.CanExecute(null)&&!vm.HasScript,"empty inspector disables action");
            Await(vm.OpenFileAsync(loose));
            Check(vm.HasScript&&vm.SelectedAssetTab==2&&vm.ScriptEvents.Count==2,"loose BDX opens Script tab automatically");
            Check(vm.ScriptRows.Count==1003&&vm.ScriptTitle=="sample.bdx","all followed instructions are exposed");
            Check(vm.ScriptInstructionDetails.Contains("431A70")&&vm.ScriptInstructionDetails.Contains("Declared operands: 3")&&
                vm.ScriptInstructionDetails.Contains("+4")&&vm.ScriptInstructionDetails.Contains("third declared operand is unused"),"selected trap details preserve verified native metadata");
            Check(vm.ScriptScope.Contains("stored values")&&vm.ScriptScope.Contains("conditional"),"scope distinguishes stored code and conditional execution");
            var view=new AssetExplorerView {DataContext=vm};var panel=Panel(view,app);
            Render(panel,output,"script-780.png");
            var tabs=(TabControl)view.FindName("AssetTabs");var list=(ListBox)view.FindName("ScriptInstructions");
            var picker=(ComboBox)view.FindName("ScriptEventPicker");
            Check(tabs.Items.Count==5&&tabs.SelectedIndex==2,"Script is the bound third tab");
            Check(VisualChildren<ListBoxItem>(list).Count()<50,"large script realizes only a bounded viewport");
            Check(VirtualizingPanel.GetIsVirtualizing(list)&&VirtualizingPanel.GetVirtualizationMode(list)==VirtualizationMode.Recycling,"script uses recycling virtualization");
            Check(((TextBox)view.FindName("ScriptInstructionDetails")).IsReadOnly&&((TextBox)view.FindName("ScriptDiagnostics")).IsReadOnly,"details and diagnostics are selectable read-only text");
            vm.ScriptFilter="Actor STATUS rebind";
            Check(vm.ScriptRows.Count==2,"descriptive native name filters both rebind adapters");
            vm.ScriptFilter="2:95";
            Check(vm.ScriptRows.Count==1&&vm.ScriptRows[0].Instruction.TrapIndex==95&&vm.SelectedScriptInstruction==null,"filter finds native call and clears stale selection");
            vm.SelectedScriptInstruction=vm.ScriptRows[0];
            Check(vm.ScriptInstructionDetails.Contains("431AA0")&&vm.ScriptInstructionDetails.Contains("Declared operands: 2")&&
                vm.ScriptInstructionDetails.Contains("4112B0")&&vm.ScriptInstructionDetails.Contains("bdx-rebind-operands-20261008"),"second trap details are updated with catalog evidence");
            vm.ScriptFilter="___no_instruction___";
            Check(vm.ScriptRows.Count==0&&!vm.ScriptInstructionDetails.Contains("431AA0"),"empty search clears old details");
            picker.SelectedItem=vm.ScriptEvents[1];Settle(panel);
            Check(vm.ScriptFilter==""&&vm.SelectedScriptInstruction?.Instruction.Pc==2020,"event picker clears filter and selects entry PC");
            var selected=(ListBoxItem?)list.ItemContainerGenerator.ContainerFromItem(vm.SelectedScriptInstruction!);
            Check(selected!=null,"event navigation realizes distant selected row; selected="+((BdxInstructionRow?)list.SelectedItem)?.PcText+
                "; rows="+list.Items.Count+"; scroll="+string.Join("/",VisualChildren<ScrollViewer>(list).Select(s=>$"{s.VerticalOffset}:{s.ExtentHeight}:{s.ViewportHeight}")));
            if(selected!=null) {
                var bounds=selected.TransformToAncestor(list).TransformBounds(new Rect(selected.RenderSize));
                Check(bounds.Bottom>0&&bounds.Top<list.ActualHeight,"event navigation scrolls selected row into viewport");
            }
            ((Expander)view.FindName("ScriptDiagnosticsExpander")).IsExpanded=true;
            Render(panel,output,"script-event-780.png");
            tabs.SelectedIndex=0;Check(vm.SelectedAssetTab==0,"tab selection flows back to viewmodel");
            Check(((Button)view.FindName("InspectBdxButton")).Command==vm.InspectScriptCommand,"explicit inspection button uses script command");
            Await(vm.OpenFileAsync(unknown));
            Check(!vm.HasScript&&vm.ScriptRows.Count==0&&vm.SelectedAssetTab==0,"unknown binary stays in Browse with no old script");
            Check(vm.InspectScriptCommand.CanExecute(null),"unknown selected payload supports explicit BDX inspection");
            Await(vm.InspectScriptAsync());
            Check(vm.HasScript&&vm.SelectedAssetTab==2&&vm.ScriptTitle=="unknown.bin","explicit inspection decodes unknown binary");
            bool cancelled=false;
            System.ComponentModel.PropertyChangedEventHandler cancelWhenBusy=(_,e)=>{
                if(e.PropertyName==nameof(vm.Busy)&&vm.Busy&&!cancelled) {
                    cancelled=true;Check(!vm.InspectScriptCommand.CanExecute(null)&&vm.CancelCommand.CanExecute(null),"busy inspection exposes only cancellation");
                    vm.CancelCommand.Execute(null);
                }
            };
            vm.PropertyChanged+=cancelWhenBusy;
            try {Await(vm.InspectScriptAsync());}finally {vm.PropertyChanged-=cancelWhenBusy;}
            Check(cancelled&&!vm.HasScript&&!vm.Busy&&vm.Status.Contains("cancelled"),"cancelled decode publishes no script and releases busy state");
            Await(vm.OpenFileAsync(bar));
            Check(!vm.HasScript&&vm.SelectedAssetTab==0,"opening container clears script state");
            vm.SelectedRow=vm.Rows[0];Task pending=vm.InspectScriptAsync();vm.SelectedRow=vm.Rows[1];Await(pending);
            Check(!vm.HasScript&&vm.SelectedRow==vm.Rows[1]&&!vm.Busy,"selection replacement cannot publish the old pending script");
            vm.SelectedRow=vm.Rows[0];Await(vm.InspectSelectedAsync());
            Check(vm.HasScript&&vm.SelectedAssetTab==2&&vm.ScriptTitle.Contains("scpt"),"BAR type3 opens script automatically");
            Check(vm.SelectedRow!.IsBdxScript,"type3 context survives navigation into its synthetic .bin name");
            Await(vm.InspectSelectedAsync());Check(vm.HasScript,"reopening a type3 payload preserves explicit script context");
            vm.BackCommand.Execute(null);
            Check(!vm.HasScript&&vm.ScriptEvents.Count==0&&vm.ScriptRows.Count==0,"back clears all script rows and events");
            vm.SelectedRow=vm.Rows[1];
            Reject<InvalidDataException>(()=>vm.InspectScriptAsync(),"invalid selected binary");
            Check(!vm.HasScript&&!vm.Busy&&vm.ScriptInstructionDetails.StartsWith("Choose an instruction"),"failed inspection cannot expose a prior script");
            Render(panel,output,"script-error-780.png");
            Await(vm.OpenFileAsync(loose));
            vm.Filter="___no_asset___";
            Check(vm.SelectedRow==null&&!vm.HasScript&&!vm.InspectScriptCommand.CanExecute(null),"filtering away asset clears script and command admission");
            Await(vm.OpenFileAsync(loose));
            Reject<FileNotFoundException>(()=>vm.OpenFileAsync(Path.Combine(output,"missing.bdx")),"missing new source");
            Check(!vm.HasScript&&vm.ScriptRows.Count==0&&!vm.Busy,"new-source failure clears old script");
            byte[] disguised=(byte[])script.Clone();"BAR\x01"u8.CopyTo(disguised);
            string disguisedLoose=Path.Combine(output,"bar-name.bdx"),disguisedBar=Path.Combine(output,"bar-name.bar");
            File.WriteAllBytes(disguisedLoose,disguised);File.WriteAllBytes(disguisedBar,Bar([(3,"name",disguised)]));
            Await(vm.OpenFileAsync(disguisedLoose));Check(vm.HasScript&&vm.SelectedRow!.Kind=="BDX script",".bdx context takes priority over BAR-like name bytes");
            Await(vm.OpenFileAsync(disguisedBar));vm.SelectedRow=vm.Rows[0];Await(vm.InspectSelectedAsync());
            Check(vm.HasScript&&vm.ScriptSummary.StartsWith("BAR"),"BAR type3 context takes priority over BAR-like name bytes");
            string hedPath=Path.Combine(output,"scripts.hed");int stored=16+((script.Length+15)&~15);
            byte[] record=new byte[stored];BinaryPrimitives.WriteInt32LittleEndian(record,script.Length);
            BinaryPrimitives.WriteInt32LittleEndian(record.AsSpan(8),-2);script.CopyTo(record,16);
            byte[] hed=new byte[64];for(int i=0;i<2;i++) {
                BinaryPrimitives.WriteInt32LittleEndian(hed.AsSpan(i*32+24),stored);
                BinaryPrimitives.WriteInt32LittleEndian(hed.AsSpan(i*32+28),script.Length);
            }
            File.WriteAllBytes(hedPath,hed);File.WriteAllBytes(Path.ChangeExtension(hedPath,".pkg"),record);
            Await(vm.OpenPackageIndexAsync(hedPath));vm.SelectedRow=vm.Rows[0];pending=vm.InspectScriptAsync();vm.SelectedRow=vm.Rows[1];Await(pending);
            Check(!vm.HasScript&&vm.SelectedRow==vm.Rows[1]&&!vm.Busy,"replacement during package resolution cannot publish old script");
            Await(vm.InspectScriptAsync());Check(vm.HasScript&&vm.ScriptRows.Count==1003,"explicit HED inspection reads the selected original script payload");
            byte[] badHeader=new byte[35];File.WriteAllBytes(Path.Combine(output,"truncated.bdx"),badHeader);
            Reject<InvalidDataException>(()=>vm.OpenFileAsync(Path.Combine(output,"truncated.bdx")),"truncated BDX file");
            Check(!vm.HasScript&&vm.ScriptDiagnostics==""&&!vm.Busy,"auto-inspection failure clears old diagnostics and busy state");
            CheckNativeCatalog(output,app);
            CheckExpandedCatalog(output,app);
            CheckBankInventory(output,app);
            CheckEventRolesAndText(output,app);
            CheckMotionAndContacts(output,app);
            CheckEmptyContactScript(output,app);
            Settle(panel);Check(log.ToString().Length==0,"BDX WPF binding errors: "+log);
            Check(app.Windows.Count==0&&app.MainWindow==null,"offscreen checks create no windows");
            Check(File.ReadAllBytes(loose).SequenceEqual(script)&&File.ReadAllBytes(unknown).SequenceEqual(script),"inspection preserves source bytes");
            var report=new {success=true,checks,renders=12,width=780,bindingErrors=0,windowCount=app.Windows.Count,
                renderFiles=new[]{"script-780.png","script-event-780.png","script-error-780.png","script-native-catalog-780.png","script-native-context-780.png","script-native-equipment-780.png","script-native-banks-780.png","script-native-query-780.png","script-events-780.png",
                    "motion-780.png","motion-error-780.png","contacts-780.png"},
                scope="Actual BDX, Motion and Contacts views and viewmodel, synthetic loose/BAR/unknown payloads, native catalog labels/details/search, null and context-dependent metadata, conditional event roles, stored text operands, RAW/Prototype/invalid type 9 entries, frame slider, B_LK120-shaped type 23 definitions with the Event 27 script link, empty and too-short type 3 entries beside them, long-name wrapping, event scrolling, virtualization, cancellation, replaced selection, failures and dark offscreen rendering. No window, script execution, game, input or process attachment."};
            File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(report,new JsonSerializerOptions {WriteIndented=true}));return report;
        }
        finally {
            SynchronizationContext.SetSynchronizationContext(previous);
            PresentationTraceSources.DataBindingSource.Listeners.Remove(listener);listener.Dispose();
        }
    }
    private static void CheckNativeCatalog(string output,Application app)
    {
        (int Bank,int Index)[] calls=[(0,16),(0,7),(0,9),(0,10),(9,0),(3,179),(11,1023),(0,105)];
        var words=calls.SelectMany(c=>new ushort[]{(ushort)((c.Bank<<6)|10),(ushort)c.Index}).Append((ushort)0x49).ToArray();
        byte[] bytes=new byte[44+words.Length*2];"Native catalog"u8.CopyTo(bytes);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(20),128);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(24),128);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(32),14);
        for(int n=0;n<words.Length;n++)BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(44+n*2),words[n]);
        string path=Path.Combine(output,"native-catalog.bdx");File.WriteAllBytes(path,bytes);
        using var vm=new AssetExplorerViewModel(_=>{});Await(vm.OpenFileAsync(path));
        Check(vm.ScriptRows.Count==9,"catalog metadata does not change decoded instructions");
        var rows=vm.ScriptRows.ToArray();
        Check(rows[0].NativeCall=="0:16 · Random integer"&&rows[1].NativeCall=="0:7 · Normalize vector and retain length","annotated calls show bank:index and descriptive name");
        Check(rows[2].NativeCall=="0:9 · Create child VM context"&&rows[2].NativeInfo?.DescriptorState==BdxNativeDescriptorState.Present,"new child context annotation reaches its native row");
        Check(rows[3].NativeCall=="0:10"&&rows[3].Details.Contains("NULL handler")&&rows[3].Details.Contains("does not terminate"),"null descriptor hole stays explicit in details");
        Check(rows[4].NativeCall=="9:0 · Create OBJ3D model object"&&rows[4].NativeInfo?.HasAnnotation==true&&rows[4].Details.Contains("Context-dependent bank")&&rows[4].Details.Contains("original registry slot is NULL"),"annotated context bank retains its conditional registration state");
        Check(rows[5].NativeInfo?.BankState==BdxNativeBankState.ContextInstalled&&rows[5].Details.Contains("not been catalogued"),"known context bank can have an uncatalogued descriptor");
        Check(rows[6].NativeCall=="11:1023"&&rows[6].Details.Contains("runtime state is unknown"),"unknown bank:index preserves its stored identity");
        Check(rows[7].NativeCall=="0:105"&&rows[7].Details.Contains("not been catalogued"),"outside catalog extent is not labeled invalid");
        Check(rows[8].NativeInfo==null&&rows[8].NativeCall==""&&!rows[8].Details.Contains("Native call"),"ordinary instruction has no fabricated native metadata");
        var view=new AssetExplorerView {DataContext=vm};var panel=Panel(view,app);Render(panel,output,"script-native-catalog-780.png");
        var list=(ListBox)view.FindName("ScriptInstructions");
        var label=VisualChildren<TextBlock>(list).Single(t=>t.Text==rows[1].NativeCall);
        var bounds=label.TransformToAncestor(list).TransformBounds(new Rect(label.RenderSize));
        Check(label.TextWrapping==TextWrapping.Wrap&&label.TextTrimming==TextTrimming.None&&
            bounds.Left>=0&&bounds.Right<=list.ActualWidth+1,"long native name wraps within the instruction column without clipping");
        Check(VisualChildren<ScrollViewer>(list).All(s=>s.ScrollableWidth<1),"native labels do not add horizontal scrolling");
        vm.ScriptFilter="rAnDoM InTeGeR";
        Check(vm.ScriptRows.Count==1&&vm.ScriptRows[0].Instruction.TrapIndex==16,"native names are searchable without case sensitivity");
        vm.SelectedScriptInstruction=vm.ScriptRows[0];Settle(panel);
        var details=(TextBox)view.FindName("ScriptInstructionDetails");
        Check(details.Text.Contains("Declared operands: 1")&&details.Text.Contains("VM return slot: yes")&&details.Text.Contains("Evidence:"),"selected native metadata reaches the bound read-only details control");
        Check(details.Height==180&&details.VerticalScrollBarVisibility==ScrollBarVisibility.Auto,"expanded metadata uses the existing bounded scroll area");
        vm.ScriptFilter="69069";
        Check(vm.ScriptRows.Count==1&&vm.ScriptRows[0].Instruction.TrapIndex==16,"native summary terms are searchable alongside names");
        vm.ScriptFilter="ContextInstalled";
        Check(vm.ScriptRows.Count==2&&vm.ScriptRows.All(r=>r.Instruction.TrapBank is 3 or 9)&&vm.SelectedScriptInstruction==null,"catalog search terms find context-dependent state and clear old selection");
        vm.SelectedScriptInstruction=vm.ScriptRows.Single(r=>r.Instruction.TrapBank==9);Render(panel,output,"script-native-context-780.png");
        Check(File.ReadAllBytes(path).SequenceEqual(bytes),"catalog inspection preserves synthetic script bytes");
    }
    private static void CheckExpandedCatalog(string output,Application app)
    {
        (int Bank,int Index)[] calls=[(0,76),(0,52),(0,62),(0,31),(0,9),(0,90),(2,9)];
        var words=calls.SelectMany(c=>new ushort[]{(ushort)((c.Bank<<6)|10),(ushort)c.Index}).Append((ushort)0x49).ToArray();
        byte[] bytes=new byte[44+words.Length*2];"Equipment"u8.CopyTo(bytes);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(20),128);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(24),128);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(32),14);
        for(int n=0;n<words.Length;n++)BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(44+n*2),words[n]);
        string path=Path.Combine(output,"equipment-catalog.bdx");File.WriteAllBytes(path,bytes);
        using var vm=new AssetExplorerViewModel(_=>{});Await(vm.OpenFileAsync(path));
        Check(vm.ScriptRows.Count==8&&vm.ScriptRows.Take(7).All(r=>r.NativeInfo?.HasAnnotation==true),"new metadata does not alter the decoded native-call sequence");
        var view=new AssetExplorerView {DataContext=vm};var panel=Panel(view,app);
        vm.ScriptFilter="Keyblade";
        Check(vm.ScriptRows.Count==1&&vm.ScriptRows[0].Instruction.TrapIndex==76,"form equipment is searchable by its purpose");
        vm.SelectedScriptInstruction=vm.ScriptRows[0];Settle(panel);
        var details=(TextBox)view.FindName("ScriptInstructionDetails");
        Check(details.Text.Contains("Set Drive Form Keyblade")&&details.Text.Contains("validated fallback")&&details.Text.Contains("not checked"),"weapon details expose the raw script write and separate trainer validation");
        Render(panel,output,"script-native-equipment-780.png");
        vm.ScriptFilter="";vm.SelectedScriptInstruction=vm.ScriptRows.Single(r=>r.Instruction.TrapIndex==90);
        Check(vm.ScriptInstructionDetails.Contains("Declared operands: 5")&&vm.ScriptInstructionDetails.Contains("discarded")&&vm.ScriptInstructionDetails.Contains("NaN"),"discarded transform still exposes input mutation and declared arity");
        vm.ScriptFilter="self-link";
        Check(vm.ScriptRows.Count==1&&vm.ScriptRows[0].Instruction.TrapBank==2,"new Actor self-link evidence reaches metadata search");
        vm.ScriptFilter="cleanup";
        Check(vm.ScriptRows.Any(r=>r.Instruction.TrapIndex==52),"effect cleanup notes participate in search");
        Check(File.ReadAllBytes(path).SequenceEqual(bytes),"expanded inspection preserves its source bytes");
    }
    private static void CheckBankInventory(string output,Application app)
    {
        (int Bank,int Index)[] calls=[(1,103),(2,0),(3,0),(4,25),(9,9),(9,25),(9,32),(1,367),(2,97),(1,8)];
        var words=calls.SelectMany(c=>new ushort[]{(ushort)((c.Bank<<6)|10),(ushort)c.Index}).Append((ushort)0x49).ToArray();
        byte[] bytes=new byte[44+words.Length*2];"Bank inventory"u8.CopyTo(bytes);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(20),128);BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(24),128);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(32),14);
        for(int n=0;n<words.Length;n++)BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(44+n*2),words[n]);
        string path=Path.Combine(output,"bank-inventory.bdx");File.WriteAllBytes(path,bytes);
        using var vm=new AssetExplorerViewModel(_=>{});Await(vm.OpenFileAsync(path));var rows=vm.ScriptRows.ToArray();
        Check(rows.Length==11,"all-bank metadata preserves decoded instruction count");
        Check(rows[0].NativeCall=="1:103 · Empty native handler"&&rows[0].NativeInfo?.DescriptorState==BdxNativeDescriptorState.Present,"RET-only body displays as a real handler");
        Check(rows[1].NativeCall=="2:0"&&rows[1].NativeInfo?.HasAnnotation==false&&rows[1].Details.Contains("0x431B10"),"structural metadata does not invent a semantic name");
        Check(rows[2].NativeInfo?.DescriptorState==BdxNativeDescriptorState.Present&&rows[2].NativeInfo?.BankState==BdxNativeBankState.ContextInstalled,"new bank3 record retains registration caveat");
        Check(rows[3].Details.Contains("0x433830")&&rows[3].NativeInfo?.DeclaredOperandCount==1,"branch-stub handler is shown despite missing IDA function entry");
        Check(rows[4].NativeInfo?.DeclaredOperandCount==6&&rows[4].Details.Contains("6..15"),"scratch-copy note is shown without changing stored arity");
        var view=new AssetExplorerView {DataContext=vm};var panel=Panel(view,app);Render(panel,output,"script-native-banks-780.png");
        vm.ScriptFilter="cooperative yield";
        Check(vm.ScriptRows.Count==1&&vm.ScriptRows[0].Instruction.TrapBank==9&&vm.ScriptRows[0].Instruction.TrapIndex==25,"group rebuild count semantics are searchable");
        vm.ScriptFilter="radians";vm.SelectedScriptInstruction=vm.ScriptRows.Single();Settle(panel);
        Check(vm.SelectedScriptInstruction.Instruction.TrapIndex==32&&vm.ScriptInstructionDetails.Contains("horizontal")&&vm.ScriptInstructionDetails.Contains("vertical"),"camera FOV search exposes mode semantics");
        vm.ScriptFilter="2^31";vm.SelectedScriptInstruction=vm.ScriptRows.Single();Settle(panel);
        Check(vm.SelectedScriptInstruction.Instruction.TrapBank==1&&vm.SelectedScriptInstruction.Instruction.TrapIndex==367,"scalar progress boundary is searchable");
        Check(vm.ScriptInstructionDetails.Contains("success byte")&&vm.ScriptInstructionDetails.Contains("does not guarantee a fresh result"),"query details expose discarded status and shared-output limitations");
        Render(panel,output,"script-native-query-780.png");
        Check(File.ReadAllBytes(path).SequenceEqual(bytes),"expanded bank inspection preserves source bytes");
    }
    private static void CheckEventRolesAndText(string output,Application app)
    {
        // Events 0, 10, 27, an unknown ID and a shadowed duplicate; event 0 pushes the stored name at PC 41.
        (int Id,int Pc)[] events=[(0,30),(10,33),(27,36),(99,39),(10,40)];
        ushort[] words=[0x00E0,41,0x0049,0x004A,15,0x0049,0x004A,87,0x0049,0x0049,0x0049,0x656C,0x7661,0x0065];
        byte[] bytes=new byte[16+2*(30+words.Length)];"Event roles"u8.CopyTo(bytes);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(16),128);BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(20),512);
        for(int i=0;i<events.Length;i++) {
            BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(28+8*i),events[i].Id);BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(32+8*i),events[i].Pc);
        }
        for(int n=0;n<words.Length;n++)BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(76+n*2),words[n]);
        string path=Path.Combine(output,"event-roles.bdx");File.WriteAllBytes(path,bytes);
        using var vm=new AssetExplorerViewModel(_=>{});Await(vm.OpenFileAsync(path));
        Check(vm.ScriptRows.Count==7&&vm.ScriptEvents.Count==5,"event-role fixture decodes every first entry and keeps the shadowed row");
        string[] labels=vm.ScriptEvents.Select(e=>e.Label).ToArray();
        Check(labels[0]=="Event 0 → PC 30 · Actor setup, if Actor-bound"&&labels[1]=="Event 10 → PC 33 · Native message, if delivered"&&
            labels[2]=="Event 27 → PC 36 · Contact hit, if delivered","known event IDs carry conditional role labels");
        Check(labels[3]=="Event 99 → PC 39"&&labels[4]=="Event 10 → PC 40 (shadowed by first entry)","unknown and shadowed entries get no invented role");
        var view=new AssetExplorerView {DataContext=vm};var panel=Panel(view,app);Settle(panel);
        var details=(TextBlock)view.FindName("ScriptEventDetails");
        Check(vm.SelectedScriptEvent==vm.ScriptEvents[0]&&details.Text==vm.ScriptEventDetails&&details.Text.Contains("@ADR")&&
            details.Text.Contains("native call convention, not proof this handler runs"),"first event details reach the bound text with the scope wording");
        ((ComboBox)view.FindName("ScriptEventPicker")).SelectedItem=vm.ScriptEvents[2];Settle(panel);
        Check(details.Text.Contains("record, ID, Actor")&&details.Text.Contains("motion-event27-20261008")&&vm.SelectedScriptInstruction?.Instruction.Pc==36,
            "event picker shows the selected role details and jumps to its entry");
        vm.SelectedScriptEvent=vm.ScriptEvents[3];
        Check(vm.ScriptEventDetails.Contains("no catalogued native caller")&&vm.ScriptEventDetails.Contains("not proof this handler runs"),"unknown event details admit the unknown caller");
        vm.SelectedScriptEvent=vm.ScriptEvents[4];
        Check(vm.ScriptEventDetails.Contains("shadowed")&&vm.SelectedScriptInstruction==null,"shadowed event details explain native lookup");
        vm.ScriptFilter="LEAVE";
        Check(vm.ScriptRows.Count==1&&vm.ScriptRows[0].Operands=="script PC 41 · stored bytes as text: \"leave\""&&vm.ScriptRows[0].Instruction.StoredText=="leave",
            "stored string operand is shown and searchable without case sensitivity");
        vm.SelectedScriptInstruction=vm.ScriptRows[0];
        Check(vm.ScriptInstructionDetails.Contains("stored bytes as text")&&vm.ScriptInstructionDetails.Contains("decides how they are used"),"stored text details keep their limitation");
        vm.ScriptFilter="3B6670";vm.SelectedScriptInstruction=vm.ScriptRows.Single();Settle(panel);
        Check(vm.SelectedScriptInstruction.NativeCall=="1:87 · Call Actor helper RVA 0x3B6670"&&vm.ScriptInstructionDetails.Contains("unresolved")&&
            vm.ScriptInstructionDetails.Contains("Declared operands: 4"),"Event27 helper names only its operand ABI");
        vm.ScriptFilter="logical motion";
        Check(vm.ScriptRows.Count==1&&vm.ScriptRows[0].NativeCall=="1:15 · Read DWORD at decoded operand +384","inferred +384 meaning is searchable but not the call name");
        vm.ScriptFilter="";Render(panel,output,"script-events-780.png");
        Check(File.ReadAllBytes(path).SequenceEqual(bytes),"event-role inspection preserves source bytes");
    }
    private static void CheckMotionAndContacts(string output,Application app)
    {
        static string Row(int row,params string[] values)=>(row==3?"row 3 (translation)":$"row {row}").PadRight(21)+string.Concat(values.Select(v=>v.PadLeft(15)));
        string path=Path.Combine(output,"B_LK120-shaped.mdlx");
        byte[] bytes=Bar([(3,"scpt",ContactScript()),(9,"raw ",MotionEntry(RawMotion())),(9,"prot",MotionEntry(PrototypeMotion())),
            (9,"bad ",MotionEntry([7,0,0,0])),(23,"coll",Lk120Definitions()),(23,"tiny",new byte[40])]);
        File.WriteAllBytes(path,bytes);
        using var vm=new AssetExplorerViewModel(_=>{});
        var view=new AssetExplorerView {DataContext=vm};var panel=Panel(view,app);Settle(panel);
        var tabs=(TabControl)view.FindName("AssetTabs");var slider=(Slider)view.FindName("MotionFrameSlider");
        var scope=(TextBlock)view.FindName("MotionScope");var error=(Border)view.FindName("MotionErrorBanner");
        Check(tabs.Items.Count==5&&tabs.Items.IndexOf(view.FindName("MotionTab"))==3&&tabs.Items.IndexOf(view.FindName("ContactsTab"))==4,"Motion and Contacts are the fourth and fifth tabs");
        tabs.SelectedIndex=3;Settle(panel);
        Check(vm.SelectedAssetTab==3&&!vm.HasMotion&&!slider.IsEnabled&&scope.Text.Contains("Offline projection, not native safety")&&scope.Text.Contains("OfflineMotionProjection")&&
            scope.Visibility==Visibility.Visible&&((FrameworkElement)scope.Parent).Visibility==Visibility.Visible,"motion scope label is shown before any motion is opened");
        Await(vm.OpenFileAsync(path));var rows=vm.Rows.ToArray();
        Check(rows[1].IsMotion&&rows[1].Kind=="Motion"&&rows[4].IsContactDefinitions&&rows[4].Kind=="Collision/contact definitions"&&rows[0].BarType==3&&!rows[0].IsMotion,
            "BAR rows keep their type for the motion and contact viewers");
        vm.SelectedRow=rows[1];Await(vm.InspectSelectedAsync());Settle(panel);
        Check(vm.HasMotion&&vm.SelectedAssetTab==3&&tabs.SelectedIndex==3&&vm.MotionSummary=="RAW format · root motion present · 0 time keys · 2 RAW matrix frames",
            "RAW type 9 entry opens the Motion tab with its format and counts");
        Check(vm.SelectedRow!.IsMotion&&vm.SelectedRow.Kind=="Motion","type 9 context survives navigation into its payload");
        Check(vm.MotionFrame==0&&vm.MotionSampleText.Contains("RAW frames 0 → 1, fraction 0")&&vm.MotionSampleText.Contains(Row(3,"0","0","0","1")),
            "frame 0 evaluates the first stored RAW matrix");
        Check(slider.Maximum==vm.MotionFrameMaximum&&slider.IsSnapToTickEnabled&&slider.IsEnabled&&error.Visibility==Visibility.Collapsed,"frame slider spans the bounded frame range");
        slider.Value=1;Settle(panel);
        Check(vm.MotionFrame==1&&vm.MotionSampleText.Contains("RAW frames 1 → 0")&&vm.MotionSampleText.Contains(Row(3,"10","0","0","3"))&&
            ((TextBox)view.FindName("MotionSample")).Text==vm.MotionSampleText,"slider evaluates the root matrix at the chosen frame");
        vm.MotionFrame=1e9;Settle(panel);
        Check(vm.MotionFrame==vm.MotionFrameMaximum&&slider.Value==vm.MotionFrameMaximum&&vm.MotionFrameText=="Frame 600 of 600"&&vm.MotionSampleText.Contains("RAW frames 1 → 0"),
            "frame input is clamped to the slider range and RAW evaluation clamps to its last frame");
        vm.MotionFrame=double.NaN;Check(vm.MotionFrame==vm.MotionFrameMaximum,"nonfinite frame input is ignored");
        Render(panel,output,"motion-780.png");
        vm.BackCommand.Execute(null);
        Check(!vm.HasMotion&&vm.MotionSampleText==""&&vm.SelectedAssetTab==0,"back clears the motion inspection");
        vm.SelectedRow=vm.Rows[2];Await(vm.InspectSelectedAsync());
        Check(vm.MotionSummary=="Prototype format · root motion present · 2 time keys · 0 RAW matrix frames"&&vm.MotionSampleText.Contains("effective frame 0")&&
            vm.MotionSampleText.Contains(Row(3,"5","0","0","1"))&&!vm.MotionSampleText.Contains("RAW frames"),"Prototype root channels evaluate through the reviewed evaluator");
        vm.BackCommand.Execute(null);vm.SelectedRow=vm.Rows[3];Await(vm.InspectSelectedAsync());Settle(panel);
        Check(!vm.HasMotion&&vm.HasMotionError&&vm.MotionError.Contains("Unsupported type9 motion kind")&&vm.MotionSummary.Contains("could not be read")&&
            vm.SelectedAssetTab==3&&error.Visibility==Visibility.Visible&&scope.Visibility==Visibility.Visible,"unreadable type 9 entry shows the parser reason beside the scope label");
        Check(!slider.IsEnabled&&vm.MotionSampleText=="","failed motion has no frame slider or matrix");
        Render(panel,output,"motion-error-780.png");

        vm.BackCommand.Execute(null);vm.SelectedRow=vm.Rows[4];Await(vm.InspectSelectedAsync());Settle(panel);
        Check(vm.HasContacts&&!vm.HasMotion&&vm.SelectedAssetTab==4&&tabs.SelectedIndex==4&&vm.ContactRows.Count==164&&vm.ContactCountText=="164 of 164 definitions",
            "type 23 entry opens every stored definition in the Contacts tab");
        Check(vm.ContactsSummary.Contains("164 stored definitions · 9 type 10/11 contact definitions · 0 trailing bytes")&&
            vm.ContactsSummary.Contains("0xBFF00001 enables groups 0, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31"),"summary shows counts and the stored default mask groups");
        Check(VisualChildren<TextBlock>(view).Any(t=>t.Text=="ENABLED BY STORED DEFAULT MASK")&&vm.ContactsScope.Contains("+1440")&&vm.ContactsScope.Contains("0x3B6310"),
            "enabled column is labelled by the stored default mask and runtime overrides are disclosed");
        var list=(ListBox)view.FindName("ContactDefinitions");
        Check(VirtualizingPanel.GetIsVirtualizing(list)&&VisualChildren<ListBoxItem>(list).Count()<60,"definition list realizes only a bounded viewport");
        vm.ShowOnlyContacts=true;var first=vm.ContactRows[0];
        Check(vm.ContactRows.Count==9&&vm.ContactCountText=="9 of 164 definitions"&&first.OrdinalText=="61"&&first.OffsetText=="0x504"&&first.GroupText=="12"&&
            first.TypeText=="10"&&first.JointText=="127"&&first.HeightText=="500"&&first.EnabledText=="no"&&first.RawText.StartsWith("0C 00 00 00 0A 00 7F 00"),
            "contact filter lists type 10 joints and heights that the stored mask leaves disabled");
        vm.ShowOnlyContacts=false;
        Check(vm.ContactRows[0] is {JointText:"",HeightText:"",EnabledText:"yes"}&&vm.ContactRows[0].RawText.Length==59,"other records show only raw bytes");
        Check(vm.ContactScriptText.Contains("scpt")&&vm.OpenContactHandlerCommand.CanExecute(null)&&
            ((Button)view.FindName("OpenContactHandlerButton")).Command==vm.OpenContactHandlerCommand,"the model script is linked for its Event 27 handler");
        Render(panel,output,"contacts-780.png");
        Await(vm.OpenContactHandlerAsync());
        Check(vm.HasScript&&vm.SelectedAssetTab==2&&vm.SelectedScriptEvent?.Event.Id==27&&vm.SelectedScriptInstruction?.Instruction.Pc==19&&
            vm.Status.Contains("Event 27 starts at PC 19")&&vm.HasContacts,"handler link opens the script at its first Event 27 entry and keeps the definitions");
        Await(vm.InspectSelectedAsync());
        Check(vm.HasContacts&&vm.ContactScriptText.Contains("scpt")&&!vm.HasScript,"reopening the definitions keeps the script link");
        vm.BackCommand.Execute(null);vm.SelectedRow=vm.Rows[5];Await(vm.InspectSelectedAsync());Settle(panel);
        Check(!vm.HasContacts&&vm.HasContactsError&&vm.ContactsError.Contains("64")&&vm.SelectedAssetTab==4&&vm.ContactRows.Count==0&&
            vm.ContactScriptText==""&&!vm.OpenContactHandlerCommand.CanExecute(null),"truncated type 23 entry shows its reason and no script link");
        vm.BackCommand.Execute(null);vm.SelectedRow=vm.Rows[1];bool cancelled=false;
        System.ComponentModel.PropertyChangedEventHandler cancelWhenBusy=(_,e)=>{
            if(e.PropertyName==nameof(vm.Busy)&&vm.Busy&&!cancelled) {cancelled=true;vm.CancelCommand.Execute(null);}
        };
        vm.PropertyChanged+=cancelWhenBusy;
        try {Await(vm.InspectSelectedAsync());}finally {vm.PropertyChanged-=cancelWhenBusy;}
        Check(cancelled&&!vm.HasMotion&&!vm.Busy&&vm.Status.Contains("cancelled"),"cancelled motion inspection publishes nothing");
        Check(File.ReadAllBytes(path).SequenceEqual(bytes),"motion and definition inspection preserve source bytes");
    }
    private static void CheckEmptyContactScript(string output,Application app)
    {
        // F_HE040-shaped: the only type 3 entry is empty beside readable type 23 definitions. The second model's first type 3 entry is too short for BDX.
        string path=Path.Combine(output,"F_HE040-shaped.mdlx"),shortPath=Path.Combine(output,"short-script.mdlx");
        byte[] bytes=Bar([(3,"scpt",[]),(23,"coll",Lk120Definitions())]),shortBytes=Bar([(3,"scpt",ContactScript()[..20]),(3,"next",ContactScript()),(23,"coll",Lk120Definitions())]);
        File.WriteAllBytes(path,bytes);File.WriteAllBytes(shortPath,shortBytes);
        using var vm=new AssetExplorerViewModel(_=>{});
        var view=new AssetExplorerView {DataContext=vm};var panel=Panel(view,app);Settle(panel);
        var button=(Button)view.FindName("OpenContactHandlerButton");var text=(TextBlock)view.FindName("ContactScriptText");
        const string empty="Event 27 delivers new type 10/11 contact IDs to the Actor script. This model's type 3 entry scpt · entry 0 is empty, so it stores no Event 27 handler.";
        Await(vm.OpenFileAsync(path));
        Check(vm.Rows[0] is {BarType:3,Length:0}&&vm.Rows[0].Payload!=null&&vm.Rows[1].IsContactDefinitions,"empty type 3 entry is listed with a payload beside the definitions");
        vm.SelectedRow=vm.Rows[1];Await(vm.InspectSelectedAsync());Settle(panel);
        Check(vm.HasContacts&&vm.ContactRows.Count==164&&vm.SelectedAssetTab==4&&vm.ContactScriptText==empty&&text.Text==empty&&
            !vm.OpenContactHandlerCommand.CanExecute(null)&&!button.IsEnabled,"an empty type 3 entry is named and links no Event 27 handler");
        Await(vm.OpenContactHandlerAsync());
        Check(!vm.HasScript&&vm.HasContacts&&vm.SelectedAssetTab==4&&!vm.Busy&&vm.Status.StartsWith("Read 164 stored definitions"),"the handler link ignores an empty script instead of failing");
        Await(vm.InspectSelectedAsync());
        Check(vm.HasContacts&&vm.ContactScriptText==empty&&!vm.OpenContactHandlerCommand.CanExecute(null),"reopening the definitions keeps the empty-script reason");
        Await(vm.OpenFileAsync(shortPath));vm.SelectedRow=vm.Rows[2];Await(vm.InspectSelectedAsync());Settle(panel);
        Check(vm.HasContacts&&vm.ContactScriptText.EndsWith("This model's type 3 entry scpt · entry 0 is only 20 bytes, too short for a BDX script, so it stores no Event 27 handler.")&&
            text.Text==vm.ContactScriptText&&!vm.OpenContactHandlerCommand.CanExecute(null)&&!button.IsEnabled,"a too-short first type 3 entry links no handler and a later entry does not stand in");
        Check(File.ReadAllBytes(path).SequenceEqual(bytes)&&File.ReadAllBytes(shortPath).SequenceEqual(shortBytes),"empty-script inspection preserves source bytes");
    }
    private static byte[] MotionEntry(byte[] payload)=>[..new byte[144],..payload];
    private static byte[] RawMotion()
    {
        // Two RAW matrices: identity, then translation (10,0,0) with W 3; loop end 1, rate 60.
        float[] values=[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1, 1,0,0,0, 0,1,0,0, 0,0,1,0, 10,0,0,3];
        byte[] b=new byte[128+4*values.Length];BinaryPrimitives.WriteInt32LittleEndian(b,1);
        BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(36),2);BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(44),128);
        BinaryPrimitives.WriteSingleLittleEndian(b.AsSpan(84),1);BinaryPrimitives.WriteSingleLittleEndian(b.AsSpan(88),60);
        for(int i=0;i<values.Length;i++)BinaryPrimitives.WriteSingleLittleEndian(b.AsSpan(128+4*i),values[i]);
        return b;
    }
    private static byte[] PrototypeMotion()
    {
        // Root descriptor at 160 with unit scale, translation X 5 and no curves; two time keys (0, 10).
        byte[] b=new byte[2048];
        void I(int at,int v)=>BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(at),v);
        void F(int at,float v)=>BinaryPrimitives.WriteSingleLittleEndian(b.AsSpan(at),v);
        I(44,160);I(172,1);I(32,2);I(48,256);I(52,9);I(56,310);I(64,384);I(68,1024);I(72,1280);I(76,1536);
        F(152,60);F(1028,10);F(160,1);F(164,1);F(168,1);F(192,5);
        for(int i=0;i<9;i++)I(208+4*i,-1);
        return b;
    }
    private static byte[] Lk120Definitions()
    {
        // B_LK120-shaped type 23: 164 records, mask 0xBFF00001 and the original type 10 records (motion-event27-20261008).
        (int Ordinal,string Raw)[] contacts=[(61,"0c0000000a007f00e903000000000000fa00f401"),(62,"0c0000000a007900e903000000000000fa00f401"),
            (63,"0c0000000a0053000004000000000000fa00bc02"),(64,"0c0000000a0067000004000000000000fa00bc02"),(151,"0d0000000a035e00760300000000000014001400"),
            (160,"0d0000000a007f00e903000000000000fa009b02"),(161,"0d0000000a007900e903000000000000fa009b02"),
            (162,"0d0000000a0067000004000000000000fa009b02"),(163,"0d0000000a0053000004000000000000fa009b02")];
        byte[] b=new byte[64+20*164];BinaryPrimitives.WriteInt32LittleEndian(b,164);BinaryPrimitives.WriteUInt32LittleEndian(b.AsSpan(4),0xBFF00001);
        for(int i=0;i<164;i++)b[64+20*i+4]=1;
        foreach(var (ordinal,raw) in contacts)Convert.FromHexString(raw).CopyTo(b,64+20*ordinal);
        return b;
    }
    private static byte[] ContactScript()
    {
        // Events 0 and 27 at PCs 18 and 19, each a single Stop.
        byte[] b=new byte[56];"b_lk120"u8.CopyTo(b);
        BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(32),18);BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(36),27);BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(40),19);
        BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(52),0x49);BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(54),0x49);
        return b;
    }
    private static Border Panel(AssetExplorerView view,Application app)
    {
        var panel=new Border {Background=(Brush)app.Resources["BackgroundBrush"],Padding=new Thickness(24),Child=view};
        panel.SetValue(TextElement.ForegroundProperty,app.Resources["TextBrush"]);panel.SetValue(TextElement.FontFamilyProperty,new FontFamily("Segoe UI"));panel.SetValue(TextElement.FontSizeProperty,14.0);return panel;
    }
    private static double Settle(FrameworkElement panel)
    {
        double previous=-1;
        for(int pass=0;pass<12;pass++) {
            panel.Dispatcher.Invoke(()=>{},DispatcherPriority.ApplicationIdle);
            panel.Measure(new Size(780,double.PositiveInfinity));double height=Math.Ceiling(panel.DesiredSize.Height);
            panel.Arrange(new Rect(0,0,780,height));panel.UpdateLayout();
            if(height==previous&&panel.IsMeasureValid&&panel.IsArrangeValid)return height;previous=height;
        }
        throw new InvalidDataException("Script offscreen layout did not stabilize.");
    }
    private static void Render(FrameworkElement panel,string output,string name)
    {
        double height=Settle(panel);Check(double.IsFinite(height)&&height>400&&height<2400,"bounded script layout at780px");
        var bitmap=new RenderTargetBitmap(780,(int)height,96,96,PixelFormats.Pbgra32);bitmap.Render(panel);
        byte[] pixels=new byte[bitmap.PixelWidth*bitmap.PixelHeight*4];bitmap.CopyPixels(pixels,bitmap.PixelWidth*4,0);
        int bright=0;for(int i=0;i<pixels.Length;i+=4)if(pixels[i]>240&&pixels[i+1]>240&&pixels[i+2]>240)bright++;
        Check(bright<(pixels.Length/4)*.02,"BDX controls keep dark backgrounds");
        var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));using var file=File.Create(Path.Combine(output,name));encoder.Save(file);
    }
    private static IEnumerable<T> VisualChildren<T>(DependencyObject root) where T:DependencyObject
    {
        for(int i=0;i<VisualTreeHelper.GetChildrenCount(root);i++) {
            var child=VisualTreeHelper.GetChild(root,i);if(child is T item)yield return item;
            foreach(var other in VisualChildren<T>(child))yield return other;
        }
    }
    private static byte[] Script()
    {
        var words=new List<ushort>{0x8a,9};for(int i=0;i<500;i++)words.AddRange([0,0,0,0xc9]);words.AddRange([0x8a,95,0x49]);
        byte[] result=new byte[52+words.Count*2];"UI fixture"u8.CopyTo(result);
        BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(16),128);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(20),512);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(24),512);
        BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(32),18);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(36),27);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(40),2020);
        for(int i=0;i<words.Count;i++)BinaryPrimitives.WriteUInt16LittleEndian(result.AsSpan(52+2*i),words[i]);return result;
    }
    private static byte[] Bar((ushort Type,string Tag,byte[] Data)[] entries)
    {
        int offset=16+16*entries.Length;byte[] result=new byte[offset+entries.Sum(x=>x.Data.Length)];"BAR\x01"u8.CopyTo(result);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(4),entries.Length);
        for(int i=0;i<entries.Length;i++) {
            int row=16+16*i;BinaryPrimitives.WriteUInt16LittleEndian(result.AsSpan(row),entries[i].Type);Encoding.ASCII.GetBytes(entries[i].Tag).CopyTo(result,row+4);
            BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(row+8),offset);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(row+12),entries[i].Data.Length);
            entries[i].Data.CopyTo(result,offset);offset+=entries[i].Data.Length;
        }
        return result;
    }
}
