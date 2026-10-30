using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed class LegacyModeRequiredException : Exception
{
    public LegacyModeRequiredException() : base("旧版规则未记录运行模式，请选择旧版实际使用的三人或七人模式。") { }
}
public sealed record RuleImportResult(JsonObject Config, IReadOnlyList<string> Names);

public static class RuleImporter
{
    public static string? ReadLegacyMode(string rulePath)
    {
        try
        {
            var file = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(rulePath))!, "randomizer_settings.json");
            var mode = JsonNode.Parse(File.ReadAllText(file))?["randomMode"]?.GetValue<string>();
            return mode is "three" or "seven" ? mode : null;
        }
        catch (Exception error) when (error is IOException or System.Text.Json.JsonException or InvalidOperationException or UnauthorizedAccessException) { return null; }
    }

    public static JsonObject MergeDefaults(JsonObject defaults, JsonObject source)
    {
        var result = (JsonObject)source.DeepClone();
        foreach (var entry in defaults)
        {
            if (entry.Value is JsonObject map)
                result[entry.Key] = MergeDefaults(map, source[entry.Key] as JsonObject ?? new());
            else if (!source.ContainsKey(entry.Key) || source[entry.Key] is null)
                result[entry.Key] = entry.Value?.DeepClone();
        }
        return result;
    }

    public static RuleImportResult Import(JsonObject existing, JsonObject payload, string? legacyMode = null)
    {
        var version = 2;
        if (payload["format"]?.GetValue<string>() == "ccz-random-rules")
        {
            if (payload["version"]?.GetValue<int>() != 1) throw new InvalidDataException("导入文件版本不受支持");
            version = payload["ruleVersion"]?.GetValue<int>() ?? 2;
        }
        else if (payload.ContainsKey("activeProfile") && payload.ContainsKey("profiles")) version = payload["version"]?.GetValue<int>() ?? 2;
        else throw new InvalidDataException("这不是随机工具的规则文件");
        if (version is not (1 or 2)) throw new InvalidDataException("规则版本不受支持");
        if (payload["profiles"] is not JsonObject profiles || profiles.Count == 0) throw new InvalidDataException("导入文件中没有可用规则");
        var merged = (JsonObject)existing.DeepClone();
        var destination = merged["profiles"] as JsonObject ?? throw new InvalidDataException("当前规则无效");
        var names = new List<string>();
        foreach (var entry in profiles)
        {
            if (string.IsNullOrWhiteSpace(entry.Key) || entry.Value is not JsonObject raw) throw new InvalidDataException("导入规则名称或内容无效");
            var source = version == 1 ? MigrateV1(raw) : (JsonObject)raw.DeepClone();
            var legacy = !source.ContainsKey("skillQualification");
            if (legacy && legacyMode is not ("three" or "seven")) throw new LegacyModeRequiredException();
            var profile = MergeDefaults(RuleDefaults.NewProfile(), source);
            if (legacy)
            {
                var stage = profile[legacyMode == "three" ? "threePerson" : "sevenPerson"]!;
                var target = new JsonObject();
                foreach (var key in new[] { "minJobAverage", "jobQualificationMode", "minQualifiedCount", "qualifiedMembers" }) target[key] = stage[key]!.DeepClone();
                if (target["jobQualificationMode"]?.GetValue<string>() == "all")
                    target["qualifiedMembers"] = RuleDefaults.NewProfile()[legacyMode == "three" ? "threePerson" : "sevenPerson"]!["qualifiedMembers"]!.DeepClone();
                profile["threePerson"] = target;
                profile["skillQualification"] = new JsonObject { ["mode"] = "total", ["threshold"] = profile["sevenPerson"]!["lowMinSkillScore"]!.DeepClone(), ["requiredCount"] = 1 };
                profile["editorMode"] = "advanced";
                profile["sevenPerson"]!["specialSkillAutoPass"] = false;
                profile["sevenPerson"]!["highJobAutoPass"] = false;
                profile["jobScoring"]!["xiahouDunMasterPenalty"] = 0;
                profile["jobScoring"]!["extraMasterPenaltyEnabled"] = false;
                profile["jobScoring"]!["extraMasterPenaltyWeight"] = 0;
                profile["legacyImport"] = new JsonObject { ["source"] = "2.10", ["mode"] = legacyMode };
            }
            profile["builtin"] = false;
            if (profile["threePerson"]!["jobQualificationMode"]?.GetValue<string>() == "all")
            {
                profile["threePerson"]!["jobQualificationMode"] = "count";
                profile["threePerson"]!["minQualifiedCount"] = profile["threePerson"]!["qualifiedMembers"]!.AsArray().Count;
            }
            RuleDefaults.MigrateSkillScores(profile);
            ValidateProfile(profile);
            var name = entry.Key.Trim();
            for (var suffix = 1; destination.ContainsKey(name); suffix++) name = $"{entry.Key.Trim()}({suffix})";
            destination[name] = profile;
            names.Add(name);
        }
        return new(merged, names);
    }

    private static JsonObject MigrateV1(JsonObject old)
    {
        var profile = RuleDefaults.NewProfile();
        profile.Remove("skillQualification");
        profile["editorMode"] = "advanced";
        profile["threePerson"]!["minJobAverage"] = old["threePerson"]?["minJobAverage"]?.DeepClone() ?? JsonValue.Create(7.4);
        var mappings = new Dictionary<string, string> { ["minJobAverage"] = "minJobAverage", ["normalJobAverage"] = "normalJobAverage", ["highJobAverage"] = "highJobAverage",
            ["mediumMinEffectiveSkills"] = "mediumMinSkillScore", ["lowMinEffectiveSkills"] = "lowMinSkillScore", ["strongSkillWeight"] = "strongSkillWeight",
            ["specialSkillAutoPass"] = "specialSkillAutoPass", ["highJobAutoPass"] = "highJobAutoPass" };
        foreach (var map in mappings)
            if (old["sevenPerson"]?[map.Key] is JsonNode value) profile["sevenPerson"]![map.Value] = value.DeepClone();
        foreach (var key in new[] { "affinityEnabled", "affinityMinBaseScore", "primaryBonusRate", "secondaryBonusRate", "xiahouDunMasterPenalty", "extraMasterPenaltyEnabled" })
            if (old["jobScoring"]?[key] is JsonNode value) profile["jobScoring"]![key] = value.DeepClone();
        return profile;
    }

    public static JsonObject Export(JsonObject config, IEnumerable<string> names)
    {
        var profiles = new JsonObject();
        foreach (var name in names.Distinct()) profiles[name] = config["profiles"]?[name]?.DeepClone() ?? throw new ArgumentException("导出规则不存在");
        if (profiles.Count == 0) throw new ArgumentException("至少选择一套规则");
        return new JsonObject { ["format"] = "ccz-random-rules", ["version"] = 1, ["ruleVersion"] = 2, ["profiles"] = profiles };
    }

    public static void ValidateProfile(JsonObject profile)
    {
        var names = RuleDefaults.NewProfile()["memberAffinity"]!.AsObject().Select(x => x.Key).ToHashSet();
        var selected = profile["threePerson"]!["qualifiedMembers"]!.AsArray().Select(x => x!.GetValue<string>()).ToArray();
        if (selected.Length == 0 || selected.Distinct().Count() != selected.Length || selected.Any(x => !names.Contains(x))) throw new InvalidDataException("导入规则的参与人物无效");
        var job = profile["threePerson"]!;
        var skill = profile["skillQualification"]!;
        foreach (var gate in new[] { (Mode: job["jobQualificationMode"]!.GetValue<string>(), Threshold: JsonNumbers.Read(job["minJobAverage"]!), Count: job["minQualifiedCount"]!.GetValue<int>(), Skill: false),
            (Mode: skill["mode"]!.GetValue<string>(), Threshold: JsonNumbers.Read(skill["threshold"]!), Count: skill["requiredCount"]!.GetValue<int>(), Skill: true) })
        {
            if (gate.Mode is not ("count" or "average" or "total" or "all") || (gate.Skill && gate.Mode == "all")) throw new InvalidDataException("无效算分模式");
            if (!double.IsFinite(gate.Threshold) || gate.Threshold < 0 || gate.Threshold > (gate.Skill ? 100000 : gate.Mode == "total" ? 2600 : 20)) throw new InvalidDataException("合格分超出范围");
            if (gate.Mode == "count" && (gate.Count < 1 || gate.Count > selected.Length)) throw new InvalidDataException("达标人数超出参与人数");
        }
        // Reuse editor validation for scores, affinity and supported types.
        _ = new RuleSettingsDraft(profile, names).BuildProfile();
    }
}
