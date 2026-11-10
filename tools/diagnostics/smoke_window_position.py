"""Probe native dialog placement on attached monitors without touching the game."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ccz_randomizer.ui.window_native import _MonitorInfo, native_placement
from ccz_randomizer.ui.window_position import centered_toplevel, show_centered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dpi", choices=("current", "unaware", "system", "per-monitor"), default="current")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    backend = native_placement()
    if backend is None:
        raise SystemExit("Windows is required")
    api = backend.api
    previous = None
    if args.dpi != "current":
        api.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
        api.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
        context = {"unaware": -1, "system": -2, "per-monitor": -4}[args.dpi]
        previous = api.SetThreadDpiAwarenessContext(context)
        if not previous:
            raise ctypes.WinError(ctypes.get_last_error())
    monitors = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    @callback_type
    def collect(handle, _dc, _rect, _data):
        info = _MonitorInfo()
        info.size = ctypes.sizeof(info)
        if api.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.work
            monitors.append((r.left, r.top, r.right, r.bottom))
        return True

    api.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
    api.EnumDisplayMonitors.restype = wintypes.BOOL
    if not api.EnumDisplayMonitors(None, None, collect, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    root = tk.Tk()
    root.attributes("-alpha", 0)
    root.geometry("200x100")
    root.update_idletasks()
    results = []
    try:
        for monitor in monitors:
            backend.move(root, monitor[0]+30, monitor[1]+30)
            root.update()
            work = backend.work_area(root)
            for size in ("300x200", "720x560", "1480x850"):
                dialog = centered_toplevel(root)
                dialog.geometry(size)
                dialog.minsize(200, 100)
                show_centered(dialog)
                root.update()
                left, top, right, bottom = backend.bounds(dialog)
                passed = (work == monitor and abs(left+right-work[0]-work[2]) <= 1 and
                          abs(top+bottom-work[1]-work[3]) <= 1 and
                          left >= work[0] and top >= work[1] and
                          right <= work[2] and bottom <= work[3] and
                          dialog.attributes("-alpha") == 1.0)
                results.append(dict(requested=size, requestedMonitor=monitor, workArea=work,
                                    outerBounds=(left, top, right, bottom), passed=passed))
                dialog.destroy()
        report = dict(dpiContext=args.dpi, monitorCount=len(monitors), results=results)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not results or not all(item["passed"] for item in results):
            raise SystemExit(1)
    finally:
        root.destroy()
        if previous:
            api.SetThreadDpiAwarenessContext(previous)


if __name__ == "__main__":
    main()
