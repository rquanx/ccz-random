using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

internal static class EquipmentTests
{
    public static void Run()
    {
        var reference = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "runtime_22/equipment-reference.json")))!;
        var decoder = new StringBuilder();
        for (var code = 0; code < 256; code++)
            for (var parameter = 0; parameter < 256; parameter++) decoder.Append($"{code}/{parameter}:{EquipmentMemoryReader.Effect((byte)code, (byte)parameter)}\n");
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(decoder.ToString()))).ToLowerInvariant();
        if (hash != reference["decoderSha256"]!.GetValue<string>()) throw new Exception("宝物特效解码与 Python 参考不一致");
        using var file = File.OpenRead(Path.Combine(AppContext.BaseDirectory, "runtime_22/source-state.bin.gz"));
        using var gzip = new GZipStream(file, CompressionMode.Decompress);
        using var stream = new MemoryStream(); gzip.CopyTo(stream);
        var actual = EquipmentMemoryReader.Decode(stream.ToArray().AsSpan(0x54D8, EquipmentMemoryReader.Size));
        if (!JsonNode.DeepEquals(actual, reference["source"])) throw new Exception("真实宝物记录的分类/组合解码不一致");
        try { EquipmentMemoryReader.Decode(new byte[375]); throw new Exception("截断宝物记录被接受"); }
        catch (InvalidDataException) { }
    }
}
