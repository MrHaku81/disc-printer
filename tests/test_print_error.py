"""Fehlermeldung bei lp-Fehlern auf temporären (treiberlosen) Zielen.

Kein echtes CUPS und kein Druck: subprocess.run, GLib.idle_add und das
Schreiben der PNG werden gemockt.
"""

import os
# Kein Datei-Log in Tests: nie in die echte Logdatei im Home schreiben.
os.environ["DISC_PRINTER_LOG_FILE"] = ""

import subprocess
import unittest
from unittest import mock

from disc_printer import printer as pr
from disc_printer.printer import DiscPrinter

LP_ERR = "lp: No such file or directory"


def _printer(temporary: bool) -> DiscPrinter:
    return DiscPrinter("Canon_TS700_series", "/etc/cups/ppd/x.ppd",
                       "Disc", "Disc", "om_square_120x120mm",
                       temporary=temporary)


class LpErrorMessageTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(pr, "_", side_effect=lambda s: s)
        p.start()
        self.addCleanup(p.stop)

    def test_permanent_queue_unchanged(self):
        self.assertEqual(pr.lp_error_message(_printer(False), LP_ERR),
                         "Druckfehler:\n" + LP_ERR)

    def test_temporary_queue_explained(self):
        msg = pr.lp_error_message(_printer(True), LP_ERR)
        self.assertIn("treiberlose Drucker", msg)
        self.assertIn("CUPS 2.4.20", msg)
        self.assertIn("fest einrichten", msg)
        self.assertNotIn(LP_ERR, msg)

    def test_temporary_message_goes_through_gettext(self):
        with mock.patch.object(pr, "_", side_effect=lambda s: "XX") as g:
            self.assertEqual(pr.lp_error_message(_printer(True), LP_ERR), "XX")
            g.assert_called_once()


class PrintThreadTests(unittest.TestCase):
    """MainWindow._print_thread mit Fake-self (kein Fenster, kein Display)."""

    @classmethod
    def setUpClass(cls):
        from disc_printer.gui import window
        cls.window = window

    def _run(self, printer, result):
        w = self.window
        fake_self = mock.Mock()
        with mock.patch.object(w, "write_print_png"), \
             mock.patch.object(w.subprocess, "run", return_value=result) as run, \
             mock.patch.object(w.GLib, "idle_add") as idle, \
             self.assertLogs("disc_printer", "INFO") as logs:
            w.MainWindow._print_thread(fake_self, printer, surf=None)
        return fake_self, run, idle, logs.output

    def test_temporary_failure_shows_explanation_and_logs_lp_error(self):
        p = _printer(True)
        fake, run, idle, logs = self._run(
            p, subprocess.CompletedProcess([], 1, "", LP_ERR + "\n"))
        self.assertEqual(run.call_args.args[0][:3], ["lp", "-d", p.name])
        idle.assert_called_once_with(fake._show_error,
                                     pr.lp_error_message(p, LP_ERR))
        self.assertTrue(any(LP_ERR in l and "rc=1" in l for l in logs))
        self.assertTrue(any("cups#1751" in l for l in logs))

    def test_permanent_failure_unchanged(self):
        p = _printer(False)
        fake, _, idle, logs = self._run(
            p, subprocess.CompletedProcess([], 1, "", LP_ERR))
        idle.assert_called_once_with(fake._show_error,
                                     self.window._("Druckfehler:\n%s") % LP_ERR)
        self.assertFalse(any("cups#1751" in l for l in logs))

    def test_temporary_success_unchanged(self):
        fake, _, idle, _ = self._run(
            _printer(True),
            subprocess.CompletedProcess([], 0, "request id is X-1 (1 file(s))\n", ""))
        idle.assert_called_once_with(fake._on_print_success,
                                     "request id is X-1 (1 file(s))")


class PrintSuccessDialogTests(unittest.TestCase):
    """_on_print_success ohne Fenster: echter Gtk.AlertDialog, show() gemockt."""

    @classmethod
    def setUpClass(cls):
        from disc_printer.gui import window
        cls.window = window

    def _call(self, job_info):
        w = self.window
        fake_self = mock.Mock()
        calls = []

        def fake_show(dlg, parent):
            calls.append((dlg, parent))

        with mock.patch.object(w.Gtk.AlertDialog, "show", fake_show):
            ret = w.MainWindow._on_print_success(fake_self, job_info)
        self.assertEqual(len(calls), 1)
        dlg, parent = calls[0]
        self.assertIs(parent, fake_self)
        self.assertEqual(ret, w.GLib.SOURCE_REMOVE)
        return dlg

    def test_no_exception_and_texts_set(self):
        dlg = self._call("request id is Canon_TS700_series-12 (1 file(s))")
        self.assertIsInstance(dlg, self.window.Gtk.AlertDialog)
        self.assertEqual(dlg.get_message(),
                         self.window._("Druckauftrag gesendet"))
        self.assertEqual(dlg.get_detail(),
                         "request id is Canon_TS700_series-12 (1 file(s))")
        self.assertEqual(list(dlg.get_buttons()), [self.window._("OK")])
        self.assertEqual(dlg.get_default_button(), 0)

    def test_empty_job_info_uses_fallback_text(self):
        dlg = self._call("")
        self.assertEqual(dlg.get_detail(), self.window._(
            "Druckauftrag erfolgreich in Warteschlange eingereiht."))


if __name__ == "__main__":
    unittest.main()
