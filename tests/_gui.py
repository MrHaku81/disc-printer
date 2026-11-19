"""Privater Broadway-Server für GUI-Tests (ohne Fenster auf dem Bildschirm).

Eigener Laufzeitordner und eigenes HOME im Temp-Verzeichnis, TCP nur auf
127.0.0.1 mit freiem Port. Ohne gtk4-broadwayd werden die GUI-Tests
übersprungen.
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = str(ROOT / "src")
SCENARIOS = str(Path(__file__).resolve().parent / "_gui_scenarios.py")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BroadwayCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        exe = shutil.which("gtk4-broadwayd")
        if exe is None:
            raise unittest.SkipTest("gtk4-broadwayd nicht installiert")
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        cls.run_dir = base / "run"
        cls.home = base / "home"
        cls.run_dir.mkdir(mode=0o700)
        cls.home.mkdir()
        env = dict(os.environ, XDG_RUNTIME_DIR=str(cls.run_dir), HOME=str(cls.home))
        cls._server = subprocess.Popen(
            [exe, "--address", "127.0.0.1", "--port", str(_free_port()), ":5"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sock = cls.run_dir / "broadway6.socket"
        for _ in range(250):
            if sock.exists():
                break
            time.sleep(0.02)
        else:
            cls._server.kill()
            cls._tmp.cleanup()
            raise unittest.SkipTest("Broadway-Server startet nicht")

    @classmethod
    def tearDownClass(cls):
        cls._server.terminate()
        cls._server.wait(5)
        cls._tmp.cleanup()

    def run_scenario(self, name: str) -> Path:
        """Szenario ausführen; gibt die Logdatei des Laufs zurück."""
        work = Path(tempfile.mkdtemp(dir=self._tmp.name))
        log = work / "app.log"
        # Feste Systemsprache: unabhängig vom Rechner, und "C" ergibt den
        # Deutsch-Fallback (keine Sprache gewählt), den Fall des Sprachfeld-Fehlers.
        env = {k: v for k, v in os.environ.items()
               if k not in ("DISPLAY", "WAYLAND_DISPLAY", "LANGUAGE", "LC_ALL",
                            "LC_MESSAGES")}
        env["LANG"] = "C.UTF-8"
        env.update(GDK_BACKEND="broadway", BROADWAY_DISPLAY=":5",
                   XDG_RUNTIME_DIR=str(self.run_dir), HOME=str(self.home),
                   XDG_STATE_HOME=str(self.home / "state"),
                   DISC_PRINTER_LOG_FILE=str(log), PYTHONPATH=SRC,
                   GSETTINGS_BACKEND="memory")
        r = subprocess.run([sys.executable, SCENARIOS, name, str(work)], env=env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0,
                         f"Szenario {name} fehlgeschlagen:\n{r.stdout}\n{r.stderr}")
        self.assertIn(f"{name} OK", r.stdout)
        return log
