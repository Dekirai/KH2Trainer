using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace KH2Trainer.Core;

internal static class Win32
{
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern nint OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool CloseHandle(nint handle);
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern nint VirtualAllocEx(nint process, nint address, nuint size, uint allocation, uint protection);
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool VirtualFreeEx(nint process, nint address, nuint size, uint type);
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool WriteProcessMemory(nint process, nint address, byte[] data, nuint size, out nuint written);
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern nint CreateRemoteThread(nint process, nint attributes, nuint stack, nint start, nint parameter, uint flags, out uint tid);
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern uint WaitForSingleObject(nint handle, uint ms);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] internal static extern nint GetModuleHandle(string module);
    [DllImport("kernel32.dll", CharSet = CharSet.Ansi)] internal static extern nint GetProcAddress(nint module, string name);
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool IsWow64Process(nint process, out bool wow64);
    internal static Exception Error(string action) => new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), action);
}

public sealed class GameSession : IDisposable
{
    private Process? process;
    private BridgeConnection? connection;
    private readonly MovementClientSession movementClient = new();
    public bool Connected => connection != null && process is { HasExited: false };
    public int? ProcessId => process?.Id;
    public static void ValidatePayload(ReadOnlySpan<byte> data)
    {
        if (data.Length < 128 || data[0] != 'M' || data[1] != 'Z') throw new InvalidDataException("The trainer bridge is not a valid PE file.");
        int pe = BitConverter.ToInt32(data.Slice(60, 4));
        if (pe < 64 || pe > data.Length - 26 || BitConverter.ToUInt32(data.Slice(pe, 4)) != 0x4550 ||
            BitConverter.ToUInt16(data.Slice(pe + 4, 2)) != 0x8664 || BitConverter.ToUInt16(data.Slice(pe + 24, 2)) != 0x20B ||
            (BitConverter.ToUInt16(data.Slice(pe + 22, 2)) & 0x2000) == 0)
            throw new InvalidDataException("The trainer requires its native AMD64 bridge DLL.");
    }
    private static string ExtractPayload(byte[] payload)
    {
        ValidatePayload(payload);
        string hash = Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();
        string folder = Path.Combine(Path.GetTempPath(), "KH2Trainer", hash);
        Directory.CreateDirectory(folder);
        string path = Path.Combine(folder, "KH2Trainer.Bridge.dll");
        if (!File.Exists(path))
        {
            try { using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read); stream.Write(payload); }
            catch (IOException) when (File.Exists(path) && TargetGame.HashFile(path) == hash) { }
        }
        if (TargetGame.HashFile(path) != hash) throw new IOException("The extracted trainer bridge has a different checksum.");
        return path;
    }
    private static nint RemoteLoadLibrary(Process game)
    {
        nint local = Win32.GetProcAddress(Win32.GetModuleHandle("kernel32.dll"), "LoadLibraryW");
        if (local == 0) throw Win32.Error("LoadLibraryW is unavailable");
        using var self = Process.GetCurrentProcess();
        var owner = self.Modules.Cast<ProcessModule>().FirstOrDefault(m => local >= m.BaseAddress && local < m.BaseAddress + m.ModuleMemorySize)
            ?? throw new IOException("The system loader module could not be identified.");
        long offset = local.ToInt64() - owner.BaseAddress.ToInt64();
        game.Refresh();
        var remote = game.Modules.Cast<ProcessModule>().FirstOrDefault(m => string.Equals(m.ModuleName, owner.ModuleName, StringComparison.OrdinalIgnoreCase))
            ?? throw new IOException("The game has not loaded the required system library yet.");
        return (nint)(remote.BaseAddress.ToInt64() + offset);
    }
    private static void Inject(Process game, string path)
    {
        nint handle = Win32.OpenProcess(0x0002 | 0x0008 | 0x0010 | 0x0020 | 0x0400, false, game.Id);
        if (handle == 0) throw Win32.Error("Cannot open the game process. Run both programs under the same user permissions");
        nint memory = 0, thread = 0; bool mayFree = true;
        try
        {
            if (!Win32.IsWow64Process(handle, out bool wow)) throw Win32.Error("Cannot check the game architecture");
            if (wow) throw new InvalidDataException("The trainer requires the x64 game process.");
            byte[] bytes = Encoding.Unicode.GetBytes(path + '\0');
            memory = Win32.VirtualAllocEx(handle, 0, (nuint)bytes.Length, 0x3000, 4);
            if (memory == 0) throw Win32.Error("Cannot allocate the bridge path");
            if (!Win32.WriteProcessMemory(handle, memory, bytes, (nuint)bytes.Length, out nuint written) || written != (nuint)bytes.Length)
                throw Win32.Error("Cannot transfer the bridge path");
            thread = Win32.CreateRemoteThread(handle, 0, 0, RemoteLoadLibrary(game), memory, 0, out _);
            if (thread == 0) throw Win32.Error("Cannot load the trainer bridge");
            if (Win32.WaitForSingleObject(thread, 15000) != 0)
            {
                mayFree = false;
                throw new TimeoutException("Loading the bridge is taking longer than expected. Its path remains allocated because the loader may still use it. Check the game before reconnecting.");
            }
        }
        finally
        {
            if (thread != 0) Win32.CloseHandle(thread);
            if (memory != 0 && mayFree) Win32.VirtualFreeEx(handle, memory, 0, 0x8000);
            Win32.CloseHandle(handle);
        }
    }
    public async Task ConnectAsync(int pid, byte[] payload, IProgress<string>? progress = null, CancellationToken cancellation = default)
    {
        if (connection != null) throw new InvalidOperationException("Disconnect the current game first.");
        var game = Process.GetProcessById(pid);
        BridgeConnection? bridge = null;
        try
        {
            ValidatePayload(payload);
            progress?.Report("Verifying the game and mod loader…");
            await Task.Run(() => { TargetGame.Validate(game.MainModule?.FileName ?? ""); TargetGame.ValidateLoader(game); }, cancellation);
            var loadedBridge = game.Modules.Cast<ProcessModule>().FirstOrDefault(m => m.ModuleName.StartsWith("KH2Trainer.Bridge", StringComparison.OrdinalIgnoreCase));
            if (loadedBridge != null && TargetGame.HashFile(loadedBridge.FileName) != Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant())
                throw new InvalidOperationException("An older or different trainer bridge is still loaded. Restart the game before connecting this build.");
            try { bridge = new BridgeConnection(pid, movementClient); } catch (FileNotFoundException) { }
            if (bridge == null)
            {
                if (game.Modules.Cast<ProcessModule>().Any(m => m.ModuleName.StartsWith("KH2Trainer.Bridge", StringComparison.OrdinalIgnoreCase)))
                    throw new InvalidOperationException("A bridge is loaded without a usable status channel. Restart the game before reconnecting.");
                progress?.Report("Loading the game-thread bridge…");
                await Task.Run(() => Inject(game, ExtractPayload(payload)), cancellation);
            }
            DateTime deadline = DateTime.UtcNow.AddSeconds(15);
            while (true)
            {
                cancellation.ThrowIfCancellationRequested();
                if (game.HasExited) throw new IOException("The game exited while connecting.");
                if (bridge == null) { try { bridge = new BridgeConnection(pid, movementClient); } catch (FileNotFoundException) { } }
                if (bridge != null)
                {
                    var snapshot = bridge.ReadSnapshot();
                    if (snapshot.Status < 0) throw new InvalidOperationException(snapshot.Message);
                    if (snapshot.Status >= 1) { process = game; connection = bridge; return; }
                }
                if (DateTime.UtcNow >= deadline) throw new TimeoutException("The game bridge did not finish starting. Restart the game before retrying.");
                await Task.Delay(100, cancellation);
            }
        }
        catch { bridge?.Dispose(); game.Dispose(); throw; }
    }
    public TrainerSnapshot ReadSnapshot() => Connected ? connection!.ReadSnapshot() : TrainerSnapshot.Disconnected;
    public Task<BridgeResult> ExecuteAsync(int command, IReadOnlyList<double> values, CancellationToken cancellation = default) =>
        Connected ? connection!.ExecuteAsync(command, values, cancellation) : throw new InvalidOperationException("Connect to a running game first.");
    public MovementOperationHandle? PendingMovement => connection?.PendingMovement ?? movementClient.Pending;
    public Task<MovementCommandResult> ExecuteMovementAsync(MovementCommand command, CancellationToken cancellation = default) =>
        Connected ? connection!.ExecuteMovementAsync(command, cancellation) : throw new InvalidOperationException("Connect to a running game first.");
    public Task<MovementCommandResult> ResolveMovementAsync(MovementOperationHandle handle, CancellationToken cancellation = default) =>
        Connected ? connection!.ResolveMovementAsync(handle, cancellation) : throw new InvalidOperationException("Connect to a running game first.");
    public async Task DisconnectAsync()
    {
        try { if (Connected) await ExecuteAsync(1114, []); }
        finally { Dispose(); }
    }
    public void Dispose() { connection?.Dispose(); connection = null; process?.Dispose(); process = null; }
}
