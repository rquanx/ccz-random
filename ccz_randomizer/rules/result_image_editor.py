"""Rule-scoped selection of people shown in result images."""
from ccz_randomizer.ui.dialog_actions import add_dialog_actions
from tkinter import ttk
import tkinter as tk
from ccz_randomizer.ui import messages as messagebox
from ccz_randomizer.ui.member_pages import MemberPages
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def show_result_image_members(parent, settings, scoring_members, on_confirm):
    member_names = tuple(scoring_members)
    dialog = centered_toplevel(parent)
    dialog.title('结果图人物')
    dialog.geometry('760x490')
    dialog.transient(parent)
    frame = tk.Frame(dialog, padx=18, pady=16)
    frame.pack(fill='both', expand=True)
    mode = tk.StringVar(dialog, value=settings.get('mode', 'selected'))
    selected = set(settings.get('members') or member_names)
    values = {name: tk.BooleanVar(dialog, value=name in selected) for name in member_names}
    tk.Label(frame, text='只控制结果图展示，不改变兵种、特技评分和合格判断。', anchor='w').pack(fill='x', pady=(0, 10))
    modes = tk.Frame(frame)
    modes.pack(fill='x', pady=(0, 12))
    for value, label in [('selected', '跟随评分人物'), ('custom', '单独选择人物')]:
        tk.Radiobutton(modes, text=label, variable=mode, value=value,
                       command=lambda: pages.refresh()).pack(side='left', padx=(0, 16))

    def render(body, visible):
        for column in range(7):
            body.columnconfigure(column, weight=1)
        for index, name in enumerate(visible):
            tk.Checkbutton(body, text=name, variable=values[name], anchor='w',
                           state='normal' if mode.get() == 'custom' else 'disabled').grid(
                row=index // 7, column=index % 7, sticky='ew', padx=4, pady=4)
    pages = MemberPages(frame, member_names, render, page_size=42)
    pages.pack(fill='both', expand=True)
    actions = tk.Frame(frame)
    actions.pack(fill='x', pady=(14, 0))
    def select_all(value):
        mode.set('custom')
        for variable in values.values():
            variable.set(value)
        pages.refresh()
    ttk.Button(actions, text='全选', command=lambda: select_all(True)).pack(side='left')
    ttk.Button(actions, text='清空选择', command=lambda: select_all(False)).pack(side='left', padx=8)
    def confirm():
        chosen = [name for name in member_names if values[name].get()]
        if mode.get() == 'custom' and not chosen:
            messagebox.showwarning('至少选择一人', '请至少选择一名结果图展示人物。', parent=dialog)
            return
        on_confirm({'mode': mode.get(), 'members': chosen if mode.get() == 'custom' else settings.get('members', [])})
        dialog.destroy()
    add_dialog_actions(actions, confirm=confirm, cancel=dialog.destroy)
    show_centered(dialog)
