"""Neues Design: Zurücksetzen, Erkennung ungespeicherter Änderungen, Rückfrage."""
import os
# Kein Datei-Log in Tests: nie in die echte Logdatei im Home schreiben.
os.environ["DISC_PRINTER_LOG_FILE"] = ""

import sys
import unittest
from pathlib import Path

import cairo

from disc_printer.model import DesignState, ImageElement, TextElement, design_fingerprint

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gui import BroadwayCase  # noqa: E402


def _surf(v=0):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
    s.get_data()[:] = bytes([v]) * len(s.get_data())
    s.mark_dirty()
    return s


class FingerprintTests(unittest.TestCase):
    def fp(self, s, hub=50.0):
        return design_fingerprint(s, hub)

    def test_fresh_states_equal(self):
        self.assertEqual(self.fp(DesignState()), self.fp(DesignState()))

    def test_hub_counts(self):
        self.assertNotEqual(self.fp(DesignState(), 50.0), self.fp(DesignState(), 33.0))

    def test_each_kind_of_change_detected(self):
        base = self.fp(DesignState())
        changes = {
            "bg_color": lambda s: s.set_bg_color(1, 0, 0),
            "bg_image": lambda s: s.set_bg_image(_surf(), "x.png"),
            "bg_move": lambda s: setattr(s, "bg_img_x_mm", 1.5),
            "bg_zoom": lambda s: setattr(s, "bg_img_scale", 1.2),
            "image": lambda s: s.images.append(ImageElement(_surf(), "a.png")),
            "text": lambda s: s.elements.append(
                TextElement("x", "Sans", 12, False, False, (0, 0, 0, 1))),
        }
        for name, change in changes.items():
            with self.subTest(change=name):
                s = DesignState()
                change(s)
                self.assertNotEqual(self.fp(s), base)

    def test_element_attribute_and_pixels(self):
        s = DesignState()
        img = ImageElement(_surf(1), "a.png")
        s.images.append(img)
        before = self.fp(s)
        img.brightness = 1.2
        self.assertNotEqual(self.fp(s), before)
        img.brightness = 1.0
        self.assertEqual(self.fp(s), before, "zurückgesetzter Wert gilt als unverändert")
        img.surface.get_data()[0] = 99
        img.surface.mark_dirty()
        self.assertNotEqual(self.fp(s), before, "Pixeländerung nicht erkannt")

    def test_selection_and_ids_ignored(self):
        s = DesignState()
        t = TextElement("x", "Sans", 12, False, False, (0, 0, 0, 1))
        s.elements.append(t)
        before = self.fp(s)
        t.selected = True
        s.selected_element = t
        t._bbox = (1, 2, 3, 4)
        self.assertEqual(self.fp(s), before)


class NewDesignGuiTests(BroadwayCase):
    def test_new_button_in_header_before_open(self):
        self.run_scenario("new_button")

    def test_reset_to_fresh_state(self):
        self.run_scenario("reset")

    def test_unsaved_change_detection(self):
        self.run_scenario("dirty_detection")

    def test_prompt_cancel_save_discard(self):
        self.run_scenario("new_prompt")


class OpenClosePromptGuiTests(BroadwayCase):
    def test_open_asks_first(self):
        self.run_scenario("open_prompt")

    def test_close_asks_and_cancel_keeps_window(self):
        self.run_scenario("close_prompt")



class LanguageSelectorGuiTests(BroadwayCase):
    def test_selector_matches_actual_language(self):
        # Sprachwechsel (auch zurück auf Deutsch), Neues Design, Öffnen
        self.run_scenario("lang_selector")


if __name__ == "__main__":
    unittest.main()
