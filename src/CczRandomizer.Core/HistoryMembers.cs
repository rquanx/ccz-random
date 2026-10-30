using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public static class HistoryMembers
{
    public static IReadOnlyList<JsonObject> Resolve(JsonObject snapshot)
    {
        var saved = Rows(snapshot["members"]);
        var job = snapshot["detail"]?["job"];
        if (job?["metrics"]?["eligibleMembers"] is not JsonArray selected) return saved.Select(x => (JsonObject)x.DeepClone()).ToArray();
        var byName = saved.ToDictionary(x => x["name"]!.GetValue<string>());
        var scores = Rows(job["members"]).ToDictionary(x => x["name"]!.GetValue<string>());
        var personnel = new Dictionary<string, JsonObject>();
        foreach (var key in new[] { "personnel", "fixedPersonnel" })
            foreach (var row in Rows(snapshot[key] ?? snapshot["detail"]?[key])) personnel[row["name"]!.GetValue<string>()] = row;
        return selected.Select(x => x!.GetValue<string>()).Distinct().Select(name =>
        {
            JsonObject member;
            if (byName.TryGetValue(name, out var previous)) member = (JsonObject)previous.DeepClone();
            else if (personnel.TryGetValue(name, out var row))
            {
                member = new JsonObject { ["name"] = name, ["job"] = row["job"]?.GetValue<string>() ?? RuleDefaults.Jobs.GetValueOrDefault(row["jobId"]?.GetValue<int>() ?? -1)?.Name ?? "未知兵种",
                    ["personalSkills"] = Skills(row["personalTalents"]), ["jobSkills"] = Skills(row["jobTalents"]) };
            }
            else member = new JsonObject { ["name"] = name, ["personalSkills"] = Skills(new JsonArray("历史记录未保存")), ["jobSkills"] = Skills(new JsonArray("历史记录未保存")) };
            if (scores.TryGetValue(name, out var score))
            {
                if (score["job"] is not null) member["job"] = score["job"]!.DeepClone();
                if (score["score"] is not null) member["jobScore"] = score["score"]!.DeepClone();
            }
            return member;
        }).ToArray();
    }
    private static JsonObject[] Rows(JsonNode? node) => node is JsonArray array ? array.OfType<JsonObject>().ToArray() : [];
    private static JsonArray Skills(JsonNode? talents) => new((talents as JsonArray ?? []).Select(x => (JsonNode)new JsonObject { ["name"] = x?.DeepClone() }).ToArray());
}
