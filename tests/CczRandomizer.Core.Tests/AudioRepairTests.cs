using CczRandomizer.Wpf.Core;
using System.Runtime.InteropServices;

internal static class AudioRepairTests
{
    public static void Run()
    {
        var game = Path.Combine(Path.GetTempPath(), "audio-test", "Ekd5.exe");
        AudioProcess[] processes = [new(100, game), new(101, Path.Combine(Path.GetDirectoryName(game)!, "sandbox/Ekd5.exe")), new(102, Path.Combine(Path.GetTempPath(), "other/Ekd5.exe"))];
        var targeted = new List<int>();
        var result = AudioRepairService.Repair(game, processes, pid => { targeted.Add(pid); return new(1, 1); });
        if (result.Status != "repaired" || !targeted.SequenceEqual([100])) throw new Exception("声音修复作用到沙箱或其他游戏");
        if (AudioRepairService.Repair(game, processes, _ => new(1, 0)).Status != "not_needed") throw new Exception("非静音会话误报修复");
        if (AudioRepairService.Repair(game, processes, _ => new(0, 0)).Status != "unable") throw new Exception("没有声音会话仍报成功");
        if (AudioRepairService.Repair(game, [], _ => throw new Exception()).Status != "unable") throw new Exception("无游戏时仍报成功");
        if (AudioRepairService.Repair(game, processes, _ => throw new IOException("read error")).Status != "unable") throw new Exception("音频失败被忽略");
    }
    public static void Probe()
    {
        // PID above the Windows process-ID range: enumerate/query ABI only, never change a session.
        var result = CoreAudioRecovery.Restore(int.MaxValue);
        if (result != new AudioRecovery(0, 0)) throw new Exception("只读声音探测意外匹配进程");
        Console.WriteLine("Core Audio read-only device/session probe passed; no mute state changed.");
    }
    public static async Task SelfSessionSmoke()
    {
        // A silent PCM stream owned by this test process, not the game or another application.
        using var stream = new MemoryStream(); using var writer = new BinaryWriter(stream);
        writer.Write("RIFF"u8); writer.Write(16036); writer.Write("WAVEfmt "u8); writer.Write(16);
        writer.Write((short)1); writer.Write((short)1); writer.Write(8000); writer.Write(16000);
        writer.Write((short)2); writer.Write((short)16); writer.Write("data"u8); writer.Write(16000); writer.Write(new byte[16000]);
        var pinned = GCHandle.Alloc(stream.ToArray(), GCHandleType.Pinned);
        try
        {
            if (!PlaySound(pinned.AddrOfPinnedObject(), 0, 0xF)) throw new Exception("无法创建测试音频会话");
            AudioRecovery muted = new(0, 0);
            for (var i = 0; i < 30 && muted.Matched == 0; i++)
            { await Task.Delay(100); muted = CoreAudioRecovery.SetMuted(Environment.ProcessId, true); }
            if (muted.Matched == 0) throw new Exception("未找到测试进程自己的声音会话");
            var restored = CoreAudioRecovery.Restore(Environment.ProcessId);
            if (restored.Restored == 0 || CoreAudioRecovery.Restore(Environment.ProcessId).Restored != 0) throw new Exception("实际声音静音恢复未通过");
            Console.WriteLine("Core Audio self-session smoke passed: silent test stream muted, restored, and second restore correctly no-op; other process sessions untouched.");
        }
        finally { try { CoreAudioRecovery.Restore(Environment.ProcessId); } finally { PlaySound(0, 0, 0); pinned.Free(); } }
    }
    [DllImport("winmm.dll", EntryPoint = "PlaySoundW", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool PlaySound(nint sound, nint module, uint flags);
}
