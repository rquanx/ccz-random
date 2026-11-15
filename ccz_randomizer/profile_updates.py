"""Profile update controls; downloads never block the Tk event loop."""
from __future__ import annotations
from tkinter import ttk

import queue
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog
from urllib.error import HTTPError

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.profiles import install_profile_package, load_profile
from ccz_randomizer.profile_feed import check_profile_update, install_feed_update, DEFAULT_PACKAGE_URL, load_feed_url

UPDATE_FAILED_MESSAGE = "数据自动更新失败，可在「常见问题 → 手动更新数据」中处理。"


def profile_version_label(app_directory: Path) -> str:
    """Report the running snapshot separately from the next-launch package."""
    current = load_profile()
    installed = load_profile(app_directory=app_directory)
    version = str(current.manifest["catalogVersion"])
    if (current.profile_id, current.manifest) != (installed.profile_id, installed.manifest):
        return f"当前 {version}；已下载 {installed.manifest['catalogVersion']}，空闲时生效"
    return version


def auto_update_profile(app_directory: Path, *, on_update_available=None):
    feed = check_profile_update(app_directory)
    if not feed:
        return None
    if on_update_available:
        on_update_available()
    return install_feed_update(feed, app_directory)


def background_call(parent, action, done, failed):
    from ccz_randomizer.ui.tasks import WindowTasks
    tasks = WindowTasks(parent, serial=False)
    def complete(callback, value):
        tasks.close()
        callback(value)
    tasks.request("background", action, lambda value: complete(done, value),
                  lambda error: complete(failed, error), durable=True)
    return tasks


def startup_profile_check(parent, app_directory: Path, notify, log_error=None, *, on_state=None, on_installed=None):
    update_available = False
    progress = queue.Queue()
    progress_timer = None

    def drain():
        nonlocal progress_timer
        progress_timer = None
        try:
            while True:
                progress.get_nowait()
                if on_state:
                    on_state("updating")
        except queue.Empty:
            pass

    def poll_progress():
        nonlocal progress_timer
        drain()
        if parent.winfo_exists():
            progress_timer = parent.after(100, poll_progress)

    remove_destroy_listener = lambda: None

    def stop_progress():
        nonlocal progress_timer
        if progress_timer is not None:
            parent.after_cancel(progress_timer)
            progress_timer = None
        remove_destroy_listener()

    def finish():
        stop_progress()
        drain()

    if isinstance(parent, tk.Misc):
        from ccz_randomizer.ui.window_events import bind_window_event
        remove_destroy_listener = bind_window_event(parent, "<Destroy>", lambda _event: stop_progress())

    def found_update():
        nonlocal update_available
        # The feed has passed compatibility and local-version checks.
        update_available = True
        progress.put(True)

    def failed(error):
        finish()
        if log_error:
            log_error(error)
        if update_available:
            notify(UPDATE_FAILED_MESSAGE)
        if on_state:
            if update_available:
                on_state("old")
            else:
                on_state("local" if isinstance(error, HTTPError) and error.code == 404 else "unknown")

    def done(profile):
        finish()
        if profile is not None and on_installed:
            on_installed(profile)
        elif on_state:
            on_state("latest" if load_feed_url(app_directory) else "local")

    if on_state:
        on_state("checking")
        progress_timer = parent.after(100, poll_progress)
    background_call(parent, lambda: auto_update_profile(
        app_directory, on_update_available=found_update,
    ), done, failed)


def show_profile_update_dialog(parent: tk.Misc, app_directory: Path, *, on_installed=None) -> None:
    dialog = centered_toplevel(parent)
    dialog.title("手动更新数据")
    dialog.transient(parent)
    dialog.resizable(False, False)
    body = tk.Frame(dialog, padx=18, pady=16)
    body.pack(fill="both", expand=True)
    tk.Label(body, text="自动更新失败时，可在这里手动更新工具数据。\n先下载文件，再上传下载的 ZIP 压缩包；工具空闲时自动生效。", justify="left", wraplength=440).pack(anchor="w")
    current = load_profile()
    status = tk.StringVar(value=f"当前：{current.profile_id} · 修订 {profile_version_label(app_directory)}")
    tk.Label(body, textvariable=status, fg="#555", wraplength=440, justify="left").pack(anchor="w", pady=(10, 12))
    actions = tk.Frame(body)
    actions.pack(fill="x")
    buttons = []
    busy = False
    def set_busy(value):
        nonlocal busy
        busy = value
        for button in buttons:
            button.configure(state="disabled" if value else "normal")
    def failed(exc):
        set_busy(False)
        status.set(f"更新失败，当前数据包保留。\n{exc}")
    def installed(profile):
        set_busy(False)
        if on_installed:
            on_installed(profile)
        status.set(f"已安装修订 {profile.manifest['catalogVersion']}，工具空闲时自动生效。")
    def run(action, done=installed):
        set_busy(True)
        status.set("正在处理，请稍候…")
        background_call(dialog, action, done, failed)
    def local():
        path = filedialog.askopenfilename(parent=dialog, filetypes=[("Profile ZIP", "*.zip")])
        if path:
            run(lambda: install_profile_package(path, app_directory))
    def download():
        try:
            if not webbrowser.open(DEFAULT_PACKAGE_URL):
                raise OSError("无法打开浏览器，请检查默认浏览器设置。")
            status.set("已打开浏览器，下载完成后点击「上传数据包」。")
        except OSError as exc:
            failed(exc)
    for label, callback in [("下载文件", download), ("上传数据包", local)]:
        button = ttk.Button(actions, text=label, command=callback)
        button.pack(side="left", padx=(0, 8))
        buttons.append(button)
    def close():
        if busy:
            return
        dialog.destroy()
        if parent.winfo_exists():
            parent.grab_set()
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.update_idletasks()
    show_centered(dialog)
    dialog.grab_set()
