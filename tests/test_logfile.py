"""Logdatei im XDG-State-Ordner, erst bei Bedarf geöffnet, umlenkbar.

Hermetisch: Pfade liegen in TemporaryDirectory, Prozesse laufen mit
temporärem HOME/XDG_STATE_HOME.
"""
import os
# Kein Datei-Log in Tests: nie in die echte Logdatei im Home schreiben.
os.environ["DISC_PRINTER_LOG_FILE"] = ""

import io
import logging
import re
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from disc_printer import _log, paths

ROOT = Path(__file__).resolve().parent.parent
SRC = str(ROOT / "src")


class _Tmp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        p = mock.patch.object(Path, "home", side_effect=AssertionError("echtes Home"))
        p.start()
        self.addCleanup(p.stop)


class LogPathTests(_Tmp):
    def test_state_dir_subfolder(self):
        self.assertEqual(paths.log_file(self.tmp, self.tmp / "st", environ={}),
                         self.tmp / "st" / "disc-printer" / "disc-printer.log")

    def test_fallback_local_state(self):
        self.assertEqual(paths.log_file(self.tmp, None, environ={}),
                         self.tmp / ".local" / "state" / "disc-printer" / "disc-printer.log")

    def test_env_override(self):
        self.assertEqual(paths.log_file(self.tmp, None, environ={paths.LOG_ENV: str(self.tmp / "x.log")}),
                         self.tmp / "x.log")

    def test_env_empty_disables(self):
        self.assertIsNone(paths.log_file(self.tmp, None, environ={paths.LOG_ENV: ""}))

    def test_never_in_home_root(self):
        self.assertNotEqual(paths.log_file(self.tmp, None, environ={}).parent, self.tmp)


class GLibVersionFallbackTests(unittest.TestCase):
    """GLib.get_user_state_dir() gibt es erst ab GLib 2.72."""

    def test_uses_glib_when_available(self):
        glib = types.SimpleNamespace(get_user_state_dir=lambda: "/x/state")
        self.assertEqual(paths._system_state_dir(glib), Path("/x/state"))

    def test_old_glib_uses_xdg_state_home(self):
        old = types.SimpleNamespace()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "/y/state"}):
            self.assertEqual(paths._system_state_dir(old), Path("/y/state"))

    def test_old_glib_ignores_relative_or_missing(self):
        old = types.SimpleNamespace()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "rel/state"}):
            self.assertIsNone(paths._system_state_dir(old))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_STATE_HOME", None)
            self.assertIsNone(paths._system_state_dir(old))

    def test_real_glib_has_it(self):
        from gi.repository import GLib
        if (GLib.MAJOR_VERSION, GLib.MINOR_VERSION) >= (2, 72):
            self.assertTrue(hasattr(GLib, "get_user_state_dir"))


def _record(msg="hello"):
    return logging.LogRecord("disc_printer", logging.INFO, __file__, 1, msg, None, None)


class LazyFileHandlerTests(_Tmp):
    def _handler(self, path):
        h = _log._LazyFileHandler(lambda: path)
        h.setFormatter(logging.Formatter("%(message)s"))
        self.addCleanup(h.close)
        return h

    def test_opens_only_on_first_record_and_creates_folder(self):
        path = self.tmp / "state" / "disc-printer" / "disc-printer.log"
        h = self._handler(path)
        self.assertFalse(path.parent.exists())
        h.handle(_record("one"))
        h.handle(_record("two"))
        self.assertEqual(path.read_text(encoding="utf-8"), "one\ntwo\n")

    def test_unwritable_reports_once_and_continues(self):
        blocker = self.tmp / "file"
        blocker.write_text("")
        h = self._handler(blocker / "disc-printer.log")
        err = io.StringIO()
        with redirect_stderr(err):
            h.handle(_record("a"))
            h.handle(_record("b"))
        self.assertEqual(err.getvalue().count("\n"), 1, err.getvalue())
        self.assertIn("cannot write log file", err.getvalue())
        self.assertIn("continuing without a log file", err.getvalue())

    def test_disabled_writes_nothing(self):
        h = self._handler(None)
        err = io.StringIO()
        with redirect_stderr(err):
            h.handle(_record())
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(list(self.tmp.iterdir()), [])


class ProcessTests(unittest.TestCase):
    def _run(self, code, home, **extra):
        env = {k: v for k, v in os.environ.items() if k != "DISC_PRINTER_LOG_FILE"}
        env.update(HOME=str(home), XDG_STATE_HOME=str(home / "state"), PYTHONPATH=SRC, **extra)
        return subprocess.run([sys.executable, "-c", code], env=env,
                              capture_output=True, text=True, timeout=60)

    def test_import_creates_no_log(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            r = self._run("import disc_printer.gui.window", home)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((home / "state").exists())
            self.assertFalse((home / "disc-printer.log").exists())

    def test_first_record_goes_to_state_dir(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            r = self._run("from disc_printer import log; log.info('hello')", home)
            self.assertEqual(r.returncode, 0, r.stderr)
            f = home / "state" / "disc-printer" / "disc-printer.log"
            self.assertIn("hello", f.read_text(encoding="utf-8"))
            self.assertFalse((home / "disc-printer.log").exists())

    def test_unwritable_app_keeps_running(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "state").write_text("")  # State-Ordner ist eine Datei
            r = self._run("from disc_printer import log; log.info('a'); log.info('b'); print('ok')",
                          home)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stderr.count("cannot write log file"), 1, r.stderr)
            self.assertIn("ok", r.stdout)


class TestPreambleTests(unittest.TestCase):
    """Jede Testdatei schaltet das Datei-Log ab, bevor disc_printer geladen wird."""

    def test_every_test_module_disables_file_log(self):
        for f in sorted((ROOT / "tests").glob("test_*.py")):
            with self.subTest(f=f.name):
                s = f.read_text(encoding="utf-8")
                pre = s.find('os.environ["DISC_PRINTER_LOG_FILE"] = ""')
                first = re.search(r"^(from|import) disc_printer", s, re.M)
                self.assertNotEqual(pre, -1)
                if first:
                    self.assertLess(pre, first.start())


if __name__ == "__main__":
    unittest.main()
