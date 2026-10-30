using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace CczRandomizer.Wpf.Core;

/// <summary>Owns a game on a private desktop, its lifetime job, and its control helper.</summary>
public sealed class GameProcessSession : IAsyncDisposable
{
    public Process Process { get; }
    public NativeControlSession Controller { get; private set; } = null!;
    public GameWindows Windows { get; }
    private readonly SafeFileHandle _job;
    private readonly DesktopHandle _desktop;
    private bool _disposed;
    private GameProcessSession(Process process, SafeFileHandle job, DesktopHandle desktop)
    { Process = process; _job = job; _desktop = desktop; Windows = new(process.Id, desktop.DangerousGetHandle()); }

    public static async Task<GameProcessSession> StartAsync(string sandboxDirectory, string nativeDirectory, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var directory = Path.GetFullPath(sandboxDirectory);
        if (!File.Exists(Path.Combine(directory, ".ccz-wpf-sandbox"))) throw new IOException("游戏只能从工具管理的沙箱启动。");
        var executable = Path.Combine(directory, "Ekd5.exe");
        var desktopName = $"CCZWpf_{Environment.ProcessId}_{Guid.NewGuid():N}";
        var desktop = CreateDesktop(desktopName, null, 0, 0, 0x01CB, 0);
        if (desktop.IsInvalid) { desktop.Dispose(); throw new Win32Exception(Marshal.GetLastWin32Error()); }
        var startup = new StartupInfo { Size = Marshal.SizeOf<StartupInfo>(), Flags = 1, ShowWindow = 4, Desktop = desktopName };
        if (!CreateProcess(executable, new StringBuilder($"\"{executable}\""), 0, 0, false, 4, 0, directory, ref startup, out var info))
        { var error = Marshal.GetLastWin32Error(); desktop.Dispose(); throw new Win32Exception(error); }
        using var processHandle = new SafeProcessHandle(info.Process, true);
        using var thread = new SafeFileHandle(info.Thread, true);
        GameProcessSession? session = null;
        SafeFileHandle? job = null;
        try
        {
            job = CreateJobObject(0, null);
            if (job.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
            var limits = new ExtendedLimits { Basic = new BasicLimits { Flags = 0x2000 } }; // KILL_ON_JOB_CLOSE
            if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<ExtendedLimits>()) || !AssignProcessToJobObject(job, processHandle))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            session = new GameProcessSession(Process.GetProcessById(info.ProcessId), job, desktop);
            if (ResumeThread(thread) == uint.MaxValue) throw new Win32Exception(Marshal.GetLastWin32Error());
            var watch = Stopwatch.StartNew();
            var windows = session.Windows;
            while (watch.Elapsed < TimeSpan.FromSeconds(15))
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (session.Process.HasExited) throw new IOException($"游戏启动失败（退出代码 {session.Process.ExitCode}）。");
                if (windows.Main != 0)
                {
                    session.Controller = await NativeControlSession.StartAsync(info.ProcessId, nativeDirectory, cancellationToken);
                    // Scope audio interception to this owned process; never change the system mixer.
                    await session.Controller.ExecuteAsync(new NativeRequest(44), cancellationToken);
                    return session;
                }
                await Task.Delay(50, cancellationToken);
            }
            throw new TimeoutException("等待游戏主窗口超时。");
        }
        catch
        {
            if (session is not null) await session.DisposeAsync();
            else { TerminateProcess(processHandle, 1); WaitForSingleObject(processHandle, 5000); job?.Dispose(); desktop.Dispose(); }
            throw;
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        _disposed = true;
        try { if (Controller is not null) await Controller.DisposeAsync(); }
        finally
        {
            _job.Dispose();
            try { await Process.WaitForExitAsync(); }
            finally { Process.Dispose(); _desktop.Dispose(); }
        }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct StartupInfo
    {
        public int Size;
        public nint Reserved;
        public string? Desktop;
        public nint Title;
        public uint X, Y, XSize, YSize, XChars, YChars, FillAttribute, Flags;
        public ushort ShowWindow, ReservedSize;
        public nint ReservedBytes, Input, Output, Error;
    }
    [StructLayout(LayoutKind.Sequential)] private struct ProcessInfo { public nint Process, Thread; public int ProcessId, ThreadId; }
    [StructLayout(LayoutKind.Sequential)] private struct BasicLimits
    {
        public long ProcessTime, JobTime;
        public uint Flags;
        public nuint MinimumWorkingSet, MaximumWorkingSet;
        public uint ActiveProcesses;
        public nuint Affinity;
        public uint Priority, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)] private struct IoCounters { public ulong ReadOperations, WriteOperations, OtherOperations, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)] private struct ExtendedLimits
    {
        public BasicLimits Basic;
        public IoCounters Io;
        public nuint ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", EntryPoint = "CreateProcessW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateProcess(string application, StringBuilder command, nint processAttributes, nint threadAttributes, bool inherit, uint flags, nint environment, string directory, ref StartupInfo startup, out ProcessInfo info);
    [DllImport("kernel32.dll", EntryPoint = "CreateJobObjectW", CharSet = CharSet.Unicode, SetLastError = true)] private static extern SafeFileHandle CreateJobObject(nint attributes, string? name);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool SetInformationJobObject(SafeFileHandle job, int type, ref ExtendedLimits limits, uint length);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool AssignProcessToJobObject(SafeFileHandle job, SafeProcessHandle process);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern uint ResumeThread(SafeFileHandle thread);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool TerminateProcess(SafeProcessHandle process, uint code);
    [DllImport("kernel32.dll")] private static extern uint WaitForSingleObject(SafeProcessHandle process, uint timeout);
    private sealed class DesktopHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        public DesktopHandle() : base(true) { }
        protected override bool ReleaseHandle() => CloseDesktop(handle);
    }
    [DllImport("user32.dll", EntryPoint = "CreateDesktopW", CharSet = CharSet.Unicode, SetLastError = true)] private static extern DesktopHandle CreateDesktop(string name, string? device, nint mode, uint flags, uint access, nint attributes);
    [DllImport("user32.dll")] private static extern bool CloseDesktop(nint desktop);
}
