"""Launch GUI tests on a private desktop without switching the user's desktop."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
import subprocess
import uuid


@contextmanager
def background_desktop():
    if os.name != "nt":
        yield None
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
                                     wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    name = "ccz-tests-" + uuid.uuid4().hex
    handle = user32.CreateDesktopW(name, None, None, 0, 0x01ff, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        startup = subprocess.STARTUPINFO()
        startup.lpDesktop = name
        yield startup
    finally:
        user32.CloseDesktop(handle)
