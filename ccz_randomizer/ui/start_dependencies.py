"""Asynchronous prerequisite gate for a user's explicit start action."""
from tkinter import TclError
from ccz_randomizer.diagnostics.dependencies import inspect_runtime_dependencies
from ccz_randomizer.ui.dependency_messages import show_dependency_issues
from ccz_randomizer.ui.tasks import WindowTasks


class StartDependencyCheck:
    def __init__(self, window, button, on_ready, command, bundle):
        self.window = window
        self.button = button
        self.on_ready = on_ready
        self.command = tuple(command)
        self.bundle = bundle
        self.pending = False
        self.tasks = None

    def request(self):
        if self.pending:
            return
        try:
            if not self.window.winfo_exists():
                return
        except TclError:
            return
        self.pending = True
        self.tasks = WindowTasks(self.window, serial=False)
        self.previous_text = self.button.cget("text")
        self.previous_state = self.button.cget("state")
        self.button.configure(text="正在检测依赖…", state="disabled")
        command, bundle = list(self.command), self.bundle
        self.tasks.request("dependencies",
                           lambda: inspect_runtime_dependencies(command, bundle),
                           self._finished, self._failed)

    def _finished(self, checks):
        self.tasks.close()
        self.pending = False
        self.button.configure(text=self.previous_text, state=self.previous_state)
        if checks and all(check["ok"] for check in checks):
            self.on_ready()
        else:
            if not checks:
                checks = [dict(label="运行依赖", ok=False, message="未能取得检测结果，请重新检测。")]
            show_dependency_issues(self.window, checks, self.request)

    def _failed(self, error):
        self._finished([dict(label="运行依赖", ok=False, message=f"未能完成检测：{error}。请重新检测或在常见问题中上报日志。")])
