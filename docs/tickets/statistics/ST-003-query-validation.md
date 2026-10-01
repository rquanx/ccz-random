# ST-003 统计查询服务与完整性校验

## 目标

提供与 UI 无关的统计查询、聚合和校验服务。

## 查询接口

```python
get_summary(filters)
get_job_distribution(filters)
get_personal_skill_distribution(filters)
get_job_skill_distribution(filters)
get_treasure_distribution(filters)
get_failure_distribution(filters)
get_trend(filters)
get_detail_rows(filters)
validate_statistics(filters)
```

## 统计口径

- `final`: `status = accepted AND save_confirmed = 1 AND published = 1`。
- `completed`: `scored = 1`。
- `attempts`: 所有尝试记录。
- 默认历史查询只统计最终保留结果。
- 不同 `rule_snapshot_hash` 默认分组；只有选择“全部规则汇总”时才跨规则合并。
- 跨规则汇总必须返回规则数量和样本数量。
- 默认规则筛选为“全部规则汇总”，并显示跨规则汇总标识。
- 异常、停止、未完成不进入合格率分母。

## 校验规则

- 兵种总数等于已统计武将位置总数。
- 多天赋总数等于数组元素总数。
- 宝物特性总数等于已识别特性元素总数。
- 未知项包含在总数中。
- 3 人、7 人使用正确分母。
- 循环中间结果不重复进入最终口径。
- 规则分组中的样本数、分母和合格率独立计算。
- 跨规则汇总与规则分组的结果不能混淆。
- 技能和宝物特性聚合使用展开索引，不逐行解析快照 JSON。
- 总览状态按 `(run_id, round_id, slot)` 的最后一次有效状态去重；
  失败原因、明细和分布按照当前口径保留尝试级数据。

## 验收标准

- 相同筛选条件在所有 Tab 返回一致的总数。
- 合格率分母正确。
- 未知类别可查询到具体存档。
- 校验失败返回具体不一致项，而不是静默修正。
- UI 不需要拼接 SQL。
- `current_run/current_round` 没有上下文时返回可识别的空状态或禁用筛选，
  不得隐式查询最近运行。
- 总览状态和已完成数按存档任务去重，不能按 attempts 行数直接计数。
- `all_summary` 与 `all_grouped` 必须使用同一基础样本集；
  分组样本数之和应与汇总样本数一致。

## 测试

- 三种口径聚合测试。
- 循环轮次去重测试。
- 3 人和 7 人分母测试。
- 未知项计数测试。
- 合格率和失败原因测试。
- 同名不同规则配置的隔离统计测试。
- 全部规则分组及并列比较测试。
- 全部规则汇总与分组样本数守恒测试。
- 原始快照和查询索引一致性测试。
- 旧版 legacy 导入数据不计入虚构的失败次数测试。
- 宝物特性索引数量、unknown 项守恒、快照与索引的 ID/name 一致性测试。
- 总览去重结果与明细/失败原因尝试级结果不混淆的回归测试。
