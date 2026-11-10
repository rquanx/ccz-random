# 测试说明

测试分为两组，默认只运行不会启动游戏的单元测试。

## 非游戏测试

```powershell
.\.venv-win10-py314\Scripts\python.exe run_tests.py unit
```

Windows 上会在独立桌面运行，不切换用户桌面。测试会捕获后台线程、Tk 回调、
对象析构异常和未恢复的环境变量，不能只看断言通过。Tk 循环对象在主线程回收。
可验证顺序独立性，或只运行指定模块：

```powershell
.\.venv-win10-py314\Scripts\python.exe run_tests.py unit --order reverse
.\.venv-win10-py314\Scripts\python.exe run_tests.py unit --order shuffle --seed 20261110
.\.venv-win10-py314\Scripts\python.exe run_tests.py unit tests.unit.test_turbo
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
不属于当前应用默认回归范围。三人/七人旧读档探针、silent-real-flow 和
start-game-loop 均保留为手动诊断。

新增默认项 normal-save-readback、turbo-save-readback、turbo-fallback-readback：
通过实际运行适配器完成三轮筛选和菜单保存，每个存档重新启动游戏读回，
比较全部人物兵种和特技；回退 case 还验证丢弃首次 NPC 输入后只回退一次。

所有 case 串行运行，每个 case 使用短路径完整游戏副本，不与源目录建立硬链接。
测试只修改副本，case 之间也不复用修改后的副本。复制需要额外临时磁盘空间。
Windows Job 在执行 case 前登记所属进程，退出/超时时仅清理其进程树（包括非游戏 worker），
不会按 Ekd5.exe 名称清理用户实例。单个 case 默认最多运行 300 秒，可用 --timeout 调整。
独立旧诊断使用的 GameFileBackup 仍只保护约定文件，不是完整游戏备份；还原失败会保留备份路径。
native-ui-load 仅检查读档前后的前台窗口相同，不代表已验证中途焦点或鼠标完全不变。

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
