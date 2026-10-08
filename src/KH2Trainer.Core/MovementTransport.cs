using System.Diagnostics;

namespace KH2Trainer.Core;

public sealed partial class BridgeConnection
{
    public MovementOperationHandle? PendingMovement => Volatile.Read(ref movementClient.Pending);

    private void RequireNoPendingMovement()
    {
        if (movementClient.Pending != null)
            throw new InvalidOperationException("Resolve the outstanding movement operation before publishing another command.");
    }

    private void RequireMovementChannel()
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        if (protocolVersion != MovementProtocol.RequiredBridgeVersion || view.ReadInt32(4) != MovementProtocol.RequiredBridgeVersion ||
            view.ReadInt32(0) != BridgeProtocol.Magic || !ReadSnapshot().Supports(MovementProtocol.CapabilitySlot))
            throw new NotSupportedException("This bridge does not expose the version-4 movement journal.");
    }

    /// <summary>Acknowledgement copies the receipt before releasing the shared command lock. No automatic mutation retry.</summary>
    public async Task<MovementCommandResult> ExecuteMovementAsync(MovementCommand command, CancellationToken cancellation = default)
    {
        await commands.WaitAsync(cancellation);
        try
        {
            RequireMovementChannel(); RequireNoPendingMovement();
            var request = new MovementRequest(movementClient.ClientId, movementClient.NextId(), command);
            MovementProtocol.Validate(request);
            return await PublishMovementAsync(request, cancellation);
        }
        finally { commands.Release(); }
    }

    /// <summary>
    /// Resolves the exact outstanding publication. A late acknowledgement is copied first. If its envelope was lost,
    /// a read-only journal query may be published only after the channel is idle; the mutation is never republished.
    /// On another uncertain result, keep the returned Handle for the next resolution attempt.
    /// </summary>
    public async Task<MovementCommandResult> ResolveMovementAsync(MovementOperationHandle handle, CancellationToken cancellation = default)
    {
        ArgumentNullException.ThrowIfNull(handle);
        await commands.WaitAsync(cancellation);
        try
        {
            RequireMovementChannel();
            if (handle != movementClient.Pending || handle.Request.ClientId != movementClient.ClientId)
                throw new InvalidOperationException("This is not this client's outstanding movement operation.");
            cancellation.ThrowIfCancellationRequested();
            int requested = view.ReadInt32(BridgeProtocol.RequestSequence), answered = view.ReadInt32(BridgeProtocol.ResponseSequence);
            if (requested != answered) return Uncertain(handle, "The published operation is still awaiting acknowledgement.");
            ulong currentInstance = CurrentBridgeInstance();
            if (answered == handle.Sequence && (currentInstance == 0 || currentInstance == handle.Request.Command.Identity.BridgeInstance) &&
                TryMovementResponse(handle, out var result)) return result!;

            // No running publication remains. Copying/validating the response failed or a later channel user replaced it.
            // Mutations have retained receipts. Queries are repeated read-only; acknowledgements are idempotent.
            var previous = handle.Request.Command;
            var query = previous.Operation is MovementOperation.Acquire or MovementOperation.Reapply or MovementOperation.ReleaseIntent
                ? new MovementCommand(MovementOperation.QueryOperation, new(previous.Identity.BridgeInstance, 0), TargetOperationId: handle.Request.OperationId)
                : previous;
            var next = new MovementRequest(movementClient.ClientId, movementClient.NextId(), query);
            // Pending remains set until Publish replaces it under the same semaphore.
            return await PublishMovementAsync(next, cancellation);
        }
        finally { commands.Release(); }
    }

    private async Task<MovementCommandResult> PublishMovementAsync(MovementRequest request, CancellationToken cancellation)
    {
        byte[] bytes = MovementProtocol.Encode(request);
        if (view.ReadInt32(BridgeProtocol.RequestSequence) != view.ReadInt32(BridgeProtocol.ResponseSequence))
            throw new InvalidOperationException("The previous command is still awaiting acknowledgement.");
        cancellation.ThrowIfCancellationRequested();
        int sequence = unchecked(view.ReadInt32(BridgeProtocol.RequestSequence) + 1);
        if (sequence == 0) sequence = 1;
        var handle = new MovementOperationHandle(request, sequence);
        // From this point any interruption is uncertain, even when publication itself throws.
        movementClient.Pending = handle;
        if (request.Command.Operation is MovementOperation.Acquire or MovementOperation.Reapply or MovementOperation.ReleaseIntent)
            movementClient.AmbiguousOrigin = handle;
        try
        {
            view.WriteArray(MovementProtocol.RequestOffset, bytes, 0, bytes.Length);
            for (int i = 0; i < 8; i++) view.Write(BridgeProtocol.Arguments + i * sizeof(double), 0d);
            view.Write(BridgeProtocol.Command, MovementProtocol.Command);
            view.Write(BridgeProtocol.CommandIssuedAt, unchecked((uint)Environment.TickCount));
            Thread.MemoryBarrier();
            view.Write(BridgeProtocol.RequestSequence, sequence);
            long start = Stopwatch.GetTimestamp();
            while (view.ReadInt32(BridgeProtocol.ResponseSequence) != sequence)
            {
                if (Stopwatch.GetElapsedTime(start) >= TimeSpan.FromSeconds(8))
                    return Uncertain(handle, "Movement acknowledgement timed out; resolve this operation before further commands.");
                await Task.Delay(25, cancellation);
            }
            return TryMovementResponse(handle, out var result) ? result! : Uncertain(handle, "The movement acknowledgement was malformed or did not match this operation.");
        }
        catch (Exception e) when (e is OperationCanceledException or IOException or ObjectDisposedException or InvalidOperationException)
        { return Uncertain(handle, "Publication or acknowledgement was interrupted: " + e.Message); }
    }

    private bool TryMovementResponse(MovementOperationHandle handle, out MovementCommandResult? result)
    {
        result = null;
        Thread.MemoryBarrier();
        byte[] bytes = new byte[MovementProtocol.ResponseSize];
        view.ReadArray(MovementProtocol.ResponseOffset, bytes, 0, bytes.Length);
        var native = new BridgeResult(handle.Sequence, view.ReadInt32(BridgeProtocol.ResultCode), ReadText(BridgeProtocol.ResultText, BridgeProtocol.ResultTextCharacters));
        Thread.MemoryBarrier();
        if (view.ReadInt32(BridgeProtocol.ResponseSequence) != handle.Sequence || view.ReadInt32(BridgeProtocol.RequestSequence) != handle.Sequence) return false;
        try
        {
            var response = MovementProtocol.Decode(bytes, handle);
            if (movementClient.AmbiguousOrigin is { } origin)
            {
                bool direct = handle.Request.OperationId == origin.Request.OperationId;
                bool receipt = response.HasReceipt && response.ReceiptOperationId == origin.Request.OperationId;
                bool replacement = response.Outcome == MovementOutcome.Rejected && response.Reason == MovementReason.StaleBridge &&
                    response.Identity.BridgeInstance != origin.Request.Command.Identity.BridgeInstance &&
                    CurrentBridgeInstance() == response.Identity.BridgeInstance && response.Identity.BridgeInstance != 0;
                if (response.Reason == MovementReason.StaleBridge && !replacement) return false;
                // A rejected QUERY or absent retained result cannot say whether the earlier mutation happened.
                if (!direct && !receipt && !replacement) return false;
                if (receipt && !MovementProtocol.ReceiptMatchesOrigin(response, origin.Request)) return false;
                if (response.JournalState != MovementJournalState.Uncertain) movementClient.AmbiguousOrigin = null;
            }
            result = new(handle, response, native);
            if (movementClient.AmbiguousOrigin == null) movementClient.Pending = null;
            return true;
        }
        catch (InvalidDataException) { return false; }
    }

    private ulong CurrentBridgeInstance()
    {
        var snapshot = ReadSnapshot();
        if (!GameplayState.HasFreshPublication(snapshot, unchecked((uint)Environment.TickCount))) return 0;
        ulong value = 0;
        for (int i = 0; i < 2; i++)
        {
            int slot = 469 + i;
            if (!snapshot.Supports(slot) || !snapshot.HasValue(slot)) return 0;
            double part = snapshot.Values[slot];
            if (!double.IsFinite(part) || part < 0 || part > uint.MaxValue || part != Math.Truncate(part)) return 0;
            value |= (ulong)(uint)part << (32 * i);
        }
        return value;
    }

    private static MovementCommandResult Uncertain(MovementOperationHandle handle, string message) => new(handle, null, null, message);
}
