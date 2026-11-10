# 弹窗定位

工具自绘的普通弹窗使用 `centered_toplevel(parent)` 创建，完成控件、最小尺寸和最终尺寸设置后，调用 `show_centered(dialog)`，再设置模态抓取或等待关闭。构建过程保持 withdrawn 和透明，不依赖第一次 Map 或定时器推断布局是否完成。

Windows 下使用同一线程 DPI 上下文中的原生 API：

- `GetAncestor(GA_ROOT)` 获取 Tk 客户区外层的真实窗口。
- `MonitorFromWindow` 选择父窗口所在显示器；`GetMonitorInfoW.rcWork` 提供扣除任务栏的工作区。
- `GetWindowRect` 测量包含标题栏、边框的外框，`SetWindowPos` 移动，保持大小、激活和堆叠状态。
- 不混用 DWM 的物理坐标，也不额外乘除缩放比例，不修改正式程序的 DPI 感知设置。

初始窗口超出工作区时，缩小客户区并仅在必要时降低最小尺寸。跨屏移动引起尺寸改变时最多补定位一次。不绑定永久 Configure 监听，不改变用户后续拖动、缩放和恢复窗口的位置。

原生定位失败时退回 Tk 屏幕定位；即使退回定位也失败，仍恢复窗口可见。诊断信息进入日志，不增加用户控制台输出。非 Windows 环境使用 Tk 退回路径。

下拉列表、悬浮提示、toast 继续靠近对应控件；Windows 原生文件选择、确认框由系统管理，不安装全局窗口钩子。

## 验证

`tests/unit/test_window_position.py` 覆盖工作区偏移、负坐标副屏、DPI 尺寸变化、完整构建后显示、外框中心、恢复后保留用户位置、固定窗口的小屏适配、异常可见性、销毁清理、实际业务窗口和重命名模态输入。

设备诊断可逐个验证当前连接的所有显示器，并输出坐标报告：

```powershell
.\.venv-win10-py314\Scripts\python.exe tools/diagnostics/smoke_window_position.py --dpi current --output artifacts/window-placement-current.json
.\.venv-win10-py314\Scripts\python.exe tools/diagnostics/smoke_window_position.py --dpi system --output artifacts/window-placement-system.json
.\.venv-win10-py314\Scripts\python.exe tools/diagnostics/smoke_window_position.py --dpi per-monitor --output artifacts/window-placement-per-monitor.json
```

诊断只创建自己的窗口；各 DPI 模式在独立诊断进程中设置，不改变游戏、工具或操作系统的显示配置。
