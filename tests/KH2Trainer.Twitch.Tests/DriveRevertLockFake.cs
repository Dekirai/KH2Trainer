using KH2Trainer.Core;

internal sealed partial class FakeGame
{
    public ulong RevertLockBridge { get; set; } = 0xFEDCBA9876543210;
    public ulong RevertLockOwner { get; set; }
    public int RevertLockState { get; set; }
    public bool RevertLockSnapshotAvailable { get; set; } = true;
    public bool RevertLockLoseNextAck { get; set; }
    public bool RevertLockQueueWithoutAck { get; set; }
    public bool RevertLockAcceptWithoutApplying { get; set; }
    public bool RevertLockReleasePending { get; set; }
    public Action<double[]>? BeforeRevertLockDispatch { get; set; }
    private double[]? queuedRevertLock;
    public int RevertLockWrites { get; private set; }

    public DriveRevertLockSnapshot DriveRevertLock => IsConnected && RevertLockSnapshotAvailable &&
        Enumerable.Range(488, 5).All(Supports)
        ? new(true, RevertLockState, RevertLockOwner, RevertLockBridge) : DriveRevertLockSnapshot.Unavailable;

    private async Task ExecuteRevertLockAsync(double[] arguments)
    {
        if (arguments.Length != 5 || arguments.Any(v => !double.IsFinite(v) || v < 0 || v > uint.MaxValue || v != Math.Truncate(v)) ||
            arguments[0] > 1) throw new ArgumentException("Invalid Revert lock arguments.");
        if (Hold is { } hold) await hold.Task;
        BeforeRevertLockDispatch?.Invoke(arguments);
        if (!IsConnected) throw new InvalidOperationException("Disconnected.");
        if (Reject?.Invoke("drive.revert_lock", arguments) == true) throw new InvalidOperationException("Revert lock rejected.");
        if (queuedRevertLock != null) throw new InvalidOperationException("An earlier command still lacks its ACK.");
        if (RevertLockQueueWithoutAck && arguments[0] == 1)
        {
            RevertLockQueueWithoutAck = false;
            queuedRevertLock = arguments;
            throw new IOException("Acquire was published without an ACK.");
        }
        DispatchRevertLock(arguments);
        AfterExecute?.Invoke("drive.revert_lock", arguments);
        if (RevertLockLoseNextAck)
        {
            RevertLockLoseNextAck = false;
            throw new IOException("Command applied but ACK lost.");
        }
    }

    public void CompleteQueuedRevertLock()
    {
        var args = queuedRevertLock ?? throw new InvalidOperationException("No queued Acquire.");
        queuedRevertLock = null;
        DispatchRevertLock(args);
    }

    private void DispatchRevertLock(double[] args)
    {
        ulong owner = (uint)args[1] | ((ulong)(uint)args[2] << 32), bridge = (uint)args[3] | ((ulong)(uint)args[4] << 32);
        if (owner == 0 || bridge == 0 || bridge != RevertLockBridge) throw new InvalidOperationException("Wrong Revert lock identity.");
        if (args[0] == 0)
        {
            if (RevertLockOwner != owner) return; // Never modify a different owner.
            if (RevertLockReleasePending) { RevertLockState = 2; return; }
            RevertLockOwner = 0; RevertLockState = 0; RevertLockWrites++;
            return;
        }
        if (!SceneReady || !Gameplay.IsControllable || RevertLockState == 2 || RevertLockOwner != 0 && RevertLockOwner != owner)
            throw new InvalidOperationException("Cannot acquire Revert lock now.");
        if (RevertLockAcceptWithoutApplying) return;
        if (RevertLockOwner == owner && RevertLockState == 1) return;
        RevertLockOwner = owner; RevertLockState = 1; RevertLockWrites++;
    }

    public bool TryVoluntaryRevert()
    {
        if (RevertLockState == 1) return false;
        Set("player.form.id", 0);
        return true;
    }
}
