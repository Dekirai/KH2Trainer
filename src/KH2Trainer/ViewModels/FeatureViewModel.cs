using System.Globalization;
using KH2Trainer.Core;

namespace KH2Trainer;

/// <summary>What a feature row needs from the shell. Keeps rows testable without a game session.</summary>
public interface IFeatureHost
{
    bool Busy { get; }
    bool ShowDescriptions { get; }
    bool IsFavorite(string featureId);
    void ToggleFavorite(FeatureVm feature);
    Task Execute(int command, IReadOnlyList<double> arguments, string label);
}

public sealed class ArgumentVm : Observable
{
    public FeatureArgument Definition { get; }
    public string Name => Definition.Name;
    public IReadOnlyList<FeatureChoice> Choices { get; }
    public bool IsChoice => Choices.Count > 0;
    public bool IsNumber => !IsChoice;
    /// <summary>Large catalogs (items, abilities) get a wider, searchable picker.</summary>
    public double InputWidth => IsChoice ? Choices.Count > 24 ? 260 : 170 : 110;
    public string RangeText => $"{Definition.Minimum:g} – {Definition.Maximum:g}";
    private string valueText;
    public string ValueText { get => valueText; set => Set(ref valueText, value); }
    private FeatureChoice? choice;
    public FeatureChoice? SelectedChoice { get => choice; set => Set(ref choice, value); }
    public ArgumentVm(FeatureArgument definition, IReadOnlyDictionary<string, IReadOnlyList<FeatureChoice>> catalogs)
    {
        Definition = definition; valueText = definition.DefaultValue.ToString(CultureInfo.InvariantCulture);
        Choices = (definition.Choices.Count > 0 ? definition.Choices : catalogs.GetValueOrDefault(definition.Catalog) ?? [])
            .Where(c => c.Value >= definition.Minimum && c.Value <= definition.Maximum).ToArray();
        choice = Choices.FirstOrDefault(c => c.Value == definition.DefaultValue) ?? Choices.FirstOrDefault();
    }
    public double Read()
    {
        double value = IsChoice ? SelectedChoice?.Value ?? throw new ArgumentException($"Choose {Name}.") :
            double.TryParse(ValueText, NumberStyles.Float, CultureInfo.InvariantCulture, out double parsed) ? parsed : throw new ArgumentException($"Enter a number for {Name}.");
        if (!double.IsFinite(value) || value < Definition.Minimum || value > Definition.Maximum) throw new ArgumentException($"{Name} must be between {Definition.Minimum} and {Definition.Maximum}.");
        return value;
    }
}

/// <summary>One catalog feature: a control (number, switch, choice or action) or a live readout.</summary>
public sealed class FeatureVm : Observable
{
    private readonly IFeatureHost host;
    private string valueText, liveValue = "—", availability = "Connect to the game to use this feature.";
    private bool toggleValue, available, dirty, applying, lastCanToggle;
    private FeatureChoice? choice;

    public FeatureDefinition Definition { get; }
    public string Id => Definition.Id;
    public string Name => Definition.Name;
    public string Description => Definition.Description;
    public string Category => Definition.Category;

    public bool IsNumber => Definition.Kind == FeatureKind.Number;
    public bool IsToggle => Definition.Kind == FeatureKind.Toggle;
    public bool IsChoice => Definition.Kind == FeatureKind.Choice;
    public bool IsAction => Definition.Kind == FeatureKind.Action;
    public bool IsReadOnly => Definition.Kind == FeatureKind.ReadOnly;
    public bool IsEditable => !IsReadOnly;
    public bool HasArguments => Arguments.Count > 0;
    public bool ShowValueInput => IsNumber && !HasArguments;
    public bool ShowChoiceInput => IsChoice && !HasArguments;
    /// <summary>Switches apply as soon as they are flipped; everything else has an explicit button.</summary>
    public bool ShowApplyButton => IsEditable && !IsToggle;
    public bool ShowLiveValue => Definition.ValueSlot >= 0 && !IsToggle;
    public bool ShowUnit => ShowValueInput && UnitText.Length > 0;
    public bool ChangesProgression => Definition.ChangesProgression;
    public bool ShowDescription => host.ShowDescriptions;

    public string ApplyLabel => Definition.Id switch
    {
        "drive.trigger" => "Transform",
        "drive.revert" => "Revert",
        "drive.cancel" => "Cancel",
        "audio.reset" => "Apply",
        _ => IsAction ? "Run" : "Apply"
    };
    public string UnitText => Definition.Unit;
    public string RangeText => $"Allowed: {Definition.Minimum:g} – {Definition.Maximum:g}{(UnitText.Length > 0 ? " " + UnitText : "")}. Press Enter to apply.";
    public IReadOnlyList<FeatureChoice> Choices => Definition.Choices;
    public IReadOnlyList<ArgumentVm> Arguments { get; }

    public string ValueText { get => valueText; set { if (Set(ref valueText, value)) dirty = true; } }
    public FeatureChoice? SelectedChoice { get => choice; set { if (Set(ref choice, value)) dirty = true; } }
    public bool ToggleValue
    {
        get => toggleValue;
        set
        {
            if (!Set(ref toggleValue, value)) return;
            if (ApplyCommand.CanExecute(null)) { dirty = true; ApplyCommand.Execute(null); }
            else dirty = false; // The next snapshot restores the actual state.
        }
    }
    public string LiveValue { get => liveValue; private set => Set(ref liveValue, value); }
    public string Availability { get => availability; private set { if (Set(ref availability, value)) Changed(nameof(ToolTipText)); } }
    public bool IsAvailable { get => available; private set => Set(ref available, value); }
    public bool CanToggle => available && !applying && !host.Busy;
    public string ToolTipText => Description + (Availability.Length > 0 ? "\n\n" + Availability : "");

    public bool IsFavorite => host.IsFavorite(Id);
    public AsyncCommand ApplyCommand { get; }
    public RelayCommand ToggleFavoriteCommand { get; }

    public FeatureVm(FeatureDefinition definition, IFeatureHost host, IReadOnlyDictionary<string, IReadOnlyList<FeatureChoice>> catalogs)
    {
        Definition = definition; this.host = host;
        valueText = definition.DefaultValue.ToString(CultureInfo.InvariantCulture);
        choice = Choices.FirstOrDefault(c => c.Value == definition.DefaultValue) ?? Choices.FirstOrDefault();
        Arguments = definition.Arguments.Select(a => new ArgumentVm(a, catalogs)).ToArray();
        ApplyCommand = new AsyncCommand(Apply, () => available && !host.Busy);
        ToggleFavoriteCommand = new RelayCommand(() => host.ToggleFavorite(this));
    }

    public bool Matches(string query) =>
        Name.Contains(query, StringComparison.OrdinalIgnoreCase) || Description.Contains(query, StringComparison.OrdinalIgnoreCase) ||
        Category.Contains(query, StringComparison.OrdinalIgnoreCase) || Id.Contains(query, StringComparison.OrdinalIgnoreCase);

    public double ReadValue()
    {
        double value = IsToggle ? ToggleValue ? 1 : 0 : IsChoice ? SelectedChoice?.Value ?? throw new ArgumentException($"Choose a value for {Name}.") :
            double.TryParse(ValueText, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) ? number : throw new ArgumentException($"Enter a number for {Name}.");
        if (!Definition.IsValidValue(value)) throw new ArgumentException($"{Name}: use a value between {Definition.Minimum} and {Definition.Maximum}.");
        return value;
    }

    /// <summary>
    /// Shows a value for review (for example from a profile) without applying it.
    /// Switches keep mirroring the game, because flipping one applies it at once.
    /// </summary>
    public void SetInput(double value)
    {
        if (IsToggle) return;
        valueText = value.ToString(CultureInfo.InvariantCulture);
        choice = Choices.FirstOrDefault(c => c.Value == value); dirty = true;
        Changed(nameof(ValueText), nameof(SelectedChoice));
    }

    /// <summary>The value was sent by other means (a profile); follow the game again.</summary>
    public void MarkApplied() => dirty = false;

    public void RefreshCanToggle()
    {
        bool canToggle = CanToggle;
        if (canToggle != lastCanToggle) { lastCanToggle = canToggle; Changed(nameof(CanToggle)); }
    }

    public void RefreshPresentation() { lastCanToggle = CanToggle; Changed(nameof(IsFavorite), nameof(ShowDescription), nameof(CanToggle)); }

    public void Update(TrainerSnapshot snapshot)
    {
        IsAvailable = snapshot.Connected && snapshot.Status >= 1 && snapshot.Supports(Definition.CapabilitySlot) && (!Definition.RequiresScene || snapshot.SceneReady);
        bool hasValue = snapshot.HasValue(Definition.ValueSlot);
        LiveValue = hasValue ? FeatureFormatting.Format(Definition, snapshot.Values[Definition.ValueSlot]) : "—";
        if (!dirty && hasValue)
        {
            // Mirror the game's value into the inputs, raising events only for real changes.
            double current = snapshot.Values[Definition.ValueSlot];
            string text = current.ToString("0.###", CultureInfo.InvariantCulture);
            var currentChoice = Choices.FirstOrDefault(c => c.Value == current);
            if (valueText != text) { valueText = text; Changed(nameof(ValueText)); }
            if (toggleValue != (current != 0)) { toggleValue = current != 0; Changed(nameof(ToggleValue)); }
            if (choice != currentChoice) { choice = currentChoice; Changed(nameof(SelectedChoice)); }
        }
        Availability = !snapshot.Connected ? "Connect to the game to use this feature."
            : !snapshot.Supports(Definition.CapabilitySlot) ? "This bridge does not provide this feature."
            : Definition.RequiresScene && !snapshot.SceneReady ? "Load a playable scene first."
            : Definition.ChangesProgression ? "Changes the loaded game state. Saving in the game can make it permanent."
            : Definition.RestoreBehavior;
        RefreshCanToggle();
        ApplyCommand.Refresh();
    }

    private async Task Apply()
    {
        var arguments = Arguments.Count > 0 ? Arguments.Select(a => a.Read()).ToArray() : IsAction ? Array.Empty<double>() : [ReadValue()];
        applying = true; lastCanToggle = false; Changed(nameof(CanToggle));
        try { await host.Execute(Definition.CommandId, arguments, Name); dirty = false; }
        catch { if (IsToggle) dirty = false; throw; } // A failed switch snaps back to the game's state.
        finally { applying = false; lastCanToggle = CanToggle; Changed(nameof(CanToggle)); }
    }
}

/// <summary>Readable labels for enumerated readouts. Unknown values never show as a measured zero.</summary>
public static class FeatureFormatting
{
    public static string Format(FeatureDefinition definition, double value)
    {
        string? label = definition.CapabilitySlot switch
        {
            124 => value switch { 0 => "None", 1 => "Valor", 2 => "Wisdom", 3 => "Limit", 4 => "Master", 5 => "Final", 6 => "Antiform", _ => "Unknown" },
            125 => value switch { 0 => "Idle", 1 => "Reverting to switch", 2 => "Transforming", 3 => "Reverting", _ => "Unknown" },
            127 => value switch { 0 => "—", 1 => "Queued", 2 => "Completed", 3 => "Cancelled", 4 => "Scene changed", 5 => "Disconnected", 6 => "Timed out", 7 => "Conditions changed", 8 => "Transition not started", _ => "Unknown" },
            159 or 408 => value == 1 ? "Available" : "Unavailable or busy",
            414 => value switch { 1 => "Base", 2 => "Point", 3 => "Line", _ => "Unknown" },
            426 => value switch { 1 => "Edit", 4 => "Preview", _ => "Unknown" },
            435 => value switch { 0 => "Windowed", 1 => "Fullscreen", 2 => "Maximized", _ => "Unknown" },
            436 => value == 1 ? "Pending" : "Idle",
            449 => value switch { 0 => "Native", 1 => "Fixed", 2 => "Maximum", _ => "Unknown" },
            455 => value switch { 0 => "Not installed", 1 => "Resident", 2 => "Restart required", _ => "Unknown" },
            456 => value == 1 ? "Verified" : "Unavailable",
            457 => value switch { 1 => "Sora", 2 => "Roxas", 3 => "Rescue Mickey", 4 => "Other actor", _ => "Unknown" },
            458 => FormatControlBlockers(value),
            459 => value == 1 ? "Controllable" : "Waiting",
            465 => FormatColorState(value),
            460 => value switch { 0 => "Inactive", 1 => "Running", 2 => "Paused", 3 => "Closing", _ => "Unknown" },
            462 => value switch { 0 => "Base", 1 => "Valor", 2 => "Wisdom", 3 => "Limit", 4 => "Master", 5 => "Final", 6 => "Antiform", 10 => "Dual-wield Roxas", 11 => "Rescue Mickey", _ => "Unknown" },
            169 => value switch { 0 => "Prototype", 1 => "RAW", _ => "Unknown" },
            170 => value switch { 0 => "Off", 1 => "Active", 2 => "Disabled", 3 => "Changed by game script", 4 => "Changed externally", 5 => "Player or scene changed", 6 => "Disconnected", 7 => "Game or mod took control", 8 => "Animation data unavailable", 9 => "Animation override unavailable", _ => "Unknown" },
            179 or 183 or 229 or 246 => value == 1 ? "Yes" : "No",
            180 => value == 1 ? "Active" : "Inactive",
            211 => value switch { 0 => "Count up", 1 => "Count down", _ => "Unknown" },
            212 => value switch { 0 => "Stopped", 1 => "Armed", 2 => "Running", _ => "Unknown" },
            241 => value switch { 0 => "Follow", 1 => "Script", 2 => "Minigame", _ => "Unknown" },
            245 => value switch { 0 => "None", 1 => "Recenter queued", 2 => "Snap queued", _ => "Unknown" },
            _ => null
        };
        if (label != null) return label;
        if (definition.Id == "player.form.id")
            return value switch { 0 => "Base Sora", 1 => "Valor", 2 => "Wisdom", 3 => "Limit", 4 => "Master", 5 => "Final", 6 => "Antiform", _ => value.ToString("0.###", CultureInfo.InvariantCulture) };
        return value.ToString("0.###", CultureInfo.InvariantCulture) + (definition.Unit.Length > 0 ? " " + definition.Unit : "");
    }

    private static string FormatColorState(double value)
    {
        if (value == 0) return "Off";
        if (!double.IsFinite(value) || value != Math.Truncate(value) || value < 17 || value > 58) return "Unknown";
        int mode = (int)value / 16, strength = (int)value % 16;
        return mode is >= 1 and <= 3 && strength is >= 1 and <= 10 ? $"Mode {mode} · {strength}/10" : "Unknown";
    }

    private static string FormatControlBlockers(double value)
    {
        if (!double.IsFinite(value) || value < 0 || value > 1023 || value != Math.Truncate(value)) return "Unknown";
        if (value == 0) return "None";
        string[] names = ["Unknown", "Loading", "Menu", "Event", "Transition", "No player", "Dead", "Input locked", "Trainer pause", "Trainer freeze"];
        return string.Join(", ", names.Where((_, bit) => ((uint)value & (1u << bit)) != 0));
    }
}
