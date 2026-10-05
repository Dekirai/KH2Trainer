using KH2Trainer.Core;

namespace KH2Trainer;

/// <summary>A display-only entry. Captions and message text remain exactly as extracted.</summary>
public sealed class RuntimeDiagnosticEntry
{
    internal RuntimeMessageDiagnostic? Message { get; }
    internal ExitPromptDiagnostic? Prompt { get; }
    internal IReadOnlyList<DiagnosticLocalization> Localizations => Message?.Localizations ?? Prompt!.Localizations;
    public string Key { get; }
    public string Title => Message?.Title ?? Prompt!.Title;
    public string Identity => Message is { } message ? $"Message {message.Id}" : $"Exit state {Prompt!.NativeGameStatus}";
    public string Kind => Message?.DialogKind ?? "Exit / progress";
    public string Summary => Message?.Summary ?? "The exit workflow chooses this text for the corresponding game state.";

    internal RuntimeDiagnosticEntry(RuntimeMessageDiagnostic message) { Message = message; Key = $"message:{message.Id}"; }
    internal RuntimeDiagnosticEntry(ExitPromptDiagnostic prompt) { Prompt = prompt; Key = $"exit:{prompt.Id}"; }

    internal bool Matches(string query) =>
        new[] { Key, Title, Identity, Kind, Summary, Message?.PrimaryEffect, Message?.SecondaryEffect, Prompt?.Behavior }
            .Any(text => text?.Contains(query, StringComparison.OrdinalIgnoreCase) == true) ||
        Localizations.Any(text => text.Text.Contains(query, StringComparison.OrdinalIgnoreCase) ||
            text.PrimaryButton.Contains(query, StringComparison.OrdinalIgnoreCase) ||
            text.SecondaryButton?.Contains(query, StringComparison.OrdinalIgnoreCase) == true);
}

/// <summary>Offline reference browser: no game access, native calls, or message-box commands.</summary>
public sealed class RuntimeDiagnosticsViewModel : Observable
{
    private readonly BinaryDiagnosticCatalog catalog;
    private readonly IReadOnlyList<RuntimeDiagnosticEntry> allEntries;
    private IReadOnlyList<RuntimeDiagnosticEntry> entries;
    private RuntimeDiagnosticEntry? selectedEntry;
    private DiagnosticLanguage selectedLanguage;
    private string filter = "";

    public RuntimeDiagnosticsViewModel() : this(LoadEmbedded()) { }

    public RuntimeDiagnosticsViewModel(BinaryDiagnosticCatalog catalog)
    {
        ArgumentNullException.ThrowIfNull(catalog);
        this.catalog = catalog;
        Languages = catalog.Languages.OrderBy(x => x.Id == 1 ? -1 : x.Id).ToArray();
        selectedLanguage = Languages.Single(x => x.Id == 1);
        allEntries = catalog.Messages.Select(x => new RuntimeDiagnosticEntry(x))
            .Concat(catalog.ClosePrompts.Select(x => new RuntimeDiagnosticEntry(x))).ToArray();
        entries = allEntries;
        selectedEntry = entries.FirstOrDefault();
    }

    private static BinaryDiagnosticCatalog LoadEmbedded()
    {
        using var stream = DataResources.Open("runtime_diagnostics.json");
        return BinaryDiagnosticCatalog.Load(stream);
    }

    public IReadOnlyList<DiagnosticLanguage> Languages { get; }
    public IReadOnlyList<RuntimeDiagnosticEntry> Entries => entries;
    public string CountText => $"{entries.Count} of {allEntries.Count} messages and prompts";
    public string Filter
    {
        get => filter;
        set
        {
            if (!Set(ref filter, value ?? "")) return;
            string query = filter.Trim();
            var previous = selectedEntry;
            entries = query.Length == 0 ? allEntries : allEntries.Where(x => x.Matches(query)).ToArray();
            // Keep a still-visible selection. Otherwise show the first match or a clear empty state.
            Changed(nameof(Entries));
            SelectedEntry = previous is not null && entries.Contains(previous) ? previous : entries.FirstOrDefault();
            Changed(nameof(CountText));
        }
    }
    public RuntimeDiagnosticEntry? SelectedEntry
    {
        get => selectedEntry;
        set
        {
            if (value is not null && !entries.Contains(value)) return;
            // A view being swapped out pushes null; keep a selection that is still listed.
            if (value is null && selectedEntry is not null && entries.Contains(selectedEntry)) return;
            if (Set(ref selectedEntry, value)) RefreshDetails();
        }
    }
    public DiagnosticLanguage SelectedLanguage
    {
        get => selectedLanguage;
        set
        {
            // WPF can transiently supply null during item-source changes.
            var language = value is null ? null : Languages.FirstOrDefault(x => x.Id == value.Id);
            if (language is not null && Set(ref selectedLanguage, language)) RefreshDetails();
        }
    }

    private DiagnosticLocalization? Localization => selectedEntry?.Localizations.Single(x => x.LanguageId == selectedLanguage.Id);
    public bool HasSelection => selectedEntry is not null;
    public bool IsRuntimeMessage => selectedEntry?.Message is not null;
    public bool IsClosePrompt => selectedEntry?.Prompt is not null;
    public string SelectedTitle => selectedEntry?.Title ?? "No matching messages";
    public string SelectedIdentity => selectedEntry is null ? "" : $"{selectedEntry.Identity} · {selectedEntry.Kind}";
    public string SelectedSummary => selectedEntry?.Summary ?? "Change the filter to browse the catalog.";
    public string OriginalText => Localization?.Text ?? "";
    public string PrimaryButtonText => Localization?.PrimaryButton ?? "";
    public string SecondaryButtonText => Localization?.SecondaryButton ?? "";
    public bool HasSecondaryButton => Localization?.SecondaryButton is not null;
    public string PrimaryEffect => selectedEntry?.Message?.PrimaryEffect ?? "";
    public string SecondaryEffect => selectedEntry?.Message?.SecondaryEffect ?? "";
    public string PromptBehavior => selectedEntry?.Prompt?.Behavior ?? "";
    public string SharedNativeBehavior => catalog.SharedNativeBehavior;
    public string SourceSha256 => catalog.SourceSha256;
    public string SourceAnchors
    {
        get
        {
            var text = Localization;
            if (text is null) return "";
            var lines = new List<string>
            {
                $"{SelectedIdentity} · original language table index {selectedLanguage.Id}",
                $"Text: {text.TextAddress}",
                $"Table record: {text.RecordAddress}"
            };
            if (text.PrimaryButtonAddress is { } primary) lines.Add($"First caption: {primary}");
            if (text.SecondaryButtonAddress is { } secondary) lines.Add($"Second caption: {secondary}");
            if (selectedEntry?.Message is { } message) lines.Add($"Original style value: {message.NativeStyle}");
            lines.Add("Addresses refer to the original executable image; CIL evidence uses synthetic IDA addresses.");
            lines.Add("");
            lines.AddRange(catalog.Evidence);
            return string.Join(Environment.NewLine, lines);
        }
    }

    private void RefreshDetails()
    {
        foreach (string property in new[] { nameof(HasSelection), nameof(IsRuntimeMessage), nameof(IsClosePrompt),
            nameof(SelectedTitle), nameof(SelectedIdentity), nameof(SelectedSummary), nameof(OriginalText),
            nameof(PrimaryButtonText), nameof(SecondaryButtonText), nameof(HasSecondaryButton),
            nameof(PrimaryEffect), nameof(SecondaryEffect), nameof(PromptBehavior), nameof(SourceAnchors) })
            Changed(property);
    }
}
