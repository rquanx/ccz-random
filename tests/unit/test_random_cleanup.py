"""Dialog cleanup must accept the game's cached, hidden member windows."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from ccz_randomizer import app


class RandomCleanupTests(unittest.TestCase):
    def cleanup(self, visible, sleep_effect=None):
        with ExitStack() as stack:
            for name, value in (
                ('process_windows', [456]), ('window_class', '#32770'),
                ('window_text', '武将情报'), ('diagnostic_log', None),
                ('check_stop_requested', None),
            ):
                stack.enter_context(patch.object(app, name, return_value=value))
            stack.enter_context(patch.object(app.user32, 'IsWindow', return_value=True))
            stack.enter_context(patch.object(app.user32, 'IsWindowVisible', side_effect=visible))
            post = stack.enter_context(patch.object(app.user32, 'PostMessageW', return_value=True))
            enable = stack.enter_context(patch.object(app.user32, 'EnableWindow'))
            stack.enter_context(patch('builtins.print'))
            sleep = stack.enter_context(patch.object(app, 'interruptible_sleep', side_effect=sleep_effect))
            count = app.recover_stale_windows(123, 789)
        self.assertEqual(count, 1)
        post.assert_called_once_with(456, 0x0010, 0, 0)
        enable.assert_called_once_with(789, True)
        return sleep

    def test_hidden_cached_member_window_does_not_delay_next_roll(self):
        self.cleanup([False]).assert_not_called()

    def test_visible_dialog_waits_until_hidden_without_requiring_destruction(self):
        self.cleanup([True, False]).assert_called_once_with(0.05)

    def test_visible_dialog_cleanup_still_honors_stop(self):
        with self.assertRaisesRegex(RuntimeError, 'stopped'):
            self.cleanup([True], sleep_effect=RuntimeError('stopped'))


if __name__ == '__main__':
    unittest.main()
