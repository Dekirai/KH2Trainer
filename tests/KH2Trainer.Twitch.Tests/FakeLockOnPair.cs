using KH2Trainer.Twitch;
using KH2Trainer.Core;

internal sealed partial class FakeGame
{
    public bool LockOnSnapshotAvailable { get; set; } = true;
    public (float Scale, float Break)? NativeLockOnOverride { get; set; }
    public int LockOnWrites { get; private set; }
    public Action<double[]>? BeforeLockOnDispatch { get; set; }
    public LockOnPairSnapshot LockOnPair
    {
        get
        {
            if (!IsConnected || !SceneReady || !LockOnSnapshotAvailable || !Supports(475) || !Supports(476) || !Supports(373) ||
                Get("targeting.search_scale") is not double scale || Get("targeting.break_distance") is not double distance ||
                Get("targeting.default_break_distance") is not double retain) return LockOnPairSnapshot.Unavailable;
            uint scaleBits=BitConverter.SingleToUInt32Bits((float)scale),breakBits=BitConverter.SingleToUInt32Bits((float)distance);
            if(!LockOnPairSnapshot.ValidPair(scaleBits,breakBits)||!double.IsFinite(retain)||retain<.000001||retain>1000000)return LockOnPairSnapshot.Unavailable;
            return new(true, scaleBits, breakBits, BitConverter.SingleToUInt32Bits((float)retain));
        }
    }
    private void DispatchLockOnPair(double[] args)
    {
        BeforeLockOnDispatch?.Invoke(args);
        if (Gameplay.Role != PlayerRole.Sora || !Gameplay.IsControllable) throw new BridgeCommandRejectedException(3,"Sora control required.");
        if (args.Any(a => !double.IsFinite(a) || a < 0 || a > uint.MaxValue || a != Math.Truncate(a)) || args[0] > 1)
            throw new BridgeCommandRejectedException(2,"Exact raw bits required.");
        float expectedScale = BitConverter.UInt32BitsToSingle((uint)args[1]),expectedBreak = BitConverter.UInt32BitsToSingle((uint)args[2]);
        float desiredScale = BitConverter.UInt32BitsToSingle((uint)args[3]),desiredBreak = BitConverter.UInt32BitsToSingle((uint)args[4]);
        float retain = (float)(Get("targeting.default_break_distance") ?? throw new InvalidOperationException("Missing native parameters."));
        if (!LockOnPairSnapshot.ValidPair((uint)args[1], (uint)args[2]) || !LockOnPairSnapshot.ValidPair((uint)args[3], (uint)args[4]) ||
            args[0] == 0 && (BitConverter.SingleToUInt32Bits(retain) != (uint)args[5] || BitConverter.SingleToUInt32Bits(desiredScale * retain) != (uint)args[4]))
            throw new BridgeCommandRejectedException(2,"Invalid or stale pair.");
        var live = NativeLockOnOverride ?? ((float)(Get("targeting.search_scale") ?? throw new InvalidOperationException()),
            (float)(Get("targeting.break_distance") ?? throw new InvalidOperationException()));
        if (BitConverter.SingleToUInt32Bits(live.Item1) != BitConverter.SingleToUInt32Bits(expectedScale) ||
            BitConverter.SingleToUInt32Bits(live.Item2) != BitConverter.SingleToUInt32Bits(expectedBreak))
        {
            if (args[0] == 0) throw new BridgeCommandRejectedException(4,"Pair changed before apply.");
            return;
        }
        if (NativeLockOnOverride != null) NativeLockOnOverride = (desiredScale,desiredBreak);
        else { Set("targeting.search_scale", desiredScale); Set("targeting.break_distance", desiredBreak); }
        LockOnWrites++;
    }
}
