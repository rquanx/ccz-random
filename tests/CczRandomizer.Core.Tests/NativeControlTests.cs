using System.Diagnostics;
using CczRandomizer.Wpf.Core;

internal static class NativeControlTests
{
    // A deterministic helper implements the actual seven-field native server protocol.
    public static void Helper(string mode)
    {
        if (mode == "startup-timeout") { Thread.Sleep(30000); return; }
        Console.WriteLine("READY");
        while (Console.ReadLine() is { } line)
        {
            if (mode == "timeout") { Thread.Sleep(30000); return; }
            if (mode == "eof") return;
            if (mode == "noise") Console.Error.Write(new string('x', 50000));
            Console.WriteLine(mode == "error" ? "207" : line == "37 0 0 0 0 0 19" ? "0" : "65");
        }
    }

    private static ProcessStartInfo Start(string mode)
    {
        var start = new ProcessStartInfo(Environment.ProcessPath!);
        if (Path.GetFileNameWithoutExtension(start.FileName).Equals("dotnet", StringComparison.OrdinalIgnoreCase)) start.ArgumentList.Add(typeof(NativeControlTests).Assembly.Location);
        start.ArgumentList.Add("--native-test-helper"); start.ArgumentList.Add(mode);
        return start;
    }
    public static async Task Run()
    {
        if (NativeRequest.SilentClick(123, 369, 234).Encode() != "22 123 369 234 0 0 0") throw new Exception("原生点击协议布局错误");
        await using (var session = await NativeControlSession.StartHelperAsync(Start("noise"), TimeSpan.FromSeconds(5)))
        {
            await Task.WhenAll(Enumerable.Range(0, 4).Select(_ => session.ExecuteAsync(NativeRequest.TitleLoad(20))));
            if (session.Diagnostics.Length > 16384) throw new Exception("控制组件日志内存未限制");
        }
        await Expect<TimeoutException>(async () => { await using var session = await NativeControlSession.StartHelperAsync(Start("startup-timeout"), TimeSpan.FromMilliseconds(200)); });
        foreach (var mode in new[] { "timeout", "error", "eof" })
        {
            await using var session = await NativeControlSession.StartHelperAsync(Start(mode), TimeSpan.FromSeconds(5));
            if (mode == "timeout") await Expect<TimeoutException>(() => session.ExecuteAsync(NativeRequest.TitleLoad(20), TimeSpan.FromMilliseconds(200)));
            else if (mode == "error") await Expect<NativeControlException>(() => session.ExecuteAsync(NativeRequest.TitleLoad(20)));
            else await Expect<IOException>(() => session.ExecuteAsync(NativeRequest.TitleLoad(20)));
            await Expect<ObjectDisposedException>(() => session.ExecuteAsync(NativeRequest.TitleLoad(20)));
        }
        await using (var session = await NativeControlSession.StartHelperAsync(Start("timeout"), TimeSpan.FromSeconds(5)))
        {
            using var cancel = new CancellationTokenSource(200);
            await Expect<OperationCanceledException>(() => session.ExecuteAsync(NativeRequest.TitleLoad(20), cancel.Token));
        }
    }
    private static async Task Expect<T>(Func<Task> action) where T : Exception
    {
        try { await action(); } catch (T) { return; }
        throw new Exception($"预期 {typeof(T).Name}");
    }
}
