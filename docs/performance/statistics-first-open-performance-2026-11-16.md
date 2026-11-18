# 统计首次打开性能调查（2026-11-16）

## 反馈与范围

用户确认：窗口先出现，数据等待 5～6 秒；仅首次打开明显。之前独立 Tk 窗口的微基准没有覆盖完整主界面的启动后台任务，不能据此认定该问题已修复。

## 本次修改

- StatisticsRepository.query 新增 view 参数，默认 all 保持原有接口及完整统计结果。overview 不扫描人物分布、特技频率和宝物样本；members、equipment 各自读取对应详情。
- UI 首先显示总览；其他页首次切换时后台查询，同一筛选下已加载页面直接复用。改变筛选、刷新、规则更新或清理统计后使页面缓存失效。
- 查询失败保留上次图表；异步请求继续使用原有代次校验和窗口关闭取消机制。
- 所有宝物效果、兵种和特技仍显示完整的正频率列表并可滚动。

## 实测证据与局限

使用游戏目录真实数据库的只读备份，规则配置也复制到临时目录；没有修改原统计数据。完整主界面模式在启动 300ms 后打开统计，与真实 250ms 特技目录预加载竞争；关闭联网数据更新和首次使用提示。

同一轮、同一数据规模的完整主界面对照（单次新进程，各项不是稳定分位数）：

| 指标 | 全页面查询基线 | 按页查询 |
| --- | ---: | ---: |
| 总览所等待的仓库查询 | 114.65ms | 22.63ms |
| 窗口创建 | 180.91ms | 181.59ms |
| 首屏数据可见 | 558.76ms | 501.05ms |
| 最大心跳间隔 | 197.53ms | 200.16ms |

原始结果：artifacts/ui-performance/statistics-eager-main.json、statistics-lazy-main.json。基线仅模拟修改前的全页面 SQL 汇总，控件结构相同。查询减少约 80%，这轮首屏改善仅约 58ms；不能宣称将用户的 5～6 秒降低到 0.5 秒，也没有证明其他弹窗普遍加快。

实际已发布 EXE 的人工 UI 检查中，点击后约 1.5 秒的截图已出现数据。这包含 UI 自动化动作和截图开销，且检查时程序已完成启动，不能用作冷启动耗时。独立窗口早期基准约 0.4 秒，同样未复现用户的 5～6 秒。

尚未排除 EXE 首次文件加载、首次数据库迁移、系统文件缓存和启动联网任务等环境因素。后续要验证 EXE 的首次打开体验，不能仅使用源码微基准替代。本轮没有打包、替换游戏目录 EXE。

## 可重复测量

```powershell
.\.venv-win10-py314\Scripts\python.exe tools/diagnostics/benchmark_statistics_open.py --base 'E:/game/ccz/曹操传加强版v2.20-1104夜' --main-window --eager-baseline --output artifacts/ui-performance/statistics-eager-main.json
.\.venv-win10-py314\Scripts\python.exe tools/diagnostics/benchmark_statistics_open.py --base 'E:/game/ccz/曹操传加强版v2.20-1104夜' --main-window --output artifacts/ui-performance/statistics-lazy-main.json
```

## 回归验证

新增真实 recorder 夹具的页面结果对照测试，并模拟详情查询缓慢，验证总览先显示、Tk 心跳仍响应、切换后详情完整。现有 UI 测试选择相应详情页后验证筛选行为。

完整单元测试 850 项通过（.tmp/statistics-full-tests.log）。最终针对性测试另见 .tmp/statistics-final-tests.log。
