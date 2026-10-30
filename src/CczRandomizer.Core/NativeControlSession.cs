using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace CczRandomizer.Wpf.Core;

// Layout is defined by ControlRequest in native/ccz_injector.c, not CLI argument order.
public readonly record struct NativeRequest(int Action, uint Window = 0, int X = 0, int Y = 0,
    int Count = 0, int Right = 0, int ItemIndex = 0)
{
    public string Encode()
    {
        if (Action is < 1 or > 48) throw new ArgumentOutOfRangeException(nameof(Action));
        return FormattableString.Invariant($"{Action} {Window} {X} {Y} {Count} {Right} {ItemIndex}");
    }
    public TimeSpan Timeout => TimeSpan.FromSeconds(Action is 15 or 25 or 41 or 46 ? 70 : Action == 1 ? 25 : 10);
    public static NativeRequest TitleLoad(int slot) => new(37, ItemIndex: SaveIndex(slot));
    public static NativeRequest SelectSave(int slot) => new(1, ItemIndex: SaveIndex(slot));
    public static NativeRequest SilentClick(uint window, int x, int y) => new(22, window, x, y);
    private static int SaveIndex(int slot) => slot is >= 1 and <= 20 ? slot - 1 : throw new ArgumentOutOfRangeException(nameof(slot));
}

public sealed class NativeControlException(uint code, string diagnostics) : IOException($"游戏控制失败（代码 {code}）。")
{
    public uint Code { get; } = code;
    public string Diagnostics { get; } = diagnostics;
}

/// <summary>One helper per game process; serializes requests and bounds diagnostics in memory.</summary>
public sealed class NativeControlSession : IAsyncDisposable
{
    private readonly Process _process;
    private readonly SemaphoreSlim _requests = new(1, 1);
    private readonly StringBuilder _diagnostics = new();
    private readonly Task _stderr;
    private int _closed;
    private bool _disposed;
    public string Diagnostics { get { lock (_diagnostics) return _diagnostics.ToString(); } }

    private NativeControlSession(Process process)
    {
        _process = process;
        _stderr = DrainErrorsAsync();
    }

    public static Task<NativeControlSession> StartAsync(int gamePid, string nativeDirectory, CancellationToken cancellationToken = default)
    {
        if (gamePid <= 0) throw new ArgumentOutOfRangeException(nameof(gamePid));
        var injector = Path.GetFullPath(Path.Combine(nativeDirectory, "ccz_injector.exe"));
        var library = Path.GetFullPath(Path.Combine(nativeDirectory, "ccz_control.dll"));
        foreach (var path in new[] { injector, library }) if (!File.Exists(path)) throw new FileNotFoundException("缺少游戏控制组件。", path);
        var start = new ProcessStartInfo(injector);
        start.ArgumentList.Add("--server");
        start.ArgumentList.Add(gamePid.ToString(CultureInfo.InvariantCulture));
        start.ArgumentList.Add(library);
        return StartHelperAsync(start, TimeSpan.FromSeconds(10), cancellationToken);
    }

    internal static async Task<NativeControlSession> StartHelperAsync(ProcessStartInfo start, TimeSpan timeout, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        start.UseShellExecute = false; start.CreateNoWindow = true;
        start.RedirectStandardInput = start.RedirectStandardOutput = start.RedirectStandardError = true;
        start.StandardOutputEncoding = start.StandardErrorEncoding = Encoding.ASCII;
        var process = Process.Start(start) ?? throw new IOException("无法启动游戏控制组件。");
        var session = new NativeControlSession(process);
        try
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            deadline.CancelAfter(timeout);
            var ready = await process.StandardOutput.ReadLineAsync(deadline.Token).ConfigureAwait(false);
            if (ready != "READY") throw new IOException("游戏控制组件未就绪。");
            return session;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        { await session.DisposeAsync(); throw new TimeoutException("启动游戏控制组件超时。"); }
        catch { await session.DisposeAsync(); throw; }
    }

    public Task ExecuteAsync(NativeRequest request, CancellationToken cancellationToken = default) => ExecuteAsync(request, request.Timeout, cancellationToken);

    public static async Task SelectSlotOnceAsync(int gamePid, string nativeDirectory, int slot, CancellationToken cancellationToken)
    {
        _ = NativeRequest.SelectSave(slot).Encode();
        var start = new ProcessStartInfo(Path.GetFullPath(Path.Combine(nativeDirectory, "ccz_injector.exe")))
        { UseShellExecute = false, CreateNoWindow = true, RedirectStandardError = true, RedirectStandardOutput = true, RedirectStandardInput = true };
        start.ArgumentList.Add(gamePid.ToString(CultureInfo.InvariantCulture));
        start.ArgumentList.Add(Path.GetFullPath(Path.Combine(nativeDirectory, "ccz_control.dll")));
        start.ArgumentList.Add("list"); start.ArgumentList.Add((slot - 1).ToString(CultureInfo.InvariantCulture));
        cancellationToken.ThrowIfCancellationRequested();
        await using var session = new NativeControlSession(Process.Start(start) ?? throw new IOException("无法启动存档控制组件。"));
        var output = DrainOutputAsync(session._process.StandardOutput);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(25));
        try
        {
            await session._process.WaitForExitAsync(deadline.Token).ConfigureAwait(false);
            await output.ConfigureAwait(false); await session._stderr.ConfigureAwait(false);
            if (session._process.ExitCode != 0) throw new NativeControlException(unchecked((uint)session._process.ExitCode), session.Diagnostics);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        { throw new TimeoutException("存档控制响应超时。"); }
        finally { session.Close(); await output.ConfigureAwait(false); }
    }

    private static async Task DrainOutputAsync(StreamReader reader)
    {
        var buffer = new char[2048];
        while (await reader.ReadAsync(buffer).ConfigureAwait(false) > 0) { }
    }

    internal async Task ExecuteAsync(NativeRequest request, TimeSpan timeout, CancellationToken cancellationToken = default)
    {
        var line = request.Encode();
        await _requests.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(Volatile.Read(ref _closed) != 0, this);
            cancellationToken.ThrowIfCancellationRequested();
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            deadline.CancelAfter(timeout);
            try
            {
                await _process.StandardInput.WriteLineAsync(line.AsMemory(), deadline.Token).ConfigureAwait(false);
                await _process.StandardInput.FlushAsync(deadline.Token).ConfigureAwait(false);
                var response = await _process.StandardOutput.ReadLineAsync(deadline.Token).ConfigureAwait(false);
                if (!uint.TryParse(response, NumberStyles.None, CultureInfo.InvariantCulture, out var result)) throw new IOException("游戏控制组件响应无效或已退出。");
                if (result != 0) throw new NativeControlException(result, Diagnostics);
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            { Close(); throw new TimeoutException("游戏控制响应超时，需要重新创建游戏会话。"); }
            // An interrupted command may already have executed. Never resend it or reuse a late reply.
            catch { Close(); throw; }
        }
        finally { _requests.Release(); }
    }

    private async Task DrainErrorsAsync()
    {
        var buffer = new char[2048];
        try
        {
            int count;
            while ((count = await _process.StandardError.ReadAsync(buffer).ConfigureAwait(false)) > 0)
                lock (_diagnostics)
                {
                    _diagnostics.Append(buffer, 0, count);
                    if (_diagnostics.Length > 16384) _diagnostics.Remove(0, _diagnostics.Length - 16384);
                }
        }
        catch (IOException) { }
        catch (ObjectDisposedException) { }
    }

    private void Close()
    {
        if (Interlocked.Exchange(ref _closed, 1) != 0) return;
        try { if (!_process.HasExited) _process.Kill(); }
        catch (InvalidOperationException) { }
    }

    public async ValueTask DisposeAsync()
    {
        Close();
        await _requests.WaitAsync().ConfigureAwait(false);
        try
        {
            if (!_disposed)
            {
                await _process.WaitForExitAsync().ConfigureAwait(false);
                await _stderr.ConfigureAwait(false);
                _process.Dispose(); _disposed = true;
            }
        }
        finally { _requests.Release(); }
        // Keep the small synchronization objects valid for callers already queued during disposal.
    }
}
