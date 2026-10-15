using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace KH2Trainer.Core;

internal static class AssetFileAccess
{
    [StructLayout(LayoutKind.Sequential)]
    private struct FileInformation
    {
        public uint Attributes, CreationLow, CreationHigh, AccessLow, AccessHigh, WriteLow, WriteHigh;
        public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInformation info);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(string path, uint access, uint share, nint security,
        uint creation, uint flags, nint template);

    internal static AssetFileStamp Stamp(string path, FileStream file)
    {
        if (!GetFileInformationByHandle(file.SafeFileHandle, out var info))
            throw new IOException("Cannot identify the asset source.", new Win32Exception(Marshal.GetLastWin32Error()));
        if ((info.Attributes & (uint)(FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
            throw new IOException("An asset source must be a regular file.");
        return new(path, checked((long)(((ulong)info.SizeHigh << 32) | info.SizeLow)),
            ((ulong)info.WriteHigh << 32) | info.WriteLow, info.Volume,
            ((ulong)info.IndexHigh << 32) | info.IndexLow,
            ((ulong)info.CreationHigh << 32) | info.CreationLow);
    }

    // Holding every directory without FILE_SHARE_DELETE prevents a folder/junction
    // swap between output validation, temporary-file creation and atomic publication.
    internal static IDisposable LockDirectories(string directory)
    {
        var paths = new Stack<string>();
        for (string? p = Path.GetFullPath(directory); p is not null; p = Path.GetDirectoryName(p))
        {
            paths.Push(p);
            if (Path.GetPathRoot(p) == p) break;
        }
        var handles = new DirectoryLocks();
        try
        {
            foreach (string path in paths)
            {
                // OPEN_EXISTING, BACKUP_SEMANTICS | OPEN_REPARSE_POINT.
                var handle = CreateFile(path, 0, 3, 0, 3, 0x02200000, 0);
                handles.Handles.Add(handle);
                if (handle.IsInvalid || !GetFileInformationByHandle(handle, out var info))
                    throw new IOException("Cannot lock the extraction folder.", new Win32Exception(Marshal.GetLastWin32Error()));
                if ((info.Attributes & (uint)FileAttributes.Directory) == 0 ||
                    (info.Attributes & (uint)FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Extraction folders must be regular directories without reparse points.");
            }
            return handles;
        }
        catch { handles.Dispose(); throw; }
    }
    private sealed class DirectoryLocks : IDisposable
    {
        internal readonly List<SafeFileHandle> Handles = [];
        public void Dispose() { for (int i = Handles.Count - 1; i >= 0; i--) Handles[i].Dispose(); }
    }
}
