using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

static class SettingsDraftTests
{
    public static void Run()
    {
        var cases = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "scoring/skill-parity.json")))!.AsArray();
        var config = (JsonObject)cases[0]!["config"]!.DeepClone();
        var profile = (JsonObject)config["profiles"]![config["activeProfile"]!.GetValue<string>()]!;
        var original = profile.ToJsonString();
        var draft = new RuleSettingsDraft(profile, ["张宝", "曹操"]);
        var sampledJob = cases[0]!["members"]![0]!["jobName"]!.GetValue<string>();
        draft.Jobs.Single(x => x.Name == sampledJob).Score = 9;
        draft.Jobs.Single(x => x.Name == sampledJob).Type = "WARRIOR";
        draft.Skills.Single(x => x.Name == "攻击追加 诱惑").Score = 4;
        draft.Skills.Single(x => x.Name == "攻击追加 诱惑").Type = "NONE";
        draft.Members.Single(x => x.Name == "张宝").PrimaryType = "WARRIOR";
        draft.BaseScoreWeight = 2;
        draft.PrimaryBonus = .1;
        draft.SkillTypeMatching = true;
        var edited = draft.BuildProfile();
        if (original != profile.ToJsonString()) throw new Exception("取消基础设置会修改原规则");
        config["profiles"]![config["activeProfile"]!.GetValue<string>()] = edited;
        var jobs = cases[0]!["members"]!.AsArray().Select(m =>
        {
            var job = RuleDefaults.Jobs.Values.First(x => x.Name == m!["jobName"]!.GetValue<string>());
            return new JobScore(m!["name"]!.GetValue<string>(), job.Name, job.Type, job.Score);
        }).ToArray();
        var score = RuleEvaluator.EvaluateJobs(config, jobs);
        if (Math.Abs(score.MemberScores[0] - 19.8) > 1e-8) throw new Exception("基础分/类型/人物倾向设置未参与评分");
        var inputs = cases[0]!["members"]!.AsArray().Select(m => new MemberSkillInput(m!["name"]!.GetValue<string>(), m["jobName"]!.GetValue<string>(), m["jobType"]!.GetValue<string>(), m["skills"]!.AsArray().Select(s => s!.GetValue<string>()).ToArray())).ToArray();
        var skills = SkillEvaluator.Evaluate(config, inputs);
        if (!skills.Details.Any(x => x.Name == "攻击追加 诱惑" && x.Score == 4 && x.Counted)) throw new Exception("特技基础设置未参与评分");
        if (edited["threePerson"]!.ToJsonString() != profile["threePerson"]!.ToJsonString()) throw new Exception("基础设置改动了阶段门槛");
        draft.Jobs[0].Score = double.NaN;
        try { draft.BuildProfile(); throw new Exception("无效分数被接受"); } catch (ArgumentException) { }
    }
}
