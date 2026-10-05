using System.Buffers.Binary;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using System.Xml.Linq;
using KH2Trainer;

internal static class AssetFingerprintUiChecks
{
    private static int checks;
    private static void Check(bool condition,string text) { checks++;if(!condition)throw new InvalidDataException(text); }
    private static void Await(Task task)=>task.GetAwaiter().GetResult();
    private static void Reject<T>(Func<Task> action,string text) where T:Exception
    { try { Await(action());throw new InvalidOperationException("Expected rejection: "+text); }catch(T) { checks++; } }
    public static object Run(string output, Application app)
    {
        checks=0; output=Path.GetFullPath(output); Directory.CreateDirectory(output);
        var bindingLog=new StringWriter();PresentationTraceSources.DataBindingSource.Listeners.Add(new TextWriterTraceListener(bindingLog));
        PresentationTraceSources.DataBindingSource.Switch.Level=SourceLevels.Warning;
        byte[] leaf=Bar([("DUPL","abc"u8.ToArray()),("DUPL","abc"u8.ToArray())]);
        byte[] root=Bar([("nest",leaf),("nest",leaf)]);
        string fixture=Path.Combine(output,"nested.bar");File.WriteAllBytes(fixture,root);
        using var vm=new AssetExplorerViewModel(_=>{});
        Check(!vm.CaptureFingerprintCommand.CanExecute(null),"empty view must not allow capture");
        Await(vm.OpenFileAsync(fixture));vm.SourceLabel="Original fixture";
        Check(vm.CaptureContainerFingerprintCommand.CanExecute(null)&&!vm.CaptureFingerprintCommand.CanExecute(null),"root container capture is separate from selected entry");
        var outerFirst=vm.Rows[0];vm.SelectedRow=outerFirst;Await(vm.InspectSelectedAsync());
        vm.SelectedRow=vm.Rows[0];Await(vm.CaptureSelectedFingerprintAsync());
        Check(vm.FingerprintRows.Count==1&&vm.FingerprintRows[0].Fingerprint.Path.Count==3,"capture preserves complete nested path");
        var first=vm.FingerprintRows[0].Fingerprint;
        vm.SelectedRow=vm.Rows[1];Await(vm.CaptureSelectedFingerprintAsync());
        Check(vm.FingerprintRows.Count==2&&vm.FingerprintRows[1].Fingerprint.Id!=first.Id,"duplicate-tag siblings have distinct identities");
        Await(vm.CompareSelectedFingerprintAsync());Check(vm.FingerprintMatches.Count==2,"same bytes from two nested entries match");
        vm.BackCommand.Execute(null);Check(vm.Rows.Count==2&&vm.SelectedRow==outerFirst&&vm.SourceLabel=="Original fixture","back restores source label and selection");
        vm.SelectedRow=vm.Rows[1];Await(vm.InspectSelectedAsync());vm.SelectedRow=vm.Rows[0];Await(vm.CaptureSelectedFingerprintAsync());
        Check(vm.FingerprintRows.Count==3&&vm.FingerprintRows.Select(r=>r.Fingerprint.Id).Distinct().Count()==3,"same inner ordinal under a different parent stays distinct");
        Await(vm.CompareSelectedFingerprintAsync());Check(vm.FingerprintMatches.Count==3,"all equal-content locators retained");
        Await(vm.CaptureSelectedFingerprintAsync());Check(vm.FingerprintRows.Count==3,"recapture updates instead of duplicating a locator");
        vm.SourceLabel="Modified fixture";Await(vm.CaptureSelectedFingerprintAsync());Check(vm.FingerprintRows.Count==4,"different portable source label adds separate observation");
        Await(vm.CaptureSelectedFingerprintAsync(true));Check(vm.FingerprintRows.Count==5&&vm.FingerprintRows[^1].Fingerprint.Length==leaf.Length,"current container capture does not silently use selected child");
        vm.SourceLabel="../invalid";Reject<InvalidDataException>(()=>vm.CaptureSelectedFingerprintAsync(),"invalid source label");Check(vm.FingerprintRows.Count==5&&!vm.Busy,"invalid label leaves index intact and releases busy state");
        vm.SourceLabel="Modified fixture";
        string saved=Path.Combine(output,"fingerprints-"+Guid.NewGuid().ToString("N")+".json");Await(vm.SaveFingerprintIndexAsync(saved));
        byte[] savedBytes=File.ReadAllBytes(saved);Reject<IOException>(()=>vm.SaveFingerprintIndexAsync(saved),"existing destination");
        Check(savedBytes.SequenceEqual(File.ReadAllBytes(saved)),"UI save preserves an existing file");
        vm.ClearFingerprintIndexCommand.Execute(null);Check(vm.FingerprintRows.Count==0&&vm.FingerprintMatches.Count==0,"clear changes only in-memory index");
        Await(vm.LoadFingerprintIndexAsync(saved));Check(vm.FingerprintRows.Count==5&&vm.FingerprintStatus.Contains("not opened"),"load restores index without opening stored locators");
        string malformed=Path.Combine(output,"malformed.json");File.WriteAllText(malformed,"{\"Version\":999}");
        Reject<InvalidDataException>(()=>vm.LoadFingerprintIndexAsync(malformed),"bad JSON index");Check(vm.FingerprintRows.Count==5&&!vm.Busy,"load failure preserves old index");
        Await(vm.CompareSelectedFingerprintAsync());Check(vm.FingerprintMatches.Count==4,"comparison remains correct after save/load");
        string game=Path.Combine(output,"fake-install");Directory.CreateDirectory(game);File.WriteAllText(Path.Combine(game,"KINGDOM HEARTS II FINAL MIX.exe"),"fixture marker only");
        string gameAsset=Path.Combine(game,"asset.bar");File.WriteAllBytes(gameAsset,root);Await(vm.OpenFileAsync(gameAsset));
        Reject<IOException>(()=>vm.SaveFingerprintIndexAsync(Path.Combine(game,"index.json")),"detected game directory");
        Check(!File.Exists(Path.Combine(game,"index.json"))&&File.ReadAllBytes(gameAsset).SequenceEqual(root),"game/source bytes remain unchanged");
        int stored=16+((root.Length+15)&~15);byte[] packageRecord=new byte[stored];
        BinaryPrimitives.WriteInt32LittleEndian(packageRecord,root.Length);BinaryPrimitives.WriteInt32LittleEndian(packageRecord.AsSpan(8),-2);root.CopyTo(packageRecord,16);
        byte[] hed=new byte[64];for(int p=0;p<64;p+=32){BinaryPrimitives.WriteInt32LittleEndian(hed.AsSpan(p+24),stored);BinaryPrimitives.WriteInt32LittleEndian(hed.AsSpan(p+28),root.Length);}
        string hedPath=Path.Combine(output,"package.hed");File.WriteAllBytes(hedPath,hed);File.WriteAllBytes(Path.ChangeExtension(hedPath,".pkg"),packageRecord);
        Await(vm.OpenPackageIndexAsync(hedPath));vm.SelectedRow=vm.Rows[0];Await(vm.CaptureSelectedFingerprintAsync());
        var packageOriginal=vm.FingerprintRows[^1].Fingerprint;
        Check(packageOriginal.Path.Count==1&&packageOriginal.Path[0].Ordinal==0&&packageOriginal.Length==root.Length,"raw HED row captures original decoded payload");
        Await(vm.InspectSelectedAsync());vm.SelectedRow=vm.Rows[0];Await(vm.InspectSelectedAsync());vm.SelectedRow=vm.Rows[0];Await(vm.InspectSelectedAsync());vm.SelectedRow=vm.Rows[0];Await(vm.CaptureSelectedFingerprintAsync());
        Check(vm.FingerprintRows[^1].Fingerprint.Path.Count==3&&vm.FingerprintRows[^1].Fingerprint.Path[0].Kind==KH2Trainer.Core.AssetSourceKind.PackageOriginal,"package to nested BAR navigation retains complete locator");
        Await(vm.OpenPackageIndexAsync(hedPath));vm.SelectedRow=vm.Rows[1];Await(vm.CaptureSelectedFingerprintAsync());
        Check(vm.FingerprintRows[^1].Fingerprint.Id!=packageOriginal.Id&&vm.FingerprintRows[^1].Fingerprint.Sha256==packageOriginal.Sha256,"same-span HED aliases stay separate in UI");
        Await(vm.OpenFileAsync(fixture));vm.SourceLabel="Original fixture";vm.SelectedRow=vm.Rows[0];Await(vm.InspectSelectedAsync());vm.SelectedRow=vm.Rows[0];Await(vm.CompareSelectedFingerprintAsync());
        vm.SelectedFingerprint=vm.FingerprintRows[0];
        var view=new AssetExplorerView { DataContext=vm };
        ((Expander)view.FindName("FingerprintDetailsExpander")).IsExpanded=true;
        var panel=new Border { Background=(Brush)app.Resources["BackgroundBrush"],Padding=new Thickness(24),Child=view };
        panel.SetValue(TextElement.ForegroundProperty,app.Resources["TextBrush"]);panel.SetValue(TextElement.FontFamilyProperty,new FontFamily("Segoe UI"));panel.SetValue(TextElement.FontSizeProperty,14.0);
        Render(panel,output,780,"asset-fingerprints-780.png");Render(panel,output,1100,"asset-fingerprints-1100.png");
        Check(bindingLog.ToString().Length==0,"WPF binding errors: "+bindingLog);
        var report=new {success=true,checks,renders=2,bindingErrors=0,scope="Actual AssetExplorerViewModel/View and application resources; no window/startup/game/input."};
        File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(report,new JsonSerializerOptions {WriteIndented=true}));return report;
    }
    private static void Render(FrameworkElement panel,string output,double width,string name)
    {
        double previous=-1,height=0;
        for(int i=0;i<12;i++) {
            panel.Dispatcher.Invoke(()=>{},DispatcherPriority.ApplicationIdle);panel.Measure(new Size(width,double.PositiveInfinity));height=Math.Ceiling(panel.DesiredSize.Height);
            panel.Arrange(new Rect(0,0,width,height));panel.UpdateLayout();
            if(height==previous&&panel.IsMeasureValid&&panel.IsArrangeValid)break;previous=height;
        }
        Check(double.IsFinite(height)&&height>1000&&height<4000,"bounded offscreen page layout");
        var bitmap=new RenderTargetBitmap((int)width,(int)height,96,96,PixelFormats.Pbgra32);bitmap.Render(panel);
        byte[] pixels=new byte[bitmap.PixelWidth*bitmap.PixelHeight*4];bitmap.CopyPixels(pixels,bitmap.PixelWidth*4,0);
        int bright=0;for(int i=0;i<pixels.Length;i+=4)if(pixels[i]>240&&pixels[i+1]>240&&pixels[i+2]>240)bright++;
        Check(bright<(pixels.Length/4)*.02,"dark background, including new lists");
        var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));using var file=File.Create(Path.Combine(output,name));encoder.Save(file);
    }
    private static byte[] Bar((string Tag,byte[] Data)[] entries)
    {
        int offset=16+16*entries.Length;byte[] result=new byte[offset+entries.Sum(e=>e.Data.Length)];"BAR\x01"u8.CopyTo(result);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(4),entries.Length);
        for(int i=0;i<entries.Length;i++){int p=16+16*i;BinaryPrimitives.WriteUInt16LittleEndian(result.AsSpan(p),1);Encoding.ASCII.GetBytes(entries[i].Tag).CopyTo(result,p+4);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(p+8),offset);BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(p+12),entries[i].Data.Length);entries[i].Data.CopyTo(result,offset);offset+=entries[i].Data.Length;}return result;
    }
}
