"""Explicit install and restore actions for the experimental growth patch."""
from pathlib import Path
import os
import sys
import tkinter as tk
from tkinter import ttk

from ccz_randomizer import growth_patch
from ccz_randomizer.ui import messages
from ccz_randomizer.ui.dialog_actions import add_dialog_actions
from ccz_randomizer.ui.tasks import WindowTasks
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def package_path() -> Path:
    root = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    return root / 'resources' / 'patches' / growth_patch.PACKAGE_NAME


def show_growth_patch(parent, api, *, is_running=lambda: False):
    try:
        configured = os.environ.get('CCZ_GAME_EXE')
        local = Path(configured) if configured else api.app_dir() / 'Ekd5.exe'
        executable = local if local.is_file() or growth_patch.backup_path(local).is_file() else api.locate_game_executable()
    except Exception as error:
        messages.showerror('吃桃补丁', f'无法定位游戏：{error}', parent=parent)
        return
    dialog = centered_toplevel(parent)
    dialog.title('吃桃补丁')
    dialog.transient(parent)
    dialog.resizable(False, False)
    body = ttk.Frame(dialog, padding=22)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text=(
        f'补丁将替换 {executable.name}，支持高编号人物吃桃、喝酒。\n\n'
        '补丁尚未充分测试，是否适用于当前游戏请自行判断。\n'
        f'使用前会自动将原 EXE 重命名为 {growth_patch.backup_path(executable).name}，\n'
        '然后安装补丁 EXE 和 CCZFX.DLL。点击“还原”可回退原 EXE。\n\n'
        '请先关闭游戏并停止随机。还原不会恢复已变化的存档或成长数据。\n'
        f'游戏位置：{executable.parent}'
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

    def run(restore):
        if tasks.pending:
            return
        if is_running():
            messages.showwarning('吃桃补丁', '请先停止随机，再使用或还原补丁。', parent=dialog)
            return
        for button in buttons.values():
            button.configure(state='disabled')
        status.configure(text='正在还原…' if restore else '正在安装…')

        def work():
            if api.find_process_ids(executable.name):
                raise ValueError('请先关闭游戏，再使用或还原补丁。')
            return growth_patch.restore_patch(executable) if restore else growth_patch.install_patch(executable, package_path())

        def finished(message, error=False):
            for button in buttons.values():
                button.configure(state='normal')
            status.configure(text='')
            (messages.showerror if error else messages.showinfo)('吃桃补丁', str(message), parent=dialog)

        tasks.request('patch', work, finished, lambda error: finished(error, True), durable=True)

    buttons = add_dialog_actions(actions, confirm=lambda: run(False), confirm_text='使用补丁',
                                 alternatives=(('还原', lambda: run(True)),), cancel=close)
    dialog.protocol('WM_DELETE_WINDOW', close)
    dialog.bind('<Escape>', lambda _: close())
    show_centered(dialog)
    dialog.grab_set()
    return dialog
