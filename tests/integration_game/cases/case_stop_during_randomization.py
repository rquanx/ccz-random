from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    artifact_dir = Path(os.environ["CCZ_GAME_TEST_ARTIFACT_DIR"])
    stop_file = artifact_dir / "stop.request"
    environment = os.environ.copy()
    environment.update(
        {
            "CCZ_AUTOSTART": "1",
            "CCZ_NO_PAUSE": "1",
            "CCZ_STOP_FILE": str(stop_file),
            "CCZ_RANDOM_MODE": "seven",
            "CCZ_LOOP_RANDOM": "0",
            "CCZ_RESULT_COUNT": "15",
            "CCZ_TEST_ACCEPT_FIRST": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    process = subprocess.Popen(
        [sys.executable, str(repo_root / "fast_randomizer.py"), "--worker"],
        cwd=repo_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    lines: queue.Queue[str] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line)

    threading.Thread(target=read_output, daemon=True).start()
    output: list[str] = []
    deadline = time.perf_counter() + 30
    marker_seen = False
    while time.perf_counter() < deadline:
        try:
            line = lines.get(timeout=0.1)
        except queue.Empty:
            if process.poll() is not None:
                break
            continue
        output.append(line)
        if "候选存档已由游戏原生保存" in line:
            marker_seen = True
            break
    if not marker_seen:
        process.kill()
        raise RuntimeError("停止测试未进入七人剧情推进前的候选保存阶段")

    requested_at = time.perf_counter()
    stop_file.write_text("stop", encoding="ascii")
    try:
        return_code = process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError("停止请求发出后 8 秒内工作进程仍未退出")
    elapsed = time.perf_counter() - requested_at
    while not lines.empty():
        output.append(lines.get_nowait())
    text = "".join(output)
    (artifact_dir / "worker-output.log").write_text(text, encoding="utf-8")

    if return_code != 130:
        raise RuntimeError(f"停止后的退出码不正确：{return_code}")
    if "隐藏游戏实例已重新启动" in text:
        raise RuntimeError("停止请求被误判成异常并触发了游戏重启")
    print(f"随机流程停止验证通过：{elapsed:.3f}s")


if __name__ == "__main__":
    raise SystemExit(main())
