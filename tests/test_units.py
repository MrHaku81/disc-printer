import gettext
import glob
import os
import shutil
import subprocess
import tempfile
import unittest

from disc_printer.units import MM_PER_INCH, dimension_args, format_dimension, mm_to_inch

DIM = "Ø %(mm).0f mm / %(inch).2f in"
DIM_PRINTABLE = "Ø %(mm).0f mm / %(inch).2f in (bedruckbar)"
DIM_TWO_LINES = "Ø %(mm).0f mm\n%(inch).2f in"

LOCALE_DIR = os.path.join(os.path.dirname(__file__), os.pardir,
                          "src", "disc_printer", "locale")


class ConversionTests(unittest.TestCase):
    def test_mm_per_inch(self):
        self.assertEqual(MM_PER_INCH, 25.4)
        self.assertAlmostEqual(mm_to_inch(25.4), 1.0)

    def test_disc_dimensions_rounded_to_two_places(self):
        for mm, inch in ((120, "4.72"), (118, "4.65"), (50, "1.97"), (33, "1.30")):
            with self.subTest(mm=mm):
                self.assertEqual(f"{mm_to_inch(mm):.2f}", inch)

    def test_dimension_args(self):
        args = dimension_args(50.0)
        self.assertEqual(set(args), {"mm", "inch"})
        self.assertEqual(args["mm"], 50.0)
        self.assertAlmostEqual(args["inch"], 50.0 / 25.4)


class FormatTests(unittest.TestCase):
    def test_single_line(self):
        self.assertEqual(format_dimension(DIM, 120.0), "Ø 120 mm / 4.72 in")
        self.assertEqual(format_dimension(DIM, 50.0), "Ø 50 mm / 1.97 in")
        self.assertEqual(format_dimension(DIM, 33.0), "Ø 33 mm / 1.30 in")

    def test_printable(self):
        self.assertEqual(format_dimension(DIM_PRINTABLE, 118.0),
                         "Ø 118 mm / 4.65 in (bedruckbar)")

    def test_two_lines(self):
        self.assertEqual(format_dimension(DIM_TWO_LINES, 33.0).split("\n"),
                         ["Ø 33 mm", "1.30 in"])

    def test_reordered_template(self):
        # Übersetzer dürfen die Reihenfolge der benannten Platzhalter ändern.
        self.assertEqual(format_dimension("%(inch).2f in / %(mm).0f mm", 33.0),
                         "1.30 in / 33 mm")


@unittest.skipUnless(shutil.which("msgfmt"), "msgfmt nicht installiert")
class CatalogTests(unittest.TestCase):
    """Jede Sprache zeigt mm UND Zoll, kein Platzhalter fällt weg."""

    def test_all_languages_show_both_units(self):
        pos = sorted(glob.glob(os.path.join(LOCALE_DIR, "*", "LC_MESSAGES",
                                            "disc_printer.po")))
        self.assertTrue(pos)
        with tempfile.TemporaryDirectory() as tmp:
            for po in pos:
                lang = po.split(os.sep)[-3]
                mo = os.path.join(tmp, lang + ".mo")
                subprocess.run(["msgfmt", "--check", "-o", mo, po], check=True)
                with open(mo, "rb") as fh:
                    tr = gettext.GNUTranslations(fh)
                for template, mm, want in ((DIM, 120.0, ("120", "4.72")),
                                           (DIM, 33.0, ("33", "1.30")),
                                           (DIM_PRINTABLE, 118.0, ("118", "4.65")),
                                           (DIM_TWO_LINES, 33.0, ("33", "1.30"))):
                    with self.subTest(lang=lang, msgid=template):
                        translated = tr.gettext(template)
                        self.assertNotIn("bedruckbar", translated)
                        text = format_dimension(translated, mm)
                        for part in want + ("mm", " in"):
                            self.assertIn(part, text)
                        if template == DIM_TWO_LINES:
                            self.assertEqual(len(text.split("\n")), 2)


if __name__ == "__main__":
    unittest.main()
