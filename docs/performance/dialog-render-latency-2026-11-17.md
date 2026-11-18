# 弹窗内容渲染优化（4.1）

## 本轮范围

人物选择、结果图人物、人物倾向、历史及存档详情、规则评分网格、图表等弹窗。保持原来的评分、合格条件和存档逻辑。

## 改动

- 抽出可复用的人物选择窗口；首次每页 24 人（六列四行），减少原先 42 个复选框的首轮创建和绘制。保留搜索、翻页、全选、清空及跨页选择。
- 人物选择及结果图人物关闭时保留控件，重开载入当前名单、当前选择、模式与最新确认回调，清除取消的草稿、页码和搜索；名单变化时重建。关闭时恢复父窗口的模态占用。
- 复选框初始化一次传入文案、变量和状态，切页时只改变化的属性；恢复曾隐藏的选项时恢复可点击状态。
- 人物卡片保留 Canvas 文本及背景元素，滚动复用时更新内容与坐标；不再反复删除、创建整张卡片。
- 可见行绘制按 6ms 工作预算让出事件循环，取消“最多四张”的额外限制，减少很轻的卡片绘制也需要分多次定时回调的等待。
- 普通弹窗用 withdrawn 保持构建阶段不可见，取消创建及恢复时不必要的 alpha=0 切换；仍在完整尺寸、屏幕工作区定位后显示，不改变特殊聚光灯窗口的透明效果。
- 图表尺寸、数据版本与已绘制画面一致时不安排重复重绘；实际尺寸变化使用 16ms 去抖，直接绘制完成则取消旧定时器。

## 性能验收

诊断逐项检查当前可见页面的后台读取、分页搜索、分批生成、可见卡片、延迟布局、规则网格及图表绘制。隐藏页不阻塞当前页。每个操作记录 command_ms、ready_ms、within_300ms；报告保留功能 status，并新增独立 performance.status、达标数量和超时列表。功能通过不表示性能达标。

ready_ms 从操作开始，包含 Tk 事件与绘制处理，直到已登记的当前页内容工作全部完成；不是只测 Python 函数返回或 Toplevel 映射。额外 120ms 观察期仅用于捕获后续回调错误和心跳，单独不加进 ready_ms。此口径覆盖 Tk 绘制，私有 Windows 桌面仍不能证明用户交互桌面的 DWM 最终呈现时刻。网络上传、游戏和系统文件选择器使用既有离线替身或取消路径，不纳入真实外部耗时保证。

最终 EXE 性能复测与构建、单元测试串行。源码报告用于故障定位，不能和 EXE 耗时混作同一前后对照。首次打开与复用重开分别报告；有限次样本不构成所有机器和所有数据规模的 300ms 保证。

## 回归

- 完整单元测试 926 项通过，402.251 秒（artifacts/dialog-render-full-unit.log）。
- 每页 28 人中间布局及相关控件针对测试 64 项通过，40.086 秒（artifacts/dialog-render-targeted-final.log）。
- 最后增加规则评分网格内容就绪登记后，6 项针对测试通过，1.729 秒（artifacts/dialog-render-readiness-final.log）。
- 新增用例验证取消草稿丢弃、缓存重开重置搜索与页码、最新回调、目录名单改变、跟随模式、空选择保护和父窗口模态恢复。
- 新增性能口径回归：窗口已经显示但内容延迟 350ms，必须记为超过 300ms；未完成的批次不能就绪；隐藏页面不阻塞当前页；销毁清除跟踪。


最终细化：人物选择首屏调整为六列四行、24 人，人物倾向首屏 6 人、12 个下拉框；缩短小弹窗高度，进一步减少首次原生控件绘制。对应分页、搜索及跨页保存用例同步验证。

## 最终 EXE 结果

195 项功能场景通过，无 Tk 回调异常；严格口径下 164 项低于 300ms，31 项超标，performance.status=over_budget。不能宣称全部达标。此表是最终单轮 EXE 样本，不是跨设备保证；较早的28人布局构建曾测得180/195项达标，波动说明不能拿最好的一轮代替持续体验。

| 操作 | 内容就绪 ms |
| --- | ---: |
| 统计首次打开 | 430.49 |
| 历史首次打开 | 1225.31 |
| 历史销毁后重建 | 1379.76 |
| 规则首次打开 | 796.68 |
| 143人存档详情 | 1087.10 |
| 宝物信息 | 651.81 |
| 入队人员 | 352.48 |
| 人物倾向首次打开 | 370.63 |
| 人物倾向复用重开 | 146.73 |
| 结果图人物首次打开 | 376.76 |
| 结果图人物复用重开 | 157.05 |
| 普通人物选择首次打开 | 217.19 |
| 普通人物选择复用重开 | 108.37 |

完整报告：artifacts/dialog-render-exe-compact-final.json。最后24人/6人布局的16项针对测试通过，8.805秒（artifacts/dialog-render-compact-regressions.log）。后台 PrintWindow 截图：artifacts/dialog-render-profile/member-picker-final.png、affinity-final.png。

超标项：

- statistics.open.first
- statistics.members.first
- statistics.open.repeat1
- statistics.open.repeat2
- history.open.first
- history.page.next
- history.filter.rule
- history.filter.reset
- history.detail.open
- history.open.cached
- history.open.repeat
- rules.open.first
- rules.tab.1
- rules.advanced.tab.1
- effects.open.first
- effects.open.repeat
- support.open
- guide.open.first
- cleanup.open.scan
- child.history.detail.open
- child.history.all_members.open
- child.history.all_members.scroll.end
- child.history.all_members.scroll.start
- child.history.overview.open
- child.equipment.open
- child.equipment.search.reset
- child.talents.open
- child.recruitment.open
- child.affinity.open
- child.image_members.open
- child.ranking.equipment.open

已将最终4.1工具同步到游戏目录的两份工具名，旧工具已备份；压缩包及说明.txt同步更新。备份位置、哈希与构建ID见 artifacts/dialog-render-delivery.json。本轮只更新工具，不修改游戏EXE、存档及实际用户数据库，不发送通知或上传日志。
