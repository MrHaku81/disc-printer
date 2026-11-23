"""Menüeintrag, Metainfo, Symbol und App-ID müssen zusammenpassen.

Das AUR-Paket installiert Menüeintrag, Symbol und Metainfo aus flatpak/;
das Flatpak-Manifest ebenso. Stimmen die Namen nicht überein, zeigen
Startmenü, Taskleiste und Titelleiste verschiedene oder gar keine Symbole.
"""
import configparser
import os
import re
import unittest
import xml.etree.ElementTree as ET

os.environ["DISC_PRINTER_LOG_FILE"] = ""

from disc_printer.constants import APP_ID

ROOT = os.path.join(os.path.dirname(__file__), os.pardir)
FLATPAK = os.path.join(ROOT, "flatpak")
WINDOW = os.path.join(ROOT, "src", "disc_printer", "gui", "window.py")


class DesktopIntegrationTest(unittest.TestCase):
    def test_files_named_after_app_id(self):
        for suffix in (".desktop", ".metainfo.xml", ".svg", ".yml"):
            path = os.path.join(FLATPAK, APP_ID + suffix)
            self.assertTrue(os.path.isfile(path), path)

    def test_desktop_entry(self):
        cp = configparser.ConfigParser(interpolation=None)
        cp.optionxform = str
        cp.read(os.path.join(FLATPAK, APP_ID + ".desktop"), encoding="utf-8")
        entry = cp["Desktop Entry"]
        self.assertEqual(entry["Icon"], APP_ID)
        self.assertEqual(entry["Exec"], "disc-printer")
        # X11: GTK bildet WM_CLASS aus dem Programmnamen (Startskript)
        self.assertEqual(entry["StartupWMClass"], "disc-printer")

    def test_metainfo(self):
        root = ET.parse(os.path.join(FLATPAK, APP_ID + ".metainfo.xml")).getroot()
        self.assertEqual(root.findtext("id"), APP_ID)
        self.assertEqual(root.find("launchable").text, APP_ID + ".desktop")

    def test_manifest(self):
        with open(os.path.join(FLATPAK, APP_ID + ".yml"), encoding="utf-8") as f:
            text = f.read()
        self.assertRegex(text, r"(?m)^id: " + re.escape(APP_ID) + r"$")
        self.assertIn(f"hicolor/scalable/apps/{APP_ID}.svg", text)
        # Nur ein Symbol für alle Größen: keine festen Größenordner, keine
        # zweite Fassung
        self.assertNotRegex(text, r"hicolor/[^/\s]*x[^/\s]*/apps/")
        self.assertNotIn("-klein.svg", text)

    def test_single_icon(self):
        svgs = sorted(n for n in os.listdir(FLATPAK) if n.endswith(".svg"))
        self.assertEqual(svgs, [APP_ID + ".svg"])

    def test_window_sets_no_own_icon_name(self):
        # Gtk.Application setzt den Standard-Symbolnamen auf die App-ID;
        # ein eigener Name am Fenster überschreibt ihn.
        with open(WINDOW, encoding="utf-8") as f:
            src = f.read()
        self.assertNotRegex(src, r"\bself\.set_icon_name\(")
        self.assertNotIn("set_default_icon_name", src)


if __name__ == "__main__":
    unittest.main()
