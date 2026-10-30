using System.Text.Json;
using CczRandomizer.Wpf.Core;

sealed class RecordedMemory : IMemoryReader
{
    private readonly (uint Address, byte[] Bytes)[] _spans;
    public RecordedMemory(string path)
    {
        using var json = JsonDocument.Parse(File.ReadAllText(path));
        _spans = json.RootElement.EnumerateObject().Select(p => (uint.Parse(p.Name.Split(':')[0]), Convert.FromHexString(p.Value.GetString()!))).ToArray();
    }
    public byte[] Read(uint address, int length)
    {
        foreach (var span in _spans)
            if (address >= span.Address && (ulong)address + (uint)length <= (ulong)span.Address + (uint)span.Bytes.Length)
                return span.Bytes.AsSpan((int)(address - span.Address), length).ToArray();
        throw new InvalidOperationException($"未采集范围 {address:X}:{length}");
    }
}
