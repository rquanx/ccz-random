"""Compare real control layouts with a Git baseline on a private Windows desktop.

Run with the project Python: python -m tools.diagnostics.benchmark_themed_controls
Uses temporary settings and fixed personnel names; does not start the game.
"""
import argparse, gc, importlib.abc, importlib.util, json, os, statistics, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
p = argparse.ArgumentParser()
p.add_argument('--variant', choices=['before', 'after'], help=argparse.SUPPRESS)
p.add_argument('--baseline-ref', default='HEAD')
p.add_argument('--output', type=Path, default=ROOT / 'artifacts/ui-performance/themed-controls-optimized')
a = p.parse_args()
if not a.variant:
    from tests.helpers.desktop import background_desktop
    output = a.output
    output.mkdir(parents=True, exist_ok=True)
    with background_desktop() as startup:
        for run, variant in enumerate(['before', 'after', 'after', 'before', 'before', 'after']):
            subprocess.run([sys.executable, __file__, '--variant', variant, '--output', str(output / f'{run}-{variant}.json'), '--baseline-ref', a.baseline_ref], cwd=ROOT, startupinfo=startup, check=True)
    combined = {}
    for variant in ['before', 'after']:
        rows = [json.loads(file.read_text()) for file in output.glob(f'*-{variant}.json')]
        samples = {}
        for row in rows:
            for metric, values in row['samples'].items():
                samples.setdefault(metric, []).extend(values)
        combined[variant] = dict(summary={metric: dict(median=round(statistics.median(values), 3), p95=round(sorted(values)[int((len(values)-1)*.95)], 3), n=len(values)) for metric, values in samples.items()}, runs=rows)
    (output / 'comparison.json').write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Control benchmark saved: {output}')
    raise SystemExit()
if a.variant == 'before':
    files = ['ccz_randomizer/app.py', 'ccz_randomizer/rules/editor.py', 'ccz_randomizer/rules/result_image_editor.py', 'ccz_randomizer/ui/theme.py', 'ccz_randomizer/ui/searchable_combo.py', 'ccz_randomizer/ui/member_pages.py']
    sources = {path[:-3].replace('/', '.'): subprocess.check_output(['git', 'show', a.baseline_ref + ':' + path], cwd=ROOT).decode('utf-8') for path in files}
    class Baseline(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in sources:
                return importlib.util.spec_from_loader(fullname, self, origin=str(ROOT / (fullname.replace('.', '/') + '.py')))
        def create_module(self, spec):
            return None
        def exec_module(self, module):
            module.__file__ = module.__spec__.origin
            exec(compile(sources[module.__name__], module.__file__, 'exec'), module.__dict__)
    sys.meta_path.insert(0, Baseline())
import faulthandler
faulthandler.dump_traceback_later(120, repeat=True)
os.environ['CCZ_GAME_VERSION'] = '2.2'
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
from ccz_randomizer import app
from ccz_randomizer.ui.theme import setup_theme
from ccz_randomizer.ui.member_pages import MemberPages
from ccz_randomizer.rules.editor import show_rule_editor
from ccz_randomizer.rules.result_image_editor import show_result_image_members
from ccz_randomizer.rules.config import default_rule_config, active_profile
from ccz_randomizer.rule_members import RULE_MEMBER_NAMES
from ccz_randomizer.rules.skill_defaults import SKILL_DEFAULTS
samples = {}
def measure(key, fn, root=None):
    start = time.perf_counter()
    value = fn()
    if root is not None:
        root.update_idletasks()
    samples.setdefault(key, []).append((time.perf_counter() - start)*1000)
    return value
def descendants(w):
    for child in w.winfo_children():
        yield child
        yield from descendants(child)
def close(root):
    for child in list(root.winfo_children()):
        child.destroy()
    for timer in root.tk.call('after', 'info'):
        root.after_cancel(timer)
    root.destroy()
    gc.collect()
errors = []
resources = []
for repetition in range(6):
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        def mainloop(root):
            root.update()
            errors.extend(getattr(root, '_errors', []))
            close(root)
        with patch.object(tk.Tk, 'mainloop', mainloop), patch.object(app, 'app_dir', return_value=base), patch('ccz_randomizer.profile_session.startup_profile_check'), patch.object(app.threading.Thread, 'start'), patch.object(app, 'locate_game_executable', side_effect=OSError):
            measure('main_build_layout_close_ms', app.gui_main)
        root = tk.Tk()
        root.report_callback_exception = lambda *args: errors.append(str(args))
        root.geometry('980x680')
        measure('theme_first_ms', lambda: setup_theme(root))
        root.update()
        start = time.perf_counter()
        for i in range(10000):
            setup_theme(root)
        samples.setdefault('theme_cached_us', []).append((time.perf_counter()-start)*1000000/10000)
        config = default_rule_config()
        import copy
        config['profiles']['性能测量'] = copy.deepcopy(active_profile(config))
        config['activeProfile'] = '性能测量'
        active_profile(config).update(builtin=False, editorMode='advanced')
        active_profile(config)['dataCollection']['allRandomPersonnel'] = True
        measure('rule_open_ms', lambda: show_rule_editor(root, base, config, app.JOB_MAP, app.TEAM_MEMBERS, SKILL_DEFAULTS, lambda value: None), root)
        editor = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        button = next(w for w in descendants(editor) if isinstance(w, ttk.Button) and str(w.cget('text')).startswith('选择人物（'))
        measure('members_open_ms', button.invoke, root)
        chooser = next(w for w in descendants(editor) if isinstance(w, tk.Toplevel) and w.title() == '选择人物')
        pages = next(w for w in descendants(chooser) if isinstance(w, MemberPages))
        initial_widgets = len(list(descendants(chooser)))
        for i in range(30):
            measure('members_page_ms', lambda i=i: pages.move(1 if i % 2 == 0 else -1), root)
        resources.append(dict(case='members', first_widgets=initial_widgets, last_widgets=len(list(descendants(chooser)))))
        chooser.destroy()
        editor.destroy()
        measure('image_open_ms', lambda: show_result_image_members(root, dict(mode='custom', members=['曹操']), RULE_MEMBER_NAMES, lambda value: None), root)
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        pages = next(w for w in descendants(dialog) if isinstance(w, MemberPages))
        initial_widgets = len(list(descendants(dialog)))
        radios = [w for w in descendants(dialog) if isinstance(w, (tk.Radiobutton, ttk.Radiobutton))]
        for i in range(30):
            measure('image_page_ms', lambda i=i: pages.move(1 if i % 2 == 0 else -1), root)
            measure('image_mode_ms', radios[i % 2].invoke, root)
        for query in ['曹', '', '无此人', '', RULE_MEMBER_NAMES[-1], '']:
            measure('image_search_ms', lambda query=query: pages.query.set(query), root)
        resources.append(dict(case='image', first_widgets=initial_widgets, last_widgets=len(list(descendants(dialog)))))
        close(root)
# Discard each process's first full cycle to avoid warm-up bias.
counts = dict(main_build_layout_close_ms=1, theme_first_ms=1, theme_cached_us=1, rule_open_ms=1, members_open_ms=1, members_page_ms=30, image_open_ms=1, image_page_ms=30, image_mode_ms=30, image_search_ms=6)
for metric, count in counts.items():
    samples[metric] = samples[metric][count:]
a.output.write_text(json.dumps(dict(variant=a.variant, baseline=subprocess.check_output(['git', 'rev-parse', a.baseline_ref], cwd=ROOT).decode().strip(), samples=samples, resources=resources, errors=errors), indent=2), encoding='utf-8')
if errors:
    raise RuntimeError(errors)
