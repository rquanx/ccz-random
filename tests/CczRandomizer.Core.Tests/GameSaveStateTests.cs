using System.IO.Compression;
using CczRandomizer.Wpf.Core;

internal static class GameSaveStateTests
{
    public static void Run()
    {
        using var compressed = File.OpenRead(Path.Combine(AppContext.BaseDirectory, "runtime_22/source-state.bin.gz"));
        using var gzip = new GZipStream(compressed, CompressionMode.Decompress);
        using var output = new MemoryStream(); gzip.CopyTo(output);
        var expected = output.ToArray();
        var memory = new StateMemory(expected);
        GameSaveState.ValidateSource(expected);
        Check(GameSaveState.InitialJobs(memory).SequenceEqual(new uint[] { 0, 0, 0 }), "真实源存档初始兵种应未随机");
        Check(GameSaveState.MatchesLoaded(memory, expected), "完整源内存匹配未通过");
        memory.State[^1] ^= 1;
        Check(!GameSaveState.MatchesLoaded(memory, expected), "只比较人物区域会误判不完整读档");
        memory.State[^1] ^= 1;
        memory.Active = 1;
        Check(!GameSaveState.MatchesLoaded(memory, expected), "过渡状态未结束就接受读档");
        memory.Active = 0; memory.Transition = 1;
        Check(!GameSaveState.MatchesLoaded(memory, expected), "加载状态未清零就接受读档");
        memory.Transition = 0;
        var random = new RecordedMemory(Path.Combine(AppContext.BaseDirectory, "fixtures/randomized-memory.json"));
        random.Read(PersonnelMemoryReader.JobTableAddress, 28).CopyTo(memory.State, 0x2F40);
        ExpectInvalid(() => GameSaveState.ValidateSource(memory.State));
        var path = Path.Combine(Path.GetTempPath(), $"ccz-save-validation-{Guid.NewGuid():N}.E5S");
        try
        {
            File.WriteAllBytes(path, expected.Concat(new byte[] { 1, 2, 3 }).ToArray());
            Check(GameSaveState.ReadSave(path).SequenceEqual(expected), "存档前缀读取错误");
            File.WriteAllBytes(path, expected[..^1]);
            ExpectInvalid(() => GameSaveState.ReadSave(path));
        }
        finally { File.Delete(path); }
    }
    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static void ExpectInvalid(Action action)
    {
        try { action(); } catch (InvalidDataException) { return; }
        throw new Exception("损坏或已经随机的存档未拒绝");
    }
    private sealed class StateMemory(byte[] state) : IMemoryReader
    {
        public byte[] State { get; } = (byte[])state.Clone();
        public byte Active { get; set; }
        public int Transition { get; set; }
        public byte[] Read(uint address, int length) => address switch
        {
            0x004AB020 when length == 1 => [Active],
            0x004ABF9C when length == 4 => BitConverter.GetBytes(Transition),
            _ when address >= GameSaveState.MemoryAddress => State.AsSpan(checked((int)(address - GameSaveState.MemoryAddress)), length).ToArray(),
            _ => throw new InvalidOperationException("未记录的内存地址")
        };
    }
}
