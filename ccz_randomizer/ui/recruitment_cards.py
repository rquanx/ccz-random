"""Measure all recruitment rows once, paint only the rows inside the viewport."""
import tkinter as tk
from ccz_randomizer.ui.text_block import shared_font
from ccz_randomizer.recruitment import display_job_options
from ccz_randomizer.runtime.skill_memory import normalize_skill_name


class RecruitmentCards:
    def __init__(self, canvas, colors):
        self.canvas, self.colors = canvas, colors
        self.font = shared_font(canvas, 'Microsoft YaHei UI', 10)
        self.bold = shared_font(canvas, 'Microsoft YaHei UI', 10, 'bold')
        self.small = shared_font(canvas, 'Microsoft YaHei UI', 9)
        self.heading = shared_font(canvas, 'Microsoft YaHei UI', 11, 'bold')
        self.probe = tk.Canvas(canvas)
        self.probe_item = self.probe.create_text(0, 0, anchor='nw')
        self.heights = {}
        self.widths = {}
        self.rows = []
        self.drawn = set()
        self.timer = None
        self.ready = False
        previous = canvas.cget('yscrollcommand')
        def scrolled(first, last):
            if previous:
                canvas.tk.call(*canvas.tk.splitlist(previous), first, last)
            self.schedule()
        canvas.configure(yscrollcommand=scrolled)
        from ccz_randomizer.ui.window_events import bind_window_event
        bind_window_event(canvas, '<Destroy>', lambda _: self.close())
        from ccz_randomizer.ui.render_state import track_render
        track_render(canvas, lambda: self.ready and self.timer is None)

    def height(self, text, font, width):
        key = (text, str(font), width)
        if key not in self.heights:
            self.probe.itemconfigure(self.probe_item, text=text or ' ', font=font, width=max(1, width))
            box = self.probe.bbox(self.probe_item)
            self.heights[key] = box[3]-box[1]
        return self.heights[key]

    def length(self, text):
        if text not in self.widths:
            self.widths[text] = self.bold.measure(text)
        return self.widths[text]

    def card(self, row, x, y, width, tag=None):
        canvas, colors = self.canvas, self.colors
        cursor = y+12
        def text(value, font, color, indent=0, reserve=0):
            nonlocal cursor
            wrap = max(1, width-24-indent-reserve)
            if tag:
                canvas.create_text(x+12+indent, cursor, anchor='nw', text=value,
                                   width=wrap, font=font, fill=color, tags=tag)
            cursor += self.height(value, font, wrap)+5
        cost = '固定' if row.entry_kind == 'fixed' else f'{row.cost}次'
        reserve = self.length(cost)+12
        if tag:
            canvas.create_text(x+width-12, cursor, anchor='ne', text=cost,
                               font=self.small, fill=colors['muted'], tags=tag)
        options = display_job_options(row).split('/')
        if not set(options) & self.high_names:
            text(row.name+' · '+display_job_options(row), self.bold, colors['ink'], reserve=reserve)
        else:
            segments = [(row.name+' · ', False)]
            for index, job in enumerate(options):
                if index:
                    segments.append(('/', False))
                segments.append((job, job in self.high_names))
            pen, right = x+12, x+width-24-reserve
            for value, high in segments:
                length = self.length(value)
                if pen > x+12 and pen+length > right:
                    pen = x+12
                    cursor += self.height('字', self.bold, width)+2
                    right = x+width-12
                if tag:
                    canvas.create_text(pen, cursor, anchor='nw', text=value, font=self.bold,
                                       fill='#B42318' if high else colors['ink'], tags=tag)
                pen += length
            cursor += self.height('字', self.bold, width)+5
        for title, talents in (('兵种天赋', row.job_talents), ('人物天赋', row.personal_talents)):
            cursor += 5
            text(title, self.bold, colors['ink'])
            for talent in talents or ('无',):
                text(talent, self.font,
                     '#B42318' if normalize_skill_name(talent) in self.special_names else colors['ink'], indent=14)
        return cursor+7

    def set(self, groups, special_names, high_names):
        self.ready = False
        self.special_names, self.high_names = special_names, high_names
        self.canvas.delete('cards')
        self.drawn.clear()
        self.rows = []
        width = max(1, self.canvas.winfo_width())
        columns = max(1, (width-16)//258)
        self.card_width = max(100, (width-28-(columns-1)*12)//columns)
        y = 12
        for stage, kinds in groups:
            self.rows.append((y, y+31, 'heading', stage.removeprefix('共通 · ')))
            y += 31
            for label, people in kinds:
                if not people:
                    continue
                self.rows.append((y, y+26, 'subheading', label))
                y += 26
                for start in range(0, len(people), columns):
                    row = people[start:start+columns]
                    bottom = max(self.card(person, 14+i*(self.card_width+12), y, self.card_width)
                                 for i, person in enumerate(row))
                    self.rows.append((y, bottom, 'cards', row))
                    y = bottom+12
            y += 8
        if not groups:
            self.rows.append((12, 52, 'empty', '没有符合条件的入队人员'))
            y = 60
        self.canvas.configure(scrollregion=(0, 0, width, y))
        self.schedule()

    def schedule(self):
        if self.timer is None:
            self.timer = self.canvas.after_idle(self.draw)

    def draw(self):
        self.timer = None
        top = self.canvas.canvasy(0)
        bottom = top+self.canvas.winfo_height()
        visible = {i for i, (y, end, _, _) in enumerate(self.rows) if end >= top and y <= bottom}
        for index in self.drawn-visible:
            self.canvas.delete(f'row:{index}')
        for index in sorted(visible-self.drawn):
            y, end, kind, data = self.rows[index]
            tag = ('cards', f'row:{index}')
            if kind == 'cards':
                for i, person in enumerate(data):
                    x = 14+i*(self.card_width+12)
                    card_tag = (f'card:{person.record_index}', *tag)
                    self.canvas.create_rectangle(x, y, x+self.card_width, end,
                                                 fill=self.colors['surface'], outline=self.colors['line'], tags=card_tag)
                    self.card(person, x, y, self.card_width, tag=card_tag)
            else:
                self.canvas.create_text(14, y, anchor='nw', text=data, tags=tag,
                                        font=self.heading if kind == 'heading' else self.small,
                                        fill=self.colors['ink'] if kind == 'heading' else self.colors['muted'])
        self.drawn = visible
        self.ready = True

    def close(self):
        if self.timer is not None:
            self.canvas.after_cancel(self.timer)
            self.timer = None
