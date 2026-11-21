"""Einstellbarer Druckbereich: Datei, Widgets, Einheit, Undo, Druckmaske."""
import os
# Kein Datei-Log in Tests: nie in die echte Logdatei im Home schreiben.
os.environ["DISC_PRINTER_LOG_FILE"] = ""

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from disc_printer import file_format as fmt
from disc_printer.model import DesignState

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gui import BroadwayCase  # noqa: E402


class FileFormatTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _old(self, design: dict) -> Path:
        p = self.dir / "old.discprint"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("design.json", json.dumps(design))
        return p

    def test_round_trip(self):
        s = DesignState()
        s.inner_mm, s.outer_mm = 41.5, 79.5
        p = self.dir / "n.discprint"
        fmt.save(p, s)
        d = json.loads(zipfile.ZipFile(p).read("design.json"))
        self.assertEqual((d["version"], d["hub_size"], d["outer_diameter"]), (2, 41.5, 79.5))
        loaded = fmt.load(p)
        self.assertEqual((loaded.inner_mm, loaded.outer_mm), (41.5, 79.5))

    def test_old_files_load_with_118(self):
        for hub in (50, 33):
            with self.subTest(hub=hub):
                st = fmt.load(self._old({"version": 2, "hub_size": hub}))
                self.assertEqual((st.inner_mm, st.outer_mm), (float(hub), 118.0))
        st = fmt.load(self._old({"version": 1}))
        self.assertEqual((st.inner_mm, st.outer_mm), (50.0, 118.0))

    def test_out_of_range_and_garbage_limited(self):
        for design, want in (({"hub_size": 5, "outer_diameter": 300}, (18.0, 120.0)),
                             ({"hub_size": 99, "outer_diameter": 10}, (50.0, 70.0)),
                             ({"hub_size": "x", "outer_diameter": None}, (50.0, 118.0)),
                             ({"hub_size": "nan"}, (50.0, 118.0))):
            with self.subTest(design=design):
                with self.assertLogs("disc_printer", "WARNING"):
                    st = fmt.load(self._old(dict(design, version=2)))
                self.assertEqual((st.inner_mm, st.outer_mm), want)


class PrintAreaGuiTests(BroadwayCase):
    def test_presets_sliders_fields_units_undo_files_print_mask(self):
        self.run_scenario("print_area")

    def test_decimal_separator_units_and_language_switch(self):
        self.run_scenario("area_lang")


if __name__ == "__main__":
    unittest.main()
