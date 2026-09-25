from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from tests.integration_game.manifest import CASES, select_cases
from tests.integration_game.runner import run_game_cases


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_GAME_DIR = Path(
    r"E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c"
)


def game_is_running() -> bool:
    completed = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Ekd5.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
        check=False,
    )
    return completed.returncode == 0 and '"Ekd5.exe"' in completed.stdout


def run_unit_tests() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/unit",
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    return completed.returncode


def require_game_confirmation(args: argparse.Namespace) -> None:
    confirmed = args.confirm_game or os.environ.get("CCZ_RUN_GAME_TESTS") == "1"
    if not confirmed:
        raise SystemExit(
            "游戏测试会启动游戏并可能修改测试存档。"
            "请确认游戏已关闭，并增加 --confirm-game 后重新执行。"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="曹操传随机工具测试入口",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("unit", help="只运行不启动游戏的测试")

    list_parser = subparsers.add_parser("list-game", help="列出完整游戏测试")
    list_parser.set_defaults(list_game=True)

    for command in ("game", "all"):
        game_parser = subparsers.add_parser(
            command,
            help="运行完整游戏测试" if command == "game" else "运行全部测试",
        )
        game_parser.add_argument(
            "--confirm-game",
            action="store_true",
            help="确认允许启动游戏并临时修改测试存档",
        )
        game_parser.add_argument(
            "--game-dir",
            type=Path,
            default=Path(os.environ.get("CCZ_GAME_DIR", DEFAULT_GAME_DIR)),
        )
        game_parser.add_argument(
            "--case",
            action="append",
            default=[],
            help="只运行指定游戏测试，可重复使用",
        )
        game_parser.add_argument(
            "--timeout",
            type=int,
            default=300,
            help="每个游戏测试的超时秒数，默认 300",
        )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "list-game":
        for case in CASES:
            print(f"{case.name:22} {case.description}")
        return 0
    if args.command == "unit":
        return run_unit_tests()
    if args.command == "all":
        unit_result = run_unit_tests()
        if unit_result:
            return unit_result

    require_game_confirmation(args)
    game_dir = args.game_dir.resolve()
    if not (game_dir / "Ekd5.exe").is_file():
        raise SystemExit(f"未找到游戏程序：{game_dir / 'Ekd5.exe'}")
    if game_is_running():
        raise SystemExit("检测到游戏正在运行，请先关闭游戏后再执行完整游戏测试。")
    try:
        cases = select_cases(args.case)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return run_game_cases(
        repo_root=REPO_ROOT,
        game_dir=game_dir,
        cases=cases,
        timeout_seconds=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
