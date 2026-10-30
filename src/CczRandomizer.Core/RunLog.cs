using System.Text;

namespace CczRandomizer.Wpf.Core;

/// <summary>Bounded diagnostics. No per-frame or per-person logging.</summary>
public sealed class RunLog
{
    private readonly object _gate = new();
    private readonly int _maximumBytes;
    public string Path { get; }
    public RunLog(string gameDirectory, int maximumBytes = 2 * 1024 * 1024)
    {
        _maximumBytes = maximumBytes;
        var directory = System.IO.Path.Combine(gameDirectory, "ccz_fast_logs");
        Directory.CreateDirectory(directory);
        Path = System.IO.Path.Combine(directory, $"fast_{DateTime.Now:yyyyMMdd_HHmmss}_inspection_wpf_{Environment.ProcessId}.log");
    }
    public void Write(string message, Exception? error = null)
    {
        lock (_gate)
        {
            try
            {
                var line = $"{DateTimeOffset.Now:O} {message}{(error is null ? "" : "\n" + error)}\n";
                if (error is NativeControlException native) line += native.Diagnostics + "\n";
                if (error is not null)
                    foreach (System.Collections.DictionaryEntry entry in error.Data) line += $"{entry.Key}: {entry.Value}\n";
                if (line.Length > _maximumBytes / 4) line = line[..(_maximumBytes / 4)] + "\n[truncated]\n";
                var bytes = Encoding.UTF8.GetBytes(line);
                if (File.Exists(Path) && new FileInfo(Path).Length + bytes.Length > _maximumBytes)
                {
                    var stem = System.IO.Path.ChangeExtension(Path, null);
                    for (var i = 2; i >= 1; i--)
                    {
                        var previous = i == 1 ? Path : stem + $".part{i - 1}.log";
                        if (File.Exists(previous)) File.Move(previous, stem + $".part{i}.log", true);
                    }
                }
                using var output = new FileStream(Path, FileMode.Append, FileAccess.Write, FileShare.Read);
                output.Write(bytes);
            }
            catch (Exception failure) when (failure is IOException or UnauthorizedAccessException) { /* Diagnostics cannot hide the operation's original failure. */ }
        }
    }
}
