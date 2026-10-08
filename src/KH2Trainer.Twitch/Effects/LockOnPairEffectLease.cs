using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>Value ownership of global targeting settings; no actor lifetime or native receipt claim.</summary>
internal sealed class LockOnPairEffectLease(LockOnPairSnapshot original, float scale)
{
    private readonly uint appliedScale = BitConverter.SingleToUInt32Bits(scale);
    private readonly uint appliedBreak = BitConverter.SingleToUInt32Bits(scale * original.RetainDefault);
    public bool PendingCleanup { get; private set; }
    private bool stopping;

    public async Task ApplyAsync(EffectContext context)
    {
        if (stopping || PendingCleanup) throw new InvalidOperationException("A targeting pair already awaits cleanup.");
        // Ordinary command timeouts are not proof of no write. Register intent before publishing.
        PendingCleanup = true;
        try
        {
            await context.RunAsync("targeting.pair_compare_apply", 0, original.ScaleBits, original.BreakBits,
                appliedScale, appliedBreak, original.RetainBits);
        }
        catch (BridgeCommandRejectedException error) when (error.Code is 2 or 3 or 4)
        {
            // Only this handler's received statuses are proven pre-write. In particular a
            // foreign pair can already equal our desired pair: never restore it after rejection.
            PendingCleanup = false; throw;
        }
        catch (EffectDeferredException)
        {
            // RunAsync's synchronous RequireControl refused before command publication.
            PendingCleanup = false; throw;
        }
    }

    public Readiness Readiness(LockOnPairSnapshot current, bool mayEnd) => current.Available && mayEnd ? ReadinessReady :
        KH2Trainer.Twitch.Readiness.Wait("Waiting for the effect's complete lock-on settings");
    private static readonly Readiness ReadinessReady = KH2Trainer.Twitch.Readiness.Ready;

    public EffectProgress Progress(LockOnPairSnapshot current) => current.Available &&
        (current.ScaleBits != appliedScale || current.BreakBits != appliedBreak)
            ? EffectProgress.Ended("Lock-on settings changed elsewhere; the new settings were preserved") : EffectProgress.Running;

    public async Task RestoreAsync(EffectContext context)
    {
        stopping = true;
        if (!PendingCleanup) return;
        // A native mismatch is an acknowledged no-op. Missing host readback does not authorize a
        // scalar restore and does not prevent the native complete-pair comparison.
        await context.RunAsync("targeting.pair_compare_apply", 1, appliedScale, appliedBreak,
            original.ScaleBits, original.BreakBits, original.RetainBits);
        PendingCleanup = false;
    }
}
