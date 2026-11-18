# 项目文档

## 开发与数据包

- [游戏数据包格式、兼容与发布](game-profiles.md)
- [宝物采样、范围映射与统计调查](equipment/)
- [界面性能、后台测量与回归记录](performance/)
- [游戏补丁原理、安装与兼容验证](patches/)
- [新手引导、依赖诊断与防睡眠](support/)

专题目录中的日期代表调查或测试时间。记录中的结论仅覆盖当时列出的版本和测试场景，不代表已完成所有设备和游戏场景测试。

## 文件放置约定

- 正式代码放在 `ccz_randomizer/`，回归测试和必要的真实样本放在 `tests/`。
- 可重复运行的诊断、调查工具分别放在 `tools/diagnostics/`、`tools/research/`；原生补丁源码放在 `native/`。
- 游戏版本资料放在 `resources/data/profiles/`；随工具分发的补丁资源放在 `resources/patches/`。
- 构建结果、临时截图、运行日志、本地发布包和备份分别保留在已有 Git 忽略目录中，例如 `dist/`、`build/`、`artifacts/`、`.tmp/`、`release/`。这些内容不提交，也不要将备份当作普通垃圾文件删除。
