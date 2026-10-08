using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using KH2Trainer.Core;

namespace KH2Trainer;

internal static class PackageVerification
{
    // Noninteractive packaging check. Does not create a window, connect to KH2,
    // load the native DLL, read game memory, or inspect real save files.
    public static void WriteReport(string path)
    {
        if (!Environment.Is64BitProcess) throw new InvalidDataException("The package must run as x64.");
        using var featuresStream = DataResources.Open("features.json");
        var features = FeatureCatalog.Load(featuresStream);
        var counts = new Dictionary<string, int>();
        foreach (string name in new[] { "items", "abilities", "characters" })
        {
            using var data = DataResources.Open(name + ".json");
            using var json = JsonDocument.Parse(data);
            var array = json.RootElement.ValueKind == JsonValueKind.Array ? json.RootElement : json.RootElement.GetProperty("items");
            counts.Add(name, array.GetArrayLength());
        }
        using var bridge = Assembly.GetExecutingAssembly().GetManifestResourceStream("KH2Trainer.Bridge")
            ?? throw new InvalidDataException("The embedded native bridge is missing.");
        using var diagnosticStream = DataResources.Open("runtime_diagnostics.json");
        var diagnostics = BinaryDiagnosticCatalog.Load(diagnosticStream);
        var nativeCalls = BdxNativeCallCatalog.Default;
        if (nativeCalls.DescriptorCount == 0 || nativeCalls.AnnotatedCount == 0)
            throw new InvalidDataException("The embedded BDX native-call catalog is empty.");
        using var bytes = new MemoryStream(); bridge.CopyTo(bytes);
        byte[] payload = bytes.ToArray(); GameSession.ValidatePayload(payload);
        var report = new
        {
            success = true, is64Bit = true, protocol = BridgeProtocol.Version,
            featureCount = features.Count, catalogs = counts,
            diagnostics = new { messages = diagnostics.Messages.Count, prompts = diagnostics.ClosePrompts.Count,
                languages = diagnostics.Languages.Count, sourceSha256 = diagnostics.SourceSha256 },
            bdxNativeCalls = new { descriptors = nativeCalls.DescriptorCount, annotations = nativeCalls.AnnotatedCount,
                sourceSha256 = BdxNativeCallCatalog.OriginalExecutableSha256 },
            embeddedBridgeSha256 = Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant(),
            scope = "Packaged runtime and embedded assets only. No window, game code or gameplay validation."
        };
        File.WriteAllText(Path.GetFullPath(path), JsonSerializer.Serialize(report, FeatureCatalog.JsonOptions));
    }
}
