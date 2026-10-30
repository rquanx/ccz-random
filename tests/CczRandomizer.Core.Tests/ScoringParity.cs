using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

static class ScoringParity
{
    public static int Run()
    {
        var cases = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "scoring", "skill-parity.json")))!.AsArray();
        foreach (var test in cases)
        {
            var config = (JsonObject)test!["config"]!;
            var before = config.ToJsonString();
            var members = test["members"]!.AsArray().Select(m => new MemberSkillInput(m!["name"]!.GetValue<string>(),
                m["jobName"]!.GetValue<string>(), m["jobType"]!.GetValue<string>(), m["skills"]!.AsArray().Select(s => s!.GetValue<string>()).ToArray())).ToArray();
            var actual = SkillEvaluator.Evaluate(config, members);
            var expected = test["expected"]!;
            if (actual.Qualified != expected["qualified"]!.GetValue<bool>() || actual.Total != expected["total"]!.GetValue<double>() ||
                actual.Average != expected["average"]!.GetValue<double>()) throw new Exception("特技门槛与 Python 不一致");
            foreach (var score in actual.MemberScores)
                if (expected["memberScores"]![score.Key]!.GetValue<double>() != score.Value) throw new Exception("人物特技分数不一致");
            var details = expected["details"]!.AsArray();
            if (details.Count != actual.Details.Count) throw new Exception("特技明细数目不一致");
            for (var i = 0; i < details.Count; i++)
                if (actual.Details[i].Name != details[i]!["name"]!.GetValue<string>() ||
                    actual.Details[i].Score != details[i]!["score"]!.GetValue<double>() ||
                    actual.Details[i].Counted != details[i]!["counted"]!.GetValue<bool>()) throw new Exception("特技明细不一致");
            if (before != config.ToJsonString()) throw new Exception("评分修改了规则");
        }
        return cases.Count + Jobs();
    }
    private static int Jobs()
    {
        var cases = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "scoring/job-parity.json")))!.AsArray();
        foreach (var test in cases)
        {
            var config = test!["config"]!.AsObject();
            var before = config.ToJsonString();
            var members = test["members"]!.AsArray();
            var jobs = test["jobs"]!.AsArray().Select((job, i) => new JobScore(members[i]!["name"]!.GetValue<string>(), job!["name"]!.GetValue<string>(), job["type"]!.GetValue<string>(), job["score"]!.GetValue<double>())).ToArray();
            var actual = RuleEvaluator.EvaluateJobs(config, jobs);
            var expected = test["expected"]!;
            static bool Close(double x, double y) => Math.Abs(x - y) < 1e-9;
            if (actual.Qualified != expected["qualified"]!.GetValue<bool>() ||
                !Close(actual.Average, expected["average"]!.GetValue<double>()) ||
                !Close(actual.QualificationAverage, expected["qualificationAverage"]!.GetValue<double>()) ||
                !Close(actual.QualificationTotal, expected["qualificationTotal"]!.GetValue<double>()) ||
                !actual.QualifiedMemberNames.SequenceEqual(expected["qualifiedMemberNames"]!.AsArray().Select(x => x!.GetValue<string>()))) throw new Exception("兵种门槛与 Python 不一致");
            for (var i = 0; i < jobs.Length; i++)
                if (!Close(actual.MemberScores[i], expected["memberScores"]![i]!.GetValue<double>())) throw new Exception("人物兵种分数不一致");
            if (config.ToJsonString() != before) throw new Exception("兵种评分修改了规则");
            config["profiles"]!["test"]!["threePerson"]!["jobQualificationMode"] = "average";
            config["profiles"]!["test"]!["threePerson"]!["qualifiedMembers"] = new JsonArray("缺失人物");
            try { RuleEvaluator.EvaluateJobs(config, jobs); throw new Exception("缺失人物被忽略"); } catch (InvalidDataException) { }
        }
        return cases.Count;
    }
}
