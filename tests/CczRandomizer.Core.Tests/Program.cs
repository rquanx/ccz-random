using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

static void Assert(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

var document = new JsonObject
{
    ["activeProfile"] = "test",
    ["profiles"] = new JsonObject
    {
        ["test"] = new JsonObject
        {
            ["threePerson"] = new JsonObject { ["minJobAverage"] = 8, ["jobQualificationMode"] = "count", ["minQualifiedCount"] = 1, ["qualifiedMembers"] = new JsonArray("张宝") },
            ["jobScoring"] = new JsonObject { ["baseScoreWeight"] = 1, ["affinityEnabled"] = false }
        }
    }
};
var score = RuleEvaluator.EvaluateJobs(document, [new JobScore("张宝", "道士", "MASTER", 9)]);
Assert(score.Qualified && score.QualifiedMemberNames.SequenceEqual(["张宝"]), "规则评分未通过");
var attempts = 0;
var workflow = RandomWorkflow.Run(2, 3, (_, _, _) => new AttemptResult<string>(++attempts % 2 == 0, true, "ok"));
Assert(workflow.Count == 2 && attempts == 4, "随机流程状态机未通过");
Assert(SkillMemoryReader.Normalize("能力替换-攻→士") == SkillMemoryReader.Normalize("能力替换攻替士"), "天赋名称规范化未通过");
Console.WriteLine("C# core smoke tests passed.");
