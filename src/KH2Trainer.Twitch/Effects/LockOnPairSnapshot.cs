using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>Two exact Float32 globals and their native default from one publication.</summary>
public readonly record struct LockOnPairSnapshot(bool Available, uint ScaleBits, uint BreakBits, uint RetainBits)
{
    public static readonly LockOnPairSnapshot Unavailable = default;
    public float Scale => BitConverter.UInt32BitsToSingle(ScaleBits);
    public float BreakDistance => BitConverter.UInt32BitsToSingle(BreakBits);
    public float RetainDefault => BitConverter.UInt32BitsToSingle(RetainBits);
    internal static bool ValidPair(uint scale, uint distance) =>
        BitConverter.UInt32BitsToSingle(scale) is var s && float.IsFinite(s) && s is >= .05f and <= 10f &&
        BitConverter.UInt32BitsToSingle(distance) is var d && float.IsFinite(d) && d is > 0f and <= 10_000_000f;
    internal bool CanApply(float scale) => Available && ValidPair(ScaleBits, BreakBits) &&
        float.IsFinite(RetainDefault) && RetainDefault is >= .000001f and <= 1_000_000f &&
        ValidPair(BitConverter.SingleToUInt32Bits(scale), BitConverter.SingleToUInt32Bits(scale * RetainDefault));

    public static LockOnPairSnapshot FromSnapshot(TrainerSnapshot snapshot, uint now)
    {
        if (snapshot.ProtocolVersion != 4 || !snapshot.SceneReady || !GameplayState.HasFreshPublication(snapshot, now) ||
            !Bits(snapshot, 475, out uint scale) || !Bits(snapshot, 476, out uint distance) ||
            !snapshot.Supports(373) || !snapshot.HasValue(373)) return Unavailable;
        double retain = snapshot.Values[373];
        if (!double.IsFinite(retain) || retain is < .000001 or > 1_000_000 || (double)(float)retain != retain ||
            !ValidPair(scale, distance)) return Unavailable;
        return new(true, scale, distance, BitConverter.SingleToUInt32Bits((float)retain));
    }

    private static bool Bits(TrainerSnapshot snapshot, int slot, out uint value)
    {
        value = 0;
        if (!snapshot.Supports(slot) || !snapshot.HasValue(slot)) return false;
        double raw = snapshot.Values[slot];
        if (!double.IsFinite(raw) || raw < 0 || raw > uint.MaxValue || raw != Math.Truncate(raw)) return false;
        value = (uint)raw; return true;
    }
}
