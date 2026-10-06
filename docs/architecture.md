# 项目结构

生产代码统一放在 `ccz_randomizer` 包中，根目录只保留运行入口、测试入口和历史导入兼容层。

```text
ccz_randomizer/
  app.py                  应用组合层、游戏会话、结果图和主窗口
  rules/
    config.py             规则模型、读写、校验和评分
    editor.py             规则编辑窗口
  runtime/
    concurrent.py         多实例 Worker、动态任务队列和兼容模式回退
    game_sandbox.py       游戏运行目录隔离、发布和清理
    loader.py             原版工具运行时加载
    s00_guard.py          第一关剧情文件替换事务与恢复
    scratch_save_guard.py 临时存档保护和候选存档原样发布
  ui/
    concurrent_console.py 多实例进度状态模型和控制台渲染
  workflow/
    randomization.py      与游戏无关的随机流程状态机
    round_archive.py      循环随机单轮结果工作区和原子归档
packaging/                PyInstaller 打包配置
resources/
  app/                    运行时图片和剧情辅助文件
  data/                   研究得到的兵种、特技和宝物数据
  icons/                  程序图标
  legacy/                 历史测试版使用的二进制模板
tools/
  diagnostics/            游戏流程和内存诊断脚本
  research/               数据提取、反汇编和映射生成脚本
  legacy/                 已停止使用的实验实现
  windows/                Windows 辅助脚本
```

## 依赖方向

- `workflow` 不依赖界面和游戏运行时，可直接进行单元测试。
- `rules.config` 不依赖界面；`rules.editor` 只依赖规则配置。
- `runtime` 负责运行时加载、游戏目录隔离、多实例调度和磁盘状态保护。
- `ui` 负责可独立测试的界面状态模型；不直接控制游戏进程。
- `workflow` 负责随机流程和循环结果归档，不依赖具体窗口实现。
- `app` 组合上述模块，并暂时负责 Windows 原生控制、游戏检查、结果输出和
  主窗口。它仍是较大的组合层，后续只做有回归测试覆盖的渐进拆分，不进行
  一次性重写。

根目录的 `fast_randomizer.py`、`rule_config.py`、`rule_editor.py`、
`runtime_loader.py` 和 `random_workflow.py` 是兼容入口。新增代码应直接从
`ccz_randomizer` 包导入。工具脚本从仓库根目录使用模块方式运行，例如：

```powershell
python -m tools.diagnostics.analyze_skill_storage --help
```

## 入口

- 开发运行：`python fast_randomizer.py`
- 单元测试：`python run_tests.py unit`
- 正式版打包：`python -m PyInstaller --noconfirm packaging/CCZ_真实随机内存快筛版.spec`
