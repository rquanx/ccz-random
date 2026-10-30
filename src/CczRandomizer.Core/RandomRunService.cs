using System.ComponentModel;
using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record RandomRunOptions(string GameDirectory, string NativeDirectory, int ResultCount = 1,
    int MaxAttempts = 10000, int Workers = 1, bool Loop = false, bool CompatibilityMode = false);
public sealed record RunProgress(string Stage, int Round, int Slot, int Attempt, int SavedCount, string Message, JsonObject? Snapshot = null);
public sealed record RunOutcome(string RunId, int SavedCount, int Rounds);
public delegate Task<IRandomGameWorker> GameWorkerFactory(string gameDirectory, string nativeDirectory, int worker, CancellationToken cancellationToken);
public delegate Task<IReadOnlyList<string>> ResultImageWriter(JsonObject snapshot);

public sealed class RandomRunService(GameWorkerFactory? factory = null, ResultImageWriter? imageWriter = null)
{
    private readonly GameWorkerFactory _factory = factory ?? RandomGameWorker.CreateAsync;
    public Task<RunOutcome> RunAsync(RandomRunOptions options, JsonObject rules, IProgress<RunProgress>? progress, CancellationToken cancellationToken)
    {
        // Freeze the rule document and keep SQLite/capture work off the WPF dispatcher.
        var frozen = (JsonObject)rules.DeepClone();
        return Task.Run(() => RunCoreAsync(options, frozen, progress, cancellationToken), cancellationToken);
    }
    private async Task<RunOutcome> RunCoreAsync(RandomRunOptions options, JsonObject rules, IProgress<RunProgress>? progress, CancellationToken cancellationToken)
    {
        if (options.ResultCount is < 1 or > 15 || options.Workers is < 1 or > 15 || options.MaxAttempts < 1) throw new ArgumentException("结果数量、并发数量或尝试上限无效。");
        GameSaveState.ValidateSource(GameSaveState.ReadSave(Path.Combine(options.GameDirectory, "SV/SV020.E5S")));
        var selected = rules["profiles"]?[rules["activeProfile"]?.GetValue<string>() ?? ""]?["threePerson"]?["qualifiedMembers"] as JsonArray;
        if (selected is null || selected.Count == 0) throw new InvalidDataException("请先选择参与评分的人物。");
        RuleImporter.ValidateProfile(rules["profiles"]![rules["activeProfile"]!.GetValue<string>()]!.AsObject());
        var runId = DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N")[..8];
        Directory.CreateDirectory(Path.Combine(options.GameDirectory, "ccz_fast_data"));
        using var runLock = new FileStream(Path.Combine(options.GameDirectory, "ccz_fast_data/wpf-run.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        var log = new RunLog(options.GameDirectory);
        log.Write($"Run {runId} started; workers={options.Workers}; results={options.ResultCount}");
        try { new StorageCleanupService(options.GameDirectory).Clean("logs", "screenshots", "sandboxes"); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { log.Write("Startup cleanup incomplete", error); }
        var repository = new HistoryRepository(options.GameDirectory);
        var publisher = new ResultPublisher(options.GameDirectory, runId, options.ResultCount);
        repository.StartRun(runId, options.Loop, rules["activeProfile"]!.GetValue<string>(), rules, new JsonObject { ["runtime"] = "C# WPF", ["gameVersion"] = "2.2" });
        var saved = 0; var round = 0; var status = "failed";
        var compatibility = options.CompatibilityMode ? 1 : 0;
        var reloadFailures = 0;
        try
        {
            do
            {
                cancellationToken.ThrowIfCancellationRequested(); round++;
                var roundId = repository.StartRound(runId, round);
                var roundStatus = "failed";
                using var stopRound = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                var nextSlot = 0;
                var tasks = Enumerable.Range(1, Math.Min(options.Workers, options.ResultCount)).Select(Worker).ToArray();
                try { await Task.WhenAll(tasks); roundStatus = "completed"; }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { roundStatus = "stopped"; throw; }
                catch
                {
                    var failure = tasks.Where(t => t.IsFaulted).SelectMany(t => t.Exception!.InnerExceptions).FirstOrDefault(e => e is not OperationCanceledException);
                    if (failure is not null) System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(failure).Throw();
                    throw;
                }
                finally
                {
                    try { repository.FinishRound(roundId, roundStatus); }
                    catch (Exception error) when (roundStatus != "completed") { log.Write("Unable to record failed/stopped round status", error); }
                }

                async Task Worker(int workerNumber)
                {
                    IRandomGameWorker? worker = null;
                    try
                    {
                        int slot;
                        while ((slot = Interlocked.Increment(ref nextSlot)) <= options.ResultCount)
                        {
                            var complete = false; var consecutiveErrors = 0;
                            for (var attempt = 1; attempt <= options.MaxAttempts; attempt++)
                            {
                                stopRound.Token.ThrowIfCancellationRequested();
                                progress?.Report(new("randomizing", round, slot, attempt, Volatile.Read(ref saved), $"第 {slot} 栏 · 第 {attempt} 次随机"));
                                SavedCandidate? candidate = null;
                                ScoredSnapshot evaluation;
                                try
                                {
                                    worker ??= await _factory(options.GameDirectory, options.NativeDirectory, workerNumber, stopRound.Token);
                                    if (Volatile.Read(ref compatibility) != 0) await worker.ResetAsync();
                                    var game = await worker.RollAsync(stopRound.Token);
                                    evaluation = ResultSnapshot.Score(rules, game, slot, attempt);
                                    progress?.Report(new("scored", round, slot, attempt, Volatile.Read(ref saved), evaluation.Qualified ? "评分达标，正在保存并验证" : "评分未达标", evaluation.Document));
                                    if (evaluation.Qualified)
                                    {
                                        candidate = await worker.SaveAndVerifyAsync(slot, stopRound.Token);
                                        evaluation = ResultSnapshot.Score(rules, candidate.Snapshot, slot, attempt);
                                    }
                                    consecutiveErrors = 0;
                                }
                                catch (Exception error) when (error is TimeoutException or Win32Exception or IOException)
                                {
                                    log.Write($"Worker {workerNumber}, slot {slot}, attempt {attempt} failed", error);
                                    if (error is GameReloadException && Interlocked.Increment(ref reloadFailures) >= 2 && Interlocked.Exchange(ref compatibility, 1) == 0)
                                        progress?.Report(new("compatibility", round, slot, attempt, Volatile.Read(ref saved), "当前设备读档不稳定，已切换兼容模式，每次随机使用新游戏实例"));
                                    if (worker is not null) { await worker.DisposeAsync(); worker = null; }
                                    if (++consecutiveErrors >= 3) throw;
                                    progress?.Report(new("recovering", round, slot, attempt, Volatile.Read(ref saved), "游戏本次未完成操作，正在重新启动后重试"));
                                    continue;
                                }
                                if (!evaluation.Qualified || candidate is null) continue;
                                stopRound.Token.ThrowIfCancellationRequested();
                                var snapshot = publisher.Publish(candidate, evaluation.Document, round);
                                if (imageWriter is not null)
                                {
                                    try
                                    {
                                        var images = await imageWriter(snapshot);
                                        snapshot["images"] = new JsonArray(images.Select(x => (JsonNode)JsonValue.Create(x)!).ToArray());
                                        ResultPublisher.WriteMetadata(snapshot);
                                    }
                                    catch (Exception error) { log.Write("Result image export failed; verified save preserved", error); snapshot["imageError"] = "结果图片未生成，存档已保留。"; }
                                }
                                try { repository.SaveResult(roundId, snapshot); }
                                catch (Exception error)
                                { throw new IOException($"存档已发布，但历史记录写入失败。存档副本：{snapshot["save"]!["path"]!.GetValue<string>()}。{error.Message}", error); }
                                var count = Interlocked.Increment(ref saved);
                                progress?.Report(new("saved", round, slot, attempt, count, $"第 {slot} 栏已保存，读回验证通过", snapshot));
                                complete = true; break;
                            }
                            if (!complete) throw new InvalidOperationException($"第 {slot} 栏达到尝试上限，尚无合格结果。");
                        }
                    }
                    catch { stopRound.Cancel(); throw; }
                    finally
                    {
                        if (worker is not null)
                            try { await worker.DisposeAsync(); }
                            catch (Exception error) { log.Write($"Worker {workerNumber} cleanup failed", error); }
                    }
                }
            } while (options.Loop);
            status = "completed";
            return new(runId, saved, round);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { status = "stopped"; throw; }
        catch (Exception error) { log.Write("Run failed", error); throw; }
        finally
        {
            try { repository.FinishRun(runId, status); }
            catch (Exception error) when (status != "completed") { log.Write("Unable to record failed/stopped run status", error); }
            log.Write($"Run {runId} {status}; saved={saved}");
        }
    }
}
