"""Log ohne doppelte Zeilen und ohne Zwischenschritte (Regler, Klicks).

Die Szenarien laufen mit echten Widgets gegen einen privaten Broadway-Server
und zählen Zeilen in der Logdatei des jeweiligen Laufs.
"""
import os
# Kein Datei-Log in Tests: nie in die echte Logdatei im Home schreiben.
os.environ["DISC_PRINTER_LOG_FILE"] = ""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gui import BroadwayCase  # noqa: E402


class LogCleanupGuiTests(BroadwayCase):
    def test_printer_selected_once(self):
        self.run_scenario("printer_once")

    def test_design_saved_logged_once(self):
        self.run_scenario("save_logged_once")

    def test_sliders_log_final_value_only(self):
        self.run_scenario("slider_final_value")

    def test_drag_logged_only_when_moved(self):
        self.run_scenario("drag_only_when_moved")


if __name__ == "__main__":
    unittest.main()
