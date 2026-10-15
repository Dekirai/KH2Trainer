using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>Published guard mode (slot 483). Lethal-only forwards every hit that leaves the character standing.</summary>
public enum DamageGuardMode { Off = 0, Full = 1, LethalOnly = 2 }

/// <summary>Guard effectiveness, mode, owner and actor identity from one fresh native publication.</summary>
public readonly record struct DamageGuardSnapshot(bool Available, ActorMovementIdentity Identity,
    GameplayState Gameplay, DamageGuardMode Mode, ulong Owner)
{
    public static readonly DamageGuardSnapshot Unavailable = new(false, default, GameplayState.Unavailable, DamageGuardMode.Off, 0);
    public bool Effective => Mode != DamageGuardMode.Off;
    public bool CanEnsure => Available && Identity.Known && Gameplay.IsControllable;

    public static DamageGuardSnapshot FromSnapshot(TrainerSnapshot snapshot, uint now)
    {
        if (snapshot.ProtocolVersion != 4 || !GameplayState.HasFreshPublication(snapshot, now) || !snapshot.Supports(472) ||
            !Integer(snapshot, 106, 1, out uint full) || !Integer(snapshot, 483, 2, out uint published) || !Integer(snapshot, 471, 2, out uint observer) ||
            !Integer(snapshot, 467, uint.MaxValue, out uint gl) || !Integer(snapshot, 468, uint.MaxValue, out uint gh) ||
            !Integer(snapshot, 469, uint.MaxValue, out uint bl) || !Integer(snapshot, 470, uint.MaxValue, out uint bh) ||
            !Integer(snapshot, 473, uint.MaxValue, out uint ol) || !Integer(snapshot, 474, uint.MaxValue, out uint oh)) return Unavailable;
        var identity = new ActorMovementIdentity(bl | ((ulong)bh << 32), gl | ((ulong)gh << 32));
        ulong owner = ol | ((ulong)oh << 32);
        var mode = (DamageGuardMode)published;
        // Slot 106 must agree with an off or full guard; a lethal-only guard does not depend on its full toggle.
        bool consistent = mode switch { DamageGuardMode.Off => full == 0 && owner == 0, DamageGuardMode.Full => full == 1, _ => true };
        if (identity.BridgeInstance == 0 || !consistent || mode != DamageGuardMode.Off && (observer != 1 || !identity.Known)) return Unavailable;
        // A fresh bridge nonce remains useful for cleanup after observer failure. It never permits Ensure.
        var gameplay = observer == 1 ? GameplayState.FromSnapshot(snapshot, now) : GameplayState.Unavailable;
        return new(true, identity, gameplay, mode, owner);
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
