namespace CczRandomizer.Wpf.Core;

public static class FixedEntryCatalog
{
    private static readonly Dictionary<string, int> Indices = new()
    {
        ["曹操"] = 0, ["夏侯惇"] = 1, ["夏侯渊"] = 6, ["曹洪"] = 12,
        ["典韦"] = 16, ["许褚"] = 15, ["荀彧"] = 20, ["郭嘉"] = 22,
        ["张辽"] = 2, ["司马懿"] = 19, ["庞德"] = 9, ["曹彰"] = 4,
        ["郭淮"] = 29, ["赵云"] = 34
    };
    private static readonly Dictionary<string, int> StageIds = new()
    {
        ["共通 · 颍川之战"] = 0, ["共通 · 汜水关之战"] = 1,
        ["共通 · 青州讨伐战"] = 4, ["共通 · 徐州之战"] = 5,
        ["共通 · 濮阳决战"] = 8, ["共通 · 徐州平定战"] = 15,
        ["红线 · 汉中讨伐战"] = 32, ["红线 · 逍遥津之战"] = 33,
        ["红线 · 定军山之战"] = 35, ["红线 · 樊城救援战"] = 38,
        ["蓝线 · 定军山之战·异"] = 46, ["蓝线 · 麦城救援战"] = 47
    };
    private static readonly (string Name, string[] Stages)[] Entries =
    [
        ("曹操", ["共通 · 颍川之战"]), ("夏侯惇", ["共通 · 颍川之战"]), ("夏侯渊", ["共通 · 颍川之战"]),
        ("曹洪", ["共通 · 汜水关之战"]), ("典韦", ["共通 · 青州讨伐战"]), ("荀彧", ["共通 · 青州讨伐战"]),
        ("郭嘉", ["共通 · 徐州之战"]), ("许褚", ["共通 · 濮阳决战"]), ("张辽", ["共通 · 徐州平定战"]),
        ("司马懿", ["红线 · 汉中讨伐战", "蓝线 · 定军山之战·异"]), ("庞德", ["红线 · 逍遥津之战", "蓝线 · 定军山之战·异"]),
        ("郭淮", ["红线 · 定军山之战"]), ("曹彰", ["红线 · 樊城救援战", "蓝线 · 定军山之战·异"]), ("赵云", ["蓝线 · 麦城救援战"]),
    ];
    // Story membership is distinct from fixed recruitment job configuration.
    public static IReadOnlyList<RecruitPerson> CreateRows() => Entries.Select(entry => new RecruitPerson(Indices[entry.Name], entry.Name, 0, false, [], entry.Stages.Select(stage => new RecruitmentStage(StageIds[stage], stage.Split(" · ").Last(), stage.Split(" · ").First())).ToArray(), [], [])).ToArray();
}
