using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

internal static class RuntimePreferencesTests
{
    public static void Run()
    {
        var directory = Path.Combine(Path.GetTempPath(), "ccz-preferences-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var settingsPath = Path.Combine(directory, "location.txt");
            var game = Path.Combine(directory, "game"); Directory.CreateDirectory(game);
            File.WriteAllText(Path.Combine(game, "Ekd5.exe"), "test executable marker");
            var portable = Path.Combine(game, "wpf"); Directory.CreateDirectory(portable);
            GameDirectorySettings.Remember(game, settingsPath);
            if (GameDirectorySettings.Discover(portable, settingsPath: settingsPath) != game || GameDirectorySettings.Discover(directory, settingsPath: settingsPath) != game)
                throw new Exception("未识别父游戏目录或记住的游戏目录");
            if (GameDirectorySettings.Discover(directory, directory, settingsPath) != directory) throw new Exception("环境覆盖未优先");
            var brokenRule = Path.Combine(directory, "random_rules_v2.json"); File.WriteAllText(brokenRule, "[]");
            var store = new RuleDocumentStore();
            try { store.Load(brokenRule); throw new Exception("损坏规则没有被拒绝"); } catch (InvalidDataException) { }
            if (store.Path is not null || File.ReadAllText(brokenRule) != "[]" || store.ActiveProfile is null) throw new Exception("损坏规则未安全保留");
            var path = Path.Combine(directory, "randomizer_settings.json");
            // Same shape as the inspected game settings, plus an unrelated setting to preserve.
            var old = """{"version":1,"loopRandom":false,"concurrency":1,"compatibilityMode":false,"gameVersion":"2.10","audioMuteRecoveryVersion":2}""";
            File.WriteAllText(path, old);
            if (RuntimePreferences.Load(directory) != new RuntimePreferences()) throw new Exception("旧运行参数读取不一致");
            var edited = new RuntimePreferences(7, 3, true, true); edited.Save(directory);
            if (RuntimePreferences.Load(directory) != edited) throw new Exception("运行参数没有持久化");
            var data = JsonNode.Parse(File.ReadAllText(path))!;
            if (data["audioMuteRecoveryVersion"]!.GetValue<int>() != 2 || data["gameVersion"]!.GetValue<string>() != "2.2" || File.ReadAllText(path + ".bak") != old) throw new Exception("旧字段或备份丢失");
            File.WriteAllText(path, "[]");
            try { edited.Save(directory); throw new Exception("覆盖了损坏的运行参数"); } catch (InvalidDataException) { }
            if (File.ReadAllText(path) != "[]") throw new Exception("损坏文件未保留");
        }
        finally { Directory.Delete(directory, true); }
    }
}
