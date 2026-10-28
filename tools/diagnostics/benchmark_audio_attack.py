from __future__ import annotations

import argparse
import ctypes
import json
import os
import threading
import time
import winreg
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

import cv2
from pycaw.api.endpointvolume import IAudioMeterInformation
from pycaw.utils import AudioUtilities

import fast_randomizer as fast
from runtime_loader import install


DEFAULT_GAME = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c"
    r"\曹操传加强版V2.10.4c\Ekd5.exe"
)
BM_CLICK = 0x00F5
BM_GETCHECK = 0x00F0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_NULL = 0x0000
WM_COMMAND = 0x0111
VK_RETURN = 0x0D
PAGE_SIZE = 20
SMTO_ABORTIFHUNG = 0x0002
SETTINGS_COMMAND = 107
BACKGROUND_MUSIC_CONTROL = 1030
SOUND_EFFECTS_CONTROL = 1031
ATTACK_CONTROL = 1287
DIRECTSOUND_CLSIDS = (
    "{47D4D946-62E8-11CF-93BC-444553540000}",
    "{3901CC3F-84B5-4FA4-BA35-AA8172B8A09B}",
)
DIRECTSOUND_REGISTRY_ROOTS = (
    r"Software\Classes\CLSID",
    r"Software\Classes\WOW6432Node\CLSID",
)


@contextmanager
def indirectsound_registry_override(enabled: bool):
    if not enabled:
        yield
        return

    backups: list[tuple[str, bool, object | None, int | None]] = []
    for root in DIRECTSOUND_REGISTRY_ROOTS:
        for clsid in DIRECTSOUND_CLSIDS:
            path = rf"{root}\{clsid}\InprocServer32"
            existed = False
            value = None
            value_type = None
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    path,
                    access=winreg.KEY_READ,
                ) as key:
                    existed = True
                    try:
                        value, value_type = winreg.QueryValueEx(key, "")
                    except FileNotFoundError:
                        pass
            except FileNotFoundError:
                pass
            backups.append((path, existed, value, value_type))
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                path,
                access=winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "dsound.dll")
    try:
        yield
    finally:
        for path, existed, value, value_type in reversed(backups):
            if existed:
                with winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER,
                    path,
                    access=winreg.KEY_SET_VALUE,
                ) as key:
                    if value_type is None:
                        try:
                            winreg.DeleteValue(key, "")
                        except FileNotFoundError:
                            pass
                    else:
                        winreg.SetValueEx(key, "", 0, value_type, value)
                continue
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except OSError:
                pass
            parent = path.rsplit("\\", 1)[0]
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, parent)
            except OSError:
                pass


def capture(runner, path: Path) -> None:
    frame = runner.wind.getMat()
    encoded, data = cv2.imencode(".png", frame)
    if not encoded:
        raise RuntimeError(f"截图编码失败：{path}")
    data.tofile(path)


def load_battle_save(game: fast.HiddenGameSession, slot: int) -> None:
    page = (slot - 1) // PAGE_SIZE
    item_index = (slot - 1) % PAGE_SIZE
    if page >= 10:
        raise ValueError("诊断脚本目前只支持前 10 页存档")

    fast.native_silent_click(
        game.pid,
        game.main_window,
        fast.TITLE_LOAD_CLIENT_POSITION[0],
        fast.TITLE_LOAD_CLIENT_POSITION[1],
        tail_delay_ms=300,
    )
    dialog = fast.wait_list_dialog(game.pid, 3)
    if not dialog:
        raise RuntimeError("读取进度窗口未出现")

    page_button = fast.user32.GetDlgItem(dialog, 9 + page)
    if not page_button:
        raise RuntimeError(f"未找到第 {page + 1} 页按钮")
    fast.user32.SendMessageW(page_button, BM_CLICK, 0, 0)
    time.sleep(0.3)
    fast.run_native_control(game.pid, ["list", str(item_index)])

    deadline = time.perf_counter() + 12
    while time.perf_counter() < deadline:
        for hwnd in fast.process_windows(game.pid):
            if hwnd == dialog or fast.window_class(hwnd) != "#32770":
                continue
            fast.click_leftmost_dialog_button(hwnd)
        if (
            not fast.user32.IsWindow(dialog)
            and fast.user32.IsWindowEnabled(game.main_window)
        ):
            fast.native_wake_game(game.pid, game.main_window, 5000)
            return
        time.sleep(0.05)
    raise RuntimeError(f"第 {slot:03d} 号存档读取超时")


def child_windows(hwnd: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    @callback_type
    def callback(child: int, _param: int) -> bool:
        rect = wintypes.RECT()
        fast.user32.GetWindowRect(child, ctypes.byref(rect))
        rows.append(
            {
                "hwnd": child,
                "class": fast.window_class(child),
                "text": fast.window_text(child),
                "controlId": fast.user32.GetDlgCtrlID(child),
                "visible": bool(fast.user32.IsWindowVisible(child)),
                "rect": [rect.left, rect.top, rect.right, rect.bottom],
            }
        )
        return True

    fast.user32.EnumChildWindows(hwnd, callback, 0)
    return rows


def window_snapshot(pid: int) -> list[dict[str, object]]:
    result = []
    for hwnd in fast.process_windows(pid, visible_only=False):
        rect = wintypes.RECT()
        fast.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        result.append(
            {
                "hwnd": hwnd,
                "class": fast.window_class(hwnd),
                "text": fast.window_text(hwnd),
                "visible": bool(fast.user32.IsWindowVisible(hwnd)),
                "enabled": bool(fast.user32.IsWindowEnabled(hwnd)),
                "rect": [rect.left, rect.top, rect.right, rect.bottom],
                "children": child_windows(hwnd),
            }
        )
    return result


def visible_dialog_with_control(pid: int, control_id: int) -> int:
    for hwnd in fast.process_windows(pid):
        if (
            fast.window_class(hwnd) == "#32770"
            and fast.user32.GetDlgItem(hwnd, control_id)
        ):
            return hwnd
    return 0


def configure_audio(
    game: fast.HiddenGameSession,
    *,
    background_music: bool | None = None,
    sound_effects: bool | None = None,
) -> dict[str, bool]:
    fast.user32.PostMessageW(
        game.main_window,
        WM_COMMAND,
        SETTINGS_COMMAND,
        0,
    )
    deadline = time.perf_counter() + 3
    dialog = 0
    while time.perf_counter() < deadline:
        dialog = visible_dialog_with_control(
            game.pid,
            SOUND_EFFECTS_CONTROL,
        )
        if dialog:
            break
        time.sleep(0.05)
    if not dialog:
        raise RuntimeError("环境设置窗口未出现")

    controls = {
        "backgroundMusic": BACKGROUND_MUSIC_CONTROL,
        "soundEffects": SOUND_EFFECTS_CONTROL,
    }
    previous: dict[str, bool] = {}
    desired = {
        "backgroundMusic": background_music,
        "soundEffects": sound_effects,
    }
    for name, control_id in controls.items():
        control = fast.user32.GetDlgItem(dialog, control_id)
        checked = bool(fast.user32.SendMessageW(control, BM_GETCHECK, 0, 0))
        previous[name] = checked
        if desired[name] is not None and checked != desired[name]:
            fast.user32.SendMessageW(control, BM_CLICK, 0, 0)
    confirmed = fast.user32.GetDlgItem(dialog, 1)
    fast.user32.SendMessageW(confirmed, BM_CLICK, 0, 0)
    deadline = time.perf_counter() + 3
    while time.perf_counter() < deadline:
        if not fast.user32.IsWindow(dialog):
            fast.native_wake_game(
                game.pid,
                game.main_window,
                800,
            )
            return previous
        time.sleep(0.05)
    raise RuntimeError("环境设置窗口未关闭")


def process_audio_meter(pid: int):
    return [
        session._ctl.QueryInterface(IAudioMeterInformation)
        for session in AudioUtilities.GetAllSessions()
        if session.ProcessId == pid
    ]


def validate_attack_result(
    result: dict[str, object],
    *,
    expect_audio: bool,
) -> None:
    attack = result["attack"]
    responsiveness = attack["responsiveness"]
    if responsiveness["frameChanges"] <= 0:
        raise RuntimeError("攻击动作未产生画面变化")
    if responsiveness["maxMessageMs"] > 50:
        raise RuntimeError(
            "游戏主线程仍存在明显停顿："
            f"{responsiveness['maxMessageMs']:.3f} ms"
        )
    if expect_audio and responsiveness["maxAudioPeak"] <= 0.001:
        raise RuntimeError("攻击期间未检测到游戏音频输出")
    if (
        expect_audio
        and (
            responsiveness["firstAudioMs"] is None
            or responsiveness["firstAudioMs"] > 250
        )
    ):
        raise RuntimeError(
            "攻击音效启动过晚："
            f"{responsiveness['firstAudioMs']} ms"
        )


def validate_move_result(result: dict[str, object]) -> None:
    move = result["move"]
    segments = move["activeSegmentsMs"]
    if not segments:
        raise RuntimeError("移动期间未检测到音效")
    if len(segments) != 1:
        raise RuntimeError(
            f"移动音效被重复播放：检测到 {len(segments)} 个播放段"
        )


def click(
    game: fast.HiddenGameSession,
    x: int,
    y: int,
    *,
    count: int = 1,
    delay: float = 0.5,
) -> None:
    for _ in range(count):
        fast.native_silent_click(
            game.pid,
            game.main_window,
            x,
            y,
            tail_delay_ms=100,
        )
    fast.native_wake_game(
        game.pid,
        game.main_window,
        max(80, int(delay * 1000)),
    )


def press_enter(game: fast.HiddenGameSession, delay: float = 0.5) -> None:
    fast.user32.PostMessageW(game.main_window, WM_KEYDOWN, VK_RETURN, 0)
    fast.user32.PostMessageW(game.main_window, WM_KEYUP, VK_RETURN, 0)
    fast.native_wake_game(
        game.pid,
        game.main_window,
        max(80, int(delay * 1000)),
    )


def frame_signature(frame) -> str:
    reduced = cv2.resize(
        frame[100:, :],
        (64, 64),
        interpolation=cv2.INTER_AREA,
    )
    gray = cv2.cvtColor(reduced, cv2.COLOR_BGR2GRAY)
    return gray.tobytes().hex()


def sample_responsiveness(
    game: fast.HiddenGameSession,
    runner,
    *,
    duration: float,
    output_dir: Path,
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    started = time.perf_counter()
    previous_signature = ""
    frame_changes = 0
    max_message_ms = 0.0
    max_audio_peak = 0.0
    first_audio_ms: float | None = None
    audio_meter = None
    while True:
        elapsed = time.perf_counter() - started
        if elapsed >= duration:
            break
        message_result = ctypes.c_size_t()
        message_started = time.perf_counter()
        responded = bool(
            fast.user32.SendMessageTimeoutW(
                game.main_window,
                WM_NULL,
                0,
                0,
                SMTO_ABORTIFHUNG,
                1000,
                ctypes.byref(message_result),
            )
        )
        message_ms = (time.perf_counter() - message_started) * 1000
        max_message_ms = max(max_message_ms, message_ms)
        frame = runner.wind.getMat()
        signature = frame_signature(frame)
        changed = bool(previous_signature and signature != previous_signature)
        frame_changes += int(changed)
        previous_signature = signature
        if not audio_meter:
            audio_meter = process_audio_meter(game.pid)
        audio_peak = max(
            (
                float(meter.GetPeakValue())
                for meter in audio_meter
            ),
            default=0.0,
        )
        max_audio_peak = max(max_audio_peak, audio_peak)
        if first_audio_ms is None and audio_peak > 0.001:
            first_audio_ms = elapsed * 1000
        samples.append(
            {
                "elapsedMs": round(elapsed * 1000, 3),
                "messageMs": round(message_ms, 3),
                "responded": responded,
                "frameChanged": changed,
                "audioPeak": round(audio_peak, 6),
            }
        )
        time.sleep(0.02)
    capture(runner, output_dir / "attack-finished.png")
    return {
        "sampleCount": len(samples),
        "frameChanges": frame_changes,
        "maxMessageMs": round(max_message_ms, 3),
        "maxAudioPeak": round(max_audio_peak, 6),
        "firstAudioMs": (
            round(first_audio_ms, 3)
            if first_audio_ms is not None
            else None
        ),
        "samples": samples,
    }


def run_attack(
    game: fast.HiddenGameSession,
    runner,
    output_dir: Path,
) -> dict[str, object]:
    click(game, 458, 850)
    click(game, 458, 753)
    action_dialog = visible_dialog_with_control(game.pid, ATTACK_CONTROL)
    if not action_dialog:
        raise RuntimeError("移动后攻击命令窗口未出现")
    capture(runner, output_dir / "before-attack-command.png")
    fast.user32.SendMessageW(
        fast.user32.GetDlgItem(action_dialog, ATTACK_CONTROL),
        BM_CLICK,
        0,
        0,
    )
    time.sleep(0.2)
    capture(runner, output_dir / "attack-targeting.png")

    target_started = time.perf_counter()
    fast.native_silent_click(
        game.pid,
        game.main_window,
        458,
        706,
        tail_delay_ms=0,
    )
    click_return_ms = (time.perf_counter() - target_started) * 1000
    responsiveness = sample_responsiveness(
        game,
        runner,
        duration=6.0,
        output_dir=output_dir,
    )
    return {
        "targetClickReturnMs": round(click_return_ms, 3),
        "responsiveness": responsiveness,
    }


def run_move(
    game: fast.HiddenGameSession,
    runner,
    output_dir: Path,
) -> dict[str, object]:
    click(game, 458, 850)
    audio_meter = process_audio_meter(game.pid)
    samples: list[dict[str, float]] = []
    click_result: dict[str, float] = {}

    def move_unit() -> None:
        started = time.perf_counter()
        fast.native_silent_click(
            game.pid,
            game.main_window,
            458,
            753,
            tail_delay_ms=0,
        )
        click_result["returnMs"] = (
            time.perf_counter() - started
        ) * 1000

    started = time.perf_counter()
    worker = threading.Thread(target=move_unit)
    worker.start()
    while time.perf_counter() - started < 2.5:
        elapsed = time.perf_counter() - started
        peak = max(
            (float(meter.GetPeakValue()) for meter in audio_meter),
            default=0.0,
        )
        samples.append(
            {
                "elapsedMs": round(elapsed * 1000, 3),
                "audioPeak": round(peak, 6),
            }
        )
        time.sleep(0.01)
    worker.join(timeout=3)
    if worker.is_alive():
        raise RuntimeError("移动点击未返回")
    capture(runner, output_dir / "move-finished.png")

    active = [
        sample["elapsedMs"]
        for sample in samples
        if sample["audioPeak"] > 0.001
    ]
    segments: list[list[float]] = []
    for elapsed in active:
        if not segments or elapsed - segments[-1][1] > 100:
            segments.append([elapsed, elapsed])
        else:
            segments[-1][1] = elapsed
    return {
        "clickReturnMs": round(click_result.get("returnMs", 0.0), 3),
        "activeSegmentsMs": [
            {
                "start": round(segment[0], 3),
                "end": round(segment[1], 3),
                "duration": round(segment[1] - segment[0], 3),
            }
            for segment in segments
        ],
        "samples": samples,
    }


def run_probe(
    game: fast.HiddenGameSession,
    runner,
    output_dir: Path,
) -> dict[str, object]:
    steps = [
        ("initial", None),
        ("unit", lambda: click(game, 458, 850)),
        ("destination", lambda: click(game, 458, 753)),
        ("enter", lambda: press_enter(game)),
        ("destination-again", lambda: click(game, 458, 753)),
        ("right-click", lambda: fast.native_background_click(
            game.main_window, 458, 753, 1, True
        )),
    ]
    result: dict[str, object] = {}
    for name, action in steps:
        if action is not None:
            action()
            time.sleep(0.3)
        capture(runner, output_dir / f"{name}.png")
        result[name] = window_snapshot(game.pid)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--slot", type=int, default=78)
    parser.add_argument(
        "--sound-effects",
        choices=("on", "off"),
        default="off",
    )
    parser.add_argument(
        "--background-music",
        choices=("on", "off"),
        default="off",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--attack", action="store_true")
    action.add_argument("--move", action="store_true")
    parser.add_argument("--indirectsound-registry", action="store_true")
    parser.add_argument("--async-sound-hook", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "audio-attack-probe",
    )
    args = parser.parse_args()

    game_executable = args.game.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CCZ_DISABLE_AUDIO_MUTE"] = "1"

    with indirectsound_registry_override(args.indirectsound_registry):
        with fast.HiddenGameSession(game_executable) as game:
            time.sleep(3)
            if args.async_sound_hook:
                fast.run_native_control(game.pid, ["async-sound"])
            original_audio = configure_audio(
                game,
                background_music=args.background_music == "on",
                sound_effects=args.sound_effects == "on",
            )
            try:
                load_battle_save(game, args.slot)
                install(fast.bundle_root())
                import task.CczReRandTask as task_module

                fast.patch_runtime(task_module, game.pid)
                runner = task_module.CczReRandTask(0)
                runner.initWind()
                if args.attack or args.move:
                    result = {
                        "slot": args.slot,
                        "backgroundMusic": args.background_music,
                        "soundEffects": args.sound_effects,
                        "indirectSoundRegistry": args.indirectsound_registry,
                        "asyncSoundHook": args.async_sound_hook,
                    }
                    if args.attack:
                        result["attack"] = run_attack(
                            game,
                            runner,
                            output_dir,
                        )
                    else:
                        result["move"] = run_move(
                            game,
                            runner,
                            output_dir,
                        )
                else:
                    result = run_probe(game, runner, output_dir)
            finally:
                configure_audio(
                    game,
                    background_music=original_audio["backgroundMusic"],
                    sound_effects=original_audio["soundEffects"],
                )

    (output_dir / "probe.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.verify:
        if args.attack:
            validate_attack_result(
                result,
                expect_audio=args.sound_effects == "on",
            )
        elif args.move:
            validate_move_result(result)
        else:
            raise ValueError("--verify 需要与 --attack 或 --move 一起使用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
