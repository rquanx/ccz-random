"""Aligned daily trends with explicit independent scales for different magnitudes."""
import math

from ccz_randomizer.ui.statistics_graphics import HitRegion


def draw_trend(chart, width, height, rows):
    from ccz_randomizer.ui.statistics_charts import PALETTE

    # Both panels share dates, while each count retains a readable linear scale.
    left = max(40, chart._label_font.measure(f"{max(max(row[1:]) for row in rows):,}") + 18)
    right = max(left + 1, width-20)
    top, bottom, gap = 66, max(112, height-30), 28
    panel_height = max(12, (bottom-top-gap)/2)
    step = (right-left)/len(rows)
    tick_every = max(1, math.ceil(len(rows)/max(1, int((right-left)/95))))

    for series, (title, color) in enumerate((("执行次数", PALETTE[0]), ("保存成功", PALETTE[2]))):
        panel_top = top + series*(panel_height+gap)
        plot_top, plot_bottom = panel_top+16, panel_top+panel_height
        maximum = max(row[series+1] for row in rows)
        total = sum(row[series+1] for row in rows)
        chart.create_text(left, panel_top, text=title, anchor="w", fill=color,
                          font=chart._label_font, tags="trend-heading")
        chart.text(right, panel_top, f"合计 {total:,} 次", anchor="e", tags="trend-total")
        # An integer upper bound keeps zero, one and other small counts unambiguous.
        ceiling = max(1, maximum)
        for value in (0, ceiling):
            y = plot_bottom-(plot_bottom-plot_top)*value/ceiling
            chart.graphics.line(left, y, right, y, fill="#EAF0F6", dash=(3, 4))
            chart.create_text(left-8, y, text=f"{value:,}", anchor="e", fill=color,
                              font=chart._label_font, tags="trend-tick")

        points = []
        for index, row in enumerate(rows):
            x = left+step*(index+.5)
            y = plot_bottom-(plot_bottom-plot_top)*row[series+1]/ceiling
            points.extend((x, y))
            chart.graphics.oval(x-3, y-3, x+3, y+3, fill=color, outline="white")
            # Full columns make tiny, zero and isolated daily values easy to inspect.
            chart.tip(HitRegion((left+step*index, plot_top-5, left+step*(index+1), plot_bottom+5)),
                      f"{row[0]}：执行 {row[1]:,} / 保存 {row[2]:,}")
            if series == 1 and index % tick_every == 0:
                chart.text(x, bottom+16, str(row[0])[-5:])
        if len(points) >= 4:
            chart.graphics.line(*points, fill=color, width=2, layer=1)
        if maximum == 0:
            chart.text((left+right)/2, (plot_top+plot_bottom)/2, "该时段为 0 次", tags="trend-zero")
