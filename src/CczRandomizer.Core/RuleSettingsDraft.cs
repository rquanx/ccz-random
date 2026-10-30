using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed class ScoreSetting
{
    public string Name { get; init; } = "";
    public double Score { get; set; }
    public string Type { get; set; } = "ALL_ROUNDER";
}
public sealed class AffinitySetting
{
    public string Name { get; init; } = "";
    public string PrimaryType { get; set; } = "NONE";
    public string SecondaryType { get; set; } = "NONE";
}

/// <summary>Detached editing state. Cancel never mutates a rule profile.</summary>
public sealed class RuleSettingsDraft
{
    private readonly JsonObject _profile;
    public IReadOnlyList<ScoreSetting> Jobs { get; }
    public IReadOnlyList<ScoreSetting> Skills { get; }
    public IReadOnlyList<AffinitySetting> Members { get; }
    public bool SkillTypeMatching { get; set; }
    public bool AffinityEnabled { get; set; }
    public double BaseScoreWeight { get; set; }
    public double AffinityMinimum { get; set; }
    public double PrimaryBonus { get; set; }
    public double SecondaryBonus { get; set; }

    public RuleSettingsDraft(JsonObject profile, IEnumerable<string> memberNames)
    {
        _profile = (JsonObject)profile.DeepClone();
        RuleDefaults.MigrateSkillScores(_profile);
        var job = (JsonObject)_profile["jobScoring"]!;
        var seven = (JsonObject)_profile["sevenPerson"]!;
        var jobScores = job["jobBaseScores"] as JsonObject ?? new();
        var jobTypes = job["jobTypeOverrides"] as JsonObject ?? new();
        var skillScores = (JsonObject)seven["skillBaseScores"]!;
        var skillTypes = (JsonObject)seven["skillTypeOverrides"]!;
        Jobs = RuleDefaults.Jobs.Values.GroupBy(x => x.Name).Select(x => x.First()).Select(x => new ScoreSetting
        { Name = x.Name, Score = JsonNumbers.Read(jobScores[x.Name], x.Score), Type = jobTypes[x.Name]?.GetValue<string>() ?? x.Type }).ToArray();
        Skills = RuleDefaults.Skills.GroupBy(x => x.Name).Select(x => x.Last()).Select(x => new ScoreSetting
        { Name = x.Name, Score = RuleDefaults.Resolve(skillScores, x.Name, x.Score), Type = RuleDefaults.Resolve(skillTypes, x.Name, x.LegacyCategory == "特殊" ? "NONE" : x.Type) }).ToArray();
        var affinity = _profile["memberAffinity"] as JsonObject ?? new();
        Members = memberNames.Distinct().Select(name => new AffinitySetting { Name = name,
            PrimaryType = affinity[name]?["primaryType"]?.GetValue<string>() ?? "NONE",
            SecondaryType = affinity[name]?["secondaryType"]?.GetValue<string>() ?? "NONE" }).ToArray();
        SkillTypeMatching = seven["skillTypeMatchingEnabled"]?.GetValue<bool>() ?? true;
        AffinityEnabled = job["affinityEnabled"]?.GetValue<bool>() ?? true;
        BaseScoreWeight = JsonNumbers.Read(job["baseScoreWeight"], 1);
        AffinityMinimum = JsonNumbers.Read(job["affinityMinBaseScore"], 7);
        PrimaryBonus = JsonNumbers.Read(job["primaryBonusRate"], .06);
        SecondaryBonus = JsonNumbers.Read(job["secondaryBonusRate"], .03);
    }

    public JsonObject BuildProfile()
    {
        static void Number(double value, double max, string name)
        { if (!double.IsFinite(value) || value < 0 || value > max) throw new ArgumentException($"{name}须在 0–{max} 之间"); }
        static void Type(string value, bool none)
        { if (value is not ("WARRIOR" or "MASTER" or "ALL_ROUNDER") && !(none && value == "NONE")) throw new ArgumentException("无效的匹配类型"); }
        foreach (var row in Jobs) { Number(row.Score, 20, row.Name); Type(row.Type, false); }
        foreach (var row in Skills) { Number(row.Score, 20, row.Name); Type(row.Type, true); }
        foreach (var row in Members) { Type(row.PrimaryType, true); Type(row.SecondaryType, true); }
        Number(BaseScoreWeight, 5, "基础分权重"); Number(AffinityMinimum, 20, "适配最低分");
        Number(PrimaryBonus, 1, "主要倾向加成"); Number(SecondaryBonus, 1, "次要倾向加成");
        var profile = (JsonObject)_profile.DeepClone();
        var job = (JsonObject)profile["jobScoring"]!;
        var seven = (JsonObject)profile["sevenPerson"]!;
        static JsonObject Map(JsonObject parent, string name)
        { if (parent[name] is JsonObject map) return map; var result = new JsonObject(); parent[name] = result; return result; }
        var jobScores = Map(job, "jobBaseScores"); var jobTypes = Map(job, "jobTypeOverrides");
        var skillScores = Map(seven, "skillBaseScores"); var skillTypes = Map(seven, "skillTypeOverrides");
        foreach (var row in Jobs) { jobScores[row.Name] = row.Score; jobTypes[row.Name] = row.Type; }
        foreach (var row in Skills) { skillScores[row.Name] = row.Score; skillTypes[row.Name] = row.Type; }
        var affinity = Map(profile, "memberAffinity");
        foreach (var row in Members) affinity[row.Name] = new JsonObject { ["primaryType"] = row.PrimaryType, ["secondaryType"] = row.SecondaryType };
        seven["skillTypeMatchingEnabled"] = SkillTypeMatching;
        job["affinityEnabled"] = AffinityEnabled; job["baseScoreWeight"] = BaseScoreWeight;
        job["affinityMinBaseScore"] = AffinityMinimum; job["primaryBonusRate"] = PrimaryBonus; job["secondaryBonusRate"] = SecondaryBonus;
        return profile;
    }
}
