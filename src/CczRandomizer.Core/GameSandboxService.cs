using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

namespace CczRandomizer.Wpf.Core;

public sealed class GameSandboxService
{
    private static readonly HashSet<string> ExcludedNames = new(StringComparer.OrdinalIgnoreCase)
        { "artifacts", "ccz_diagnostics", "ccz_fast_backup", "ccz_fast_data", "ccz_fast_logs", "ccz_r1_test", "randResult", "soundtrk", "wav", "兵种映射验证", "中文路径检查-20260925", "随即工具" };
    private static readonly HashSet<string> MutableRootFiles = new(StringComparer.OrdinalIgnoreCase)
        { "Ekd5.exe", "CczCustom.ini", "randomizer_settings.json" };
    private static readonly HashSet<string> MutableExtensions = new(StringComparer.OrdinalIgnoreCase) { ".ini", ".log", ".txt", ".json", ".jsonl", ".db", ".sqlite3", ".bak" };
    private const string Marker = ".ccz-wpf-sandbox";

    public string Create(string gameDirectory, string? root = null, string workerName = "worker-1", CancellationToken cancellation = default)
    {
        var source = new DirectoryInfo(Path.GetFullPath(gameDirectory));
        if (!File.Exists(Path.Combine(source.FullName, "Ekd5.exe"))) throw new FileNotFoundException("未找到游戏程序", Path.Combine(source.FullName, "Ekd5.exe"));
        if (ManagedPaths.HasLink(source.FullName)) throw new IOException("游戏目录不能是目录链接");
        if (!Regex.IsMatch(workerName, @"^[a-zA-Z0-9_-]+$")) throw new ArgumentException("实例名无效", nameof(workerName));
        var sandboxRoot = Path.GetFullPath(root ?? Path.Combine(source.FullName, "ccz_fast_data", "sandboxes"));
        if (ManagedPaths.HasLink(sandboxRoot)) throw new IOException("沙箱目录不能是目录链接");
        if (sandboxRoot.Equals(source.FullName, StringComparison.OrdinalIgnoreCase)) throw new IOException("沙箱根目录不能是游戏目录");
        var sourceSave = Path.Combine(source.FullName, "SV", "SV020.E5S");
        if (!File.Exists(sourceSave)) throw new FileNotFoundException("沙箱缺少第 20 栏源存档", sourceSave);
        Directory.CreateDirectory(sandboxRoot);
        var session = Path.Combine(sandboxRoot, $"{Environment.ProcessId}-{DateTime.UtcNow.Ticks}");
        var sandbox = Path.Combine(session, workerName);
        Directory.CreateDirectory(sandbox);
        File.WriteAllText(Path.Combine(sandbox, Marker), "1");
        try
        {
            foreach (var item in source.EnumerateFileSystemInfos())
            {
                cancellation.ThrowIfCancellationRequested();
                if (ManagedPaths.HasLink(item.FullName)) continue;
                if (item is DirectoryInfo && File.Exists(Path.Combine(item.FullName, ".ccz-wpf-release"))) continue;
                if (item.FullName.Equals(sandboxRoot, StringComparison.OrdinalIgnoreCase) || ManagedPaths.IsContained(item.FullName, sandboxRoot)) continue;
                if (item.Name.Equals(Marker, StringComparison.OrdinalIgnoreCase) || ExcludedNames.Contains(item.Name) || item.Name.StartsWith("ccz-inspect-", StringComparison.OrdinalIgnoreCase) || item.Name.Equals("Ekd5.ccz-fast-random.exe", StringComparison.OrdinalIgnoreCase) || item.Name.EndsWith("随机工具.exe", StringComparison.OrdinalIgnoreCase)) continue;
                var target = Path.Combine(sandbox, item.Name);
                if (item.Name.Equals("SV", StringComparison.OrdinalIgnoreCase) && item is DirectoryInfo)
                {
                    Directory.CreateDirectory(target);
                    File.Copy(sourceSave, Path.Combine(target, "SV020.E5S"));
                }
                else if (item is DirectoryInfo directory) CopyDirectory(directory.FullName, target, item.Name.Equals("RS", StringComparison.OrdinalIgnoreCase), cancellation);
                else if (item is FileInfo file) CopyFile(file.FullName, target, MutableRootFiles.Contains(item.Name) || MutableExtensions.Contains(file.Extension));
            }
            return sandbox;
        }
        catch { try { Remove(sandbox); } catch (IOException) { } throw; }
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
        if (!Directory.Exists(full)) return;
        var session = Path.GetDirectoryName(full)!;
        if (!Regex.IsMatch(Path.GetFileName(session), @"^\d+-\d+$") || ManagedPaths.HasLink(full) ||
            !File.Exists(Path.Combine(full, Marker))) throw new InvalidOperationException("拒绝删除非工具管理的沙箱目录");
        // No recursive delete follows a junction or link introduced after creation.
        // Keep ownership proof until all payload files are gone, so a sharing violation is retryable.
        var marker = Path.Combine(full, Marker);
        foreach (var file in ManagedPaths.Files(full))
            if (!file.Equals(marker, StringComparison.OrdinalIgnoreCase)) File.Delete(file);
        File.Delete(marker);
        DeleteEmptyDirectories(full);
        if (!Directory.EnumerateFileSystemEntries(session).Any()) Directory.Delete(session);
    }

    private static void DeleteEmptyDirectories(string directory)
    {
        foreach (var child in Directory.EnumerateDirectories(directory))
            if (!ManagedPaths.HasLink(child)) DeleteEmptyDirectories(child);
        if (!Directory.EnumerateFileSystemEntries(directory).Any()) Directory.Delete(directory);
    }

    private static void CopyFile(string source, string target, bool mutable)
    {
        if (!mutable && CreateHardLink(target, source, IntPtr.Zero)) return;
        File.Copy(source, target);
    }
    [DllImport("kernel32.dll", EntryPoint = "CreateHardLinkW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateHardLink(string target, string source, IntPtr security);

    private static void CopyDirectory(string source, string target, bool mutable, CancellationToken cancellation)
    {
        Directory.CreateDirectory(target);
        foreach (var file in Directory.EnumerateFiles(source))
        {
            cancellation.ThrowIfCancellationRequested();
            if (!ManagedPaths.HasLink(file)) CopyFile(file, Path.Combine(target, Path.GetFileName(file)), mutable || MutableExtensions.Contains(Path.GetExtension(file)));
        }
        foreach (var child in Directory.EnumerateDirectories(source))
        {
            cancellation.ThrowIfCancellationRequested();
            if (!ManagedPaths.HasLink(child)) CopyDirectory(child, Path.Combine(target, Path.GetFileName(child)), mutable, cancellation);
        }
    }
}
