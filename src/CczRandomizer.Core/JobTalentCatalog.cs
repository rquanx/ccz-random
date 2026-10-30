using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record JobTalentCard(int JobId, string Name, IReadOnlyList<string>? Talents)
{
    public string Description => Talents is null ? "未采集（请查看新生成的结果）" : Talents.Count == 0 ? "无兵种天赋" : string.Join("\n", Talents);
}
public static class JobTalentCatalog
{
    public static IReadOnlyList<JobTalentCard> Capture(SkillMemorySnapshot snapshot) => RuleDefaults.Jobs.Values.Select(job => new JobTalentCard(job.Id, job.Name,
        snapshot.Catalog.Where(skill => SkillMemoryReader.JobMatches(snapshot.RuleTable[skill.InternalId * SkillMemoryReader.RuleStride + 6], job.Id, snapshot.DirectJobMatch)).Select(skill => skill.DisplayName).ToArray())).ToArray();

    public static IReadOnlyList<JobTalentCard> Read(JsonObject snapshot)
    {
        var node = snapshot["jobTalents"] ?? snapshot["detail"]?["jobTalents"];
        if (node is not null && node is not JsonArray) throw new InvalidDataException("兵种天赋快照格式错误");
        var values = new Dictionary<int, string[]>();
        foreach (var row in node as JsonArray ?? [])
        {
            var id = row?["jobId"]?.GetValue<int>() ?? -1;
            if (!RuleDefaults.Jobs.ContainsKey(id) || values.ContainsKey(id) || row?["talents"] is not JsonArray talents) throw new InvalidDataException("兵种天赋快照编号或数据无效");
            values[id] = talents.Select(x => x?.GetValue<string>() ?? throw new InvalidDataException("天赋名称无效")).ToArray();
        }
        return RuleDefaults.Jobs.Values.Select(job => new JobTalentCard(job.Id, job.Name, values.GetValueOrDefault(job.Id))).ToArray();
    }
}
