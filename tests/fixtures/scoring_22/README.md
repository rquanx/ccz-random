# C# 特技评分对照夹具

由 `python -m tools.diagnostics.export_wpf_scoring_fixtures` 生成。

人物与天赋来自 `personnel_22/randomized-personnel.json` 前两名真实人物；兵种类型来自现有 `JOB_MAP`。规则变化覆盖既有功能：人数/平均/总分门槛、类型匹配、独立分数及旧分档迁移、实际特技名称的标点别名。

预期结果调用现有 Python `migrate_skill_scores`、`skill_types_match` 和 `evaluate_skill_rules` 计算，包含总分、人物分数及逐条特技是否计分。C# 对每组逐项比对，不依赖运行 Python 或游戏。

`resources/data/rules/defaults_2.2.json` 同样来自现有 `skill_defaults.py` 和 `jobs.py`，作为 C# 嵌入资源发布，无 Python 运行时依赖。
