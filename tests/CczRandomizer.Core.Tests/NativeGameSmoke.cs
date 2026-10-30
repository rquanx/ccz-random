using System.Diagnostics;
using System.Security.Cryptography;
using CczRandomizer.Wpf.Core;

internal static class NativeGameSmoke
{
    // Explicit opt-in only: starts and removes an isolated copy, never attaches to the user's game.
    public static async Task Run(string gameDirectory, string nativeDirectory)
    {
        var source = Path.Combine(gameDirectory, "SV", "SV020.E5S");
        var before = SHA256.HashData(File.ReadAllBytes(source));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        var sandbox = new GameSandboxService().Create(gameDirectory, cancellation: timeout.Token);
        GameProcessSession? owned = null;
        Exception? failure = null;
        try
        {
            owned = await GameProcessSession.StartAsync(sandbox, nativeDirectory, timeout.Token);
            var game = owned.Process;
            while (true)
            {
                timeout.Token.ThrowIfCancellationRequested(); game.Refresh();
                if (game.HasExited) throw new Exception($"隔离游戏提前退出：{game.ExitCode}");
                if (owned.Windows.Main != IntPtr.Zero) break;
                await Task.Delay(100, timeout.Token);
            }
            var controller = owned.Controller;
            await controller.ExecuteAsync(new NativeRequest(9), timeout.Token);
            using var memory = new ProcessMemoryReader(game.Id);
            while (true)
            {
                timeout.Token.ThrowIfCancellationRequested();
                try
                {
                    var people = PersonnelMemoryReader.Read(memory, [0, 1, 6], false, new HashSet<int>());
                    if (!people.Select(x => x.Name).SequenceEqual(new[] { "曹操", "夏侯惇", "夏侯渊" })) throw new Exception("真实游戏人物内存校验失败");
                    break;
                }
                catch (InvalidDataException) { await Task.Delay(100, timeout.Token); }
            }
            var interaction = new GameInteraction(game.Id, nativeDirectory, memory, controller, owned.Windows);
            await interaction.LoadAsync(Path.Combine(sandbox, "SV", "SV020.E5S"), 20, true, timeout.Token);
            var jobs = await interaction.RandomizeAsync(timeout.Token);
            var catalog = RecruitmentCatalog.Load(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(nativeDirectory))!, "resources/data/recruitment/recruits_2.2.json"));
            var indices = FixedEntryCatalog.CreateRows().Concat(catalog.People).Select(x => x.RecordIndex).ToArray();
            var fixedJobs = catalog.People.Where(x => x.FixedConfiguration).Select(x => x.RecordIndex).ToHashSet();
            string Capture() => System.Text.Json.JsonSerializer.Serialize(PersonnelMemoryReader.Read(memory, indices, true, fixedJobs));
            var result = Path.Combine(sandbox, "SV", "SV001.E5S");
            await interaction.SaveAsync(result, 1, timeout.Token);
            var expectedPeople = Capture(); // The first save can complete additional story talent assignments.
            var expectedEquipment = EquipmentMemoryReader.Capture(memory);
            await interaction.SaveAsync(result, 1, timeout.Token); // Exercise the game's overwrite confirmation.
            await interaction.LoadAsync(Path.Combine(sandbox, "SV", "SV020.E5S"), 20, false, timeout.Token);
            await interaction.RandomizeAsync(timeout.Token);
            await interaction.LoadAsync(result, 1, false, timeout.Token);
            if (Capture() != expectedPeople) throw new Exception("保存读回后人物兵种或天赋发生变化");
            if (!System.Text.Json.Nodes.JsonNode.DeepEquals(expectedEquipment, EquipmentMemoryReader.Capture(memory))) throw new Exception("保存读回后宝物信息发生变化");
            Console.WriteLine($"Isolated game smoke passed: source load, randomization ({string.Join(',', jobs)}), save/overwrite, 130-person readback and source reload/reroll.");
        }
        catch (Exception error)
        {
            failure = error;
            foreach (System.Collections.DictionaryEntry item in error.Data) Console.Error.WriteLine($"{item.Key}: {item.Value}");
            throw;
        }
        finally
        {
            if (owned is not null) await owned.DisposeAsync();
            for (var attempt = 0; attempt < 20; attempt++)
            {
                try { GameSandboxService.Remove(sandbox); break; }
                catch (Exception error) when (attempt < 19 && error is IOException or UnauthorizedAccessException) { await Task.Delay(100); }
                catch (Exception error) when (failure is not null && error is IOException or UnauthorizedAccessException) { Console.Error.WriteLine($"Sandbox retained after failure: {sandbox}"); }
            }
            if (!SHA256.HashData(File.ReadAllBytes(source)).SequenceEqual(before)) throw new Exception("源存档发生变化");
        }
    }
}
