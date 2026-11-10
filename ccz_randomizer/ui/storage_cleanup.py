from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ccz_randomizer.runtime.storage_cleanup import CATEGORIES, clean_storage, scan_storage
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.theme import setup_theme, style_dialog


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


def show_storage_cleanup(parent, base: Path, *, is_running=lambda: False) -> None:
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("空间清理")
    dialog.resizable(True, True)
    dialog.transient(parent)
    # Reserve the footer before laying out the content; a fixed-height window
    # otherwise clips these buttons on systems with larger fonts / DPI.
    actions = ttk.Frame(dialog, padding=(20, 8, 20, 20))
    actions.pack(fill="x", side="bottom")
    body = ttk.Frame(dialog, padding=20)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="清理工具产生的临时内容", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
    ttk.Label(body, text="保留结果图片、存档和历史记录。最近 24 小时的日志与截图、\n运行中的沙箱及无法确认归属的目录不会清理。",
              foreground="#667085").pack(anchor="w", pady=(8, 16))
    grid = ttk.Frame(body)
    grid.pack(fill="x")
    grid.columnconfigure(0, weight=1)
    for column, text in enumerate(("内容", "占用空间", "可清理", "")):
        ttk.Label(grid, text=text, foreground="#667085").grid(row=0, column=column, sticky="w", padx=8, pady=5)
    values = {}
    buttons = []
    usage = {}
    busy = False
    messages = queue.Queue()
    status = tk.StringVar(value="正在统计空间…")

    def begin(categories=None):
        nonlocal busy
        if busy:
            return
        if categories and is_running():
            status.set("请先停止随机任务，再清理空间。")
            return
        busy = True
        for button in buttons:
            button.configure(state="disabled")
        status.set("正在清理…" if categories else "正在统计空间…")

        def work():
            try:
                result = clean_storage(base, categories) if categories else None
                messages.put((scan_storage(base), result, None))
            except Exception as exc:
                messages.put((None, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    for row, (key, label) in enumerate(CATEGORIES.items(), 1):
        ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=12)
        total, available = tk.StringVar(value="—"), tk.StringVar(value="—")
        values[key] = (total, available)
        for column, variable in ((1, total), (2, available)):
            ttk.Label(grid, textvariable=variable).grid(row=row, column=column, padx=8)
        button = ttk.Button(grid, text="清理", command=lambda key=key: begin({key}))
        button.grid(row=row, column=3, padx=8)
        buttons.append(button)
    ttk.Label(body, text="沙箱共享的游戏资源不重复计入占用。", foreground="#667085").pack(anchor="w", pady=(8, 4))
    ttk.Label(body, textvariable=status, wraplength=570).pack(anchor="w", pady=4)
    refresh = ttk.Button(actions, text="刷新", command=begin)
    refresh.pack(side="left")
    clear_all = ttk.Button(actions, text="全部清理", command=lambda: begin(set(CATEGORIES)))
    clear_all.pack(side="right")
    buttons.extend((refresh, clear_all))
    timer = None

    def poll():
        nonlocal timer, busy, usage
        try:
            scanned, result, error = messages.get_nowait()
        except queue.Empty:
            pass
        else:
            busy = False
            if error:
                status.set(f"操作未完成：{error}")
            else:
                usage = scanned
                for key, (total, available) in values.items():
                    total.set(format_size(usage[key].total))
                    available.set(format_size(usage[key].cleanable))
                status.set(f"已清理 {result[0]} 个文件，{result[1]} 个文件未能清理。" if result else "统计完成，可按分类清理。")
            for button in buttons:
                button.configure(state="normal")
        timer = dialog.after(100, poll)

    def destroyed(event):
        if event.widget is dialog and timer:
            dialog.after_cancel(timer)
    dialog.bind("<Destroy>", destroyed, add="+")
    dialog.update_idletasks()
    width = max(620, dialog.winfo_reqwidth())
    height = max(370, dialog.winfo_reqheight())
    dialog.minsize(width, height)
    dialog.geometry(f"{width}x{height}")
    show_centered(dialog)
    begin()
    poll()
