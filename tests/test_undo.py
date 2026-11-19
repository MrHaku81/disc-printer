"""Undo vollständig: Hintergrund-Gesten und Audit aller Designaktionen."""
import os
# Kein Datei-Log in Tests: nie in die echte Logdatei im Home schreiben.
os.environ["DISC_PRINTER_LOG_FILE"] = ""

import sys
import unittest
from pathlib import Path

from disc_printer.history import Command, History

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gui import BroadwayCase  # noqa: E402


class BeforeChangeHookTests(unittest.TestCase):
    def test_hook_runs_before_push_undo_redo_and_may_push(self):
        h = History()
        order = []
        pending = ["gesture"]

        def flush():
            order.append("hook")
            if pending:
                pending.pop()
                h.push(Command("gesture", lambda: None, lambda: None))

        h.before_change = flush
        h.push(Command("next", lambda: None, lambda: None))
        self.assertEqual([c.description for c in h._undo], ["gesture", "next"])
        h.undo()
        h.redo()
        self.assertEqual(order, ["hook", "hook", "hook"])  # nicht rekursiv


class UndoGuiTests(BroadwayCase):
    def test_background_gestures(self):
        self.run_scenario("bg_undo")

    def test_every_design_action_is_undoable(self):
        self.run_scenario("undo_audit")

    def test_image_slider_gestures_close_before_undo_and_other_entries(self):
        self.run_scenario("img_slider_undo")


if __name__ == "__main__":
    unittest.main()
