using System.Security.Cryptography;
using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>One command-table owner intent. This lease never takes ownership again after loss or stopping.</summary>
internal sealed class DriveRevertEffectLease(IGameControl game)
{
    private readonly ulong owner = NewOwner();
    private ulong intentBridge, admittedBridge;
    private bool stopping, confirmed;
    public bool PendingCleanup => intentBridge != 0;
    public bool OwnershipLost { get; private set; }
    public bool ForeignIdentity { get; private set; }
    public string? Detail { get; private set; }
    public Readiness Readiness => !stopping && !OwnershipLost && game.IsConnected && Owns(game.DriveRevertLock)
        ? Readiness.Ready : Readiness.Wait("Waiting for this reward's voluntary Revert lock");

    private bool Owns(DriveRevertLockSnapshot sample) => sample.Effective && intentBridge != 0 &&
        sample.BridgeInstance == intentBridge && sample.Owner == owner;

    public static Readiness StartReadiness(IGameControl game, DriveRevertEffectLease? releasing)
        => StartReadiness(game, game.DriveRevertLock, releasing);

    private static Readiness StartReadiness(IGameControl game, DriveRevertLockSnapshot sample, DriveRevertEffectLease? releasing)
    {
        if (!game.IsConnected || !game.Supports(488) || !sample.Available)
            return Readiness.Wait("Waiting for fresh voluntary Revert lock information");
        if (sample.CleanupPending) return Readiness.Wait("Waiting until the previous Revert lock is released");
        if (sample.Effective && !(releasing?.Owns(sample) == true && !releasing.stopping && !releasing.OwnershipLost))
            return Readiness.Reject("Voluntary Revert is controlled by another action.");
        return Readiness.Ready;
    }

    public async Task AcquireAsync()
    {
        if (stopping || intentBridge != 0 || OwnershipLost) throw new EffectRejectedException("This Revert lock cannot be acquired again.");
        var sample = game.DriveRevertLock;
        var readiness = StartReadiness(game, sample, null);
        if (readiness.Kind != ReadinessKind.Ready) throw new EffectDeferredException(readiness.Reason);
        intentBridge = admittedBridge = sample.BridgeInstance; // Retain the admitted sample even if publication or ACK becomes uncertain.
        await game.ExecuteAsync(1488, Arguments(1), "Twitch · lock voluntary Revert");
    }

    public bool Confirm()
    {
        if (Readiness.Kind != ReadinessKind.Ready) return false;
        confirmed = true;
        return true;
    }

    public EffectProgress ObserveProgress(bool established)
    {
        if (stopping || !confirmed || !game.IsConnected) return EffectProgress.Running;
        var sample = game.DriveRevertLock;
        if (!sample.Available) return EffectProgress.Running; // A missing observation proves no takeover.
        ObserveForeignIdentity(sample);
        if (!Owns(sample)) OwnershipLost = true;
        if (!OwnershipLost) return EffectProgress.Running;
        const string reason = "The reward's voluntary Revert lock is no longer effective.";
        return established ? EffectProgress.Ended(reason) : EffectProgress.Failed(reason);
    }

    public async Task ReleaseAsync()
    {
        stopping = true;
        if (!game.IsConnected) return;
        var sample = game.DriveRevertLock;
        ObserveForeignIdentity(sample);
        if (intentBridge == 0) return;
        if (sample.Available && sample.BridgeInstance != intentBridge)
        {
            intentBridge = 0; Detail = null; // Fresh different process nonce makes the old command intent unreachable.
            return;
        }
        try
        {
            // No player-control gate: native release validates only our token and bridge, even while loading.
            // The ordinary channel serializes this behind an Acquire with an uncertain acknowledgement.
            await game.ExecuteAsync(1488, Arguments(0), "Twitch · release voluntary Revert lock");
            sample = game.DriveRevertLock;
            ObserveForeignIdentity(sample);
            if (sample.Available && (sample.BridgeInstance != intentBridge || sample.Owner != owner))
            { intentBridge = 0; Detail = null; }
            else Detail = "Waiting to confirm that the voluntary Revert lock was released.";
        }
        catch (Exception error) { Detail = "Waiting to release the voluntary Revert lock: " + error.Message; }
    }

    private void ObserveForeignIdentity(DriveRevertLockSnapshot sample)
    {
        // A deferred form end may resume after its lock was already released. Keep the
        // admitted bridge identity so that it cannot revert a same-ID form in a new game
        // or one controlled by a later owner. Owner zero after our own release is normal.
        if (admittedBridge != 0 && sample.Available &&
            (sample.BridgeInstance != admittedBridge || sample.Owner != 0 && sample.Owner != owner))
            OwnershipLost = ForeignIdentity = true;
    }

    private double[] Arguments(uint operation) =>
        [operation, (uint)owner, (uint)(owner >> 32), (uint)intentBridge, (uint)(intentBridge >> 32)];

    private static ulong NewOwner()
    {
        ulong result;
        do { result = BitConverter.ToUInt64(RandomNumberGenerator.GetBytes(sizeof(ulong))); } while (result == 0);
        return result;
    }
}
