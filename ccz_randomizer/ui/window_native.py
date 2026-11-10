"""Windows placement using one DPI coordinate context throughout."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from functools import lru_cache


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD)]


class WindowsPlacement:
    def __init__(self):
        self.api = api = ctypes.WinDLL("user32", use_last_error=True)
        api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        api.GetAncestor.restype = wintypes.HWND
        api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        api.MonitorFromWindow.restype = wintypes.HANDLE
        api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)]
        api.GetMonitorInfoW.restype = wintypes.BOOL
        api.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        api.GetWindowRect.restype = wintypes.BOOL
        api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        api.SetWindowPos.restype = wintypes.BOOL

    def _handle(self, window):
        # Tk's winfo_id is the client child, not the decorated outer window.
        handle = self.api.GetAncestor(window.winfo_id(), 2)  # GA_ROOT
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def work_area(self, parent):
        monitor = self.api.MonitorFromWindow(self._handle(parent.winfo_toplevel()), 2)
        info = _MonitorInfo()
        info.size = ctypes.sizeof(info)
        if not self.api.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        rect = info.work
        return rect.left, rect.top, rect.right, rect.bottom

    def bounds(self, window):
        rect = wintypes.RECT()
        if not self.api.GetWindowRect(self._handle(window), ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        return rect.left, rect.top, rect.right, rect.bottom

    def move(self, window, x, y):
        # Negative monitor origins are native absolute coordinates, not Tk's
        # right-edge geometry syntax. Keep activation and stacking unchanged.
        if not self.api.SetWindowPos(self._handle(window), None, x, y, 0, 0,
                                     0x0001 | 0x0004 | 0x0010):
            raise ctypes.WinError(ctypes.get_last_error())


@lru_cache(maxsize=1)
def native_placement():
    return WindowsPlacement() if os.name == "nt" else None
