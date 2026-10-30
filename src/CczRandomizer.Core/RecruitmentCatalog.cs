using System.Text.Json;
using System.IO;

namespace CczRandomizer.Wpf.Core;

public sealed record RecruitmentStage(int StageId, string Name, string Route);
public sealed record RecruitPerson(int RecordIndex, string Name, int Cost, bool FixedConfiguration, string[] JobChoices, RecruitmentStage[] Stages, string[] JobTalents, string[] PersonalTalents);

public sealed class RecruitmentCatalog
{
    public static RecruitmentCatalog Bundled { get; } = LoadBundled();
    private static RecruitmentCatalog LoadBundled()
    {
        using var stream = typeof(RecruitmentCatalog).Assembly.GetManifestResourceStream("Recruitment.Catalog")!;
        return Read(stream);
    }
    public IReadOnlyList<RecruitPerson> People { get; }
    public IReadOnlyList<RecruitmentStage> Stages { get; }
    private RecruitmentCatalog(IReadOnlyList<RecruitPerson> people, IReadOnlyList<RecruitmentStage> stages) { People = people; Stages = stages; }

    public static RecruitmentCatalog Load(string path)
    {
        using var stream = File.OpenRead(path);
        return Read(stream);
    }
    private static RecruitmentCatalog Read(Stream stream)
    {
        using var document = JsonDocument.Parse(stream);
        var root = document.RootElement;
        if (root.GetProperty("schemaVersion").GetInt32() != 1 || root.GetProperty("gameVersion").GetString() != "2.2") throw new InvalidDataException("招募目录版本不匹配");
        var stages = root.GetProperty("stages").EnumerateArray().Select(stage => new RecruitmentStage(stage.GetProperty("stageId").GetInt32(), stage.GetProperty("name").GetString() ?? "", stage.GetProperty("route").GetString() ?? "")).ToArray();
        var byId = stages.ToDictionary(x => x.StageId);
        var people = root.GetProperty("people").EnumerateArray().Select(person => new RecruitPerson(
            person.GetProperty("recordIndex").GetInt32(), person.GetProperty("name").GetString() ?? "", person.GetProperty("cost").GetInt32(), person.GetProperty("fixedConfiguration").GetBoolean(),
            person.GetProperty("jobChoices").EnumerateArray().Select(x => x.GetString() ?? "").ToArray(),
            person.GetProperty("stages").EnumerateArray().Select(stage => new RecruitmentStage(stage.GetProperty("stageId").GetInt32(), stage.GetProperty("name").GetString() ?? "", stage.GetProperty("route").GetString() ?? "")).ToArray(),
            person.TryGetProperty("jobTalents", out var jobTalents) ? jobTalents.EnumerateArray().Select(x => x.GetString() ?? "").ToArray() : [],
            person.TryGetProperty("personalTalents", out var personalTalents) ? personalTalents.EnumerateArray().Select(x => x.GetString() ?? "").ToArray() : []
        )).ToArray();
        return new RecruitmentCatalog(people, stages);
    }
}
