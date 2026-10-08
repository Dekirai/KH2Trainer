using KH2Trainer.Core;

internal sealed partial class FakeGame
{
    private static readonly string[] MovementIds = ["movement.walk_speed", "movement.run_speed", "movement.fall_speed", "movement.base_jump_height"];
    private readonly MovementClientSession movementClient = new();
    private readonly Dictionary<ulong, MovementResponse> movementLeases = [];
    private readonly Dictionary<ulong, MovementResponse> movementReceipts = [];
    private readonly Dictionary<ulong, double?[]> actorValues = [];
    private readonly HashSet<ulong> retiredActors = [];
    private ulong nextLease, nextGeneration = 1;
    private int movementSequence;
    public ulong MovementGeneration { get; private set; } = 1;
    public ulong MovementInstance { get; set; } = 0xF0E1D2C3B4A59687;
    public bool MovementAvailable { get; set; } = true;
    public bool WithholdMovementAck { get; set; }
    public bool LoseNextMovementAck { get; set; }
    public bool UncertainMovementLease { get; set; }
    public Action<MovementCommand>? BeforeMovementDispatch { get; set; }
    public Action<MovementCommand>? AfterMovementDispatch { get; set; }
    public Func<MovementCommand, MovementReason?>? RejectMovement { get; set; }
    public TaskCompletionSource? MovementHold { get; set; }
    public MovementOperationHandle? PendingMovement { get; private set; }
    private MovementCommandResult? pendingMovementResult;
    public List<MovementCommand> MovementCommands { get; } = [];
    public int MovementWrites { get; private set; }
    public int MovementLeaseCount => movementLeases.Count;
    public int MovementReceiptCount => movementReceipts.Count;
    public MovementSnapshot Movement
    {
        get
        {
            if (!IsConnected || !MovementAvailable || !Supports(466)) return MovementSnapshot.Unavailable;
            uint[] bits = new uint[4]; MovementMask fields = 0;
            for (int i = 0; i < 4; i++) if (Supports(344 + i) && Get(MovementIds[i]) is double v && double.IsFinite(v) && float.IsFinite((float)v))
            { bits[i] = BitConverter.SingleToUInt32Bits((float)v); fields |= (MovementMask)(1u << i); }
            return new(true, new(MovementInstance, MovementGeneration), Gameplay, new(bits[0], bits[1], bits[2], bits[3]), fields, 100);
        }
    }
    public void SwitchMovementActor(PlayerRole role, MovementValues values, bool retireOld = false, ulong existingGeneration = 0)
    {
        actorValues[MovementGeneration] = MovementIds.Select(Get).ToArray();
        if (retireOld) retiredActors.Add(MovementGeneration);
        MovementGeneration = existingGeneration != 0 ? existingGeneration : ++nextGeneration;
        gameplay = new(true, role, GameplayBlockers.None);
        for (int i = 0; i < 4; i++) Set(MovementIds[i], existingGeneration != 0 && actorValues.TryGetValue(existingGeneration, out var saved) ? saved[i] ?? double.NaN : values.Value(i));
        PumpMovement();
    }
    public double? ActorValue(ulong generation, int field) => generation == MovementGeneration ? Get(MovementIds[field]) : actorValues.GetValueOrDefault(generation)?[field];
    public void RetireMovementActor(ulong generation) { retiredActors.Add(generation); PumpMovement(); }
    public void RestartMovementBridge(MovementValues values)
    {
        MovementInstance++; movementLeases.Clear(); movementReceipts.Clear(); retiredActors.Clear();
        SwitchMovementActor(PlayerRole.Sora, values, true);
    }

    private void PumpMovement()
    {
        foreach (var pair in movementLeases.ToArray())
        {
            var l = pair.Value;
            if (l.Terminal) continue;
            if (retiredActors.Contains(l.Identity.Generation))
            { movementLeases[pair.Key] = l with { JournalState = MovementJournalState.Destroyed, Revision = l.Revision + 1 }; continue; }
            if (l.JournalState != MovementJournalState.ReleasePending || !Movement.Available || !Gameplay.IsControllable || l.Identity != Movement.Identity) continue;
            MovementMask restored = l.RestoredMask, superseded = l.SupersededMask;
            for (int i = 0; i < 4; i++) if (((uint)l.Mask & (1u << i)) != 0 && (((uint)(restored | superseded) & (1u << i)) == 0))
            {
                var bit = (MovementMask)(1u << i);
                if (Movement.Values[i] != l.Applied[i]) superseded |= bit;
                else if (Reject?.Invoke(MovementIds[i], [l.Original.Value(i)]) != true)
                { Set(MovementIds[i], l.Original.Value(i)); restored |= bit; MovementWrites++; }
            }
            var state = (restored | superseded) == l.Mask ? superseded == 0 ? MovementJournalState.Released : MovementJournalState.Superseded : MovementJournalState.ReleasePending;
            if (restored != l.RestoredMask || superseded != l.SupersededMask)
                movementLeases[pair.Key] = l with { RestoredMask = restored, SupersededMask = superseded, JournalState = state, Revision = l.Revision + 1 };
        }
    }

    public async Task<MovementCommandResult> ExecuteMovementAsync(MovementCommand command, CancellationToken cancellation = default)
    {
        if (PendingMovement != null) throw new InvalidOperationException("Outstanding movement operation");
        cancellation.ThrowIfCancellationRequested();
        var request = new MovementRequest(movementClient.ClientId, movementClient.NextId(), command);
        MovementProtocol.Validate(request); var handle = new MovementOperationHandle(request, ++movementSequence);
        MovementCommands.Add(command); BeforeMovementDispatch?.Invoke(command);
        if (MovementHold is { } hold) await hold.Task;
        PumpMovement();
        var r = DispatchMovement(handle);
        if (command.Operation is MovementOperation.Acquire or MovementOperation.Reapply or MovementOperation.ReleaseIntent)
        { r = r with { Flags = r.Flags | MovementResponseFlags.HasReceipt, ReceiptOperationId = request.OperationId }; movementReceipts[request.OperationId] = r; }
        AfterMovementDispatch?.Invoke(command);
        var result = new MovementCommandResult(handle, r, new(handle.Sequence, r.Outcome == MovementOutcome.Rejected ? 1 : 0, "fake journal"));
        if (LoseNextMovementAck || WithholdMovementAck)
        {
            LoseNextMovementAck = false; PendingMovement = handle; pendingMovementResult = result;
            return new(handle, null, null, "simulated lost acknowledgement");
        }
        return result;
    }

    public Task<MovementCommandResult> ResolveMovementAsync(MovementOperationHandle handle, CancellationToken cancellation = default)
    {
        if (handle != PendingMovement || pendingMovementResult == null) throw new InvalidOperationException("Wrong pending handle");
        if (WithholdMovementAck) return Task.FromResult(new MovementCommandResult(handle, null, null, "still pending"));
        var result = pendingMovementResult; PendingMovement = null; pendingMovementResult = null; return Task.FromResult(result);
    }

    private MovementResponse DispatchMovement(MovementOperationHandle h)
    {
        var q = h.Request; var c = q.Command;
        var empty = new MovementResponse(q.ClientId, q.OperationId, new(MovementInstance, 0), 0, 0, 0,
            MovementOutcome.Rejected, 0, 0, 0, 0, MovementJournalState.None, default, default, default, h.Sequence,
            MovementReason.None, 100, 0, 0);
        MovementResponse RejectResult(MovementReason reason) => empty with { Reason = reason };
        if (c.Identity.BridgeInstance != MovementInstance) return RejectResult(MovementReason.StaleBridge);
        if (RejectMovement?.Invoke(c) is { } rejected) return RejectResult(rejected);
        if (c.Operation == MovementOperation.QueryOperation)
            return movementReceipts.TryGetValue(c.TargetOperationId, out var prior) ? prior with { OperationId = q.OperationId, RequestSequence = h.Sequence } :
                empty with { Outcome = MovementOutcome.OperationUnknown, Reason = MovementReason.ReceiptNotFound };
        movementLeases.TryGetValue(c.LeaseId, out var l);
        if (c.Operation == MovementOperation.AcknowledgeReceipt)
        {
            movementReceipts.Remove(c.TargetOperationId);
            if (l != null && l.Terminal && l.Revision == c.ExpectedRevision && !movementReceipts.Values.Any(r => r.LeaseId == l.LeaseId)) movementLeases.Remove(l.LeaseId);
            return empty with { Outcome = MovementOutcome.ReceiptAcknowledged };
        }
        if (c.Operation != MovementOperation.Acquire)
        {
            if (l == null) return RejectResult(MovementReason.LeaseNotFound);
            empty = l with { ClientId = q.ClientId, OperationId = q.OperationId, RequestSequence = h.Sequence, Outcome = MovementOutcome.Rejected,
                Flags = MovementResponseFlags.IdentityKnown, AppliedMask = 0, Observed = default, ReceiptOperationId = 0 };
            if (l.EffectOwnerId != c.EffectOwnerId) return RejectResult(MovementReason.NotOwner);
            if (c.Operation == MovementOperation.QueryLease) return empty with { Outcome = MovementOutcome.LeaseObserved,
                JournalState = UncertainMovementLease ? MovementJournalState.Uncertain : empty.JournalState };
            if (l.Revision != c.ExpectedRevision) return RejectResult(MovementReason.RevisionMismatch);
            if (c.Operation == MovementOperation.ReleaseIntent)
            {
                if (l.JournalState == MovementJournalState.Active) movementLeases[l.LeaseId] = l with { JournalState = MovementJournalState.ReleasePending, Revision = l.Revision + 1 };
                PumpMovement(); return movementLeases[l.LeaseId] with { ClientId = q.ClientId, OperationId = q.OperationId, RequestSequence = h.Sequence, Outcome = MovementOutcome.ReleaseAccepted, AppliedMask = 0 };
            }
        }
        if (!Movement.CanUse(c.Mask)) return RejectResult(MovementReason.NotReady);
        if (Movement.Identity != c.Identity) return RejectResult(MovementReason.ActorMismatch);
        if (!Movement.Values.Matches(c.Expected, c.Mask)) return RejectResult(MovementReason.ExpectedMismatch);
        if (c.Operation == MovementOperation.Acquire && movementLeases.Values.Any(r => !r.Terminal && r.Identity == c.Identity && (r.Mask & c.Mask) != 0)) return RejectResult(MovementReason.LeaseConflict);
        for (int i = 0; i < 4; i++) if (((uint)c.Mask & (1u << i)) != 0 && Reject?.Invoke(MovementIds[i], [c.Desired.Value(i)]) == true) return RejectResult(MovementReason.NotReady);
        uint[] original = new uint[4];
        for (int i = 0; i < 4; i++) if (((uint)c.Mask & (1u << i)) != 0)
        { original[i] = l != null && Movement.Values[i] == l.Applied[i] ? l.Original[i] : Movement.Values[i]; Set(MovementIds[i], c.Desired.Value(i)); MovementWrites++; }
        var applied = empty with { Identity = c.Identity, LeaseId = l?.LeaseId ?? ++nextLease, Revision = (l?.Revision ?? 0) + 1, EffectOwnerId = c.EffectOwnerId,
            Outcome = l == null ? MovementOutcome.Applied : MovementOutcome.Reapplied, Mask = c.Mask, AppliedMask = c.Mask, JournalState = MovementJournalState.Active,
            Original = new(original[0], original[1], original[2], original[3]), Applied = c.Desired, Observed = c.Desired, Flags = MovementResponseFlags.IdentityKnown | MovementResponseFlags.ObservedKnown };
        movementLeases[applied.LeaseId] = applied; return applied;
    }
}
