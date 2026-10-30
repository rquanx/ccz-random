# C# WPF 迁移

目标框架 `net10.0-windows`。应用运行使用 C# Core、WPF、SQLite 和现有 C 原生控制组件，不调用 Python。Python 代码保留作为迁移行为基准与开发夹具导出工具。

- `src/CczRandomizer.Core`：内存读取、评分、沙箱、游戏会话、随机服务、结果发布、历史和清理。
- `src/CczRandomizer.Wpf`：主窗口、规则编辑、信息卡片、历史详情和后台 PNG 导出。
- `tests/CczRandomizer.Core.Tests`、`tests/CczRandomizer.Wpf.Tests`：可执行回归测试，用 `dotnet run --project ... -c Release`，不是 `dotnet test`。

构建：`dotnet build CczRandomizer.slnx -c Release`。

独立发布：`dotnet publish src/CczRandomizer.Wpf/CczRandomizer.Wpf.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -o artifacts/wpf-portable`。

发布目录必须整体保留，包括 native 子目录与 .NET 运行时。使用目录发布避免单文件自解压产生额外运行时缓存。

发布并部署：`./tools/windows/publish-wpf.ps1 -GameDirectory 'E:/game/ccz/曹操传加强版2.2'`。

脚本创建带时间戳的独立版本目录，并更新游戏目录的 `2.2随机工具-WPF.lnk`。不覆盖旧 EXE，不改规则或存档。程序从父目录识别游戏位置，继续使用 `random_rules_v2.json`、原历史库及运行偏好。版本目录内的 `.ccz-wpf-release` 标记用于防止把整个运行时复制到随机沙箱。

完整验收证据及本机测试边界见 [wpf-parity.md](wpf-parity.md)。
