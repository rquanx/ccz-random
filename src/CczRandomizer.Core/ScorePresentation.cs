using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public static class ScorePresentation
{
    public static string Summary(JsonObject snapshot, bool includeMembers = true) => string.Join("\n\n", new[] { Stage(snapshot, "job", "兵种评分", includeMembers), Stage(snapshot, "skill", "特技评分", includeMembers) }.Where(x => x.Length > 0));
    private static string Stage(JsonObject snapshot, string key, string title, bool includeMembers)
    {
        var stage = snapshot["detail"]?[key];
        if (stage is null) return "";
        if (stage["skipped"]?.GetValue<bool>() == true) return $"{title} · 未检查\n{stage["reason"]}";
        var metrics = stage["metrics"];
        if (metrics is null) return $"{title} · 历史记录未保存门槛明细";
        var threshold = JsonNumbers.Read(metrics["threshold"], 0);
        var names = metrics["qualifiedMemberNames"]?.AsArray().Select(x => x!.GetValue<string>()).ToArray() ?? [];
        var mode = metrics["qualificationMode"]?.GetValue<string>();
        var requirement = mode switch
        {
            "count" or "all" => $"每人 ≥ {threshold:0.##} 分，需 {metrics["requiredCount"]} 人达标；本次 {names.Length} 人",
            "average" => $"平均分 {JsonNumbers.Read(metrics["qualificationAverage"], 0):0.##} / 要求 ≥ {threshold:0.##}",
            "total" => $"总分 {JsonNumbers.Read(metrics[key == "job" ? "qualificationTotal" : "skillScore"], 0):0.##} / 要求 ≥ {threshold:0.##}",
            _ => "历史记录未保存算分模式"
        };
        var scores = key == "job" ? stage["members"]?.AsArray().Select(x => $"{x!["name"]}：{JsonNumbers.Read(x["score"]!, 0):0.##} 分")
            : metrics["memberSkillScores"]?.AsObject().Select(x => $"{x.Key}：{JsonNumbers.Read(x.Value, 0):0.##} 分");
        var members = includeMembers ? "\n" + string.Join("　", scores ?? []) : "";
        return $"{title} · {(stage["qualified"]?.GetValue<bool>() == true ? "通过" : "未通过")}\n{requirement}{members}";
    }
}
