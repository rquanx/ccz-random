using System.Text.Json;
using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record RuntimePreferences(int ResultCount = 1, int Workers = 1, bool Loop = false, bool CompatibilityMode = false)
{
    public static RuntimePreferences Load(string gameDirectory)
    {
        var path = Path.Combine(gameDirectory, "randomizer_settings.json");
        if (!File.Exists(path)) return new();
        var json = JsonNode.Parse(File.ReadAllText(path)) as JsonObject ?? throw new InvalidDataException("运行参数文件格式无效。");
        int Count(string key) => json[key] is JsonValue value && value.TryGetValue<int>(out var number) && number is >= 1 and <= 15 ? number : 1;
        bool Flag(string key) => json[key] is JsonValue value && value.TryGetValue<bool>(out var flag) && flag;
        return new(Count("resultCount"), Count("concurrency"), Flag("loopRandom"), Flag("compatibilityMode"));
    }
    public void Save(string gameDirectory)
    {
        if (ResultCount is < 1 or > 15 || Workers is < 1 or > 15) throw new ArgumentOutOfRangeException(nameof(ResultCount));
        var path = Path.Combine(gameDirectory, "randomizer_settings.json");
        var before = File.Exists(path) ? File.ReadAllBytes(path) : null;
        var json = before is null ? new JsonObject() : JsonNode.Parse(before) as JsonObject ?? throw new InvalidDataException("运行参数文件格式无效，未覆盖。");
        json["version"] = 1; json["gameVersion"] = "2.2"; json["resultCount"] = ResultCount;
        json["concurrency"] = Workers; json["loopRandom"] = Loop; json["compatibilityMode"] = CompatibilityMode;
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                var bytes = System.Text.Encoding.UTF8.GetBytes(json.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
                file.Write(bytes); file.Flush(true);
            }
            if (before is null ? File.Exists(path) : !File.Exists(path) || !File.ReadAllBytes(path).SequenceEqual(before))
                throw new IOException("运行参数已被其他程序修改，未覆盖。");
            if (before is null) File.Move(temporary, path); else File.Replace(temporary, path, path + ".bak");
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
