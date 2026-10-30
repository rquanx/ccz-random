using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record ScoredSnapshot(bool Qualified, JsonObject Document);
public static class ResultSnapshot
{
    public static ScoredSnapshot Score(JsonObject rules, GameSnapshot game, int slot, int attempt)
    {
        var profile = rules["profiles"]![rules["activeProfile"]!.GetValue<string>()]!;
        var selected = profile["threePerson"]!["qualifiedMembers"]!.AsArray().Select(x => x!.GetValue<string>()).ToArray();
        if (selected.Length == 0 || selected.Distinct().Count() != selected.Length) throw new InvalidDataException("请选择不重复的参与人物。");
        var byName = game.People.ToDictionary(x => x.Name);
        if (selected.Any(x => !byName.ContainsKey(x))) throw new InvalidDataException("所选人物的随机数据未采集完整。");
        var members = selected.Select(x => byName[x]).ToArray();
        var jobs = members.Select(x =>
        {
            if (!RuleDefaults.Jobs.TryGetValue(x.JobId, out var job)) throw new InvalidDataException($"{x.Name} 的兵种编号未知：{x.JobId}");
            return new JobScore(x.Name, job.Name, job.Type, job.Score);
        }).ToArray();
        var jobScore = RuleEvaluator.EvaluateJobs(rules, jobs);
        SkillEvaluationResult? skillScore = jobScore.Qualified ? SkillEvaluator.Evaluate(rules, members.Select((x, i) =>
            new MemberSkillInput(x.Name, jobs[i].JobName, jobs[i].JobType, x.PersonalTalents.Concat(x.JobTalents).ToArray())).ToArray()) : null;
        var fixedIds = FixedEntryCatalog.CreateRows().Select(x => x.RecordIndex).ToHashSet();
        JsonArray Strings(IEnumerable<string> values) => new(values.Select(x => (JsonNode)JsonValue.Create(x)!).ToArray());
        JsonArray People(bool fixedEntry) => new(game.People.Where(x => fixedIds.Contains(x.RecordIndex) == fixedEntry).Select(x => (JsonNode)new JsonObject
        {
            ["recordIndex"] = x.RecordIndex, ["memberId"] = x.MemberId, ["name"] = x.Name, ["jobId"] = (int)x.JobId,
            ["currentJobId"] = (int)x.CurrentJobId, ["job"] = RuleDefaults.Jobs.GetValueOrDefault(x.JobId)?.Name ?? "未知兵种",
            ["jobTalents"] = Strings(x.JobTalents), ["personalTalents"] = Strings(x.PersonalTalents), ["availabilityVerified"] = true
        }).ToArray());
        JsonArray Skills(IEnumerable<string> names) => new(names.Select(name => (JsonNode)new JsonObject { ["name"] = name }).ToArray());
        var memberRows = new JsonArray(members.Select((x, i) => (JsonNode)new JsonObject
        {
            ["name"] = x.Name, ["job"] = jobs[i].JobName, ["jobScore"] = jobScore.MemberScores[i],
            ["personalSkills"] = Skills(x.PersonalTalents), ["jobSkills"] = Skills(x.JobTalents)
        }).ToArray());
        var jobDetail = new JsonObject
        {
            ["qualified"] = jobScore.Qualified, ["reasons"] = Strings(jobScore.Reasons),
            ["members"] = new JsonArray(jobs.Select((x, i) => (JsonNode)new JsonObject { ["name"] = x.MemberName, ["job"] = x.JobName, ["score"] = jobScore.MemberScores[i] }).ToArray()),
            ["metrics"] = new JsonObject
            {
                ["average"] = jobScore.Average, ["qualificationAverage"] = jobScore.QualificationAverage, ["qualificationTotal"] = jobScore.QualificationTotal,
                ["eligibleMembers"] = Strings(selected), ["qualifiedMemberNames"] = Strings(jobScore.QualifiedMemberNames),
                ["qualificationMode"] = jobScore.Mode, ["threshold"] = jobScore.Threshold,
                ["requiredCount"] = jobScore.Mode == "all" ? selected.Length : profile["threePerson"]!["minQualifiedCount"]!.DeepClone()
            }
        };
        var skillDetail = skillScore is null ? new JsonObject { ["skipped"] = true, ["reason"] = "兵种未达标，本次未检查特技。" } : new JsonObject
        {
            ["qualified"] = skillScore.Qualified,
            ["metrics"] = new JsonObject { ["skillScore"] = skillScore.Total, ["qualificationAverage"] = skillScore.Average,
                ["qualificationMode"] = skillScore.Mode, ["threshold"] = skillScore.Threshold, ["requiredCount"] = skillScore.RequiredCount,
                ["memberSkillScores"] = new JsonObject(skillScore.MemberScores.Select(x => KeyValuePair.Create<string, JsonNode?>(x.Key, JsonValue.Create(x.Value)))),
                ["qualifiedMemberNames"] = Strings(skillScore.QualifiedMembers) },
            ["details"] = new JsonArray(skillScore.Details.Select(x => (JsonNode)new JsonObject { ["member"] = x.Member, ["name"] = x.Name, ["score"] = x.Score, ["counted"] = x.Counted }).ToArray())
        };
        var qualified = jobScore.Qualified && skillScore?.Qualified == true;
        return new(qualified, new JsonObject
        {
            ["schemaVersion"] = 1, ["gameVersion"] = "2.2", ["mode"] = "three", ["slot"] = slot, ["acceptedAttempt"] = attempt,
            ["createdAt"] = DateTimeOffset.Now.ToString("O"), ["qualified"] = qualified, ["members"] = memberRows,
            ["personnel"] = People(false), ["fixedPersonnel"] = People(true), ["equipment"] = game.Equipment.DeepClone(),
            ["jobTalents"] = new JsonArray(game.Jobs.Select(x => (JsonNode)new JsonObject { ["jobId"] = x.JobId, ["name"] = x.Name, ["talents"] = x.Talents is null ? null : Strings(x.Talents) }).ToArray()),
            ["detail"] = new JsonObject { ["job"] = jobDetail, ["skill"] = skillDetail }
        });
    }
}
