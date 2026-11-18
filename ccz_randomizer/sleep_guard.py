"""Thread-owned Windows idle sleep request; never change the power plan."""
import ctypes

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def execution_state(flags):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    setter = kernel.SetThreadExecutionState
    setter.argtypes = [ctypes.c_uint32]
    setter.restype = ctypes.c_uint32
    previous = setter(flags)
    if not previous:
        raise OSError('Windows 未能设置防睡眠状态')
    return previous


class SleepGuard:
    """Acquire/release on the GUI thread, including launch failure and exit."""
    def __init__(self, setter=None):
        self._setter = setter or execution_state
        self._previous = None

    def start(self):
        if self._previous is None:
            self._previous = self._setter(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)

    def close(self):
        if self._previous is not None:
            self._setter(self._previous | ES_CONTINUOUS)
            self._previous = None
