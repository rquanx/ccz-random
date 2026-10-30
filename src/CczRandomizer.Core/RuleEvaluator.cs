using System.Text.Json;
using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record RuleEvaluationResult(
    bool Qualified,
    IReadOnlyList<string> Reasons,
    double Average,
    double QualificationAverage,
    double QualificationTotal,
    IReadOnlyList<double> MemberScores,
    IReadOnlyList<string> QualifiedMemberNames,
    string Mode,
    double Threshold);

public static class RuleEvaluator
{
    public static RuleEvaluationResult EvaluateJobs(JsonObject document, IReadOnlyList<JobScore> jobs, string mode = "three")
    {
        var profileName = document["activeProfile"]?.GetValue<string>() ?? "默认规则";
        var profile = document["profiles"]?[profileName] as JsonObject ?? new();
        var scoring = profile["jobScoring"] as JsonObject ?? new();
        var settings = profile[mode == "seven" ? "sevenPerson" : "threePerson"] as JsonObject ?? new();
        var affinity = profile["memberAffinity"] as JsonObject ?? new();
        var baseScores = scoring["jobBaseScores"] as JsonObject ?? new();
        var typeOverrides = scoring["jobTypeOverrides"] as JsonObject ?? new();
        var weight = Number(scoring, "baseScoreWeight", 1);
        var affinityEnabled = Bool(scoring, "affinityEnabled", true);
        var affinityMinimum = Number(scoring, "affinityMinBaseScore", 7);
        var primaryBonus = Number(scoring, "primaryBonusRate", .06);
        var secondaryBonus = Number(scoring, "secondaryBonusRate", .03);
        var members = settings["qualifiedMembers"]?.AsArray().Select(x => x?.GetValue<string>() ?? "").Where(x => x.Length > 0).ToArray() ?? [];
        var scores = new List<double>();
        var total = 0d;
        foreach (var job in jobs)
        {
            var baseScore = Number(baseScores, job.JobName, job.BaseScore);
            var jobType = typeOverrides[job.JobName]?.GetValue<string>() ?? job.JobType;
            var weighted = baseScore * weight;
            var memberAffinity = affinity[job.MemberName] as JsonObject;
            var primary = memberAffinity?["primaryType"]?.GetValue<string>();
            var secondary = memberAffinity?["secondaryType"]?.GetValue<string>();
            var bonus = affinityEnabled && baseScore >= affinityMinimum
                ? jobType == primary ? weighted * primaryBonus
                : jobType == secondary ? weighted * secondaryBonus : 0 : 0;
            var score = weighted + bonus;
            scores.Add(score); total += score;
        }
        var scoreByMember = jobs.Zip(scores).ToDictionary(x => x.First.MemberName, x => x.Second);
        var threshold = Number(settings, "minJobAverage", 0);
        var qualificationMode = settings["jobQualificationMode"]?.GetValue<string>() ?? "average";
        if (qualificationMode == "all") members = jobs.Select(x => x.MemberName).ToArray();
        if (members.Distinct().Count() != members.Length || members.Any(name => !scoreByMember.ContainsKey(name)))
            throw new InvalidDataException("参与评分的人物数据缺失或重复");
        var eligibleScores = members.Select(name => scoreByMember[name]).ToArray();
        var qualified = members.Where(scoreByMember.ContainsKey).Where(name => scoreByMember[name] >= threshold).ToArray();
        var average = total / Math.Max(1, scores.Count);
        var qualificationAverage = eligibleScores.Length == 0 ? 0 : eligibleScores.Average();
        var qualificationTotal = eligibleScores.Sum();
        var required = (int)Number(settings, "minQualifiedCount", 1);
        if (qualificationMode == "all") required = jobs.Count;
        var passed = qualificationMode switch
        {
            "count" or "all" => required > 0 && qualified.Length >= required,
            "total" => eligibleScores.Length > 0 && qualificationTotal >= threshold,
            "average" => eligibleScores.Length > 0 && qualificationAverage >= threshold,
            _ => throw new InvalidDataException("未知兵种算分模式"),
        };
        return new RuleEvaluationResult(passed, passed ? [] : ["兵种综合评价未达到当前规则要求"], average, qualificationAverage, qualificationTotal, scores, qualified, qualificationMode, threshold);
    }

    private static double Number(JsonObject obj, string key, double fallback) => JsonNumbers.Read(obj[key], fallback);
    private static bool Bool(JsonObject obj, string key, bool fallback) => obj[key] is JsonValue value && value.TryGetValue<bool>(out var result) ? result : fallback;
}

public sealed record JobScore(string MemberName, string JobName, string JobType, double BaseScore);
