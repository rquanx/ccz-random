"""Exercise maintenance child windows with offline service substitutes."""
from types import SimpleNamespace
from unittest.mock import patch
import threading


def exercise_support(run, base, results):
    from ccz_randomizer import app
    from ccz_randomizer.ui import support_controller, messages
    from ccz_randomizer.ui.support_controller import create_support_actions
    from ccz_randomizer.diagnostics.ui_benchmark import descendants
    import tkinter as tk
    from tkinter import ttk

    keys = ('UploadCancelled', 'app_dir', 'application_build_info', 'build_version_text',
            'centered_toplevel', 'create_log_archive', 'show_centered', 'show_toast',
            'upload_log_archive', 'bundle_root', 'current_game_version', 'inspect_environment',
            'locate_game_executable', 'native_dir', 'source_entry_path')
    api = SimpleNamespace(**{key: getattr(app, key) for key in keys})
    api.app_dir = lambda: base
    archive = base/'offline-test.zip'
    archive.write_bytes(b'isolated UI test; no user logs')
    api.create_log_archive = lambda *_args, **_kwargs: archive
    api.locate_game_executable = lambda: (_ for _ in ()).throw(FileNotFoundError('offline UI test'))

    def has_window(title):
        return any(isinstance(w, tk.Toplevel) and w.title() == title for w in descendants(run.root))

    with patch.object(support_controller, 'inspect_runtime_dependencies', return_value=[]), \
            patch.object(messages, 'askyesno', return_value=True):
        upload, _, diagnose = create_support_actions(run.root, api)
        run.measure('child.diagnostics.open', diagnose,
                    lambda: has_window('随机无法使用诊断'))
        dialog = run.window('随机无法使用诊断')
        text = next(w for w in descendants(dialog) if isinstance(w, tk.Text))
        run.measure('child.diagnostics.result', lambda: None,
                    lambda: '游戏定位失败' in text.get('1.0', 'end'))
        run.measure('child.diagnostics.retry', run.button(dialog, '再次测试').invoke,
                    lambda: '游戏定位失败' in text.get('1.0', 'end'))
        run.measure('child.diagnostics.close', dialog.destroy)

        def failed(*_args, **_kwargs):
            raise OSError('offline upload failure')
        api.upload_log_archive = failed
        upload, _, _ = create_support_actions(run.root, api)
        run.measure('child.logs.failure', upload, lambda: has_window('日志上传失败'))
        failure = run.window('日志上传失败')
        # Retry is exercised against a local stub, never a real upload endpoint.
        api.upload_log_archive = lambda *_a, **_kw: 'https://example.invalid/offline-test.zip'
        success_upload, _, _ = create_support_actions(run.root, api)
        run.measure('child.logs.failure.close', failure.destroy)
        run.measure('child.logs.success', success_upload, lambda: has_window('日志上传成功'))
        run.measure('child.logs.success.close', run.window('日志上传成功').destroy)

        started = threading.Event()
        def cancellable(_archive, *, cancel_event, **_kwargs):
            started.set()
            if not cancel_event.wait(10):
                raise TimeoutError('test did not cancel')
            raise app.UploadCancelled()
        api.upload_log_archive = cancellable
        cancel_upload, _, _ = create_support_actions(run.root, api)
        run.measure('child.logs.progress', cancel_upload, started.is_set)
        run.measure('child.logs.cancel', run.button(run.window('上传日志'), '取消').invoke,
                    lambda: not has_window('上传日志'))
    results['support_services'] = 'offline substitutes; no game, upload, browser, clipboard or shell actions'
