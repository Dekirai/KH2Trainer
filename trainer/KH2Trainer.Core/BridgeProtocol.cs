using System.IO.MemoryMappedFiles;
using System.Text;

namespace KH2Trainer.Core;

public static class BridgeProtocol
{
    public const int Magic = 0x4B483254;
    public const int Version = 3;
    public const int MappingSize = 16384;
    public const int ValueCount = 512;
    public const int MaskWordCount = ValueCount / 64;
    public const string MappingPrefix = "Local\\KH2Trainer_";
    public const int RequestSequence = 544, ResponseSequence = 548, Command = 552, ResultCode = 556;
    public const int Arguments = 560, ResultText = 640, ResultTextCharacters = 192;
    public const int Heartbeat = 624;
    public const int CommandIssuedAt = 628;
    public const int SnapshotSequence = 2048, SceneReady = 2052, ValidBits = 2056;
    public const int SupportedBits = ValidBits + MaskWordCount * sizeof(ulong);
    public const int Values = SupportedBits + MaskWordCount * sizeof(ulong);
}

public sealed class BridgeConnection : IDisposable
{
    private readonly MemoryMappedFile map;
    private readonly MemoryMappedViewAccessor view;
    private readonly SemaphoreSlim commands = new(1, 1);
    private bool disposed;

    public BridgeConnection(int pid)
    {
        map = MemoryMappedFile.OpenExisting(BridgeProtocol.MappingPrefix + pid, MemoryMappedFileRights.ReadWrite);
        try
        {
            view = map.CreateViewAccessor(0, BridgeProtocol.MappingSize, MemoryMappedFileAccess.ReadWrite);
            if (view.ReadInt32(0) == 0) throw new FileNotFoundException("The trainer bridge is starting.");
            if (view.ReadInt32(0) != BridgeProtocol.Magic || view.ReadInt32(4) != BridgeProtocol.Version)
                throw new InvalidDataException("A different trainer bridge is already loaded. Restart the game before reconnecting.");
        }
        catch { view?.Dispose(); map.Dispose(); throw; }
    }
    private string ReadText(long offset, int characters)
    {
        var bytes = new byte[characters * 2];
        view.ReadArray(offset, bytes, 0, bytes.Length);
        return Encoding.Unicode.GetString(bytes).Split('\0')[0];
    }
    public TrainerSnapshot ReadSnapshot()
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        view.Write(BridgeProtocol.Heartbeat, unchecked((uint)Environment.TickCount));
        for (var attempt = 0; attempt < 12; attempt++)
        {
            var sequence = view.ReadInt32(BridgeProtocol.SnapshotSequence);
            if ((sequence & 1) != 0) { Thread.Yield(); continue; }
            Thread.MemoryBarrier();
            var values = new double[BridgeProtocol.ValueCount];
            var valid = new ulong[BridgeProtocol.MaskWordCount]; var supported = new ulong[BridgeProtocol.MaskWordCount];
            view.ReadArray(BridgeProtocol.Values, values, 0, values.Length);
            view.ReadArray(BridgeProtocol.ValidBits, valid, 0, valid.Length);
            view.ReadArray(BridgeProtocol.SupportedBits, supported, 0, supported.Length);
            var ready = view.ReadInt32(BridgeProtocol.SceneReady) != 0;
            Thread.MemoryBarrier();
            if (sequence != view.ReadInt32(BridgeProtocol.SnapshotSequence)) continue;
            string message = "Updating game status…";
            for (int n = 0; n < 8; n++)
            {
                var generation = view.ReadInt32(28);
                if ((generation & 1) != 0) { Thread.Yield(); continue; }
                Thread.MemoryBarrier();
                var candidate = ReadText(32, 256);
                Thread.MemoryBarrier();
                if (generation == view.ReadInt32(28)) { message = candidate; break; }
            }
            return new TrainerSnapshot
            {
                Connected = true, SceneReady = ready, Status = view.ReadInt32(12), ErrorCode = view.ReadInt32(16),
                FrameCount = view.ReadUInt32(20), Flags = view.ReadUInt32(24), Message = message,
                Values = values, Valid = valid, Supported = supported
            };
        }
        throw new IOException("The game snapshot changed during reading. Try again on the next frame.");
    }
    public async Task<BridgeResult> ExecuteAsync(int command, IReadOnlyList<double> arguments, CancellationToken cancellation = default)
    {
        if (command <= 0 || arguments.Count > 8 || arguments.Any(v => !double.IsFinite(v)))
            throw new ArgumentException("Invalid trainer command.");
        await commands.WaitAsync(cancellation);
        try
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            if (view.ReadInt32(BridgeProtocol.RequestSequence) != view.ReadInt32(BridgeProtocol.ResponseSequence))
                throw new InvalidOperationException("The previous command is still pending. Resume the game and wait for its acknowledgement.");
            int sequence = unchecked(view.ReadInt32(BridgeProtocol.RequestSequence) + 1);
            if (sequence == 0) sequence = 1;
            for (int i = 0; i < 8; i++) view.Write(BridgeProtocol.Arguments + i * sizeof(double), i < arguments.Count ? arguments[i] : 0d);
            view.Write(BridgeProtocol.Command, command);
            view.Write(BridgeProtocol.CommandIssuedAt, unchecked((uint)Environment.TickCount));
            Thread.MemoryBarrier();
            view.Write(BridgeProtocol.RequestSequence, sequence);
            var timeout = DateTime.UtcNow.AddSeconds(8);
            while (view.ReadInt32(BridgeProtocol.ResponseSequence) != sequence)
            {
                cancellation.ThrowIfCancellationRequested();
                if (DateTime.UtcNow >= timeout)
                    throw new TimeoutException("The game has not acknowledged this command. An unstarted command expires after 8 seconds. Resume the game so it can acknowledge the result before issuing another action.");
                await Task.Delay(25, cancellation);
            }
            Thread.MemoryBarrier();
            return new BridgeResult(sequence, view.ReadInt32(BridgeProtocol.ResultCode), ReadText(BridgeProtocol.ResultText, BridgeProtocol.ResultTextCharacters));
        }
        finally { commands.Release(); }
    }
    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        try
        {
            // Prevent an unstarted request from surviving a quick reconnect.
            view.Write(BridgeProtocol.CommandIssuedAt, 0u);
            view.Write(BridgeProtocol.Heartbeat, 0u);
        }
        catch (ObjectDisposedException) { }
        finally { view.Dispose(); map.Dispose(); }
    }
}
