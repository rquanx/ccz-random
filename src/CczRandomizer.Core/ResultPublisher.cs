using System.Security.Cryptography;
using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

/// <summary>Archive each verified result before replacing a game result slot. Never touches slot 20.</summary>
public sealed class ResultPublisher
{
    private readonly string _gameDirectory;
    private readonly string _runId;
    private readonly Dictionary<int, string?> _expected;
    private readonly object _gate = new();
    public ResultPublisher(string gameDirectory, string runId, int count)
    {
        _gameDirectory = Path.GetFullPath(gameDirectory);
        if (runId.Any(c => !char.IsAsciiLetterOrDigit(c) && c != '-')) throw new ArgumentException("运行编号无效。", nameof(runId));
        _runId = runId;
        _expected = Enumerable.Range(1, count).ToDictionary(slot => slot, slot => Hash(Target(slot)));
    }
    private string Target(int slot) => Path.Combine(_gameDirectory, "SV", $"SV{slot:000}.E5S");
    private static string? Hash(string path) => File.Exists(path) ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant() : null;
    public JsonObject Publish(SavedCandidate candidate, JsonObject snapshot, int round)
    {
        lock (_gate) return PublishCore(candidate, snapshot, round);
    }
    private JsonObject PublishCore(SavedCandidate candidate, JsonObject snapshot, int round)
    {
        var slot = snapshot["slot"]!.GetValue<int>();
        if (slot is < 1 or > 15 || !_expected.ContainsKey(slot) || snapshot["qualified"]?.GetValue<bool>() != true)
            throw new InvalidOperationException("只能发布已验证的合格结果栏位。");
        var data = File.ReadAllBytes(candidate.Path);
        if (data.Length < GameSaveState.MemorySize) throw new InvalidDataException("结果存档不完整。");
        var hash = Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();
        var directory = Path.Combine(_gameDirectory, "randResult", _runId, $"round-{round:0000}");
        Directory.CreateDirectory(directory);
        var archive = Path.Combine(directory, $"SV{slot:000}.E5S");
        using (var output = new FileStream(archive, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { output.Write(data); output.Flush(true); }
        var result = (JsonObject)snapshot.DeepClone();
        result["save"] = new JsonObject { ["path"] = archive, ["gamePath"] = Target(slot), ["sha256"] = hash, ["verified"] = true, ["published"] = false, ["verificationError"] = "" };
        // A recoverable snapshot exists even if a later filesystem/database step fails.
        WriteMetadata(result);
        var target = Target(slot);
        if (Hash(target) != _expected[slot]) throw new IOException($"第 {slot} 栏在运行期间被其他程序修改，未覆盖游戏存档。结果副本：{archive}");
        var temporary = Path.Combine(Path.GetDirectoryName(target)!, $".ccz-{Guid.NewGuid():N}.tmp");
        try
        {
            File.WriteAllBytes(temporary, data);
            if (File.Exists(target)) File.Replace(temporary, target, Path.Combine(directory, $"previous-SV{slot:000}.E5S"));
            else File.Move(temporary, target);
            _expected[slot] = hash;
            result["save"]!["published"] = true;
            WriteMetadata(result);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        { throw new IOException($"结果发布或状态记录未完成。已验证存档保留在：{archive}。{error.Message}", error); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
        return result;
    }
    public static void WriteMetadata(JsonObject result)
    {
        var path = Path.ChangeExtension(result["save"]!["path"]!.GetValue<string>(), ".json");
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                var bytes = System.Text.Encoding.UTF8.GetBytes(result.ToJsonString()); output.Write(bytes); output.Flush(true);
            }
            File.Move(temporary, path, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
