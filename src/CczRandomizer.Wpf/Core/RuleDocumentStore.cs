using System.Text.Json;
using System.Text.Json.Nodes;
using System.IO;

namespace CczRandomizer.Wpf.Core;

public sealed class RuleDocumentStore
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    public JsonObject Document { get; private set; } = new();
    public string? Path { get; private set; }

    public bool Load(string path)
    {
        if (!File.Exists(path)) return false;
        if (JsonNode.Parse(File.ReadAllText(path)) is not JsonObject node) return false;
        Document = node; Path = path; return true;
    }

    public void SetJobThreshold(double value)
    {
        var profileName = Document["activeProfile"]?.GetValue<string>() ?? "默认规则";
        var profile = Document["profiles"]?[profileName] as JsonObject ?? throw new InvalidDataException("activeProfile 不存在");
        var three = profile["threePerson"] as JsonObject ?? new JsonObject();
        three["minJobAverage"] = value; profile["threePerson"] = three;
    }

    public void Save()
    {
        if (Path is null) throw new InvalidOperationException("规则文件尚未加载");
        File.WriteAllText(Path, Document.ToJsonString(Options));
    }
}
