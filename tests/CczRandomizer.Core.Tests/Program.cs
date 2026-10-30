using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

if (args.Length == 2 && args[0] == "--native-test-helper") { NativeControlTests.Helper(args[1]); return; }
if (args.Length == 1 && args[0] == "--audio-probe") { AudioRepairTests.Probe(); return; }
if (args.Length == 1 && args[0] == "--audio-self-smoke") { await AudioRepairTests.SelfSessionSmoke(); return; }
if (args.Length == 3 && args[0] == "--native-game-smoke") { await NativeGameSmoke.Run(args[1], args[2]); return; }
if (args.Length is >= 3 and <= 5 && args[0] == "--run-service-smoke") { await RunServiceSmoke.Run(args[1], args[2], args.Contains("--export-fixture"), args.Contains("--compatibility")); return; }

static void Assert(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

var document = new JsonObject
{
    ["version"] = 2,
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
Assert(!RuleEvaluator.EvaluateJobs(document, [new JobScore("张宝", "道士", "MASTER", 7)]).Qualified, "整数门槛被忽略");
var attempts = 0;
var workflow = RandomWorkflow.Run(2, 3, (_, _, _) => new AttemptResult<string>(++attempts % 2 == 0, true, "ok"));
Assert(workflow.Count == 2 && attempts == 4, "随机流程状态机未通过");
Assert(SkillMemoryReader.Normalize("能力替换-攻→士") == SkillMemoryReader.Normalize("能力替换攻替士"), "天赋名称规范化未通过");
var fixtures = Path.Combine(AppContext.BaseDirectory, "fixtures");
var memory = new RecordedMemory(Path.Combine(fixtures, "randomized-memory.json"));
var jobTalents = JobTalentCatalog.Capture(SkillMemoryReader.Read(memory, [0])).ToDictionary(x => x.JobId);
var verified = 0;
foreach (var file in new[] { "randomized-personnel.json", "randomized-fixed-personnel.json" })
{
    var expected = JsonNode.Parse(File.ReadAllText(Path.Combine(fixtures, file)))!.AsArray();
    var indices = expected.Select(x => x!["recordIndex"]!.GetValue<int>()).ToArray();
    var fixedIndices = expected.Where(x => x!["fixedConfiguration"]?.GetValue<bool>() == true).Select(x => x!["recordIndex"]!.GetValue<int>()).ToHashSet();
    var actual = PersonnelMemoryReader.Read(memory, indices, true, fixedIndices);
    for (var index = 0; index < actual.Count; index++)
    {
        var row = expected[index]!;
        var person = actual[index];
        Assert(person.RecordIndex == row["recordIndex"]!.GetValue<int>(), "记录编号不符");
        Assert(person.Name == row["name"]!.GetValue<string>(), "姓名不符");
        Assert(person.JobId == row["jobId"]!.GetValue<int>(), $"{person.Name} 预生成兵种不符");
        Assert(person.CurrentJobId == row["currentJobId"]!.GetValue<int>(), $"{person.Name} 当前兵种不符");
        Assert(person.JobTalents.SequenceEqual(row["jobTalents"]!.AsArray().Select(x => x!.GetValue<string>())), $"{person.Name} 兵种天赋不符");
        Assert(jobTalents[person.JobId].Talents!.SequenceEqual(person.JobTalents), $"{person.Name} 全兵种天赋目录不一致");
        Assert(person.PersonalTalents.SequenceEqual(row["personalTalents"]!.AsArray().Select(x => x!.GetValue<string>())), $"{person.Name} 人物天赋不符");
        verified++;
    }
}
Assert(JobTalentCatalog.Read(new JsonObject()).All(x => x.Talents is null), "缺失历史天赋不得当成无天赋");
var temp = Path.Combine(Path.GetTempPath(), "ccz-core-test-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(temp);
try
{
    string Write(string relative, bool old = true)
    {
        var path = Path.Combine(temp, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "12345678");
        if (old) File.SetLastWriteTimeUtc(path, DateTime.UtcNow.AddDays(-2));
        return path;
    }
    var log = Write("ccz_fast_logs/fast_20261001_120000.log");
    var ruleFile = Path.Combine(temp, "random_rules_v2.json");
    File.WriteAllText(ruleFile, document.ToJsonString());
    var store = new RuleDocumentStore();
    Assert(store.Load(ruleFile), "规则未加载");
    var isolatedDraft = store.CreateDraft(); isolatedDraft.SetJobThreshold(12);
    Assert(store.ActiveProfile["threePerson"]!["minJobAverage"]!.GetValue<double>() == 8 && File.ReadAllText(ruleFile) == document.ToJsonString(), "未保存的草稿影响运行规则或文件");
    store.SetQualifiedMembers(["张宝"]);
    store.SetJobThreshold(7);
    store.SetGates("total", 30, 1, "average", 2.5, 1);
    Assert(store.ActiveProfile["skillQualification"]!["threshold"]!.GetValue<double>() == 2.5, "独立特技门槛未保存");
    Assert(store.ActiveProfile["threePerson"]!["minJobAverage"]!.GetValue<double>() == 30, "总分门槛不应受单人20分限制");
    try { store.SetGates("count", 8, 2, "average", 2, 1); throw new Exception("允许了超出选择人数的要求"); } catch (ArgumentException) { }
    store.SetGates("count", 7, 1, "total", 5, 1);
    store.Save();
    Assert(JsonNode.Parse(File.ReadAllText(ruleFile))!["profiles"]!["test"]!["threePerson"]!["minJobAverage"]!.GetValue<double>() == 7, "规则未正确保存");
    Assert(File.ReadAllText(ruleFile + ".bak") == document.ToJsonString(), "规则备份不符");
    File.WriteAllText(ruleFile, document.ToJsonString());
    try { store.Save(); throw new Exception("覆盖了外部修改"); } catch (IOException) { }
    var image = Write("ccz_fast_logs/fast_20261001_120000_inspection_failure_panel.png");
    var recent = Write("ccz_fast_logs/fast_20261029_120000.log", false);
    var unknown = Write("ccz_fast_logs/notes.txt");
    var dead = Write("ccz_fast_data/sandboxes/123-456/workers/game.dat");
    var live = Write("ccz_fast_data/sandboxes/789-456/workers/game.dat");
    var result = Write("randResult/loop/run/SV001.E5S");
    var history = Write("ccz_fast_data/history.sqlite3");
    var service = new StorageCleanupService(temp, pid => pid == 789);
    Assert(service.Scan().Single(x => x.Category == "logs").Cleanable == 8, "清理大小不符");
    Assert(service.Clean("logs").Removed == 1 && File.Exists(image), "分类清理不符");
    Assert(service.Clean("logs", "screenshots", "sandboxes").Removed == 2, "全清理范围不符");
    Assert(!File.Exists(dead) && !File.Exists(log), "残留文件未删除");
    Assert(new[] { recent, unknown, live, result, history }.All(File.Exists), "用户文件或运行中的沙箱被删除");
}
finally { Directory.Delete(temp, true); }
var game = Path.Combine(Path.GetTempPath(), "ccz-sandbox-test-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(game);
try
{
    Directory.CreateDirectory(Path.Combine(game, "SV"));
    Directory.CreateDirectory(Path.Combine(game, "RS"));
    File.WriteAllText(Path.Combine(game, "Ekd5.exe"), "fixture executable, never started");
    File.WriteAllText(Path.Combine(game, "SV/SV020.E5S"), "source save");
    File.WriteAllText(Path.Combine(game, "SV/SV001.E5S"), "user save");
    File.WriteAllText(Path.Combine(game, "RS/R_00.eex"), "script");
    File.WriteAllText(Path.Combine(game, "resource.dat"), "shared resource");
    File.WriteAllText(Path.Combine(game, "random_rules_v2.json"), "user rules");
    Directory.CreateDirectory(Path.Combine(game, "portable-tool"));
    File.WriteAllText(Path.Combine(game, "portable-tool/.ccz-wpf-release"), "1");
    File.WriteAllText(Path.Combine(game, "portable-tool/coreclr.dll"), "packaged runtime");
    var sandbox = new GameSandboxService().Create(game);
    Assert(!Directory.Exists(Path.Combine(sandbox, "portable-tool")), "发布目录不应复制到游戏沙箱");
    var nested = new GameSandboxService().Create(sandbox);
    File.WriteAllText(Path.Combine(nested, "random_rules_v2.json"), "test rules");
    Assert(File.ReadAllText(Path.Combine(sandbox, "random_rules_v2.json")) == "user rules" && File.ReadAllText(Path.Combine(game, "random_rules_v2.json")) == "user rules", "嵌套沙箱修改了源规则");
    Assert(File.ReadAllText(Path.Combine(nested, "SV/SV020.E5S")) == "source save", "隔离副本不能再次创建沙箱");
    GameSandboxService.Remove(nested);
    Assert(!File.Exists(Path.Combine(sandbox, "SV/SV001.E5S")), "沙箱复制了非源存档");
    File.WriteAllText(Path.Combine(sandbox, "SV/SV020.E5S"), "changed");
    File.WriteAllText(Path.Combine(sandbox, "RS/R_00.eex"), "changed");
    Assert(File.ReadAllText(Path.Combine(game, "SV/SV020.E5S")) == "source save", "沙箱修改源存档");
    Assert(File.ReadAllText(Path.Combine(game, "RS/R_00.eex")) == "script", "沙箱修改源脚本");
    var usage = new StorageCleanupService(game, _ => false).Scan().Single(x => x.Category == "sandboxes");
    var totalBytes = Directory.EnumerateFiles(sandbox, "*", SearchOption.AllDirectories).Sum(x => new FileInfo(x).Length);
    Assert(usage.Total == totalBytes - "shared resource".Length, "硬链接被计算为可回收磁盘空间");
    var lockedPath = Path.Combine(sandbox, "locked-test.dat");
    using (var locked = new FileStream(lockedPath, FileMode.Create, FileAccess.ReadWrite, FileShare.None))
    {
        try { GameSandboxService.Remove(sandbox); throw new Exception("锁定文件应阻止沙箱清理"); }
        catch (IOException) { }
        Assert(File.Exists(Path.Combine(sandbox, ".ccz-wpf-sandbox")), "清理失败丢失沙箱标记，无法重试");
    }
    GameSandboxService.Remove(sandbox);
    Assert(File.ReadAllText(Path.Combine(game, "resource.dat")) == "shared resource", "清理沙箱影响原始资源");
    Assert(!Directory.Exists(sandbox), "沙箱未清理");
}
finally { Directory.Delete(game, true); }
var scoringCases = ScoringParity.Run();
SettingsDraftTests.Run();
RuleImportTests.Run();
HistoryTests.Run();
GameSaveStateTests.Run();
EquipmentTests.Run();
await NativeControlTests.Run();
await RunServiceTests.Run();
RuntimePreferencesTests.Run();
AudioRepairTests.Run();
Console.WriteLine($"C# core tests passed: {verified} recorded personnel, {scoringCases} scoring parity cases, workflow, cleanup boundaries.");
