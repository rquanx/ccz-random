using System.Text.Json.Nodes;
using System.IO;

namespace CczRandomizer.Wpf;

public sealed class RuleStore
{
    public string? FilePath { get; private set; }
    public JsonObject Document { get; private set; } = new();

    public bool TryLoad(string? baseDirectory = null)
    {
        var candidates = new[] { Environment.GetEnvironmentVariable("CCZ_GAME_DIR"), baseDirectory, AppContext.BaseDirectory }
            .Where(path => !string.IsNullOrWhiteSpace(path));
        foreach (var directory in candidates)
        {
            var path = Path.Combine(directory!, "random_rules_v2.json");
            if (!File.Exists(path)) continue;
            try
            {
                if (JsonNode.Parse(File.ReadAllText(path)) is not JsonObject node) continue;
                Document = node; FilePath = path; return true;
            }
            catch (System.Text.Json.JsonException) { }
        }
        return false;
    }

    public string ActiveProfileName => Document["activeProfile"]?.GetValue<string>() ?? "默认规则";
    public JsonObject ActiveProfile => Document["profiles"]?[ActiveProfileName] as JsonObject ?? new();
    public IReadOnlyList<string> QualifiedMembers => ActiveProfile["threePerson"]?["qualifiedMembers"]?.AsArray()
        .Select(node => node?.GetValue<string>() ?? string.Empty).Where(name => name.Length > 0).ToArray() ?? [];
    public double JobThreshold => ActiveProfile["threePerson"]?["minJobAverage"]?.GetValue<double>() ?? 0;
    public string JobMode => ActiveProfile["threePerson"]?["jobQualificationMode"]?.GetValue<string>() ?? "average";
}
