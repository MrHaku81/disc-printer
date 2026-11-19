"""Start ohne Anzeige (Issue #2): klare Meldung, Exit-Code != 0, kein Traceback.

Vorher: RuntimeError "Gtk couldn't be initialized" als Traceback aus dem
activate-Handler, danach "exit=0" im Log.

Die In-Prozess-Tests mocken log, damit nichts in die echte Logdatei im Home
geschrieben wird; der End-to-End-Test läuft mit temporärem HOME.
"""
import io
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from disc_printer import _log
from disc_printer.gui import window as w

SRC = str(Path(__file__).resolve().parent.parent / "src")


class MainWithoutDisplayTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(w, "log")
        self.log = p.start()
        self.addCleanup(p.stop)

    def _main(self, available: bool, env: dict[str, str]):
        err = io.StringIO()
        with mock.patch.object(w, "_display_available", return_value=available), \
             mock.patch.object(w, "DiscPrinterApp") as app_cls, \
             mock.patch.dict(os.environ, env, clear=False), \
             redirect_stderr(err), \
             self.assertRaises(SystemExit) as cm:
            for k in ("WAYLAND_DISPLAY", "DISPLAY"):
                if k not in env:
                    os.environ.pop(k, None)
            w.main()
        return cm.exception.code, err.getvalue(), app_cls

    def test_exits_nonzero_with_one_line(self):
        code, err, app_cls = self._main(False, {})
        self.assertNotEqual(code, 0)
        self.assertEqual(err.count("\n"), 1, err)
        self.assertIn("cannot open a display", err)
        self.assertIn("neither WAYLAND_DISPLAY nor DISPLAY is set", err)
        self.assertNotIn("Traceback", err)
        app_cls.assert_not_called()

    def test_names_unreachable_display(self):
        _, err, _ = self._main(False, {"DISPLAY": ":99"})
        self.assertIn("DISPLAY=:99 is not reachable", err)
        _, err, _ = self._main(False, {"WAYLAND_DISPLAY": "wayland-9"})
        self.assertIn("WAYLAND_DISPLAY=wayland-9 is not reachable", err)

    def test_logged_to_file_only(self):
        self._main(False, {})
        self.log.error.assert_called_once()
        self.assertEqual(self.log.error.call_args.kwargs.get("extra"), _log.FILE_ONLY)

    def test_with_display_runs_app_and_keeps_its_exit_code(self):
        app = mock.Mock()
        app.run.return_value = 0
        with mock.patch.object(w, "_display_available", return_value=True), \
             mock.patch.object(w, "DiscPrinterApp", return_value=app), \
             self.assertRaises(SystemExit) as cm:
            w.main()
        app.run.assert_called_once()
        self.assertEqual(cm.exception.code, 0)


class DisplayAvailableTests(unittest.TestCase):
    def test_init_check_true_but_no_display_is_unavailable(self):
        # GTK 4 nach fehlgeschlagener Import-Initialisierung
        with mock.patch.object(w.Gtk, "init_check", return_value=True), \
             mock.patch.object(w.Gdk.Display, "get_default", return_value=None):
            self.assertFalse(w._display_available())

    def test_display_present(self):
        with mock.patch.object(w.Gtk, "init_check", return_value=True), \
             mock.patch.object(w.Gdk.Display, "get_default", return_value=object()):
            self.assertTrue(w._display_available())


class FileOnlyFilterTests(unittest.TestCase):
    def test_console_handler_drops_file_only_records(self):
        rec = logging.LogRecord("disc_printer", logging.ERROR, __file__, 1, "x", None, None)
        self.assertTrue(_log._console_filter(rec))
        rec.console = _log.FILE_ONLY["console"]
        self.assertFalse(_log._console_filter(rec))


class EndToEndTests(unittest.TestCase):
    def test_real_start_without_display(self):
        with tempfile.TemporaryDirectory() as home:
            env = {k: v for k, v in os.environ.items()
                   if k not in ("DISPLAY", "WAYLAND_DISPLAY", "GDK_BACKEND")}
            env.update(HOME=home, PYTHONPATH=SRC)
            r = subprocess.run([sys.executable, "-m", "disc_printer"], env=env,
                               capture_output=True, text=True, timeout=60)
            logtext = (Path(home) / "disc-printer.log").read_text(encoding="utf-8")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr.count("\n"), 1, r.stderr)
        self.assertIn("cannot open a display", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("Gtk-CRITICAL", r.stderr)
        self.assertIn("GTK initialisation failed", logtext)
        self.assertNotIn("exit=0", logtext)


if __name__ == "__main__":
    unittest.main()
