"""Support dialogs isolated from the randomization and main-window lifecycle."""
from pathlib import Path
import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
from ccz_randomizer.ui import scrolled_text as scrolledtext
from ccz_randomizer.ui import messages as messagebox
from ccz_randomizer.ui.inputs import TextEntry
from ccz_randomizer.ui.dependency_messages import add_download_actions
from ccz_randomizer.diagnostics.dependencies import (
    dependency_guidance, format_checks, inspect_runtime_dependencies,
    official_downloads, system_information,
)


def create_support_actions(root, api):
    """Bind service dependencies explicitly; workers never call Tk."""
    UploadCancelled = api.UploadCancelled
    app_dir = api.app_dir
    application_build_info = api.application_build_info
    build_version_text = api.build_version_text
    centered_toplevel = api.centered_toplevel
    create_log_archive = api.create_log_archive
    show_centered = api.show_centered
    show_toast = api.show_toast
    upload_log_archive = api.upload_log_archive
    bundle_root = api.bundle_root
    current_game_version = api.current_game_version
    inspect_environment = api.inspect_environment
    locate_game_executable = api.locate_game_executable
    native_dir = api.native_dir
    source_entry_path = api.source_entry_path
    diagnostic_inflight = threading.Event()

    def open_log_upload_progress(parent: tk.Misc = root) -> None:
        if not messagebox.askyesno(
            "上传最新日志",
            "将跳过环境检测，仅上传近期日志（最多约 8 MB）到匿名临时文件服务。"
            "日志可能包含路径、系统信息和运行错误，但不包含游戏存档内容。是否继续？",
            parent=parent,
        ):
            return
        dialog = centered_toplevel(parent)
        dialog.title("上传日志")
        dialog.resizable(False, False)
        dialog.transient(parent)
        body = tk.Frame(dialog, padx=20, pady=18)
        body.pack(fill="both", expand=True)
        status = tk.Label(body, text="正在准备日志压缩包……", anchor="w", width=54)
        status.pack(fill="x")
        progress = ttk.Progressbar(body, mode="indeterminate", length=440)
        progress.pack(fill="x", pady=(12, 14))
        progress.start(12)
        cancel = threading.Event()
        cancel_button = ttk.Button(body, text="取消", width=10)
        cancel_button.pack(anchor="e")
        archive_holder: dict[str, Path] = {}

        def show_upload_success(url: str) -> None:
            success = centered_toplevel(parent)
            success.title("日志上传成功")
            success.transient(parent)
            frame = tk.Frame(success, padx=20, pady=18)
            frame.pack(fill="both", expand=True)
            tk.Label(frame, text="日志已上传，请将下面地址提供给开发者：", anchor="w").pack(fill="x")
            url_var = tk.StringVar(value=url)
            url_entry = TextEntry(frame, textvariable=url_var, width=72)
            url_entry.pack(fill="x", pady=(12, 8))
            url_entry.selection_range(0, "end")
            actions = tk.Frame(frame)
            actions.pack(fill="x")
            def copy_url() -> None:
                success.clipboard_clear()
                success.clipboard_append(url)
                show_toast(success, "地址已复制")
            ttk.Button(actions, text="复制地址", width=12, command=copy_url).pack(side="left")
            ttk.Button(actions, text="打开地址", width=12, command=lambda: os.startfile(url)).pack(side="left", padx=(8, 0))
            ttk.Button(actions, text="关闭", width=10, command=success.destroy).pack(side="right")
            success.update_idletasks()
            success.geometry(f"{max(620, success.winfo_reqwidth())}x{max(150, success.winfo_reqheight())}")
            show_centered(success)
            success.grab_set()

        def open_folder() -> None:
            archive = archive_holder.get("path")
            if archive is not None:
                os.startfile(str(archive.parent))

        def finish_failure(error: BaseException) -> None:
            progress.stop()
            dialog.destroy()
            archive = archive_holder.get("path")
            failure = centered_toplevel(parent)
            failure.title("日志上传失败")
            failure.transient(parent)
            frame = tk.Frame(failure, padx=20, pady=18)
            frame.pack(fill="both", expand=True)
            tk.Label(frame, text=f"无法上传日志：{error}", justify="left", anchor="w", wraplength=560).pack(fill="x")
            if archive is not None:
                tk.Label(frame, text="压缩包已保存在：", anchor="w").pack(fill="x", pady=(14, 2))
                path_label = tk.Label(frame, text=str(archive), fg="#1565c0", cursor="hand2", anchor="w", wraplength=560, justify="left")
                path_label.pack(fill="x")
                path_label.bind("<Button-1>", lambda _event: open_folder())
                ttk.Button(frame, text="打开所在文件夹", command=open_folder, width=16).pack(anchor="w", pady=(8, 0))
            failure_actions = tk.Frame(frame)
            failure_actions.pack(fill="x", pady=(14, 0))
            ttk.Button(
                failure_actions,
                text="再次上传",
                command=lambda: (failure.destroy(), open_log_upload_progress(parent)),
                width=12,
            ).pack(side="left")
            ttk.Button(failure_actions, text="关闭", command=failure.destroy, width=10).pack(side="right")
            failure.update_idletasks()
            failure.geometry(f"{max(560, failure.winfo_reqwidth())}x{max(220, failure.winfo_reqheight())}")
            show_centered(failure)
            failure.grab_set()

        from ccz_randomizer.ui.tasks import WindowTasks
        tasks = WindowTasks(dialog, serial=False, on_close=cancel.set)
        def update_progress(phase):
            progress.stop()
            if phase == "uploading":
                progress.configure(mode="indeterminate")
                progress.start(12)
                status.configure(text="正在上传日志……")
            else:
                progress.configure(mode="determinate", maximum=1, value=1)
        report_progress = tasks.channel("progress", update_progress)

        def work():
            archive = create_log_archive(app_dir() / "ccz_fast_logs", extra={"toolVersion": build_version_text(application_build_info())})
            archive_holder["path"] = archive
            if cancel.is_set():
                raise UploadCancelled()
            report_progress("uploading")
            def update_upload_progress(sent, total):
                if sent >= total:
                    report_progress("complete")
            return upload_log_archive(archive, cancel_event=cancel, progress_callback=update_upload_progress)

        def uploaded(url):
            progress.stop()
            dialog.destroy()
            show_upload_success(url)

        def upload_failed(error):
            if isinstance(error, UploadCancelled):
                dialog.destroy()
            else:
                finish_failure(error)

        def cancel_upload() -> None:
            cancel.set()
            cancel_button.configure(state="disabled")
            status.configure(text="正在取消上传……")

        cancel_button.configure(command=cancel_upload)
        dialog.update_idletasks()
        dialog.geometry(f"{max(520, dialog.winfo_reqwidth())}x{max(170, dialog.winfo_reqheight())}")
        show_centered(dialog)
        dialog.grab_set()
        tasks.request("upload", work, uploaded, upload_failed, cancel_event=cancel)

    def upload_latest_logs(parent: tk.Misc = root) -> None:
        open_log_upload_progress(parent)

    def open_unusable_diagnostics(parent: tk.Misc = root) -> None:
        """Run safe checks and offer an explicit one-shot compatibility probe."""
        dialog = centered_toplevel(parent)
        dialog.title("随机无法使用诊断")
        dialog.geometry("720x560")
        dialog.minsize(620, 460)
        dialog.transient(parent)
        body = tk.Frame(dialog, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="先检查运行依赖，再测试兼容模式", font=("Microsoft YaHei UI", 12, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, text="依赖异常时提供官方下载指引；依赖正常后，兼容模式测试会随机一次并保护现场存档。", fg="#666666", anchor="w", justify="left", wraplength=650).pack(fill="x", pady=(6, 12))
        report = scrolledtext.ScrolledText(body, height=16, wrap="word", state="disabled")
        report.pack(fill="both", expand=True)
        downloads_frame = ttk.Frame(body)
        downloads_frame.pack(fill="x", pady=(8, 0))
        actions = tk.Frame(body)
        actions.pack(fill="x", pady=(12, 0))
        probe_button = ttk.Button(actions, text="再次测试", width=16)
        probe_button.pack(side="left")
        upload_button = ttk.Button(actions, text="上报日志给开发者", width=18)
        upload_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="关闭", width=10, command=dialog.destroy).pack(side="right")

        def write_report(lines: list[str], downloads=()) -> None:
            report.configure(state="normal")
            report.delete("1.0", "end")
            for child in downloads_frame.winfo_children():
                child.destroy()
            for download in downloads:
                url = download["url"]
                lines = [*lines, "", download["label"] + "（官方下载）：", url]
            add_download_actions(downloads_frame, downloads,
                                 on_copy=lambda: show_toast(dialog, "下载地址已复制"))
            report.insert("end", "\n".join(lines))
            report.configure(state="disabled")


        closed = threading.Event()

        def run_probe() -> dict:
            try:
                game_executable = locate_game_executable()
                log_root = app_dir() / "ccz_fast_logs"
                checks = inspect_environment(
                    game_executable,
                    app_root=app_dir(),
                    native_root=native_dir(),
                    bundle_root=bundle_root(),
                    log_root=log_root,
                )
                source = game_executable.parent / "SV" / "SV020.E5S"
                checks.append({"label": "第20栏源存档", "ok": source.is_file(), "message": "第20栏源存档存在。" if source.is_file() else "未找到第20栏源存档。"})
            except Exception as exc:
                game_executable = None
                log_root = app_dir() / "ccz_fast_logs"
                checks = [{"label": "游戏定位", "ok": False, "message": f"无法定位游戏：{exc}"}]

            command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(source_entry_path())]
            dependencies = inspect_runtime_dependencies(command, bundle_root())
            environment_lines = format_checks([*checks, *dependencies])
            downloads = official_downloads(dependencies)
            if closed.is_set():
                return dict(lines=["已取消诊断。"], downloads=[])
            if any(not item["ok"] for item in dependencies):
                return dict(lines=[*environment_lines, "", "请先修复上述依赖问题，再点击“再次测试”。本次未启动游戏。"], downloads=downloads)
            if game_executable is None:
                return dict(lines=[*environment_lines, "", "无法执行兼容模式测试：游戏定位失败。"], downloads=downloads)
            env = os.environ.copy()
            env.update({"CCZ_AUTOSTART": "1", "CCZ_NO_PAUSE": "1", "CCZ_SUPPORT_PROBE": "1", "CCZ_COMPATIBILITY_MODE": "1", "CCZ_RESULT_COUNT": "1", "CCZ_TOTAL_RESULT_COUNT": "1", "CCZ_RESULT_SLOT_START": "1", "CCZ_GAME_VERSION": current_game_version(), "CCZ_RANDOM_MODE": "three"})
            command = [*command, "--worker"]
            try:
                completed = subprocess.run(command, cwd=str(app_dir()), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                output = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-12000:]
                success = completed.returncode == 0
                message = ("兼容模式测试成功。建议在主界面勾选“兼容模式”后重试。" if success else "兼容模式测试也未成功，暂时无法明确定位原因，请上报日志给开发者。")
                if not success and any(token in output.casefold() for token in ("dll load failed", "mfc140", "vcruntime140", "msvcp140")):
                    guidance = dependency_guidance(output, system_information())
                    message = guidance["message"]
                    downloads = official_downloads([guidance])
                return dict(lines=[*environment_lines, "", message, "", output], downloads=downloads)
            except Exception as exc:
                error_text = str(exc)
                return dict(lines=[*environment_lines, "", f"兼容模式测试失败：{error_text}", "请上报日志给开发者。"], downloads=downloads)

        def probe():
            try:
                return run_probe()
            finally:
                diagnostic_inflight.clear()

        from ccz_randomizer.ui.tasks import WindowTasks
        tasks = WindowTasks(dialog, serial=False)
        def probe_finished(result):
            write_report(result["lines"], result["downloads"])
            probe_button.configure(state="normal")

        def start_probe() -> None:
            if diagnostic_inflight.is_set():
                write_report(["已有兼容模式测试正在收尾，请稍后点击“再次测试”。"])
                return
            diagnostic_inflight.set()
            probe_button.configure(state="disabled")
            write_report(["正在检测系统、VC++/MFC 运行库和工具组件……", "依赖正常后将继续执行一次兼容模式测试，请等待最多两分半钟。"])
            tasks.request("probe", probe, probe_finished,
                          lambda error: probe_finished(dict(lines=[str(error)], downloads=[])), durable=True)

        def upload() -> None:
            open_log_upload_progress(dialog)

        probe_button.configure(command=start_probe)
        upload_button.configure(command=upload)
        dialog.update_idletasks()
        dialog.geometry(f"{max(720, dialog.winfo_reqwidth())}x{max(560, dialog.winfo_reqheight())}")
        show_centered(dialog)
        dialog.grab_set()
        # Opening this FAQ item is an explicit request to diagnose the failure.
        # Start the one-shot compatibility probe automatically after the initial
        # environment report is visible; the user should not need to advance a
        # second dialog just to obtain the conclusion.
        initial_timer = dialog.after(1, start_probe)
        def cancel_initial():
            closed.set()
            dialog.after_cancel(initial_timer)
        tasks.on_close = cancel_initial

    return open_log_upload_progress, upload_latest_logs, open_unusable_diagnostics
