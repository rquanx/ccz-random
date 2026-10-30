using System.Text.Json;
using System.Text.Json.Nodes;
using System.IO;

namespace CczRandomizer.Wpf.Core;

public sealed class RuleDocumentStore
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    public JsonObject Document { get; private set; } = RuleDefaults.NewConfig();
    public string? Path { get; private set; }
    private byte[]? _loadedBytes;
    public RuleDocumentStore CreateDraft() => new()
    {
        Document = (JsonObject)Document.DeepClone(), Path = Path, _loadedBytes = _loadedBytes?.ToArray()
    };
    public IReadOnlyList<string> ProfileNames => Document["profiles"]!.AsObject().Select(x => x.Key).ToArray();
    public string ActiveProfileName => Document["activeProfile"]!.GetValue<string>();
    public bool IsBuiltin => ActiveProfile["builtin"]?.GetValue<bool>() == true;
    public void RenameActiveProfile(string name)
    {
        if (IsBuiltin) throw new InvalidOperationException("内置规则不能重命名");
        name = name.Trim();
        if (name == ActiveProfileName) return;
        var profiles = Document["profiles"]!.AsObject();
        if (name.Length == 0 || profiles.ContainsKey(name)) throw new ArgumentException("规则名称为空或已存在");
        var profile = ActiveProfile;
        profiles.Remove(ActiveProfileName); profiles[name] = profile; SelectProfile(name);
    }
    public void ResetActiveProfile()
    {
        if (IsBuiltin) throw new InvalidOperationException("内置规则不能修改，请先复制");
        var profile = RuleDefaults.NewProfile(); profile["builtin"] = false;
        ReplaceActiveProfile(profile);
    }
    public void SelectProfile(string name)
    {
        if (Document["profiles"]?[name] is not JsonObject) throw new ArgumentException("规则不存在");
        Document["activeProfile"] = name;
    }
    public string CopyProfile(string name)
    {
        name = name.Trim();
        if (name.Length == 0 || Document["profiles"]![name] is not null) throw new ArgumentException("规则名称为空或已存在");
        var profile = (JsonObject)ActiveProfile.DeepClone();
        profile["builtin"] = false;
        Document["profiles"]![name] = profile;
        SelectProfile(name);
        return name;
    }
    public void DeleteActiveProfile()
    {
        if (ActiveProfile["builtin"]?.GetValue<bool>() == true) throw new InvalidOperationException("内置规则不能删除");
        var profiles = Document["profiles"]!.AsObject();
        if (profiles.Count == 1) throw new InvalidOperationException("至少保留一套规则");
        profiles.Remove(ActiveProfileName);
        Document["activeProfile"] = profiles.First().Key;
    }
    public IReadOnlyList<string> Import(JsonObject payload, string? mode = null)
    {
        var result = RuleImporter.Import(Document, payload, mode);
        Document = result.Config;
        SelectProfile(result.Names[0]);
        return result.Names;
    }
    public void RestoreDraft(JsonObject config) => Document = (JsonObject)config.DeepClone();
    public void ReplaceActiveProfile(JsonObject profile)
    {
        var name = Document["activeProfile"]!.GetValue<string>();
        Document["profiles"]![name] = profile.DeepClone();
    }
    public JsonObject ActiveProfile => Document["profiles"]?[Document["activeProfile"]!.GetValue<string>()] as JsonObject
        ?? throw new InvalidDataException("当前规则不存在");

    public void SetGates(string jobMode, double jobThreshold, int jobCount,
        string skillMode, double skillThreshold, int skillCount)
    {
        static void Validate(string mode, double threshold, int count, int selectionCount, bool skill)
        {
            if (mode is not ("count" or "average" or "total")) throw new ArgumentException("未知算分模式");
            if (!double.IsFinite(threshold) || threshold < 0 || threshold > (skill ? 100000 : mode == "total" ? 2600 : 20))
                throw new ArgumentException("合格分超出范围");
            if (mode == "count" && (count < 1 || count > selectionCount)) throw new ArgumentException("达标人数不能超过所选人物数量");
        }
        var profile = ActiveProfile;
        var selectionCount = profile["threePerson"]!["qualifiedMembers"]!.AsArray().Count;
        Validate(jobMode, jobThreshold, jobCount, selectionCount, false);
        Validate(skillMode, skillThreshold, skillCount, selectionCount, true);
        var job = (JsonObject)profile["threePerson"]!;
        job["jobQualificationMode"] = jobMode; job["minJobAverage"] = jobThreshold; job["minQualifiedCount"] = jobCount;
        profile["skillQualification"] = new JsonObject { ["mode"] = skillMode, ["threshold"] = skillThreshold, ["requiredCount"] = skillCount };
    }

    public bool Load(string path)
    {
        if (!File.Exists(path))
        {
            Document = RuleDefaults.NewConfig(); Path = System.IO.Path.GetFullPath(path); _loadedBytes = null;
            return true;
        }
        var bytes = File.ReadAllBytes(path);
        if (JsonNode.Parse(bytes) is not JsonObject node) throw new InvalidDataException("规则文件必须是 JSON 对象");
        if (node["version"]?.GetValue<int>() != 2 || node["activeProfile"] is not JsonValue active ||
            node["profiles"]?[active.GetValue<string>()] is not JsonObject) throw new InvalidDataException("规则文件格式或当前规则无效");
        var selected = node["profiles"]![active.GetValue<string>()]!["threePerson"]?["qualifiedMembers"];
        if (selected is not JsonArray people || people.Count == 0 || people.Any(x => x is not JsonValue value || !value.TryGetValue<string>(out var name) || string.IsNullOrWhiteSpace(name)))
            throw new InvalidDataException("规则文件中的参与人物无效");
        Document = node; Path = System.IO.Path.GetFullPath(path); _loadedBytes = bytes; return true;
    }

    public void SetJobThreshold(double value)
    {
        if (!double.IsFinite(value) || value < 0) throw new ArgumentOutOfRangeException(nameof(value));
        var profileName = Document["activeProfile"]?.GetValue<string>() ?? "默认规则";
        var profile = Document["profiles"]?[profileName] as JsonObject ?? throw new InvalidDataException("activeProfile 不存在");
        var three = profile["threePerson"] as JsonObject ?? new JsonObject();
        var maximum = three["jobQualificationMode"]?.GetValue<string>() == "total" ? 20 * 130 : 20;
        if (value > maximum) throw new ArgumentOutOfRangeException(nameof(value));
        three["minJobAverage"] = value;
        if (three.Parent is null) profile["threePerson"] = three;
    }

    public void SetQualifiedMembers(IEnumerable<string> members)
    {
        var selected = members.ToArray();
        if (selected.Length == 0 || selected.Any(string.IsNullOrWhiteSpace) || selected.Distinct().Count() != selected.Length)
            throw new ArgumentException("至少选择一名人物且不能重复");
        var profileName = Document["activeProfile"]?.GetValue<string>() ?? "默认规则";
        var profile = Document["profiles"]?[profileName] as JsonObject ?? throw new InvalidDataException("activeProfile 不存在");
        var three = profile["threePerson"] as JsonObject ?? new JsonObject();
        three["qualifiedMembers"] = new JsonArray(selected.Select(member => JsonValue.Create(member)).ToArray());
        if (three.Parent is null) profile["threePerson"] = three;
    }

    public void Save()
    {
        if (Path is null) throw new InvalidOperationException("规则文件尚未加载");
        if (_loadedBytes is null ? File.Exists(Path) : !File.Exists(Path) || !File.ReadAllBytes(Path).SequenceEqual(_loadedBytes))
            throw new IOException("规则文件已被其他程序修改，请重新加载后保存");
        var bytes = System.Text.Encoding.UTF8.GetBytes(Document.ToJsonString(Options));
        var temporary = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(Path)!, ".random_rules_v2.json." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { stream.Write(bytes); stream.Flush(true); }
            // Preserve the previous complete file for recovery; replacement stays on one volume.
            if (_loadedBytes is null) File.Move(temporary, Path);
            else File.Replace(temporary, Path, Path + ".bak");
            _loadedBytes = bytes;
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
