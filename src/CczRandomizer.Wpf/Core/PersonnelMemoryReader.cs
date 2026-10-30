using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace CczRandomizer.Wpf.Core;

public sealed class ProcessMemoryReader : IDisposable
{
    private const uint QueryInformation = 0x0400;
    private const uint VirtualMemoryRead = 0x0010;
    private readonly IntPtr _handle;
    public ProcessMemoryReader(int processId)
    {
        _handle = OpenProcess(QueryInformation | VirtualMemoryRead, false, processId);
        if (_handle == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    public byte[] Read(nuint address, int length)
    {
        var data = new byte[length];
        if (!ReadProcessMemory(_handle, (IntPtr)address, data, length, out var read) || read.ToInt64() != length)
            throw new Win32Exception(Marshal.GetLastWin32Error());
        return data;
    }
    public void Dispose() { if (_handle != IntPtr.Zero) CloseHandle(_handle); GC.SuppressFinalize(this); }
    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr OpenProcess(uint access, bool inherit, int processId);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool ReadProcessMemory(IntPtr process, IntPtr address, byte[] buffer, int size, out IntPtr read);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool CloseHandle(IntPtr handle);
}

public sealed record PersonnelRecord(int Index, string Name, uint MemberId, byte JobId);

public static class PersonnelMemoryReader
{
    public const uint RecordArrayBasePointerAddress = 0x004CEA00;
    public const uint JobTableAddress = 0x00503F40;
    public const int RecordSize = 0x48;

    public static IReadOnlyList<PersonnelRecord> Read(ProcessMemoryReader reader, IReadOnlyList<int> indices)
    {
        if (indices.Count == 0 || indices.Any(index => index is < 0 or > 1023) || indices.Distinct().Count() != indices.Count)
            throw new ArgumentOutOfRangeException(nameof(indices), "人物记录编号必须是 0 到 1023 且不能重复。");
        var baseAddress = BitConverter.ToUInt32(reader.Read(RecordArrayBasePointerAddress, 4));
        var result = new List<PersonnelRecord>(indices.Count);
        foreach (var index in indices)
        {
            var record = reader.Read((nuint)(baseAddress + (uint)(index * RecordSize)), RecordSize);
            var expectedId = 0x1000u + (uint)index;
            if (BitConverter.ToUInt32(record, 0) != expectedId) throw new InvalidDataException($"人物记录 {index} 标识不匹配。");
            var nameEnd = Array.IndexOf(record, (byte)0, 8, 9); if (nameEnd < 0) nameEnd = 17;
            var name = Encoding.GetEncoding(936).GetString(record, 8, nameEnd - 8);
            if (string.IsNullOrWhiteSpace(name)) throw new InvalidDataException($"人物记录 {index} 名称为空。");
            result.Add(new PersonnelRecord(index, name, BitConverter.ToUInt32(record, 4), record[0x2B]));
        }
        return result;
    }

    public static IReadOnlyList<uint> ReadCurrentJobs(ProcessMemoryReader reader, IReadOnlyList<int> indices)
    {
        if (indices.Count == 0) return [];
        var table = reader.Read(JobTableAddress, (indices.Max() + 1) * 4);
        return indices.Select(index => BitConverter.ToUInt32(table, index * 4)).ToArray();
    }
}
