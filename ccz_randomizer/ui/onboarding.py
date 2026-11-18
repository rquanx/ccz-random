"""A spotlight walkthrough over the real main-window controls."""
import tkinter as tk
from tkinter import ttk

from ccz_randomizer.ui.window_events import bind_window_event
from ccz_randomizer.ui.spotlight import Spotlight, card_position, place_surface
from ccz_randomizer.ui.theme import COLORS, FONT


STEPS = (
    ('先准备第20栏存档',
     '先在游戏里按提示完成许子将配置，在剧情推进、触发随机之前，用游戏菜单保存到第20栏。'
     '回到工具后再开始随机。把鼠标移到主界面的“第20栏”上，可以看位置示意图。', ('source',)),
    ('选一套规则，先用默认设置',
     '在“规则”下拉框选择方案，第一次可以先用默认规则。想调整筛选要求，点“规则设置”；'
     '内置规则只读，先点“新建副本”再改。规则控制评分和筛选，不改变游戏本身的随机效果。', ('rules', 'rule_editor')),
    ('先用单实例，熟悉后再循环',
     '建议先把“实例并发”填为 1，取消“循环随机”，完成一轮后再增加并发或开启循环。'
     '并发越高，设备负载越高；循环会持续生成新轮次，同号游戏存档会被后续结果覆盖。', ('runtime',)),
    ('开始随机，观察进度',
     '点击“开始随机”后，工具会先检查依赖，再自动检查并保存合格结果。依赖缺失时按提示下载安装，'
     '再点“重新检测”。运行中不要手动操作游戏或覆盖存档；需要结束时点停止，并等待后台实例退出。'
     '本引导只介绍操作，不会替你启动随机。', ('start',)),
    ('去哪里找结果',
     '合格结果保存在游戏 SV 对应槽位，回到游戏读档即可使用。点击“randResult”查看结果图；'
     '在“历史记录”中选择轮次，点“查看完整详情”比较结果，有绿色备份圆点的存档可点击导出。'
     '“数据统计”用于观察随机过程的频率，不是存档列表。', ('results', 'history', 'statistics')),
    ('记住帮助入口',
     '遇到不懂的操作，点“常见问题 → 不会用？”查看使用说明，“快速开始”按实际操作顺序讲解。'
     '“新手引导”可重看这些步骤，“随机用不了？”用于故障检测。'
     '想查宝物或特技含义，点“特效手册”，无需先随机。', ('help', 'effects')),
)


class Onboarding(tk.Toplevel):
    def __init__(self, parent, *, before, targets, open_help):
        self.root = parent.winfo_toplevel()
        super().__init__(self.root)
        self.withdraw()
        self.overrideredirect(True)
        self.transient(self.root)
        self.configure(bg=COLORS['accent'], padx=1, pady=1)
        self.targets, self.open_help = targets, open_help
        self.index = 0
        self.timer = None
        self.closed = False
        self.layout_signature = None
        self.spotlight = Spotlight(self.root)
        body = tk.Frame(self, bg=COLORS['surface'], padx=20, pady=16)
        body.pack(fill='both', expand=True)
        self.progress = tk.Label(body, bg=COLORS['surface'], fg=COLORS['accent'],
                                 font=(FONT, 10, 'bold'), anchor='w')
        self.progress.pack(fill='x')
        self.heading = tk.Label(body, bg=COLORS['surface'], fg=COLORS['ink'],
                                font=(FONT, 12, 'bold'), anchor='w', justify='left')
        self.heading.pack(fill='x', pady=(8, 0))
        self.description = tk.Label(body, bg=COLORS['surface'], fg=COLORS['muted'],
                                    font=(FONT, 10), justify='left', anchor='w')
        self.description.pack(fill='x', pady=(10, 14))
        actions = ttk.Frame(body)
        actions.pack(fill='x')
        self.previous = ttk.Button(actions, text='上一步', command=lambda: self.move(-1))
        self.previous.pack(side='left')
        ttk.Button(actions, text='跳过引导', command=self.destroy).pack(side='left', padx=8)
        self.next = ttk.Button(actions, text='下一步', style='Primary.TButton', command=lambda: self.move(1))
        self.next.pack(side='right')
        footer = tk.Frame(body, bg=COLORS['surface'])
        footer.pack(fill='x', pady=(12, 0))
        ttk.Button(footer, text='查看使用说明', command=self.help).pack(side='left')
        tk.Label(footer, text='Esc 退出引导', bg=COLORS['surface'],
                 fg=COLORS['muted'], font=(FONT, 9)).pack(side='right')
        self._remove_events = [bind_window_event(self.root, event, callback)
                               for event, callback in (('<Configure>', self.schedule_outline),
                                   ('<Map>', self.schedule_outline), ('<Unmap>', self.hide))]
        self._remove_events += [bind_window_event(widget, sequence, self.schedule_outline)
                                for widget in set(targets.values()) for sequence in ('<Map>', '<Configure>')]
        bind_window_event(self, '<Destroy>', self.cleanup)
        self.bind('<Escape>', lambda event: self.destroy())
        self.render()

    def hide(self, _event=None):
        self.withdraw()
        self.spotlight.withdraw()

    def render(self):
        title, description, _ = STEPS[self.index]
        self.progress.configure(text=f'新手引导   {self.index+1} / {len(STEPS)}')
        self.heading.configure(text=title)
        self.description.configure(text=description)
        self.previous.configure(state='normal' if self.index else 'disabled')
        self.next.configure(text='完成引导' if self.index == len(STEPS)-1 else '下一步')
        self.schedule_outline()

    def move(self, delta):
        if self.index + delta >= len(STEPS):
            self.destroy()
            return
        self.index = max(0, self.index+delta)
        self.render()

    def help(self):
        root, open_help = self.root, self.open_help
        self.destroy()
        open_help(root)

    def schedule_outline(self, _event=None):
        if not self.closed and self.timer is None:
            self.timer = self.after_idle(self.draw_outline)

    def draw_outline(self):
        self.timer = None
        if not self.root.winfo_ismapped():
            self.hide()
            return
        width, height = self.root.winfo_width(), self.root.winfo_height()
        card_width = min(470, max(1, width-24))
        for label in (self.heading, self.description):
            label.configure(wraplength=max(1, card_width-42))
        self.update_idletasks()
        card_height = self.winfo_reqheight()
        holes = []
        for widget in dict.fromkeys(self.targets[key] for key in STEPS[self.index][2] if key in self.targets):
            if widget.winfo_exists() and widget.winfo_ismapped():
                x = widget.winfo_rootx()-self.root.winfo_rootx()
                y = widget.winfo_rooty()-self.root.winfo_rooty()
                box = (max(0, x-5), max(0, y-5), min(width, x+widget.winfo_width()+5),
                       min(height, y+widget.winfo_height()+5))
                if box[2] > box[0] and box[3] > box[1]:
                    holes.append(box)
        signature = (self.index, self.root.winfo_rootx(), self.root.winfo_rooty(),
                     width, height, card_width, card_height, tuple(holes))
        # Windows emits Configure for stacking changes too. Do not lift owned
        # surfaces again unless their actual layout changed.
        if signature == self.layout_signature and self.winfo_ismapped():
            return
        self.layout_signature = signature
        self.spotlight.show(holes)
        x, y = card_position(width, height, card_width, card_height, holes)
        first_show = not self.winfo_ismapped()
        place_surface(self, card_width, card_height, self.root.winfo_rootx()+x, self.root.winfo_rooty()+y)
        self.lift(self.spotlight)
        if first_show:
            self.grab_set()
            self.next.focus_set()

    def cleanup(self, _event=None):
        self.closed = True
        for remove in self._remove_events:
            remove()
        if self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None
        if self.grab_current() is self:
            self.grab_release()
        self.spotlight.destroy()


def show_onboarding(parent, *, before, targets, open_help):
    root = parent.winfo_toplevel()
    previous = getattr(root, '_ccz_onboarding', None)
    if previous is not None and previous.winfo_exists():
        previous.destroy()
    root._ccz_onboarding = Onboarding(parent, before=before, targets=targets, open_help=open_help)
    return root._ccz_onboarding
