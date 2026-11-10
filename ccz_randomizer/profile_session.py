"""UI-thread lifecycle for one startup check and an idle-time activation."""
from ccz_randomizer.profiles import load_profile
from ccz_randomizer.profile_activation import activate_installed_profile
from ccz_randomizer.profile_updates import startup_profile_check, UPDATE_FAILED_MESSAGE
from ccz_randomizer.ui.profile_status import ProfileStatus


class ProfileUpdateSession:
    def __init__(self, parent, directory, *, is_idle, display, notify, log_error=None, on_activated=None):
        self.parent, self.directory = parent, directory
        self.is_idle, self.display = is_idle, display
        self.notify, self.log_error, self.on_activated = notify, log_error, on_activated
        self.current = load_profile()
        self.pending = None
        self.timer = None
        self.started = False
        self.error_detail = ""
        import tkinter as tk
        if isinstance(parent, tk.Misc):
            from ccz_randomizer.ui.window_events import bind_window_event
            bind_window_event(parent, "<Destroy>", lambda _event: self.close())

    def close(self):
        if self.timer is not None:
            self.parent.after_cancel(self.timer)
            self.timer = None
        self.pending = None

    def _show(self, state):
        self.display(ProfileStatus(state, self.current.manifest["catalogVersion"],
            self.pending.manifest["catalogVersion"] if self.pending else None,
            self.error_detail if state in {"unknown", "old"} else ""))

    def _record_error(self, error):
        self.error_detail = str(error)
        if self.log_error:
            self.log_error(error)

    def start(self):
        if self.started:
            return
        self.started = True
        startup_profile_check(self.parent, self.directory, self.notify, self._record_error,
            on_state=self._show, on_installed=self.downloaded)

    def downloaded(self, profile):
        self.pending = profile
        if self.timer is not None:
            self.parent.after_cancel(self.timer)
            self.timer = None
        self._apply_when_idle()

    def _apply_when_idle(self):
        self.timer = None
        if not self.parent.winfo_exists():
            return
        if not self.is_idle():
            self._show("pending")
            self.timer = self.parent.after(250, self._apply_when_idle)
            return
        try:
            self.current = activate_installed_profile(self.directory)
        except Exception as error:
            if self.log_error:
                self.log_error(error)
            self._show("old")
            self.notify(UPDATE_FAILED_MESSAGE)
            return
        self.pending = None
        self._show("latest")
        if self.on_activated:
            self.on_activated()
