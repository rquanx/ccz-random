using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record SkillDefault(string Name, double Score, string LegacyCategory, string Type);
public sealed record JobDefault(int Id, string Name, double Score, string Type);

public static class RuleDefaults
{
    public static JsonObject NewConfig()
    {
        using var stream = typeof(RuleDefaults).Assembly.GetManifestResourceStream("Rules.Config")!;
        return (JsonObject)JsonNode.Parse(stream)!;
    }
    public static JsonObject NewProfile() => (JsonObject)NewConfig()["profiles"]!["默认规则"]!.DeepClone();
    public static IReadOnlyList<SkillDefault> Skills { get; }
    public static IReadOnlyDictionary<int, JobDefault> Jobs { get; }
    static RuleDefaults()
    {
        using var stream = typeof(RuleDefaults).Assembly.GetManifestResourceStream("Rules.Defaults")!;
        var data = JsonNode.Parse(stream)!;
        Skills = data["skills"]!.AsArray().Select(x => new SkillDefault(x!["name"]!.GetValue<string>(),
            x["score"]!.GetValue<double>(), x["legacyCategory"]!.GetValue<string>(), x["type"]!.GetValue<string>())).ToArray();
        Jobs = data["jobs"]!.AsArray().Select(x => new JobDefault(x!["id"]!.GetValue<int>(), x["name"]!.GetValue<string>(),
            x["score"]!.GetValue<double>(), x["type"]!.GetValue<string>())).ToDictionary(x => x.Id);
    }
    public static T Resolve<T>(JsonObject settings, string name, T fallback)
    {
        if (settings[name] is JsonValue exact) return Read<T>(exact);
        var normalized = SkillMemoryReader.Normalize(name);
        foreach (var entry in settings.Reverse())
            if (SkillMemoryReader.Normalize(entry.Key) == normalized && entry.Value is JsonValue value) return Read<T>(value);
        return fallback;
    }
    private static T Read<T>(JsonValue value) => typeof(T) == typeof(double) ? (T)(object)JsonNumbers.Read(value) : value.GetValue<T>();
    public static void MigrateSkillScores(JsonObject profile)
    {
        var settings = (JsonObject)profile["sevenPerson"]!;
        if (settings["individualSkillScores"]?.GetValue<bool>() == true) return;
        var scores = settings["skillBaseScores"] as JsonObject ?? new();
        var types = settings["skillTypeOverrides"] as JsonObject ?? new();
        if (scores.Parent is null) settings["skillBaseScores"] = scores;
        if (types.Parent is null) settings["skillTypeOverrides"] = types;
        var oldScores = (JsonObject)scores.DeepClone();
        var oldTypes = (JsonObject)types.DeepClone();
        var weights = new Dictionary<string, double>
        {
            ["优质"] = JsonNumbers.Read(settings["ordinarySkillWeight"], 1),
            ["强力"] = JsonNumbers.Read(settings["strongSkillWeight"], 2),
            ["特殊"] = JsonNumbers.Read(settings["specialSkillWeight"], 5), ["其他"] = 0
        };
        foreach (var skill in Skills)
        {
            var score = Resolve(oldScores, skill.Name, weights.GetValueOrDefault(skill.LegacyCategory, skill.Score));
            if (score != skill.Score || oldScores.ContainsKey(skill.Name)) scores[skill.Name] = score;
            types[skill.Name] = score >= weights["特殊"] ? "NONE" : Resolve(oldTypes, skill.Name, skill.Type);
        }
        foreach (var score in oldScores)
            if (JsonNumbers.Read(score.Value!) >= weights["特殊"]) types[score.Key] = "NONE";
        settings["individualSkillScores"] = true;
    }
}
