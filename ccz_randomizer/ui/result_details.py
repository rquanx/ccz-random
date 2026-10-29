from __future__ import annotations

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


def format_result_detail(detail: dict[str, Any]) -> dict[str, Any]:
    status = str(detail.get("label") or "未知")
    mode = "3人" if detail.get("mode") == "three" else "7人"
    sections: list[dict[str, Any]] = []

    job = detail.get("job")
    if isinstance(job, dict):
        metrics = job.get("metrics") or {}
        members = job.get("members") or []
        rows = [
            (
                f"{item.get('name', '未知')}："
                f"{item.get('job', '未知兵种')}　"
                f"评分 {_score(item.get('score'))}"
            )
            for item in members
            if isinstance(item, dict)
        ]
        qualification_mode = metrics.get("qualificationMode")
        if qualification_mode == "count":
            eligible = metrics.get("eligibleMembers") or []
            qualified_names = metrics.get("qualifiedMemberNames") or []
            explanation = (
                f"参与人物：{'、'.join(eligible) or '无'}\n"
                f"达到门槛 {_score(metrics.get('threshold'))} 的人物："
                f"{'、'.join(qualified_names) or '无'}\n"
                f"人数 {metrics.get('qualifiedCount', 0)} "
                f"{'>=' if job.get('qualified') else '<'} "
                f"要求 {metrics.get('requiredCount', 0)} 人"
            )
        else:
            explanation = _comparison(
                metrics.get("average"),
                metrics.get("threshold"),
                qualified=bool(job.get("qualified")),
                value_label="平均分",
            )
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
        if auto_pass == "special_skill":
            explanation = "存在特殊特技，按当前规则直接合格"
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
                "title": "特技评分",
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
    from tkinter import scrolledtext
    from ccz_randomizer.ui.detail_actions import add_detail_actions
    view = format_result_detail(detail)
    dialog = tk.Toplevel(root)
    dialog.title("评分详情")
    dialog.geometry("720x590")
    dialog.minsize(620, 460)
    dialog.transient(root)

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

    tk.Button(
        body,
        text="关闭",
        width=10,
        command=dialog.destroy,
    ).pack(anchor="e", pady=(12, 0))
    dialog.update_idletasks()
    x = root.winfo_rootx() + max(
        0, (root.winfo_width() - dialog.winfo_width()) // 2
    )
    y = root.winfo_rooty() + max(
        0, (root.winfo_height() - dialog.winfo_height()) // 2
    )
    dialog.geometry(f"+{x}+{y}")

