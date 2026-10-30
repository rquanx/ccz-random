using System.IO.Compression;
using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

internal static class RunServiceTests
{
    private static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    private static byte[] Inflate(string name)
    {
        using var input = File.OpenRead(Path.Combine(AppContext.BaseDirectory, "runtime_22", name));
        using var zip = new GZipStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream(); zip.CopyTo(output); return output.ToArray();
    }
    public static async Task Run()
    {
        var saved = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "runtime_22/verified-result.json")))!;
        var people = new[] { "personnel", "fixedPersonnel" }.SelectMany(key => saved[key]!.AsArray()).Select(x => new PersonnelRecord(
            x!["recordIndex"]!.GetValue<int>(), x["memberId"]!.GetValue<uint>(), x["name"]!.GetValue<string>(),
            x["jobId"]!.GetValue<byte>(), x["currentJobId"]!.GetValue<byte>(),
            x["jobTalents"]!.AsArray().Select(t => t!.GetValue<string>()).ToArray(),
            x["personalTalents"]!.AsArray().Select(t => t!.GetValue<string>()).ToArray())).ToArray();
        var snapshot = new GameSnapshot(people, JobTalentCatalog.Read(saved.AsObject()), saved["equipment"]!.AsObject());
        var rules = RuleDefaults.NewConfig();
        var profile = rules["profiles"]![rules["activeProfile"]!.GetValue<string>()]!;
        profile["threePerson"]!["qualifiedMembers"] = new JsonArray("张宝");
        profile["threePerson"]!["minJobAverage"] = 0;
        profile["threePerson"]!["jobQualificationMode"] = "average";
        profile["skillQualification"]!["threshold"] = 0;
        profile["skillQualification"]!["mode"] = "average";
        var game = Path.Combine(Path.GetTempPath(), "ccz-run-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(game, "SV"));
        var source = Inflate("source-state.bin.gz");
        File.WriteAllBytes(Path.Combine(game, "SV/SV020.E5S"), source);
        var candidate = Path.Combine(game, "verified.E5S");
        File.WriteAllBytes(candidate, Inflate("verified-result.E5S.gz"));
        var workers = new System.Collections.Concurrent.ConcurrentBag<FakeWorker>();
        GameWorkerFactory factory = (_, _, _, _) =>
        {
            var worker = new FakeWorker(candidate, snapshot); workers.Add(worker);
            return Task.FromResult<IRandomGameWorker>(worker);
        };
        try
        {
            var log = new RunLog(game, 1024);
            for (var i = 0; i < 100; i++) log.Write(new string('x', 1500), new IOException("test diagnostic"));
            var logs = Directory.GetFiles(Path.Combine(game, "ccz_fast_logs"));
            Check(logs.Length <= 3 && logs.Sum(x => new FileInfo(x).Length) <= 3072, "日志轮转没有限制空间");
            var service = new RandomRunService(factory);
            var result = await service.RunAsync(new(game, "", 2, 2, 2), rules, null, default);
            Check(result.SavedCount == 2 && workers.All(w => w.Disposed), "并发结果或清理不完整");
            var history = new HistoryRepository(game);
            var round = history.ListRounds().Single();
            var results = history.GetResults(round.Id);
            Check(results.Count == 2 && results.All(r => HistoryMembers.Resolve(r).Single()["name"]!.GetValue<string>() == "张宝"), "历史未限定所选人物");
            Check(results.All(r => r["detail"]!["skill"]!["metrics"]!["memberSkillScores"]!.AsObject().Select(x => x.Key).SequenceEqual(["张宝"])), "特技未使用所选人物");
            Check(File.ReadAllBytes(Path.Combine(game, "SV/SV020.E5S")).SequenceEqual(source), "修改了源存档");
            var publisher = new ResultPublisher(game, "publisher-test", 2);
            var scored = ResultSnapshot.Score(rules, snapshot, 1, 1).Document;
            var published = publisher.Publish(new(candidate, snapshot), scored, 1);
            Check(published["save"]!["published"]!.GetValue<bool>() && JsonNode.Parse(File.ReadAllText(Path.ChangeExtension(published["save"]!["path"]!.GetValue<string>(), ".json")))!["save"]!["published"]!.GetValue<bool>(), "发布状态未持久化");
            Check(File.ReadAllBytes(Path.Combine(game, "randResult/publisher-test/round-0001/previous-SV001.E5S")).SequenceEqual(File.ReadAllBytes(candidate)), "旧存档未备份");
            scored["slot"] = 2;
            File.WriteAllText(Path.Combine(game, "SV/SV002.E5S"), "external change");
            try { publisher.Publish(new(candidate, snapshot), scored, 1); throw new Exception("覆盖外部修改"); } catch (IOException) { }
            Check(File.ReadAllText(Path.Combine(game, "SV/SV002.E5S")) == "external change" && File.Exists(Path.Combine(game, "randResult/publisher-test/round-0001/SV002.E5S")), "未保护外部修改与结果副本");
            Check(JsonNode.Parse(File.ReadAllText(Path.Combine(game, "randResult/publisher-test/round-0001/SV002.json")))!["save"]!["published"]!.GetValue<bool>() == false, "未发布的归档被标为已发布");

            profile["threePerson"]!["minJobAverage"] = 20;
            var before = workers.Count;
            var previousWorkers = workers.ToHashSet();
            try { await service.RunAsync(new(game, "", 1, 2), rules, null, default); throw new Exception("未达标仍成功"); } catch (InvalidOperationException) { }
            Check(history.ListRounds().Count == 1 && workers.Count == before + 1 && workers.All(w => w.Disposed), "不合格结果入库或未释放");
            Check(workers.Except(previousWorkers).Single().Saves == 0, "未达标仍保存");

            profile["threePerson"]!["minJobAverage"] = 0;
            using (var database = new Microsoft.Data.Sqlite.SqliteConnection($"Data Source={history.DatabasePath};Pooling=False"))
            {
                database.Open();
                using var command = database.CreateCommand();
                command.CommandText = "CREATE TRIGGER reject_result BEFORE INSERT ON results BEGIN SELECT RAISE(ABORT, 'test write failure'); END;"; command.ExecuteNonQuery();
                try
                {
                    try { await service.RunAsync(new(game, "", 1, 2), rules, null, default); throw new Exception("历史写入失败被忽略"); }
                    catch (IOException error)
                    {
                        Check(error.Message.Contains("存档副本：") && error.Message.Contains("SV001.E5S") && File.ReadAllBytes(Path.Combine(game, "SV/SV001.E5S")).SequenceEqual(File.ReadAllBytes(candidate)), "历史失败没有保留存档或提示位置");
                    }
                }
                finally { command.CommandText = "DROP TRIGGER reject_result"; command.ExecuteNonQuery(); }
            }
            using var cancel = new CancellationTokenSource();
            var progress = new InlineProgress(p => { if (p.Stage == "saved" && p.Round == 2) cancel.Cancel(); });
            try { await service.RunAsync(new(game, "", 1, 2, 1, true), rules, progress, cancel.Token); throw new Exception("取消未生效"); } catch (OperationCanceledException) { }
            Check(workers.All(w => w.Disposed) && history.ListRounds().Count == 3, "循环或取消清理错误");

            var failures = 0;
            var failing = new RandomRunService((_, _, _, _) => { failures++; throw new IOException("recorded transient category"); });
            try { await failing.RunAsync(new(game, "", 1, 10), rules, null, default); throw new Exception("连续失败被忽略"); } catch (IOException) { }
            Check(failures == 3 && history.ListRounds().Count == 3, "失败恢复上限或空历史错误");
            using var inFlightCancel = new CancellationTokenSource();
            var blocked = new BlockingWorker();
            var running = new RandomRunService((_, _, _, _) => Task.FromResult<IRandomGameWorker>(blocked))
                .RunAsync(new(game, ""), rules, null, inFlightCancel.Token);
            await blocked.Started.Task.WaitAsync(TimeSpan.FromSeconds(5));
            inFlightCancel.Cancel();
            try { await running; throw new Exception("运行中取消未生效"); } catch (OperationCanceledException) { }
            Check(blocked.Disposed && history.ListRounds().Count == 3, "取消没有等待实例释放或留下空历史");
            profile["threePerson"]!["minJobAverage"] = 20;
            var reloadWorkers = new List<ReloadWorker>(); var compatibilityNotices = 0;
            var reloadService = new RandomRunService((_, _, _, _) =>
            {
                var worker = new ReloadWorker(snapshot); reloadWorkers.Add(worker); return Task.FromResult<IRandomGameWorker>(worker);
            });
            try
            {
                await reloadService.RunAsync(new(game, "", 1, 6), rules, new InlineProgress(p => { if (p.Stage == "compatibility") compatibilityNotices++; }), default);
                throw new Exception("不合格结果仍通过");
            }
            catch (InvalidOperationException) { }
            Check(compatibilityNotices == 1 && reloadWorkers.Count == 3 && reloadWorkers.Sum(x => x.Resets) == 2 && reloadWorkers.All(x => x.Disposed), "复用失败后未切换为每次重启");
        }
        finally { Directory.Delete(game, true); }
    }
    private sealed class InlineProgress(Action<RunProgress> callback) : IProgress<RunProgress>
    { public void Report(RunProgress value) => callback(value); }
    private sealed class FakeWorker(string path, GameSnapshot snapshot) : IRandomGameWorker
    {
        public int Rolls; public int Saves; public bool Disposed;
        public Task ResetAsync() => Task.CompletedTask;
        public Task<GameSnapshot> RollAsync(CancellationToken token) { token.ThrowIfCancellationRequested(); Rolls++; return Task.FromResult(snapshot); }
        public Task<SavedCandidate> SaveAndVerifyAsync(int slot, CancellationToken token) { token.ThrowIfCancellationRequested(); Saves++; return Task.FromResult(new SavedCandidate(path, snapshot)); }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
    private sealed class BlockingWorker : IRandomGameWorker
    {
        public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool Disposed;
        public Task ResetAsync() => Task.CompletedTask;
        public async Task<GameSnapshot> RollAsync(CancellationToken token)
        { Started.SetResult(); await Task.Delay(Timeout.Infinite, token); throw new Exception("unreachable"); }
        public Task<SavedCandidate> SaveAndVerifyAsync(int slot, CancellationToken token) => throw new Exception("取消后不应保存");
        public async ValueTask DisposeAsync() { await Task.Yield(); Disposed = true; }
    }
    private sealed class ReloadWorker(GameSnapshot snapshot) : IRandomGameWorker
    {
        private bool _loaded;
        public int Resets; public bool Disposed;
        public Task ResetAsync() { Resets++; _loaded = false; return Task.CompletedTask; }
        public Task<GameSnapshot> RollAsync(CancellationToken token)
        {
            if (_loaded) throw new GameReloadException(new TimeoutException("读取进度窗口未出现。"));
            _loaded = true; return Task.FromResult(snapshot);
        }
        public Task<SavedCandidate> SaveAndVerifyAsync(int slot, CancellationToken token) => throw new Exception("不合格结果不应保存");
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }
}
