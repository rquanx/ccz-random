# 曹操传加强版 2.2 随机工具

正式客户端使用 C# / WPF，目标框架为 .NET 10 Windows。游戏控制复用 C 原生组件；运行不需要 Python 或另行安装 .NET。

## 使用

在游戏目录打开 `2.2随机工具-WPF.lnk`。发布文件夹需要整体保留，不能只移动 EXE。源存档为第 20 栏，结果使用第 1–15 栏；工具保存被替换栏位的备份。规则文件为 `random_rules_v2.json`，历史和结果继续使用游戏目录中的原数据。

## 开发与发布

```powershell
dotnet build CczRandomizer.slnx -c Release
dotnet run --project tests/CczRandomizer.Core.Tests -c Release
dotnet run --project tests/CczRandomizer.Wpf.Tests -c Release
./tools/windows/publish-wpf.ps1 -GameDirectory 'E:/game/ccz/曹操传加强版2.2'
```

构建前需要现有 `native` 控制组件二进制；源码和原构建工具仍在仓库中。发布脚本使用独立版本目录，保留旧版以便回退。Python 源码仅作为历史实现和评分对照/夹具生成工具保留，不是新客户端的运行依赖。

详细架构、发布方式与验收边界见 [迁移说明](docs/wpf-migration.md) 和 [验收记录](docs/wpf-parity.md)。
