"""Extended child-dialog scenarios; all data and writes stay in the test copy."""
import json
import copy
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk


def exercise_dialogs(run, base, results, actions=None):
    from ccz_randomizer.diagnostics.ui_benchmark import descendants
    from ccz_randomizer.history import HistoryRepository
    from ccz_randomizer.ui.inputs import SearchEntry, TextEntry
    from ccz_randomizer.ui.member_pages import MemberPages
    from ccz_randomizer.ui.history import _show_detail, _show_round_overview
    from ccz_randomizer.ui.history_actions import edit_history_metadata
    from ccz_randomizer.ui.result_details import show_score_detail
    from ccz_randomizer.ui.equipment import show_equipment_window
    from ccz_randomizer.ui.job_talents import show_job_talents_window
    from ccz_randomizer.ui.recruitment import show_recruit_window
    from ccz_randomizer.rules.editor import show_advanced_help, show_member_affinity_editor
    from ccz_randomizer.rules.result_image_editor import show_result_image_members
    from ccz_randomizer.rule_members import RULE_MEMBER_NAMES
    from ccz_randomizer.profile_updates import show_profile_update_dialog
    from ccz_randomizer.ui.statistics_ranking import show_ranking_window
    from ccz_randomizer.statistics_store import StatisticsRepository
    from ccz_randomizer.ui import messages, rule_change_prompt, text_prompt
    from ccz_randomizer.rules.config import AFFINITY_TYPES

    root = run.root
    repository = HistoryRepository(base)
    row = repository.list_rounds(page_size=1)[0]
    snapshots = repository.get_round_results(int(row['id']))
    snapshot = snapshots[0]
    results['child_snapshot'] = dict(slot=snapshot.get('slot'), members=snapshot.get('memberCount'),
                                     personnel=len(snapshot.get('personnel') or []))

    def opened():
        return {w for w in descendants(root) if isinstance(w, tk.Toplevel)}

    def scenario(name, factory, interact=None, ready=None):
        before = opened()
        holder = []
        def action():
            factory()
            holder.extend(opened()-before)
        run.measure(name+'.open', action,
                    lambda: bool(holder) and content_ready(holder[0]) and (ready(holder[0]) if ready else True))
        window = holder[0]
        if interact:
            interact(window)
        if hasattr(window, '_reload_picker') or hasattr(window, '_reload_affinity'):
            run.measure(name+'.cancel', run.button(window, '取消').invoke,
                        lambda: not window.winfo_ismapped())
            run.measure(name+'.open.cached', factory,
                        lambda: window.winfo_ismapped() and content_ready(window))
        timers = set(getattr(window, '_ccz_owned_timers', ()))
        run.measure(name+'.close', window.destroy)
        if timers.intersection(root.tk.call('after', 'info')):
            raise AssertionError(name+': delayed callback outlived its window')
        if opened()-before:
            raise AssertionError(f'{name}: child dialog leaked')

    def canvas_text(window):
        return [str(w.itemcget(item, 'text')) for w in descendants(window) if isinstance(w, tk.Canvas)
                for item in w.find_all() if w.type(item) == 'text']

    def content_ready(window):
        viewport = getattr(window, '_member_viewport', None)
        cards = getattr(window, '_recruitment_cards', None)
        return (viewport is None or viewport.ready) and (cards is None or cards.ready)

    def search_and_scroll(name, window):
        entry = next(w for w in descendants(window) if isinstance(w, SearchEntry))
        run.measure(name+'.search.empty', lambda: entry.insert(0, '不存在的匹配项'),
                    lambda: any('没有符合' in text for text in [*run.texts(window), *canvas_text(window)]))
        run.measure(name+'.search.reset', lambda: entry.delete(0, 'end'),
                    lambda: not any('没有符合' in text for text in [*run.texts(window), *canvas_text(window)]))
        canvas = next(w for w in descendants(window) if isinstance(w, tk.Canvas))
        run.measure(name+'.scroll.end', lambda: canvas.yview_moveto(1))
        run.measure(name+'.scroll.start', lambda: canvas.yview_moveto(0))

    scenario('child.history.detail', lambda: _show_detail(root, snapshot))
    recorded = json.loads((base/'recorded-ui-result.json').read_text(encoding='utf-8'))
    def detail_scroll(window):
        viewport = window._member_viewport
        run.measure('child.history.all_members.scroll.end', lambda: viewport.canvas.yview_moveto(1),
                    lambda: viewport.timer is None)
        run.measure('child.history.all_members.scroll.start', lambda: viewport.canvas.yview_moveto(0),
                    lambda: viewport.ready)
    scenario('child.history.all_members', lambda: _show_detail(root, recorded), detail_scroll)
    scenario('child.history.overview', lambda: _show_round_overview(root, row, snapshots))
    scenario('child.history.metadata', lambda: edit_history_metadata(root, {}, lambda _: None))
    scenario('child.score', lambda: show_score_detail(root, snapshot.get('detail') or {}))
    scenario('child.equipment', lambda: show_equipment_window(root, snapshot=snapshot,
             history_path=base/'equipment-search.json'), lambda w: search_and_scroll('child.equipment', w))
    def talent_actions(window):
        search_and_scroll('child.talents', window)
        for text in ('只看特殊技能', '只看高阶兵种'):
            check = next(w for w in descendants(window) if isinstance(w, ttk.Checkbutton)
                         and w.cget('text') == text)
            run.measure('child.talents.filter.'+text, check.invoke)
            run.measure('child.talents.reset.'+text, check.invoke)
    scenario('child.talents', lambda: show_job_talents_window(root, snapshot=snapshot),
             talent_actions, lambda w: bool(canvas_text(w)))
    if snapshot.get('personnel') or snapshot.get('fixedPersonnel'):
        scenario('child.recruitment', lambda: show_recruit_window(root, snapshot=snapshot,
                 history_path=base/'personnel-search.json'),
                 lambda w: search_and_scroll('child.recruitment', w), lambda w: bool(canvas_text(w)))

    def members(name, window):
        pages = next(w for w in descendants(window) if isinstance(w, MemberPages))
        if not pages.next.instate(('disabled',)):
            run.measure(name+'.next', pages.next.invoke)
            run.measure(name+'.previous', pages.previous.invoke)
        target = pages.names[-1]
        run.measure(name+'.search', lambda: pages.query.set(target),
                    lambda: any(str(w.cget('text')) == target and w.winfo_manager()
                                for w in descendants(pages.body)))
        run.measure(name+'.reset', lambda: pages.query.set(''))

    values = {name: (AFFINITY_TYPES[0], AFFINITY_TYPES[0]) for name in RULE_MEMBER_NAMES}
    def affinity_actions(window):
        members('child.affinity', window)
        run.measure('child.affinity.hide', lambda: window.tk.call(window.protocol('WM_DELETE_WINDOW')))
        run.measure('child.affinity.reopen', lambda: show_member_affinity_editor(root, RULE_MEMBER_NAMES,
                    values, True, lambda _: None))
    scenario('child.affinity', lambda: show_member_affinity_editor(root, RULE_MEMBER_NAMES,
             values, True, lambda _: None), affinity_actions)
    scenario('child.image_members', lambda: show_result_image_members(root,
             {'mode':'custom', 'members':list(RULE_MEMBER_NAMES)}, RULE_MEMBER_NAMES, lambda _: None),
             lambda w: members('child.image_members', w))
    def help_tabs(window):
        book = next(w for w in descendants(window) if isinstance(w, ttk.Notebook))
        for index in range(len(book.tabs())):
            run.measure(f'child.rules_help.tab.{index}', lambda i=index: book.select(i))
    scenario('child.rules_help', lambda: show_advanced_help(root, 0), help_tabs)
    scenario('child.profile_update', lambda: show_profile_update_dialog(root, base))
    scenario('child.changelog', lambda: app_changelog(root))

    # Real history filter entries open the date/time subwindow via their bindings.
    from ccz_randomizer.ui.history import show_history_window
    show_history_window(root, base)
    history = run.window('历史记录')
    run.wait(lambda: history._result_viewport.ready)
    date_entries = [w for w in descendants(history) if type(w) is TextEntry]
    for index, entry in enumerate(date_entries[:2]):
        scenario(f'child.history.time.{index}', lambda entry=entry: entry.event_generate('<Button-1>'))
    history.destroy()

    from ccz_randomizer.ui.dependency_messages import show_dependency_issues
    scenario('child.dependencies', lambda: show_dependency_issues(root,
             [dict(label='组件', ok=False, message='离线界面验证')], lambda: None))

    from ccz_randomizer.rules.editor import show_rule_editor, ScoreGrid
    from ccz_randomizer.rules.config import default_rule_config
    from ccz_randomizer import app
    config = default_rule_config()
    profile = copy.deepcopy(config['profiles'][config['activeProfile']])
    profile['builtin'] = False
    config['activeProfile'] = '性能验证副本'
    config['profiles'][config['activeProfile']] = profile
    show_rule_editor(root, base, config, app.JOB_MAP, app.TEAM_MEMBERS,
                     app.skill_score_catalog(), lambda _: None)
    editor = run.window('规则设置')
    book = next(w for w in descendants(editor) if isinstance(w, ttk.Notebook))
    book.select(1)
    root.update()
    advanced = [w for w in descendants(editor) if isinstance(w, ttk.Notebook)][1]
    for index in range(len(advanced.tabs())):
        run.measure(f'child.rules.advanced.{index}', lambda i=index: advanced.select(i))
        grids = [w for w in descendants(editor) if isinstance(w, ScoreGrid) and w.winfo_ismapped()]
        for grid_index, grid in enumerate(grids):
            prefix = f'child.rules.grid.{index}.{grid_index}'
            run.measure(prefix+'.search', lambda grid=grid: grid.search_var.set('不存在的匹配项'),
                        lambda grid=grid: not grid.hit_boxes)
            run.measure(prefix+'.reset', lambda grid=grid: grid.search_var.set(''))
            run.measure(prefix+'.scroll.end', lambda grid=grid: grid.canvas.yview_moveto(1))
            run.measure(prefix+'.scroll.start', lambda grid=grid: grid.canvas.yview_moveto(0))
    advanced.select(0)
    root.update()
    chooser = next(w for w in descendants(editor) if isinstance(w, ttk.Button) and
                   str(w.cget('text')).startswith('选择人物'))
    scenario('child.rules.qualification_members', chooser.invoke,
             lambda w: members('child.rules.qualification_members', w))
    # Export scope is a modal step; cancellation never reaches the OS file picker.
    def export_scope():
        root.after(80, lambda: run.button(run.window('导出规则'), '取消').invoke())
        run.button(editor, '导出规则').invoke()
    run.measure('child.rules.export_scope.cancel', export_scope)
    editor.destroy()

    statistics = StatisticsRepository(base)
    for kind in ('jobs', 'skills', 'equipment'):
        def ranking_actions(window, kind=kind):
            following = run.button(window, '下一页')
            if not following.instate(('disabled',)):
                run.measure(f'child.ranking.{kind}.next', following.invoke,
                            lambda: any('2/' in t for t in run.texts(window)))
                run.measure(f'child.ranking.{kind}.previous', run.button(window, '上一页').invoke,
                            lambda: any('1/' in t for t in run.texts(window)))
            entry = next(w for w in descendants(window) if isinstance(w, SearchEntry))
            run.measure(f'child.ranking.{kind}.search', lambda: entry.insert(0, '不存在的匹配项'),
                        lambda: any(t.startswith('0 项') for t in run.texts(window)))
        scenario('child.ranking.'+kind, lambda kind=kind: show_ranking_window(root, statistics, kind, {}),
                 ranking_actions, lambda w: any(' 页' in t for t in run.texts(w)))

    def modal(name, action, button, expected):
        def dismiss():
            window = next(w for w in opened() if w.title() == '交互测试')
            run.button(window, button).invoke()
        def invoke():
            root.after(80, dismiss)
            if action() != expected:
                raise AssertionError(name+' returned incorrect answer')
        run.measure(name, invoke)
    modal('child.message.info', lambda: messages.showinfo('交互测试', '测试提示', parent=root), '关闭', 'ok')
    modal('child.message.long', lambda: messages.showwarning('交互测试', '诊断内容\n'*100, parent=root), '关闭', 'ok')
    modal('child.message.choice', lambda: messages.askyesnocancel('交互测试', '测试选择', parent=root), '取消', None)
    modal('child.text.cancel', lambda: text_prompt.ask_text('交互测试', '规则名称', parent=root), '取消', None)
    # Rule-change prompts have their own title; exercise their real nested loop.
    for closing in (False, True):
        for history in (False, True):
            def invoke(closing=closing, history=history):
                root.after(80, lambda: run.button(run.window('放弃修改' if closing else '保存修改'), '取消').invoke())
                assert rule_change_prompt.ask_rule_change(root, closing=closing, has_statistics=history) == 'cancel'
            run.measure(f'child.rule_change.{closing}.{history}', invoke)
    from ccz_randomizer.diagnostics.support_benchmark import exercise_support
    exercise_support(run, base, results)
    if actions:
        run.measure('child.slot_help.open', actions['show_slot_help'])
        run.measure('child.slot_help.close', actions['hide_slot_help'])
        def cancel_sound():
            root.after(80, lambda: run.button(run.window('游戏声音修复'), '取消').invoke())
            actions['repair_game_sound']()
        run.measure('child.sound.confirm.cancel', cancel_sound)
        with patch.object(app, 'first_use_notice_acknowledged', return_value=False):
            scenario('child.first_use', actions['show_first_use_notice'])
        if 'start_onboarding' in actions:
            from ccz_randomizer.ui.onboarding import STEPS
            run.measure('onboarding.open', actions['start_onboarding'],
                        lambda: root._ccz_onboarding.winfo_ismapped())
            guide = root._ccz_onboarding
            for index in range(len(STEPS)):
                run.measure(f'onboarding.step.{index+1}', lambda: guide.move(1))
            if guide.winfo_exists():
                raise AssertionError('Completed walkthrough must release its controls')
            run.measure('onboarding.replay', actions['start_onboarding'])
            run.measure('onboarding.skip', root._ccz_onboarding.destroy)
        from ccz_randomizer.ui.concurrent_console import ConcurrentConsoleState
        state = ConcurrentConsoleState(1, 1)
        for index in range(1, 101):
            state.consume_result(dict(snapshot.get('detail') or {}, resultSlot=1, attempt=index))
        actions['concurrent_console_rounds'][9001] = state
        scenario('child.concurrent_detail', lambda: actions['show_concurrent_slot_detail'](9001, 1))
        actions['concurrent_console_rounds'].pop(9001)
        scenario('child.toast', lambda: app.show_toast(root, '后台交互验证'))
        from ccz_randomizer.ui.tooltip import HoverTooltip
        label = ttk.Label(root, text='后台提示')
        label.pack()
        tip = HoverTooltip(label, '后台交互验证')
        run.measure('child.tooltip.open', tip._show)
        run.measure('child.tooltip.close', tip.hide)
        label.destroy()


def app_changelog(root):
    from ccz_randomizer.app import show_changelog_window
    show_changelog_window(root)
