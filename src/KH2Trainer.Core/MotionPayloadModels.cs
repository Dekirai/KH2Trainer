using System.Collections.ObjectModel;

namespace KH2Trainer.Core;

/// <summary>Limits for copied, offline type9 root-motion data, not native resource safety.</summary>
public sealed record MotionReadLimits
{
    public int MaxPayloadBytes { get; init; } = 64 * 1024 * 1024;
    public int MaxTimeEntries { get; init; } = 16_384;
    public int MaxCurveRecords { get; init; } = 65_536;
    public int MaxRawFrames { get; init; } = 65_536;
    public int MaxDecodedElements { get; init; } = 2_000_000;
    public int MaxEvaluationSteps { get; init; } = 100_000;
    internal void Validate()
    {
        if (MaxPayloadBytes < 4 || MaxPayloadBytes > 256 * 1024 * 1024 ||
            MaxTimeEntries is < 1 or > 16_384 || MaxCurveRecords is < 1 or > 1_000_000 ||
            MaxRawFrames is < 1 or > 1_000_000 || MaxDecodedElements is < 1 or > 16_000_000 ||
            MaxEvaluationSteps is < 1 or > 10_000_000)
            throw new ArgumentOutOfRangeException(nameof(MotionReadLimits));
    }
}

public sealed class MotionPayloadException : FormatException
{
    public MotionPayloadException(string message) : base(message) { }
}

public enum MotionPayloadKind { Prototype = 0, Raw = 1 }

/// <summary>A copied row-major Float32 matrix. No public backing array is exposed.</summary>
public sealed class MotionMatrix
{
    private readonly float[] values;
    public ReadOnlyCollection<float> Values { get; }
    public float this[int row, int column] => (uint)row<4 && (uint)column<4
        ? values[row*4+column] : throw new ArgumentOutOfRangeException(nameof(row));
    public MotionMatrix(IEnumerable<float> values)
    {
        ArgumentNullException.ThrowIfNull(values);
        // Bound enumeration as well as the final allocation.
        this.values = values.Take(17).ToArray();
        if (this.values.Length != 16 || this.values.Any(x => !float.IsFinite(x)))
            throw new MotionPayloadException("A matrix needs exactly 16 finite Float32 values.");
        Values = Array.AsReadOnly(this.values);
    }
    internal float[] Copy() => (float[])values.Clone();
    public static MotionMatrix Identity { get; } = new(new float[] { 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1 });
}

public sealed record MotionRootSample(MotionMatrix Matrix, bool HasRoot, float EffectiveFrame,
    int? FirstRawFrame, int? SecondRawFrame, float? RawFraction)
{
    public string Binding => "OfflineMotionProjection";
    public bool EstablishesNativeMotionSafety => false;
}

/// <summary>Only the root path is decoded. Skeletal, IK, attachments, resource lifetime and native binding are excluded.</summary>
public sealed class MotionPayload
{
    public MotionPayloadKind Kind { get; }
    public bool HasRoot { get; }
    public int RawFrameCount => Matrices.Length;
    public int TimeCount => Times.Length;
    public string Binding => "OfflineMotionProjection";
    internal MotionReadLimits Limits { get; }
    internal float[] Times { get; }
    internal float[] Initial { get; }
    internal MotionCurve?[] Curves { get; }
    internal MotionMatrix[] Matrices { get; }
    internal float FrameOffset { get; }
    internal float FrameRate { get; }
    internal float LoopEnd { get; }
    internal float LoopStart { get; }
    internal MotionPayload(MotionPayloadKind kind, bool hasRoot, MotionReadLimits limits,
        float[]? times = null, float[]? initial = null, MotionCurve?[]? curves = null,
        MotionMatrix[]? matrices = null, float frameOffset = 0, float frameRate = 60,
        float loopEnd = 0, float loopStart = 0)
    {
        Kind = kind; HasRoot = hasRoot; Limits = limits;
        Times = times ?? []; Initial = initial ?? []; Curves = curves ?? [];
        Matrices = matrices ?? []; FrameOffset = frameOffset; FrameRate = frameRate;
        LoopEnd = loopEnd; LoopStart = loopStart;
    }
    public MotionRootSample Evaluate(float frame) => MotionRootEvaluator.Evaluate(this, frame);
}

internal sealed record MotionKey(int TimeIndex, int Interpolation, float Value, float In, float Out);
internal sealed record MotionCurve(byte Flags, MotionKey[] Keys);
