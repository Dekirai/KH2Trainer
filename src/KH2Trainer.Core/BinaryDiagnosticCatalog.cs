using System.Globalization;
using System.Text.Json;

namespace KH2Trainer.Core;

public sealed record DiagnosticLanguage(int Id, string Code, string Name);

public sealed record DiagnosticLocalization(
    int LanguageId, string Text, string PrimaryButton, string? SecondaryButton,
    string TextAddress, string? PrimaryButtonAddress, string? SecondaryButtonAddress,
    string RecordAddress);

public sealed class RuntimeMessageDiagnostic
{
    public required int Id { get; init; }
    public required string Title { get; init; }
    public required string Summary { get; init; }
    public required int NativeStyle { get; init; }
    public required string PrimaryEffect { get; init; }
    public required string SecondaryEffect { get; init; }
    public required IReadOnlyList<DiagnosticLocalization> Localizations { get; init; }
    public DiagnosticLocalization English => Localizations.Single(x => x.LanguageId == 1);
    public string DialogKind => NativeStyle == 0 ? "Information" : "Confirmation";
}

public sealed class ExitPromptDiagnostic
{
    public required string Id { get; init; }
    public required int NativeGameStatus { get; init; }
    public required string Title { get; init; }
    public required string Behavior { get; init; }
    public required IReadOnlyList<DiagnosticLocalization> Localizations { get; init; }
    public DiagnosticLocalization English => Localizations.Single(x => x.LanguageId == 1);
}

/// <summary>Offline reference data only. This class has no game or window-message API.</summary>
public sealed class BinaryDiagnosticCatalog
{
    public const string SupportedSourceSha256 = "9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed";
    private const int MaximumBytes = 256 * 1024;
    public string SourceSha256 { get; }
    public string Scope { get; }
    public string SharedNativeBehavior { get; }
    public IReadOnlyList<DiagnosticLanguage> Languages { get; }
    public IReadOnlyList<RuntimeMessageDiagnostic> Messages { get; }
    public IReadOnlyList<ExitPromptDiagnostic> ClosePrompts { get; }
    public IReadOnlyList<string> Evidence { get; }

    private BinaryDiagnosticCatalog(CatalogData data)
    {
        SourceSha256 = data.SourceSha256!;
        Scope = data.Scope!;
        SharedNativeBehavior = data.SharedNativeBehavior!;
        Languages = Array.AsReadOnly(data.Languages!);
        Messages = Array.AsReadOnly(data.Messages!.Select(x => new RuntimeMessageDiagnostic
        {
            Id = x.Id, Title = x.Title, Summary = x.Summary, NativeStyle = x.NativeStyle,
            PrimaryEffect = x.PrimaryEffect, SecondaryEffect = x.SecondaryEffect,
            Localizations = Array.AsReadOnly(x.Localizations.ToArray())
        }).OrderBy(x => x.Id).ToArray());
        ClosePrompts = Array.AsReadOnly(data.ClosePrompts!.Select(x => new ExitPromptDiagnostic
        {
            Id = x.Id, NativeGameStatus = x.NativeGameStatus, Title = x.Title, Behavior = x.Behavior,
            Localizations = Array.AsReadOnly(x.Localizations.ToArray())
        }).OrderBy(x => x.NativeGameStatus).ToArray());
        Evidence = Array.AsReadOnly(data.Evidence!);
    }

    public static BinaryDiagnosticCatalog Load(string path)
    {
        using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (file.Length is <= 0 or > MaximumBytes)
            throw new InvalidDataException("Diagnostic catalog size is invalid.");
        return Load(file);
    }

    /// <summary>Reads at most 256 KiB plus one guard byte. The caller owns the stream.</summary>
    public static BinaryDiagnosticCatalog Load(Stream stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        using var buffer = new MemoryStream();
        byte[] chunk = new byte[4096];
        while (buffer.Length <= MaximumBytes)
        {
            int read = stream.Read(chunk, 0, (int)Math.Min(chunk.Length, MaximumBytes + 1L - buffer.Length));
            if (read == 0) break;
            buffer.Write(chunk, 0, read);
        }
        if (buffer.Length is <= 0 or > MaximumBytes)
            throw new InvalidDataException("Diagnostic catalog size is invalid.");
        buffer.Position = 0;
        CatalogData data;
        try
        {
            data = JsonSerializer.Deserialize<CatalogData>(buffer, new JsonSerializerOptions
            { PropertyNameCaseInsensitive = true, MaxDepth = 32 })
                ?? throw new InvalidDataException("Diagnostic catalog is empty.");
        }
        catch (JsonException error)
        { throw new InvalidDataException("Diagnostic catalog JSON is invalid.", error); }
        Validate(data);
        return new BinaryDiagnosticCatalog(data);
    }

    public RuntimeMessageDiagnostic? FindMessage(int id) => Messages.FirstOrDefault(x => x.Id == id);

    // Original CIL switch plus this binary's native get_RegionNumber(), which returns 1.
    public static int ResolveNativeLanguage(int nativeLanguage) => nativeLanguage switch
    { 0 or 7 => 0, 4 => 2, 6 => 3, 3 => 4, 5 => 5, _ => 1 };

    private static void Validate(CatalogData data)
    {
        Require(data.Schema == 1 && string.Equals(data.SourceSha256, SupportedSourceSha256,
            StringComparison.OrdinalIgnoreCase), "Unsupported diagnostic catalog source or schema.");
        Text(data.Scope); Text(data.SharedNativeBehavior);
        string[] codes = ["ja", "en", "fr", "it", "de", "es"];
        Require(data.Languages is { Length: 6 }, "The catalog must contain the six original languages.");
        var languages = data.Languages!;
        Require(languages.All(x => x is not null) &&
            languages.Select(x => x.Id).Order().SequenceEqual(Enumerable.Range(0, 6)), "Invalid language IDs.");
        foreach (var lang in languages)
        { Require(lang.Code == codes[lang.Id], "Invalid native language mapping."); Text(lang.Name); }
        Require(data.Messages is { Length: 8 } && data.Messages.All(x => x is not null) &&
            data.Messages.Select(x => x.Id).Order().SequenceEqual(Enumerable.Range(0, 8)), "Invalid message IDs.");
        int[] styles = [0, 2, 0, 0, 0, 1, 1, 0];
        foreach (var entry in data.Messages!)
        {
            Text(entry.Title); Text(entry.Summary); Text(entry.PrimaryEffect); Text(entry.SecondaryEffect);
            Require(entry.NativeStyle == styles[entry.Id], "Invalid original dialog style.");
            Localizations(entry.Localizations, entry.NativeStyle != 0);
        }
        Require(data.ClosePrompts is { Length: 3 } && data.ClosePrompts.All(x => x is not null) &&
            data.ClosePrompts.Select(x => x.NativeGameStatus).Order().SequenceEqual(new[] { 0, 1, 2 }), "Invalid exit states.");
        string[] ids = ["idle", "gameplay", "busy"];
        foreach (var entry in data.ClosePrompts!)
        {
            Require(entry.Id == ids[entry.NativeGameStatus], "Invalid exit prompt ID.");
            Text(entry.Title); Text(entry.Behavior); Localizations(entry.Localizations, true);
        }
        Require(data.Evidence is { Length: > 0 and <= 16 }, "Missing evidence references.");
        foreach (string item in data.Evidence!) Text(item);
    }

    private static void Localizations(IReadOnlyList<DiagnosticLocalization>? values, bool confirmation)
    {
        Require(values is { Count: 6 } && values.All(x => x is not null) &&
            values.Select(x => x.LanguageId).Order().SequenceEqual(Enumerable.Range(0, 6)), "Invalid localized entries.");
        foreach (var value in values!)
        {
            Text(value.Text); Text(value.PrimaryButton);
            Require(confirmation == (value.SecondaryButton is not null), "Invalid dialog buttons.");
            if (value.SecondaryButton is not null) Text(value.SecondaryButton);
            Address(value.TextAddress); Address(value.RecordAddress);
            if (value.PrimaryButtonAddress is not null) Address(value.PrimaryButtonAddress);
            if (value.SecondaryButtonAddress is not null) Address(value.SecondaryButtonAddress);
        }
    }

    private static void Address(string? value) => Require(value is not null && value.StartsWith("0x", StringComparison.Ordinal) &&
        ulong.TryParse(value.AsSpan(2), NumberStyles.HexNumber, CultureInfo.InvariantCulture, out ulong address) &&
        address >= 0x140000000 && address < 0x144000000, "Invalid original native address.");
    private static void Text(string? value) => Require(!string.IsNullOrWhiteSpace(value) && value.Length <= 16_384 &&
        !value.Contains('\0'), "Invalid diagnostic text.");
    private static void Require(bool condition, string message)
    { if (!condition) throw new InvalidDataException(message); }

    private sealed class CatalogData
    {
        public int Schema { get; set; }
        public string? SourceSha256 { get; set; }
        public string? Scope { get; set; }
        public string? SharedNativeBehavior { get; set; }
        public DiagnosticLanguage[]? Languages { get; set; }
        public RuntimeMessageDiagnostic[]? Messages { get; set; }
        public ExitPromptDiagnostic[]? ClosePrompts { get; set; }
        public string[]? Evidence { get; set; }
    }
}
