"""Small history metadata editor shared by rounds and individual saves."""
from ccz_randomizer.ui.inputs import TextEntry
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.theme import setup_theme, style_dialog


def edit_history_metadata(parent, metadata, save):
    import tkinter as tk

    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("命名与备注")
    dialog.transient(parent)
    body = tk.Frame(dialog, padx=18, pady=16)
    body.pack(fill="both", expand=True)
    title = tk.StringVar(value=metadata.get("title", ""))
    tk.Label(body, text="名称（最多 100 字）", anchor="w").pack(fill="x")
    entry = TextEntry(body, textvariable=title, width=44)
    entry.pack(fill="x", pady=(4, 12))
    tk.Label(body, text="备注（最多 1000 字，可搜索）", anchor="w").pack(fill="x")
    note = tk.Text(body, width=44, height=6, wrap="word")
    note.insert("1.0", metadata.get("note", ""))
    note.pack(fill="both", expand=True, pady=(4, 8))
    buttons = tk.Frame(body)
    buttons.pack(fill="x", pady=(12, 0))

    def submit():
        values = dict(title=title.get()[:100], note=note.get("1.0", "end-1c")[:1000])
        save(values)
        dialog.destroy()

    tk.Button(buttons, text="保存", command=submit).pack(side="right")
    tk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right", padx=8)
    show_centered(dialog)
    entry.focus_set()
