using System.IO;
using System.Buffers.Binary;
using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using KH2Trainer;
using KH2Trainer.Core;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if(args.Length!=2) return 2;
        string output=Path.GetFullPath(args[1]);Directory.CreateDirectory(output);
        bool fixture=args[0]=="--fixture";
        string source=fixture?Path.Combine(output,"fixture.bar"):Path.GetFullPath(args[0]);
        if(fixture) {
            byte[] bytes=new byte[80];"BAR\x01"u8.CopyTo(bytes);BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(4),1);
            BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(16),2);"test"u8.CopyTo(bytes.AsSpan(20));
            BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(24),32);BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(28),48);
            for(int i=32;i<80;++i)bytes[i]=(byte)i;File.WriteAllBytes(source,bytes);
        }
        // A plain WPF Application has no trainer Startup override or StartupUri.
        // Load only the compiled theme and templates; never construct KH2Trainer.App or MainWindow.
        var app=new Application { ShutdownMode=ShutdownMode.OnExplicitShutdown };
        app.Resources=new ResourceDictionary { Source=new Uri("pack://application:,,,/KH2_Trainer;component/Themes/FeatureTemplates.xaml",UriKind.Absolute) };
        var bindingLog=new StringWriter();PresentationTraceSources.DataBindingSource.Listeners.Add(new TextWriterTraceListener(bindingLog));
        PresentationTraceSources.DataBindingSource.Switch.Level=SourceLevels.Warning;
        using var vm=new AssetExplorerViewModel(_=>{});
        vm.OpenFileAsync(source).GetAwaiter().GetResult();
        if(vm.Rows.Count==0 || vm.Busy)throw new InvalidDataException("The actual viewmodel did not load the asset fixture.");
        var first=vm.Rows[0];vm.SelectedRow=first;
        vm.Filter="___missing_asset_name___";
        if(vm.Rows.Count!=0 || vm.SelectedRow!=null)throw new InvalidDataException("Filter must clear invisible selection.");
        vm.Filter="";vm.SelectedRow=first;
        int rootEntries=vm.Rows.Count;
        vm.InspectSelectedAsync().GetAwaiter().GetResult();
        if(vm.Preview.Length==0 || !vm.BackCommand.CanExecute(null))throw new InvalidDataException("Inspect must preview the real entry and preserve back navigation.");
        vm.BackCommand.Execute(null);
        if(vm.Rows.Count!=rootEntries || vm.SelectedRow!=first)throw new InvalidDataException("Back must restore the parent and selection.");
        vm.InspectSelectedAsync().GetAwaiter().GetResult();
        var view=new AssetExplorerView { DataContext=vm };
        var panel=new Border { Background=(Brush)app.Resources["BackgroundBrush"],Padding=new Thickness(24),Child=view };
        panel.SetValue(TextElement.ForegroundProperty,app.Resources["TextBrush"]);
        panel.SetValue(TextElement.FontFamilyProperty,new FontFamily("Segoe UI"));panel.SetValue(TextElement.FontSizeProperty,14.0);
        double height=LayoutOffscreen(panel);
        var bitmap=new RenderTargetBitmap(780,(int)height,96,96,PixelFormats.Pbgra32);bitmap.Render(panel);
        var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using(var stream=File.Create(Path.Combine(output,"asset-explorer.png")))encoder.Save(stream);
        var pixels=new byte[bitmap.PixelWidth*bitmap.PixelHeight*4];bitmap.CopyPixels(pixels,bitmap.PixelWidth*4,0);
        int bright=0;for(int i=0;i<pixels.Length;i+=4)if(pixels[i]>240&&pixels[i+1]>240&&pixels[i+2]>240)bright++;
        if(bright>(pixels.Length/4)*.02)throw new InvalidDataException("Unexpected light background in the asset page.");
        var diagnostics=CheckDiagnostics(output,app);
        var fingerprints=AssetFingerprintUiChecks.Run(Path.Combine(output,"Fingerprints"),app);
        var featurePages=FeatureLayoutUiChecks.Run(Path.Combine(output,"FeaturePages"),app);
        if(app.Windows.Count!=0 || app.MainWindow!=null || app.StartupUri!=null)
            throw new InvalidDataException("Offscreen verification created an application window or startup target.");
        if(bindingLog.ToString().Length>0)throw new InvalidDataException(bindingLog.ToString());
        var report=new { success=true,source,sourceIsSynthetic=fixture,entries=rootEntries,height,width=780,bindingErrors=0,
            diagnostics,fingerprints,featurePages,applicationType=app.GetType().FullName,windowCount=app.Windows.Count,
            scope="Offscreen feature pages (sections, tabs, control rows and readouts), Asset Explorer, content-fingerprint comparison and Game Messages views. Navigation completeness, switch behavior, diagnostic states, fingerprint identity/save/load, all 66 diagnostic texts/captions and bindings checked. No visible window, game process, input or gameplay test." };
        File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(report,new JsonSerializerOptions {WriteIndented=true}));
        Console.WriteLine(JsonSerializer.Serialize(report));return 0;
    }
    private static object CheckDiagnostics(string output,Application app)
    {
        using var stream=typeof(RuntimeDiagnosticsViewModel).Assembly.GetManifestResourceStream("KH2Trainer.Data.runtime_diagnostics.json")
            ?? throw new InvalidDataException("Embedded diagnostics missing.");
        var catalog=BinaryDiagnosticCatalog.Load(stream);
        var vm=new RuntimeDiagnosticsViewModel();
        int checks=0;
        void Require(bool condition,string message) { ++checks;if(!condition)throw new InvalidDataException(message); }
        Require(vm.Entries.Count==11 && vm.Languages.Count==6 && vm.SelectedLanguage.Id==1 && vm.HasSelection,"Diagnostics must start with all entries and English.");
        var entries=vm.Entries.ToArray();
        foreach(var entry in entries)foreach(var language in vm.Languages) {
            vm.SelectedEntry=entry;vm.SelectedLanguage=language;
            var original=entry.Key.StartsWith("message:",StringComparison.Ordinal)
                ? catalog.FindMessage(int.Parse(entry.Key[8..]))!.Localizations.Single(x=>x.LanguageId==language.Id)
                : catalog.ClosePrompts.Single(x=>"exit:"+x.Id==entry.Key).Localizations.Single(x=>x.LanguageId==language.Id);
            Require(vm.OriginalText==original.Text && vm.PrimaryButtonText==original.PrimaryButton &&
                vm.SecondaryButtonText==(original.SecondaryButton??"") && vm.HasSecondaryButton==(original.SecondaryButton is not null),
                "Diagnostics altered original wording or button order: "+entry.Key+"/"+language.Code);
            Require(vm.SourceAnchors.Contains(original.TextAddress,StringComparison.Ordinal) &&
                vm.SourceAnchors.Contains(original.RecordAddress,StringComparison.Ordinal),"Diagnostics lost selected source addresses.");
        }
        vm.SelectedLanguage=vm.Languages.Single(x=>x.Id==1);
        vm.Filter="Speicherdaten";
        Require(vm.Entries.Count>0 && vm.Entries.Count<11 && vm.HasSelection,"Cross-language search must find German content while English is selected.");
        vm.Filter="___no_diagnostic_match___";
        Require(vm.Entries.Count==0 && !vm.HasSelection && vm.OriginalText=="" && vm.SourceAnchors=="","Empty diagnostics filter must clear stale details.");
        double emptyHeight=RenderDiagnostics(vm,app,output,"game-messages-empty.png",false);
        vm.Filter="";
        Require(vm.Entries.Count==11 && vm.HasSelection,"Clearing the diagnostic filter must restore selection.");
        vm.SelectedEntry=entries.Single(x=>x.Key=="message:1");
        Require(vm.HasSecondaryButton && vm.PrimaryButtonText=="Quit Game" && vm.SecondaryButtonText=="OK","Retry dialog button order changed.");
        double englishHeight=RenderDiagnostics(vm,app,output,"game-messages-english.png",true);
        vm.SelectedEntry=entries.Single(x=>x.Key=="exit:busy");vm.SelectedLanguage=vm.Languages.Single(x=>x.Id==4);
        Require(vm.IsClosePrompt && !vm.IsRuntimeMessage && vm.PromptBehavior==catalog.ClosePrompts.Single(x=>x.Id=="busy").Behavior,"Busy exit prompt lost its behavior.");
        double germanHeight=RenderDiagnostics(vm,app,output,"game-messages-german.png",false);
        vm.SelectedEntry=entries.Single(x=>x.Key=="message:7");vm.SelectedLanguage=vm.Languages.Single(x=>x.Id==0);
        Require(vm.IsRuntimeMessage && !vm.HasSecondaryButton,"Information dialog cannot gain a second button.");
        double japaneseHeight=RenderDiagnostics(vm,app,output,"game-messages-japanese.png",false);
        return new {success=true,checks,entries=11,localizations=66,renders=4,width=780,englishHeight,germanHeight,japaneseHeight,emptyHeight};
    }
    private static double RenderDiagnostics(RuntimeDiagnosticsViewModel vm,Application app,string output,string name,bool expanded)
    {
        var view=new RuntimeDiagnosticsView {DataContext=vm};
        ((Expander)view.FindName("DiagnosticSourceDetails")).IsExpanded=expanded;
        var panel=new Border {Background=(Brush)app.Resources["BackgroundBrush"],Padding=new Thickness(24),Child=view};
        panel.SetValue(TextElement.ForegroundProperty,app.Resources["TextBrush"]);
        panel.SetValue(TextElement.FontFamilyProperty,new FontFamily("Segoe UI"));panel.SetValue(TextElement.FontSizeProperty,14.0);
        double height=LayoutOffscreen(panel);
        if(!double.IsFinite(height) || height<200 || height>4000)throw new InvalidDataException("Invalid diagnostics page size.");
        if(vm.HasSelection) {
            var language=(ComboBox)view.FindName("DiagnosticLanguage");
            if(!VisualChildren<TextBlock>(language).Any(x=>x.Visibility==Visibility.Visible && x.Text==vm.SelectedLanguage.Name))
                throw new InvalidDataException("The selected diagnostic language is not displayed by name: "+string.Join(" | ",VisualChildren<TextBlock>(language).Select(x=>x.Text)));
        }
        var bitmap=new RenderTargetBitmap(780,(int)height,96,96,PixelFormats.Pbgra32);bitmap.Render(panel);
        byte[] pixels=new byte[bitmap.PixelWidth*bitmap.PixelHeight*4];bitmap.CopyPixels(pixels,bitmap.PixelWidth*4,0);
        int bright=0;for(int i=0;i<pixels.Length;i+=4)if(pixels[i]>240&&pixels[i+1]>240&&pixels[i+2]>240)bright++;
        if(bright>(pixels.Length/4)*.02)throw new InvalidDataException("Unexpected light background in diagnostics.");
        var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var file=File.Create(Path.Combine(output,name));encoder.Save(file);
        return height;
    }
    private static double LayoutOffscreen(FrameworkElement panel)
    {
        // Templates and bindings may invalidate measure during the first arrange.
        // Settle the dispatcher and layout before sizing the export bitmap.
        double previous=-1;
        for(int pass=0;pass<10;++pass) {
            panel.Dispatcher.Invoke(()=>{},DispatcherPriority.ApplicationIdle);
            panel.Measure(new Size(780,double.PositiveInfinity));
            double height=Math.Ceiling(panel.DesiredSize.Height);
            panel.Arrange(new Rect(0,0,780,height));panel.UpdateLayout();
            if(height==previous && panel.IsMeasureValid && panel.IsArrangeValid && Math.Ceiling(panel.DesiredSize.Height)==height)
                return height;
            previous=height;
        }
        throw new InvalidDataException("Offscreen layout did not stabilize.");
    }
    private static IEnumerable<T> VisualChildren<T>(DependencyObject root) where T:DependencyObject
    {
        for(int i=0;i<VisualTreeHelper.GetChildrenCount(root);++i) {
            var child=VisualTreeHelper.GetChild(root,i);
            if(child is T item)yield return item;
            foreach(var descendant in VisualChildren<T>(child))yield return descendant;
        }
    }
}
