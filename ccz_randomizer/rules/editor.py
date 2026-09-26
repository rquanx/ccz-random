from __future__ import annotations

import copy
import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from ccz_randomizer.rules.config import (
    AFFINITY_TYPES,
    DEFAULT_PROFILE_NAME,
    JOB_AFFINITY_TYPES,
    SIMPLE_PRESET_OPTIONS,
    apply_simple_settings,
    build_rule_export,
    classify_skill_score,
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
SKILL_TIER_LABELS = {
    "other": "其他",
    "ordinary": "优质",
    "strong": "强力",
    "special": "特殊",
}

ADVANCED_HELP_SECTIONS = (
    (
        "先看这里",
        """【随机结果怎样才会保存】
每次随机都会先检查兵种，再检查特技。兵种和特技都合格，才会保存结果。

只随机3人：检查曹操、夏侯惇、夏侯渊的兵种和特技。
完整7人：检查全部7人的兵种和特技。

【简单模式和高级模式】
普通用户建议使用简单模式，只需要选择“宽松、标准、严格”。
高级模式适合希望调整评分侧重点的用户。它只改变工具怎样判断合格，不会修改游戏数据，也不会指定必须随机出某个兵种或特技。

【调整数值时记住两点】
合格门槛越高，越难通过，随机时间通常越长。
兵种或特技分数越高，包含它的结果越容易通过。

提示：不确定怎样设置时，保留默认规则即可。建议先创建规则副本，再进行调整。""",
    ),
    (
        "阶段门槛",
        """【初始3人兵种合格门槛】
只随机3人时使用。默认按三人的兵种平均分判断，也可以改为按达到门槛的人数判断。
调高：兵种要求更严格，进入特技检查的结果更少。
调低：兵种要求更宽松，但仍然需要通过特技检查。

【完整7人兵种合格门槛】
完整7人时使用。默认按7人的兵种平均分判断，也可以改为按达到门槛的人数判断。
调高：更难通过。调低：更容易进入特技检查。

【兵种合格方式】
平均分达到门槛：队伍兵种平均分大于或等于门槛时合格。
任意人数达到门槛：达到门槛的个人数量大于或等于指定人数时合格。例如门槛为7、人数为3，表示至少3人的个人兵种分大于或等于7。

【普通兵种质量分界】
决定本轮使用哪一个特技合格门槛，3人和7人模式都会使用。
兵种平均分达到该数值时，使用“普通兵种组合所需特技分”；未达到时，使用要求更高的“较低兵种组合所需特技分”。

【高兵种质量分界】
只有开启“达到高兵种质量分界时直接合格”后才生效。
兵种平均分达到该数值时，不再要求特技总分，但工具仍会读取特技并生成结果图。

提示：门槛越高，规则越严格。修改门槛不会改变兵种本身的基础分。""",
    ),
    (
        "兵种评分",
        """【兵种分数是怎样算出的】
工具先取每个兵种的基础分，再考虑人物倾向和队伍结构，最后计算队伍的兵种平均分。

【兵种基础分权重】
统一放大或缩小所有兵种的基础分。1表示保持原值。
大于1：兵种基础分的影响更大。小于1：人物倾向和扣分规则相对更明显。
普通用户建议保持1。

【人物兵种适配加成】
开启后，人物获得符合主要倾向或次要倾向的兵种时会加分。
关闭后，所有人物只看兵种基础分，不再考虑人物倾向。

【适配加成最低基础分】
基础分低于该数值的兵种不会获得人物倾向加成。
它可以避免低质量兵种仅靠人物倾向获得过多加分。

【主要倾向、次要倾向加成比例】
主要倾向的加成通常高于次要倾向。0.06表示增加6%。

【夏侯惇为文官型时扣分】
夏侯惇得到文官型兵种时额外扣除的分数。数值越高，越不希望出现这种组合。

【文官型兵种过多扣分】
开启后，队伍中的文官型兵种越多，扣分越多，用于避免队伍结构过于集中。""",
    ),
    (
        "人物倾向",
        """【它有什么作用】
人物倾向只用于加分，不会指定或禁止任何兵种。
例如把曹操的主要倾向设为全能型，只代表曹操得到全能型兵种时更容易加分，并不代表曹操只能随机到全能型。

【主要倾向】
匹配时使用“主要倾向加成比例”，加成通常较高。

【次要倾向】
匹配时使用“次要倾向加成比例”，加成通常较低。

【选择“无”】
表示不设置该项倾向，也不会产生对应的加成。

【兵种所属类型】
点击“设置兵种所属类型”可以查看全部兵种当前所属的类型，也可以在规则副本中调整。
修改后，人物倾向加成、夏侯惇文官型扣分和文官型兵种过多扣分都会按照新类型计算。
内置默认规则只能查看，请先新建规则副本再修改。
这里修改的是当前规则，保存后会随规则一起导入、导出。
修改所属类型不会改变兵种基础分，也不会修改游戏数据。

提示：如果不希望人物倾向影响结果，可以关闭“人物兵种适配加成”，不需要逐个人改成“无”。""",
    ),
    (
        "兵种基础分",
        """【它有什么作用】
这里设置每个兵种在评分时使用的基础分。

【调高某个兵种】
包含该兵种的组合更容易达到兵种合格门槛。

【调低某个兵种】
包含该兵种的组合更难达到兵种合格门槛。

【它不会做什么】
修改分数不会改变游戏里的兵种数据，也不会指定或排除某个兵种。游戏仍然按照原本逻辑随机。

提示：这里的分数还会受到“兵种基础分权重”、人物倾向加成和队伍结构扣分影响。普通用户不建议一次修改太多兵种。""",
    ),
    (
        "特技评分",
        """【适用范围】
只随机3人和完整7人都会检查特技。3人模式统计初始3人的特技，7人模式统计全部7人的特技。

【优质、强力、特殊特技基础分】
这三个数值同时是该档次的默认分数和分档门槛。
单项特技的最终基础分达到哪个门槛，就按哪个档次处理；达到特殊门槛后，也会参与“出现特殊特技时直接合格”。
三个门槛必须满足：普通优质 ≤ 强力 ≤ 特殊。

【普通兵种组合所需特技分】
兵种平均分达到“普通兵种质量分界”时，特技总分需要达到该数值。

【较低兵种组合所需特技分】
兵种平均分未达到普通质量分界时使用。通常应比上一个门槛更高，用更好的特技弥补兵种不足。

【出现特殊特技时直接合格】
开启后，只要本次检查的人物中出现特殊特技，就不再要求特技总分。

【达到高兵种质量分界时直接合格】
开启后，兵种平均分足够高时，不再要求特技总分。

提示：特技合格门槛越高，结果越难通过，随机时间通常也会更长。""",
    ),
    (
        "特技基础分",
        """【它有什么作用】
这里可以单独调整某一个特技的分数。单独设置的分数优先于该特技所属类别的默认分数。

【分数会改变特技档次】
最终基础分达到特殊门槛时按特殊特技处理；达到强力门槛时按强力特技处理；达到普通优质门槛时按优质特技处理。
档次变化会同时影响人物类型匹配和“出现特殊特技时直接合格”。

【举例】
普通优质、强力、特殊门槛分别为1、2、5分时，把一个优质特技改为5分，它会按特殊特技处理；把特殊特技降到1分，它会按优质特技处理。

【“其他”类别】
“其他”类别默认不计分。你可以在这里给少数想要重视的特技单独设置分数。

【人物类型是否匹配】
优质和强力特技只有符合人物类型时才会正常计分。例如文官型特技出现在武将型人物身上时，可能不会计入有效分数。
当前分数达到特殊门槛的特技不受这一限制。

【直接合格的优先级】
如果开启“出现特殊特技时直接合格”，出现特殊特技后会直接通过，不再比较这个特技的单项分数。

提示：这里适合少量微调。大范围调整时，优先修改“特技评分”中的分类分数。""",
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
        category_resolver: Callable[[str, str, str], str] | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.items = items
        self.category_resolver = category_resolver
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
        self.commit_pending(refresh=False)
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
            display_category = (
                self.category_resolver(name, variable.get(), category)
                if self.category_resolver is not None
                else category
            )
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
            if display_category:
                category_color = {
                    "特殊": "#b24747",
                    "强力": "#496fa8",
                    "优质": "#4d8560",
                    "其他": "#888888",
                }.get(display_category, "#888888")
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
            value_x1 = max(score_x1 + 92, score_x2 - 58)
            self.canvas.create_rectangle(
                score_x1,
                score_y1,
                score_x2,
                score_y2,
                fill="#fafafa" if self.enabled else "#f0f0f0",
                outline="#b8b8b8",
            )
            self.canvas.create_line(
                value_x1,
                score_y1,
                value_x1,
                score_y2,
                fill="#d0d0d0",
            )
            self.canvas.create_text(
                score_x1 + 8,
                (score_y1 + score_y2) / 2,
                text=(
                    f"{display_category} · 基础分"
                    if display_category
                    else "基础分"
                ),
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
                (value_x1, score_y1, score_x2, score_y2, index)
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

    def commit_pending(self, refresh: bool = True) -> None:
        if self.editor is None or self.editing_index is None:
            return
        try:
            self.items[self.editing_index][1].set(self.editor.get())
        finally:
            self._destroy_editor()
        if refresh:
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
            spacing1=3,
            spacing3=8,
        )
        text.tag_configure(
            "heading",
            font=("Microsoft YaHei UI", 10, "bold"),
            foreground="#1f4e79",
            spacing1=8,
            spacing3=3,
        )
        text.tag_configure(
            "tip",
            foreground="#555555",
            lmargin1=8,
            lmargin2=8,
            spacing1=8,
        )
        for line in content.splitlines():
            tag = None
            if line.startswith("【") and line.endswith("】"):
                tag = "heading"
            elif line.startswith("提示："):
                tag = "tip"
            text.insert("end", line + "\n", tag)
        text.configure(state="disabled")
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    help_index = selected_index + 1
    if 0 <= help_index < len(tabs):
        book.select(tabs[help_index])

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


def show_job_type_editor(
    parent,
    job_map: dict,
    current_values: dict[str, str],
    editable: bool,
    on_apply: Callable[[dict[str, str]], None],
) -> None:
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title("兵种所属类型")
    dialog.geometry("820x500")
    dialog.minsize(700, 420)
    dialog.transient(parent)

    header = tk.Frame(dialog, padx=16, pady=12)
    header.pack(fill="x")
    tk.Label(
        header,
        text="兵种所属类型",
        font=("Microsoft YaHei UI", 11, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        header,
        text=(
            "类型会影响人物倾向加成和文官型相关扣分。"
            + ("" if editable else "内置规则仅供查看，请先新建副本再修改。")
        ),
        fg="#666666",
        anchor="w",
    ).pack(fill="x", pady=(4, 0))

    body = ScrollableFrame(dialog)
    body.pack(fill="both", expand=True, padx=16)
    options = tuple(TYPE_LABELS[value] for value in JOB_AFFINITY_TYPES)
    variables: dict[str, tk.StringVar] = {}
    jobs = [job for _job_id, job in sorted(job_map.items())]
    column_count = 4
    rows_per_column = (len(jobs) + column_count - 1) // column_count
    for index, (job_name, _score, default_type) in enumerate(jobs):
        group = index // rows_per_column
        row = index % rows_per_column
        label_column = group * 2
        value_column = label_column + 1
        variable = tk.StringVar(
            value=TYPE_LABELS[current_values.get(job_name, default_type)]
        )
        variables[job_name] = variable
        tk.Label(body.body, text=job_name, anchor="w", width=9).grid(
            row=row,
            column=label_column,
            sticky="w",
            padx=(0 if group == 0 else 18, 6),
            pady=4,
        )
        combo = ttk.Combobox(
            body.body,
            textvariable=variable,
            values=options,
            state="readonly" if editable else "disabled",
            width=10,
        )
        combo.grid(
            row=row,
            column=value_column,
            sticky="w",
            pady=4,
        )

    footer = tk.Frame(dialog, padx=16, pady=12)
    footer.pack(fill="x")

    def apply_changes() -> None:
        on_apply(
            {
                job_name: TYPE_VALUES[variable.get()]
                for job_name, variable in variables.items()
            }
        )
        dialog.destroy()

    tk.Button(
        footer,
        text="取消" if editable else "关闭",
        command=dialog.destroy,
        width=10,
    ).pack(side="right")
    if editable:
        tk.Button(
            footer,
            text="确定",
            command=apply_changes,
            width=10,
        ).pack(side="right", padx=(0, 8))

    dialog.update_idletasks()
    width = max(820, dialog.winfo_reqwidth())
    height = max(500, dialog.winfo_reqheight())
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    x = max(0, min(x, dialog.winfo_screenwidth() - width))
    y = max(0, min(y, dialog.winfo_screenheight() - height))
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    dialog.deiconify()
    dialog.lift()
    dialog.grab_set()


def show_toast(parent, message: str, duration_ms: int = 1800) -> None:
    toast = tk.Toplevel(parent)
    toast.withdraw()
    toast.overrideredirect(True)
    toast.transient(parent)
    toast.configure(bg="#242424")
    tk.Label(
        toast,
        text=message,
        bg="#242424",
        fg="#ffffff",
        padx=18,
        pady=10,
        font=("Microsoft YaHei UI", 10),
    ).pack()
    toast.update_idletasks()
    width = toast.winfo_reqwidth()
    height = toast.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + parent.winfo_height() - height - 28
    x = max(0, min(x, toast.winfo_screenwidth() - width))
    y = max(0, min(y, toast.winfo_screenheight() - height))
    toast.geometry(f"{width}x{height}+{x}+{y}")
    toast.deiconify()
    toast.lift()
    toast.after(duration_ms, toast.destroy)


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
    qualification_mode_vars: dict[str, tk.StringVar] = {}
    qualification_count_vars: dict[str, tk.StringVar] = {}
    qualification_controls: dict[
        str,
        tuple[ttk.Combobox, ttk.Combobox, tk.Label],
    ] = {}

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
    qualification_mode_labels = {
        "按平均分判断": "average",
        "按达标人数判断": "count",
    }
    qualification_mode_values = {
        value: label for label, value in qualification_mode_labels.items()
    }

    def add_qualification_control(
        row: int,
        key: str,
        maximum: int,
    ) -> None:
        mode_var = tk.StringVar()
        count_var = tk.StringVar()
        qualification_mode_vars[key] = mode_var
        qualification_count_vars[key] = count_var
        mode_combo = ttk.Combobox(
            threshold_tab,
            textvariable=mode_var,
            values=tuple(qualification_mode_labels),
            state="readonly",
            width=18,
        )
        mode_combo.grid(
            row=row,
            column=3,
            sticky="w",
            padx=(20, 8),
            pady=5,
        )
        count_combo = ttk.Combobox(
            threshold_tab,
            textvariable=count_var,
            values=tuple(str(value) for value in range(1, maximum + 1)),
            state="readonly",
            width=4,
        )
        count_combo.grid(row=row, column=4, sticky="w", pady=5)
        count_label = tk.Label(
            threshold_tab,
            text="人达到门槛",
            anchor="w",
        )
        count_label.grid(row=row, column=5, sticky="w", padx=(5, 0), pady=5)
        qualification_controls[key] = (
            mode_combo,
            count_combo,
            count_label,
        )
        editable_widgets.extend((mode_combo, count_combo))

        def refresh_count_control(_event=None) -> None:
            enabled = (
                mode_var.get() == "按达标人数判断"
                and str(mode_combo.cget("state")) != "disabled"
            )
            count_combo.configure(state="readonly" if enabled else "disabled")
            count_label.configure(fg="#222222" if enabled else "#999999")

        mode_combo.bind(
            "<<ComboboxSelected>>",
            refresh_count_control,
            add="+",
        )

    add_qualification_control(0, "three", 3)
    add_number(
        threshold_tab,
        1,
        "seven_min",
        "完整7人兵种合格门槛",
        "低于门槛时直接重新随机",
    )
    add_qualification_control(1, "seven", 7)
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

    job_default_types = {
        job_name: job_type
        for job_name, _score, job_type in job_map.values()
    }
    job_type_vars = {
        job_name: tk.StringVar(value=job_type)
        for job_name, job_type in job_default_types.items()
    }

    def apply_job_types(values: dict[str, str]) -> None:
        for job_name, job_type in values.items():
            job_type_vars[job_name].set(job_type)

    def open_job_type_editor() -> None:
        show_job_type_editor(
            editor,
            job_map,
            {
                job_name: variable.get()
                for job_name, variable in job_type_vars.items()
            },
            not is_builtin(selected_name),
            apply_job_types,
        )

    tk.Button(
        affinity_tab,
        text="设置兵种所属类型",
        command=open_job_type_editor,
        width=18,
    ).grid(
        row=len(team_members) + 2,
        column=0,
        columnspan=2,
        sticky="w",
        pady=(14, 0),
    )
    tk.Label(
        affinity_tab,
        text="查看并调整全能型、武将型、文官型的兵种归类",
        fg="#666666",
        anchor="w",
    ).grid(
        row=len(team_members) + 3,
        column=0,
        columnspan=3,
        sticky="w",
        pady=(4, 0),
    )

    job_score_vars: dict[str, tk.StringVar] = {}
    job_score_items = []
    for _job_id, job in sorted(job_map.items()):
        job_name, default_score, _job_type = job
        variable = tk.StringVar(value=str(default_score))
        job_score_vars[job_name] = variable
        job_score_items.append((job_name, variable, ""))
    job_score_grid = ScoreGrid(base_score_tab, job_score_items)
    job_score_grid.pack(fill="both", expand=True)

    add_number(
        skill_tab,
        0,
        "ordinary_weight",
        "普通优质特技基础分 / 门槛",
    )
    add_number(
        skill_tab,
        1,
        "strong_weight",
        "强力特技基础分 / 门槛",
    )
    add_number(
        skill_tab,
        2,
        "special_weight",
        "特殊特技基础分 / 门槛",
    )
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

    def resolve_skill_tier(
        _skill_name: str,
        score_text: str,
        original_category: str,
    ) -> str:
        try:
            tier = classify_skill_score(
                float(score_text),
                float(number_vars["ordinary_weight"].get()),
                float(number_vars["strong_weight"].get()),
                float(number_vars["special_weight"].get()),
            )
            return SKILL_TIER_LABELS[tier]
        except (KeyError, TypeError, ValueError):
            return original_category

    skill_score_grid = ScoreGrid(
        skill_score_tab,
        skill_score_items,
        category_resolver=resolve_skill_tier,
    )
    skill_score_grid.pack(fill="both", expand=True)
    score_grids = (job_score_grid, skill_score_grid)

    refresh_skill_grid_job: str | None = None

    def refresh_skill_grid() -> None:
        nonlocal refresh_skill_grid_job
        refresh_skill_grid_job = None
        skill_score_grid.refresh()

    def schedule_skill_grid_refresh(*_args) -> None:
        nonlocal refresh_skill_grid_job
        if refresh_skill_grid_job is not None:
            editor.after_cancel(refresh_skill_grid_job)
        refresh_skill_grid_job = editor.after(80, refresh_skill_grid)

    def cancel_skill_grid_refresh(event) -> None:
        nonlocal refresh_skill_grid_job
        if event.widget != editor or refresh_skill_grid_job is None:
            return
        try:
            editor.after_cancel(refresh_skill_grid_job)
        except tk.TclError:
            pass
        refresh_skill_grid_job = None

    editor.bind("<Destroy>", cancel_skill_grid_refresh, add="+")
    for key in ("ordinary_weight", "strong_weight", "special_weight"):
        number_vars[key].trace_add("write", schedule_skill_grid_refresh)

    def is_builtin(name: str) -> bool:
        return bool(working["profiles"][name].get("builtin"))

    def refresh_qualification_controls(enabled: bool) -> None:
        for key, (mode_combo, count_combo, count_label) in (
            qualification_controls.items()
        ):
            count_enabled = (
                enabled
                and qualification_mode_vars[key].get()
                == "按达标人数判断"
            )
            mode_combo.configure(state="readonly" if enabled else "disabled")
            count_combo.configure(
                state="readonly" if count_enabled else "disabled"
            )
            count_label.configure(
                fg="#222222" if count_enabled else "#999999"
            )

    def set_editable(enabled: bool) -> None:
        for widget in editable_widgets:
            try:
                if isinstance(widget, ttk.Combobox):
                    widget.configure(state="readonly" if enabled else "disabled")
                else:
                    widget.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass
        refresh_qualification_controls(enabled)
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
        profile["threePerson"]["jobQualificationMode"] = (
            qualification_mode_labels[qualification_mode_vars["three"].get()]
        )
        profile["threePerson"]["minQualifiedCount"] = int(
            qualification_count_vars["three"].get()
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
                "jobQualificationMode": qualification_mode_labels[
                    qualification_mode_vars["seven"].get()
                ],
                "minQualifiedCount": int(
                    qualification_count_vars["seven"].get()
                ),
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
                "jobTypeOverrides": {
                    job_name: variable.get()
                    for job_name, variable in job_type_vars.items()
                    if variable.get() != job_default_types[job_name]
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
            for key, settings in (("three", three), ("seven", seven)):
                qualification_mode_vars[key].set(
                    qualification_mode_values[
                        settings["jobQualificationMode"]
                    ]
                )
                qualification_count_vars[key].set(
                    str(settings["minQualifiedCount"])
                )
            special_auto.set(seven["specialSkillAutoPass"])
            high_auto.set(seven["highJobAutoPass"])
            affinity_enabled.set(scoring["affinityEnabled"])
            balance_enabled.set(scoring["extraMasterPenaltyEnabled"])
            for member, (primary, secondary) in affinity_vars.items():
                row = profile["memberAffinity"][member]
                primary.set(TYPE_LABELS[row["primaryType"]])
                secondary.set(TYPE_LABELS[row["secondaryType"]])
            overrides = scoring["jobBaseScores"]
            type_overrides = scoring["jobTypeOverrides"]
            defaults = {
                job[0]: job[1] for job in job_map.values()
            }
            for job_name, variable in job_score_vars.items():
                variable.set(f"{overrides.get(job_name, defaults[job_name]):g}")
            for job_name, variable in job_type_vars.items():
                variable.set(
                    type_overrides.get(
                        job_name,
                        job_default_types[job_name],
                    )
                )
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
            save_rule_config(base_dir, normalized)
        except Exception as exc:
            messagebox.showerror(
                "规则无法保存",
                f"请检查填写内容。\n\n{exc}",
                parent=editor,
            )
            return
        on_saved(normalized)
        editor.destroy()
        show_toast(parent, "规则已保存")

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
            editor,
            (
                -1
                if notebook.index(notebook.select()) == 0
                else advanced_book.index(advanced_book.select())
            ),
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
