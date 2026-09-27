from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes


CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0x0
ERENDER = 0
DEVICE_STATE_ACTIVE = 0x1
RPC_E_CHANGED_MODE = 0x80010106


class Guid(ctypes.Structure):
    _fields_ = [
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, value: str) -> "Guid":
        raw = uuid.UUID(value).bytes_le
        return cls.from_buffer_copy(raw)


CLSID_MMDEVICE_ENUMERATOR = Guid.parse(
    "bcde0395-e52f-467c-8e3d-c4579291692e"
)
IID_IMMDEVICE_ENUMERATOR = Guid.parse(
    "a95664d2-9614-4f35-a746-de8db63617e6"
)
IID_AUDIO_SESSION_MANAGER2 = Guid.parse(
    "77aa99a0-1bd6-484f-8bc7-2c654c9a9b6f"
)
IID_AUDIO_SESSION_CONTROL2 = Guid.parse(
    "bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"
)
IID_SIMPLE_AUDIO_VOLUME = Guid.parse(
    "87ce5498-68d6-44e5-9215-6da47ef883d8"
)


ole32 = ctypes.WinDLL("ole32", use_last_error=True)
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = ctypes.c_long
ole32.CoUninitialize.argtypes = []
ole32.CoUninitialize.restype = None
ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(Guid),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(Guid),
    ctypes.POINTER(ctypes.c_void_p),
]
ole32.CoCreateInstance.restype = ctypes.c_long


def _failed(result: int) -> bool:
    return result < 0


def _call(
    interface: ctypes.c_void_p,
    index: int,
    *argtypes,
):
    table = ctypes.cast(
        interface,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    prototype = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_void_p,
        *argtypes,
    )
    return prototype(table[index])


def _release(interface: ctypes.c_void_p | None) -> None:
    if not interface or not interface.value:
        return
    release = _call(interface, 2)
    release(interface)


def _query_interface(
    interface: ctypes.c_void_p,
    interface_id: Guid,
) -> ctypes.c_void_p | None:
    result = ctypes.c_void_p()
    query = _call(
        interface,
        0,
        ctypes.POINTER(Guid),
        ctypes.POINTER(ctypes.c_void_p),
    )
    status = query(interface, ctypes.byref(interface_id), ctypes.byref(result))
    return None if _failed(status) else result


def _mute_device_sessions(device: ctypes.c_void_p, pid: int) -> int:
    manager = ctypes.c_void_p()
    sessions = ctypes.c_void_p()
    muted = 0
    try:
        activate = _call(
            device,
            3,
            ctypes.POINTER(Guid),
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        )
        status = activate(
            device,
            ctypes.byref(IID_AUDIO_SESSION_MANAGER2),
            CLSCTX_ALL,
            None,
            ctypes.byref(manager),
        )
        if _failed(status):
            return 0

        get_session_enumerator = _call(
            manager,
            5,
            ctypes.POINTER(ctypes.c_void_p),
        )
        status = get_session_enumerator(manager, ctypes.byref(sessions))
        if _failed(status):
            return 0

        count = ctypes.c_int()
        get_count = _call(
            sessions,
            3,
            ctypes.POINTER(ctypes.c_int),
        )
        if _failed(get_count(sessions, ctypes.byref(count))):
            return 0

        get_session = _call(
            sessions,
            4,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
        )
        for index in range(count.value):
            control = ctypes.c_void_p()
            control2 = None
            volume = None
            try:
                if _failed(
                    get_session(sessions, index, ctypes.byref(control))
                ):
                    continue
                control2 = _query_interface(
                    control,
                    IID_AUDIO_SESSION_CONTROL2,
                )
                if control2 is None:
                    continue
                session_pid = wintypes.DWORD()
                get_process_id = _call(
                    control2,
                    14,
                    ctypes.POINTER(wintypes.DWORD),
                )
                if _failed(
                    get_process_id(control2, ctypes.byref(session_pid))
                ):
                    continue
                if session_pid.value != pid:
                    continue
                volume = _query_interface(
                    control2,
                    IID_SIMPLE_AUDIO_VOLUME,
                )
                if volume is None:
                    continue
                set_mute = _call(
                    volume,
                    5,
                    wintypes.BOOL,
                    ctypes.c_void_p,
                )
                if not _failed(set_mute(volume, True, None)):
                    muted += 1
            finally:
                _release(volume)
                _release(control2)
                _release(control)
        return muted
    finally:
        _release(sessions)
        _release(manager)


def mute_process_audio_sessions(pid: int) -> int:
    """Mute every current Windows audio session owned by one process."""
    initialized = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
    should_uninitialize = not _failed(initialized)
    if _failed(initialized) and initialized & 0xFFFFFFFF != RPC_E_CHANGED_MODE:
        raise OSError(f"CoInitializeEx failed: 0x{initialized & 0xFFFFFFFF:08X}")

    enumerator = ctypes.c_void_p()
    devices = ctypes.c_void_p()
    muted = 0
    try:
        status = ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDEVICE_ENUMERATOR),
            None,
            CLSCTX_ALL,
            ctypes.byref(IID_IMMDEVICE_ENUMERATOR),
            ctypes.byref(enumerator),
        )
        if _failed(status):
            raise OSError(
                f"CoCreateInstance failed: 0x{status & 0xFFFFFFFF:08X}"
            )

        enum_endpoints = _call(
            enumerator,
            3,
            ctypes.c_int,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
        )
        status = enum_endpoints(
            enumerator,
            ERENDER,
            DEVICE_STATE_ACTIVE,
            ctypes.byref(devices),
        )
        if _failed(status):
            return 0

        count = wintypes.UINT()
        get_count = _call(
            devices,
            3,
            ctypes.POINTER(wintypes.UINT),
        )
        if _failed(get_count(devices, ctypes.byref(count))):
            return 0

        get_item = _call(
            devices,
            4,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
        )
        for index in range(count.value):
            device = ctypes.c_void_p()
            try:
                if _failed(get_item(devices, index, ctypes.byref(device))):
                    continue
                muted += _mute_device_sessions(device, pid)
            finally:
                _release(device)
        return muted
    finally:
        _release(devices)
        _release(enumerator)
        if should_uninitialize:
            ole32.CoUninitialize()
