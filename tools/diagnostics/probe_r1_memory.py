from __future__ import annotations

import ctypes
import hashlib
import json
import os
import struct
import time
from ctypes import wintypes
from pathlib import Path

import cv2

import fast_randomizer as fr
from runtime_loader import install
from tools.project_paths import APP_RESOURCES_DIR, ARTIFACTS_DIR


GAME_DIR = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c"
)
GAME_EXE = GAME_DIR / "Ekd5.exe"
OUTPUT = ARTIFACTS_DIR / "r1-probe"
S00_PATHS = (GAME_DIR / "S_00.eex", GAME_DIR / "RS" / "S_00.eex")
RANDOM_S00 = APP_RESOURCES_DIR / "random_s00.eex"
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
WRITABLE_PAGE_PROTECTIONS = {0x04, 0x08, 0x40, 0x80}
MODULE_ADDRESS_START = 0x00400000
MODULE_ADDRESS_END = 0x00645000


class MemoryBasicInformation(ctypes.Structure):
    _fields_ = (
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    )


def readable_writable_regions(pid: int):
    handle = fr.kernel32.OpenProcess(
        fr.PROCESS_QUERY_INFORMATION | fr.PROCESS_VM_READ,
        False,
        pid,
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        address = 0
        info = MemoryBasicInformation()
        while address < 0x80000000:
            queried = fr.kernel32.VirtualQueryEx(
                handle,
                ctypes.c_void_p(address),
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not queried:
                break
            base = int(info.BaseAddress or 0)
            size = int(info.RegionSize)
            protect = int(info.Protect)
            if (
                info.State == MEM_COMMIT
                and not protect & PAGE_GUARD
                and protect & 0xFF in WRITABLE_PAGE_PROTECTIONS
                and 0 < size <= 128 * 1024 * 1024
            ):
                yield handle, base, size
            next_address = base + max(size, 0x1000)
            if next_address <= address:
                break
            address = next_address
    finally:
        fr.kernel32.CloseHandle(handle)


def read_process_region(handle, base: int, size: int) -> bytes | None:
    buffer = ctypes.create_string_buffer(size)
    count = ctypes.c_size_t()
    if not fr.kernel32.ReadProcessMemory(
        handle,
        ctypes.c_void_p(base),
        buffer,
        size,
        ctypes.byref(count),
    ):
        return None
    if count.value != size:
        return None
    return buffer.raw


def read_absolute_memory(pid: int, address: int, size: int) -> bytes | None:
    handle = fr.kernel32.OpenProcess(
        fr.PROCESS_QUERY_INFORMATION | fr.PROCESS_VM_READ,
        False,
        pid,
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return read_process_region(handle, address, size)
    finally:
        fr.kernel32.CloseHandle(handle)


def direct_skill_slot_candidates(
    pid: int,
    slot_ids: list[int | None],
) -> dict[str, list[str]]:
    populated = [
        (index, model_id)
        for index, model_id in enumerate(slot_ids)
        if model_id is not None
    ]
    if len({model_id for _, model_id in populated}) < 2:
        return {}

    configurations = (
        (1, 1),
        (1, 2),
        (1, 4),
        (2, 2),
        (2, 4),
        (2, 8),
        (4, 4),
        (4, 8),
        (4, 16),
    )
    formats = {1: "<B", 2: "<H", 4: "<I"}
    candidates = {
        f"u{width * 8}_stride_{stride}": set()
        for width, stride in configurations
    }

    for handle, region_base, region_size in readable_writable_regions(pid):
        data = read_process_region(handle, region_base, region_size)
        if data is None:
            continue
        for width, stride in configurations:
            first_slot, first_id = populated[0]
            token = struct.pack(formats[width], first_id)
            position = data.find(token)
            key = f"u{width * 8}_stride_{stride}"
            while position >= 0:
                base_offset = position - first_slot * stride
                if (
                    base_offset >= 0
                    and base_offset + (len(slot_ids) - 1) * stride + width
                    <= len(data)
                    and (region_base + base_offset) % width == 0
                ):
                    matches = True
                    for slot_index, model_id in populated[1:]:
                        value = struct.unpack_from(
                            formats[width],
                            data,
                            base_offset + slot_index * stride,
                        )[0]
                        if value != model_id:
                            matches = False
                            break
                    if matches:
                        candidates[key].add(region_base + base_offset)
                position = data.find(token, position + 1)

    return {
        key: [f"0x{address:08X}" for address in sorted(addresses)]
        for key, addresses in candidates.items()
        if addresses
    }


def snapshot_module_writable_memory(pid: int) -> dict[int, bytes]:
    snapshot = {}
    for handle, region_base, region_size in readable_writable_regions(pid):
        region_end = region_base + region_size
        start = max(region_base, MODULE_ADDRESS_START)
        end = min(region_end, MODULE_ADDRESS_END)
        if start >= end:
            continue
        data = read_process_region(handle, start, end - start)
        if data is not None:
            snapshot[start] = data
    return snapshot


def analyze_module_transitions(
    snapshots: list[dict[int, bytes]],
) -> dict:
    if len(snapshots) < 2:
        return {}

    common_regions = set(snapshots[0])
    for snapshot in snapshots[1:]:
        common_regions.intersection_update(snapshot)

    expected_zero_based = tuple(range(len(snapshots)))
    expected_one_based = tuple(range(1, len(snapshots) + 1))
    index_candidates = {"u8": [], "u16": [], "u32": []}
    changed_byte_count = 0
    changed_every_transition = 0
    changed_bytes = []
    changed_u32 = []
    index_address_references = []
    neighborhood_address = 0x006008EC
    neighborhood = []

    for region_base in sorted(common_regions):
        region_snapshots = [snapshot[region_base] for snapshot in snapshots]
        region_size = min(len(data) for data in region_snapshots)
        for offset in range(region_size):
            values = tuple(data[offset] for data in region_snapshots)
            if len(set(values)) > 1:
                changed_byte_count += 1
                changed_bytes.append(
                    {
                        "address": f"0x{region_base + offset:08X}",
                        "values": list(values),
                    }
                )
            if all(
                values[index] != values[index - 1]
                for index in range(1, len(values))
            ):
                changed_every_transition += 1

        for offset in range(0, region_size - 3, 4):
            values = tuple(
                struct.unpack_from("<I", data, offset)[0]
                for data in region_snapshots
            )
            if len(set(values)) > 1:
                changed_u32.append(
                    {
                        "address": f"0x{region_base + offset:08X}",
                        "values": [f"0x{value:08X}" for value in values],
                    }
                )

        index_pointer = struct.pack("<I", 0x004B7504)
        position = region_snapshots[0].find(index_pointer)
        while position >= 0:
            if all(
                data[position : position + 4] == index_pointer
                for data in region_snapshots[1:]
            ):
                index_address_references.append(
                    f"0x{region_base + position:08X}"
                )
            position = region_snapshots[0].find(index_pointer, position + 1)

        for width, label, fmt in (
            (1, "u8", "<B"),
            (2, "u16", "<H"),
            (4, "u32", "<I"),
        ):
            for offset in range(0, region_size - width + 1, width):
                values = tuple(
                    struct.unpack_from(fmt, data, offset)[0]
                    for data in region_snapshots
                )
                if values in (expected_zero_based, expected_one_based):
                    index_candidates[label].append(
                        {
                            "address": f"0x{region_base + offset:08X}",
                            "values": list(values),
                        }
                    )

        if region_base <= neighborhood_address < region_base + region_size:
            offset = neighborhood_address - region_base
            start = max(0, offset - 32)
            end = min(region_size, offset + 64)
            neighborhood = [
                {
                    "member_index": index + 1,
                    "address": f"0x{region_base + start:08X}",
                    "hex": data[start:end].hex(),
                }
                for index, data in enumerate(region_snapshots)
            ]

    return {
        "snapshot_count": len(snapshots),
        "common_regions": [
            {
                "base": f"0x{base:08X}",
                "size": min(len(snapshot[base]) for snapshot in snapshots),
            }
            for base in sorted(common_regions)
        ],
        "changed_byte_count": changed_byte_count,
        "changed_every_transition": changed_every_transition,
        "changed_bytes": changed_bytes,
        "changed_u32": changed_u32,
        "index_address_references": index_address_references,
        "member_index_candidates": {
            key: values[:200] for key, values in index_candidates.items()
        },
        "member_index_candidate_counts": {
            key: len(values) for key, values in index_candidates.items()
        },
        "candidate_0x006008ec_neighborhood": neighborhood,
    }


def install_render_trace(pid: int):
    import frida

    messages = []
    session = frida.attach(pid)
    script = session.create_script(
        r"""
        const moduleStart = 0x00400000;
        const moduleEnd = 0x00645000;
        let eventCount = 0;

        function inGameModule(address) {
            const value = address.toUInt32();
            return value >= moduleStart && value < moduleEnd;
        }

        function emit(payload) {
            if (eventCount >= 20000) {
                return;
            }
            eventCount += 1;
            send(payload);
        }

        const bitBlt = Module.getGlobalExportByName("BitBlt");
        Interceptor.attach(bitBlt, {
            onEnter(args) {
                if (!inGameModule(this.returnAddress)) {
                    return;
                }
                const width = args[3].toInt32();
                const height = args[4].toInt32();
                if (
                    height !== 14
                    || width < 90
                    || width > 150
                ) {
                    return;
                }
                emit({
                    kind: "BitBlt",
                    return_address: this.returnAddress.toString(),
                    x: args[1].toInt32(),
                    y: args[2].toInt32(),
                    width: width,
                    height: height,
                    source_x: args[6].toInt32(),
                    source_y: args[7].toInt32(),
                    rop: args[8].toUInt32(),
                });
            }
        });

        Interceptor.attach(ptr(0x0040A775), {
            onEnter(args) {
                const values = [];
                for (let index = 0; index < 5; index += 1) {
                    values.push(args[index].toString());
                }
                emit({
                    kind: "bitmap_wrapper",
                    return_address: this.returnAddress.toString(),
                    ecx: this.context.ecx.toString(),
                    args: values,
                });
            }
        });

        for (const target of [0x00401126, 0x0040F436]) {
            Interceptor.attach(ptr(target), {
                onEnter(args) {
                    const values = [];
                    for (let index = 0; index < 8; index += 1) {
                        values.push(args[index].toString());
                    }
                    emit({
                        kind: "internal_call",
                        target: ptr(target).toString(),
                        return_address: this.returnAddress.toString(),
                        ecx: this.context.ecx.toString(),
                        edx: this.context.edx.toString(),
                        args: values,
                    });
                }
            });
        }
        """
    )

    def on_message(message, data):
        if message.get("type") == "send":
            messages.append(message["payload"])
        else:
            messages.append({"kind": "frida_error", "message": message})

    script.on("message", on_message)
    script.load()
    return session, script, messages


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
            render_trace = None
            if os.environ.get("PROBE_TRACE_RENDER") == "1":
                render_trace = install_render_trace(game.pid)
            runner = task_module.CczReRandTask(0)
            runner.savePos = 1
            runner.is2_08 = False
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
                    from models.CczModels import CCZ_MODELS
                    from window.CczWindow import CczPeopleInfoWindow

                    model_ids = {
                        skill.name: index
                        for index, skill in enumerate(CCZ_MODELS.skills)
                    }
                    slot_probes = []
                    module_snapshots = []
                    original_get_skill_mats = (
                        CczPeopleInfoWindow.getSkillMatList
                    )

                    def probed_get_skill_mats(window):
                        mats = original_get_skill_mats(window)
                        slots = []
                        for slot_index, mat in enumerate(mats):
                            skill = task_module.CczUtils.getCczSkillWithMat(mat)
                            slots.append(
                                {
                                    "slot": slot_index + 1,
                                    "category": (
                                        "personal"
                                        if slot_index < 3
                                        else "job"
                                    ),
                                    "model_id": (
                                        model_ids.get(skill.name)
                                        if skill is not None
                                        else None
                                    ),
                                    "name": (
                                        skill.name
                                        if skill is not None
                                        else None
                                    ),
                                }
                            )
                        slot_ids = [item["model_id"] for item in slots]
                        if (
                            os.environ.get("PROBE_SCAN_SKILL_MEMORY") == "1"
                        ):
                            module_snapshots.append(
                                snapshot_module_writable_memory(game.pid)
                            )
                        current_record_pointer = None
                        current_record_hex = None
                        pointer_data = read_absolute_memory(
                            game.pid,
                            0x00500E28,
                            4,
                        )
                        if pointer_data is not None:
                            current_record_pointer = struct.unpack(
                                "<I",
                                pointer_data,
                            )[0]
                            record_data = read_absolute_memory(
                                game.pid,
                                current_record_pointer,
                                0x200,
                            )
                            if record_data is not None:
                                current_record_hex = record_data.hex()
                        slot_probes.append(
                            {
                                "member_index": len(slot_probes) + 1,
                                "slots": slots,
                                "current_record_pointer": (
                                    f"0x{current_record_pointer:08X}"
                                    if current_record_pointer is not None
                                    else None
                                ),
                                "current_record_hex": current_record_hex,
                                "direct_memory_candidates": (
                                    direct_skill_slot_candidates(
                                        game.pid,
                                        slot_ids,
                                    )
                                    if os.environ.get(
                                        "PROBE_SCAN_SKILL_MEMORY"
                                    )
                                    == "1"
                                    else {}
                                ),
                            }
                        )
                        return mats

                    CczPeopleInfoWindow.getSkillMatList = (
                        probed_get_skill_mats
                    )
                    try:
                        runner._getTeamSkillsInfo()
                    finally:
                        CczPeopleInfoWindow.getSkillMatList = (
                            original_get_skill_mats
                        )
                    skill_dump = [
                        {
                            "name": member.name,
                            "job": getattr(member.job, "name", ""),
                            "slots": (
                                slot_probes[index]["slots"]
                                if index < len(slot_probes)
                                else []
                            ),
                            "skills": [
                                {
                                    "name": skill.name,
                                    "score": skill.score,
                                    "type": skill.type.value,
                                }
                                for skill in member.skillList
                            ],
                        }
                        for index, member in enumerate(
                            task_module.TEAM_MEMBER_LIST
                        )
                    ]
                    (OUTPUT / "skills-actual.json").write_text(
                        json.dumps(skill_dump, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    if os.environ.get("PROBE_SCAN_SKILL_MEMORY") == "1":
                        if module_snapshots:
                            for base, data in module_snapshots[0].items():
                                (
                                    OUTPUT
                                    / f"runtime-module-{base:08x}.bin"
                                ).write_bytes(data)
                        shared_candidates = {}
                        candidate_keys = {
                            key
                            for probe in slot_probes
                            for key in probe["direct_memory_candidates"]
                        }
                        for key in sorted(candidate_keys):
                            groups = [
                                set(
                                    probe["direct_memory_candidates"].get(
                                        key, ()
                                    )
                                )
                                for probe in slot_probes
                                if probe["direct_memory_candidates"].get(key)
                            ]
                            if len(groups) >= 2:
                                shared = set.intersection(*groups)
                                if shared:
                                    shared_candidates[key] = sorted(shared)
                        (OUTPUT / "skill-memory-probe.json").write_text(
                            json.dumps(
                                {
                                    "members": slot_probes,
                                    "shared_current_dialog_candidates": (
                                        shared_candidates
                                    ),
                                    "module_transition_analysis": (
                                        analyze_module_transitions(
                                            module_snapshots
                                        )
                                    ),
                                },
                                ensure_ascii=False,
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    if render_trace is not None:
                        session, script, trace_messages = render_trace
                        (OUTPUT / "render-trace.json").write_text(
                            json.dumps(
                                trace_messages,
                                ensure_ascii=False,
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                        script.unload()
                        session.detach()
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
