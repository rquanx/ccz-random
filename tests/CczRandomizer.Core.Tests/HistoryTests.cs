using System.Text.Json.Nodes;
using CczRandomizer.Wpf.Core;

static class HistoryTests
{
    public static void Run()
    {
        var directory = Path.Combine(Path.GetTempPath(), "ccz-history-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(directory, "ccz_fast_data"));
        try
        {
            File.Copy(Path.Combine(AppContext.BaseDirectory, "history_22/python-history.sqlite3"), Path.Combine(directory, "ccz_fast_data/history.sqlite3"));
            var repository = new HistoryRepository(directory);
            Check(repository.CountRounds() == 1 && repository.ListRounds().Count == 1, "空轮次没有隐藏");
            var round = repository.ListRounds()[0];
            var snapshot = repository.GetResults(round.Id)[0];
            var before = snapshot.ToJsonString();
            var members = HistoryMembers.Resolve(snapshot);
            Check(members.Count == 1 && members[0]["name"]!.GetValue<string>() == "张宝", "错误地展示初始三人");
            Check(members[0]["personalSkills"]![0]!["name"]!.GetValue<string>() == "攻击追加 诱惑", "人物天赋恢复失败");
            Check(before == snapshot.ToJsonString(), "历史恢复修改原数据");
            repository.UpdateVerification(round.Id, 1, false, "test error");
            Check(repository.GetResults(round.Id)[0]["save"]!["verified"]!.GetValue<bool>() == false, "回读验证状态未保存");
            repository.StartRun("csharp", false, "新规则", new(), new());
            var empty = repository.StartRound("csharp", 1);
            repository.FinishRound(empty, "stopped");
            Check(repository.CountRounds() == 1, "空结果轮次被记录");
            var valid = repository.StartRound("csharp", 2);
            repository.SaveResult(valid, snapshot);
            repository.FinishRound(valid, "stopped");
            repository.FinishRun("csharp", "stopped");
            Check(repository.CountRounds() == 2 && repository.ListRounds(2, 1).Count == 1, "有合格结果的中断轮次丢失或分页失败");
            repository.DeleteRound(valid);
            Check(repository.GetResults(valid).Count == 0 && repository.CountRounds() == 1, "外键级联删除失败");
            repository.Clear(); Check(repository.CountRounds() == 0, "历史清空失败");
            var fresh = new HistoryRepository(Path.Combine(directory, "fresh"));
            fresh.StartRun("new", false, "规则", new(), new());
            var first = fresh.StartRound("new", 1); fresh.SaveResult(first, snapshot);
            Check(fresh.GetResults(first).Count == 1, "新建数据库无法读写");
        }
        finally { Directory.Delete(directory, true); }
    }
    private static void Check(bool ok, string message) { if (!ok) throw new Exception(message); }
}
