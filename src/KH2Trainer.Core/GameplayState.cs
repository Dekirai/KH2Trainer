namespace KH2Trainer.Core;

public enum PlayerRole { Unknown, Sora, Roxas, Mickey, Other }

[Flags]
public enum GameplayBlockers : uint
{
    None = 0, Unknown = 1, Loading = 2, Menu = 4, Cutscene = 8,
    Transition = 16, NoPlayer = 32, Dead = 64, InputBlocked = 128,
    TrainerFieldPause = 256, TrainerActorFreeze = 512
}

/// <summary>A fresh, read-only observation of whether the field player accepts control.</summary>
public readonly record struct GameplayState(bool Known, PlayerRole Role, GameplayBlockers Blockers)
{
    public static readonly GameplayState Unavailable = new(false, PlayerRole.Unknown, GameplayBlockers.Unknown);
    public bool IsControllable => Known && Role is PlayerRole.Sora or PlayerRole.Roxas or PlayerRole.Mickey && Blockers == GameplayBlockers.None;

    public const int KnownSlot = 456, RoleSlot = 457, BlockersSlot = 458, ControllableSlot = 459;
    public const int FieldModuleSlot = 460, CharacterSlot = 461, FormSlot = 462, PublicationTickSlot = 463;
    public const uint MaximumAgeMilliseconds = 1000;
    private const uint AllBlockers = 1023;

    /// <summary>Both processes use the same Windows uptime clock; unsigned subtraction handles its wrap.</summary>
    public static bool HasFreshPublication(TrainerSnapshot snapshot, uint now) =>
        snapshot.Connected && snapshot.Status >= 1 && snapshot.ErrorCode == 0 &&
        ReadInteger(snapshot, PublicationTickSlot, uint.MaxValue, out uint tick) &&
        unchecked(now - tick) <= MaximumAgeMilliseconds;

    public static GameplayState FromSnapshot(TrainerSnapshot snapshot, uint now)
    {
        if (!HasFreshPublication(snapshot, now) ||
            !ReadInteger(snapshot, KnownSlot, 1, out uint known) ||
            !ReadInteger(snapshot, RoleSlot, 4, out uint role) ||
            !ReadInteger(snapshot, BlockersSlot, AllBlockers, out uint blockers) ||
            !ReadInteger(snapshot, ControllableSlot, 1, out uint controllable)) return Unavailable;

        var state = new GameplayState(known == 1, (PlayerRole)role, (GameplayBlockers)blockers);
        // Reject a torn or incompatible semantic contract even if the transport was coherent.
        if (state.IsControllable != (controllable == 1)) return Unavailable;
        if (!snapshot.SceneReady) state = state with { Blockers = state.Blockers | GameplayBlockers.Loading };
        return state;
    }

    private static bool ReadInteger(TrainerSnapshot snapshot, int slot, uint maximum, out uint result)
    {
        result = 0;
        if (!snapshot.HasValue(slot) || !snapshot.Supports(slot)) return false;
        double value = snapshot.Values[slot];
        if (!double.IsFinite(value) || value < 0 || value > maximum || value != Math.Truncate(value)) return false;
        result = (uint)value;
        return true;
    }
}
