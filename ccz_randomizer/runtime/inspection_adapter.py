"""Legacy game runtime adapter; dependencies are captured for one worker session."""
from __future__ import annotations
from pathlib import Path


def patch_inspection_runtime(task_module, pid: int, panel_dir: Path, *, services):
    BM_CLICK = services.BM_CLICK
    NativeControlError = services.NativeControlError
    NativeControlTimeout = services.NativeControlTimeout
    Point = services.Point
    ctypes = services.ctypes
    diagnostic_log = services.diagnostic_log
    find_process_window = services.find_process_window
    inspection_background_click = services.inspection_background_click
    interruptible_sleep = services.interruptible_sleep
    native_silent_click = services.native_silent_click
    native_silent_click_burst = services.native_silent_click_burst
    native_wake_game = services.native_wake_game
    os = services.os
    post_click = services.post_click
    post_key_to_game = services.post_key_to_game
    print_window_mat = services.print_window_mat
    process_windows = services.process_windows
    run_native_control = services.run_native_control
    time = services.time
    user32 = services.user32
    window_class = services.window_class
    window_text = services.window_text
    wintypes = services.wintypes
    from window.BaseWindow import BaseWindow
    from window.CczWindow import CczPeopleWindow

    panels: list[np.ndarray] = []

    def get_hwnd_by_name(self, window_name: str) -> None:
        self._BaseWindow__hwnd = find_process_window(pid, window_name)

    def no_foreground(self) -> None:
        return None

    def background_click_rect(
        self, x: int, y: int, w: int, h: int, rightClick: bool = False
    ) -> None:
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            return
        client_x = x + w // 2
        client_y = y + h // 2
        if os.environ.get(
            "CCZ_INSPECTION_FORCE_INJECTED_STORY_CLICK"
        ) == "1":
            inspection_background_click(
                pid,
                self.hwnd,
                client_x,
                client_y,
                right=rightClick,
            )
            return
        rect = wintypes.RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return
        post_click(
            self.hwnd,
            rect.left + client_x,
            rect.top + client_y,
            right=rightClick,
        )
        diagnostic_log(
            "inspection_click_rect",
            pid=pid,
            hwnd=self.hwnd,
            client_point=(client_x, client_y),
            right=rightClick,
            method="post_message",
        )

    def window_mat(
        self,
        x: int = 0,
        y: int = 0,
        w: int = 0,
        h: int = 0,
        toGray: bool = False,
    ):
        mat = print_window_mat(
            self.hwnd, x, y, w, h, strip_client=False
        )
        if toGray:
            task_module.CvUtils.transNotBlackToWhite(mat, 100)
        return mat

    def click_people(self, index: int) -> None:
        run_native_control(
            pid, ["list-window", str(self.hwnd), str(index)]
        )
        interruptible_sleep(0.6)

    def open_people(self) -> None:
        self.initWind()
        if not self.wind.isInitSuccess():
            raise RuntimeError("候选检查阶段未找到游戏主窗口")
        for attempt in range(1, 5):
            self.initPeopleWind()
            if self.peopleWind.isInitSuccess():
                return
            native_wake_game(pid, self.wind.hwnd, 600)
            method = "silent_click"
            try:
                if attempt == 1:
                    native_silent_click(
                        pid,
                        self.wind.hwnd,
                        138,
                        18,
                        tail_delay_ms=350,
                    )
                elif attempt == 2:
                    method = "silent_burst"
                    native_silent_click_burst(
                        self.wind.hwnd,
                        138,
                        18,
                        2,
                    )
                else:
                    # The original synchronous click works on most systems,
                    # but is kept behind non-blocking methods because it can
                    # stall inside the game window procedure on some devices.
                    method = "synchronous_click"
                    point = Point(138, 18)
                    user32.ClientToScreen(
                        self.wind.hwnd, ctypes.byref(point)
                    )
                    post_click(self.wind.hwnd, point.x, point.y)
                diagnostic_log(
                    "inspection_roster_open_click",
                    pid=pid,
                    hwnd=self.wind.hwnd,
                    attempt=attempt,
                    method=method,
                )
            except (NativeControlError, NativeControlTimeout) as exc:
                # A direct queued click is a weaker final fallback, but cannot
                # stall the inspection process.
                lparam = (18 << 16) | 138
                user32.PostMessageW(
                    self.wind.hwnd, 0x0201, 0x0001, lparam
                )
                user32.PostMessageW(
                    self.wind.hwnd, 0x0202, 0, lparam
                )
                diagnostic_log(
                    "inspection_roster_open_click_fallback",
                    pid=pid,
                    hwnd=self.wind.hwnd,
                    attempt=attempt,
                    error=repr(exc),
                    failed_method=method,
                    method="post_message",
                )
            deadline = time.perf_counter() + 3.0
            while time.perf_counter() < deadline:
                interruptible_sleep(0.15)
                self.initPeopleWind()
                if self.peopleWind.isInitSuccess():
                    print(f"候选武将列表第 {attempt} 次尝试打开成功")
                    return
            print(f"候选武将列表第 {attempt}/4 次尝试未打开")
            native_silent_click_burst(self.wind.hwnd, 360, 400, 12)
            native_wake_game(pid, self.wind.hwnd, 800)
        windows = [
            {
                "class": window_class(hwnd),
                "title": window_text(hwnd),
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "enabled": bool(user32.IsWindowEnabled(hwnd)),
            }
            for hwnd in process_windows(pid, visible_only=False)
        ]
        raise RuntimeError(
            "候选存档的武将列表连续4次未能打开；"
            f"当前窗口={windows}"
        )

    def click_info_button(hwnd: int, from_right: int) -> None:
        buttons: list[tuple[int, int]] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def callback(child: int, _param: int) -> bool:
            if window_class(child) == "Button":
                rect = wintypes.RECT()
                if user32.GetWindowRect(child, ctypes.byref(rect)):
                    buttons.append((rect.left, child))
            return True

        user32.EnumChildWindows(hwnd, callback, 0)
        if len(buttons) < from_right:
            raise RuntimeError("武将能力窗口按钮不完整")
        buttons.sort()
        target_button = buttons[-from_right]
        user32.PostMessageW(target_button[1], BM_CLICK, 0, 0)

    BaseWindow.setForeground = no_foreground
    BaseWindow._BaseWindow__getHwndbyName = get_hwnd_by_name
    BaseWindow.clickRect = background_click_rect
    BaseWindow.moveMouseToEnd = no_foreground
    BaseWindow.getMat = window_mat
    CczPeopleWindow.clickPeople = click_people
    task_module.KeyboardUtils.tapKey = lambda key: post_key_to_game(pid, key)
    task_module.CczReRandTask.openPeople = open_people
    return panels, click_info_button

