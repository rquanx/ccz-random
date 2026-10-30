using System.Diagnostics;
using System.Text.RegularExpressions;

namespace CczRandomizer.Wpf.Core;

public sealed record StorageUsage(string Category, string Name, long Total, long Cleanable, int Files);
public sealed record CleanupResult(int Removed, int Failed);

/// <summary>Only owned diagnostics and abandoned sessions; never results, saves or history.</summary>
public sealed class StorageCleanupService
{
    private static readonly Dictionary<string, string> Categories = new()
    { ["logs"] = "运行日志", ["screenshots"] = "故障截图", ["sandboxes"] = "残留沙箱" };
    private static readonly Regex SessionPattern = new(@"^(\d+)-\d+$");
    private static readonly Regex LogPattern = new(@"^fast_\d{8}_\d{6}(?:_diagnostic(?:_summary)?|_inspection_.*)?(?:\.part\d+)?\.(?:log|jsonl|json)$", RegexOptions.IgnoreCase);
    private static readonly Regex ImagePattern = new(@"^fast_\d{8}_\d{6}_(?:diagnostic_interaction_failure|inspection_failure)_.*\.png$", RegexOptions.IgnoreCase);
    private static readonly Regex TimingPattern = new(@"^concurrent_\d{8}_\d{6}_\d+_timing(?:\.part\d+)?\.jsonl$", RegexOptions.IgnoreCase);
    private readonly string _root;
    private readonly Func<int, bool> _processExists;
    private readonly Func<DateTime> _now;

    public StorageCleanupService(string root, Func<int, bool>? processExists = null, Func<DateTime>? now = null)
    {
        _root = Path.GetFullPath(root);
        _processExists = processExists ?? ProcessExists;
        _now = now ?? (() => DateTime.UtcNow);
    }

    private static bool ProcessExists(int pid)
    {
        try { using var process = Process.GetProcessById(pid); return !process.HasExited; }
        catch (ArgumentException) { return false; }
        // Inaccessible processes must be protected.
        catch (System.ComponentModel.Win32Exception) { return true; }
        catch (InvalidOperationException) { return true; }
    }

    private IEnumerable<(string Category, string Path, string? Session)> Candidates()
    {
        var logs = Path.Combine(_root, "ccz_fast_logs");
        if (Directory.Exists(logs) && !ManagedPaths.HasLink(logs))
            foreach (var path in Directory.EnumerateFiles(logs))
            {
                if (ManagedPaths.HasLink(path)) continue;
                var name = Path.GetFileName(path);
                if (ImagePattern.IsMatch(name)) yield return ("screenshots", path, null);
                else if (LogPattern.IsMatch(name) || TimingPattern.IsMatch(name)) yield return ("logs", path, null);
            }
        var sandboxes = Path.Combine(_root, "ccz_fast_data", "sandboxes");
        if (!Directory.Exists(sandboxes) || ManagedPaths.HasLink(sandboxes)) yield break;
        foreach (var session in Directory.EnumerateDirectories(sandboxes))
            foreach (var file in ManagedPaths.Files(session)) yield return ("sandboxes", file, session);
    }

    private bool Eligible(string path, string? session)
    {
        if (!ManagedPaths.IsContained(_root, path) || ManagedPaths.HasLink(path)) return false;
        if (session is null) return _now() - File.GetLastWriteTimeUtc(path) >= TimeSpan.FromDays(1);
        var match = SessionPattern.Match(Path.GetFileName(session));
        return match.Success && int.TryParse(match.Groups[1].Value, out var pid) && pid > 0 && !_processExists(pid);
    }

    public IReadOnlyList<StorageUsage> Scan()
    {
        var usage = Categories.ToDictionary(x => x.Key, x => new StorageUsage(x.Key, x.Value, 0, 0, 0));
        foreach (var item in Candidates())
        {
            try
            {
                var size = ManagedPaths.ReclaimableSize(item.Path);
                var eligible = Eligible(item.Path, item.Session);
                var row = usage[item.Category];
                usage[item.Category] = row with { Total = row.Total + size,
                    Cleanable = row.Cleanable + (eligible ? size : 0), Files = row.Files + (eligible ? 1 : 0) };
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        return usage.Values.ToArray();
    }

    public CleanupResult Clean(params string[] categories)
    {
        if (categories.Any(x => !Categories.ContainsKey(x))) throw new ArgumentException("未知清理分类");
        var removed = 0;
        var failed = 0;
        foreach (var item in Candidates())
        {
            if (!categories.Contains(item.Category)) continue;
            try
            {
                // Re-read process and modification time immediately before deleting.
                if (!Eligible(item.Path, item.Session)) continue;
                File.Delete(item.Path);
                removed++;
            }
            catch (IOException) { failed++; }
            catch (UnauthorizedAccessException) { failed++; }
        }
        return new(removed, failed);
    }
}
