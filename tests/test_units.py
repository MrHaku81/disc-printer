import os
# Kein Datei-Log in Tests: nie in die echte Logdatei im Home schreiben.
os.environ["DISC_PRINTER_LOG_FILE"] = ""

import gettext
import glob
import shutil
import subprocess
import tempfile
import unittest

from disc_printer.units import (
    MM_PER_INCH, clamp, decimal_sep, format_number, mm_to_inch, parse_number, snap,
)

LOCALE_DIR = os.path.join(os.path.dirname(__file__), os.pardir,
                          "src", "disc_printer", "locale")


class ConversionTests(unittest.TestCase):
    def test_mm_per_inch(self):
        self.assertEqual(MM_PER_INCH, 25.4)
        self.assertAlmostEqual(mm_to_inch(25.4), 1.0)

    def test_snap_and_clamp(self):
        self.assertEqual(snap(41.3, 0.5), 41.5)
        self.assertEqual(snap(41.2, 0.5), 41.0)
        self.assertEqual(snap(117.75, 0.5), 118.0)
        self.assertEqual(clamp(130, 70, 120), 120)
        self.assertEqual(clamp(10, 18, 50), 18)


class FormatTests(unittest.TestCase):
    def test_decimal_separator_follows_language_not_unit(self):
        self.assertEqual(decimal_sep("de"), ",")
        self.assertEqual(decimal_sep("en"), ".")
        for unit, de, en in (("mm", "118,0", "118.0"), ("in", "4,65", "4.65")):
            with self.subTest(unit=unit):
                self.assertEqual(format_number(118.0, unit, "de"), de)
                self.assertEqual(format_number(118.0, unit, "en"), en)

    def test_precision(self):
        self.assertEqual(format_number(41.25, "mm", "en"), "41.2")   # 0,1 mm
        self.assertEqual(format_number(33.0, "in", "en"), "1.30")    # 0,01 in
        self.assertEqual(format_number(120.0, "in", "de"), "4,72")

    def test_trim_only_for_whole_millimetres(self):
        self.assertEqual(format_number(5.0, "mm", "de", trim=True), "5")
        self.assertEqual(format_number(5.5, "mm", "de", trim=True), "5,5")
        self.assertEqual(format_number(5.0, "in", "de", trim=True), "0,20")
        self.assertEqual(format_number(5.0, "in", "en", trim=True), "0.20")

    def test_every_interface_language_has_a_separator(self):
        with open(os.path.join(LOCALE_DIR, "LINGUAS"), encoding="utf-8") as fh:
            langs = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
        self.assertEqual(len(langs), 34)
        for lang in langs:
            self.assertIn(decimal_sep(lang), (",", "."))


class ParseTests(unittest.TestCase):
    def test_comma_and_point_both_accepted(self):
        for text in ("41,5", "41.5", " 41,5 ", "41,5 mm", "41.5mm", "41,50"):
            with self.subTest(text=text):
                self.assertEqual(parse_number(text, "mm"), 41.5)

    def test_rounded_to_tenth_of_millimetre(self):
        self.assertEqual(parse_number("41,26", "mm"), 41.3)
        self.assertEqual(parse_number("4,65", "in"), 118.1)       # 118,11 mm
        self.assertEqual(parse_number("1.3", "in"), 33.0)         # 33,02 mm
        self.assertEqual(parse_number('4.5"', "in"), 114.3)
        self.assertEqual(parse_number("4,5 in", "in"), 114.3)

    def test_arabic_decimal_separator_and_digits(self):
        self.assertEqual(parse_number("٤١٫٥", "mm"), 41.5)

    def test_invalid(self):
        for text in ("", " ", "abc", "1,2,3", "1.2.3", "nan", "inf", "-", ","):
            with self.subTest(text=text):
                self.assertIsNone(parse_number(text, "mm"))

    def test_round_trip_in_inches(self):
        # Anzeige in Zoll und erneute Eingabe ändert den Wert höchstens um 0,1 mm
        for mm in (18.0, 21.0, 33.0, 41.5, 50.0, 70.0, 80.0, 118.0, 119.5, 120.0):
            for lang in ("de", "en"):
                with self.subTest(mm=mm, lang=lang):
                    back = parse_number(format_number(mm, "in", lang), "in")
                    self.assertLessEqual(abs(back - mm), 0.13)


# Sprachen mit eigener Schreibweise der Einheiten; alle anderen „mm“/„in“.
NATIVE_UNITS = {
    "ar": ("مم", "بوصة"),
    "fa": ("میلی‌متر", "اینچ"),
    "he": ('מ"מ', "אינץ'"),
    "hi": ("मिमी", "इंच"),
    "ru": ("мм", "дюйм."),
    "th": ("มม.", "นิ้ว"),
    "uk": ("мм", "дюйм."),
}

# Neue Texte mit benannten Platzhaltern: alle müssen in jeder Übersetzung stehen.
PLACEHOLDERS = {
    "%(length)s links": ("%(length)s",),
    "%(length)s rechts": ("%(length)s",),
    "%(length)s oben": ("%(length)s",),
    "%(length)s unten": ("%(length)s",),
    "Innen %(inner)s, außen %(outer)s": ("%(inner)s", "%(outer)s"),
    ("Außerhalb des üblichen Druckbereichs (innen ab %(inner)s, außen bis "
     "%(outer)s): Tinte kann auf dem Disc-Fach landen."): ("%(inner)s", "%(outer)s"),
}


def _catalogs():
    return sorted(glob.glob(os.path.join(LOCALE_DIR, "*", "LC_MESSAGES",
                                         "disc_printer.po")))


@unittest.skipUnless(shutil.which("msgfmt"), "msgfmt nicht installiert")
class CatalogTests(unittest.TestCase):
    """Einheitszeichen und Platzhalter in allen 33 Übersetzungen."""

    def _each(self):
        pos = _catalogs()
        self.assertEqual(len(pos), 33)
        with tempfile.TemporaryDirectory() as tmp:
            for po in pos:
                lang = po.split(os.sep)[-3]
                mo = os.path.join(tmp, lang + ".mo")
                subprocess.run(["msgfmt", "--check", "-o", mo, po], check=True)
                with open(mo, "rb") as fh:
                    yield lang, gettext.GNUTranslations(fh)

    def test_unit_symbols(self):
        for lang, tr in self._each():
            with self.subTest(lang=lang):
                want = NATIVE_UNITS.get(lang, ("mm", "in"))
                self.assertEqual((tr.gettext("mm"), tr.gettext("in")), want)

    def test_placeholders_kept_and_translated(self):
        for lang, tr in self._each():
            for msgid, needed in PLACEHOLDERS.items():
                with self.subTest(lang=lang, msgid=msgid):
                    # im Katalog vorhanden (Niederländisch „links“ = Deutsch)
                    self.assertTrue(tr._catalog.get(msgid), "nicht übersetzt")
                    text = tr.gettext(msgid)
                    for ph in needed:
                        self.assertEqual(text.count(ph), 1, ph)
                    # füllbar ohne Fehler
                    text % {"length": "5 mm", "inner": "21 mm", "outer": "118 mm"}


if __name__ == "__main__":
    unittest.main()
