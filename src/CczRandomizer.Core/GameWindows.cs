using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace CczRandomizer.Wpf.Core;

public sealed record GameWindow(nint Handle, string ClassName, string Title, bool Visible);

/// <summary>All window operations are restricted to one owned game process.</summary>
public sealed class GameWindows(int processId, nint desktop = 0)
{
    public IReadOnlyList<GameWindow> Snapshot()
    {
        var windows = new List<GameWindow>();
        EnumCallback callback = (window, _) =>
        {
            if (BelongsToGame(window)) windows.Add(new(window, Class(window), Title(window), IsWindowVisible(window)));
            return true;
        };
        if (desktop == 0) EnumWindows(callback, 0);
        else if (!EnumDesktopWindows(desktop, callback, 0) && Marshal.GetLastWin32Error() is var error && error != 0) throw new Win32Exception(error);
        return windows;
    }
    public nint Main => Snapshot().FirstOrDefault(x => x.ClassName == "SOUSOU")?.Handle ?? 0;
    public nint ListDialog => Snapshot().FirstOrDefault(x => x.ClassName == "#32770" && x.Visible && HasList(x.Handle))?.Handle ?? 0;
    public bool Exists(nint window) => window != 0 && BelongsToGame(window);
    public bool Enabled(nint window) => Exists(window) && IsWindowEnabled(window);
    public bool HasList(nint window) => Exists(window) && FindWindowEx(window, 0, "SysListView32", null) != 0;
    public uint NativeHandle(nint window)
    {
        Require(window);
        return checked((uint)(nuint)window);
    }
    public void Menu(nint window, int command)
    {
        if (command is not (101 or 102)) throw new ArgumentOutOfRangeException(nameof(command));
        Post(window, 0x0111, (nuint)command);
    }
    public void ConfirmAlerts(nint main, nint listDialog)
    {
        Require(main);
        foreach (var dialog in Snapshot().Where(x => x.Visible && x.ClassName == "#32770" && x.Handle != listDialog && !HasList(x.Handle)))
        {
            if (GetAncestor(dialog.Handle, 3) != main) continue;
            var buttons = new List<nint>();
            EnumChildWindows(dialog.Handle, (child, _) =>
            {
                if (BelongsToGame(child) && Class(child) == "Button" && IsWindowVisible(child) && IsWindowEnabled(child)) buttons.Add(child);
                return true;
            }, 0);
            // Match the original game confirmation labels, never click an unrelated/unknown alert.
            var button = buttons.FirstOrDefault(x => new[] { "是", "确定", "确认", "OK", "Yes" }.Contains(Title(x)));
            if (button != 0) Post(button, 0x00F5, 0);
        }
    }
    private void Post(nint window, uint message, nuint parameter)
    {
        Require(window);
        if (!PostMessage(window, message, parameter, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    private bool BelongsToGame(nint window) { GetWindowThreadProcessId(window, out var pid); return pid == processId; }
    private void Require(nint window) { if (!Exists(window)) throw new IOException("游戏窗口已关闭或归属发生变化。"); }
    private static string Class(nint window) { var text = new StringBuilder(256); GetClassName(window, text, text.Capacity); return text.ToString(); }
    private static string Title(nint window) { var text = new StringBuilder(512); GetWindowText(window, text, text.Capacity); return text.ToString(); }
    private delegate bool EnumCallback(nint window, nint parameter);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumCallback callback, nint parameter);
    [DllImport("user32.dll", SetLastError = true)] private static extern bool EnumDesktopWindows(nint desktop, EnumCallback callback, nint parameter);
    [DllImport("user32.dll")] private static extern bool EnumChildWindows(nint parent, EnumCallback callback, nint parameter);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint window, out int pid);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(nint window);
    [DllImport("user32.dll")] private static extern bool IsWindowEnabled(nint window);
    [DllImport("user32.dll")] private static extern nint GetAncestor(nint window, uint flags);
    [DllImport("user32.dll", EntryPoint = "GetClassNameW", CharSet = CharSet.Unicode)] private static extern int GetClassName(nint window, StringBuilder text, int length);
    [DllImport("user32.dll", EntryPoint = "GetWindowTextW", CharSet = CharSet.Unicode)] private static extern int GetWindowText(nint window, StringBuilder text, int length);
    [DllImport("user32.dll", EntryPoint = "FindWindowExW", CharSet = CharSet.Unicode)] private static extern nint FindWindowEx(nint parent, nint after, string className, string? title);
    [DllImport("user32.dll", EntryPoint = "PostMessageW", SetLastError = true)] private static extern bool PostMessage(nint window, uint message, nuint parameter, nint value);
}
