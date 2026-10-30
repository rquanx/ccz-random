using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

static class RuleImportTests
{
    public static void Run()
    {
        foreach (var file in new[] { "export.json", "full-config.json" })
        {
            var payload = (JsonObject)JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "rules_210", file)))!;
            foreach (var mode in new[] { "three", "seven" })
            {
                var original = payload.ToJsonString();
                var config = RuleDefaults.NewConfig();
                var before = config.ToJsonString();
                var result = RuleImporter.Import(config, payload, mode);
                var profile = result.Config["profiles"]![result.Names[0]]!;
                Check(profile["threePerson"]!["minJobAverage"]!.GetValue<double>() == (mode == "three" ? 8.1 : 7.3), "生效门槛错误");
                var names = profile["threePerson"]!["qualifiedMembers"]!.AsArray().Select(x => x!.GetValue<string>()).ToHashSet();
                Check(names.SetEquals(mode == "three" ? ["曹操"] : new[] { "曹仁", "曹洪" }), "生效人物错误");
                Check(profile["skillQualification"]!["threshold"]!.GetValue<double>() == 9, "特技门槛丢失");
                Check(profile["sevenPerson"]!["skillBaseScores"]!["先手攻击"]!.GetValue<double>() == 6, "特技自定义分数丢失");
                Check(profile["sevenPerson"]!["skillTypeOverrides"]!["先手攻击"]!.GetValue<string>() == "NONE", "特殊档免匹配未转换");
                Check(!profile["sevenPerson"]!["highJobAutoPass"]!.GetValue<bool>(), "旧版自动通过未关闭");
                Check(before == config.ToJsonString() && original == payload.ToJsonString(), "导入改变输入文件");
                var second = RuleImporter.Import(result.Config, RuleImporter.Export(result.Config, result.Names));
                Check(second.Names[0] == result.Names[0] + "(1)", "同名规则被覆盖");
                Check(JsonNode.DeepEquals(profile, second.Config["profiles"]![second.Names[0]]), "再次导入改变规则");
            }
            try { RuleImporter.Import(RuleDefaults.NewConfig(), payload); throw new Exception("未确认旧版模式就导入"); } catch (LegacyModeRequiredException) { }
            var allPayload = (JsonObject)payload.DeepClone();
            foreach (var entry in allPayload["profiles"]!.AsObject()) entry.Value!["sevenPerson"]!["jobQualificationMode"] = "all";
            var allResult = RuleImporter.Import(RuleDefaults.NewConfig(), allPayload, "seven");
            var allStage = allResult.Config["profiles"]![allResult.Names[0]]!["threePerson"]!;
            Check(allStage["jobQualificationMode"]!.GetValue<string>() == "count" && allStage["minQualifiedCount"]!.GetValue<int>() == 7 && allStage["qualifiedMembers"]!.AsArray().Count == 7, "旧版全部七人达标没有转换为明确人数");
        }
        var v1 = JsonNode.Parse("""{"version":1,"activeProfile":"旧规则","profiles":{"旧规则":{"threePerson":{"minJobAverage":8.1},"sevenPerson":{"minJobAverage":7.2,"lowMinEffectiveSkills":11}}}}""")!.AsObject();
        var imported = RuleImporter.Import(RuleDefaults.NewConfig(), v1, "seven");
        Check(imported.Config["profiles"]!["旧规则"]!["skillQualification"]!["threshold"]!.GetValue<double>() == 11, "v1 特技门槛错误");
        var temp = Path.Combine(Path.GetTempPath(), "ccz-import-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try
        {
            var file = Path.Combine(temp, "rules.json");
            Check(RuleImporter.ReadLegacyMode(file) is null, "无配置时猜测模式");
            File.WriteAllText(Path.Combine(temp, "randomizer_settings.json"), "{\"randomMode\":\"seven\"}", new System.Text.UTF8Encoding(true));
            Check(RuleImporter.ReadLegacyMode(file) == "seven", "BOM 配置未识别");
            var store = new RuleDocumentStore();
            Check(store.Load(file), "无法初始化新规则");
            store.Save();
            store.CopyProfile("测试副本");
            store.Save();
            var copy = (JsonObject)store.ActiveProfile.DeepClone();
            copy["threePerson"]!["minJobAverage"] = 9;
            store.ReplaceActiveProfile(copy);
            store.Save();
            var loaded = new RuleDocumentStore();
            loaded.Load(file);
            Check(loaded.ActiveProfileName == "测试副本", "规则选择未持久化");
            Check(loaded.ActiveProfile["threePerson"]!["minJobAverage"]!.GetValue<double>() == 9, "规则修改丢失");
            loaded.SelectProfile("默认规则");
            Check(loaded.ActiveProfile["threePerson"]!["minJobAverage"]!.GetValue<double>() == 7.4, "副本修改污染内置规则");
            try { loaded.DeleteActiveProfile(); throw new Exception("允许删除内置规则"); } catch (InvalidOperationException) { }
            loaded.SelectProfile("测试副本");
            loaded.RenameActiveProfile("重命名副本"); loaded.Save();
            var renamed = new RuleDocumentStore(); renamed.Load(file);
            Check(renamed.ActiveProfileName == "重命名副本" && !renamed.ProfileNames.Contains("测试副本") && renamed.ActiveProfile["threePerson"]!["minJobAverage"]!.GetValue<double>() == 9, "重命名改变参数或没有持久化");
            loaded.ResetActiveProfile();
            Check(loaded.ActiveProfile["threePerson"]!["minJobAverage"]!.GetValue<double>() == 7.4 && !loaded.IsBuiltin, "恢复默认参数错误");
            var exported = RuleImporter.Export(loaded.Document, loaded.ProfileNames);
            Check(exported["profiles"]!.AsObject().Count == 2, "批量导出丢失规则");
            loaded.DeleteActiveProfile();
            loaded.Save();
            Check(loaded.ProfileNames.SequenceEqual(["默认规则"]), "规则删除失败");
        }
        finally { Directory.Delete(temp, true); }
    }
    private static void Check(bool value, string message) { if (!value) throw new Exception(message); }
}
