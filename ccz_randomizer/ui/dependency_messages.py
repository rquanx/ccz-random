"""Shared official download actions for FAQ and start-time dependency errors."""
import os
import tkinter as tk
from tkinter import ttk
from ccz_randomizer.ui import scrolled_text as scrolledtext

from ccz_randomizer.diagnostics.dependencies import format_checks, official_downloads
from ccz_randomizer.ui.dialog_actions import add_dialog_actions
from ccz_randomizer.ui.theme import setup_theme, style_dialog
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def add_download_actions(frame, downloads, *, on_copy=None):
    for download in downloads:
        url = download["url"]
        ttk.Button(frame, text="打开" + download["label"],
                   command=lambda url=url: os.startfile(url)).pack(side="left", padx=(0, 8))
        def copy_url(url=url):
            window = frame.winfo_toplevel()
            window.clipboard_clear()
            window.clipboard_append(url)
            if on_copy is not None:
                on_copy()
        ttk.Button(frame, text="复制下载地址", command=copy_url).pack(side="left")


def show_dependency_issues(parent, checks, retry):
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("无法开始随机")
    dialog.geometry("720x520")
    dialog.minsize(620, 420)
    dialog.transient(parent)
    body = ttk.Frame(dialog, padding=18)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="运行依赖检测未通过", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
    ttk.Label(body, text="随机尚未启动。请按提示修复，再点击“重新检测”；通过后将继续随机。",
              wraplength=650).pack(fill="x", pady=(6, 12))
    downloads = official_downloads(checks)
    lines = format_checks(checks)
    for download in downloads:
        lines.extend(("", download["label"] + "（官方下载）：", download["url"]))
    report = scrolledtext.ScrolledText(body, height=12, wrap="word")
    report.insert("end", "\n".join(lines))
    report.configure(state="disabled")
    report.pack(fill="both", expand=True)
    links = ttk.Frame(body)
    links.pack(fill="x", pady=(10, 0))
    copied = tk.StringVar(dialog)
    add_download_actions(links, downloads, on_copy=lambda: copied.set("下载地址已复制"))
    ttk.Label(body, textvariable=copied).pack(anchor="w", pady=(4, 0))
    actions = ttk.Frame(body)
    actions.pack(fill="x", pady=(8, 0))
    def recheck():
        dialog.destroy()
        retry()
    add_dialog_actions(actions, confirm=recheck, confirm_text="重新检测", cancel=dialog.destroy)
    show_centered(dialog)
    dialog.grab_set()
    return dialog
