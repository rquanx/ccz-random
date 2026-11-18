"""Build dialogs hidden, then place their final outer frame before revealing."""
from __future__ import annotations

import logging
import tkinter as tk

from ccz_randomizer.ui.window_native import native_placement

_log = logging.getLogger(__name__)


def _exists(window):
    try:
        return bool(window.winfo_exists())
    except tk.TclError:
        return False


def centered_origin(work_area, width, height):
    left, top, right, bottom = work_area
    return left + max(0, (right-left-width)//2), top + max(0, (bottom-top-height)//2)


def _fit_to_work_area(window, work, outer_width, outer_height):
    available_width, available_height = work[2]-work[0], work[3]-work[1]
    width, height = window.winfo_width(), window.winfo_height()
    fitted_width = max(1, width-max(0, outer_width-available_width))
    fitted_height = max(1, height-max(0, outer_height-available_height))
    if (width, height) != (fitted_width, fitted_height):
        min_width, min_height = window.minsize()
        window.minsize(min(min_width, fitted_width), min(min_height, fitted_height))
        window.geometry(f"{fitted_width}x{fitted_height}")
        window.update_idletasks()


def _center_native(window, parent, backend):
    work = backend.work_area(parent)
    # A bounded second pass accommodates a DPI-induced change in window size.
    for _ in range(2):
        left, top, right, bottom = backend.bounds(window)
        _fit_to_work_area(window, work, right-left, bottom-top)
        left, top, right, bottom = backend.bounds(window)
        x, y = centered_origin(work, right-left, bottom-top)
        backend.move(window, x, y)
        window.update_idletasks()
        placed = backend.bounds(window)
        if placed == (x, y, x+right-left, y+bottom-top):
            break


def _center_fallback(window):
    # A placement failure must never leave a dialog invisible.
    work = (0, 0, window.winfo_screenwidth(), window.winfo_screenheight())
    _fit_to_work_area(window, work, window.winfo_width(), window.winfo_height())
    x, y = centered_origin(work, window.winfo_width(), window.winfo_height())
    window.geometry(f"+{x}+{y}")
    window.update_idletasks()


def centered_toplevel(parent):
    """Create a dialog; the builder must finish with show_centered(window)."""
    window = tk.Toplevel(parent)
    window.withdraw()
    window._ccz_dialog_parent = parent
    window._ccz_dialog_shown = False
    return window


def show_centered(window):
    """Finalize first placement; later calls only restore the window."""
    if not _exists(window):
        return
    if getattr(window, "_ccz_dialog_shown", False):
        window.deiconify()
        return
    # A Tk root has no master; select its own monitor for initial placement.
    parent = getattr(window, "_ccz_dialog_parent", window.master) or window
    backend = None
    placed = None
    try:
        # Windows supplies the outer frame for a withdrawn Tk window after
        # geometry negotiation. Lay out and center it before mapping, so those
        # passes do not paint the entire transparent window repeatedly.
        window.update_idletasks()
        if not _exists(window):
            return
        try:
            backend = native_placement()
            if backend is None:
                _center_fallback(window)
            else:
                _center_native(window, parent, backend)
                placed = backend.bounds(window)
        except (OSError, tk.TclError):
            _log.debug("Native dialog placement failed", exc_info=True)
            if _exists(window):
                try:
                    _center_fallback(window)
                except tk.TclError:
                    _log.debug("Fallback dialog placement failed", exc_info=True)
        if _exists(window):
            window.deiconify()
            # Mapping on another DPI monitor may adjust the outer frame. Keep
            # the existing correction without repainting every normal dialog.
            if backend is not None and placed is not None:
                try:
                    if backend.bounds(window) != placed:
                        _center_native(window, parent, backend)
                except (OSError, tk.TclError):
                    _log.debug("Mapped dialog placement failed", exc_info=True)
    finally:
        if _exists(window):
            if window.state() == "withdrawn":
                window.deiconify()
            window._ccz_dialog_shown = True
            window.attributes("-alpha", 1.0)
