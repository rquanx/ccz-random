from __future__ import annotations
from tkinter import ttk

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.theme import COLORS, FONT, setup_theme, style_dialog
from ccz_randomizer.rules.reporting import participating_members

import json
from typing import Any


RESULT_DETAIL_PREFIX = "@@CCZ_RESULT_DETAIL@@"


def encode_result_detail(detail: dict[str, Any]) -> str:
    return RESULT_DETAIL_PREFIX + json.dumps(
        detail,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_result_detail(line: str) -> dict[str, Any] | None:
    if not line.startswith(RESULT_DETAIL_PREFIX):
        return None
    value = json.loads(line[len(RESULT_DETAIL_PREFIX) :])
    return value if isinstance(value, dict) else None


def _score(value: Any) -> str:
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "-"


def _comparison(
    value: Any,
    threshold: Any,
    *,
    qualified: bool,
    value_label: str,
) -> str:
    operator = ">=" if qualified else "<"
    return (
        f"{value_label} {_score(value)} {operator} "
        f"门槛 {_score(threshold)}"
    )


def _threshold_result(value, threshold) -> str:
    try:
        gap = float(threshold) - float(value)
    except (TypeError, ValueError):
        return "评分数据未采集"
    return f"还差 {_score(gap)} 分" if gap > 1e-9 else "已达标"


def format_result_detail(detail: dict[str, Any]) -> dict[str, Any]:
    status = str(detail.get("label") or "未知")
    mode = "3人" if detail.get("mode") == "three" else "7人"
    sections: list[dict[str, Any]] = []

    job = detail.get("job")
    if isinstance(job, dict):
        metrics = job.get("metrics") or {}
        members = participating_members(job)
        mode = f"兵种筛选 {len(members)} 人"
        qualification_mode = metrics.get("qualificationMode")
        threshold = metrics.get("threshold")
        rows = []
        for item in members:
            if not isinstance(item, dict):
                continue
            row = f"{item.get('name', '未知')}：{item.get('job', '未知兵种')}　{_score(item.get('score'))} 分"
            if qualification_mode in {"count", "all"} and len(members) > 1:
                row += "　" + _threshold_result(item.get("score"), threshold)
            rows.append(row)
        if metrics.get("autoPassReason") == "high_job":
            explanation = "所选人物出现高阶兵种，按当前规则直接通过兵种阶段"
        elif qualification_mode == "none":
            explanation = "无要求，不设兵种评分门槛"
        elif qualification_mode in {"count", "all"}:
            if len(members) == 1:
                explanation = f"门槛 {_score(threshold)} 分，" + _threshold_result(members[0].get("score"), threshold)
            else:
                actual = metrics.get("qualifiedCount", 0)
                required = metrics.get("requiredCount", 0)
                explanation = f"需至少 {required} 人达到 {_score(threshold)} 分；本次 {actual} 人达标"
                if actual < required:
                    explanation += f"，还差 {required - actual} 人"
        elif qualification_mode == "total":
            total = metrics.get("qualificationTotal")
            explanation = (f"所选人物总分 {_score(total)} 分，门槛 {_score(threshold)} 分，"
                           + _threshold_result(total, threshold))
        else:
            average = metrics.get("qualificationAverage", metrics.get("average"))
            explanation = (f"所选人物平均 {_score(average)} 分，门槛 {_score(threshold)} 分，"
                           + _threshold_result(average, threshold))
        sections.append(
            {
                "title": "兵种评分",
                "qualified": bool(job.get("qualified")),
                "rows": rows,
                "explanation": explanation,
            }
        )

    skill = detail.get("skill")
    if isinstance(skill, dict):
        metrics = skill.get("metrics") or {}
        members = skill.get("members") or []
        rows = []
        for item in members:
            if not isinstance(item, dict):
                continue
            skills = item.get("skills") or []
            skill_text = "、".join(skills) if skills else "未识别到有效特技"
            rows.append(
                f"{item.get('name', '未知')}：{skill_text}　"
                f"计分 {_score(item.get('score'))}"
            )
        auto_pass = str(metrics.get("autoPassReason") or "")
        gate_mode = metrics.get("qualificationMode")
        if auto_pass == "special_skill":
            explanation = "存在特殊特技，按当前规则直接合格"
        elif gate_mode == "none":
            explanation = "无要求，不设特技评分门槛"
        elif gate_mode == "count":
            threshold = metrics.get("threshold")
            if len(members) == 1:
                explanation = f"门槛 {_score(threshold)} 分，" + _threshold_result(members[0].get("score"), threshold)
            else:
                actual, required = metrics.get("qualifiedCount", 0), metrics.get("requiredCount", 0)
                explanation = f"需至少 {required} 人达到 {_score(threshold)} 分；本次 {actual} 人达标"
                if actual < required:
                    explanation += f"，还差 {required - actual} 人"
        elif gate_mode in {"average", "total"}:
            value = metrics.get("qualificationAverage") if gate_mode == "average" else metrics.get("skillScore")
            label = "所选人物平均" if gate_mode == "average" else "所选人物总分"
            threshold = metrics.get("threshold")
            explanation = f"{label} {_score(value)} 分，门槛 {_score(threshold)} 分，" + _threshold_result(value, threshold)
        elif auto_pass == "high_job_average":
            explanation = (
                "兵种平均分达到直接合格条件："
                f"{_score(metrics.get('jobAverage'))} >= "
                f"{_score(metrics.get('highJobAverage'))}"
            )
        else:
            explanation = _comparison(
                metrics.get("skillScore"),
                metrics.get("requiredSkillScore"),
                qualified=bool(skill.get("qualified")),
                value_label="特技总分",
            )
        sections.append(
            {
                "title": "特技评分" if metrics.get("qualificationMode") else ("特技评分（初始三人）" if detail.get("mode") == "three" else "特技评分"),
                "qualified": bool(skill.get("qualified")),
                "rows": rows,
                "explanation": explanation,
            }
        )
    elif status == "兵种不合格":
        sections.append(
            {
                "title": "特技评分",
                "qualified": None,
                "rows": [],
                "explanation": "兵种未通过，本次未继续检查特技。",
            }
        )

    return {
        "title": f"第 {detail.get('resultSlot', '-')} 号存档"
        f"｜第 {detail.get('attempt', '-')} 次尝试",
        "status": status,
        "mode": mode,
        "sections": sections,
    }

def show_score_detail(root, detail: dict) -> None:
    import tkinter as tk
    from ccz_randomizer.ui import scrolled_text as scrolledtext
    from ccz_randomizer.ui.detail_actions import add_detail_actions
    view = format_result_detail(detail)
    dialog = centered_toplevel(root)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title("评分详情")
    dialog.geometry("720x590")
    dialog.minsize(620, 460)
    dialog.transient(root)
    dialog.bind("<Escape>", lambda _event: dialog.destroy())

    # 等待窗口完成映射后再抢占焦点，避免 centered_toplevel 的透明定位阶段
    # 让焦点短暂落到主窗口，导致打开评分详情后第一次按 Esc 没有反应。
    def focus_dialog() -> None:
        if dialog.winfo_exists():
            dialog.lift()
            dialog.focus_force()

    dialog.after_idle(focus_dialog)

    body = tk.Frame(dialog, padx=18, pady=16)
    body.pack(fill="both", expand=True)
    tk.Label(
        body,
        text=view["title"],
        font=("Microsoft YaHei UI", 13, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        body,
        text=f"{view['mode']}　结果：{view['status']}",
        font=("Microsoft YaHei UI", 10),
        fg=(
            "#16794b"
            if view["status"] == "合格"
            else "#b42318"
        ),
        anchor="w",
    ).pack(fill="x", pady=(5, 12))

    add_detail_actions(body, dialog, detail)

    ttk.Button(body, text="关闭", width=10, command=dialog.destroy).pack(
        side="bottom", anchor="e", pady=(12, 0))

    detail_text = scrolledtext.ScrolledText(
        body,
        wrap="word",
        font=("Microsoft YaHei UI", 10),
        bg="#ffffff",
        relief="solid",
        borderwidth=1,
        padx=12,
        pady=10,
    )
    detail_text.pack(fill="both", expand=True)
    detail_text.tag_configure(
        "section",
        font=("Microsoft YaHei UI", 11, "bold"),
        spacing1=10,
        spacing3=5,
    )
    detail_text.tag_configure("pass", foreground="#16794b")
    detail_text.tag_configure("fail", foreground="#b42318")
    detail_text.tag_configure("muted", foreground="#666666")
    for section in view["sections"]:
        detail_text.insert("end", section["title"] + "\n", "section")
        for row in section["rows"]:
            detail_text.insert("end", row + "\n")
        state = section["qualified"]
        if state is None:
            detail_text.insert(
                "end",
                section["explanation"] + "\n",
                "muted",
            )
        else:
            detail_text.insert(
                "end",
                ("通过： " if state else "未通过： ")
                + section["explanation"]
                + "\n",
                "pass" if state else "fail",
            )
        detail_text.insert("end", "\n")
    detail_text.configure(state="disabled")
    show_centered(dialog)

