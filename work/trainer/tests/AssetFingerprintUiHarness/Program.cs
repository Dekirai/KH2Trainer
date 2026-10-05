using System.Windows;
using System.Windows.Markup;
using System.Xml.Linq;
using System.Text.Json;
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if(args.Length!=2)return 2;
        string workspace=Path.GetFullPath(args[0]),output=Path.GetFullPath(args[1]);
        var xml=XDocument.Load(Path.Combine(workspace,"trainer/KH2Trainer/App.xaml"));
        XNamespace ns="http://schemas.microsoft.com/winfx/2006/xaml/presentation",x="http://schemas.microsoft.com/winfx/2006/xaml";
        var resources=new XElement(ns+"ResourceDictionary",new XAttribute(XNamespace.Xmlns+"x",x),xml.Root!.Element(ns+"Application.Resources")!.Elements());
        var app=new Application { Resources=(ResourceDictionary)XamlReader.Parse(resources.ToString()) };
        Console.WriteLine(JsonSerializer.Serialize(AssetFingerprintUiChecks.Run(output,app)));return 0;
    }
}
