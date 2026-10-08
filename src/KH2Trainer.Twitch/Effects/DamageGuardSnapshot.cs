using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>Guard effectiveness, owner and actor identity from one fresh native publication.</summary>
public readonly record struct DamageGuardSnapshot(bool Available, ActorMovementIdentity Identity,
    GameplayState Gameplay, bool Effective, ulong Owner)
{
    public static readonly DamageGuardSnapshot Unavailable = new(false, default, GameplayState.Unavailable, false, 0);
    public bool CanEnsure => Available && Identity.Known && Gameplay.IsControllable;

    public static DamageGuardSnapshot FromSnapshot(TrainerSnapshot snapshot, uint now)
    {
        if (snapshot.ProtocolVersion != 4 || !GameplayState.HasFreshPublication(snapshot, now) || !snapshot.Supports(472) ||
            !Integer(snapshot, 106, 1, out uint effective) || !Integer(snapshot, 471, 2, out uint observer) ||
            !Integer(snapshot, 467, uint.MaxValue, out uint gl) || !Integer(snapshot, 468, uint.MaxValue, out uint gh) ||
            !Integer(snapshot, 469, uint.MaxValue, out uint bl) || !Integer(snapshot, 470, uint.MaxValue, out uint bh) ||
            !Integer(snapshot, 473, uint.MaxValue, out uint ol) || !Integer(snapshot, 474, uint.MaxValue, out uint oh)) return Unavailable;
        var identity = new ActorMovementIdentity(bl | ((ulong)bh << 32), gl | ((ulong)gh << 32));
        ulong owner = ol | ((ulong)oh << 32);
        if (identity.BridgeInstance == 0 || effective == 0 && owner != 0 || effective != 0 && (observer != 1 || !identity.Known)) return Unavailable;
        // A fresh bridge nonce remains useful for cleanup after observer failure. It never permits Ensure.
        var gameplay = observer == 1 ? GameplayState.FromSnapshot(snapshot, now) : GameplayState.Unavailable;
        return new(true, identity, gameplay, effective != 0, owner);
    }

    private static bool Integer(TrainerSnapshot snapshot, int slot, uint max, out uint result)
    {
        result = 0;
        if (!snapshot.HasValue(slot) || !snapshot.Supports(slot)) return false;
        double value = snapshot.Values[slot];
        if (!double.IsFinite(value) || value < 0 || value > max || value != Math.Truncate(value)) return false;
        result = (uint)value; return true;
    }
}
