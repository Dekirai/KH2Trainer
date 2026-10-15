namespace KH2Trainer.Core;

/// <summary>Voluntary Revert lock ownership from one fresh bridge publication; independent of actor hooks.</summary>
public readonly record struct DriveRevertLockSnapshot(bool Available, int State, ulong Owner, ulong BridgeInstance)
{
    public static readonly DriveRevertLockSnapshot Unavailable = new(false, 0, 0, 0);
    public bool Effective => Available && State == 1;
    public bool CleanupPending => Available && State == 2;

    public static DriveRevertLockSnapshot FromSnapshot(TrainerSnapshot snapshot, uint now)
    {
        if (snapshot.ProtocolVersion != 4 || !GameplayState.HasFreshPublication(snapshot, now) ||
            !Integer(snapshot, 488, 2, out uint state) ||
            !Integer(snapshot, 489, uint.MaxValue, out uint ol) || !Integer(snapshot, 490, uint.MaxValue, out uint oh) ||
            !Integer(snapshot, 491, uint.MaxValue, out uint bl) || !Integer(snapshot, 492, uint.MaxValue, out uint bh)) return Unavailable;
        ulong owner = ol | ((ulong)oh << 32), bridge = bl | ((ulong)bh << 32);
        if (bridge == 0 || (state == 0) != (owner == 0)) return Unavailable;
        return new(true, (int)state, owner, bridge);
    }

    private static bool Integer(TrainerSnapshot snapshot, int slot, uint maximum, out uint result)
    {
        result = 0;
        if (!snapshot.Supports(slot) || !snapshot.HasValue(slot)) return false;
        double value = snapshot.Values[slot];
        if (!double.IsFinite(value) || value < 0 || value > maximum || value != Math.Truncate(value)) return false;
        result = (uint)value;
        return true;
    }
}
