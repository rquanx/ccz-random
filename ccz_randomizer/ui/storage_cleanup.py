from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from ccz_randomizer.ui import messages as messagebox

from ccz_randomizer.runtime.storage_cleanup import CATEGORIES, clean_storage, scan_storage
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.theme import setup_theme, style_dialog
from ccz_randomizer.ui.tasks import WindowTasks

DATA_DESCRIPTIONS = {
    "results": "随机结果：结果图片和归档存档文件",
    "history": "历史记录（含存档副本）：全部轮次、备注、标记和独立存档副本",
    "statistics": "随机统计数据：全部随机观测及人物、兵种、特技和宝物统计",
    "searches": "最近搜索记录：入队人员和宝物的最近搜索关键词",
}


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


def show_storage_cleanup(parent, base: Path, *, is_running=lambda: False) -> None:
    previous_grab = parent.grab_current()
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
    ttk.Label(body, text="按数据类型管理占用空间", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
    ttk.Label(body, text="结果、历史、统计和最近搜索可分别清理；全部清理也包含这些数据。\n最近 24 小时的日志与截图、运行中的沙箱及未知文件不会清理。\n游戏原始存档、规则、设置和数据包不受影响。",
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
    cleaning = False
    status = tk.StringVar(value="正在统计空间…")

    def begin(categories=None):
        nonlocal busy, cleaning
        if busy:
            return
        if categories and is_running():
            status.set("请先停止随机任务，再清理空间。")
            return
        if categories:
            affected = [description for key, description in DATA_DESCRIPTIONS.items() if key in categories]
            if affected and not messagebox.askyesno(
                "确认清理数据", "将永久清理以下数据：\n" + "\n".join(affected)
                + "\n\n各分类独立清理，游戏原始存档、规则和设置不受影响。"
                + "\n需要保留的文件请先导出备份。此操作无法撤销，确认继续吗？",
                parent=dialog, default="no", icon="warning",
            ):
                return
            if is_running():
                status.set("请先停止随机任务，再清理空间。")
                return
        busy = True
        cleaning = bool(categories)
        for button in buttons:
            button.configure(state="disabled")
        status.set("正在清理…" if categories else "正在统计空间…")

        def work():
            result = clean_storage(base, categories) if categories else None
            return scan_storage(base), result, categories
        tasks.request("storage", work, completed, failed, durable=bool(categories))

    for row, (key, label) in enumerate(CATEGORIES.items(), 1):
        ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=12)
        total, available = tk.StringVar(value="—"), tk.StringVar(value="—")
        values[key] = (total, available)
        for column, variable in ((1, total), (2, available)):
            ttk.Label(grid, textvariable=variable).grid(row=row, column=column, padx=8)
        button = ttk.Button(grid, text="清理", command=lambda key=key: begin({key}))
        button.grid(row=row, column=3, padx=8)
        buttons.append(button)
    ttk.Label(body, text="沙箱共享资源不重复计入占用；数据库清空后保留结构，占用不会归零。", foreground="#667085").pack(anchor="w", pady=(8, 4))
    ttk.Label(body, textvariable=status, wraplength=570).pack(anchor="w", pady=4)
    refresh = ttk.Button(actions, text="刷新", command=begin)
    refresh.pack(side="left")
    clear_all = ttk.Button(actions, text="全部清理", command=lambda: begin(set(CATEGORIES)))
    clear_all.pack(side="right")
    buttons.extend((refresh, clear_all))
    def finish():
        nonlocal busy, cleaning
        busy = False
        cleaning = False
        for button in buttons:
            button.configure(state="normal")

    def completed(data):
        nonlocal usage
        scanned, result, categories = data
        usage = scanned
        for key, (total, available) in values.items():
            total.set(format_size(usage[key].total))
            available.set(format_size(usage[key].cleanable))
        status.set(f"已清理 {result[0]} 项，{result[1]} 项未能清理。" if result else "统计完成，可按分类清理。")
        if result:
            owner = dialog._root()
            owner._ccz_cleaned_categories = categories
            owner.event_generate("<<StorageCleaned>>")
        finish()

    def failed(error):
        status.set(f"操作未完成：{error}")
        finish()

    tasks = WindowTasks(dialog, serial=False)
    def close():
        if cleaning:
            return
        dialog.destroy()
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.update_idletasks()
    width = max(620, dialog.winfo_reqwidth())
    height = max(370, dialog.winfo_reqheight())
    dialog.minsize(width, height)
    dialog.geometry(f"{width}x{height}")
    show_centered(dialog)
    dialog.grab_set()
    begin()
