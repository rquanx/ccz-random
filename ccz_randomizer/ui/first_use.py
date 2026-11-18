"""One-time reminder and an explicit choice of the beginner walkthrough."""
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.theme import style_dialog
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.window_timer import window_after


def show_first_use_prompt(parent, *, acknowledge, on_beginner, on_save_failed, on_exit):
    dialog = centered_toplevel(parent)
    dialog.title('首次使用提示')
    dialog.resizable(False, False)
    dialog.transient(parent)
    style_dialog(dialog)
    dialog.protocol('WM_DELETE_WINDOW', on_exit)
    body = ttk.Frame(dialog, padding=24)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='使用前，请先阅读', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w')
    ttk.Label(body, text='1. 本工具为玩家自制，仅在 QQ 群「吕布/曹操/蜀汉交流群」\n'
              '   （656913383）发布。\n\n'
              '2. 请勿盲目追求高强度存档，避免丢失游戏乐趣。',
              justify='left').pack(anchor='w', pady=(12, 20))
    ttk.Separator(body).pack(fill='x')
    ttk.Label(body, text='你是第一次使用这个工具吗？',
              font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', pady=(16, 8))
    choice = tk.StringVar(dialog)
    ttk.Radiobutton(body, text='是，带我了解怎么用', variable=choice, value='beginner').pack(anchor='w')
    ttk.Radiobutton(body, text='不是，直接使用', variable=choice, value='experienced').pack(anchor='w', pady=(4, 0))
    ttk.Label(body, text='等待期间即可选择；新手引导可随时跳过，也能在“常见问题”中重看。',
              foreground='#667085').pack(anchor='w', pady=(10, 16))
    footer = ttk.Frame(body)
    footer.pack(fill='x')
    remaining = 5
    wait_text = tk.StringVar(dialog)
    ttk.Label(footer, textvariable=wait_text, foreground='#667085').pack(side='left')
    confirm = ttk.Button(footer, state='disabled')
    confirm.pack(side='right', padx=(12, 0))
    finished = False

    def refresh(*_):
        wait_text.set(f'请阅读提示，还需等待 {remaining} 秒' if remaining else
                      '请选择是否第一次使用' if not choice.get() else '已阅读，可以继续')
        confirm.configure(text='开始新手引导' if choice.get() == 'beginner' else '进入工具',
                          state='normal' if remaining == 0 and choice.get() else 'disabled')

    def finish():
        nonlocal finished
        if finished or remaining or not choice.get():
            return
        finished = True
        beginner = choice.get() == 'beginner'
        saved = acknowledge()
        if dialog.grab_current() is dialog:
            dialog.grab_release()
        dialog.destroy()
        # Finish the transition before reporting a persistence problem.
        if beginner:
            on_beginner()
        if not saved:
            on_save_failed()

    def tick():
        nonlocal remaining
        remaining -= 1
        refresh()
        if remaining:
            window_after(dialog, 1000, tick)

    choice.trace_add('write', refresh)
    confirm.configure(command=finish)
    refresh()
    show_centered(dialog)
    dialog.grab_set()
    confirm.focus_set()
    window_after(dialog, 1000, tick)
    return dialog
