using System.Security.Cryptography;
using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>Owns native journal records, never scalar guesses about an actor's lifetime.</summary>
internal sealed class MovementEffectLease(IGameControl game, MovementMask mask, Func<MovementValues, MovementValues> transform)
{
    private readonly ulong owner = NewOwner();
    private readonly Dictionary<(ulong Bridge, ulong Lease), MovementResponse> leases = [];
    private readonly Dictionary<(ulong Bridge, ulong Lease), ulong> inspectedAt = [];
    private ulong inspectionCounter;
    private readonly Queue<MovementCommand> acknowledgements = [];
    private MovementOperationHandle? pending;
    private MovementCommand pendingIntent;
    private bool ending;
    private string? fault;
    private ulong faultBridge;
    public bool EverApplied { get; private set; }
    public bool PendingCleanup => pending != null || leases.Count != 0 || acknowledgements.Count != 0 || fault != null;
    public Readiness Readiness
    {
        get
        {
            if (fault != null) return Readiness.Wait(fault);
            if (ending || pending != null || acknowledgements.Count != 0) return Readiness.Wait("Waiting for movement ownership acknowledgement");
            var current = game.Movement;
            if (!current.CanUse(mask)) return Readiness.Wait("Waiting for controllable movement values within the supported restore range");
            var lease = leases.Values.FirstOrDefault(l => l.Identity == current.Identity && l.JournalState == MovementJournalState.Active);
            return lease != null && lease.Applied.Matches(current.Values, mask) ? Readiness.Ready :
                Readiness.Wait("Waiting for this character's movement ownership");
        }
    }

    public async Task MaintainAsync(bool release = false)
    {
        ending |= release;
        if (!game.IsConnected) return;
        try
        {
            // Only this ledger can consume its pending operation. Another effect's operation is never stolen.
            if (pending != null)
            {
                var result = await game.ResolveMovementAsync(pending);
                if (!Accept(result, pendingIntent)) return;
            }
            if (game.PendingMovement != null) return;
            var fresh = game.Movement;
            if (fresh.Available && fresh.Identity.Known)
            {
                // A proven different bridge cannot access the old process's journal. Never replay its originals.
                foreach (var key in leases.Keys.Where(k => k.Bridge != fresh.Identity.BridgeInstance).ToArray()) { leases.Remove(key); inspectedAt.Remove(key); }
                var retained = acknowledgements.Where(a => a.Identity.BridgeInstance == fresh.Identity.BridgeInstance).ToArray();
                acknowledgements.Clear(); foreach (var a in retained) acknowledgements.Enqueue(a);
                if (fault != null && faultBridge != 0 && faultBridge != fresh.Identity.BridgeInstance) { fault = null; faultBridge = 0; }
            }
            if (fault != null) return;
            var inspected = new HashSet<(ulong Bridge, ulong Lease)>();
            // Bounded work per tick. No simultaneous publication or recursive retries.
            for (int budget = 0; budget < 12; budget++)
            {
                if (acknowledgements.TryPeek(out var ack))
                {
                    if (!await Send(ack)) return;
                    continue;
                }
                var current = game.Movement;
                var old = leases.Values.Where(l => !inspected.Contains((l.Identity.BridgeInstance, l.LeaseId)))
                    .OrderBy(l => l.Terminal || l.JournalState == MovementJournalState.Active && (ending || current.Available && l.Identity != current.Identity) ? 0 :
                        l.Identity == current.Identity && l.JournalState == MovementJournalState.Active ? 1 : 2)
                    .ThenBy(l => inspectedAt.GetValueOrDefault((l.Identity.BridgeInstance, l.LeaseId))).FirstOrDefault();
                if (old != null)
                {
                    if (old.JournalState == MovementJournalState.Uncertain) { faultBridge = old.Identity.BridgeInstance; fault = "Movement ownership is uncertain; restart the game before reusing it"; return; }
                    if (old.Terminal)
                    {
                        acknowledgements.Enqueue(new(MovementOperation.AcknowledgeReceipt, new(old.Identity.BridgeInstance, 0),
                            LeaseId: old.LeaseId, ExpectedRevision: old.Revision, EffectOwnerId: owner));
                        continue;
                    }
                    bool releaseOld = ending || current.Available && old.Identity != current.Identity;
                    var op = old.JournalState == MovementJournalState.Active && releaseOld ? MovementOperation.ReleaseIntent : MovementOperation.QueryLease;
                    var command = new MovementCommand(op, new(old.Identity.BridgeInstance, op == MovementOperation.ReleaseIntent ? old.Identity.Generation : 0),
                        LeaseId: old.LeaseId, ExpectedRevision: op == MovementOperation.ReleaseIntent ? old.Revision : 0, EffectOwnerId: owner);
                    if (!await Send(command)) return;
                    inspected.Add((old.Identity.BridgeInstance, old.LeaseId));
                    inspectedAt[(old.Identity.BridgeInstance, old.LeaseId)] = ++inspectionCounter;
                    // An old living actor may remain off-current. Its native release intent persists without blocking
                    // a different generation's acquire; the native overlap check still prevents reusing its fields.
                    if (leases.TryGetValue((old.Identity.BridgeInstance, old.LeaseId), out var refreshed) && refreshed.JournalState == MovementJournalState.ReleasePending)
                    {
                        if (ending || refreshed.Identity == current.Identity) return;
                    }
                    continue;
                }
                break;
            }
            if (ending || pending != null || acknowledgements.Count != 0 || fault != null || game.PendingMovement != null) return;
            var snapshot = game.Movement;
            if (!snapshot.CanUse(mask)) return;
            if (leases.Values.Any(l => l.Identity != snapshot.Identity && l.JournalState == MovementJournalState.Active)) return;
            var existing = leases.Values.FirstOrDefault(l => l.Identity == snapshot.Identity);
            if (existing != null && existing.JournalState != MovementJournalState.Active) return;
            if (existing != null && !inspected.Contains((existing.Identity.BridgeInstance, existing.LeaseId))) return;
            if (existing != null && existing.Applied.Matches(snapshot.Values, mask)) return;
            var desired = existing?.Applied ?? transform(snapshot.Values).Selected(mask);
            if (!desired.IsRestorable(mask)) { faultBridge = snapshot.Identity.BridgeInstance; fault = "The movement reward produced an unsupported value"; return; }
            var write = new MovementCommand(existing == null ? MovementOperation.Acquire : MovementOperation.Reapply,
                snapshot.Identity, mask, snapshot.Values.Selected(mask), desired, existing?.LeaseId ?? 0, existing?.Revision ?? 0, owner);
            if (!await Send(write)) return;
            // Receipt is retained until our copied ownership state is established; only then acknowledge it.
            if (acknowledgements.TryPeek(out var receiptAck)) await Send(receiptAck);
        }
        catch (Exception e) when (e is IOException or InvalidOperationException or NotSupportedException or OperationCanceledException)
        { /* Connection/queue errors before publication have no new receipt. Retain all established ownership. */ }
    }

    private async Task<bool> Send(MovementCommand command)
    {
        pendingIntent = command;
        var result = await game.ExecuteMovementAsync(command);
        return Accept(result, command);
    }

    private bool Accept(MovementCommandResult result, MovementCommand intent)
    {
        if (result.InDoubt) { pending = result.Handle; return false; }
        pending = null;
        var r = result.Response!;
        faultBridge = intent.Identity.BridgeInstance;
        if (r.Reason == MovementReason.StaleBridge && r.Outcome == MovementOutcome.Rejected)
        {
            fault = null;
            // This bridge cannot address the old journal. Never translate an old lease into the new instance.
            foreach (var key in leases.Keys.Where(k => k.Bridge == intent.Identity.BridgeInstance).ToArray()) { leases.Remove(key); inspectedAt.Remove(key); }
            while (acknowledgements.TryPeek(out var queued) && queued.Identity.BridgeInstance == intent.Identity.BridgeInstance) acknowledgements.Dequeue();
            return true;
        }
        if (r.Outcome == MovementOutcome.OperationUnknown)
        { fault = "The movement operation's result is unavailable; ownership cannot be safely recreated"; return false; }
        if ((r.Flags & MovementResponseFlags.IdentityKnown) != 0)
        {
            if (r.EffectOwnerId != owner || r.Mask != mask || r.Identity.BridgeInstance != intent.Identity.BridgeInstance ||
                (intent.LeaseId != 0 && intent.LeaseId != r.LeaseId) ||
                (r.Outcome is MovementOutcome.Applied or MovementOutcome.Reapplied &&
                    (r.Identity != intent.Identity || r.Applied != intent.Desired)))
            { fault = "The movement receipt does not belong to this effect"; return false; }
            leases[(r.Identity.BridgeInstance, r.LeaseId)] = r;
        }
        if (r.Outcome is MovementOutcome.Applied or MovementOutcome.Reapplied) EverApplied = true;
        if (r.JournalState == MovementJournalState.Uncertain)
        {
            // QueryLease can report a known uncertain record without an outstanding publication.
            // Only the transport's unresolved mutation origin may be resolved through its Handle again.
            pending = game.PendingMovement == result.Handle ? result.Handle : null;
            fault = "The movement write is uncertain; the native journal has stopped further writes"; return false;
        }
        if (r.HasReceipt)
        {
            var ack = new MovementCommand(MovementOperation.AcknowledgeReceipt, new(r.Identity.BridgeInstance, 0), TargetOperationId: r.ReceiptOperationId);
            if (!acknowledgements.Contains(ack)) acknowledgements.Enqueue(ack);
        }
        if (r.Outcome == MovementOutcome.ReceiptAcknowledged)
        {
            if (acknowledgements.TryPeek(out var queued) && queued == intent) acknowledgements.Dequeue();
            if (intent.LeaseId != 0) { leases.Remove((intent.Identity.BridgeInstance, intent.LeaseId)); inspectedAt.Remove((intent.Identity.BridgeInstance, intent.LeaseId)); }
        }
        if (r.Outcome == MovementOutcome.Rejected && r.Reason == MovementReason.LeaseNotFound && intent.LeaseId != 0)
        { fault = "The movement ownership record is unavailable; automatic restoration remains suspended"; return false; }
        if (r.Outcome == MovementOutcome.Rejected && intent.Operation == MovementOperation.AcknowledgeReceipt) return false;
        return true;
    }

    private static ulong NewOwner()
    {
        ulong value; do { value = BitConverter.ToUInt64(RandomNumberGenerator.GetBytes(8)); } while (value == 0); return value;
    }
}
