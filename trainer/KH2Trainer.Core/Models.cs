using System.Text.Json;
using System.Text.Json.Serialization;

namespace KH2Trainer.Core;

public enum FeatureKind { Number, Toggle, Action, Choice, ReadOnly }
public sealed record FeatureChoice(string Label, double Value);
public sealed record Evidence(string Address, string Finding, string Level);
public sealed class FeatureArgument
{
    public required string Name { get; init; }
    public double Minimum { get; init; }
    public double Maximum { get; init; }
    public double DefaultValue { get; init; }
    public string Catalog { get; init; } = "";
    public IReadOnlyList<FeatureChoice> Choices { get; init; } = [];
}

public sealed class FeatureDefinition
{
    public required string Id { get; init; }
    public required string Category { get; init; }
    public required string Name { get; init; }
    public required string Description { get; init; }
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public FeatureKind Kind { get; init; }
    public int CommandId { get; init; }
    public int ValueSlot { get; init; } = -1;
    public int CapabilitySlot { get; init; } = -1;
    public double Minimum { get; init; }
    public double Maximum { get; init; }
    public double DefaultValue { get; init; }
    public double Step { get; init; } = 1;
    public string Unit { get; init; } = "";
    public bool RequiresScene { get; init; } = true;
    public bool ChangesProgression { get; init; }
    public bool CanSaveInProfile { get; init; }
    public string RestoreBehavior { get; init; } = "";
    public IReadOnlyList<FeatureChoice> Choices { get; init; } = [];
    public IReadOnlyList<Evidence> Evidence { get; init; } = [];
    public IReadOnlyList<FeatureArgument> Arguments { get; init; } = [];
    public void Validate()
    {
        if (string.IsNullOrWhiteSpace(Id) || string.IsNullOrWhiteSpace(Name) || string.IsNullOrWhiteSpace(Category))
            throw new InvalidDataException("Feature identity is missing.");
        if (!double.IsFinite(Minimum) || !double.IsFinite(Maximum) || Minimum > Maximum)
            throw new InvalidDataException($"Invalid range for {Id}.");
        if (ValueSlot < -1 || ValueSlot >= BridgeProtocol.ValueCount || CapabilitySlot < -1 || CapabilitySlot >= BridgeProtocol.ValueCount)
            throw new InvalidDataException($"Invalid protocol slot for {Id}.");
        if (Kind != FeatureKind.ReadOnly && CommandId <= 0)
            throw new InvalidDataException($"Missing command for {Id}.");
        if (Evidence.Count == 0) throw new InvalidDataException($"Missing implementation evidence for {Id}.");
        if (Arguments.Count > 8 || Arguments.Any(a => !double.IsFinite(a.Minimum) || !double.IsFinite(a.Maximum) || a.Minimum > a.Maximum))
            throw new InvalidDataException($"Invalid command arguments for {Id}.");
    }
    public bool IsValidValue(double value) => double.IsFinite(value) && value >= Minimum && value <= Maximum &&
        (Kind != FeatureKind.Choice || Choices.Any(c => c.Value == value));
}

public static class FeatureCatalog
{
    public static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true, WriteIndented = true };
    public static IReadOnlyList<FeatureDefinition> Load(Stream stream)
    {
        var features = JsonSerializer.Deserialize<List<FeatureDefinition>>(stream, JsonOptions) ?? [];
        foreach (var feature in features) feature.Validate();
        if (features.Select(f => f.Id).Distinct(StringComparer.Ordinal).Count() != features.Count)
            throw new InvalidDataException("Duplicate feature IDs.");
        return features;
    }
}

public sealed record GameProcess(int Pid, string Name, string Path);
public sealed record BridgeResult(int Sequence, int Code, string Message)
{
    public bool Success => Code == 0;
}
public sealed record TrainerSnapshot
{
    public static readonly TrainerSnapshot Disconnected = new();
    public bool Connected { get; init; }
    public bool SceneReady { get; init; }
    public int Status { get; init; }
    public int ErrorCode { get; init; }
    public uint FrameCount { get; init; }
    public uint Flags { get; init; }
    public string Message { get; init; } = "Start KINGDOM HEARTS II FINAL MIX to connect.";
    public double[] Values { get; init; } = new double[BridgeProtocol.ValueCount];
    public ulong[] Valid { get; init; } = new ulong[BridgeProtocol.MaskWordCount];
    public ulong[] Supported { get; init; } = new ulong[BridgeProtocol.MaskWordCount];
    public bool HasValue(int slot) => slot >= 0 && slot < Values.Length && slot / 64 < Valid.Length && (Valid[slot / 64] & (1UL << (slot % 64))) != 0;
    public bool Supports(int slot) => slot >= 0 && slot < Values.Length && slot / 64 < Supported.Length && (Supported[slot / 64] & (1UL << (slot % 64))) != 0;
}

public sealed record TrainerProfile
{
    public int Version { get; init; } = 1;
    public required string Name { get; init; }
    public string GameHash { get; init; } = TargetGame.Sha256;
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;
    public Dictionary<string, double> Values { get; init; } = new(StringComparer.Ordinal);
}
