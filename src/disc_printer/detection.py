import http.client
import os
import re
import socket
import subprocess
from pathlib import Path

from ._log import log
from .printer import DiscPrinter

# ── Keyword-Sets ──────────────────────────────────────────────────────────────
# Substring-Matches (case-insensitive) für die drei PPD-Schlüssel.
# Jeweils sowohl Option-Value (maschinenlesbar) als auch UI-Label (nach '/').

_SLOT_KEYS = frozenset({
    "disc", "cdtray", "cd_tray", "cd-r", "cdr", "cd", "dvd", "blu",
})
_TYPE_KEYS = frozenset({
    "disc", "cd-r", "cdr", "cd", "dvd", "blu",
})
_SIZE_KEYS = frozenset({
    "disc", "cd", "dvd", "120x120", "120mm",
})

# Canon/Epson kodieren 120 mm in PostScript-Punkten: 120 mm × (72/25.4) ≈ 340 pt
# → "w340h340".  Wir tolerieren ±5 Punkte Rundungsdifferenz (335–345 pt).
_SIZE_PT_RE = re.compile(r'\bw3[34]\dh3[34]\d\b', re.IGNORECASE)

# PPD-Optionszeile: *KeyName Value[/UILabel]:  ...
_PPD_OPT_RE = re.compile(r'^\*(\w+)\s+([^\s/:]+)(?:/([^:]+))?\s*:')

_PPD_DIR = Path("/etc/cups/ppd")


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _matches(token: str, keys: frozenset[str]) -> bool:
    """True wenn einer der Keys als Teilstring in token (lowercase) vorkommt."""
    t = token.lower()
    return any(k in t for k in keys)


def _find_ppd(name: str) -> Path | None:
    p = _PPD_DIR / f"{name}.ppd"
    return p if p.exists() else None


# ── PPD-Parser ────────────────────────────────────────────────────────────────

def _parse_ppd(ppd_path: Path) -> tuple[str | None, str | None, str] | None:
    """
    Liest eine PPD-Datei direkt und sucht nach Disc-Tray-Fähigkeiten.

    Geprüft werden *InputSlot-, *MediaType- und *PageSize-Einträge,
    jeweils der Option-Value (maschinenlesbar) UND der UI-Label (nach '/').
    Canon-/Epson-spezifische PostScript-Punktgrößen ("w340h340" = 120×120 mm)
    werden per Regex erkannt.

    Rückgabe: (input_slot, media_type, page_size)  oder  None.
    """
    try:
        # Adobe PPD-Spec 4.3 schreibt Latin-1 vor; errors='replace' für Robustheit
        text = ppd_path.read_text(encoding="latin-1", errors="replace")
    except OSError as e:
        log.debug(f"    PPD-Lesefehler {ppd_path.name}: {e}")
        return None

    slot:  str | None = None
    mtype: str | None = None
    msize: str | None = None

    for line in text.splitlines():
        m = _PPD_OPT_RE.match(line)
        if not m:
            continue
        key   = m.group(1).lower()
        value = m.group(2)
        label = m.group(3) or ""

        if key == "inputslot" and slot is None:
            if _matches(value, _SLOT_KEYS) or _matches(label, _SLOT_KEYS):
                slot = value
                log.debug(f"    PPD InputSlot gefunden: {value!r}  label={label!r}")

        elif key == "mediatype" and mtype is None:
            if _matches(value, _TYPE_KEYS) or _matches(label, _TYPE_KEYS):
                mtype = value
                log.debug(f"    PPD MediaType gefunden: {value!r}  label={label!r}")

        elif key == "pagesize" and msize is None:
            if (
                _matches(value, _SIZE_KEYS)
                or _matches(label, _SIZE_KEYS)
                or bool(_SIZE_PT_RE.search(value))
            ):
                msize = value
                log.debug(f"    PPD PageSize  gefunden: {value!r}  label={label!r}")

    if slot is None and mtype is None:
        return None
    return slot, mtype, msize or "120x120mm"


# ── lpoptions-Fallback ────────────────────────────────────────────────────────

def _query_via_lpoptions(name: str) -> tuple[str | None, str | None, str] | None:
    """
    Ermittelt Disc-Fähigkeiten über `lpoptions -p <name> -l`.

    Wird verwendet wenn die PPD-Datei nicht existiert (driverless/IPP) oder
    nicht lesbar ist (fehlende Berechtigung).
    """
    try:
        r = subprocess.run(
            ["lpoptions", "-p", name, "-l"],
            capture_output=True, text=True, timeout=6,
        )
    except FileNotFoundError:
        log.error("lpoptions nicht gefunden — ist CUPS installiert?")
        return None
    except subprocess.TimeoutExpired:
        log.error(f"lpoptions Timeout für {name}")
        return None
    except Exception as e:
        log.error(f"lpoptions Fehler für {name}: {e}")
        return None

    slot:  str | None = None
    mtype: str | None = None
    msize: str | None = None

    for line in r.stdout.splitlines():
        if ":" not in line:
            continue
        key_part, _, values_part = line.partition(":")
        key_lower = key_part.strip().lower()
        # '*token' markiert den aktuellen Default → Stern entfernen
        tokens = [t.lstrip("*") for t in values_part.split()]

        if key_lower.startswith("inputslot"):
            disc = [t for t in tokens if _matches(t, _SLOT_KEYS)]
            if disc and slot is None:
                slot = disc[0]
        elif key_lower.startswith("mediatype"):
            disc = [t for t in tokens if _matches(t, _TYPE_KEYS)]
            if disc and mtype is None:
                mtype = disc[0]
        elif key_lower.startswith("pagesize"):
            for t in tokens:
                if (_matches(t, _SIZE_KEYS) or "120x120" in t) and msize is None:
                    msize = t

    if slot is None and mtype is None:
        return None
    return slot, mtype, msize or "120x120mm"


# ── CUPS-HTTP-Fallback ────────────────────────────────────────────────────────

_CUPS_SOCKETS = ["/run/cups/cups.sock", "/var/run/cups/cups.sock"]


def _fetch_ppd_via_cups_http(name: str) -> str | None:
    """
    Holt die PPD-Datei eines Druckers über die CUPS HTTP-API via Unix-Socket.

    Funktioniert im Flatpak-Sandbox ohne Dateisystemzugriff auf /etc/cups,
    solange --socket=cups das Host-Socket nach /run/cups/cups.sock mappt.
    """
    for sock_path in _CUPS_SOCKETS:
        if not os.path.exists(sock_path):
            continue
        try:
            class _UnixConn(http.client.HTTPConnection):
                def connect(self) -> None:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(6)
                    s.connect(sock_path)
                    self.sock = s

            conn = _UnixConn("localhost")
            conn.request("GET", f"/printers/{name}.ppd")
            resp = conn.getresponse()
            if resp.status == 200:
                content = resp.read().decode("latin-1", errors="replace")
                log.debug(f"    PPD via CUPS-HTTP geholt ({len(content)} Bytes)")
                return content
            log.debug(f"    CUPS-HTTP PPD Status {resp.status} für {name!r}")
        except Exception as e:
            log.debug(f"    CUPS-HTTP Fehler ({sock_path}): {e}")
    return None


def _query_via_cups_http(name: str) -> tuple[str | None, str | None, str] | None:
    """Lädt PPD über CUPS HTTP-API und analysiert sie wie eine lokale PPD-Datei."""
    content = _fetch_ppd_via_cups_http(name)
    if content is None:
        return None

    slot:  str | None = None
    mtype: str | None = None
    msize: str | None = None

    for line in content.splitlines():
        m = _PPD_OPT_RE.match(line)
        if not m:
            continue
        key   = m.group(1).lower()
        value = m.group(2)
        label = m.group(3) or ""

        if key == "inputslot" and slot is None:
            if _matches(value, _SLOT_KEYS) or _matches(label, _SLOT_KEYS):
                slot = value
                log.debug(f"    HTTP-PPD InputSlot: {value!r}  label={label!r}")
        elif key == "mediatype" and mtype is None:
            if _matches(value, _TYPE_KEYS) or _matches(label, _TYPE_KEYS):
                mtype = value
                log.debug(f"    HTTP-PPD MediaType: {value!r}  label={label!r}")
        elif key == "pagesize" and msize is None:
            if (
                _matches(value, _SIZE_KEYS)
                or _matches(label, _SIZE_KEYS)
                or bool(_SIZE_PT_RE.search(value))
            ):
                msize = value
                log.debug(f"    HTTP-PPD PageSize:  {value!r}  label={label!r}")

    if slot is None and mtype is None:
        return None
    return slot, mtype, msize or "120x120mm"


# ── Orchestrierung ────────────────────────────────────────────────────────────

def _detect_caps(
    name: str,
) -> tuple[tuple[str | None, str | None, str] | None, str]:
    """
    Erkennt Disc-Fähigkeiten eines Druckers.

    Strategie:
      1. PPD vorhanden + lesbar  → PPD-Parser (schnell, kein Subprocess)
      2. PPD vorhanden, aber kein Lesezugriff (cups-Gruppe fehlt)
                                 → lpoptions-Fallback
      3. Kein PPD (driverless / IPP / Flatpak-Sandbox)
                                 → lpoptions-Fallback
      4. lpoptions liefert kein Ergebnis (z. B. Flatpak-Sandbox ohne
         /etc/cups-Zugriff)    → PPD via CUPS HTTP-API (Unix-Socket)

    Rückgabe: (caps | None, Quelle)
      caps   = (input_slot, media_type, page_size) oder None
      Quelle = "ppd" | "lpoptions" | "cups-http"
    """
    ppd_path = _find_ppd(name)

    if ppd_path is not None:
        if os.access(ppd_path, os.R_OK):
            result = _parse_ppd(ppd_path)
            if result is not None:
                return result, "ppd"
            # PPD lesbar, kein Disc-Support → maßgeblich negativ
            return None, "ppd"
        else:
            log.debug(
                f"    PPD existiert, aber kein Lesezugriff "
                f"(cups-Gruppe?) → lpoptions"
            )
    else:
        log.debug(f"    Kein PPD für {name!r} (driverless?) → lpoptions")

    result = _query_via_lpoptions(name)
    if result is not None:
        return result, "lpoptions"

    log.debug(f"    lpoptions kein Ergebnis → versuche CUPS HTTP-API")
    return _query_via_cups_http(name), "cups-http"


# ── lpstat ────────────────────────────────────────────────────────────────────

def _lpstat_names() -> list[str]:
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    try:
        r = subprocess.run(
            ["lpstat", "-p"], capture_output=True, text=True,
            timeout=6, env=env,
        )
        names: list[str] = []
        for line in r.stdout.splitlines():
            if line.startswith("printer "):
                p = line.split()
                if len(p) >= 2:
                    names.append(p[1])
        return names
    except FileNotFoundError:
        log.error("lpstat nicht gefunden — ist CUPS installiert?")
    except subprocess.TimeoutExpired:
        log.error("lpstat Timeout")
    except Exception as e:
        log.error(f"lpstat Fehler: {e}")
    return []


# ── Öffentliche API ───────────────────────────────────────────────────────────

def detect_disc_printers() -> list[DiscPrinter]:
    """
    Gibt alle CUPS-Drucker zurück, die Disc-Druck unterstützen.

    Erkennung je Drucker: PPD-Parser zuerst, dann lpoptions-Fallback.
    Nur Drucker mit nachgewiesenem InputSlot oder MediaType für Discs
    erscheinen in der Liste — die GUI zeigt damit automatisch nur
    kompatible Geräte an.
    """
    log.info("=== Druckererkennung gestartet ===")
    names = _lpstat_names()
    log.info(f"CUPS-Drucker gefunden: {names or '(keine)'}")

    found: list[DiscPrinter] = []
    for name in names:
        log.info(f"  Prüfe {name!r} …")
        result, source = _detect_caps(name)
        if result:
            slot, mtype, msize = result
            ppd_path = str(_find_ppd(name) or f"/etc/cups/ppd/{name}.ppd")
            dp = DiscPrinter(name, ppd_path, slot, mtype, msize)
            found.append(dp)
            log.info(
                f"  ✓ {name} [{source}]: "
                f"InputSlot={slot!r}  MediaType={mtype!r}  media={msize!r}"
            )
        else:
            log.info(f"  ✗ {name}: kein Disc-Druck erkannt")

    log.info(f"Disc-fähige Drucker: {len(found)}")
    return found
