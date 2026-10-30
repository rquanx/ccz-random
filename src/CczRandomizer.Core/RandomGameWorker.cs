using System.Text.Json;
using System.Text.Json.Nodes;

namespace CczRandomizer.Wpf.Core;

public sealed record GameSnapshot(IReadOnlyList<PersonnelRecord> People, IReadOnlyList<JobTalentCard> Jobs, JsonObject Equipment)
{
    public static GameSnapshot Capture(IMemoryReader memory)
    {
        var catalog = RecruitmentCatalog.Bundled;
        var indices = FixedEntryCatalog.CreateRows().Concat(catalog.People).Select(x => x.RecordIndex).ToArray();
        var fixedJobs = catalog.People.Where(x => x.FixedConfiguration).Select(x => x.RecordIndex).ToHashSet();
        return new(PersonnelMemoryReader.Read(memory, indices, true, fixedJobs),
            JobTalentCatalog.Capture(SkillMemoryReader.Read(memory, [0])), EquipmentMemoryReader.Capture(memory));
    }
    public bool SameAs(GameSnapshot other) =>
        JsonSerializer.Serialize(People) == JsonSerializer.Serialize(other.People) &&
        JsonSerializer.Serialize(Jobs) == JsonSerializer.Serialize(other.Jobs) && JsonNode.DeepEquals(Equipment, other.Equipment);
}

public sealed record SavedCandidate(string Path, GameSnapshot Snapshot);
public sealed class GameReloadException(Exception inner) : IOException("当前游戏实例无法稳定重新读档。", inner);
public interface IRandomGameWorker : IAsyncDisposable
{
    Task ResetAsync();
    Task<GameSnapshot> RollAsync(CancellationToken cancellationToken);
    Task<SavedCandidate> SaveAndVerifyAsync(int slot, CancellationToken cancellationToken);
}

public sealed class RandomGameWorker : IRandomGameWorker
{
    private readonly string _sandbox;
    private readonly string _nativeDirectory;
    private GameProcessSession? _session;
    private ProcessMemoryReader? _memory;
    private GameInteraction? _interaction;
    private bool _loaded;
    private bool _disposed;
    private RandomGameWorker(string sandbox, string nativeDirectory) { _sandbox = sandbox; _nativeDirectory = nativeDirectory; }
    public static async Task<IRandomGameWorker> CreateAsync(string gameDirectory, string nativeDirectory, int worker, CancellationToken cancellationToken)
    {
        var sandbox = await Task.Run(() => new GameSandboxService().Create(gameDirectory, workerName: $"worker-{worker}", cancellation: cancellationToken), cancellationToken);
        return new RandomGameWorker(sandbox, nativeDirectory);
    }
    private async Task StartAsync(CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (_session is not null) return;
        _session = await GameProcessSession.StartAsync(_sandbox, _nativeDirectory, cancellationToken);
        _memory = new ProcessMemoryReader(_session.Process.Id);
        _interaction = new(_session.Process.Id, _nativeDirectory, _memory, _session.Controller, _session.Windows);
        _loaded = false;
    }
    public async Task<GameSnapshot> RollAsync(CancellationToken cancellationToken)
    {
        await StartAsync(cancellationToken);
        try { await _interaction!.LoadAsync(Path.Combine(_sandbox, "SV/SV020.E5S"), 20, !_loaded, cancellationToken); }
        catch (Exception error) when (_loaded && error is IOException or TimeoutException) { throw new GameReloadException(error); }
        _loaded = true;
        await _interaction.RandomizeAsync(cancellationToken);
        return GameSnapshot.Capture(_memory!);
    }
    public async Task<SavedCandidate> SaveAndVerifyAsync(int slot, CancellationToken cancellationToken)
    {
        if (!_loaded || _interaction is null) throw new InvalidOperationException("尚未完成随机。");
        var path = Path.Combine(_sandbox, "SV", $"SV{slot:000}.E5S");
        await _interaction.SaveAsync(path, slot, cancellationToken);
        var expected = GameSnapshot.Capture(_memory!);
        // Loading a result consumes this session on some clients. Always verify in a fresh game.
        await StopSessionAsync();
        try
        {
            await StartAsync(cancellationToken);
            await _interaction!.LoadAsync(path, slot, true, cancellationToken);
            var actual = GameSnapshot.Capture(_memory!);
            if (!expected.SameAs(actual)) throw new InvalidDataException("存档读回后的兵种、天赋或宝物信息不一致。");
            return new(path, actual);
        }
        finally { await StopSessionAsync(); }
    }
    private async Task StopSessionAsync()
    {
        _memory?.Dispose(); _memory = null; _interaction = null; _loaded = false;
        var session = _session; _session = null;
        if (session is not null) await session.DisposeAsync();
    }
    public Task ResetAsync() => StopSessionAsync();
    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        _disposed = true;
        try { await StopSessionAsync(); }
        finally
        {
            for (var attempt = 0; ; attempt++)
            {
                try { GameSandboxService.Remove(_sandbox); break; }
                catch (Exception error) when (attempt < 19 && error is IOException or UnauthorizedAccessException)
                { await Task.Delay(100); }
            }
        }
    }
}
