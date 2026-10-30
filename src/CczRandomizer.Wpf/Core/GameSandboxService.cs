using System.Diagnostics;
using System.IO;

namespace CczRandomizer.Wpf.Core;

public sealed class GameSandboxService
{
    private static readonly HashSet<string> ExcludedNames = new(StringComparer.OrdinalIgnoreCase)
        { "artifacts", "ccz_diagnostics", "ccz_fast_backup", "ccz_fast_data", "ccz_fast_logs", "randResult", "soundtrk", "wav" };

    public string Create(string gameDirectory, string? root = null, string workerName = "worker-1")
    {
        var source = new DirectoryInfo(Path.GetFullPath(gameDirectory));
        if (!File.Exists(Path.Combine(source.FullName, "Ekd5.exe"))) throw new FileNotFoundException("未找到游戏程序", Path.Combine(source.FullName, "Ekd5.exe"));
        var sandboxRoot = root ?? Path.Combine(source.FullName, "ccz_fast_data", "sandboxes");
        Directory.CreateDirectory(sandboxRoot);
        var sandbox = Path.Combine(sandboxRoot, $"{workerName}-{Environment.ProcessId}-{Guid.NewGuid():N}");
        Directory.CreateDirectory(sandbox);
        try
        {
            foreach (var item in source.EnumerateFileSystemInfos())
            {
                if (ExcludedNames.Contains(item.Name) || item.Name.EndsWith("随机工具.exe", StringComparison.OrdinalIgnoreCase)) continue;
                var target = Path.Combine(sandbox, item.Name);
                if (item is DirectoryInfo directory) CopyDirectory(directory.FullName, target);
                else if (item is FileInfo file) File.Copy(file.FullName, target, true);
            }
            return sandbox;
        }
        catch { try { Directory.Delete(sandbox, true); } catch { } throw; }
    }

    public static Process StartGame(string sandboxDirectory)
    {
        var executable = Path.Combine(sandboxDirectory, "Ekd5.exe");
        if (!File.Exists(executable)) throw new FileNotFoundException("沙箱缺少游戏程序", executable);
        return Process.Start(new ProcessStartInfo(executable) { WorkingDirectory = sandboxDirectory, UseShellExecute = true })
            ?? throw new InvalidOperationException("无法启动游戏进程");
    }

    public static void Remove(string sandboxDirectory)
    {
        var full = Path.GetFullPath(sandboxDirectory);
        if (!full.Contains(Path.DirectorySeparatorChar + "sandboxes" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("拒绝删除非沙箱目录");
        if (Directory.Exists(full)) Directory.Delete(full, true);
    }

    private static void CopyDirectory(string source, string target)
    {
        Directory.CreateDirectory(target);
        foreach (var file in Directory.EnumerateFiles(source)) File.Copy(file, Path.Combine(target, Path.GetFileName(file)), true);
        foreach (var child in Directory.EnumerateDirectories(source)) CopyDirectory(child, Path.Combine(target, Path.GetFileName(child)));
    }
}
