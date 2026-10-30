using System.Buffers.Binary;

namespace CczRandomizer.Wpf.Core;

public static class GameSaveState
{
    public const uint MemoryAddress = 0x00501000;
    public const int MemorySize = 0x30000;
    public static byte[] ReadSave(string path)
    {
        using var input = File.OpenRead(path);
        var expected = new byte[MemorySize];
        try { input.ReadExactly(expected); }
        catch (EndOfStreamException error) { throw new InvalidDataException("存档长度不足，无法验证读取结果。", error); }
        return expected;
    }
    public static bool MatchesLoaded(IMemoryReader memory, ReadOnlySpan<byte> expected)
    {
        if (expected.Length != MemorySize) throw new ArgumentException("存档校验数据长度错误。", nameof(expected));
        return memory.Read(MemoryAddress, MemorySize).AsSpan().SequenceEqual(expected) &&
            memory.Read(0x004AB020, 1)[0] == 0 && BinaryPrimitives.ReadUInt32LittleEndian(memory.Read(0x004ABF9C, 4)) == 0;
    }
    public static uint[] InitialJobs(IMemoryReader memory) => ReadJobs(memory.Read(PersonnelMemoryReader.JobTableAddress, 28));
    public static void ValidateSource(ReadOnlySpan<byte> save)
    {
        if (save.Length < MemorySize) throw new InvalidDataException("第 20 栏存档长度不足。");
        if (ReadJobs(save.Slice(0x2F40, 28)).Any(x => x != 0))
            throw new InvalidDataException("第 20 栏已包含随机结果。请在许子将配置完成后、触发随机前保存到第 20 栏。");
    }
    private static uint[] ReadJobs(ReadOnlySpan<byte> bytes) =>
        [BinaryPrimitives.ReadUInt32LittleEndian(bytes), BinaryPrimitives.ReadUInt32LittleEndian(bytes[4..]), BinaryPrimitives.ReadUInt32LittleEndian(bytes[24..])];
}
