using System.Security.Cryptography;

namespace KH2Trainer.Core;

[Flags]
public enum MovementMask : uint { None = 0, Walk = 1, Run = 2, Fall = 4, Jump = 8, Speed = Walk | Run, Air = Fall | Jump, All = 15 }
public enum MovementOperation : uint { Acquire = 1, Reapply = 2, ReleaseIntent = 3, QueryOperation = 4, QueryLease = 5, AcknowledgeReceipt = 6 }
public enum MovementOutcome : uint { Invalid = 0, Applied = 1, Reapplied = 2, ReleaseAccepted = 3, LeaseObserved = 4, ReceiptAcknowledged = 5, OperationUnknown = 6, Rejected = 7 }
public enum MovementJournalState : uint { None = 0, Active = 1, ReleasePending = 2, Released = 3, Superseded = 4, Destroyed = 5, Uncertain = 6 }
public enum MovementReason : uint
{
    None = 0, UnsupportedSchema = 1, InvalidRequest = 2, StaleBridge = 3, ActorMismatch = 4, NotReady = 5,
    ExpectedMismatch = 6, InvalidValues = 7, JournalFull = 8, LeaseNotFound = 9, LeaseConflict = 10,
    RevisionMismatch = 11, RequestIdConflict = 12, ObserverUnavailable = 13, ObserverFault = 14,
    Expired = 15, HostExpired = 16, NoChange = 17, WriteFault = 18, ReceiptNotFound = 19, NotOwner = 20, WrongThread = 21
}
[Flags]
public enum MovementResponseFlags : uint { None = 0, IdentityKnown = 1, ObservedKnown = 2, HasReceipt = 4 }
public readonly record struct ActorMovementIdentity(ulong BridgeInstance, ulong Generation)
{
    public bool Known => BridgeInstance != 0 && Generation != 0;
}

/// <summary>Exact native Float32 bits; no mutable array or approximate ownership comparison.</summary>
public readonly record struct MovementValues(uint Walk, uint Run, uint Fall, uint Jump)
{
    public uint this[int index] => index switch { 0 => Walk, 1 => Run, 2 => Fall, 3 => Jump, _ => throw new ArgumentOutOfRangeException(nameof(index)) };
    public float Value(int index) => BitConverter.UInt32BitsToSingle(this[index]);
    public static MovementValues FromValues(float walk, float run, float fall, float jump) =>
        new(BitConverter.SingleToUInt32Bits(walk), BitConverter.SingleToUInt32Bits(run), BitConverter.SingleToUInt32Bits(fall), BitConverter.SingleToUInt32Bits(jump));
    public MovementValues Selected(MovementMask mask) => new(
        (mask & MovementMask.Walk) != 0 ? Walk : 0, (mask & MovementMask.Run) != 0 ? Run : 0,
        (mask & MovementMask.Fall) != 0 ? Fall : 0, (mask & MovementMask.Jump) != 0 ? Jump : 0);
    public bool Matches(MovementValues other, MovementMask mask)
    {
        for (int i = 0; i < 4; i++) if (((uint)mask & (1u << i)) != 0 && this[i] != other[i]) return false;
        return true;
    }
    public bool IsRestorable(MovementMask mask)
    {
        if (mask == 0 || ((uint)mask & ~15u) != 0) return false;
        for (int i = 0; i < 4; i++) if (((uint)mask & (1u << i)) != 0 && !MovementProtocol.ValidValue(i, Value(i))) return false;
        return true;
    }
}

/// <summary>A single coherent publication. Invalid fields remain invalid, not zero-valued defaults.</summary>
public readonly record struct MovementSnapshot(bool Available, ActorMovementIdentity Identity, GameplayState Gameplay,
    MovementValues Values, MovementMask ValidFields, uint PublicationTick)
{
    public static readonly MovementSnapshot Unavailable = new(false, default, GameplayState.Unavailable, default, MovementMask.None, 0);
    public bool CanUse(MovementMask mask) => Available && Identity.Known && Gameplay.IsControllable && mask != 0 &&
        ((uint)mask & ~15u) == 0 && (ValidFields & mask) == mask && Values.IsRestorable(mask);

    public static MovementSnapshot FromSnapshot(TrainerSnapshot snapshot, uint now)
    {
        if (snapshot.ProtocolVersion != MovementProtocol.RequiredBridgeVersion || !GameplayState.HasFreshPublication(snapshot, now) ||
            !Integer(snapshot, 466, 1, out uint schema) || schema != 1 ||
            !Integer(snapshot, 471, 2, out uint observer) || observer != 1 ||
            !Integer(snapshot, 467, uint.MaxValue, out uint generationLow) || !Integer(snapshot, 468, uint.MaxValue, out uint generationHigh) ||
            !Integer(snapshot, 469, uint.MaxValue, out uint instanceLow) || !Integer(snapshot, 470, uint.MaxValue, out uint instanceHigh) ||
            !Integer(snapshot, 463, uint.MaxValue, out uint tick)) return Unavailable;
        var identity = new ActorMovementIdentity(instanceLow | ((ulong)instanceHigh << 32), generationLow | ((ulong)generationHigh << 32));
        if (!identity.Known) return Unavailable;
        uint[] bits = new uint[4]; MovementMask valid = 0;
        for (int i = 0; i < 4; i++)
        {
            int slot = 344 + i;
            if (!snapshot.HasValue(slot) || !snapshot.Supports(slot)) continue;
            double observed = snapshot.Values[slot]; float value = (float)observed;
            if (!double.IsFinite(observed) || !float.IsFinite(value) || (double)value != observed) continue;
            bits[i] = BitConverter.SingleToUInt32Bits(value);
            valid |= (MovementMask)(1u << i);
        }
        return new(true, identity, GameplayState.FromSnapshot(snapshot, now), new(bits[0], bits[1], bits[2], bits[3]), valid, tick);
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

public readonly record struct MovementCommand(MovementOperation Operation, ActorMovementIdentity Identity,
    MovementMask Mask = MovementMask.None, MovementValues Expected = default, MovementValues Desired = default,
    ulong LeaseId = 0, ulong ExpectedRevision = 0, ulong EffectOwnerId = 0, ulong TargetOperationId = 0);

public sealed record MovementRequest(ulong ClientId, ulong OperationId, MovementCommand Command);
public sealed record MovementOperationHandle(MovementRequest Request, int Sequence);
public sealed record MovementResponse(ulong ClientId, ulong OperationId, ActorMovementIdentity Identity,
    ulong LeaseId, ulong Revision, ulong EffectOwnerId, MovementOutcome Outcome, MovementMask Mask,
    MovementMask AppliedMask, MovementMask RestoredMask, MovementMask SupersededMask, MovementJournalState JournalState,
    MovementValues Original, MovementValues Applied, MovementValues Observed, int RequestSequence, MovementReason Reason,
    uint Tick, MovementResponseFlags Flags, ulong ReceiptOperationId)
{
    public bool HasReceipt => (Flags & MovementResponseFlags.HasReceipt) != 0;
    public bool Terminal => JournalState is MovementJournalState.Released or MovementJournalState.Superseded or MovementJournalState.Destroyed;
}

/// <summary>InDoubt preserves the operation handle. It never means a refused or unapplied mutation.</summary>
public sealed record MovementCommandResult(MovementOperationHandle Handle, MovementResponse? Response, BridgeResult? NativeResult, string? Uncertainty = null)
{
    public bool Acknowledged => Response != null;
    public bool InDoubt => Response == null;
}

/// <summary>Keep this object across reconnects to preserve client and monotonic operation identity.</summary>
public sealed class MovementClientSession
{
    private readonly object gate = new();
    private ulong next;
    internal readonly SemaphoreSlim Commands = new(1, 1);
    // Guarded by Commands. Kept across connection disposal/reconnect.
    internal MovementOperationHandle? Pending;
    internal MovementOperationHandle? AmbiguousOrigin;
    public ulong ClientId { get; }
    public MovementClientSession()
    {
        ulong value;
        do { value = BitConverter.ToUInt64(RandomNumberGenerator.GetBytes(sizeof(ulong))); } while (value == 0);
        ClientId = value;
    }
    public ulong NextId()
    {
        lock (gate)
        {
            if (next == ulong.MaxValue) throw new InvalidOperationException("Movement operation IDs are exhausted; create a new client session.");
            return ++next;
        }
    }
}
