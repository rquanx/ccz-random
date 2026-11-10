"""Hover text with owned timers and no focus/grab changes."""
import tkinter as tk


class HoverTooltip:
    def __init__(self, widget, text, delay=300):
        self.widget, self.text, self.delay = widget, text, delay
        self.timer = None
        self.popup = None
        self.label = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def _enter(self, _event=None):
        self.hide()
        self.timer = self.widget.after(self.delay, self._show)

    def refresh(self):
        if self.label is not None:
            self.label.configure(text=self.text() if callable(self.text) else self.text)

    def _show(self):
        self.timer = None
        if not self.widget.winfo_exists():
            return
        self.popup = tk.Toplevel(self.widget)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        self.label = tk.Label(self.popup, bg="#182230", fg="#ffffff",
            padx=10, pady=7, justify="left", font=("Microsoft YaHei UI", 9), wraplength=320)
        self.label.pack()
        self.refresh()
        self.popup.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - self.popup.winfo_reqwidth() - 8)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        if y + self.popup.winfo_reqheight() > self.widget.winfo_screenheight() - 8:
            y = self.widget.winfo_rooty() - self.popup.winfo_reqheight() - 6
        self.popup.geometry(f"+{max(8, x)}+{max(8, y)}")
        self.popup.deiconify()
        self.popup.lift()

    def hide(self, _event=None):
        if self.timer is not None:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.popup is not None:
            popup, self.popup, self.label = self.popup, None, None
            popup.destroy()
