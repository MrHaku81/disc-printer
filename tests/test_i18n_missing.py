import tempfile
import unittest
from pathlib import Path
from unittest import mock

from disc_printer import i18n


class MissingTranslationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Leeres Locale-Verzeichnis: keine .mo vorhanden
        patches = [
            mock.patch.object(i18n, "_LOCALE_DIR", Path(self._tmp.name)),
            mock.patch.object(i18n, "_missing_warned", set()),
            mock.patch.object(i18n, "_t", i18n._t),
            mock.patch.object(i18n, "_current_lang", i18n._current_lang),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_warns_once_with_language_path_and_hint(self):
        with mock.patch.object(i18n.log, "warning") as warn:
            i18n.switch_language("fr")
            i18n.switch_language("fr")
        warn.assert_called_once()
        msg = warn.call_args.args[0]
        self.assertIn("'fr'", msg)
        self.assertIn(str(Path(self._tmp.name) / "fr" / "LC_MESSAGES" / "disc_printer.mo"), msg)
        self.assertIn("make compile-mo", msg)

    def test_fallback_to_german_unchanged(self):
        with mock.patch.object(i18n.log, "warning"):
            i18n.switch_language("fr")
        self.assertIsInstance(i18n._t, i18n.gettext.NullTranslations)
        self.assertEqual(i18n._("Drucken"), "Drucken")
        self.assertEqual(i18n.get_current_lang(), "fr")

    def test_each_language_warned_separately(self):
        with mock.patch.object(i18n.log, "warning") as warn:
            i18n.switch_language("fr")
            i18n.switch_language("ja")
        self.assertEqual(warn.call_count, 2)

    def test_no_warning_for_german_or_none(self):
        with mock.patch.object(i18n.log, "warning") as warn:
            i18n.switch_language("de")
            i18n.switch_language(None)
        warn.assert_not_called()

    def test_no_warning_when_catalog_exists(self):
        with mock.patch.object(i18n.log, "warning") as warn, \
             mock.patch.object(i18n.gettext, "translation",
                               return_value=i18n.gettext.NullTranslations()):
            i18n.switch_language("fr")
        warn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
