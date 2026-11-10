"""Encode CLI actions into the fixed native ControlRequest wire layout.

The CLI argument order is action-specific; the server always reads
(action, window, x, y, count, right, item_index).
"""
from __future__ import annotations

PERSISTENT_NATIVE_ACTION_CODES = {
    "list": 1,
    "click": 2,
    "guard": 3,
    "wake": 4,
    "load": 5,
    "save": 6,
    "loadui": 7,
    "closedialog": 8,
    "status": 9,
    "wndproc": 10,
    "trace-random": 11,
    "notifylist": 12,
    "reallist": 13,
    "trace-dialog": 14,
    "openload": 15,
    "trace-load": 16,
    "trace-address": 17,
    "event": 18,
    "confirm-choice": 19,
    "mouse": 20,
    "frame-click": 21,
    "silent-click": 22,
    "dump-list": 23,
    "dialog-dblclick": 24,
    "real-load": 25,
    "dialog-enter": 26,
    "dialog-notify": 27,
    "dialog-window": 28,
    "dialog-accessible": 29,
    "tick": 30,
    "process-state": 31,
    "dispatch-state": 32,
    "mark-ready": 33,
    "dump-contexts": 34,
    "loop-load": 35,
    "start-loop": 36,
    "title-load": 37,
    "pulse-click": 38,
    "arm-first-choice": 39,
    "pulse-burst": 40,
    "silent-burst": 41,
    "list-window": 42,
    "end-dialog": 43,
    "mute-audio": 44,
    "silent-click-timed": 45,
    "silent-burst-timed": 46,
    "enable-acceleration": 47,
    "async-sound": 48,
}

# Each index names a field in the server payload after the action code.
_WINDOW, _X, _Y, _COUNT, _RIGHT, _ITEM = range(6)
_ARGUMENT_FIELDS = {name: () for name in PERSISTENT_NATIVE_ACTION_CODES}
for _name in (
    'list', 'load', 'save', 'closedialog', 'notifylist', 'reallist',
    'dialog-dblclick', 'real-load', 'dialog-enter', 'dialog-notify',
    'dialog-window', 'dialog-accessible', 'mark-ready', 'loop-load', 'title-load',
):
    _ARGUMENT_FIELDS[_name] = (_ITEM,)
for _name in ('event', 'confirm-choice', 'frame-click', 'pulse-click'):
    _ARGUMENT_FIELDS[_name] = (_X, _Y)
for _name in ('silent-click',):
    _ARGUMENT_FIELDS[_name] = (_WINDOW, _X, _Y)
_ARGUMENT_FIELDS.update({
    'click': (_WINDOW, _X, _Y, _COUNT, _RIGHT),
    'wake': (_WINDOW, _COUNT),
    'loadui': (_ITEM, _WINDOW),
    'trace-address': (_WINDOW, _ITEM),
    'mouse': (_COUNT, _X, _Y),
    'pulse-burst': (_X, _Y, _COUNT),
    'silent-burst': (_WINDOW, _X, _Y, _COUNT),
    'list-window': (_WINDOW, _ITEM),
    'end-dialog': (_WINDOW, _ITEM),
    'silent-click-timed': (_WINDOW, _X, _Y, _ITEM),
    'silent-burst-timed': (_WINDOW, _X, _Y, _COUNT, _RIGHT, _ITEM),
})


def encode_native_request(arguments: list[str]) -> str:
    if not arguments or arguments[0] not in PERSISTENT_NATIVE_ACTION_CODES:
        raise ValueError(f'持久化控件不支持操作：{arguments!r}')
    action, *parameters = arguments
    fields = _ARGUMENT_FIELDS[action]
    if len(parameters) != len(fields):
        raise ValueError(f'控件参数数量不正确：{arguments!r}')
    payload = [0] * 6
    for field, value in zip(fields, parameters):
        payload[field] = int(value, 0)
    values = [PERSISTENT_NATIVE_ACTION_CODES[action], *payload]
    return ' '.join(str(value) for value in values) + '\n'
