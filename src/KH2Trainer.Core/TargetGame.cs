using System.Diagnostics;
using System.Security.Cryptography;

namespace KH2Trainer.Core;

public static class TargetGame
{
    public const string Name = "KINGDOM HEARTS II FINAL MIX";
    public const string Filename = Name + ".exe";
    public const string Sha256 = "9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed";
    public const string PanaceaSha256 = "055d5032324eab2ed8f03f2a1b3ff3381642f82b3239a17164c25bef8815e68d";
    public const string DefaultPath = @"E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe";
    public static string HashFile(string path)
    {
        using var file = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant();
    }
    public static void Validate(string path)
    {
        if (!string.Equals(Path.GetFileName(path), Filename, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"Choose {Filename}.");
        if (!File.Exists(path)) throw new FileNotFoundException("The game executable was not found.", path);
        if (HashFile(path) != Sha256)
            throw new InvalidDataException("This game build is not supported. Expected the analyzed Steam build 1.0.0.2. No trainer changes were made.");
    }
    public static IReadOnlyList<GameProcess> FindRunning()
    {
        var result = new List<GameProcess>();
        foreach (var process in Process.GetProcessesByName(Name))
        {
            using (process)
            {
                try { result.Add(new GameProcess(process.Id, Name, process.MainModule?.FileName ?? "")); }
                catch (System.ComponentModel.Win32Exception) { result.Add(new GameProcess(process.Id, Name, "")); }
                catch (InvalidOperationException) { }
            }
        }
        return result;
    }
    public static void ValidateLoader(Process game)
    {
        var gamePath = game.MainModule?.FileName ?? throw new IOException("The game module is unavailable.");
        var localLoader = Path.Combine(Path.GetDirectoryName(gamePath)!, "dbghelp.dll");
        foreach (ProcessModule module in game.Modules)
        {
            if (module.ModuleName.StartsWith("KH2DevTools.Payload", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("The earlier developer-tools activator is loaded. Restart the game, then connect only this trainer.");
            if (string.Equals(module.FileName, localLoader, StringComparison.OrdinalIgnoreCase) && HashFile(module.FileName) != PanaceaSha256)
                throw new InvalidDataException("The loaded Panacea version is different from the verified build. No trainer changes were made.");
        }
    }
}
