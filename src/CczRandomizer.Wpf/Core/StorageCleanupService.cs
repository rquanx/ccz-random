using System.IO;

namespace CczRandomizer.Wpf.Core;

public static class StorageCleanupService
{
    public static long GetDirectorySize(string path)
        => Directory.Exists(path) ? Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories).Sum(file => new FileInfo(file).Length) : 0;

    public static int ClearDirectory(string path)
    {
        if (!Directory.Exists(path)) return 0;
        var count = 0;
        foreach (var file in Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories).ToArray())
        {
            try { File.Delete(file); count++; } catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        foreach (var directory in Directory.EnumerateDirectories(path, "*", SearchOption.AllDirectories).OrderByDescending(x => x.Length).ToArray())
        {
            try { Directory.Delete(directory, false); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }
        return count;
    }
}
