using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record MemberSkillInput(string Name, string JobName, string JobType, IReadOnlyList<string> Skills);
public sealed record SkillScoreDetail(string Member, string Name, double Score, bool Counted);
public sealed record SkillEvaluationResult(bool Qualified, double Total, double Average, string Mode, double Threshold,
    int RequiredCount, IReadOnlyList<string> QualifiedMembers, IReadOnlyDictionary<string, double> MemberScores,
    IReadOnlyList<SkillScoreDetail> Details);

public static class SkillEvaluator
{
    public static bool TypesMatch(string job, string skill) => !((job == "WARRIOR" && skill == "MASTER") || (job == "MASTER" && skill == "WARRIOR"));

    public static SkillEvaluationResult Evaluate(JsonObject document, IReadOnlyList<MemberSkillInput> members)
    {
        // Migration is local: evaluating must never edit the user's rules.
        var profile = (JsonObject)document["profiles"]![document["activeProfile"]!.GetValue<string>()]!.DeepClone();
        RuleDefaults.MigrateSkillScores(profile);
        var settings = (JsonObject)profile["sevenPerson"]!;
        var scores = (JsonObject)settings["skillBaseScores"]!;
        var types = (JsonObject)settings["skillTypeOverrides"]!;
        var jobTypes = profile["jobScoring"]?["jobTypeOverrides"] as JsonObject ?? new();
        var selected = profile["threePerson"]!["qualifiedMembers"]!.AsArray().Select(x => x!.GetValue<string>()).ToHashSet();
        var byName = members.ToDictionary(x => x.Name);
        if (selected.Any(name => !byName.ContainsKey(name))) throw new InvalidDataException("参与评分的人物数据不完整");
        var defaultScores = RuleDefaults.Skills.GroupBy(x => x.Name).ToDictionary(x => x.Key, x => x.Last());
        var totals = new Dictionary<string, double>();
        var details = new List<SkillScoreDetail>();
        var matching = settings["skillTypeMatchingEnabled"]?.GetValue<bool>() ?? true;
        foreach (var member in members.Where(m => selected.Contains(m.Name)))
        {
            var jobType = jobTypes[member.JobName]?.GetValue<string>() ?? member.JobType;
            totals[member.Name] = 0;
            foreach (var name in member.Skills)
            {
                var defaults = defaultScores.GetValueOrDefault(name);
                var score = RuleDefaults.Resolve(scores, name, defaults?.Score ?? 0);
                var type = RuleDefaults.Resolve(types, name, defaults?.LegacyCategory == "特殊" ? "NONE" : defaults?.Type ?? "ALL_ROUNDER");
                var counted = score > 0 && (!matching || TypesMatch(jobType, type));
                if (counted) totals[member.Name] += score;
                details.Add(new(member.Name, name, counted ? score : 0, counted));
            }
        }
        var gate = profile["skillQualification"]!;
        var threshold = JsonNumbers.Read(gate["threshold"]!);
        var mode = gate["mode"]!.GetValue<string>();
        var required = gate["requiredCount"]!.GetValue<int>();
        var total = totals.Values.Sum();
        var average = total / Math.Max(1, totals.Count);
        var qualified = totals.Where(x => x.Value >= threshold).Select(x => x.Key).ToArray();
        var passed = totals.Count > 0 && (mode switch
        {
            "count" => required > 0 && qualified.Length >= required,
            "average" => average >= threshold,
            "total" => total >= threshold,
            _ => throw new InvalidDataException("未知特技算分模式")
        });
        return new(passed, total, average, mode, threshold, required, qualified, totals, details);
    }
}
