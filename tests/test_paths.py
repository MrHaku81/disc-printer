"""Speicherort der Designs (Issue #2: kein festes ~/Dokumente mehr).

Hermetisch: jedes Home-Verzeichnis ist ein TemporaryDirectory, der
Dokumente-Ordner wird übergeben statt über GLib/user-dirs.dirs ermittelt.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from disc_printer import paths


class _HomeCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        # Sicherheitsnetz: ein vergessenes home= darf nie das echte Home treffen.
        p = mock.patch.object(Path, "home", side_effect=AssertionError("echtes Home"))
        p.start()
        self.addCleanup(p.stop)

    def legacy(self, with_file: bool) -> Path:
        d = self.home / "Dokumente" / "DiscPrinter"
        d.mkdir(parents=True)
        if with_file:
            (d / "alt.discprint").write_bytes(b"x")
        return d


class DocumentsDirTests(_HomeCase):
    def test_none_when_system_reports_nothing(self):
        self.assertIsNone(paths.documents_dir(self.home, None))

    def test_none_when_disabled_points_to_home(self):
        self.assertIsNone(paths.documents_dir(self.home, str(self.home)))

    def test_system_value_used(self):
        self.assertEqual(paths.documents_dir(self.home, str(self.home / "Documents")),
                         self.home / "Documents")

    def test_default_queries_glib(self):
        with mock.patch.object(paths, "_system_documents_dir",
                               return_value=self.home / "Documenti") as q:
            self.assertEqual(paths.design_dir(self.home),
                             self.home / "Documenti" / "DiscPrinter")
        q.assert_called_once_with()


class DesignDirTests(_HomeCase):
    def test_english_system(self):
        self.assertEqual(paths.design_dir(self.home, self.home / "Documents"),
                         self.home / "Documents" / "DiscPrinter")

    def test_fallback_without_documents_dir(self):
        self.assertEqual(paths.design_dir(self.home, None), self.home / "DiscPrinter")

    def test_independent_of_app_language(self):
        for lang in ("de_DE.UTF-8", "en_US.UTF-8", "ja_JP.UTF-8"):
            with self.subTest(lang=lang), mock.patch.dict(os.environ, {"LANGUAGE": lang, "LANG": lang}):
                self.assertEqual(paths.design_dir(self.home, self.home / "Documents"),
                                 self.home / "Documents" / "DiscPrinter")

    def test_does_not_create_anything(self):
        paths.design_dir(self.home, self.home / "Documents")
        paths.open_dialog_folder(self.home, self.home / "Documents")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_legacy_with_files_kept(self):
        legacy = self.legacy(with_file=True)
        self.assertEqual(paths.design_dir(self.home, self.home / "Documents"), legacy)
        self.assertEqual(paths.design_dir(self.home, None), legacy)

    def test_legacy_empty_ignored(self):
        self.legacy(with_file=False)
        self.assertEqual(paths.design_dir(self.home, self.home / "Documents"),
                         self.home / "Documents" / "DiscPrinter")

    def test_new_dir_existing_wins_over_legacy(self):
        self.legacy(with_file=True)
        new = self.home / "Documents" / "DiscPrinter"
        new.mkdir(parents=True)
        self.assertEqual(paths.design_dir(self.home, self.home / "Documents"), new)

    def test_german_system_same_dir(self):
        legacy = self.legacy(with_file=False)
        self.assertEqual(paths.design_dir(self.home, self.home / "Dokumente"), legacy)

    def test_legacy_untouched(self):
        legacy = self.legacy(with_file=True)
        paths.ensure_design_dir(self.home, self.home / "Documents")
        self.assertEqual([p.name for p in legacy.iterdir()], ["alt.discprint"])
        self.assertFalse((self.home / "Documents").exists())


class DialogFolderTests(_HomeCase):
    def test_open_falls_back_to_documents(self):
        docs = self.home / "Documents"
        docs.mkdir()
        self.assertEqual(paths.open_dialog_folder(self.home, docs), docs)

    def test_open_falls_back_to_home(self):
        self.assertEqual(paths.open_dialog_folder(self.home, self.home / "Documents"), self.home)

    def test_open_uses_existing_subdir(self):
        sub = self.home / "Documents" / "DiscPrinter"
        sub.mkdir(parents=True)
        self.assertEqual(paths.open_dialog_folder(self.home, self.home / "Documents"), sub)

    def test_save_creates_subdir(self):
        target = paths.ensure_design_dir(self.home, self.home / "Documents")
        self.assertEqual(target, self.home / "Documents" / "DiscPrinter")
        self.assertTrue(target.is_dir())

    def test_save_mkdir_failure_falls_back(self):
        docs = self.home / "Documents"
        docs.mkdir()
        with mock.patch.object(Path, "mkdir", side_effect=PermissionError("ro")):
            self.assertEqual(paths.ensure_design_dir(self.home, docs), docs)


class NoStartupMkdirTests(unittest.TestCase):
    def test_window_has_no_startup_mkdir_and_no_hardcoded_dir(self):
        src = (Path(__file__).parent.parent / "src" / "disc_printer")
        window = (src / "gui" / "window.py").read_text(encoding="utf-8")
        fmt = (src / "file_format.py").read_text(encoding="utf-8")
        self.assertNotIn("DEFAULT_DIR", window)
        self.assertNotIn("DEFAULT_DIR", fmt)
        self.assertNotIn('"Dokumente"', fmt)


if __name__ == "__main__":
    unittest.main()
