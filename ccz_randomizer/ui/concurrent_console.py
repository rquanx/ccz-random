from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


ATTEMPT_PATTERN = re.compile(
    r"^=+\s*结果\s+(\d+)/(\d+)，原生随机第\s+(\d+)\s+轮\s*=+$"
)
SAVE_SUCCESS_PATTERN = re.compile(
    r"^第\s+(\d+)\s+号结果存档已通过游戏菜单保存"
)
SLOT_ASSIGNED_PATTERN = re.compile(r"^@@CCZ_SLOT_ASSIGNED@@(\d+)$")
SLOT_RETRY_PATTERN = re.compile(r"^@@CCZ_SLOT_RETRY@@(\d+)$")
SLOT_FAILED_PATTERN = re.compile(r"^@@CCZ_SLOT_FAILED@@(\d+)$")
RESULT_IMAGE_UPDATED_MARKER = "总图已更新："
ROUND_IMAGE_PATH_PREFIX = "本轮总图路径："
RESULT_IMAGE_PATH_PREFIX = "@@CCZ_RESULT_IMAGE@@"


def chinese_ordinal(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 1:
        raise ValueError("序号必须大于 0")
    if value < 10:
        return digits[value]
    if value == 10:
        return "十"
    if value < 20:
        return "十" + digits[value - 10]
    if value < 100:
        tens, ones = divmod(value, 10)
        return digits[tens] + "十" + (digits[ones] if ones else "")
    return str(value)


def format_round_heading(round_number: int) -> str:
    return f"第{chinese_ordinal(round_number)}轮"


def extract_result_image_path(line: str) -> Path | None:
    text = line.strip()
    if text.startswith(RESULT_IMAGE_PATH_PREFIX):
        value = text[len(RESULT_IMAGE_PATH_PREFIX) :].strip()
    elif text.startswith(ROUND_IMAGE_PATH_PREFIX):
        value = text[len(ROUND_IMAGE_PATH_PREFIX) :].strip()
    elif RESULT_IMAGE_UPDATED_MARKER in text:
        value = text.split(RESULT_IMAGE_UPDATED_MARKER, 1)[1].strip()
    else:
        return None
    return Path(value) if value else None


def is_completion_console_line(line: str) -> bool:
    text = line.strip()
    return bool(
        SAVE_SUCCESS_PATTERN.match(text)
        or extract_result_image_path(text) is not None
    )


def build_console_render_signature(
    rounds: Mapping[int, ConcurrentConsoleState],
    round_images: Mapping[int, Path],
    *,
    active_round: int,
    footer: str,
    mode: str,
    loop_enabled: bool,
) -> tuple:
    round_signatures = []
    for round_number, state in sorted(rounds.items()):
        slots = tuple(
            (
                slot,
                progress.attempt,
                progress.stage,
                progress.completed,
                progress.detail is not None,
            )
            for slot in state.visible_slots()
            for progress in (state.slots[slot],)
        )
        image = round_images.get(round_number)
        round_signatures.append(
            (
                round_number,
                state.result_count,
                state.concurrency,
                slots,
                str(image) if image is not None else "",
            )
        )
    return (
        mode,
        loop_enabled,
        active_round,
        footer,
        tuple(round_signatures),
    )


@dataclass
class AttemptProgress:
    attempt: int
    member_summary: str = ""
    detail: dict | None = None


@dataclass
class SlotProgress:
    slot: int
    attempt: int = 0
    stage: str = "等待开始"
    started: bool = False
    completed: bool = False
    detail: dict | None = None
    history: list[str] = field(default_factory=list)
    result_details: list[dict] = field(default_factory=list)
    attempts: list[AttemptProgress] = field(default_factory=list)


class ConcurrentConsoleState:
    def __init__(self, result_count: int, concurrency: int) -> None:
        if not 1 <= result_count <= 15:
            raise ValueError("结果数量必须位于 1-15")
        if concurrency < 1:
            raise ValueError("同时运行数量必须大于 0")
        self.result_count = result_count
        self.concurrency = concurrency
        self.slots = {
            slot: SlotProgress(slot)
            for slot in range(1, result_count + 1)
        }
        self.worker_slots: dict[int, int] = {}

    @staticmethod
    def _record_history(progress: SlotProgress, text: str) -> None:
        text = text.strip()
        if not text or text.startswith("@@"):
            return
        if progress.history and progress.history[-1] == text:
            return
        progress.history.append(text)
        # A single worker can run for a long time. Keep the dialog useful
        # without allowing stale progress to grow without bound.
        if len(progress.history) > 500:
            del progress.history[:100]

    @staticmethod
    def _attempt_progress(
        progress: SlotProgress,
        attempt: int,
    ) -> AttemptProgress:
        for item in reversed(progress.attempts):
            if item.attempt == attempt:
                return item
        item = AttemptProgress(attempt=attempt)
        progress.attempts.append(item)
        if len(progress.attempts) > 100:
            del progress.attempts[:20]
        return item

    def visible_slots(self) -> tuple[int, ...]:
        return tuple(
            slot
            for slot, progress in self.slots.items()
            if progress.started
        )

    def consume_line(
        self,
        worker_index: int,
        line: str,
        *,
        history_line: str | None = None,
    ) -> bool:
        text = line.strip()
        history_text = text if history_line is None else history_line.strip()
        assignment_match = SLOT_ASSIGNED_PATTERN.match(text)
        if assignment_match:
            slot = int(assignment_match.group(1))
            if slot not in self.slots:
                return False
            self.worker_slots[worker_index] = slot
            progress = self.slots[slot]
            progress.started = True
            progress.stage = "正在启动随机流程"
            progress.completed = False
            self._record_history(progress, "已领取任务，正在启动随机流程")
            return True

        retry_match = SLOT_RETRY_PATTERN.match(text)
        if retry_match:
            slot = int(retry_match.group(1))
            if slot not in self.slots:
                return False
            progress = self.slots[slot]
            progress.started = True
            progress.stage = "后台实例异常，等待重试"
            progress.completed = False
            self._record_history(progress, "后台实例异常，任务已重新排队")
            return True

        failed_match = SLOT_FAILED_PATTERN.match(text)
        if failed_match:
            slot = int(failed_match.group(1))
            if slot not in self.slots:
                return False
            progress = self.slots[slot]
            progress.started = True
            progress.stage = "执行失败"
            progress.completed = True
            self._record_history(progress, "后台实例连续失败，已停止重试")
            return True

        attempt_match = ATTEMPT_PATTERN.match(text)
        if attempt_match:
            slot = int(attempt_match.group(1))
            attempt = int(attempt_match.group(3))
            if slot not in self.slots:
                return False
            self.worker_slots[worker_index] = slot
            progress = self.slots[slot]
            progress.started = True
            progress.attempt = attempt
            progress.stage = "正在执行随机流程"
            progress.completed = False
            progress.detail = None
            self._attempt_progress(progress, attempt)
            self._record_history(progress, history_text)
            return True

        save_match = SAVE_SUCCESS_PATTERN.match(text)
        if save_match:
            slot = int(save_match.group(1))
            if slot not in self.slots:
                return False
            progress = self.slots[slot]
            progress.started = True
            progress.stage = "已完成：合格"
            progress.completed = True
            self._record_history(progress, history_text)
            return True

        slot = self.worker_slots.get(worker_index)
        if slot is None:
            return False
        progress = self.slots[slot]
        if text.startswith(("R0 七人兵种筛选:", "R0 三人兵种筛选:")):
            progress.stage = (
                "兵种合格，正在检查特技"
                if text.endswith("结果=通过")
                else "兵种不合格，准备再次随机"
            )
            if progress.attempt:
                self._attempt_progress(
                    progress,
                    progress.attempt,
                ).member_summary = history_text
            self._record_history(progress, history_text)
            return True
        if text.startswith(
            (
                "初始三人兵种合格，正在检查特技条件",
                "R1 七人特技内存读取:",
            )
        ):
            progress.stage = "正在检查特技条件"
            self._record_history(progress, history_text)
            return True
        if text.startswith("用户进度:"):
            if "合格，开始保存" in text:
                progress.stage = "条件合格，正在保存"
            elif "特技不合格" in text:
                progress.stage = "特技不合格，准备再次随机"
            elif "兵种不合格" in text:
                progress.stage = "兵种不合格，准备再次随机"
            else:
                return False
            self._record_history(progress, history_text)
            return True
        if (
            text.startswith(f"第 {slot} 号结果存档已保存")
            or text.startswith(f"第 {slot} 号结果图已生成")
        ):
            if not progress.completed:
                progress.stage = "正在生成结果图"
            self._record_history(progress, history_text)
            return True
        if text.startswith("后台游戏运行异常"):
            progress.stage = "后台游戏异常，正在重新启动"
            self._record_history(progress, history_text)
            return True
        if history_text:
            self._record_history(progress, history_text)
            return True
        return False

    def consume_result(
        self,
        detail: dict,
        *,
        preserve_stopped: bool = False,
    ) -> bool:
        try:
            slot = int(detail["resultSlot"])
            attempt = int(detail["attempt"])
        except (KeyError, TypeError, ValueError):
            return False
        if slot not in self.slots:
            return False
        progress = self.slots[slot]
        was_stopped = (
            preserve_stopped
            and progress.started
            and not progress.completed
            and progress.stage in {"正在停止", "已停止"}
        )
        progress.started = True
        progress.attempt = attempt
        status = str(detail.get("status", ""))
        label = str(detail.get("label") or "未知")
        attempt_progress = self._attempt_progress(progress, attempt)
        attempt_progress.detail = detail
        if (
            not progress.result_details
            or progress.result_details[-1] != detail
        ):
            progress.result_details.append(detail)
            if len(progress.result_details) > 100:
                del progress.result_details[:20]
        if was_stopped:
            if status == "accepted":
                progress.detail = detail
            self._record_history(progress, f"结果：{label}")
            return True
        if status == "accepted":
            if progress.completed:
                progress.detail = detail
                return True
            progress.stage = "条件合格，正在保存"
            progress.completed = False
            progress.detail = detail
            self._record_history(progress, f"结果：{label}")
        else:
            progress.stage = f"{label}，准备再次随机"
            progress.completed = False
            progress.detail = None
            self._record_history(progress, f"结果：{label}")
        return True

    def mark_stopped(self) -> None:
        for progress in self.slots.values():
            if progress.started and not progress.completed:
                progress.stage = "已停止"

    def mark_stopping(self) -> None:
        for progress in self.slots.values():
            if progress.started and not progress.completed:
                progress.stage = "正在停止"
