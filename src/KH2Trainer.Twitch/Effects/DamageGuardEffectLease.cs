using System.Security.Cryptography;
using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>One owner intent on the ordinary serialized command channel; this is not a MOV1 receipt.</summary>
internal sealed class DamageGuardEffectLease(IGameControl game)
{
    private readonly ulong owner = NewOwner();
    private ulong intentBridge;
    private bool stopping;
    private ActorMovementIdentity confirmed;
    public bool EverApplied { get; private set; }
    public bool PendingCleanup => intentBridge != 0;
    public string? Detail { get; private set; }
    public ActorMovementIdentity Identity => game.DamageGuard.Identity;
    public Readiness Readiness
    {
        get
        {
            var sample = game.DamageGuard;
            return !stopping && game.IsConnected && sample.CanEnsure && sample.Effective && sample.Owner == owner &&
                sample.Identity == confirmed ? Readiness.Ready : Readiness.Wait("Waiting for confirmed protection on the current character");
        }
    }

    public static Readiness StartReadiness(IGameControl game)
    {
        var sample = game.DamageGuard;
        if (!game.Supports(472) || !sample.CanEnsure) return Readiness.Wait("Waiting for fresh damage-guard ownership and character information");
        return sample.Effective ? Readiness.Reject("Damage protection is already active outside this reward.") : Readiness.Ready;
    }

    public async Task MaintainAsync(bool mayEnsure, bool release = false)
    {
        stopping |= release; // Irreversible: a deferred end must never issue another Ensure.
        if (!game.IsConnected) return;
        var sample = game.DamageGuard;
        if (intentBridge != 0 && sample.Available && sample.Identity.BridgeInstance != intentBridge)
        {
            // A fresh, independently observed new process nonce makes the old intent unreachable.
            intentBridge = 0; confirmed = default;
        }
        if (stopping)
        {
            if (intentBridge == 0) return;
            try
            {
                // Generation zero releases only this owner in this bridge, including an off-current lease.
                // The ordinary transport cannot publish this while an earlier Ensure lacks its ACK.
                await game.ExecuteAsync(1472, Arguments(0, owner, intentBridge, 0), "Twitch · release damage protection");
                intentBridge = 0; confirmed = default; Detail = null;
            }
            catch (Exception error) { Detail = "Waiting to release damage protection: " + error.Message; }
            return;
        }
        Observe(sample);
        if (!mayEnsure || !sample.CanEnsure || Readiness.Kind == ReadinessKind.Ready) return;
        if (sample.Effective && sample.Owner != owner) { Detail = "Damage protection is controlled by another action."; return; }
        intentBridge = sample.Identity.BridgeInstance; // Record before the await, even if publication or ACK is uncertain.
        confirmed = default;
        try
        {
            await game.ExecuteAsync(1472, Arguments(1, owner, intentBridge, sample.Identity.Generation), "Twitch · protect current character");
            Detail = null;
        }
        catch (Exception error) { Detail = "Waiting for damage protection: " + error.Message; }
        Observe(game.DamageGuard); // ACK alone never establishes paid protection.
    }

    private void Observe(DamageGuardSnapshot sample)
    {
        if (intentBridge != 0 && sample.CanEnsure && sample.Identity.BridgeInstance == intentBridge && sample.Effective && sample.Owner == owner)
        { confirmed = sample.Identity; EverApplied = true; }
    }

    private static double[] Arguments(uint operation, ulong owner, ulong bridge, ulong generation) =>
        [operation, (uint)owner, (uint)(owner >> 32), (uint)bridge, (uint)(bridge >> 32), (uint)generation, (uint)(generation >> 32)];
    private static ulong NewOwner()
    {
        ulong result;
        do { result = BitConverter.ToUInt64(RandomNumberGenerator.GetBytes(sizeof(ulong))); } while (result == 0);
        return result;
    }
}
