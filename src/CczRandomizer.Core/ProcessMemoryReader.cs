using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace CczRandomizer.Wpf.Core;

public interface IMemoryReader { byte[] Read(uint address, int length); }

public sealed class ProcessMemoryReader : IMemoryReader, IDisposable
{
    private readonly SafeProcessHandle _handle;
    public ProcessMemoryReader(int processId)
    {
        _handle = OpenProcess(0x0400 | 0x0010, false, processId);
        if (_handle.IsInvalid) { _handle.Dispose(); throw new Win32Exception(Marshal.GetLastWin32Error()); }
    }
    public byte[] Read(uint address, int length)
    {
        if (length < 0 || length > 16 * 1024 * 1024) throw new ArgumentOutOfRangeException(nameof(length));
        var data = new byte[length];
        if (!ReadProcessMemory(_handle, (nuint)address, data, (nuint)length, out var read)) throw new Win32Exception(Marshal.GetLastWin32Error());
        if (read != (nuint)length) throw new IOException($"游戏内存读取不完整：{read}/{length}");
        return data;
    }
    public void Dispose() => _handle.Dispose();
    [DllImport("kernel32.dll", SetLastError = true)] private static extern SafeProcessHandle OpenProcess(uint access, bool inherit, int processId);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool ReadProcessMemory(SafeProcessHandle process, nuint address, byte[] buffer, nuint size, out nuint read);
}
