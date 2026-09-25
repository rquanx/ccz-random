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
所有 case 串行运行，测试套件会统一备份并恢复 `SV/*.E5S` 和
`RS/S_00.eex`，包括删除测试期间新增的存档。单个 case 默认最多运行
300 秒，可用 `--timeout` 调整。

每轮记录写入：

```text
artifacts/game-tests/YYYY-MM-DD HH.mm.ss/
```

目录中包含每个 case 的 `case.json`、标准输出、错误输出、运行前后前台
窗口和鼠标坐标，以及测试期间新增的日志、诊断文件和截图。真实游戏中
发现的新状态应脱敏后放入 `tests/fixtures/`，再补充为非游戏回归测试。
