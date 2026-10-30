namespace CczRandomizer.Wpf.Core;

public static class FixedEntryCatalog
{
    private static readonly (string Name, string[] Stages)[] Entries =
    [
        ("曹操", ["共通 · 颍川之战"]), ("夏侯惇", ["共通 · 颍川之战"]), ("夏侯渊", ["共通 · 颍川之战"]),
        ("曹洪", ["共通 · 汜水关之战"]), ("典韦", ["共通 · 青州讨伐战"]), ("荀彧", ["共通 · 青州讨伐战"]),
        ("郭嘉", ["共通 · 徐州之战"]), ("许褚", ["共通 · 濮阳决战"]), ("张辽", ["共通 · 徐州平定战"]),
        ("司马懿", ["红线 · 汉中讨伐战", "蓝线 · 定军山之战·异"]), ("庞德", ["红线 · 逍遥津之战", "蓝线 · 定军山之战·异"]),
        ("郭淮", ["红线 · 定军山之战"]), ("曹彰", ["红线 · 樊城救援战", "蓝线 · 定军山之战·异"]), ("赵云", ["蓝线 · 麦城救援战"]),
    ];
    public static IReadOnlyList<RecruitPerson> CreateRows() => Entries.Select((entry, index) => new RecruitPerson(10000 + index, entry.Name, 0, true, [], entry.Stages.Select((stage, stageIndex) => new RecruitmentStage(stageIndex, stage.Split(" · ").Last(), stage.Split(" · ").First())).ToArray(), [], [])).ToArray();
}
