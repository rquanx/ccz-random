using System.Buffers.Binary;

namespace CczRandomizer.Wpf.Core;

public sealed record PersonnelRecord(int RecordIndex, uint MemberId, string Name, byte JobId, byte CurrentJobId,
    IReadOnlyList<string> JobTalents, IReadOnlyList<string> PersonalTalents);

public static class PersonnelMemoryReader
{
    public const uint JobTableAddress = 0x00503F40;

    public static (string Name, uint MemberId, byte Job) Decode(ReadOnlySpan<byte> record, int index)
    {
        if (record.Length != SkillMemoryReader.RecordSize || BinaryPrimitives.ReadUInt32LittleEndian(record) != 0x1000u + index)
            throw new InvalidDataException($"人物记录 {index} 标识或长度错误");
        var name = SkillMemoryReader.CString(record.Slice(8, 9));
        if (name.Length == 0 || name.Any(char.IsControl)) throw new InvalidDataException($"人物记录 {index} 名称无效");
        return (name, BinaryPrimitives.ReadUInt32LittleEndian(record[4..]), record[0x2B]);
    }

    public static IReadOnlyList<PersonnelRecord> Read(IMemoryReader memory, IReadOnlyList<int> indices,
        bool planned = false, IReadOnlySet<int>? fixedIndices = null)
    {
        SkillMemoryReader.ValidateIndices(indices);
        var recordBase = SkillMemoryReader.ReadUInt32(memory, SkillMemoryReader.RecordsPointer);
        var data = memory.Read(recordBase, (indices.Max() + 1) * SkillMemoryReader.RecordSize);
        var jobs = planned ? ReadRuleJobs(memory, indices, fixedIndices) : null;
        var snapshot = SkillMemoryReader.Read(memory, indices, jobs);
        if (snapshot.RecordArrayBase != recordBase) throw new IOException("读取期间人物表变化，请重试");
        return snapshot.Members.Select(member =>
        {
            var index = member.RecordIndex;
            var record = Decode(data.AsSpan(index * SkillMemoryReader.RecordSize, SkillMemoryReader.RecordSize), index);
            var effectiveJob = jobs?.GetValueOrDefault(index, record.Job) ?? record.Job;
            if (record.MemberId != member.MemberId || effectiveJob != member.JobId) throw new IOException("读取期间人物数据变化，请重试");
            return new PersonnelRecord(index, record.MemberId, record.Name, effectiveJob, record.Job,
                member.Job.Select(s => s.DisplayName).ToArray(), member.Personal.Select(s => s.DisplayName).ToArray());
        }).ToArray();
    }

    public static IReadOnlyDictionary<int, byte> ReadRuleJobs(IMemoryReader memory, IReadOnlyList<int> indices, IReadOnlySet<int>? fixedIndices = null)
    {
        SkillMemoryReader.ValidateIndices(indices);
        var jobs = memory.Read(JobTableAddress, (indices.Max() + 1) * 4);
        var fixedJobs = indices.Where(i => fixedIndices?.Contains(i) == true).ToArray();
        var recordBase = fixedJobs.Length > 0 ? SkillMemoryReader.ReadUInt32(memory, SkillMemoryReader.RecordsPointer) : 0;
        return indices.ToDictionary(i => i, i => fixedJobs.Contains(i)
            ? Decode(memory.Read(recordBase + (uint)(i * SkillMemoryReader.RecordSize), SkillMemoryReader.RecordSize), i).Job
            : checked((byte)BinaryPrimitives.ReadUInt32LittleEndian(jobs.AsSpan(i * 4))));
    }
}
