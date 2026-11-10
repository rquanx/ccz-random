"""Standalone, fixed-state preview; filename selects the displayed state."""
from pathlib import Path
import sys
import tkinter as tk

from ccz_randomizer.app import application_build_info
from ccz_randomizer.ui.profile_status import ProfileStatus, ProfileStatusBadge, STATES
from ccz_randomizer.ui.theme import setup_theme
from ccz_randomizer.ui.tooltip import HoverTooltip


def main():
    filename = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).stem
    state = next((value for text, value in (
        ("旧版本", "old"), ("更新中", "updating"), ("待生效", "pending"), ("最新", "latest"))
        if text in filename), "updating")
    if len(sys.argv) > 1 and sys.argv[1] in STATES:
        state = sys.argv[1]
    root = tk.Tk()
    setup_theme(root)
    root.title(f"数据包状态 · {STATES[state][0]} · 临时 UI 预览")
    root.geometry("980x240")
    root.minsize(840, 220)
    body = tk.Frame(root, padx=14, pady=12)
    body.pack(fill="both", expand=True)
    header = tk.Frame(body)
    header.pack(fill="x")
    badge = ProfileStatusBadge(header, ProfileStatus(state, 3 if state == "latest" else 2,
        None if state == "latest" else 3))
    badge.pack(side="right", padx=(0, 2))
    version_label = tk.Label(header, text=f"V{application_build_info()['version']}", fg="#666666", font=("Microsoft YaHei UI", 10), cursor="hand2")
    version_label.pack(side="right", padx=(12, 0))
    version_label._tooltip = HoverTooltip(version_label, "双击查看更新日志")
    tk.Label(header, text="请将本工具放置到游戏目录下，双击运行。", fg="#444444").pack(side="left")
    tk.Frame(body, height=1, bg="#dce0e5").pack(fill="x", pady=(20, 22))
    tk.Label(body, text="数据包状态预览", font=("Microsoft YaHei UI", 12, "bold"), anchor="w").pack(fill="x")
    tk.Label(body, text="将鼠标移到右上角圆点或版本号，查看悬浮说明。", fg="#666666", anchor="w").pack(fill="x", pady=(8, 0))
    if "--smoke-test" in sys.argv:
        root.after(350, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
