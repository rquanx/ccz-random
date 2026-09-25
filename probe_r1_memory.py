from __future__ import annotations

import ctypes
import hashlib
import json
import os
import time
from ctypes import wintypes
from pathlib import Path

import cv2

import fast_randomizer as fr
from runtime_loader import install


GAME_DIR = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c"
)
GAME_EXE = GAME_DIR / "Ekd5.exe"
OUTPUT = Path(__file__).resolve().parent / "r1-probe"
S00_PATHS = (GAME_DIR / "S_00.eex", GAME_DIR / "RS" / "S_00.eex")
RANDOM_S00 = Path(__file__).resolve().parent / "random_s00.eex"


def write_memory(pid: int, offset: int, data: bytes) -> None:
    process_vm_write = 0x0020
    process_vm_operation = 0x0008
    handle = fr.kernel32.OpenProcess(
        fr.PROCESS_QUERY_INFORMATION | process_vm_write | process_vm_operation,
        False,
        pid,
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        count = ctypes.c_size_t()
        buffer = ctypes.create_string_buffer(data)
        if not fr.kernel32.WriteProcessMemory(
            handle,
            ctypes.c_void_p(fr.MEMORY_BASE + offset),
            buffer,
            len(data),
            ctypes.byref(count),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value != len(data):
            raise RuntimeError(f"内存写入不完整：{count.value}/{len(data)}")
    finally:
        fr.kernel32.CloseHandle(handle)


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    actual_r1 = os.environ.get("PROBE_ACTUAL_R1") == "1"
    use_old_save = os.environ.get("PROBE_OLD_SAVE") == "1"
    use_after_save = os.environ.get("PROBE_AFTER_SAVE") == "1"
    use_s00 = actual_r1 or os.environ.get("PROBE_USE_S00") == "1"
    original_s00 = {path: path.read_bytes() for path in S00_PATHS}
    original_hash = {
        path: hashlib.sha256(data).hexdigest()
        for path, data in original_s00.items()
    }
    save_path = GAME_DIR / "SV" / "SV001.E5S"
    original_save = save_path.read_bytes()
    renderer_save_path = GAME_DIR / "SV" / "SV018.E5S"
    original_renderer_save = (
        renderer_save_path.read_bytes()
        if renderer_save_path.is_file()
        else None
    )
    try:
        if use_s00:
            for path in S00_PATHS:
                path.write_bytes(RANDOM_S00.read_bytes())
        if use_after_save:
            render_file = Path(
                os.environ.get(
                    "PROBE_RENDER_FILE",
                    str(OUTPUT / "r1_renderer_template.E5S"),
                )
            )
            save_path.write_bytes(
                render_file.read_bytes()
            )
        elif use_old_save:
            save_path.write_bytes(
                (GAME_DIR / "随即工具" / "1" / "SV001.E5S").read_bytes()
            )
        install(fr.bundle_root())
        import task.CczReRandTask as task_module

        with fr.HiddenGameSession(GAME_EXE) as game:
            fr.patch_runtime(task_module, game.pid)
            runner = task_module.CczReRandTask(0)
            if not fr.title_load_verified(game.pid, 0, save_path):
                raise RuntimeError("第 1 号存档读取失败")
            time.sleep(1.5)
            capture_size = save_path.stat().st_size
            before = fr.read_memory(game.pid, 0, capture_size)
            (OUTPUT / "before.bin").write_bytes(before)

            if actual_r1:
                fr.run_native_control(
                    game.pid,
                    [
                        "silent-click",
                        str(game.main_window),
                        str(fr.XU_CLIENT_POSITION[0]),
                        str(fr.XU_CLIENT_POSITION[1]),
                    ],
                )
                for _ in range(4):
                    fr.run_native_control(
                        game.pid,
                        [
                            "silent-burst",
                            str(game.main_window),
                            str(fr.CONFIRM_FIRST_CLIENT_POSITION[0]),
                            str(fr.CONFIRM_FIRST_CLIENT_POSITION[1]),
                            "20",
                        ],
                    )
                    fr.native_wake_game(game.pid, game.main_window, 1000)
                (OUTPUT / "after.bin").write_bytes(
                    fr.read_memory(game.pid, 0, capture_size)
                )
                renderer_mtime = (
                    renderer_save_path.stat().st_mtime_ns
                    if renderer_save_path.is_file()
                    else None
                )
                fr.native_direct_save(game.pid, 17)
                save_deadline = time.perf_counter() + 5
                while time.perf_counter() < save_deadline:
                    if (
                        renderer_save_path.is_file()
                        and renderer_save_path.stat().st_mtime_ns
                        != renderer_mtime
                    ):
                        break
                    time.sleep(0.1)
                if (
                    not renderer_save_path.is_file()
                    or renderer_save_path.stat().st_mtime_ns
                    == renderer_mtime
                ):
                    raise RuntimeError("R1 渲染模板保存失败")
                (OUTPUT / "r1_renderer_template.E5S").write_bytes(
                    renderer_save_path.read_bytes()
                )
                runner.initWind()
                cv2.imwrite(
                    str(OUTPUT / "scene-actual.png"),
                    runner.wind.getMat(),
                )
            elif not use_after_save:
                template_before = (OUTPUT / "before.bin").read_bytes()
                template_after = (OUTPUT / "after.bin").read_bytes()
                offsets = [
                    index
                    for index, (left, right) in enumerate(
                        zip(template_before, template_after)
                    )
                    if left != right
                ]
                for offset in offsets:
                    write_memory(
                        game.pid,
                        offset,
                        template_after[offset : offset + 1],
                    )
                time.sleep(0.5)

            runner.initWind()
            cv2.imwrite(
                str(OUTPUT / "scene-before-open.png"),
                fr.print_window_mat(runner.wind.hwnd),
            )
            runner.openPeople()
            fr.native_wake_game(game.pid, game.main_window, 1500)
            time.sleep(1)
            runner.initPeopleWind()
            if runner.peopleWind.isInitSuccess():
                suffix = "actual" if actual_r1 else "patched"
                cv2.imwrite(
                    str(OUTPUT / f"people-{suffix}.png"),
                    runner.peopleWind.getMat(),
                )
                cv2.imwrite(
                    str(OUTPUT / f"jobs-{suffix}.png"),
                    runner.peopleWind.getPeopleJobRangeMat(7),
                )
                if actual_r1 or (use_after_save and use_s00):
                    for probe_y in (
                        129,
                        189,
                        249,
                        309,
                        369,
                        429,
                        489,
                    ):
                        fr.native_background_click(
                            runner.peopleWind.hwnd,
                            60,
                            probe_y,
                            1,
                            False,
                        )
                        time.sleep(0.7)
                        windows = [
                            (fr.window_class(hwnd), fr.window_text(hwnd))
                            for hwnd in fr.process_windows(game.pid)
                        ]
                        print("点击", probe_y, "窗口:", windows)
                        if any("武将情报" in title for _, title in windows):
                            break
                    runner.initPeopleInfoWind()
                    if runner.peopleInfoWind.isInitSuccess():
                        cv2.imwrite(
                            str(OUTPUT / "people-info-actual.png"),
                            runner.peopleInfoWind.getMat(),
                        )
                    runner._getTeamSkillsInfo()
                    skill_dump = [
                        {
                            "name": member.name,
                            "job": getattr(member.job, "name", ""),
                            "skills": [
                                {
                                    "name": skill.name,
                                    "score": skill.score,
                                    "type": skill.type.value,
                                }
                                for skill in member.skillList
                            ],
                        }
                        for member in task_module.TEAM_MEMBER_LIST
                    ]
                    (OUTPUT / "skills-actual.json").write_text(
                        json.dumps(skill_dump, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                print("人员窗口截图完成")
            else:
                print("人员窗口未能打开")
    finally:
        if use_old_save or use_after_save:
            save_path.write_bytes(original_save)
        if original_renderer_save is None:
            renderer_save_path.unlink(missing_ok=True)
        else:
            renderer_save_path.write_bytes(original_renderer_save)
        if use_s00:
            for path, data in original_s00.items():
                path.write_bytes(data)
                if hashlib.sha256(path.read_bytes()).hexdigest() != original_hash[path]:
                    raise RuntimeError(f"{path} 恢复校验失败")


if __name__ == "__main__":
    main()
