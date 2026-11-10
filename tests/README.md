# 测试说明

测试分为两组，默认只运行不会启动游戏的单元测试。

## 非游戏测试

```powershell
.\.venv-win10-py314\Scripts\python.exe run_tests.py unit
```

这组测试覆盖规则、界面逻辑、工作流状态、异常恢复决策、日志转换和
游戏文件备份恢复。`tests/unit/test_workflow.py` 使用 Mock 回调模拟随机
不合格、合格、停止、异常重启和重启后再次失败，不创建游戏进程。

## 完整游戏测试

先查看可运行的 case：

```powershell
.\.venv-win10-py314\Scripts\python.exe run_tests.py list-game
```

只运行指定 case：

```powershell
.\.venv-win10-py314\Scripts\python.exe run_tests.py game `
  --confirm-game --case native-ui-load
```

完整游戏测试必须显式增加 `--confirm-game`。测试前应关闭手动打开的游戏。
不指定 `--case` 时运行生产回归用例；诊断探针和耗时基准用例在
`list-game` 中标为“手动”，需要通过 `--case` 明确选择。
当前应用入口固定采用三人起步、自选人物筛选的流程；`result-save-stage`
验证实际游戏菜单保存。旧七人剧情推进和候选存档检查仅作为历史引擎诊断保留，
不属于当前应用默认回归范围。`randomizer-seven-normal-load` 只验证七个内存位置的
读档复位，不代表应用仍提供七人模式。
所有 case 串行运行，测试套件会统一备份并恢复 `SV/*.E5S` 和
`RS/S_00.eex`，包括删除测试期间新增的存档。单个 case 默认最多运行
300 秒，可用 `--timeout` 调整。

测试打包 EXE 的多实例流程时，隔离副本应使用较短的临时目录，避免在已隔离的游戏副本外
再叠加较长目录。2026-11-06 实测中，较长嵌套测试路径触发了启动失败与回退；
同一 EXE 在短目录下可正常双实例运行。回退成功和并发成功应分别记录，
并发须确认两个测试实例实际同时运行，不能计入用户自行打开的游戏进程。
循环调度器收到停止请求后正常收尾返回 `0`，其被中断的 Worker 可返回 `130`，
测试不能将两者混为一谈。

每轮记录写入：

```text
artifacts/game-tests/YYYY-MM-DD HH.mm.ss/
```

目录中包含每个 case 的 `case.json`、标准输出、错误输出、运行前后前台
窗口和鼠标坐标，以及测试期间新增的日志、诊断文件和截图。真实游戏中
发现的新状态应脱敏后放入 `tests/fixtures/`，再补充为非游戏回归测试。
