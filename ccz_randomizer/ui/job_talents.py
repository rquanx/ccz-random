from __future__ import annotations

from ccz_randomizer.ui.window_position import centered_toplevel, show_centered
from ccz_randomizer.ui.inputs import SearchEntry
from ccz_randomizer.ui.theme import setup_theme, style_dialog

from ccz_randomizer.jobs import JOB_MAP


def load_job_talents(snapshot: dict) -> tuple[dict, ...]:
    """Never substitute a different random result for missing historical data."""
    rows = snapshot.get("jobTalents")
    if rows is None:
        return tuple({"jobId": i, "name": value[0], "talents": None} for i, value in JOB_MAP.items())
    if not isinstance(rows, list):
        raise ValueError("兵种天赋快照格式错误")
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("jobId")) is not int or row["jobId"] not in JOB_MAP:
            raise ValueError("兵种天赋快照编号无效")
        if row["jobId"] in by_id or not isinstance(row.get("talents"), list) or not all(isinstance(s, str) for s in row["talents"]):
            raise ValueError("兵种天赋快照数据无效")
        by_id[row["jobId"]] = row["talents"]
    return tuple({"jobId": i, "name": value[0], "talents": by_id.get(i)} for i, value in JOB_MAP.items())


def show_job_talents_window(parent, *, snapshot: dict) -> None:
    import tkinter as tk
    from tkinter import ttk, font
    from ccz_randomizer.ui import messages as messagebox

    try:
        jobs = load_job_talents(snapshot)
    except (OSError, ValueError) as exc:
        messagebox.showerror("无法读取兵种天赋", str(exc), parent=parent)
        return
    dialog = centered_toplevel(parent)
    setup_theme(dialog)
    style_dialog(dialog)
    dialog.title(f"{snapshot.get('gameVersion', '2.2')} 兵种天赋")
    dialog.geometry("900x680")
    dialog.minsize(680, 480)
    dialog.transient(parent)
    colors = {"ink": "#182230", "muted": "#667085", "surface": "#FFFFFF", "page": "#F4F6FA"}
    outer = ttk.Frame(dialog, padding=20)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="全部兵种天赋", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
    ttk.Label(outer, text="本次随机的 40 类兵种天赋；未采集的历史数据标为未采集，不代表无天赋。", foreground=colors["muted"]).pack(anchor="w", pady=(4, 12))
    query = tk.StringVar()
    SearchEntry(outer, textvariable=query, width=32,
        hint="即时搜索兵种或天赋；Esc 清空，Ctrl+A 全选").pack(anchor="w", pady=(0, 12))
    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    canvas = tk.Canvas(body, background=colors["page"], highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)
    title_font = font.Font(dialog, family="Microsoft YaHei UI", size=11, weight="bold")
    text_font = font.nametofont("TkDefaultFont", root=dialog)
    count = ttk.Label(outer, foreground=colors["muted"])
    count.pack(anchor="w", pady=(10, 0))
    # Prepare searchable text once; filtering never creates native child windows.
    cards = [(job["name"],
              "未采集（请查看新生成的结果）" if job["talents"] is None
              else "\n".join(job["talents"]) or "无兵种天赋",
              (job["name"] + " " + " ".join(job["talents"] or [])).casefold())
             for job in jobs]
    pending = None
    last_layout = None

    def refresh():
        nonlocal pending, last_layout
        pending = None
        width = canvas.winfo_width()
        if width <= 1:
            width = 840  # Initial layout; Configure adapts to the mapped window.
        term = query.get().casefold().strip()
        layout = (width, term)
        if layout == last_layout:
            return
        if last_layout is None or term != last_layout[1]:
            canvas.yview_moveto(0)
        last_layout = layout
        visible = [card for card in cards if all(word in card[2] for word in term.split())]
        canvas.delete("all")
        columns = max(1, min(3, width // 250))
        card_width = (width - 12 * (columns + 1)) / columns
        y = 6
        for start in range(0, len(visible), columns):
            backgrounds, bottoms = [], []
            for column, (name, talents, _) in enumerate(visible[start:start + columns]):
                x = 12 + column * (card_width + 12)
                backgrounds.append(canvas.create_rectangle(x, y, x + card_width, y + 1,
                    fill=colors["surface"], outline="#D9DEE7"))
                title = canvas.create_text(x + 12, y + 10, anchor="nw", text=name,
                    font=title_font, fill=colors["ink"], width=card_width - 24)
                text = canvas.create_text(x + 12, canvas.bbox(title)[3] + 8, anchor="nw",
                    text=talents, font=text_font, fill=colors["ink"], width=card_width - 24)
                bottoms.append(canvas.bbox(text)[3] + 12)
            bottom = max(bottoms)
            for background in backgrounds:
                left, top, right, _ = canvas.coords(background)
                canvas.coords(background, left, top, right, bottom)
            y = bottom + 12
        if not visible:
            canvas.create_text(12, 12, anchor="nw", text="没有符合条件的兵种。",
                font=text_font, fill=colors["muted"])
            y = 48
        count.configure(text=f"显示 {len(visible)} / {len(jobs)} 个兵种")
        canvas.configure(scrollregion=(0, 0, width, y))

    def schedule(*_args):
        nonlocal pending
        if pending is None:
            pending = dialog.after_idle(refresh)

    def destroyed(event):
        nonlocal pending
        if event.widget is dialog and pending is not None:
            dialog.after_cancel(pending)
            pending = None

    canvas.bind("<Configure>", schedule)
    dialog.bind("<Destroy>", destroyed, add="+")
    dialog.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
    query.trace_add("write", schedule)
    schedule()
    show_centered(dialog)
