using System.Buffers.Binary;
using System.Text;

namespace CczRandomizer.Wpf.Core;

public sealed record SkillDefinition(int InternalId, string DisplayName, string BaseName, byte FormatType, byte Parameter);
public sealed record MemberSkills(int RecordIndex, uint MemberId, byte JobId, IReadOnlyList<SkillDefinition> Personal, IReadOnlyList<SkillDefinition> Job);
public sealed record SkillMemorySnapshot(uint RecordArrayBase, uint RuleTableBase, bool DirectJobMatch, IReadOnlyList<SkillDefinition> Catalog, IReadOnlyList<MemberSkills> Members, byte[] RuleTable);

public static class SkillMemoryReader
{
    public const uint RecordsPointer = 0x004CEA00, RulesPointer = 0x00500C3B, DirectMatchAddress = 0x00505F68, NamesAddress = 0x004CC600;
    public const int RecordSize = 0x48, RuleCount = 255, RuleStride = 8;
    private static readonly Encoding Encoding = CreateEncoding();
    private static Encoding CreateEncoding() { System.Text.Encoding.RegisterProvider(CodePagesEncodingProvider.Instance); return System.Text.Encoding.GetEncoding("GB18030"); }
    public static string CString(ReadOnlySpan<byte> bytes) { var end = bytes.IndexOf((byte)0); return Encoding.GetString(end < 0 ? bytes : bytes[..end]); }
    public static uint ReadUInt32(IMemoryReader memory, uint address) => BinaryPrimitives.ReadUInt32LittleEndian(memory.Read(address, 4));
    public static void ValidateIndices(IReadOnlyList<int> indices) { if (indices.Count == 0 || indices.Any(i => i is < 0 or > 1023) || indices.Distinct().Count() != indices.Count) throw new ArgumentException("人物记录编号须位于 0–1023 范围内且不能重复"); }
    public static int NormalizedJob(int job) => job < 0x3C ? job / 3 : job < 0x50 ? job - 0x28 : 0x28;
    public static bool JobMatches(int entry, int job, bool direct) => direct ? entry == job : NormalizedJob(entry) == NormalizedJob(job) && entry <= job;
    public static (int[] Personal, int[] Job) Resolve(int recordIndex, byte job, byte[] rules, bool direct)
    {
        if (rules.Length != RuleCount * RuleStride) throw new InvalidDataException("天赋规则表长度错误");
        var personal = new List<int>(); var jobs = new List<int>();
        for (var id = 0; id < RuleCount; id++)
        {
            var offset = id * RuleStride;
            if (Enumerable.Range(0, 3).Any(slot => BinaryPrimitives.ReadUInt16LittleEndian(rules.AsSpan(offset + slot * 2)) == recordIndex)) personal.Add(id);
            if (JobMatches(rules[offset + 6], job, direct)) jobs.Add(id);
        }
        return (personal.ToArray(), jobs.ToArray());
    }
    public static SkillMemorySnapshot Read(IMemoryReader memory, IReadOnlyList<int> indices, IReadOnlyDictionary<int, byte>? plannedJobs = null)
    {
        ValidateIndices(indices); var recordBase = ReadUInt32(memory, RecordsPointer); var ruleBase = ReadUInt32(memory, RulesPointer);
        var rules = memory.Read(ruleBase, RuleCount * RuleStride); var direct = memory.Read(DirectMatchAddress, 1)[0] != 0;
        var records = memory.Read(recordBase, (indices.Max() + 1) * RecordSize); var names = memory.Read(NamesAddress, RuleCount * 16);
        var shorts = ReadStrings(memory.Read(0x0048EC6A, 32), 6);
        var abilities = ReadStrings(memory.Read(0x00486ADB, 48), 8);
        var all = CString(memory.Read(0x0048B3E1, 16));
        var strategies = new Dictionary<byte, string>();
        var catalog = Enumerable.Range(0, RuleCount).Select(id =>
        {
            var offset = id * 16;
            var name = CString(names.AsSpan(offset, 15));
            var format = names[offset + 15];
            var parameter = rules[id * RuleStride + 7];
            var strategy = "";
            if (format == 7 && !strategies.TryGetValue(parameter, out strategy))
                strategies[parameter] = strategy = CString(memory.Read(0x004A3E77 + (uint)(parameter * 0x61), 0x61));
            return new SkillDefinition(id, Format(name, format, parameter, shorts, abilities, all, strategy ?? ""), name, format, parameter);
        }).ToArray();
        var members = indices.Select(index => { var offset = index * RecordSize; var job = plannedJobs?.GetValueOrDefault(index, records[offset + 0x2B]) ?? records[offset + 0x2B]; var ids = Resolve(index, job, rules, direct); return new MemberSkills(index, BinaryPrimitives.ReadUInt32LittleEndian(records.AsSpan(offset + 4)), job, ids.Personal.Select(i => catalog[i]).ToArray(), ids.Job.Select(i => catalog[i]).ToArray()); }).ToArray();
        return new(recordBase, ruleBase, direct, catalog, members, rules);
    }
    public static string Format(string name, byte format, byte parameter) => format switch { 1 => $"{name} +{parameter}", 2 => $"{name} +{parameter}%", 3 => $"{name} -{parameter}%", 4 => $"{name} {parameter}%", 5 => $"{name} {parameter}", _ => name };
    private static string[] ReadStrings(byte[] data, int count)
    {
        var result = new List<string>();
        for (var start = 0; start < data.Length && result.Count < count;)
        {
            var end = Array.IndexOf(data, (byte)0, start);
            if (end < 0) break;
            result.Add(Encoding.GetString(data, start, end - start));
            start = end + 1;
        }
        return result.ToArray();
    }
    private static string Mask(int parameter, IReadOnlyList<string> names, string all, int count)
    {
        var mask = parameter & ((1 << count) - 1);
        return mask == (1 << count) - 1 ? all : string.Concat(Enumerable.Range(0, count).Where(i => (mask & (1 << i)) != 0).Select(i => names[i]));
    }
    public static string Format(string name, byte format, byte parameter, IReadOnlyList<string> shorts,
        IReadOnlyList<string> abilities, string all, string strategy = "")
    {
        if (format == 6)
        {
            var source = parameter / 16;
            var target = parameter % 16;
            if (target is 0 or 15) { source--; target += 16; }
            if (source < 0) source += shorts.Count;
            var sourceName = source < shorts.Count ? shorts[source] : source.ToString();
            return $"{name} {sourceName}→{Mask(target, shorts, all, 5)}";
        }
        return format switch
        {
            7 => $"{name} {(strategy.Length > 0 ? strategy : parameter.ToString())}",
            8 => $"{name} {(parameter < abilities.Count ? abilities[parameter] : parameter.ToString())}",
            9 or 10 => $"{name} {Mask(parameter, shorts, all, format == 9 ? 5 : 6)}",
            _ => Format(name, format, parameter)
        };
    }
    private static readonly System.Text.RegularExpressions.Regex Ignored = new(@"[\s\-—－_()（）:：+＋%％]");
    private static readonly Dictionary<string, string> Aliases = new()
    {
        ["辅助攻击格挡24"] = "辅助攻击格挡20", ["辅助全格挡18"] = "辅助全格挡16",
        ["减轻远距损伤50"] = "减轻远距损伤40", ["强化反击20"] = "强化反击15",
        ["盾反20"] = "盾反15", ["辅助连击率40"] = "辅助连击率25"
    };
    public static string Normalize(string name)
    {
        name = name.Trim();
        if (name.StartsWith("能力替换")) name = name.Replace("→", "替");
        else if (name.StartsWith("能力辅助")) name = name.Replace("→", "辅");
        name = Ignored.Replace(name, "");
        return Aliases.GetValueOrDefault(name, name);
    }
}
