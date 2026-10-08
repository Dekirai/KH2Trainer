using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal sealed partial class FakeGame
{
    private ActorMovementIdentity guardIdentity;
    private PlayerRole guardRole;
    private ulong guardOwner;
    private bool guardOn;
    private double[]? queuedGuard;
    public bool GuardSnapshotAvailable { get; set; } = true;
    public bool GuardAcceptWithoutApplying { get; set; }
    public bool GuardQueueWithoutAck { get; set; }
    public bool GuardLoseNextAck { get; set; }
    public TaskCompletionSource? GuardHold { get; set; }
    public Action<double[]>? BeforeGuardDispatch { get; set; }
    public Action<double[]>? AfterGuardDispatch { get; set; }
    public int GuardWrites { get; private set; }
    public ulong GuardOwner => guardOwner;
    public DamageGuardSnapshot DamageGuard
    {
        get
        {
            // Mirrors native lease invalidation separately from input readiness. A hit reaction
            // may block input without disabling the guard. Field pause retains the lease, but
            // the effective snapshot uses the stricter non-paused callback context.
            var state = Gameplay;
            bool contextRetained = state.Known && state.Role == guardRole &&
                (state.Blockers & ~(GameplayBlockers.InputBlocked | GameplayBlockers.TrainerFieldPause)) == 0;
            if (guardOn && (guardIdentity != new ActorMovementIdentity(MovementInstance, MovementGeneration) || !contextRetained))
            { guardOn = false; guardOwner = 0; Set("player_damage_guard", 0); }
            if (!IsConnected || !GuardSnapshotAvailable || !Supports(472)) return DamageGuardSnapshot.Unavailable;
            bool effective = guardOn && (state.Blockers & GameplayBlockers.TrainerFieldPause) == 0;
            Set("player_damage_guard", effective ? 1 : 0);
            return new(true, new(MovementInstance, MovementGeneration), state, effective, effective ? guardOwner : 0);
        }
    }
    public void SetManualGuard(bool enabled, ulong foreignOwner = 0)
    {
        guardOn = enabled; guardOwner = enabled ? foreignOwner : 0;
        guardIdentity = new(MovementInstance, MovementGeneration);
        guardRole = Gameplay.Role;
        Set("player_damage_guard", enabled ? 1 : 0);
    }
    public void CompleteQueuedGuard()
    {
        var args = queuedGuard ?? throw new InvalidOperationException("No queued guard request");
        queuedGuard = null; DispatchGuard(args);
    }
    private async Task ExecuteGuardAsync(double[] args)
    {
        if (args.Length != 7 || args.Any(a => !double.IsFinite(a) || a < 0 || a > uint.MaxValue || a != Math.Truncate(a)))
            throw new ArgumentException("Invalid guard words");
        if (queuedGuard != null) throw new InvalidOperationException("The previous command is still pending");
        if (GuardHold is { } hold) await hold.Task;
        if (!IsConnected) throw new InvalidOperationException("Disconnected");
        if (Reject?.Invoke("combat.damage_guard_owned", args) == true) throw new InvalidOperationException("Rejected by the bridge");
        if (GuardQueueWithoutAck)
        { GuardQueueWithoutAck = false; queuedGuard = args; throw new TimeoutException("Lost ACK before dispatch"); }
        BeforeGuardDispatch?.Invoke(args);
        DispatchGuard(args);
        AfterGuardDispatch?.Invoke(args);
        if (GuardLoseNextAck) { GuardLoseNextAck = false; throw new TimeoutException("Lost ACK after dispatch"); }
    }
    private void DispatchGuard(double[] args)
    {
        static ulong Join(double low, double high) => (uint)low | ((ulong)(uint)high << 32);
        ulong owner = Join(args[1], args[2]), bridge = Join(args[3], args[4]), generation = Join(args[5], args[6]);
        if (owner == 0 || bridge == 0 || bridge != MovementInstance) throw new InvalidOperationException("Invalid owner or bridge");
        _ = DamageGuard; // Simulates native tick invalidation before dispatch.
        if (args[0] == 0)
        {
            if (guardOn && bridge == MovementInstance && guardOwner == owner && (generation == 0 || generation == guardIdentity.Generation))
            { guardOn = false; guardOwner = 0; GuardWrites++; Set("player_damage_guard", 0); }
            return;
        }
        if (args[0] != 1 || !Gameplay.IsControllable || generation != MovementGeneration || bridge != MovementInstance || guardOn && guardOwner != owner)
            throw new InvalidOperationException("Guard identity or ownership changed");
        if (GuardAcceptWithoutApplying) return;
        guardIdentity = new(bridge, generation); guardRole = Gameplay.Role; guardOwner = owner; guardOn = true; GuardWrites++;
        Set("player_damage_guard", 1);
    }
}
