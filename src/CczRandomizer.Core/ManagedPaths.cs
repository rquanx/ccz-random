using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace CczRandomizer.Wpf.Core;

internal static class ManagedPaths
{
    public static bool IsContained(string root, string path) => Path.GetFullPath(path).StartsWith(
        Path.TrimEndingDirectorySeparator(Path.GetFullPath(root)) + Path.DirectorySeparatorChar,
        StringComparison.OrdinalIgnoreCase);

    public static bool HasLink(string path)
    {
        for (var current = Path.GetFullPath(path); current is not null; current = Path.GetDirectoryName(current))
        {
            if ((File.Exists(current) || Directory.Exists(current)) &&
                (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) return true;
        }
        return false;
    }

    public static IEnumerable<string> Files(string root)
    {
        if (!Directory.Exists(root) || HasLink(root)) yield break;
        foreach (var file in Directory.EnumerateFiles(root))
            if (!HasLink(file)) yield return file;
        foreach (var directory in Directory.EnumerateDirectories(root))
            foreach (var file in Files(directory)) yield return file;
    }

    public static long ReclaimableSize(string path)
    {
        using var handle = File.OpenHandle(path, FileMode.Open, FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete);
        if (!GetFileInformationByHandle(handle, out var info)) throw new Win32Exception(Marshal.GetLastWin32Error());
        return info.NumberOfLinks == 1 ? ((long)info.FileSizeHigh << 32) | info.FileSizeLow : 0;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct FileInformation
    {
        public uint Attributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime, AccessTime, WriteTime;
        public uint VolumeSerialNumber, FileSizeHigh, FileSizeLow, NumberOfLinks, FileIndexHigh, FileIndexLow;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInformation information);
}
