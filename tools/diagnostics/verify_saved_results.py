from __future__ import annotations

import time
from pathlib import Path

import fast_randomizer as randomizer


def job_ids_from_save(
    data: bytes, positions: tuple[int, ...]
) -> tuple[int, ...]:
    return tuple(
        int.from_bytes(
            data[
                randomizer.JOB_OFFSET + position * 4 :
                randomizer.JOB_OFFSET + position * 4 + 4
            ],
            "little",
        )
        for position in positions
    )


def main() -> int:
    game_executable = randomizer.locate_game_executable()
    source_save = game_executable.parent / "SV" / "SV019.E5S"
    source_hash = randomizer.hashlib.sha256(source_save.read_bytes()).hexdigest()
    expected = {}
    for slot in range(1, 16):
        path = game_executable.parent / "SV" / f"SV{slot:03}.E5S"
        data = path.read_bytes()
        expected[slot] = (
            path,
            job_ids_from_save(data, randomizer.JOB_POSITIONS_R1),
            job_ids_from_save(data, randomizer.JOB_POSITIONS_R0),
        )

    for slot, (path, jobs, initial_three) in expected.items():
        with randomizer.HiddenGameSession(game_executable) as game:
            time.sleep(1.5)
            loaded = randomizer.title_load_verified(
                game.pid, slot - 1, path
            )
            if not loaded:
                raise RuntimeError(f"第 {slot} 号存档回读失败")
            if randomizer.read_job_ids(
                game.pid, randomizer.JOB_POSITIONS_R1
            ) != jobs:
                raise RuntimeError(f"第 {slot} 号存档七人兵种回读不一致")
            if randomizer.read_job_ids(
                game.pid, randomizer.JOB_POSITIONS_R0
            ) != initial_three:
                raise RuntimeError(f"第 {slot} 号存档初始三人回读不一致")
            print(f"第 {slot} 号存档回读校验通过")

    if randomizer.hashlib.sha256(source_save.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("第 20 号源存档被修改")
    print("15 个结果存档全部通过游戏原生回读校验。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
