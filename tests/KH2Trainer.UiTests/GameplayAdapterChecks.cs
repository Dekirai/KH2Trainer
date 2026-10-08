using System.IO;
using System.Reflection;
using KH2Trainer;
using KH2Trainer.Core;
using KH2Trainer.Twitch;

internal static class GameplayAdapterChecks
{
    private class Host : ITwitchHost
    {
        public string UserFolder => "";
        public IReadOnlyList<FeatureDefinition> Catalog => [];
        public bool IsConnected { get; set; } = true;
        public TrainerSnapshot Snapshot { get; set; } = TrainerSnapshot.Disconnected;
        public bool FailRead { get; set; }
        public int Reads { get; private set; }
        public int OrdinaryCommands { get; private set; }
        public Action? OnOrdinaryCommand { get; set; }
        public bool FailOrdinaryCommand { get; set; }
        public Exception? OrdinaryError { get; set; }
        public TrainerSnapshot ReadGameSnapshot() { ++Reads; return FailRead ? throw new IOException("Fixture read failure") : Snapshot; }
        public Task Execute(int command, IReadOnlyList<double> arguments, string label) {
            ++OrdinaryCommands; OnOrdinaryCommand?.Invoke();
            if (OrdinaryError != null) return Task.FromException(OrdinaryError);
            return FailOrdinaryCommand ? Task.FromException(new IOException("Fixture command failure")) : Task.CompletedTask;
        }
        public void Log(string message) { }
        public void Notify(string message, bool isError) { }
    }

    private sealed class MovementHost : Host, ITwitchMovementHost
    {
        public MovementOperationHandle? PendingMovement { get; set; }
        public MovementCommand LastCommand { get; private set; }
        public MovementOperationHandle? LastResolved { get; private set; }
        public CancellationToken LastCancellation { get; private set; }
        public MovementCommandResult Result { get; set; } = null!;
        public Action? OnCommand { get; set; }
        public bool FailCommand { get; set; }
        public Task<MovementCommandResult> ExecuteMovementAsync(MovementCommand command, CancellationToken cancellation = default)
        {
            LastCommand = command; LastCancellation = cancellation; OnCommand?.Invoke();
            return FailCommand ? Task.FromException<MovementCommandResult>(new IOException("Fixture command failure")) : Task.FromResult(Result);
        }
        public Task<MovementCommandResult> ResolveMovementAsync(MovementOperationHandle handle, CancellationToken cancellation = default)
        {
            LastResolved = handle; LastCancellation = cancellation; OnCommand?.Invoke();
            return Task.FromResult(Result);
        }
    }

    private static IGameControl Adapter(ITwitchHost host)
    {
        var type = typeof(TwitchVm).Assembly.GetType("KH2Trainer.TrainerGameControl", throwOnError: true)!;
        return (IGameControl)Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
            binder: null, args: [host], culture: null)!;
    }

    private static void MovementChecks(Action<bool, string> check)
    {
        var identity = new ActorMovementIdentity(0xFEDCBA9876543210, 0x1234567887654321);
        var snapshot = new TrainerSnapshot { Connected = true, SceneReady = true, Status = 1, ProtocolVersion = 4 };
        void Set(int slot, double value)
        {
            snapshot.Values[slot] = value;
            snapshot.Valid[slot / 64] |= 1UL << (slot % 64);
            snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
        }
        Set(456, 1); Set(457, 1); Set(458, 0); Set(459, 1); Set(463, unchecked((uint)Environment.TickCount));
        Set(466, 1); Set(467, (uint)identity.Generation); Set(468, (uint)(identity.Generation >> 32));
        Set(469, (uint)identity.BridgeInstance); Set(470, (uint)(identity.BridgeInstance >> 32)); Set(471, 1);
        Set(344, 3); Set(345, 9); Set(346, 20); Set(347, 100);
        var legacy = new Host { Snapshot = snapshot };
        var legacyGame = Adapter(legacy);
        check(!legacyGame.Movement.Available && legacy.Reads == 0,
            "A host without the typed movement channel cannot advertise movement ownership from scalar metadata.");
        var host = new MovementHost { Snapshot = snapshot };
        var game = Adapter(host);
        var current = game.Movement;
        check(current.Identity == identity && current.CanUse(MovementMask.All) && host.Reads == 1,
            "The real adapter decodes all movement and identity fields from a single host snapshot, preserving UInt64 halves.");
        var command = new MovementCommand(MovementOperation.Acquire, identity, MovementMask.Speed,
            current.Values.Selected(MovementMask.Speed), MovementValues.FromValues(6, 18, 0, 0), EffectOwnerId: 0x123456789ABCDEF0);
        var handle = new MovementOperationHandle(new MovementRequest(0x8765432112345678, 0xFEDCBA9800000001, command), 37);
        var uncertain = new MovementCommandResult(handle, null, null, "Synthetic lost acknowledgement");
        host.Result = uncertain; host.PendingMovement = handle;
        check(ReferenceEquals(game.PendingMovement, handle), "The actual adapter preserves the unresolved operation handle.");
        bool legacyRefused = false;
        try { legacyGame.ExecuteMovementAsync(command).GetAwaiter().GetResult(); }
        catch (NotSupportedException) { legacyRefused = true; }
        check(legacyRefused && legacy.OrdinaryCommands == 0, "Typed movement never falls back to ordinary scalar commands.");
        using var cancellation = new CancellationTokenSource();
        host.OnCommand = () => { host.Snapshot = snapshot with { Values = (double[])snapshot.Values.Clone() }; host.Snapshot.Values[345] = 18; };
        int reads = host.Reads;
        var result = game.ExecuteMovementAsync(command, cancellation.Token).GetAwaiter().GetResult();
        check(ReferenceEquals(result, uncertain) && host.LastCommand == command && host.LastCancellation == cancellation.Token && host.OrdinaryCommands == 0,
            "The typed adapter forwards the exact request, cancellation token and uncertain result without fabricating acknowledgement.");
        check(game.Movement.Values.Run == BitConverter.SingleToUInt32Bits(18) && host.Reads > reads,
            "Even an uncertain typed result invalidates the adapter cache before the next movement observation.");
        host.OnCommand = () => { host.Snapshot = snapshot with { Values = (double[])snapshot.Values.Clone() }; host.Snapshot.Values[467] = (uint)identity.Generation + 1u; };
        reads = host.Reads;
        result = game.ResolveMovementAsync(handle, cancellation.Token).GetAwaiter().GetResult();
        check(ReferenceEquals(result, uncertain) && ReferenceEquals(host.LastResolved, handle) && host.LastCancellation == cancellation.Token,
            "The actual adapter passes the exact pending handle and preserves an unresolved recovery result.");
        check(game.Movement.Identity.Generation == identity.Generation + 1 && host.Reads > reads,
            "Recovery also invalidates cached actor identity; a replaced actor is observed in the next coherent snapshot.");
        host.FailCommand = true;
        host.OnCommand = () => { host.Snapshot = snapshot with { Values = (double[])snapshot.Values.Clone() }; host.Snapshot.Values[471] = 2; };
        bool failed = false;
        try { game.ExecuteMovementAsync(command).GetAwaiter().GetResult(); } catch (IOException) { failed = true; }
        check(failed && !game.Movement.Available, "A typed command exception invalidates the cache and does not hide a newly faulted lifetime observer.");
        host.FailCommand = false;
        host.OnCommand = () => host.Snapshot = snapshot with { ProtocolVersion = 3 };
        game.ResolveMovementAsync(handle).GetAwaiter().GetResult();
        check(!game.Movement.Available, "The real adapter refuses old protocol snapshots even when their scalar metadata looks valid.");
        host.OnCommand = () => host.Snapshot = snapshot;
        game.ResolveMovementAsync(handle).GetAwaiter().GetResult();
        Set(463, unchecked((uint)Environment.TickCount - 2000));
        check(!game.Movement.Available, "Typed movement metadata expires without requiring a disconnect.");
        Set(463, unchecked((uint)Environment.TickCount));
        check(game.Movement.CanUse(MovementMask.Speed), "Fresh coherent typed metadata restores movement observations.");
        host.IsConnected = false;
        check(!game.Movement.Available && ReferenceEquals(game.PendingMovement, handle),
            "Disconnect suppresses movement readiness while preserving the handle needed for recovery.");
    }

    private static void DamageGuardChecks(Action<bool, string> check)
    {
        ulong owner=0xFEDCBA9876543210, bridge=0x8877665544332211, generation=0xAABBCCDD11223344;
        var snapshot=new TrainerSnapshot { Connected=true, SceneReady=true, Status=1, ProtocolVersion=4 };
        void Set(int slot,double value) {
            snapshot.Values[slot]=value; snapshot.Valid[slot/64]|=1UL<<(slot%64); snapshot.Supported[slot/64]|=1UL<<(slot%64);
        }
        Set(456,1); Set(457,1); Set(458,0); Set(459,1); Set(463,unchecked((uint)Environment.TickCount));
        Set(106,1); Set(467,(uint)generation); Set(468,(uint)(generation>>32));
        Set(469,(uint)bridge); Set(470,(uint)(bridge>>32)); Set(471,1); Set(472,0);
        Set(473,(uint)owner); Set(474,(uint)(owner>>32));
        var host=new Host { Snapshot=snapshot }; var game=Adapter(host); var sample=game.DamageGuard;
        check(host.Reads==1 && sample.Effective && sample.Owner==owner && sample.Identity==new ActorMovementIdentity(bridge,generation) && sample.CanEnsure,
            "Guard ownership, effectiveness, player generation and control decode together from one actual-adapter read without a typed-movement host.");
        host.OnOrdinaryCommand=()=> { host.Snapshot=snapshot with { Values=(double[])snapshot.Values.Clone() }; host.Snapshot.Values[473]=0; host.Snapshot.Values[474]=0; };
        game.ExecuteAsync(1472,[],"fixture").GetAwaiter().GetResult();
        check(game.DamageGuard.Effective && game.DamageGuard.Owner==0 && host.Reads==2,
            "Ordinary owned-guard command invalidates the adapter cache and exposes a later manual owner coherently.");
        host.FailOrdinaryCommand=true;
        host.OnOrdinaryCommand=()=> { host.Snapshot=snapshot with { Values=(double[])snapshot.Values.Clone() }; host.Snapshot.Values[106]=0; host.Snapshot.Values[473]=0; host.Snapshot.Values[474]=0; host.Snapshot.Values[471]=2; };
        bool failed=false; try { game.ExecuteAsync(1472,[],"fixture").GetAwaiter().GetResult(); } catch(IOException) { failed=true; }
        sample=game.DamageGuard;
        check(failed && sample.Available && !sample.CanEnsure && !sample.Effective && sample.Identity.BridgeInstance==bridge,
            "A lost ordinary acknowledgement discards cached protection; an observer fault preserves only the fresh nonce needed for cleanup.");
        host.Snapshot.Values[106]=1;
        check(!game.DamageGuard.Available,"A faulted observer cannot advertise effective guard ownership.");
        host.Snapshot.Values[106]=0; host.Snapshot.Values[463]=unchecked((uint)Environment.TickCount-2000);
        check(!game.DamageGuard.Available,"Cached guard ownership expires with its native publication.");
        host.Snapshot.Values[463]=unchecked((uint)Environment.TickCount); host.IsConnected=false;
        check(!game.DamageGuard.Available,"Host disconnect suppresses cached guard ownership.");
    }

    private static void LockOnPairChecks(Action<bool, string> check)
    {
        var snapshot = new TrainerSnapshot { Connected=true, SceneReady=true, Status=1, ProtocolVersion=4 };
        void Set(int slot, double value) {
            snapshot.Values[slot]=value; snapshot.Valid[slot/64]|=1UL<<(slot%64); snapshot.Supported[slot/64]|=1UL<<(slot%64);
        }
        Set(456,1); Set(457,1); Set(458,0); Set(459,1); Set(463,unchecked((uint)Environment.TickCount));
        Set(475,BitConverter.SingleToUInt32Bits(1.25f)); Set(476,BitConverter.SingleToUInt32Bits(3210.5f)); Set(373,2000);
        var host = new Host { Snapshot=snapshot }; var game=Adapter(host);
        var pair=game.LockOnPair;
        check(pair.Available && pair.Scale==1.25f && pair.BreakDistance==3210.5f && pair.RetainDefault==2000 && host.Reads==1,
            "The actual adapter reads both exact targeting globals and their default from one publication.");
        host.OnOrdinaryCommand=()=> { host.Snapshot=snapshot with { Values=(double[])snapshot.Values.Clone() }; host.Snapshot.Values[476]=BitConverter.SingleToUInt32Bits(4567.25f); };
        game.ExecuteAsync(1475,[],"fixture").GetAwaiter().GetResult();
        pair=game.LockOnPair;
        check(pair.Available && pair.Scale==1.25f && pair.BreakDistance==4567.25f && host.Reads==2,
            "A paired command invalidates cached globals and exposes the next coherent pair.");
        host.FailOrdinaryCommand=true;
        host.OnOrdinaryCommand=()=> { host.Snapshot=snapshot with { Values=(double[])snapshot.Values.Clone() }; host.Snapshot.Values[373]=3000; };
        bool failed=false; try { game.ExecuteAsync(1475,[],"fixture").GetAwaiter().GetResult(); } catch(IOException) { failed=true; }
        check(failed && game.LockOnPair.Available && game.LockOnPair.RetainDefault==3000 && host.Reads==3,
            "A failed paired acknowledgement also discards the old default and pair cache.");
        host.Snapshot.Valid[476/64]&=~(1UL<<(476%64));
        check(!game.LockOnPair.Available,"A missing break-distance half cannot become a paired observation.");
        host.Snapshot.Valid[476/64]|=1UL<<(476%64);
        host.Snapshot.Values[463]=unchecked((uint)Environment.TickCount-2000);
        check(!game.LockOnPair.Available,"Paired targeting observations expire with the native publication.");
        host.Snapshot.Values[463]=unchecked((uint)Environment.TickCount);
        host.FailOrdinaryCommand=false; host.OnOrdinaryCommand=null;
        var rejection=new BridgeCommandRejectedException(4,"Actual native rejection fixture");
        host.OrdinaryError=rejection;
        Exception? received=null;
        try { game.ExecuteAsync(1475,[],"fixture").GetAwaiter().GetResult(); } catch(Exception error) { received=error; }
        check(ReferenceEquals(received,rejection) && received is BridgeCommandRejectedException { Code:4 },
            "The actual adapter preserves a received native rejection separately from a lost acknowledgement.");
        host.IsConnected=false;
        check(!game.LockOnPair.Available,"A disconnected host suppresses cached targeting globals.");
    }

    internal static object Run()
    {
        int count = 0;
        void Check(bool condition, string message) { ++count; if (!condition) throw new InvalidDataException(message); }
        var host = new Host();
        var game = Adapter(host);
        var snapshot = new TrainerSnapshot { Connected = true, Status = 1, SceneReady = true };
        void Set(int slot, double value)
        {
            snapshot.Values[slot] = value;
            snapshot.Valid[slot / 64] |= 1UL << (slot % 64);
            snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
        }
        Set(456, 1); Set(457, 1); Set(458, 0); Set(459, 1); Set(463, unchecked((uint)Environment.TickCount)); Set(0, 50);
        host.Snapshot = snapshot;
        Check(game.IsConnected && game.Gameplay.IsControllable && game.TryRead(0, out double hp) && hp == 50,
            "The real game adapter must expose a fresh coherent state.");
        Set(463, unchecked((uint)Environment.TickCount - 2000));
        Check(!game.Gameplay.Known && !game.TryRead(0, out _), "A cached snapshot must expire even when the connection stays open.");
        Set(463, unchecked((uint)Environment.TickCount));
        Check(game.Gameplay.IsControllable, "A fresh publication must resume observations.");
        host.FailRead = true;
        game.ExecuteAsync(1000, [50], "fixture").GetAwaiter().GetResult(); // Invalidates the actual adapter cache.
        Check(!game.IsConnected && !game.Gameplay.Known && !game.TryRead(0, out _),
            "A failed snapshot read must discard the previous controllable observation.");
        host.FailRead = false;
        Check(game.IsConnected && game.Gameplay.IsControllable, "A successful read after a transient failure must recover.");
        host.IsConnected = false;
        Check(!game.IsConnected && !game.Gameplay.Known && !game.TryRead(0, out _), "The host disconnect must override a cached connected snapshot.");
        MovementChecks(Check);
        DamageGuardChecks(Check);
        LockOnPairChecks(Check);
        return new { checks = count, nativeAccess = false };
    }
}
