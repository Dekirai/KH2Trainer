using System.Buffers.Binary;

namespace KH2Trainer.Core;

/// <summary>Protocol-v4 binary extension. All identifiers and Float32 bits stay integers.</summary>
public static class MovementProtocol
{
    public const uint Magic = 0x31564F4D;
    public const ushort Schema = 1;
    public const int RequiredBridgeVersion = 4, Command = 1466, CapabilitySlot = 466;
    public const int RequestOffset = 1024, ResponseOffset = 1152, RequestSize = 128, ResponseSize = 192;

    public static bool ValidValue(int field, float value) => float.IsFinite(value) && field switch
    { 0 => value >= 0 && value <= 32, 1 => value >= 0 && value <= 64,
      2 => (double)value >= .1 && value <= 100, 3 => value >= 0 && value <= 1000, _ => false };

    public static void Validate(MovementRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        var c = request.Command;
        bool valid = request.ClientId != 0 && request.OperationId != 0 && c.Identity.BridgeInstance != 0 &&
            c.Operation is >= MovementOperation.Acquire and <= MovementOperation.AcknowledgeReceipt && (uint)c.Mask <= 15;
        if (c.Operation is MovementOperation.Acquire or MovementOperation.Reapply)
        {
            valid &= c.Identity.Generation != 0 && c.EffectOwnerId != 0 && c.TargetOperationId == 0 &&
                c.Mask != 0 && c.Expected == c.Expected.Selected(c.Mask) && c.Desired == c.Desired.Selected(c.Mask) &&
                c.Expected.IsRestorable(c.Mask) && c.Desired.IsRestorable(c.Mask);
            valid &= c.Operation == MovementOperation.Acquire ? c.LeaseId == 0 && c.ExpectedRevision == 0 : c.LeaseId != 0 && c.ExpectedRevision != 0;
        }
        else
        {
            valid &= c.Mask == 0 && c.Expected == default && c.Desired == default;
            valid &= c.Operation switch
            {
                MovementOperation.ReleaseIntent => c.LeaseId != 0 && c.EffectOwnerId != 0 && c.ExpectedRevision != 0 && c.TargetOperationId == 0,
                MovementOperation.QueryOperation => c.TargetOperationId != 0 && c.LeaseId == 0 && c.EffectOwnerId == 0 && c.ExpectedRevision == 0 && c.Identity.Generation == 0,
                MovementOperation.QueryLease => c.LeaseId != 0 && c.EffectOwnerId != 0 && c.TargetOperationId == 0 && c.ExpectedRevision == 0 && c.Identity.Generation == 0,
                MovementOperation.AcknowledgeReceipt => c.Identity.Generation == 0 &&
                    ((c.TargetOperationId != 0 && c.LeaseId == 0 && c.EffectOwnerId == 0 && c.ExpectedRevision == 0) ||
                     (c.LeaseId != 0 && c.EffectOwnerId != 0 && c.ExpectedRevision != 0)),
                _ => false
            };
        }
        if (!valid) throw new ArgumentException("Invalid typed movement request.", nameof(request));
    }

    public static byte[] Encode(MovementRequest request)
    {
        Validate(request);
        var b = new byte[RequestSize]; var c = request.Command;
        U32(b, 0, Magic); U16(b, 4, Schema); U16(b, 6, RequestSize);
        U64(b, 8, request.ClientId); U64(b, 16, request.OperationId); U64(b, 24, c.Identity.BridgeInstance);
        U64(b, 32, c.Identity.Generation); U64(b, 40, c.LeaseId); U32(b, 48, (uint)c.Operation); U32(b, 52, (uint)c.Mask);
        Values(b, 56, c.Expected); Values(b, 72, c.Desired);
        U64(b, 88, c.ExpectedRevision); U64(b, 96, c.EffectOwnerId); U64(b, 112, c.TargetOperationId);
        return b;
    }

    /// <summary>Copies and validates a correlated result. Observed bits can describe an invalid external value.</summary>
    public static MovementResponse Decode(ReadOnlySpan<byte> b, MovementOperationHandle handle)
    {
        ArgumentNullException.ThrowIfNull(handle);
        Validate(handle.Request);
        if (b.Length != ResponseSize || R32(b, 0) != Magic || R16(b, 4) != Schema || R16(b, 6) != ResponseSize ||
            b[160..].ContainsAnyExcept((byte)0)) throw new InvalidDataException("Invalid movement response header or reserved bytes.");
        var r = new MovementResponse(R64(b, 8), R64(b, 16), new(R64(b, 24), R64(b, 32)),
            R64(b, 40), R64(b, 48), R64(b, 56), (MovementOutcome)R32(b, 64), (MovementMask)R32(b, 68),
            (MovementMask)R32(b, 72), (MovementMask)R32(b, 76), (MovementMask)R32(b, 80), (MovementJournalState)R32(b, 84),
            Values(b, 88), Values(b, 104), Values(b, 120), unchecked((int)R32(b, 136)), (MovementReason)R32(b, 140),
            R32(b, 144), (MovementResponseFlags)R32(b, 148), R64(b, 152));
        var q = handle.Request; var c = q.Command;
        bool identity = (r.Flags & MovementResponseFlags.IdentityKnown) != 0;
        bool observed = (r.Flags & MovementResponseFlags.ObservedKnown) != 0;
        bool stale = r.Outcome == MovementOutcome.Rejected && r.Reason == MovementReason.StaleBridge;
        bool valid = r.ClientId == q.ClientId && r.OperationId == q.OperationId && r.RequestSequence == handle.Sequence &&
            r.Outcome is >= MovementOutcome.Applied and <= MovementOutcome.Rejected && (uint)r.Reason <= 21 &&
            (uint)r.JournalState <= 6 && (uint)r.Flags <= 7 && (uint)r.Mask <= 15 &&
            (r.AppliedMask & ~r.Mask) == 0 && (r.RestoredMask & ~r.Mask) == 0 && (r.SupersededMask & ~r.Mask) == 0 &&
            (r.RestoredMask & r.SupersededMask) == 0 && (stale || r.Identity.BridgeInstance == c.Identity.BridgeInstance);
        valid &= identity ? r.Identity.Known && r.LeaseId != 0 && r.Revision != 0 && r.EffectOwnerId != 0 && r.Mask != 0 &&
            r.Original.IsRestorable(r.Mask) && r.Applied.IsRestorable(r.Mask) && r.JournalState != MovementJournalState.None :
            r.Identity.Generation == 0 && r.LeaseId == 0 && r.Revision == 0 && r.EffectOwnerId == 0 && r.Mask == 0;
        valid &= r.Original == r.Original.Selected(r.Mask) && r.Applied == r.Applied.Selected(r.Mask) &&
            r.Observed == r.Observed.Selected(r.Mask) && (!observed || identity) && (observed || r.Observed == default);
        valid &= r.HasReceipt ? r.ReceiptOperationId == (c.Operation == MovementOperation.QueryOperation ? c.TargetOperationId : q.OperationId) : r.ReceiptOperationId == 0;
        if (c.Operation != MovementOperation.QueryOperation)
        {
            valid &= r.Outcome == MovementOutcome.Rejected || (c.Operation, r.Outcome) switch
            {
                (MovementOperation.Acquire, MovementOutcome.Applied) or (MovementOperation.Reapply, MovementOutcome.Reapplied) or
                (MovementOperation.ReleaseIntent, MovementOutcome.ReleaseAccepted) or (MovementOperation.QueryLease, MovementOutcome.LeaseObserved) or
                (MovementOperation.AcknowledgeReceipt, MovementOutcome.ReceiptAcknowledged) => true,
                _ => false
            };
            if (identity) valid &= r.EffectOwnerId == c.EffectOwnerId && (c.LeaseId == 0 || r.LeaseId == c.LeaseId);
        }
        else valid &= r.Outcome is MovementOutcome.Applied or MovementOutcome.Reapplied or MovementOutcome.ReleaseAccepted or MovementOutcome.Rejected or MovementOutcome.OperationUnknown;
        if (r.Outcome is MovementOutcome.Applied or MovementOutcome.Reapplied)
        {
            valid &= identity && observed && r.HasReceipt && r.AppliedMask == r.Mask && r.JournalState == MovementJournalState.Active &&
                r.Reason == MovementReason.None && r.Observed == r.Applied && r.RestoredMask == 0 && r.SupersededMask == 0;
            if (c.Operation != MovementOperation.QueryOperation)
                valid &= r.Identity == c.Identity && r.Mask == c.Mask && r.Applied == c.Desired;
        }
        if (r.Outcome == MovementOutcome.ReleaseAccepted) valid &= identity && r.HasReceipt &&
            r.JournalState is MovementJournalState.ReleasePending or MovementJournalState.Released or MovementJournalState.Superseded or MovementJournalState.Destroyed;
        if (r.Outcome == MovementOutcome.LeaseObserved) valid &= identity && !r.HasReceipt;
        if (r.Outcome == MovementOutcome.ReceiptAcknowledged) valid &= !r.HasReceipt;
        if (r.Outcome == MovementOutcome.OperationUnknown) valid &= c.Operation == MovementOperation.QueryOperation && !r.HasReceipt && !identity && r.Reason == MovementReason.ReceiptNotFound;
        if (r.Outcome == MovementOutcome.Rejected) valid &= r.Reason != MovementReason.None;
        if (!valid) throw new InvalidDataException("Movement response does not match the request or its ownership contract.");
        return r;
    }

    /// <summary>A recovery query does not carry the original write parameters; retain and check them separately.</summary>
    public static bool ReceiptMatchesOrigin(MovementResponse response, MovementRequest origin)
    {
        var c = origin.Command;
        if (!response.HasReceipt || response.ClientId != origin.ClientId || response.ReceiptOperationId != origin.OperationId ||
            response.Identity.BridgeInstance != c.Identity.BridgeInstance) return false;
        if (response.Outcome is MovementOutcome.Applied or MovementOutcome.Reapplied)
            return response.Outcome == (c.Operation == MovementOperation.Acquire ? MovementOutcome.Applied : MovementOutcome.Reapplied) &&
                c.Operation is MovementOperation.Acquire or MovementOperation.Reapply && response.Identity == c.Identity &&
                response.EffectOwnerId == c.EffectOwnerId && response.Mask == c.Mask && response.Applied == c.Desired &&
                (c.LeaseId == 0 || response.LeaseId == c.LeaseId);
        if (response.Outcome == MovementOutcome.ReleaseAccepted)
            return c.Operation == MovementOperation.ReleaseIntent && response.LeaseId == c.LeaseId && response.EffectOwnerId == c.EffectOwnerId &&
                (c.Identity.Generation == 0 || response.Identity.Generation == c.Identity.Generation);
        return response.Outcome == MovementOutcome.Rejected &&
            ((response.Flags & MovementResponseFlags.IdentityKnown) == 0 || response.EffectOwnerId == c.EffectOwnerId &&
                (c.LeaseId == 0 || response.LeaseId == c.LeaseId));
    }

    private static ushort R16(ReadOnlySpan<byte> b, int o) => BinaryPrimitives.ReadUInt16LittleEndian(b[o..]);
    private static uint R32(ReadOnlySpan<byte> b, int o) => BinaryPrimitives.ReadUInt32LittleEndian(b[o..]);
    private static ulong R64(ReadOnlySpan<byte> b, int o) => BinaryPrimitives.ReadUInt64LittleEndian(b[o..]);
    private static void U16(Span<byte> b, int o, int n) => BinaryPrimitives.WriteUInt16LittleEndian(b[o..], checked((ushort)n));
    private static void U32(Span<byte> b, int o, uint n) => BinaryPrimitives.WriteUInt32LittleEndian(b[o..], n);
    private static void U64(Span<byte> b, int o, ulong n) => BinaryPrimitives.WriteUInt64LittleEndian(b[o..], n);
    private static MovementValues Values(ReadOnlySpan<byte> b, int o) => new(R32(b, o), R32(b, o + 4), R32(b, o + 8), R32(b, o + 12));
    private static void Values(Span<byte> b, int o, MovementValues v) { for (int i = 0; i < 4; i++) U32(b, o + i * 4, v[i]); }
}
