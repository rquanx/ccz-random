using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

internal static class RunServiceSmoke
{
    public static async Task Run(string gameDirectory, string nativeDirectory, bool exportFixture, bool compatibility = false)
    {
        var sourcePath = Path.Combine(gameDirectory, "SV/SV020.E5S");
        var sourceHash = SHA256.HashData(File.ReadAllBytes(sourcePath));
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(2));
        // The outer managed copy is the service's game directory: publication cannot touch real game slots.
        var outer = new GameSandboxService().Create(gameDirectory, workerName: "service-smoke", cancellation: timeout.Token);
        try
        {
            var rules = RuleDefaults.NewConfig();
            var profile = rules["profiles"]![rules["activeProfile"]!.GetValue<string>()]!;
            profile["threePerson"]!["qualifiedMembers"] = new JsonArray("张宝");
            profile["threePerson"]!["minJobAverage"] = 0;
            profile["threePerson"]!["jobQualificationMode"] = "average";
            profile["skillQualification"]!["threshold"] = 0;
            var options = new RandomRunOptions(outer, nativeDirectory, 2, 3, 2);
            var outcome = await new RandomRunService().RunAsync(options, rules, null, timeout.Token);
            if (outcome.SavedCount != 2) throw new Exception("服务未生成两份合格存档");
            var history = new HistoryRepository(outer);
            var rounds = history.ListRounds();
            if (rounds.Count != 1 || rounds[0].Status != "completed" || rounds[0].ResultCount != 2) throw new Exception("服务历史记录不完整");
            var results = history.GetResults(rounds[0].Id);
            foreach (var snapshot in results)
            {
                if (HistoryMembers.Resolve(snapshot).Single()["name"]!.GetValue<string>() != "张宝") throw new Exception("服务记录了未选择的人物");
                var archive = snapshot["save"]!["path"]!.GetValue<string>();
                var target = snapshot["save"]!["gamePath"]!.GetValue<string>();
                if (!File.ReadAllBytes(archive).SequenceEqual(File.ReadAllBytes(target)) || snapshot["save"]!["verified"]!.GetValue<bool>() != true) throw new Exception("发布结果与已验证存档不同");
                if (EquipmentCatalog.Read(snapshot).Count(x => !x.Special) != 70 || EntrySnapshot.Read(snapshot, RecruitmentCatalog.Bundled).Count != 130) throw new Exception("完整人物或宝物快照缺失");
            }
            if (compatibility)
            {
                profile["threePerson"]!["minJobAverage"] = 20;
                var scored = 0;
                try
                {
                    await new RandomRunService().RunAsync(new(outer, nativeDirectory, 1, 2, 1, CompatibilityMode: true), rules,
                        new ImmediateProgress(p => { if (p.Stage == "scored") scored++; }), timeout.Token);
                    throw new Exception("不可达门槛仍被判为通过");
                }
                catch (InvalidOperationException error) when (error.Message.Contains("达到尝试上限")) { }
                if (scored != 2 || history.ListRounds().Count != 1) throw new Exception("兼容模式未完成两次独立随机，或不合格结果入库");
                Console.WriteLine("Compatibility smoke passed: two fresh game sessions, both rejected, no extra history.");
            }
            if (exportFixture)
            {
                var directory = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(nativeDirectory))!, "tests/fixtures/runtime_22");
                var snapshot = results[0];
                var raw = File.ReadAllBytes(snapshot["save"]!["path"]!.GetValue<string>());
                using (var file = File.Create(Path.Combine(directory, "verified-result.E5S.gz")))
                using (var gzip = new GZipStream(file, CompressionLevel.SmallestSize)) gzip.Write(raw);
                snapshot["save"]!["path"] = "verified-result.E5S.gz";
                snapshot["save"]!["gamePath"] = null;
                File.WriteAllText(Path.Combine(directory, "verified-result.json"), snapshot.ToJsonString(new() { WriteIndented = true }));
            }
            Console.WriteLine("Run service smoke passed: 2 concurrent results, selected-person scoring, independent readback, archived/game saves and history; original game untouched.");
        }
        finally
        {
            for (var attempt = 0; ; attempt++)
                try { GameSandboxService.Remove(outer); break; }
                catch (Exception error) when (attempt < 19 && error is IOException or UnauthorizedAccessException) { await Task.Delay(100); }
            if (!SHA256.HashData(File.ReadAllBytes(sourcePath)).SequenceEqual(sourceHash)) throw new Exception("源第20栏发生变化");
        }
    }
    private sealed class ImmediateProgress(Action<RunProgress> action) : IProgress<RunProgress> { public void Report(RunProgress value) => action(value); }
}
