"""Reusable personnel selection, with fresh draft state on every opening."""
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.cached_dialog import hide_dialog, restore_dialog
from ccz_randomizer.ui.dialog_actions import add_dialog_actions
from ccz_randomizer.ui.member_pages import MemberCheckGrid, MemberPages
from ccz_randomizer.ui.theme import setup_theme, style_dialog
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui import messages


def show_member_picker(parent, names, selected, on_confirm, *, cache_key, title,
                       description, follow_mode=None, empty_message='请至少选择一名参与判断的人物。'):
    names = tuple(names)
    cache = getattr(parent, '_ccz_member_pickers', None)
    if cache is None:
        cache = parent._ccz_member_pickers = {}
    existing = cache.get(cache_key)
    signature = (names, follow_mode is not None)
    if existing is not None and existing.winfo_exists():
        if existing._picker_signature == signature:
            if not getattr(existing, '_ccz_cached_closed', False):
                existing.lift()
                return existing
            existing._reload_picker(selected, on_confirm, follow_mode)
            restore_dialog(existing, modal=True)
            return existing
        existing.destroy()

    dialog = centered_toplevel(parent)
    cache[cache_key] = dialog
    dialog._picker_signature = signature
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title(title)
    dialog.geometry('760x430' if follow_mode is not None else '840x380')
    dialog.transient(parent)
    frame = tk.Frame(dialog, padx=18, pady=16)
    frame.pack(fill='both', expand=True)
    tk.Label(frame, text=description, anchor='w').pack(fill='x', pady=(0, 10))
    mode = tk.StringVar(dialog, value=follow_mode or 'custom')
    selected = set(selected)
    values = {name: tk.BooleanVar(dialog, value=name in selected) for name in names}
    callback = [on_confirm]
    previous_grab = [parent.grab_current()]
    if follow_mode is not None:
        modes = tk.Frame(frame)
        modes.pack(fill='x', pady=(0, 12))
        for value, label in (('selected', '跟随评分人物'), ('custom', '单独选择人物')):
            ttk.Radiobutton(modes, text=label, variable=mode, value=value,
                            command=lambda: pages.refresh()).pack(side='left', padx=(0, 16))
    render = MemberCheckGrid(values, columns=6, state=lambda: 'normal' if mode.get() == 'custom' else 'disabled')
    pages = MemberPages(frame, names, render, page_size=24, reuse_widgets=True)
    pages.pack(fill='both', expand=True)
    actions = tk.Frame(frame)
    actions.pack(fill='x', pady=(14, 0))

    def close():
        hide_dialog(dialog)
        previous = previous_grab[0]
        if previous is not None and previous.winfo_exists():
            previous.grab_set()

    def reload(selected, on_confirm, follow_mode):
        callback[0] = on_confirm
        previous_grab[0] = parent.grab_current()
        chosen = set(selected)
        for name, variable in values.items():
            value = name in chosen
            if variable.get() != value:
                variable.set(value)
        mode.set(follow_mode or 'custom')
        pages.query.set('')
        pages.page = 0
        pages.refresh()
    dialog._reload_picker = reload

    def select_all(value):
        mode.set('custom')
        for variable in values.values():
            if variable.get() != value:
                variable.set(value)
        pages.refresh()

    def confirm():
        chosen = [name for name in names if values[name].get()]
        if mode.get() == 'custom' and not chosen:
            messages.showwarning('至少选择一人', empty_message, parent=dialog)
            return
        callback[0](mode.get(), chosen)
        close()

    ttk.Button(actions, text='全选', command=lambda: select_all(True)).pack(side='left')
    ttk.Button(actions, text='清空选择', command=lambda: select_all(False)).pack(side='left', padx=8)
    add_dialog_actions(actions, confirm=confirm, cancel=close)
    dialog.protocol('WM_DELETE_WINDOW', close)
    dialog.bind('<Escape>', lambda event: close())
    show_centered(dialog)
    dialog.lift()
    dialog.grab_set()
    return dialog
