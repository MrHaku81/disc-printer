"""Versionsnummer (eine Quelle) und Erkennung der Installationsart."""
import os
# Kein Datei-Log in Tests: nie in die echte Logdatei im Home schreiben.
os.environ["DISC_PRINTER_LOG_FILE"] = ""

import re
import tempfile
import tomllib
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from disc_printer import _version, install_kind as ik
from disc_printer.constants import APP_ID, README_UPDATING_URL, RELEASES_URL, REPO_URL

ROOT = Path(__file__).resolve().parent.parent


class VersionSourceTests(unittest.TestCase):
    def test_format(self):
        self.assertRegex(_version.__version__, r"^\d+\.\d+\.\d+$")

    def test_pyproject_reads_version_file(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertNotIn("version", data["project"], "zweite Versionsnummer in pyproject")
        self.assertIn("version", data["project"]["dynamic"])
        self.assertEqual(data["tool"]["hatch"]["version"]["path"],
                         "src/disc_printer/_version.py")

    def test_makefile_reads_version_file(self):
        mk = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("_version.py", mk)
        self.assertNotIn("pyproject.toml", mk)

    def test_metainfo_newest_release_matches(self):
        root = ET.parse(ROOT / "flatpak" / f"{APP_ID}.metainfo.xml").getroot()
        newest = root.find("releases").find("release").get("version")
        self.assertEqual(newest, _version.__version__)

    def test_no_other_version_literal_in_package(self):
        # Keine zweite Quelle im Programmcode
        v = re.escape(_version.__version__)
        for py in (ROOT / "src" / "disc_printer").rglob("*.py"):
            if py.name == "_version.py":
                continue
            self.assertNotRegex(py.read_text(encoding="utf-8"), rf"['\"]{v}['\"]", py)


class UrlTests(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(REPO_URL, "https://github.com/MrHaku81/disc-printer")
        self.assertEqual(RELEASES_URL,
                         "https://github.com/MrHaku81/disc-printer/releases/latest")
        self.assertEqual(README_UPDATING_URL, REPO_URL + "#updating")

    def test_readme_has_updating_anchor(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(readme, r"(?m)^## Updating$")


class InstallKindTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.module = self.base / "usr/lib/python3.14/site-packages/disc_printer/__init__.py"
        self.module.parent.mkdir(parents=True)
        self.module.touch()
        self.db = self.base / "pacman-local"
        self.db.mkdir()
        self.no_flatpak = self.base / "missing-flatpak-info"

    def package(self, dirname, *paths):
        d = self.db / dirname
        d.mkdir()
        lines = ["%FILES%"] + [str(p).lstrip("/") for p in paths]
        (d / "files").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def kind(self, **kw):
        kw.setdefault("flatpak_info", self.no_flatpak)
        return ik.install_kind(self.module, pacman_local=self.db, **kw)

    def test_flatpak_wins(self):
        info = self.base / ".flatpak-info"
        info.write_text("[Application]\n")
        self.package("disc-printer-0.2.0-2", self.module)
        self.assertEqual(self.kind(flatpak_info=info), "flatpak")

    def test_pacman_owns_running_file(self):
        self.package("disc-printer-0.2.0-2", self.module.parent, self.module)
        self.assertEqual(self.kind(), "pacman")

    def test_pacman_package_but_running_elsewhere(self):
        # AUR-Paket installiert, Programm läuft aber aus pipx/Quelltext
        self.package("disc-printer-0.2.0-2",
                     "/usr/lib/python3.14/site-packages/disc_printer/__init__.py")
        other = self.base / "home/.local/share/pipx/disc_printer/__init__.py"
        other.parent.mkdir(parents=True)
        other.touch()
        self.assertEqual(ik.install_kind(other, flatpak_info=self.no_flatpak,
                                         pacman_local=self.db), "other")

    def test_other_package_name_ignored(self):
        self.package("disc-printer-extra-1.0-1", self.module)
        self.assertEqual(self.kind(), "other")

    def test_no_pacman(self):
        self.assertEqual(ik.install_kind(self.module, flatpak_info=self.no_flatpak,
                                         pacman_local=self.base / "nope"), "other")

    def test_unreadable_files_list(self):
        (self.db / "disc-printer-0.2.0-2").mkdir()      # ohne files
        self.assertEqual(self.kind(), "other")

    def test_default_from_source_tree(self):
        # Start aus dem Quelltext: Modul liegt im Repo, nie pacman
        self.assertEqual(ik.install_kind(flatpak_info=self.no_flatpak), "other")


if __name__ == "__main__":
    unittest.main()
