import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ccz_randomizer.search_history import SearchHistory, SearchSession


class SearchHistoryTests(unittest.TestCase):
    def test_delete_and_clear_persist_and_do_not_restore_stale_window_items(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "searches.json"
            first, second = SearchHistory(path), SearchHistory(path)
            first.remember("曹操")
            first.remember("夏侯惇")
            second.remove(" 曹操 ")
            self.assertEqual(["夏侯惇"], SearchHistory(path).items)
            first.remember("夏侯渊")
            self.assertEqual(["夏侯渊", "夏侯惇"], SearchHistory(path).items)
            second.clear()
            self.assertEqual([], SearchHistory(path).items)
            first.remember("曹仁")
            self.assertEqual(["曹仁"], SearchHistory(path).items)

    def test_auto_session_merges_new_prefixes_but_preserves_existing_keywords(self):
        with tempfile.TemporaryDirectory() as temp:
            history = SearchHistory(Path(temp)/"searches.json")
            session = SearchSession(history)
            session.remember("曹")
            session.remember("曹仁")
            self.assertEqual(["曹仁"], history.items)
            session.reset()
            history.remember("夏侯")
            session.remember("夏侯")
            session.remember("夏侯惇")
            self.assertEqual(["夏侯惇", "夏侯", "曹仁"], history.items)
            session.remember("荀", finalize=True)
            session.remember("荀彧")
            self.assertEqual(["荀彧", "荀", "夏侯惇", "夏侯", "曹仁"], history.items)

    def test_ten_item_lru_is_deduplicated_and_survives_reopen(self):
        words = ("曹操", "夏侯惇", "夏侯渊", "曹仁", "曹洪", "荀彧", "荀攸", "郭嘉", "程昱", "于禁", "典韦", "许褚")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"searches.json"
            history = SearchHistory(path)
            for word in words:
                history.remember(word)
            self.assertEqual(list(reversed(words[2:])), history.items)
            history.remember("  夏侯渊  ")
            expected = ["夏侯渊", *reversed(words[3:])]
            self.assertEqual(expected, history.items)
            self.assertEqual(expected, SearchHistory(path).items)
            self.assertFalse(history.remember("   "))
            self.assertEqual(expected, history.items)

    def test_normalization_and_two_windows_keep_new_searches(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"searches.json"
            first, second = SearchHistory(path), SearchHistory(path)
            first.remember("  MP   恢复 ")
            second.remember("曹操")
            second.remember("mp 恢复")
            self.assertEqual(["mp 恢复", "曹操"], SearchHistory(path).items)

    def test_bad_file_and_read_only_storage_do_not_break_searches(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"searches.json"
            path.write_text("broken", encoding="utf-8")
            history = SearchHistory(path)
            self.assertEqual([], history.items)
            history.remember("曹操")
            with patch.object(Path, "replace", side_effect=PermissionError("read only")):
                history.remember("曹仁")
            self.assertEqual(["曹仁", "曹操"], history.items)
            self.assertEqual(["曹操"], SearchHistory(path).items)
            self.assertEqual([path], list(Path(temp).iterdir()))
