"""The persistent wire request must match the native CLI's actual parser."""
import subprocess
import unittest
from pathlib import Path

from ccz_randomizer.runtime.native_protocol import (
    PERSISTENT_NATIVE_ACTION_CODES, encode_native_request,
)


class NativeProtocolTests(unittest.TestCase):
    def test_wake_duration_and_save_slot_reach_the_native_fields(self):
        self.assertEqual('4 456 0 0 80 0 0\n', encode_native_request(['wake', '456', '80']))
        self.assertEqual('5 0 0 0 0 0 19\n', encode_native_request(['load', '19']))
        self.assertEqual('6 0 0 0 0 0 14\n', encode_native_request(['save', '14']))
        self.assertEqual('45 456 369 234 0 0 350\n',
                         encode_native_request(['silent-click-timed', '456', '369', '234', '350']))

    def test_invalid_requests_are_rejected_before_they_can_be_sent(self):
        for arguments in ([], ['unknown'], ['wake', '456'], ['status', '1'],
                          ['silent-burst-timed', '456', '369', '234', '1', '100'],
                          ['load', 'bad']):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                encode_native_request(arguments)

    def test_all_persistent_actions_match_the_compiled_native_cli_parser(self):
        injector = Path(__file__).resolve().parents[2] / 'native/ccz_injector.exe'
        if not injector.is_file():
            self.skipTest('需先运行 native/build_native.bat 才能执行 C/Python 协议契约测试')
        # CLI samples are based on native/ccz_injector.c and real game calls.
        # Distinct values expose swapped fields; zero-argument actions are
        # explicitly listed so a new action requires a contract case.
        groups = (
            ('guard status wndproc trace-random trace-dialog openload trace-load dump-list '
             'tick process-state dispatch-state dump-contexts start-loop arm-first-choice '
             'mute-audio enable-acceleration async-sound', []),
            ('list load save closedialog notifylist reallist dialog-dblclick real-load '
             'dialog-enter dialog-notify dialog-window dialog-accessible mark-ready '
             'loop-load title-load', ['19']),
            ('event confirm-choice frame-click pulse-click', ['369', '234']),
            ('silent-click', ['456', '369', '234']),
            ('click', ['456', '369', '234', '2', '1']),
            ('wake', ['456', '80']),
            ('loadui', ['19', '456']),
            ('trace-address', ['0x503f40', '1']),
            ('mouse', ['513', '369', '234']),
            ('pulse-burst', ['369', '234', '2']),
            ('silent-burst', ['456', '369', '234', '2']),
            ('list-window end-dialog', ['456', '19']),
            ('silent-click-timed', ['456', '369', '234', '350']),
            ('silent-burst-timed', ['456', '369', '234', '2', '100', '50']),
        )
        covered = set()
        for names, parameters in groups:
            for action in names.split():
                covered.add(action)
                with self.subTest(action=action):
                    arguments = [action, *parameters]
                    result = subprocess.run(
                        [str(injector), '--encode-request', '-', *arguments],
                        capture_output=True, text=True, timeout=5,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(result.stdout, encode_native_request(arguments))
        self.assertEqual(set(PERSISTENT_NATIVE_ACTION_CODES), covered)
