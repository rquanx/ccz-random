"""Hover-only reminders for features still being tried out."""
from ccz_randomizer.ui.tooltip import HoverTooltip

EXPERIMENTAL_NOTICE = "实验功能：尚未充分测试，使用时可能遇到问题，请自行决定是否使用。"

def experimental_tooltip(widget, description):
    widget._tooltip = HoverTooltip(widget, f"{description}\n\n{EXPERIMENTAL_NOTICE}")
    return widget._tooltip
