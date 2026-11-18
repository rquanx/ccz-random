"""Keep process enumeration and Windows audio calls outside the UI thread."""
from ccz_randomizer.runtime.manual_repair import ManualRepairResult
from ccz_randomizer.ui import messages
from ccz_randomizer.ui.tasks import WindowTasks


def create_sound_repair(root, api):
    busy = False

    def repair(parent=root):
        nonlocal busy
        if busy:
            return
        if not messages.askyesno('游戏声音修复',
            '用于修复旧版本通过 Windows 音量合成器静音了正常 Ekd5.exe，导致之后手动启动游戏也没有声音的问题。\n\n'
            '请先启动正常游戏并进入能播放声音的界面。本操作只恢复正常 Ekd5.exe 的静音状态。是否继续？', parent=parent):
            return
        busy = True
        tasks = WindowTasks(root, serial=False)
        api.show_toast(root, '正在检查游戏声音…')

        def work():
            try:
                executable = api.locate_game_executable()
            except Exception as exc:
                return ManualRepairResult('unable', f'无法定位游戏目录：{exc}')
            return api.repair_normal_game_audio(executable, find_process_ids=api.find_process_ids,
                process_executable=api.process_executable, restore_sessions=api.restore_process_audio_sessions)

        def completed(result):
            nonlocal busy
            tasks.close()
            busy = False
            api.show_toast(root, result.message, 4800 if result.status == 'unable' else 3200)

        tasks.request('audio', work, completed,
                      lambda error: completed(ManualRepairResult('unable', f'游戏声音修复失败：{error}')), durable=True)

    return repair
