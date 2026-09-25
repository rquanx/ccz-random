from __future__ import annotations

import copy
import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from rule_config import (
    AFFINITY_TYPES,
    DEFAULT_PROFILE_NAME,
    SIMPLE_PRESET_OPTIONS,
    apply_simple_settings,
    build_rule_export,
    default_rule_config,
    merge_rule_export,
    save_rule_config,
    validate_rule_config,
)


TYPE_LABELS = {
    "ALL_ROUNDER": "全能型",
    "WARRIOR": "武将型",
    "MASTER": "文官型",
    "NONE": "无",
}
TYPE_VALUES = {label: value for value, label in TYPE_LABELS.items()}

ADVANCED_HELP_SECTIONS = (
    (
        "阶段门槛",
        """用于决定一轮结果是否进入后续检查，以及最终需要达到的标准。

初始3人兵种合格门槛
只随机3人时使用，3人的兵种综合平均分达到该数值才合格。

完整7人兵种合格门槛
随机7人时使用。低于该数值会直接重新随机，不再检查特技。

普通兵种质量分界
兵种平均分达到该数值后，使用“普通兵种组合所需特技分”。

高兵种质量分界
开启“达到高兵种质量分界时直接合格”后，兵种平均分达到该数值即可合格。

数值越高，规则越严格。修改门槛不会改变各个兵种本身的基础分。""",
    ),
    (
        "兵种评分",
        """控制兵种基础分、人物倾向和队伍结构如何共同形成兵种综合分。

兵种基础分权重
统一放大或缩小全部兵种基础分。1表示保持原值。

人物兵种适配加成
开启后，兵种类型符合人物的主要倾向或次要倾向时获得加成。

适配加成最低基础分
基础分低于该数值的兵种不会获得人物倾向加成。

主要倾向、次要倾向加成比例
例如0.06表示在加权后的兵种分数上增加6%。

夏侯惇为文官型时扣分
夏侯惇随机为文官型兵种时额外扣除的分数。

文官型兵种过多扣分
开启后，队伍中出现多个文官型兵种时会按数量增加扣分。""",
    ),
    (
        "人物倾向",
        """设置每个人更适合的兵种类型，只影响兵种综合评分，不会限制实际能够随机出的兵种。

主要倾向
匹配时使用“主要倾向加成比例”。

次要倾向
匹配时使用“次要倾向加成比例”。

选择“无”
表示该位置不设置倾向，不会产生对应的适配加成。

人物倾向不是指定条件。设置武将型后，人物仍然可能随机到全能型或文官型兵种，只是综合评分可能不同。""",
    ),
    (
        "兵种基础分",
        """设置每个兵种参与综合评价时使用的原始分数。

这里的数值会覆盖工具内置的兵种基础分，再经过“兵种基础分权重”、人物倾向加成和队伍结构扣分计算。

提高某个兵种的基础分，会让包含该兵种的组合更容易达到阶段门槛；降低则会让它更难通过。

兵种基础分只影响评分，不会指定、排除或改变游戏实际随机出的兵种。""",
    ),
    (
        "特技评分",
        """设置特技阶段的分类默认分值、合格门槛和直接合格条件。

优质、强力、特殊特技基础分
未在“特技基础分”中单独修改的特技，按照所属分类使用这里的默认分值。

普通兵种组合所需特技分
兵种平均分达到普通质量分界时使用。

较低兵种组合所需特技分
兵种平均分未达到普通质量分界时使用，通常应设置得更高。

出现特殊特技时直接合格
开启后，只要出现特殊特技便跳过特技分数门槛。

达到高兵种质量分界时直接合格
开启后，兵种平均分达到高质量分界便跳过特技分数门槛。""",
    ),
    (
        "特技基础分",
        """设置单个特技参与综合评价时使用的分数。

单独修改后的分数优先级高于“特技评分”中的分类默认分值。没有单独修改的特技继续跟随所属分类的默认分值。

例如：特殊特技分类分值为5，某个特殊特技单独改为3，则该特技按3分计算，其他特殊特技仍按5分计算。

“其他”类别默认不计分，但可以在这里为个别特技设置分数。

普通优质特技和强力特技仍需符合人物类型适配规则才会计分。特殊特技不受该适配过滤影响。

如果开启“出现特殊特技时直接合格”，直接合格规则的优先级高于单项分数和分类分值。""",
    ),
)


class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.body = tk.Frame(self.canvas)
        self.window = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.body.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(
                self.window, width=event.width
            ),
        )
        self.winfo_toplevel().bind(
            "<MouseWheel>", self._on_mousewheel, add="+"
        )

    def _contains(self, widget: tk.Widget) -> bool:
        current = widget
        while current is not None:
            if current == self:
                return True
            current = getattr(current, "master", None)
        return False

    def _on_mousewheel(self, event) -> None:
        if not self.winfo_ismapped() or not self._contains(event.widget):
            return
        units = int(event.delta / 120)
        if units:
            self.canvas.yview_scroll(-units, "units")


class ScoreGrid(tk.Frame):
    COLUMN_COUNT = 4
    CARD_HEIGHT = 66
    GAP = 8
    SCORE_HEIGHT = 24

    def __init__(
        self,
        parent,
        items: list[tuple[str, tk.StringVar, str]],
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.items = items
        self.enabled = True
        self.editor: tk.Entry | None = None
        self.editor_window: int | None = None
        self.editing_index: int | None = None
        self.hit_boxes: list[tuple[int, int, int, int, int]] = []
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            background="#f5f5f5",
        )
        scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", lambda _event: self.refresh())
        self.canvas.bind("<Button-1>", self._start_edit)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Destroy>", self._destroy_editor, add="+")
        self.after_idle(self.refresh)

    def refresh(self) -> None:
        self.commit_pending()
        self.canvas.delete("all")
        self.hit_boxes.clear()
        viewport_width = max(760, self.canvas.winfo_width())
        content_width = viewport_width - self.GAP
        card_width = (
            content_width - self.GAP * (self.COLUMN_COUNT - 1)
        ) // self.COLUMN_COUNT
        rows = (
            len(self.items) + self.COLUMN_COUNT - 1
        ) // self.COLUMN_COUNT
        for index, (name, variable, category) in enumerate(self.items):
            row, column = divmod(index, self.COLUMN_COUNT)
            x1 = self.GAP + column * (card_width + self.GAP)
            y1 = self.GAP + row * (self.CARD_HEIGHT + self.GAP)
            x2 = x1 + card_width
            y2 = y1 + self.CARD_HEIGHT
            self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#ffffff",
                outline="#d8d8d8",
            )
            if category:
                category_color = {
                    "特殊": "#b24747",
                    "强力": "#496fa8",
                    "优质": "#4d8560",
                    "其他": "#888888",
                }.get(category, "#888888")
                self.canvas.create_rectangle(
                    x1,
                    y1,
                    x1 + 3,
                    y2,
                    fill=category_color,
                    outline="",
                )
            self.canvas.create_text(
                x1 + 9,
                y1 + 16,
                text=name,
                anchor="w",
                fill="#222222",
                font=("Microsoft YaHei UI", 9),
            )
            score_x1 = x1 + 8
            score_y1 = y2 - self.SCORE_HEIGHT - 7
            score_x2 = x2 - 8
            score_y2 = y2 - 7
            self.canvas.create_rectangle(
                score_x1,
                score_y1,
                score_x2,
                score_y2,
                fill="#fafafa" if self.enabled else "#f0f0f0",
                outline="#b8b8b8",
            )
            self.canvas.create_text(
                score_x1 + 8,
                (score_y1 + score_y2) / 2,
                text=f"{category} · 基础分" if category else "基础分",
                anchor="w",
                fill="#777777",
                font=("Microsoft YaHei UI", 8),
            )
            self.canvas.create_text(
                score_x2 - 8,
                (score_y1 + score_y2) / 2,
                text=variable.get(),
                anchor="e",
                fill="#222222" if self.enabled else "#888888",
                font=("Microsoft YaHei UI", 9, "bold"),
            )
            self.hit_boxes.append(
                (score_x1, score_y1, score_x2, score_y2, index)
            )
        total_height = (
            self.GAP + rows * (self.CARD_HEIGHT + self.GAP)
            if rows
            else self.CARD_HEIGHT
        )
        self.canvas.configure(
            scrollregion=(0, 0, viewport_width, total_height)
        )

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.commit_pending()
        self.refresh()

    def commit_pending(self) -> None:
        if self.editor is None or self.editing_index is None:
            return
        try:
            self.items[self.editing_index][1].set(self.editor.get())
        finally:
            self._destroy_editor()
        self.refresh()

    def _start_edit(self, event) -> None:
        if not self.enabled:
            return
        canvas_x = int(self.canvas.canvasx(event.x))
        canvas_y = int(self.canvas.canvasy(event.y))
        match = next(
            (
                box
                for box in self.hit_boxes
                if box[0] <= canvas_x <= box[2]
                and box[1] <= canvas_y <= box[3]
            ),
            None,
        )
        if match is None:
            return
        self.commit_pending()
        x1, y1, x2, y2, item_index = match
        variable = self.items[item_index][1]
        self.editor = tk.Entry(
            self.canvas,
            justify="center",
        )
        self.editor.insert(0, variable.get())
        self.editing_index = item_index
        self.editor_window = self.canvas.create_window(
            x1,
            y1,
            anchor="nw",
            width=x2 - x1,
            height=y2 - y1,
            window=self.editor,
        )
        self.editor.select_range(0, "end")
        self.editor.focus_set()
        self.editor.bind("<Return>", lambda _event: self.commit_pending())
        self.editor.bind("<FocusOut>", lambda _event: self.commit_pending())
        self.editor.bind("<Escape>", lambda _event: self._destroy_editor())

    def _on_mousewheel(self, event) -> None:
        units = int(event.delta / 120)
        if units:
            self.canvas.yview_scroll(-units, "units")

    def _destroy_editor(self, _event=None) -> None:
        editor = self.editor
        editor_window = self.editor_window
        self.editor = None
        self.editor_window = None
        self.editing_index = None
        if editor_window is not None:
            self.canvas.delete(editor_window)
        if editor is not None:
            editor.destroy()


def show_advanced_help(parent, selected_index: int) -> None:
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title("高级规则说明")
    dialog.geometry("760x560")
    dialog.minsize(680, 480)
    dialog.transient(parent)

    book = ttk.Notebook(dialog)
    book.pack(fill="both", expand=True, padx=14, pady=(14, 8))
    tabs = []
    for title, content in ADVANCED_HELP_SECTIONS:
        tab = tk.Frame(book, padx=18, pady=16)
        book.add(tab, text=title)
        tabs.append(tab)
        text = tk.Text(
            tab,
            wrap="word",
            relief="flat",
            padx=4,
            pady=4,
            font=("Microsoft YaHei UI", 10),
            spacing1=2,
            spacing3=7,
        )
        text.insert("1.0", content)
        text.configure(state="disabled")
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    if 0 <= selected_index < len(tabs):
        book.select(tabs[selected_index])

    footer = tk.Frame(dialog, padx=14)
    footer.pack(fill="x", pady=(0, 12))
    tk.Button(
        footer,
        text="关闭",
        command=dialog.destroy,
        width=10,
    ).pack(side="right")

    dialog.update_idletasks()
    width = max(760, dialog.winfo_reqwidth())
    height = max(560, dialog.winfo_reqheight())
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    x = max(0, min(x, dialog.winfo_screenwidth() - width))
    y = max(0, min(y, dialog.winfo_screenheight() - height))
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    dialog.deiconify()
    dialog.lift()
    dialog.grab_set()


def show_rule_editor(
    parent,
    base_dir: Path,
    config: dict,
    job_map: dict,
    team_members: tuple,
    skill_catalog: tuple,
    on_saved: Callable[[dict], None],
) -> None:
    working = copy.deepcopy(validate_rule_config(config))
    saved_snapshot = json.dumps(
        working,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    editor = tk.Toplevel(parent)
    editor.withdraw()
    editor.title("规则设置")
    editor.geometry("980x760")
    editor.minsize(860, 660)
    editor.transient(parent)

    selected_name = working["activeProfile"]
    loading = False
    editable_widgets: list[tk.Widget] = []

    top = tk.Frame(editor, padx=14, pady=12)
    top.pack(fill="x")
    tk.Label(top, text="规则方案").pack(side="left")
    profile_var = tk.StringVar(value=selected_name)
    profile_combo = ttk.Combobox(
        top,
        textvariable=profile_var,
        values=tuple(working["profiles"]),
        state="readonly",
        width=24,
    )
    profile_combo.pack(side="left", padx=(8, 12))

    action_frame = tk.Frame(editor, padx=14)
    action_frame.pack(fill="x", pady=(0, 10))

    notebook = ttk.Notebook(editor)
    notebook.pack(fill="both", expand=True, padx=14)
    simple_tab = tk.Frame(notebook, padx=18, pady=16)
    advanced_tab = tk.Frame(notebook, padx=12, pady=12)
    notebook.add(simple_tab, text="简单模式")
    notebook.add(advanced_tab, text="高级模式")

    simple_vars: dict[str, tk.StringVar] = {}
    simple_rows = (
        (
            "jobQuality",
            "兵种质量要求",
            "控制进入后续检查所需的整体兵种质量。",
        ),
        (
            "affinityImportance",
            "人物适配重视程度",
            "越高越重视兵种类型是否符合人物倾向。",
        ),
        (
            "teamBalance",
            "队伍兵种平衡",
            "越严格，文官型兵种过多时扣分越明显。",
        ),
        (
            "skillQuality",
            "特技质量要求",
            "控制七人模式需要达到的特技综合质量。",
        ),
        (
            "strongSkillImportance",
            "强力特技重视程度",
            "越高，强力特技在综合评价中占比越大。",
        ),
        (
            "highJobPreference",
            "高质量兵种优先程度",
            "越高，优秀兵种组合越容易直接通过特技阶段。",
        ),
    )
    for row, (key, label, description) in enumerate(simple_rows):
        tk.Label(
            simple_tab,
            text=label,
            anchor="w",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=row * 2, column=0, sticky="w", pady=(5, 0))
        options = tuple(SIMPLE_PRESET_OPTIONS[key])
        variable = tk.StringVar(value=options[0])
        simple_vars[key] = variable
        combo = ttk.Combobox(
            simple_tab,
            textvariable=variable,
            values=options,
            state="readonly",
            width=14,
        )
        combo.grid(
            row=row * 2,
            column=1,
            sticky="w",
            padx=(24, 0),
            pady=(5, 0),
        )
        editable_widgets.append(combo)
        tk.Label(
            simple_tab,
            text=description,
            fg="#666666",
            anchor="w",
        ).grid(
            row=row * 2 + 1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(2, 8),
        )
    simple_tab.columnconfigure(0, weight=1)

    advanced_book = ttk.Notebook(advanced_tab)
    advanced_book.pack(fill="both", expand=True)
    threshold_tab = tk.Frame(advanced_book, padx=16, pady=14)
    job_tab = tk.Frame(advanced_book, padx=16, pady=14)
    affinity_tab = tk.Frame(advanced_book, padx=16, pady=14)
    base_score_tab = tk.Frame(advanced_book, padx=8, pady=8)
    skill_tab = tk.Frame(advanced_book, padx=16, pady=14)
    skill_score_tab = tk.Frame(advanced_book, padx=8, pady=8)
    advanced_book.add(threshold_tab, text="阶段门槛")
    advanced_book.add(job_tab, text="兵种评分")
    advanced_book.add(affinity_tab, text="人物倾向")
    advanced_book.add(base_score_tab, text="兵种基础分")
    advanced_book.add(skill_tab, text="特技评分")
    advanced_book.add(skill_score_tab, text="特技基础分")

    number_vars: dict[str, tk.StringVar] = {}
    bool_vars: dict[str, tk.BooleanVar] = {}

    def add_number(
        tab,
        row: int,
        key: str,
        label: str,
        hint: str = "",
    ) -> None:
        tk.Label(tab, text=label, anchor="w").grid(
            row=row, column=0, sticky="w", pady=5
        )
        variable = tk.StringVar()
        number_vars[key] = variable
        entry = tk.Entry(tab, textvariable=variable, width=16)
        entry.grid(row=row, column=1, sticky="w", padx=(18, 10), pady=5)
        editable_widgets.append(entry)
        if hint:
            tk.Label(tab, text=hint, fg="#666666", anchor="w").grid(
                row=row, column=2, sticky="w", pady=5
            )

    add_number(
        threshold_tab,
        0,
        "three_min",
        "初始3人兵种合格门槛",
        "只随机初始3人时使用",
    )
    add_number(
        threshold_tab,
        1,
        "seven_min",
        "完整7人兵种合格门槛",
        "低于门槛时直接重新随机",
    )
    add_number(
        threshold_tab,
        2,
        "normal_average",
        "普通兵种质量分界",
        "达到后使用较低的特技要求",
    )
    add_number(
        threshold_tab,
        3,
        "high_average",
        "高兵种质量分界",
        "开启直接合格时使用",
    )

    add_number(job_tab, 0, "base_weight", "兵种基础分权重")
    add_number(
        job_tab,
        1,
        "affinity_min",
        "适配加成最低基础分",
        "低于此分数不计算人物适配",
    )
    add_number(
        job_tab,
        2,
        "primary_bonus",
        "主要倾向加成比例",
        "0.06 表示增加6%",
    )
    add_number(
        job_tab,
        3,
        "secondary_bonus",
        "次要倾向加成比例",
        "0.03 表示增加3%",
    )
    add_number(job_tab, 4, "xiahou_penalty", "夏侯惇为文官型时扣分")
    add_number(job_tab, 5, "master_weight", "文官型兵种过多扣分权重")
    affinity_enabled = tk.BooleanVar()
    balance_enabled = tk.BooleanVar()
    bool_vars["affinity_enabled"] = affinity_enabled
    bool_vars["balance_enabled"] = balance_enabled
    affinity_check = tk.Checkbutton(
        job_tab,
        text="启用人物兵种适配加成",
        variable=affinity_enabled,
        anchor="w",
    )
    affinity_check.grid(row=6, column=0, columnspan=2, sticky="w", pady=5)
    balance_check = tk.Checkbutton(
        job_tab,
        text="启用文官型兵种过多扣分",
        variable=balance_enabled,
        anchor="w",
    )
    balance_check.grid(row=7, column=0, columnspan=2, sticky="w", pady=5)
    editable_widgets.extend((affinity_check, balance_check))

    affinity_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
    tk.Label(affinity_tab, text="人物").grid(
        row=0, column=0, sticky="w", pady=(0, 8)
    )
    tk.Label(affinity_tab, text="主要倾向").grid(
        row=0, column=1, sticky="w", padx=(18, 0), pady=(0, 8)
    )
    tk.Label(affinity_tab, text="次要倾向").grid(
        row=0, column=2, sticky="w", padx=(18, 0), pady=(0, 8)
    )
    primary_options = tuple(TYPE_LABELS[value] for value in AFFINITY_TYPES)
    secondary_options = tuple(TYPE_LABELS[value] for value in AFFINITY_TYPES)
    for row, member in enumerate(team_members, start=1):
        member_name = member[0] if isinstance(member, tuple) else str(member)
        tk.Label(affinity_tab, text=member_name).grid(
            row=row, column=0, sticky="w", pady=4
        )
        primary_var = tk.StringVar()
        secondary_var = tk.StringVar()
        affinity_vars[member_name] = (primary_var, secondary_var)
        primary = ttk.Combobox(
            affinity_tab,
            textvariable=primary_var,
            values=primary_options,
            state="readonly",
            width=14,
        )
        secondary = ttk.Combobox(
            affinity_tab,
            textvariable=secondary_var,
            values=secondary_options,
            state="readonly",
            width=14,
        )
        primary.grid(row=row, column=1, padx=(18, 0), pady=4)
        secondary.grid(row=row, column=2, padx=(18, 0), pady=4)
        editable_widgets.extend((primary, secondary))

    job_score_vars: dict[str, tk.StringVar] = {}
    job_score_items = []
    for _job_id, job in sorted(job_map.items()):
        job_name, default_score, _job_type = job
        variable = tk.StringVar(value=str(default_score))
        job_score_vars[job_name] = variable
        job_score_items.append((job_name, variable, ""))
    job_score_grid = ScoreGrid(base_score_tab, job_score_items)
    job_score_grid.pack(fill="both", expand=True)

    add_number(skill_tab, 0, "ordinary_weight", "普通优质特技基础分")
    add_number(skill_tab, 1, "strong_weight", "强力特技基础分")
    add_number(skill_tab, 2, "special_weight", "特殊特技基础分")
    add_number(
        skill_tab,
        3,
        "medium_skills",
        "普通兵种组合所需特技分",
    )
    add_number(
        skill_tab,
        4,
        "low_skills",
        "较低兵种组合所需特技分",
    )
    special_auto = tk.BooleanVar()
    high_auto = tk.BooleanVar()
    bool_vars["special_auto"] = special_auto
    bool_vars["high_auto"] = high_auto
    special_check = tk.Checkbutton(
        skill_tab,
        text="出现特殊特技时直接合格",
        variable=special_auto,
        anchor="w",
    )
    special_check.grid(row=5, column=0, columnspan=2, sticky="w", pady=5)
    high_check = tk.Checkbutton(
        skill_tab,
        text="达到高兵种质量分界时直接合格",
        variable=high_auto,
        anchor="w",
    )
    high_check.grid(row=6, column=0, columnspan=2, sticky="w", pady=5)
    editable_widgets.extend((special_check, high_check))

    skill_score_vars: dict[str, tk.StringVar] = {}
    skill_defaults: dict[str, float] = {}
    skill_categories: dict[str, str] = {}
    skill_score_items = []
    for skill_name, default_score, category in skill_catalog:
        variable = tk.StringVar(value=f"{default_score:g}")
        skill_score_vars[skill_name] = variable
        skill_defaults[skill_name] = float(default_score)
        skill_categories[skill_name] = category
        skill_score_items.append((skill_name, variable, category))
    skill_score_grid = ScoreGrid(skill_score_tab, skill_score_items)
    skill_score_grid.pack(fill="both", expand=True)
    score_grids = (job_score_grid, skill_score_grid)

    def is_builtin(name: str) -> bool:
        return bool(working["profiles"][name].get("builtin"))

    def set_editable(enabled: bool) -> None:
        for widget in editable_widgets:
            try:
                if isinstance(widget, ttk.Combobox):
                    widget.configure(state="readonly" if enabled else "disabled")
                else:
                    widget.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass
        for score_grid in score_grids:
            score_grid.set_enabled(enabled)
        reset_button.configure(state="normal" if enabled else "disabled")
        rename_button.configure(state="normal" if enabled else "disabled")
        delete_button.configure(state="normal" if enabled else "disabled")

    def store_profile(name: str) -> None:
        if loading or is_builtin(name):
            return
        for score_grid in score_grids:
            score_grid.commit_pending()
        profile = working["profiles"][name]
        profile["editorMode"] = (
            "simple" if notebook.index(notebook.select()) == 0 else "advanced"
        )
        for key, variable in simple_vars.items():
            profile["simpleSettings"][key] = variable.get()
        profile["threePerson"]["minJobAverage"] = float(
            number_vars["three_min"].get()
        )
        category_scores = {
            "优质": float(number_vars["ordinary_weight"].get()),
            "强力": float(number_vars["strong_weight"].get()),
            "特殊": float(number_vars["special_weight"].get()),
            "其他": 0.0,
        }
        profile["sevenPerson"].update(
            {
                "minJobAverage": float(number_vars["seven_min"].get()),
                "normalJobAverage": float(
                    number_vars["normal_average"].get()
                ),
                "highJobAverage": float(number_vars["high_average"].get()),
                "mediumMinSkillScore": float(
                    number_vars["medium_skills"].get()
                ),
                "lowMinSkillScore": float(number_vars["low_skills"].get()),
                "ordinarySkillWeight": float(
                    number_vars["ordinary_weight"].get()
                ),
                "strongSkillWeight": float(
                    number_vars["strong_weight"].get()
                ),
                "specialSkillWeight": float(
                    number_vars["special_weight"].get()
                ),
                "skillBaseScores": {
                    skill_name: float(variable.get())
                    for skill_name, variable in skill_score_vars.items()
                    if float(variable.get())
                    != category_scores.get(
                        skill_categories[skill_name],
                        skill_defaults[skill_name],
                    )
                },
                "specialSkillAutoPass": bool(special_auto.get()),
                "highJobAutoPass": bool(high_auto.get()),
            }
        )
        profile["jobScoring"].update(
            {
                "baseScoreWeight": float(number_vars["base_weight"].get()),
                "affinityEnabled": bool(affinity_enabled.get()),
                "affinityMinBaseScore": float(
                    number_vars["affinity_min"].get()
                ),
                "primaryBonusRate": float(
                    number_vars["primary_bonus"].get()
                ),
                "secondaryBonusRate": float(
                    number_vars["secondary_bonus"].get()
                ),
                "xiahouDunMasterPenalty": float(
                    number_vars["xiahou_penalty"].get()
                ),
                "extraMasterPenaltyEnabled": bool(balance_enabled.get()),
                "extraMasterPenaltyWeight": float(
                    number_vars["master_weight"].get()
                ),
                "jobBaseScores": {
                    job_name: float(variable.get())
                    for job_name, variable in job_score_vars.items()
                },
            }
        )
        profile["memberAffinity"] = {
            member: {
                "primaryType": TYPE_VALUES[primary.get()],
                "secondaryType": TYPE_VALUES[secondary.get()],
            }
            for member, (primary, secondary) in affinity_vars.items()
        }
        if profile["editorMode"] == "simple":
            apply_simple_settings(profile)

    def load_profile(name: str) -> None:
        nonlocal loading, selected_name
        loading = True
        try:
            selected_name = name
            profile = working["profiles"][name]
            for key, variable in simple_vars.items():
                variable.set(profile["simpleSettings"][key])
            three = profile["threePerson"]
            seven = profile["sevenPerson"]
            scoring = profile["jobScoring"]
            values = {
                "three_min": three["minJobAverage"],
                "seven_min": seven["minJobAverage"],
                "normal_average": seven["normalJobAverage"],
                "high_average": seven["highJobAverage"],
                "medium_skills": seven["mediumMinSkillScore"],
                "low_skills": seven["lowMinSkillScore"],
                "ordinary_weight": seven["ordinarySkillWeight"],
                "strong_weight": seven["strongSkillWeight"],
                "special_weight": seven["specialSkillWeight"],
                "base_weight": scoring["baseScoreWeight"],
                "affinity_min": scoring["affinityMinBaseScore"],
                "primary_bonus": scoring["primaryBonusRate"],
                "secondary_bonus": scoring["secondaryBonusRate"],
                "xiahou_penalty": scoring["xiahouDunMasterPenalty"],
                "master_weight": scoring["extraMasterPenaltyWeight"],
            }
            for key, value in values.items():
                number_vars[key].set(f"{value:g}")
            special_auto.set(seven["specialSkillAutoPass"])
            high_auto.set(seven["highJobAutoPass"])
            affinity_enabled.set(scoring["affinityEnabled"])
            balance_enabled.set(scoring["extraMasterPenaltyEnabled"])
            for member, (primary, secondary) in affinity_vars.items():
                row = profile["memberAffinity"][member]
                primary.set(TYPE_LABELS[row["primaryType"]])
                secondary.set(TYPE_LABELS[row["secondaryType"]])
            overrides = scoring["jobBaseScores"]
            defaults = {
                job[0]: job[1] for job in job_map.values()
            }
            for job_name, variable in job_score_vars.items():
                variable.set(f"{overrides.get(job_name, defaults[job_name]):g}")
            skill_overrides = seven["skillBaseScores"]
            category_scores = {
                "优质": seven["ordinarySkillWeight"],
                "强力": seven["strongSkillWeight"],
                "特殊": seven["specialSkillWeight"],
                "其他": 0.0,
            }
            for skill_name, variable in skill_score_vars.items():
                fallback_score = category_scores.get(
                    skill_categories[skill_name],
                    skill_defaults[skill_name],
                )
                variable.set(
                    f"{skill_overrides.get(skill_name, fallback_score):g}"
                )
            for score_grid in score_grids:
                score_grid.refresh()
            notebook.select(
                simple_tab
                if profile["editorMode"] == "simple"
                else advanced_tab
            )
            set_editable(not is_builtin(name))
        finally:
            loading = False

    def refresh_profiles(select_name: str) -> None:
        profile_combo.configure(values=tuple(working["profiles"]))
        profile_var.set(select_name)
        load_profile(select_name)

    def switch_profile(_event=None) -> None:
        new_name = profile_var.get()
        if new_name == selected_name:
            return
        try:
            store_profile(selected_name)
        except Exception as exc:
            profile_var.set(selected_name)
            messagebox.showerror(
                "当前规则无法切换",
                f"请先修正当前页面中的数值。\n\n{exc}",
                parent=editor,
            )
            return
        load_profile(new_name)

    def unique_name(base: str) -> str:
        if base not in working["profiles"]:
            return base
        index = 2
        while f"{base} {index}" in working["profiles"]:
            index += 1
        return f"{base} {index}"

    def copy_profile() -> None:
        try:
            store_profile(selected_name)
        except Exception as exc:
            messagebox.showerror("无法复制", str(exc), parent=editor)
            return
        name = unique_name(f"{selected_name}副本")
        profile = copy.deepcopy(working["profiles"][selected_name])
        profile["builtin"] = False
        working["profiles"][name] = profile
        refresh_profiles(name)

    def new_profile() -> None:
        copy_profile()

    def rename_profile() -> None:
        nonlocal selected_name
        if is_builtin(selected_name):
            return
        name = simpledialog.askstring(
            "重命名规则",
            "输入新的规则名称：",
            initialvalue=selected_name,
            parent=editor,
        )
        if not name:
            return
        name = name.strip()
        if name in working["profiles"] and name != selected_name:
            messagebox.showerror(
                "名称已存在", "请换一个规则名称。", parent=editor
            )
            return
        profile = working["profiles"].pop(selected_name)
        old_name = selected_name
        working["profiles"][name] = profile
        if working["activeProfile"] == old_name:
            working["activeProfile"] = name
        refresh_profiles(name)

    def delete_profile() -> None:
        if is_builtin(selected_name):
            return
        if not messagebox.askyesno(
            "删除规则",
            f"确定删除“{selected_name}”吗？",
            parent=editor,
        ):
            return
        was_active = working["activeProfile"] == selected_name
        del working["profiles"][selected_name]
        target = DEFAULT_PROFILE_NAME
        if was_active:
            working["activeProfile"] = target
        refresh_profiles(target)

    def reset_profile() -> None:
        if is_builtin(selected_name):
            return
        name = selected_name
        profile = copy.deepcopy(
            default_rule_config()["profiles"][DEFAULT_PROFILE_NAME]
        )
        profile["builtin"] = False
        working["profiles"][name] = profile
        load_profile(name)

    def choose_export_scope() -> str | None:
        choice = {"value": None}
        dialog = tk.Toplevel(editor)
        dialog.withdraw()
        dialog.title("导出规则")
        dialog.resizable(False, False)
        dialog.transient(editor)
        frame = tk.Frame(dialog, padx=18, pady=16)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="选择要导出的规则：", anchor="w").pack(
            fill="x"
        )
        values = ("全部规则", *working["profiles"].keys())
        scope_var = tk.StringVar(value=selected_name)
        combo = ttk.Combobox(
            frame,
            textvariable=scope_var,
            values=values,
            state="readonly",
            width=30,
        )
        combo.pack(fill="x", pady=(8, 16))
        actions = tk.Frame(frame)
        actions.pack(fill="x")

        def confirm() -> None:
            choice["value"] = scope_var.get()
            dialog.destroy()

        tk.Button(
            actions, text="取消", command=dialog.destroy, width=10
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            actions, text="下一步", command=confirm, width=10
        ).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        x = editor.winfo_rootx() + (editor.winfo_width() - width) // 2
        y = editor.winfo_rooty() + (editor.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        dialog.deiconify()
        dialog.lift()
        dialog.grab_set()
        combo.focus_set()
        dialog.wait_window()
        return choice["value"]

    def export_rules() -> None:
        try:
            store_profile(selected_name)
        except Exception as exc:
            messagebox.showerror(
                "规则无法导出",
                f"请先修正当前页面中的数值。\n\n{exc}",
                parent=editor,
            )
            return
        scope = choose_export_scope()
        if not scope:
            return
        names = None if scope == "全部规则" else (scope,)
        try:
            payload = build_rule_export(working, names)
        except Exception as exc:
            messagebox.showerror("规则无法导出", str(exc), parent=editor)
            return
        safe_scope = "全部" if scope == "全部规则" else scope
        default_name = (
            f"随机规则-{safe_scope}-{datetime.now():%Y%m%d}.json"
        )
        path = filedialog.asksaveasfilename(
            parent=editor,
            title="保存规则文件",
            defaultextension=".json",
            filetypes=(("规则文件", "*.json"), ("所有文件", "*.*")),
            initialfile=default_name,
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            messagebox.showerror(
                "规则无法导出", f"文件保存失败：{exc}", parent=editor
            )
            return
        messagebox.showinfo(
            "规则已导出",
            f"已导出到：\n{path}",
            parent=editor,
        )

    def import_rules() -> None:
        nonlocal working, saved_snapshot
        try:
            store_profile(selected_name)
        except Exception as exc:
            messagebox.showerror(
                "规则无法导入",
                f"请先修正当前页面中的数值。\n\n{exc}",
                parent=editor,
            )
            return
        path = filedialog.askopenfilename(
            parent=editor,
            title="选择规则文件",
            filetypes=(("规则文件", "*.json"), ("所有文件", "*.*")),
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            merged, imported_names = merge_rule_export(working, payload)
            save_rule_config(base_dir, merged)
        except Exception as exc:
            messagebox.showerror(
                "规则无法导入",
                f"所选文件无法使用：\n{exc}",
                parent=editor,
            )
            return
        working = merged
        saved_snapshot = json.dumps(
            validate_rule_config(working),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        on_saved(working)
        refresh_profiles(imported_names[0])
        messagebox.showinfo(
            "规则已导入",
            f"已追加并保存 {len(imported_names)} 套规则。",
            parent=editor,
        )

    def has_unsaved_changes() -> bool:
        try:
            store_profile(selected_name)
            current_snapshot = json.dumps(
                validate_rule_config(working),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except Exception:
            return True
        return current_snapshot != saved_snapshot

    def request_close() -> None:
        if has_unsaved_changes() and not messagebox.askyesno(
            "放弃未保存的修改",
            "当前规则有尚未保存的修改，确定关闭吗？",
            parent=editor,
        ):
            return
        editor.destroy()

    def save_all() -> None:
        try:
            store_profile(selected_name)
            normalized = validate_rule_config(working)
            path = save_rule_config(base_dir, normalized)
        except Exception as exc:
            messagebox.showerror(
                "规则无法保存",
                f"请检查填写内容。\n\n{exc}",
                parent=editor,
            )
            return
        on_saved(normalized)
        messagebox.showinfo(
            "规则已保存",
            f"规则已保存到工具目录：\n{path.name}",
            parent=editor,
        )
        editor.destroy()

    new_button = tk.Button(action_frame, text="新建副本", command=new_profile)
    rename_button = tk.Button(
        action_frame, text="重命名", command=rename_profile
    )
    delete_button = tk.Button(
        action_frame, text="删除", command=delete_profile
    )
    reset_button = tk.Button(
        action_frame, text="恢复默认参数", command=reset_profile
    )
    help_button = tk.Button(
        action_frame,
        text="规则说明",
        command=lambda: show_advanced_help(
            editor, advanced_book.index(advanced_book.select())
        ),
        width=10,
    )
    export_button = tk.Button(
        action_frame,
        text="导出规则",
        command=export_rules,
        width=10,
    )
    import_button = tk.Button(
        action_frame,
        text="导入规则",
        command=import_rules,
        width=10,
    )
    new_button.pack(side="left")
    rename_button.pack(side="left", padx=(8, 0))
    delete_button.pack(side="left", padx=(8, 0))
    reset_button.pack(side="left", padx=(8, 0))
    help_button.pack(side="right", padx=(0, 8))
    export_button.pack(side="right", padx=(0, 8))
    import_button.pack(side="right", padx=(0, 8))

    footer = tk.Frame(editor, padx=14, pady=12)
    footer.pack(fill="x")
    tk.Label(
        footer,
        text="内置默认规则只读。需要调整时，请先创建副本。",
        fg="#555555",
    ).pack(side="left")
    tk.Button(
        footer, text="取消", command=request_close, width=10
    ).pack(side="right", padx=(8, 0))
    tk.Button(
        footer, text="保存规则", command=save_all, width=12
    ).pack(side="right")

    profile_combo.bind("<<ComboboxSelected>>", switch_profile)
    editor.protocol("WM_DELETE_WINDOW", request_close)
    load_profile(selected_name)
    editor.update_idletasks()
    width = max(980, editor.winfo_reqwidth())
    height = max(760, editor.winfo_reqheight())
    if parent.winfo_viewable():
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    else:
        x = (editor.winfo_screenwidth() - width) // 2
        y = (editor.winfo_screenheight() - height) // 2
    x = max(0, min(x, editor.winfo_screenwidth() - width))
    y = max(0, min(y, editor.winfo_screenheight() - height))
    editor.geometry(f"{width}x{height}+{x}+{y}")
    editor.deiconify()
    editor.lift()
    editor.grab_set()
