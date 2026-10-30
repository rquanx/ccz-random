using System.Diagnostics;

namespace CczRandomizer.Wpf.Core;

public sealed record AudioRecovery(int Matched, int Restored);
public sealed record AudioRepairResult(string Status, string Message);
public sealed record AudioProcess(int Id, string Path);

public static class AudioRepairService
{
    public static AudioRepairResult Repair(string gameDirectory) => Repair(Path.Combine(gameDirectory, "Ekd5.exe"), FindProcesses(), CoreAudioRecovery.Restore);
    internal static AudioRepairResult Repair(string expectedExecutable, IEnumerable<AudioProcess> processes, Func<int, AudioRecovery> restore)
    {
        var expected = Path.GetFullPath(expectedExecutable); var found = 0; var matched = 0; var restored = 0;
        Exception? failure = null;
        foreach (var process in processes)
        {
            if (process.Id <= 0 || !Path.GetFullPath(process.Path).Equals(expected, StringComparison.OrdinalIgnoreCase)) continue;
            found++;
            try { var result = restore(process.Id); matched += result.Matched; restored += result.Restored; }
            catch (Exception error) { failure = error; }
        }
        if (restored > 0) return new("repaired", "游戏声音已恢复，请回到游戏确认音量。");
        if (failure is not null) return new("unable", $"声音状态检查失败：{failure.Message}");
        if (matched > 0) return new("not_needed", "正常游戏进程没有被静音，不需要修复。");
        return new("unable", found > 0 ? "已找到正常游戏，但尚未建立声音会话。请进入能播放声音的界面后重试。" : "未找到正在运行的正常游戏。请先启动游戏目录中的 Ekd5.exe，进入能播放声音的界面后重试。");
    }
    private static IReadOnlyList<AudioProcess> FindProcesses()
    {
        var result = new List<AudioProcess>();
        foreach (var process in Process.GetProcessesByName("Ekd5"))
            using (process)
                try { if (process.MainModule?.FileName is { } path) result.Add(new(process.Id, path)); }
                catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException) { }
        return result;
    }
}
