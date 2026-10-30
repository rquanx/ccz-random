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
        var catalog = Enumerable.Range(0, RuleCount).Select(id => { var offset = id * 16; var name = CString(names.AsSpan(offset, 15)); var format = names[offset + 15]; var parameter = rules[id * RuleStride + 7]; return new SkillDefinition(id, Format(name, format, parameter), name, format, parameter); }).ToArray();
        var members = indices.Select(index => { var offset = index * RecordSize; var job = plannedJobs?.GetValueOrDefault(index, records[offset + 0x2B]) ?? records[offset + 0x2B]; var ids = Resolve(index, job, rules, direct); return new MemberSkills(index, BinaryPrimitives.ReadUInt32LittleEndian(records.AsSpan(offset + 4)), job, ids.Personal.Select(i => catalog[i]).ToArray(), ids.Job.Select(i => catalog[i]).ToArray()); }).ToArray();
        return new(recordBase, ruleBase, direct, catalog, members, rules);
    }
    public static string Format(string name, byte format, byte parameter) => format switch { 1 => $"{name} +{parameter}", 2 => $"{name} +{parameter}%", 3 => $"{name} -{parameter}%", 4 => $"{name} {parameter}%", 5 => $"{name} {parameter}", _ => name };
    public static string Normalize(string name) => name.Trim().Replace("→", "替").Replace("-", "").Replace("+", "").Replace("%", "").Replace(" ", "");
}
