using System.Diagnostics;

namespace CczRandomizer.Wpf.Core;

/// <summary>Game-menu interactions; memory is used only to verify, never to manufacture a save.</summary>
public sealed class GameInteraction(int processId, string nativeDirectory, IMemoryReader memory, NativeControlSession controller, GameWindows? windows = null)
{
    private readonly GameWindows _windows = windows ?? new(processId);
    public async Task LoadAsync(string savePath, int slot, bool fromTitle, CancellationToken cancellationToken)
    {
        if (slot is < 1 or > 20) throw new ArgumentOutOfRangeException(nameof(slot));
        if (!Path.GetFileName(savePath).Equals($"SV{slot:000}.E5S", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("读取路径与存档栏位不一致。", nameof(savePath));
        cancellationToken.ThrowIfCancellationRequested();
        var expected = GameSaveState.ReadSave(savePath);
        if (slot == 20) GameSaveState.ValidateSource(expected);
        var main = _windows.Main;
        if (main == 0) throw new IOException("未找到游戏主窗口。");
        nint dialog = 0;
        var open = Stopwatch.StartNew();
        if (!fromTitle) _windows.Menu(main, 102);
        while (open.Elapsed < TimeSpan.FromSeconds(6))
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (fromTitle)
                await controller.ExecuteAsync(new NativeRequest(45, _windows.NativeHandle(main), 512, 168, ItemIndex: 300), cancellationToken);
            dialog = await WaitListAsync(TimeSpan.FromSeconds(1), cancellationToken);
            if (dialog != 0) break;
        }
        if (dialog == 0) throw new TimeoutException("读取进度窗口未出现。");
        try
        {
            await SelectSlotAsync(main, dialog, slot,
                () => !_windows.Exists(dialog) && _windows.Enabled(main) && GameSaveState.MatchesLoaded(memory, expected), cancellationToken);
        }
        catch (Exception error)
        {
            try
            {
                error.Data["windows"] = string.Join("; ", _windows.Snapshot());
                error.Data["mainEnabled"] = _windows.Enabled(main);
                var actual = memory.Read(GameSaveState.MemoryAddress, GameSaveState.MemorySize);
                error.Data["memoryDifferences"] = string.Join(",", Enumerable.Range(0, actual.Length).Where(i => actual[i] != expected[i]).Take(20).Select(i => $"{i:X}:{expected[i]:X2}>{actual[i]:X2}"));
                error.Data["transition"] = Convert.ToHexString(memory.Read(0x004AB020, 1)) + "/" + Convert.ToHexString(memory.Read(0x004ABF9C, 4));
            }
            catch (Exception diagnosticError) { error.Data["diagnosticError"] = diagnosticError.Message; }
            throw;
        }
        await controller.ExecuteAsync(new NativeRequest(4, _windows.NativeHandle(main), Count: 80), cancellationToken);
    }

    public async Task<uint[]> RandomizeAsync(CancellationToken cancellationToken)
    {
        var before = GameSaveState.InitialJobs(memory);
        if (before.Any(x => x != 0)) throw new InvalidOperationException("当前场景已包含随机结果，请重新读取源存档。");
        var window = _windows.NativeHandle(_windows.Main);
        await controller.ExecuteAsync(new NativeRequest(47), cancellationToken);
        await Task.Delay(1500, cancellationToken);
        for (var attempt = 0; attempt < 3; attempt++)
        {
            await controller.ExecuteAsync(new NativeRequest(45, window, 369, 234, ItemIndex: attempt == 0 ? 0 : 1200), cancellationToken);
            await Task.Delay(500, cancellationToken);
            await controller.ExecuteAsync(new NativeRequest(45, window, 297, 220, ItemIndex: attempt == 0 ? 0 : 1200), cancellationToken);
            var deadline = Stopwatch.StartNew();
            while (deadline.Elapsed < TimeSpan.FromSeconds(3))
            {
                cancellationToken.ThrowIfCancellationRequested();
                var jobs = GameSaveState.InitialJobs(memory);
                if (!jobs.SequenceEqual(before) && jobs.Any(x => x != 0)) return jobs;
                await Task.Delay(50, cancellationToken);
            }
            await controller.ExecuteAsync(new NativeRequest(4, window, Count: 900), cancellationToken);
        }
        throw new TimeoutException("许子将随机未触发，兵种数据仍未更新。");
    }

    public async Task SaveAsync(string targetPath, int slot, CancellationToken cancellationToken)
    {
        if (slot is < 1 or > 15) throw new ArgumentOutOfRangeException(nameof(slot), "结果只能保存到第 1 至 15 栏。");
        if (!Path.GetFileName(targetPath).Equals($"SV{slot:000}.E5S", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("结果路径与存档栏位不一致。", nameof(targetPath));
        cancellationToken.ThrowIfCancellationRequested();
        var previous = File.Exists(targetPath) ? File.GetLastWriteTimeUtc(targetPath) : (DateTime?)null;
        var main = _windows.Main;
        _windows.Menu(main, 101);
        var dialog = await WaitListAsync(TimeSpan.FromSeconds(3), cancellationToken);
        if (dialog == 0) throw new TimeoutException("保存进度窗口未出现。");
        await SelectSlotAsync(main, dialog, slot, () =>
        {
            if (!File.Exists(targetPath) || File.GetLastWriteTimeUtc(targetPath) == previous || _windows.ListDialog != 0 || !_windows.Enabled(main)) return false;
            try { _ = GameSaveState.ReadSave(targetPath); return true; }
            catch (Exception error) when (error is IOException or InvalidDataException) { return false; }
        }, cancellationToken);
    }

    private async Task<nint> WaitListAsync(TimeSpan timeout, CancellationToken cancellationToken)
    {
        var watch = Stopwatch.StartNew();
        while (watch.Elapsed < timeout)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var dialog = _windows.ListDialog;
            if (dialog != 0) return dialog;
            await Task.Delay(80, cancellationToken);
        }
        return 0;
    }

    private async Task SelectSlotAsync(nint main, nint dialog, int slot, Func<bool> completed, CancellationToken cancellationToken)
    {
        // Modal confirmations must be handled while native list activation is running.
        using var pending = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var command = NativeControlSession.SelectSlotOnceAsync(processId, nativeDirectory, slot, pending.Token);
        try
        {
            var watch = Stopwatch.StartNew();
            while (watch.Elapsed < TimeSpan.FromSeconds(25))
            {
                cancellationToken.ThrowIfCancellationRequested();
                _windows.ConfirmAlerts(main, dialog);
                if (completed()) return;
                if (command.IsFaulted) await command;
                await Task.Delay(80, cancellationToken);
            }
            throw new TimeoutException($"第 {slot} 栏存档操作未完成。");
        }
        finally
        {
            pending.Cancel();
            try { await command; } catch (OperationCanceledException) when (pending.IsCancellationRequested) { }
        }
    }
}
