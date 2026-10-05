namespace KH2Trainer;

/// <summary>
/// Groups the catalog's many small categories into a few sections with tabs.
/// Categories missing from this table still appear, in a "More" section.
/// </summary>
public static class CategoryLayout
{
    public sealed record Section(string Key, string Title, string Icon, string Subtitle);
    public sealed record Placement(string Category, string Section, string Tab);

    public static readonly IReadOnlyList<Section> Sections =
    [
        new("sora", "Sora", "", "Health, stats, Drive Forms, position and movement."),
        new("combat", "Combat", "", "Practice helpers, damage scaling, targeting and loot."),
        new("progression", "Progression", "", "EXP, munny, boosts, inventory, abilities and equipment."),
        new("world", "World", "", "Travel, party, time, missions and Mickey rescues."),
        new("display", "Camera & Display", "", "Camera, display previews, window size and anti-aliasing."),
        new("gummi", "Gummi Ship", "", "Ship status, flight controls and the Gummi editor."),
        new("audio", "Audio", "", "Volume mix, spatial listeners and mixer diagnostics."),
        new("advanced", "Advanced", "", "Developer tools, shortcuts and engine diagnostics."),
        new("more", "More", "", "Additional catalog features."),
    ];

    /// <summary>Display order: tabs appear in the order of their first category.</summary>
    public static readonly IReadOnlyList<Placement> Placements =
    [
        new("Player", "sora", "Status"),
        new("Live Stats", "sora", "Status"),
        new("Drive and Forms", "sora", "Drive Forms"),
        new("Position", "sora", "Position"),
        new("Sora movement", "sora", "Movement"),
        new("Animation", "sora", "Animation"),
        new("Combat Practice", "combat", "Practice"),
        new("Damage Tuning", "combat", "Damage"),
        new("Targeting", "combat", "Targeting"),
        new("Loot and Collection", "combat", "Loot"),
        new("Progression", "progression", "EXP & Munny"),
        new("Progression - Stats", "progression", "Stat Boosts"),
        new("Progression - Forms", "progression", "Forms & Summons"),
        new("Inventory", "progression", "Inventory"),
        new("Abilities", "progression", "Abilities"),
        new("Equipment", "progression", "Equipment"),
        new("World", "world", "Travel & Party"),
        new("Time", "world", "Time & Field"),
        new("Practice", "world", "Time & Field"),
        new("Missions", "world", "Missions"),
        new("Mickey Rescue", "world", "Mickey Rescue"),
        new("Camera", "display", "Camera"),
        new("Display", "display", "Display"),
        new("Display previews", "display", "Display"),
        new("Window and Resolution", "display", "Window"),
        new("Renderer MSAA", "display", "Anti-aliasing"),
        new("Gummi", "gummi", "Ship"),
        new("Gummi controls", "gummi", "Flight"),
        new("Gummi Editor", "gummi", "Editor"),
        new("Audio Mix", "audio", "Mix"),
        new("Spatial Audio", "audio", "Spatial"),
        new("Audio Diagnostics", "audio", "Mixer"),
        new("Developer Tools", "advanced", "Tools"),
        new("Keyboard Shortcuts", "advanced", "Tools"),
        new("Graphics Diagnostics", "advanced", "Graphics"),
        new("Renderer Timing", "advanced", "Renderer"),
        new("Renderer Resources", "advanced", "Renderer"),
        new("Collision diagnostics", "advanced", "Collision"),
    ];

    public static Placement Place(string category) =>
        Placements.FirstOrDefault(p => string.Equals(p.Category, category, StringComparison.OrdinalIgnoreCase)) ?? new(category, "more", category);

    /// <summary>Builds the feature sections in display order. Empty sections are omitted.</summary>
    public static IReadOnlyList<FeatureSectionVm> Build(IReadOnlyList<FeatureVm> features)
    {
        var order = Placements.Select((p, i) => (p.Category, i)).ToDictionary(x => x.Category, x => x.i, StringComparer.OrdinalIgnoreCase);
        var categories = features.Select(f => f.Category).Distinct()
            .OrderBy(c => order.TryGetValue(c, out int i) ? i : int.MaxValue).ToArray();
        var sections = new List<FeatureSectionVm>();
        foreach (var section in Sections)
        {
            var tabs = categories.Select(Place).Where(p => p.Section == section.Key)
                .GroupBy(p => p.Tab)
                .Select(tab => new TabVm(tab.Key, tab.Select(p => FeatureGroupVm.Create(p.Category, features.Where(f => f.Category == p.Category))).ToArray()))
                .ToArray();
            if (tabs.Length > 0) sections.Add(new FeatureSectionVm(section, tabs));
        }
        return sections;
    }
}

/// <summary>One catalog category: its controls in a list and its readouts in a compact grid.</summary>
public sealed class FeatureGroupVm
{
    public string Title { get; }
    public bool ShowTitle { get; set; }
    public IReadOnlyList<FeatureVm> Controls { get; }
    public IReadOnlyList<FeatureVm> Readouts { get; }
    public bool HasControls => Controls.Count > 0;
    public bool HasReadouts => Readouts.Count > 0;
    public FeatureGroupVm(string title, IReadOnlyList<FeatureVm> controls, IReadOnlyList<FeatureVm> readouts)
    {
        Title = title; Controls = controls; Readouts = readouts;
    }
    public static FeatureGroupVm Create(string title, IEnumerable<FeatureVm> features)
    {
        var list = features.ToArray();
        return new FeatureGroupVm(title, list.Where(f => f.IsEditable).ToArray(), list.Where(f => f.IsReadOnly).ToArray());
    }
}

public sealed class TabVm
{
    public string Title { get; }
    public IReadOnlyList<FeatureGroupVm> Groups { get; }
    public TabVm(string title, IReadOnlyList<FeatureGroupVm> groups)
    {
        Title = title; Groups = groups;
        // A single category is already named by its tab.
        foreach (var group in groups) group.ShowTitle = groups.Count > 1;
    }
}

/// <summary>Base for everything the sidebar can show.</summary>
public abstract class PageVm : Observable
{
    public abstract string Title { get; }
    public abstract string Icon { get; }
    public abstract string Subtitle { get; }
    /// <summary>Sidebar group heading.</summary>
    public virtual string Group => "TRAINER";
    /// <summary>Feature pages show the connection banner when controls are unavailable.</summary>
    public virtual bool UsesGame => false;
}

public sealed class FeatureSectionVm : PageVm
{
    private readonly CategoryLayout.Section section;
    private TabVm selectedTab;
    public FeatureSectionVm(CategoryLayout.Section section, IReadOnlyList<TabVm> tabs)
    {
        this.section = section; Tabs = tabs; selectedTab = tabs[0];
    }
    public string Key => section.Key;
    public override string Title => section.Title;
    public override string Icon => section.Icon;
    public override string Subtitle => section.Subtitle;
    public override bool UsesGame => true;
    public IReadOnlyList<TabVm> Tabs { get; }
    public bool ShowTabs => Tabs.Count > 1;
    public TabVm SelectedTab { get => selectedTab; set { if (value != null) Set(ref selectedTab, value); } }
}

/// <summary>Wraps a tool view model (Asset Explorer, Game Messages, ...) for the sidebar.</summary>
public sealed class ToolPageVm(string title, string icon, string subtitle, object content, string group = "TOOLS") : PageVm
{
    public override string Title => title;
    public override string Icon => icon;
    public override string Subtitle => subtitle;
    public override string Group => group;
    public object Content { get; } = content;
}
