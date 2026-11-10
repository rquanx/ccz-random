"""A selection-only combobox with a separate searchable popup."""
import tkinter as tk
from tkinter import ttk
from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.theme import FONT, setup_theme


class SearchableCombobox(ttk.Combobox):
    def __init__(self, parent, *, search_label="搜索选项", empty_text="没有匹配的选项",
                 search_threshold=0, **kwargs):
        setup_theme(parent)
        kwargs.setdefault("state", "readonly")
        kwargs.setdefault("font", (FONT, 10))
        super().__init__(parent, **kwargs)
        self._textvariable = kwargs.get("textvariable")
        self.search_label, self.empty_text = search_label, empty_text
        self.search_threshold = search_threshold
        self.popup = None
        self._outside_binding = None
        self._focus_timer = None
        self._previous_grab = None
        self.bind("<Button-1>", self.open_popup)
        self.bind("<Down>", self.open_popup)
        self.bind("<space>", self.open_popup)
        self.bind("<Alt-Down>", self.open_popup)
        self.bind("<F4>", self.open_popup)
        # Hovering a dropdown while scrolling a settings page must not edit it.
        self.bind("<MouseWheel>", lambda _event: "break")
        self.bind("<Button-4>", lambda _event: "break")
        self.bind("<Button-5>", lambda _event: "break")
        self.bind("<Destroy>", self.close_popup, add="+")

    def open_popup(self, _event=None):
        if self.instate(("disabled",)):
            return "break"
        if self.popup is not None:
            self.close_popup()
            return "break"
        if len(self.cget("values")) <= self.search_threshold:
            return None  # Small option sets keep the native direct picker.
        owner = self.winfo_toplevel()
        self.popup = popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(owner)
        outline = tk.Frame(popup, bg="#D9E0EA", padx=1, pady=1)
        outline.pack(fill="both", expand=True)
        content = ttk.Frame(outline, padding=8)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text=self.search_label, foreground="#667085").pack(anchor="w", pady=(0, 4))
        self.search = tk.StringVar()
        self.search_entry = SearchEntry(content, textvariable=self.search)
        self.search_entry.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(content)
        row.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(row, height=10, exportselection=False, borderwidth=0,
            highlightthickness=0, activestyle="none", bg="#FFFFFF", fg="#182230",
            font=(FONT, 10), selectbackground="#EAF0FB", selectforeground="#182230")
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(row, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.empty = ttk.Label(self.listbox, text=self.empty_text, foreground="#667085")
        self.search.trace_add("write", self._filter)
        self._filter()
        values = self.listbox.get(0, "end")
        if self.get() in values:
            self._select(values.index(self.get()))
        for widget in (popup, self.search_entry, self.listbox):
            widget.bind("<Escape>", self._cancel_choice)
            widget.bind("<Return>", self._choose)
            widget.bind("<KP_Enter>", self._choose)
            widget.bind("<Tab>", self._tab_next)
            widget.bind("<Shift-Tab>", lambda event: self._tab_next(event, backwards=True))
        self.search_entry.bind("<Down>", lambda event: self._move(1))
        self.search_entry.bind("<Up>", lambda event: self._move(-1))
        self.listbox.bind("<ButtonRelease-1>", self._click_choice)
        # Toplevel bindtags see clicks on their children, including non-focusable canvases.
        self._owner = owner
        self._outside_binding = owner.bind("<ButtonPress-1>", self._outside, add="+")
        popup.bind("<FocusOut>", self._focus_out)
        popup.bind("<ButtonPress-1>", self._popup_click)
        popup.update_idletasks()
        width = max(self.winfo_width(), 270)
        height = popup.winfo_reqheight()
        x = min(self.winfo_rootx(), self.winfo_screenwidth()-width-8)
        y = self.winfo_rooty()+self.winfo_height()+3
        if y+height > self.winfo_screenheight()-8:
            y = self.winfo_rooty()-height-3
        popup.geometry(f"{width}x{height}+{max(0,x)}+{max(0,y)}")
        popup.deiconify()
        popup.lift()
        self._previous_grab = self.grab_current()
        popup.grab_set()
        self.search_entry.focus_set()
        return "break"

    def _filter(self, *_args):
        terms = self.search.get().casefold().split()
        self.listbox.delete(0, "end")
        for value in self.cget("values"):
            if all(term in value.casefold() for term in terms):
                self.listbox.insert("end", value)
        if self.listbox.size():
            self.empty.place_forget()
            self._select(0)
        else:
            self.empty.place(relx=.5, rely=.5, anchor="center")

    def _select(self, index):
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.activate(index)
        self.listbox.see(index)

    def _move(self, delta):
        if self.listbox.size():
            current = self.listbox.curselection()
            self._select(max(0, min(self.listbox.size()-1, (current[0] if current else 0)+delta)))
        return "break"

    def _choose(self, _event=None):
        selected = self.listbox.curselection()
        if selected:
            value = self.listbox.get(selected[0])
            self.focus_set()
            self.close_popup()
            self.set(value)
            # Consumers may destroy the selector or open another modal window.
            self.event_generate("<<ComboboxSelected>>")
        return "break"

    def _click_choice(self, event):
        index = self.listbox.nearest(event.y)
        bounds = self.listbox.bbox(index) if self.listbox.size() else None
        if bounds and bounds[1] <= event.y < bounds[1]+bounds[3]:
            self._select(index)
            return self._choose()
        return "break"

    def _cancel_choice(self, _event=None):
        self.focus_set()
        self.close_popup()
        return "break"

    def _tab_next(self, _event=None, *, backwards=False):
        target = self.tk_focusPrev() if backwards else self.tk_focusNext()
        target.focus_set()
        self.close_popup()
        return "break"

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf) if isinstance(cnf, dict) else {}
        options.update(kwargs)
        if "textvariable" in options:
            self._textvariable = options["textvariable"]
        if getattr(self, "popup", None) is not None and any(
                key in options for key in ("state", "values", "textvariable")):
            self.close_popup()
        return super().configure(cnf, **kwargs)

    config = configure

    def state(self, statespec=None):
        result = super().state(statespec)
        if statespec is not None and self.instate(("disabled",)):
            self.close_popup()
        return result

    def _outside(self, event):
        if event.widget is not self:
            self.close_popup()

    def _focus_out(self, _event):
        if self.popup is not None:
            if self._focus_timer is not None:
                self.popup.after_cancel(self._focus_timer)
            self._focus_timer = self.popup.after_idle(self._check_focus)

    def _check_focus(self):
        self._focus_timer = None
        if self.popup is not None:
            focus = self.focus_get()
            if focus is None or focus.winfo_toplevel() is not self.popup:
                self.close_popup()

    def _popup_click(self, event):
        if self.popup is not None:
            x, y = event.x_root-self.popup.winfo_rootx(), event.y_root-self.popup.winfo_rooty()
            if not (0 <= x < self.popup.winfo_width() and 0 <= y < self.popup.winfo_height()):
                self.close_popup()
                return "break"

    def close_popup(self, _event=None):
        if self._outside_binding is not None:
            self._owner.unbind("<ButtonPress-1>", self._outside_binding)
            self._outside_binding = None
        if self.popup is not None:
            popup, self.popup = self.popup, None
            if self._focus_timer is not None:
                popup.after_cancel(self._focus_timer)
                self._focus_timer = None
            popup.grab_release()
            popup.destroy()
            previous, self._previous_grab = self._previous_grab, None
            if previous is not None and previous.winfo_exists():
                previous.grab_set()
        return "break"


class SelectionCombobox(SearchableCombobox):
    """Direct selection for short menus; searchable selection for long ones."""

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("search_threshold", 10)
        super().__init__(parent, **kwargs)
