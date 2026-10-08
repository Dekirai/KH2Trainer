using System.Buffers.Binary;
using System.IO.MemoryMappedFiles;
using KH2Trainer.Core;

internal static class MovementProtocolTests
{
    private static readonly ActorMovementIdentity Identity = new(0xFEDCBA9876543210, 0x123456789ABCDEFF);
    private static readonly MovementValues Original = MovementValues.FromValues(2, 8, 12, 160);
    private static readonly MovementValues Applied = MovementValues.FromValues(4, 16, 6, 320);
    private static MovementCommand Acquire(MovementMask mask = MovementMask.Speed) => new(MovementOperation.Acquire, Identity, mask, Original.Selected(mask), Applied.Selected(mask), EffectOwnerId: 0xCAFEF00DDEADC0DE);
    private static MovementRequest Request(MovementCommand? c = null) => new(0xFFEEDDCCBBAA9988, 0xAABBCCDDEEFF9876, c ?? Acquire());
    private static uint R32(byte[] b, int o) => BinaryPrimitives.ReadUInt32LittleEndian(b.AsSpan(o));
    private static ulong R64(byte[] b, int o) => BinaryPrimitives.ReadUInt64LittleEndian(b.AsSpan(o));
    private static void W32(byte[] b, int o, uint n) => BinaryPrimitives.WriteUInt32LittleEndian(b.AsSpan(o), n);
    private static void W64(byte[] b, int o, ulong n) => BinaryPrimitives.WriteUInt64LittleEndian(b.AsSpan(o), n);
    private static void Reject(Action action, string name, Action<bool, string> check)
    { try { action(); check(false, name); } catch (Exception e) when (e is ArgumentException or InvalidDataException or InvalidOperationException or NotSupportedException) { check(true, name); } }
    private static async Task RejectAsync(Func<Task> action, string name, Action<bool, string> check)
    { try { await action(); check(false, name); } catch (Exception e) when (e is ArgumentException or InvalidOperationException or NotSupportedException or OperationCanceledException) { check(true, name); } }

    private static byte[] Response(MovementOperationHandle h, MovementOutcome outcome = MovementOutcome.Applied, MovementReason reason = MovementReason.None)
    {
        var q = h.Request; var c = q.Command; var b = new byte[192];
        W32(b, 0, MovementProtocol.Magic); W32(b, 4, 1 | (192u << 16));
        W64(b, 8, q.ClientId); W64(b, 16, q.OperationId); W64(b, 24, c.Identity.BridgeInstance);
        W32(b, 64, (uint)outcome); W32(b, 136, unchecked((uint)h.Sequence)); W32(b, 140, (uint)reason); W32(b, 144, 1234);
        if (outcome is MovementOutcome.Applied or MovementOutcome.Reapplied or MovementOutcome.ReleaseAccepted or MovementOutcome.LeaseObserved)
        {
            var mask = c.Mask == 0 ? MovementMask.Speed : c.Mask;
            W64(b, 32, Identity.Generation); W64(b, 40, c.LeaseId == 0 ? 0xF00DBA5EF00DBA5E : c.LeaseId);
            W64(b, 48, 1); W64(b, 56, Acquire().EffectOwnerId); W32(b, 68, (uint)mask);
            W32(b, 72, outcome is MovementOutcome.Applied or MovementOutcome.Reapplied ? (uint)mask : 0);
            W32(b, 84, outcome == MovementOutcome.ReleaseAccepted ? 2u : 1u);
            for (int i = 0; i < 4; i++) if (((uint)mask & (1u << i)) != 0)
            { W32(b, 88 + i * 4, Original[i]); W32(b, 104 + i * 4, Applied[i]); W32(b, 120 + i * 4, Applied[i]); }
            W32(b, 148, outcome == MovementOutcome.LeaseObserved ? 3u : 7u);
            if (outcome != MovementOutcome.LeaseObserved) W64(b, 152, c.Operation == MovementOperation.QueryOperation ? c.TargetOperationId : q.OperationId);
        }
        return b;
    }

    internal static async Task RunAsync(Action<bool, string> check)
    {
        for (uint m = 1; m <= 15; m++)
        {
            var q = Request(Acquire((MovementMask)m)); var wire = MovementProtocol.Encode(q); var h = new MovementOperationHandle(q, -43);
            check(wire.Length == 128 && R32(wire, 0) == 0x31564F4D && R32(wire, 4) == 0x00800001 && R32(wire, 52) == m,
                $"movement request exact header and nonempty mask {m}");
            check(R64(wire, 8) == q.ClientId && R64(wire, 16) == q.OperationId && R64(wire, 24) == Identity.BridgeInstance &&
                R64(wire, 32) == Identity.Generation && R64(wire, 96) == q.Command.EffectOwnerId,
                $"movement mask {m} preserves UInt64 values above double precision");
            var parsed = MovementProtocol.Decode(Response(h), h);
            check(parsed.Original == Original.Selected((MovementMask)m) && parsed.Applied == Applied.Selected((MovementMask)m) && parsed.HasReceipt,
                $"movement mask {m} receipt exact bits");
        }
        var request = Request(); var handle = new MovementOperationHandle(request, 50);
        foreach (uint invalid in new uint[] { 0, 16, uint.MaxValue }) Reject(() => MovementProtocol.Encode(Request(Acquire((MovementMask)invalid))), $"movement invalid mask {invalid}", check);
        foreach (float bad in new[] { float.NaN, float.PositiveInfinity, -1f, 33f })
            Reject(() => MovementProtocol.Encode(Request(Acquire(MovementMask.Walk) with { Desired = MovementValues.FromValues(bad, 0, 0, 0) })), $"movement bad walk {bad}", check);
        check(MovementProtocol.ValidValue(2, .1f) && !MovementProtocol.ValidValue(2, MathF.BitDecrement(.1f)) &&
            MovementProtocol.ValidValue(0, -0f), "movement Float32 policy boundaries and signed zero");
        Reject(() => MovementProtocol.Encode(request with { ClientId = 0 }), "movement zero client", check);
        Reject(() => MovementProtocol.Encode(request with { OperationId = 0 }), "movement zero operation", check);
        Reject(() => MovementProtocol.Encode(Request(Acquire() with { Expected = Original })), "movement unselected raw values rejected", check);
        Reject(() => MovementProtocol.Encode(Request(Acquire() with { LeaseId = 2 })), "acquire cannot target a lease", check);
        Reject(() => MovementProtocol.Encode(Request(Acquire() with { Operation = MovementOperation.Reapply })), "reapply requires lease revision", check);
        var query = new MovementCommand(MovementOperation.QueryOperation, new(Identity.BridgeInstance, 0), TargetOperationId: request.OperationId);
        var queryHandle = new MovementOperationHandle(Request(query), 71);
        check(MovementProtocol.Decode(Response(queryHandle), queryHandle).ReceiptOperationId == request.OperationId, "query keeps immutable mutation receipt ID distinct from query ID");
        check(MovementProtocol.Decode(Response(queryHandle, MovementOutcome.OperationUnknown, MovementReason.ReceiptNotFound), queryHandle).Outcome == MovementOutcome.OperationUnknown,
            "unknown operation is explicit, never applied");
        var ack = new MovementCommand(MovementOperation.AcknowledgeReceipt, new(Identity.BridgeInstance, 0), LeaseId: 42, ExpectedRevision: 7, EffectOwnerId: 44);
        check(MovementProtocol.Encode(Request(ack)).Length == 128, "terminal lease GC accepts complete tuple without target receipt");
        Reject(() => MovementProtocol.Encode(Request(ack with { ExpectedRevision = 0 })), "terminal GC needs revision", check);
        check(MovementProtocol.Encode(Request(ack with { LeaseId = 0, ExpectedRevision = 0, EffectOwnerId = 0, TargetOperationId = 2 })).Length == 128, "receipt-only acknowledgement supported");
        foreach (int length in new[] { 0, 127, 191, 193 }) Reject(() => MovementProtocol.Decode(new byte[length], handle), $"response exact size {length}", check);
        var response = Response(handle);
        for (int offset = 160; offset < 192; offset++) { var corrupt = (byte[])response.Clone(); corrupt[offset] = 1; Reject(() => MovementProtocol.Decode(corrupt, handle), $"response reserved byte {offset}", check); }
        foreach (int offset in new[] { 0, 4, 6, 8, 16, 24, 32, 56, 64, 68, 72, 76, 80, 84, 136, 140, 148, 152 })
        { var corrupt = (byte[])response.Clone(); corrupt[offset] ^= 0x80; Reject(() => MovementProtocol.Decode(corrupt, handle), $"response correlation/shape corruption at {offset}", check); }
        var noLease = (byte[])response.Clone(); W64(noLease, 40, 0); Reject(() => MovementProtocol.Decode(noLease, handle), "successful acquire requires nonzero native lease", check);
        var stale = Response(handle, MovementOutcome.Rejected, MovementReason.StaleBridge); W64(stale, 24, 33);
        check(MovementProtocol.Decode(stale, handle).Identity.BridgeInstance == 33, "stale bridge rejection can report replacement instance");
        var leaseQuery = new MovementOperationHandle(Request(new(MovementOperation.QueryLease, new(Identity.BridgeInstance, 0), LeaseId: 8, EffectOwnerId: Acquire().EffectOwnerId)), 7);
        var external = Response(leaseQuery, MovementOutcome.LeaseObserved); W32(external, 120, 0x7FC00000);
        check(float.IsNaN(MovementProtocol.Decode(external, leaseQuery).Observed.Value(0)), "nonfinite external observation does not erase valid ownership receipt");
        W32(external, 88, 0x7FC00000); Reject(() => MovementProtocol.Decode(external, leaseQuery), "invalid original cannot become restorable ownership", check);
        SnapshotChecks(check);
        await TransportChecks(check);
    }

    private static void SnapshotChecks(Action<bool, string> check)
    {
        var s = new TrainerSnapshot { Connected = true, SceneReady = true, Status = 1, ProtocolVersion = 4 };
        void Slot(int n, double v) { s.Values[n] = v; s.Valid[n / 64] |= 1UL << (n % 64); s.Supported[n / 64] |= 1UL << (n % 64); }
        Slot(456, 1); Slot(457, 2); Slot(458, 0); Slot(459, 1); Slot(463, 100);
        Slot(466, 1); Slot(467, (uint)Identity.Generation); Slot(468, (uint)(Identity.Generation >> 32));
        Slot(469, (uint)Identity.BridgeInstance); Slot(470, (uint)(Identity.BridgeInstance >> 32)); Slot(471, 1);
        for (int i = 0; i < 4; i++) Slot(344 + i, Original.Value(i));
        check(MovementSnapshot.FromSnapshot(s, 200).CanUse(MovementMask.All) && MovementSnapshot.FromSnapshot(s, 200).Identity == Identity,
            "coherent Roxas movement snapshot retains exact identity and all fields");
        check(!MovementSnapshot.FromSnapshot(s with { ProtocolVersion = 3 }, 200).Available && !MovementSnapshot.FromSnapshot(s, 1101).Available,
            "movement old protocol and stale publication fail closed");
        foreach (int slot in new[] { 466, 467, 468, 469, 470, 471 })
        {
            double old = s.Values[slot];
            foreach (double bad in new[] { double.NaN, double.PositiveInfinity, -.5, .5, (double)uint.MaxValue + 1 })
            { s.Values[slot] = bad; check(!MovementSnapshot.FromSnapshot(s, 200).Available, $"movement malformed identity slot{slot}/{bad}"); }
            s.Values[slot] = old; s.Valid[slot / 64] &= ~(1UL << (slot % 64));
            check(!MovementSnapshot.FromSnapshot(s, 200).Available, $"movement missing identity slot{slot}"); s.Valid[slot / 64] |= 1UL << (slot % 64);
        }
        Slot(345, 100); check(!MovementSnapshot.FromSnapshot(s, 200).CanUse(MovementMask.Speed), "movement out-of-policy readback not usable");
        Slot(345, 8.00000000001); check((MovementSnapshot.FromSnapshot(s, 200).ValidFields & MovementMask.Run) == 0, "movement non-Float32 snapshot rejected");
        Slot(345, 8); Slot(458, 4); Slot(459, 0);
        check(MovementSnapshot.FromSnapshot(s, 200).Available && !MovementSnapshot.FromSnapshot(s, 200).CanUse(MovementMask.Speed), "known menu identity remains observable but cannot write");
    }

    private sealed class Fixture : IDisposable
    {
        public readonly int Pid = Random.Shared.Next(10000000, int.MaxValue);
        public readonly MemoryMappedFile Map; public readonly MemoryMappedViewAccessor View;
        public Fixture(int version = 4)
        {
            Map = MemoryMappedFile.CreateNew(BridgeProtocol.MappingPrefix + Pid, BridgeProtocol.MappingSize);
            View = Map.CreateViewAccessor(); View.Write(0, BridgeProtocol.Magic); View.Write(4, version); View.Write(12, 1);
            View.Write(BridgeProtocol.SupportedBits + (466 / 64) * 8, 1UL << (466 % 64));
        }
        public async Task<MovementOperationHandle> AwaitRequest(int previous = 0)
        {
            using var timeout = new CancellationTokenSource(3000);
            while (View.ReadInt32(BridgeProtocol.RequestSequence) == previous) await Task.Delay(1, timeout.Token);
            Thread.MemoryBarrier(); var b = new byte[128]; View.ReadArray(1024, b, 0, 128);
            var c = new MovementCommand((MovementOperation)R32(b, 48), new(R64(b, 24), R64(b, 32)), (MovementMask)R32(b, 52),
                new(R32(b, 56), R32(b, 60), R32(b, 64), R32(b, 68)), new(R32(b, 72), R32(b, 76), R32(b, 80), R32(b, 84)),
                R64(b, 40), R64(b, 88), R64(b, 96), R64(b, 112));
            return new(new(R64(b, 8), R64(b, 16), c), View.ReadInt32(BridgeProtocol.RequestSequence));
        }
        public void Complete(MovementOperationHandle h, byte[]? response = null)
        { var b = response ?? Response(h); View.WriteArray(1152, b, 0, b.Length); View.Write(556, 0); Thread.MemoryBarrier(); View.Write(548, h.Sequence); }
        public void Dispose() { View.Dispose(); Map.Dispose(); }
    }

    private static async Task TransportChecks(Action<bool, string> check)
    {
        using (var old = new Fixture(3)) Reject(() => { using var ignored = new BridgeConnection(old.Pid); }, "protocol4 host rejects old bridge rather than falling back", check);
        using var f = new Fixture(); var client = new MovementClientSession();
        using var bridge = new BridgeConnection(f.Pid, client);
        await RejectAsync(() => bridge.ExecuteAsync(1466, []), "generic command1466 is prohibited", check);
        using var pre = new CancellationTokenSource(); pre.Cancel();
        await RejectAsync(() => bridge.ExecuteMovementAsync(Acquire(), pre.Token), "prepublication cancellation has no request", check);
        check(f.View.ReadInt32(544) == 0 && bridge.PendingMovement == null, "cancelled-before-publication leaves idle channel");
        for (int i = 0; i < 8; i++) f.View.Write(560 + i * 8, 999d);
        var operation = bridge.ExecuteMovementAsync(Acquire()); var h = await f.AwaitRequest();
        check(Enumerable.Range(0, 8).All(i => f.View.ReadDouble(560 + i * 8) == 0) && h.Request.Command == Acquire(), "typed publication has zero generic args and exact copied command");
        f.Complete(h); var result = await operation;
        check(result.Acknowledged && result.Response!.HasReceipt && bridge.PendingMovement == null, "matched acknowledgement copies receipt then unlocks next publication");
        using var cancel = new CancellationTokenSource();
        var uncertainTask = bridge.ExecuteMovementAsync(Acquire(), cancel.Token); var late = await f.AwaitRequest(h.Sequence); cancel.Cancel();
        var uncertain = await uncertainTask;
        check(uncertain.InDoubt && uncertain.Handle == late && bridge.PendingMovement == late, "postpublication cancellation retains exact outstanding handle");
        await RejectAsync(() => bridge.ExecuteAsync(1344, [2]), "ordinary command blocked behind unknown movement outcome", check);
        await RejectAsync(() => bridge.ExecuteMovementAsync(Acquire()), "second typed publication blocked behind unknown outcome", check);
        var still = await bridge.ResolveMovementAsync(late);
        check(still.InDoubt && f.View.ReadInt32(544) == late.Sequence, "resolution while unacknowledged never publishes another request");
        f.Complete(late); var resolved = await bridge.ResolveMovementAsync(late);
        check(resolved.Acknowledged && resolved.Response!.Original == Original.Selected(MovementMask.Speed), "late acknowledgement resolves without replaying mutation");
        using var stop = new CancellationTokenSource();
        var lostTask = bridge.ExecuteMovementAsync(Acquire(), stop.Token); var lost = await f.AwaitRequest(late.Sequence); stop.Cancel(); await lostTask;
        f.Complete(lost, new byte[192]);
        var queryTask = bridge.ResolveMovementAsync(lost); var query = await f.AwaitRequest(lost.Sequence);
        check(query.Request.Command.Operation == MovementOperation.QueryOperation && query.Request.Command.TargetOperationId == lost.Request.OperationId &&
            query.Request.OperationId != lost.Request.OperationId, "malformed completed result recovers through distinct read-only journal query");
        f.Complete(query); var recovered = await queryTask;
        check(recovered.Acknowledged && recovered.Response!.ReceiptOperationId == lost.Request.OperationId, "query resolution returns retained mutation receipt, not a new write");
        using var reconnectCancel = new CancellationTokenSource();
        var reconnectTask = bridge.ExecuteMovementAsync(Acquire(), reconnectCancel.Token); var reconnect = await f.AwaitRequest(query.Sequence); reconnectCancel.Cancel(); await reconnectTask;
        bridge.Dispose();
        using var next = new BridgeConnection(f.Pid, client);
        check(next.PendingMovement == reconnect, "same client preserves outstanding publication across reconnect");
        f.Complete(reconnect); check((await next.ResolveMovementAsync(reconnect)).Acknowledged, "reconnect copies late receipt before any new publication");
        await RejectAsync(() => next.ResolveMovementAsync(reconnect), "settled or foreign handle cannot steal another result", check);
        check(next.ReadSnapshot().ProtocolVersion == 4, "snapshot exposes negotiated protocol version");
        using var ambiguousCancellation = new CancellationTokenSource();
        var ambiguousTask = next.ExecuteMovementAsync(Acquire(), ambiguousCancellation.Token); var ambiguous = await f.AwaitRequest(reconnect.Sequence);
        ambiguousCancellation.Cancel(); await ambiguousTask; f.Complete(ambiguous, new byte[192]);
        var missTask = next.ResolveMovementAsync(ambiguous); var miss = await f.AwaitRequest(ambiguous.Sequence);
        f.Complete(miss, Response(miss, MovementOutcome.OperationUnknown, MovementReason.ReceiptNotFound));
        check((await missTask).InDoubt && next.PendingMovement == miss, "query miss keeps ambiguous original globally blocked");
        await RejectAsync(() => next.ExecuteAsync(1344, [2]), "ordinary command remains blocked after query miss", check);
        await RejectAsync(() => next.ExecuteMovementAsync(Acquire()), "new movement mutation remains blocked after query miss", check);
        var rejectedQueryTask = next.ResolveMovementAsync(miss); var rejectedQuery = await f.AwaitRequest(miss.Sequence);
        f.Complete(rejectedQuery, Response(rejectedQuery, MovementOutcome.Rejected, MovementReason.HostExpired));
        check((await rejectedQueryTask).InDoubt, "query rejection does not settle the original mutation");
        next.Dispose(); using var reconnected = new BridgeConnection(f.Pid, client);
        await RejectAsync(() => reconnected.ExecuteAsync(1344, [2]), "ambiguous original survives reconnect after rejected query", check);
        var wrongReceiptTask = reconnected.ResolveMovementAsync(rejectedQuery); var wrongReceipt = await f.AwaitRequest(rejectedQuery.Sequence);
        var wrong = Response(wrongReceipt); W32(wrong, 104, BitConverter.SingleToUInt32Bits(5.5f)); W32(wrong, 120, BitConverter.SingleToUInt32Bits(5.5f));
        f.Complete(wrongReceipt, wrong);
        check((await wrongReceiptTask).InDoubt, "structurally valid recovered receipt must match original desired bits");
        var rightTask = reconnected.ResolveMovementAsync(wrongReceipt); var right = await f.AwaitRequest(wrongReceipt.Sequence); f.Complete(right);
        check((await rightTask).Acknowledged && reconnected.PendingMovement == null, "correct retained receipt finally clears ambiguous origin");
        using var faultCancellation = new CancellationTokenSource();
        var faultTask = reconnected.ExecuteMovementAsync(Acquire(), faultCancellation.Token); var fault = await f.AwaitRequest(right.Sequence);
        var unbound = Response(fault, MovementOutcome.Rejected, MovementReason.WriteFault);
        W32(unbound, 84, (uint)MovementJournalState.Uncertain); W32(unbound, 148, (uint)MovementResponseFlags.HasReceipt); W64(unbound, 152, fault.Request.OperationId);
        f.Complete(fault, unbound); var uncertainWrite = await faultTask;
        check(uncertainWrite.Acknowledged && uncertainWrite.Response!.JournalState == MovementJournalState.Uncertain && reconnected.PendingMovement == fault,
            "unbound write-fault receipt is observable but keeps global origin blocked");
        await RejectAsync(() => reconnected.ExecuteAsync(1344, [2]), "unbound uncertain write blocks ordinary commands", check);
        // Replace the shared channel's last packet, as reconnect to a different instance could do.
        f.View.Write(544, fault.Sequence + 50); f.View.Write(548, fault.Sequence + 50);
        var unprovedTask = reconnected.ResolveMovementAsync(fault); var unproved = await f.AwaitRequest(fault.Sequence + 50);
        var unprovedReply = Response(unproved, MovementOutcome.Rejected, MovementReason.StaleBridge); W64(unprovedReply, 24, 77);
        f.Complete(unproved, unprovedReply);
        check((await unprovedTask).InDoubt, "stale-bridge reply alone cannot discard an uncertain original");
        void Publish(int slot, double value)
        {
            f.View.Write(BridgeProtocol.Values + slot * 8, value);
            int offset = slot / 64 * 8; ulong bit = 1UL << (slot % 64);
            f.View.Write(BridgeProtocol.ValidBits + offset, f.View.ReadUInt64(BridgeProtocol.ValidBits + offset) | bit);
            f.View.Write(BridgeProtocol.SupportedBits + offset, f.View.ReadUInt64(BridgeProtocol.SupportedBits + offset) | bit);
        }
        Publish(463, unchecked((uint)Environment.TickCount)); Publish(469, 77); Publish(470, 0);
        var newBridgeTask = reconnected.ResolveMovementAsync(unproved); var newBridge = await f.AwaitRequest(unproved.Sequence);
        var replacement = Response(newBridge, MovementOutcome.Rejected, MovementReason.StaleBridge); W64(replacement, 24, 77);
        f.Complete(newBridge, replacement);
        check((await newBridgeTask).Acknowledged && reconnected.PendingMovement == null, "fresh independently observed new bridge permits explicit old-instance invalidation");
    }
}
