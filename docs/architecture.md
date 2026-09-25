# 项目结构

生产代码统一放在 `ccz_randomizer` 包中，根目录只保留打包入口和历史导入兼容层。

```text
ccz_randomizer/
  app.py                  应用协调、游戏会话、结果图和主窗口
  rules/
    config.py             规则模型、读写、校验和评分
    editor.py             规则编辑窗口
  runtime/
    loader.py             原版工具运行时加载
  workflow/
    randomization.py      与游戏无关的随机流程状态机
```

## 依赖方向

- `workflow` 不依赖界面和游戏运行时，可直接进行单元测试。
- `rules.config` 不依赖界面；`rules.editor` 只依赖规则配置。
- `runtime` 只负责加载原版工具运行环境。
- `app` 组合上述模块，并负责 Windows 原生控制、游戏检查、结果输出和界面。

根目录的 `fast_randomizer.py`、`rule_config.py`、`rule_editor.py`、
`runtime_loader.py` 和 `random_workflow.py` 是兼容入口。旧诊断脚本仍可沿用原导入路径，
新增代码应直接从 `ccz_randomizer` 包导入。

## 入口

- 开发运行：`python fast_randomizer.py`
- 单元测试：`python run_tests.py unit`
- 打包入口：`fast_randomizer.py`

