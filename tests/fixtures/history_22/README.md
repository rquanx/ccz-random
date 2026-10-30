# Python 历史库兼容夹具

`python-history.sqlite3` 由 `python -m tools.diagnostics.export_wpf_history_fixture` 调用现有 Python `HistoryRepository` 生成。

包含一条有合格结果的轮次、一条正在运行但没有结果的轮次。结果使用真实 `randomized-personnel.json` 中张宝的兵种和天赋，故意保留旧的初始人物字段，验证 C# 按评分选择恢复实际人员。

文件中的运行 ID、时间和存档路径是测试元数据，不代表用户实际运行记录。测试只对临时副本读写。生成器使用 SQLite backup，确保 WAL 内容完整合入数据库。
