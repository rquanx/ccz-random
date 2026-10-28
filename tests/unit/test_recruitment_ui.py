import json
from pathlib import Path
import tempfile
import unittest

from ccz_randomizer.history import HistoryRepository
from ccz_randomizer.ui.recruitment import show_recruit_window

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/personnel_22"


def saved_snapshot():
    return {"schemaVersion": 1, "gameVersion": "2.2", "phase": "randomized",
        "slot": 1, "acceptedAttempt": 1, "mode": "three",
        "personnel": json.loads((FIXTURES / "randomized-personnel.json").read_text(encoding="utf-8"))}


class RecruitmentHistoryTests(unittest.TestCase):
    def test_reopen_preserves_result_bound_candidates_and_talents(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory))
            repository.start_run("recruit-test", mode="three", loop_random=False,
                rule_name="test", rule={}, build={})
            round_id = repository.start_round("recruit-test", 1)
            snapshot = saved_snapshot()
            repository.save_result(round_id, snapshot)
            reopened = HistoryRepository(Path(directory))
            self.assertEqual([snapshot], reopened.get_round_results(round_id))


class RecruitmentWindowTests(unittest.TestCase):
    def test_all_people_multiselect_search_and_stage_filter(self):
        import tkinter as tk
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        self.addCleanup(root.destroy)
        show_recruit_window(root, snapshot=saved_snapshot())
        root.update()

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        widgets = list(descendants(root))
        tree = next(w for w in widgets if isinstance(w, ttk.Treeview))
        self.assertEqual(116, len(tree.get_children()))
        tree.selection_set("146", "147")
        next(w for w in widgets if isinstance(w, ttk.Button)).invoke()
        watched = next(w for w in widgets if isinstance(w, ttk.Checkbutton))
        watched.invoke()
        self.assertEqual({"146", "147"}, set(tree.get_children()))
        watched.invoke()
        search = next(w for w in widgets if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox))
        search.insert(0, "曹仁")
        self.assertEqual(("5",), tree.get_children())
        search.delete(0, "end")
        stage = next(w for w in widgets if isinstance(w, ttk.Combobox))
        stage.set("共通 · 颍川之战")
        self.assertEqual({"146", "147", "5"}, set(tree.get_children()))
