"""Explain and install the independent audio patch launcher."""
from pathlib import Path
import sys
from tkinter import ttk

from ccz_randomizer.audio_patch import LAUNCHER_NAME, install_launcher
from ccz_randomizer.ui import messages
from ccz_randomizer.ui.dialog_actions import add_dialog_actions
from ccz_randomizer.ui.tasks import WindowTasks
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def launcher_resource() -> Path:
    root = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    return root / 'resources' / 'patches' / LAUNCHER_NAME


def show_audio_patch(parent, api):
    try:
        executable = Path(api.locate_game_executable())
    except Exception as error:
        messages.showerror('音效卡顿补丁', f'无法定位游戏：{error}', parent=parent)
        return
    dialog = centered_toplevel(parent)
    dialog.title('音效卡顿补丁')
    dialog.transient(parent)
    dialog.resizable(False, False)
    body = ttk.Frame(dialog, padding=22)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text=(
        '修复部分设备开启音效后在攻击、释放策略卡顿问题。\n\n'
        '补丁是独立 EXE 启动器，需要使用补丁提供的 EXE 启动游戏才能生效。\n'
        f'点击“使用补丁”将 {LAUNCHER_NAME} 放入游戏目录。\n'
        f'以后请双击 {LAUNCHER_NAME} 启动游戏。\n\n'
        f'游戏目录：{executable.parent}'
    ), wraplength=540, justify='left').pack(fill='x')
    status = ttk.Label(body, text='')
    status.pack(fill='x', pady=(12, 0))
    actions = ttk.Frame(body)
    actions.pack(fill='x', pady=(16, 0))
    tasks = WindowTasks(dialog, serial=True)

    def close():
        if tasks.pending:
            return
        dialog.destroy()
        if parent.winfo_exists():
            parent.grab_set()

    def finished(result, error=False):
        for button in buttons.values():
            button.configure(state='normal')
        status.configure(text='')
        if error:
            messages.showerror('音效卡顿补丁', str(result), parent=dialog)
        else:
            messages.showinfo('音效卡顿补丁',
                f'启动器已准备好：\n{result}\n\n请使用 {LAUNCHER_NAME} 启动游戏。', parent=dialog)

    def install():
        if tasks.pending:
            return
        for button in buttons.values():
            button.configure(state='disabled')
        status.configure(text='正在安装启动器…')
        tasks.request('install', lambda: install_launcher(executable, launcher_resource()),
                      finished, lambda error: finished(error, True), durable=True)

    buttons = add_dialog_actions(actions, confirm=install, confirm_text='使用补丁', cancel=close)
    dialog.protocol('WM_DELETE_WINDOW', close)
    dialog.bind('<Escape>', lambda _: close())
    show_centered(dialog)
    dialog.grab_set()
    return dialog
