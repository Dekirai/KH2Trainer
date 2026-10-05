using System.Windows;
using System.Windows.Markup;
using System.Text.Json;
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if(args.Length!=2)return 2;
        string workspace=Path.GetFullPath(args[0]),output=Path.GetFullPath(args[1]);
        // The theme uses only built-in WPF types, so it loads as loose XAML.
        using var theme=File.OpenRead(Path.Combine(workspace,"trainer/KH2Trainer/Themes/Theme.xaml"));
        var app=new Application { Resources=(ResourceDictionary)XamlReader.Load(theme) };
        Console.WriteLine(JsonSerializer.Serialize(AssetFingerprintUiChecks.Run(output,app)));return 0;
    }
}
