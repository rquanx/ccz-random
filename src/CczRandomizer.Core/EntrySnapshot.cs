using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record EntryCard(int Index, string Name, string Job, bool Fixed, int Cost,
    IReadOnlyList<string> JobTalents, IReadOnlyList<string> PersonalTalents, IReadOnlyList<RecruitmentStage> Stages)
{
    public string Title => $"{Name} · {Job}";
    public string CostText => Fixed ? "固定" : $"{Cost}次";
    public string JobTalentText => string.Join("\n", JobTalents.Count == 0 ? ["无"] : JobTalents);
    public string PersonalTalentText => string.Join("\n", PersonalTalents.Count == 0 ? ["无"] : PersonalTalents);
}
public sealed record EntryGroup(string Stage, string Kind, IReadOnlyList<EntryCard> People);
public static class EntrySnapshot
{
    public static IReadOnlyList<EntryCard> Read(JsonObject snapshot, RecruitmentCatalog catalog)
    {
        var data = new Dictionary<int, JsonObject>();
        foreach (var key in new[] { "personnel", "fixedPersonnel" })
            foreach (var row in snapshot[key] as JsonArray ?? snapshot["detail"]?[key] as JsonArray ?? [])
            {
                if (row is not JsonObject person || person["recordIndex"] is null) throw new InvalidDataException("入队人物快照无效");
                var id = person["recordIndex"]!.GetValue<int>();
                if (!data.TryAdd(id, person)) throw new InvalidDataException("入队人物快照编号重复");
            }
        var fixedPeople = FixedEntryCatalog.CreateRows();
        var fixedIds = fixedPeople.Select(x => x.RecordIndex).ToHashSet();
        return fixedPeople.Concat(catalog.People).Select(person =>
        {
            data.TryGetValue(person.RecordIndex, out var row);
            if (row is not null && row["name"]?.GetValue<string>() != person.Name) throw new InvalidDataException("入队人物与 2.2 目录不匹配");
            string[] Talents(string key) => row?[key] is JsonArray values ? values.Select(x => x!.GetValue<string>()).ToArray() : ["未采集"];
            var job = row?["job"]?.GetValue<string>() ?? (row?["jobId"] is JsonNode id ? RuleDefaults.Jobs.GetValueOrDefault(id.GetValue<int>())?.Name ?? "未知兵种" : "未采集");
            return new EntryCard(person.RecordIndex, person.Name, job, fixedIds.Contains(person.RecordIndex), person.Cost,
                Talents("jobTalents"), Talents("personalTalents"), person.Stages);
        }).ToArray();
    }
    public static string StageLabel(RecruitmentStage stage) => stage.Route == "共通" ? stage.Name : $"{stage.Route} · {stage.Name}";
    public static IReadOnlyList<EntryGroup> Group(IReadOnlyList<EntryCard> people, string query = "", string? stageFilter = null)
    {
        var terms = query.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        var matches = people.Where(person => terms.All(term => (person.Title + " " + person.JobTalentText + " " + person.PersonalTalentText).Contains(term, StringComparison.OrdinalIgnoreCase))).ToArray();
        var stages = people.SelectMany(x => x.Stages).DistinctBy(x => (x.StageId, x.Route, x.Name)).OrderBy(x => x.StageId);
        var result = new List<EntryGroup>();
        foreach (var stage in stages)
        {
            var label = StageLabel(stage);
            if (stageFilter is not null && label != stageFilter) continue;
            foreach (var fixedEntry in new[] { true, false })
            {
                var rows = matches.Where(x => x.Fixed == fixedEntry && x.Stages.Contains(stage)).ToArray();
                if (rows.Length > 0) result.Add(new(label, fixedEntry ? "固定入队 · 战前（随机预览）" : "可招募 · 战后", rows));
            }
        }
        return result;
    }
}
