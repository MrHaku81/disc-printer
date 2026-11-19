import http.client
import os
import re
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote, urlsplit

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
        log.debug(f"    PPD read error {ppd_path.name}: {e}")
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
                log.debug(f"    PPD InputSlot found: {value!r}  label={label!r}")

        elif key == "mediatype" and mtype is None:
            if _matches(value, _TYPE_KEYS) or _matches(label, _TYPE_KEYS):
                mtype = value
                log.debug(f"    PPD MediaType found: {value!r}  label={label!r}")

        elif key == "pagesize" and msize is None:
            if (
                _matches(value, _SIZE_KEYS)
                or _matches(label, _SIZE_KEYS)
                or bool(_SIZE_PT_RE.search(value))
            ):
                msize = value
                log.debug(f"    PPD PageSize  found: {value!r}  label={label!r}")

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
        log.error("lpoptions not found; is CUPS installed?")
        return None
    except subprocess.TimeoutExpired:
        log.error(f"lpoptions timeout for {name}")
        return None
    except Exception as e:
        log.error(f"lpoptions error for {name}: {e}")
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
                log.debug(f"    PPD fetched via CUPS HTTP ({len(content)} bytes)")
                return content
            log.debug(f"    CUPS HTTP PPD status {resp.status} for {name!r}")
        except Exception as e:
            log.debug(f"    CUPS HTTP error ({sock_path}): {e}")
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


# ── IPP-Fallback (treiberlose / temporäre Ziele) ─────────────────────────────

# Zeile der ipptool-Ausgabe (-t -v):  "        name (typ) = wert1,wert2"
_IPPTOOL_ATTR_RE = re.compile(r'^\s+([\w-]+) \([^)]*\) = (.*)$')

# dnssd://<Instanzname>.<_ipp|_ipps>._tcp.<domain>/?uuid=…
_DNSSD_HOST_RE = re.compile(r'^(?P<name>.+)\.(?P<regtype>_ipps?\._tcp)\.(?P<domain>.+?)\.?$')

_IPP_ATTRS = ("media-source-supported", "media-type-supported", "media-supported")


def _ppdize(keyword: str) -> str:
    """
    IPP-Keyword → PPD-Choice-Name, genauso wie CUPS es für treiberlose
    Warteschlangen erzeugt (pwg_ppdize_name): "disc" → "Disc",
    "photographic-glossy" → "PhotographicGlossy".  Damit sind die Werte
    identisch zu denen einer dauerhaft angelegten treiberlosen Queue.
    """
    if not keyword:
        return keyword
    out = [keyword[0].upper()]
    i = 1
    while i < len(keyword):
        c = keyword[i]
        if c == "-" and i + 1 < len(keyword) and keyword[i + 1].isalnum():
            out.append(keyword[i + 1].upper())
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _posix_regex_escape(text: str) -> str:
    return re.sub(r'([.^$|?*+()\[\]{}\\])', r'\\\1', text)


def _ipptool_cmd(device_uri: str) -> list[str] | None:
    """Baut den Befehl für Get-Printer-Attributes; dnssd:// via ippfind."""
    query = ["ipptool", "-T", "8", "-t", "-v"]
    scheme = device_uri.split(":", 1)[0].lower()
    if scheme in ("ipp", "ipps"):
        return query + [device_uri, "get-printer-attributes.test"]
    if scheme == "dnssd":
        m = _DNSSD_HOST_RE.match(unquote(urlsplit(device_uri).netloc))
        if not m:
            return None
        return [
            "ippfind", "-T", "3", m.group("regtype"),
            "--name", f"^{_posix_regex_escape(m.group('name'))}$",
            "-p",   # aufgelöste ipp(s)://host:port/… URI mit ausgeben
            "-x", *query, "{}", "get-printer-attributes.test", ";",
        ]
    return None


# Zeile von `ippfind -p`: aufgelöste URI am Zeilenanfang (ipptool rückt ein)
_RESOLVED_URI_RE = re.compile(r'^(ipps?://\S+)$')

_IPP_PACKAGE_HINT = "Debian/Ubuntu: cups-ipp-utils, Arch: cups"
_ipp_tools_warned = False


class _IppInfo(NamedTuple):
    resolved_uri: str | None          # ipp(s)://host:port/… (None wenn unbekannt)
    attrs: dict[str, list[str]]


# Ergebnis je device_uri, wird pro Erkennungslauf geleert. Die Abfragen
# laufen vorab parallel; die Kaskade (_detect_caps) liest nur noch hieraus.
_ipp_cache: dict[str, _IppInfo | None] = {}


def _check_ipp_tools(cmd: list[str]) -> bool:
    """True wenn alle benötigten Werkzeuge da sind; warnt sonst einmalig."""
    global _ipp_tools_warned
    needed = ["ipptool"] + (["ippfind"] if "ippfind" in cmd else [])
    missing = [t for t in needed if shutil.which(t) is None]
    if not missing:
        return True
    if not _ipp_tools_warned:
        _ipp_tools_warned = True
        log.warning(
            f"{' and '.join(missing)} not found; driverless printers "
            f"without a permanent CUPS queue cannot be detected as disc-capable. "
            f"Install the missing package ({_IPP_PACKAGE_HINT})."
        )
    return False


def _ipp_lookup(
    device_uri: str, resolved_uri: str | None = None,
) -> _IppInfo | None:
    """
    Get-Printer-Attributes beim Drucker (gecacht je device_uri).

    Mit resolved_uri (aus dem gemeinsamen ippfind-Suchlauf) wird ipptool
    direkt aufgerufen; sonst wie bisher ippfind + ipptool je Ziel.
    """
    if device_uri in _ipp_cache:
        return _ipp_cache[device_uri]
    info = _ipp_lookup_uncached(resolved_uri or device_uri)
    _ipp_cache[device_uri] = info
    return info


def _ipp_lookup_uncached(device_uri: str) -> _IppInfo | None:
    cmd = _ipptool_cmd(device_uri)
    if cmd is None:
        log.debug(f"    IPP: unsupported URI: {device_uri!r}")
        return None
    if not _check_ipp_tools(cmd):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        _check_ipp_tools(cmd)
        log.debug(f"    IPP: {cmd[0]} not found")
        return None
    except subprocess.TimeoutExpired:
        log.debug(f"    IPP: timeout for {device_uri!r}")
        return None
    except Exception as e:
        log.debug(f"    IPP: error for {device_uri!r}: {e}")
        return None

    resolved = device_uri if cmd[0] == "ipptool" else None
    attrs: dict[str, list[str]] = {}
    for line in r.stdout.splitlines():
        m = _IPPTOOL_ATTR_RE.match(line)
        if m and m.group(1) in _IPP_ATTRS and m.group(1) not in attrs:
            attrs[m.group(1)] = [v.strip() for v in m.group(2).split(",")]
            continue
        m = _RESOLVED_URI_RE.match(line)
        if m and resolved is None:
            resolved = m.group(1)
    log.debug(f"    IPP: resolved to {resolved!r}")
    return _IppInfo(resolved, attrs)


def _caps_from_ipp(
    attrs: dict[str, list[str]],
) -> tuple[str | None, str | None, str] | None:
    slot  = next((v for v in attrs.get("media-source-supported", [])
                  if _matches(v, _SLOT_KEYS)), None)
    mtype = next((v for v in attrs.get("media-type-supported", [])
                  if _matches(v, _TYPE_KEYS)), None)
    msize = next((v for v in attrs.get("media-supported", [])
                  if _matches(v, _SIZE_KEYS) or "120x120" in v), None)

    log.debug(f"    IPP: source={slot!r} type={mtype!r} media={msize!r}")
    if slot is None and mtype is None:
        return None
    # InputSlot/MediaType im PPD-Format; media= akzeptiert PWG-Namen direkt
    return (
        _ppdize(slot) if slot else None,
        _ppdize(mtype) if mtype else None,
        msize or "120x120mm",
    )


def _query_via_ipp(
    device_uri: str,
) -> tuple[str | None, str | None, str] | None:
    """
    Fragt die Disc-Fähigkeiten direkt beim Drucker per IPP ab.

    Für temporäre Ziele (nur in `lpstat -e`) existiert noch keine
    CUPS-Warteschlange und damit keine PPD — lpoptions und die CUPS-HTTP-API
    liefern dann nichts.  Die IPP-Attribute media-source-supported,
    media-type-supported und media-supported sind die Quelle, aus der CUPS
    später selbst die PPD der temporären Queue erzeugt.
    """
    info = _ipp_lookup(device_uri)
    if info is None:
        return None
    return _caps_from_ipp(info.attrs)


# ── Dubletten: temporäres Ziel ↔ feste Queue ──────────────────────────────────

_NETWORK_SCHEMES = frozenset({"ipp", "ipps", "http", "https", "socket", "lpd"})


def _device_keys(uri: str | None) -> set[tuple[str, str]]:
    """
    Vergleichsschlüssel für ein Gerät, ohne Netzwerkauflösung:
      ("host", "e1f4f9000000.local")      aus ipp://, ipps://, socket:// …
      ("dnssd", "canon ts700 series")     Dienstname aus dnssd://
    """
    if not uri:
        return set()
    try:
        parts = urlsplit(uri)
    except ValueError:
        return set()
    scheme = parts.scheme.lower()
    if scheme == "dnssd":
        m = _DNSSD_HOST_RE.match(unquote(parts.netloc))
        return {("dnssd", m.group("name").lower())} if m else set()
    if scheme not in _NETWORK_SCHEMES:
        return set()     # usb://Canon/… o. ä.: "Host" ist kein Netzwerkname
    try:
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return set()
    if not host or host in ("localhost", "127.0.0.1", "::1"):
        return set()
    return {("host", host)}


def _find_permanent_twin(
    dest: "_Dest",
    permanent: dict[tuple[str, str], str],
    resolved_uri: str | None = None,
) -> str | None:
    """
    Name der festen Queue, die auf dasselbe Gerät zeigt wie das temporäre
    Ziel — oder None, wenn keine passt bzw. kein Vergleich möglich ist
    (dann wird das Ziel angezeigt: lieber doppelt als verschwunden).
    resolved_uri stammt aus dem gemeinsamen ippfind-Suchlauf.
    """
    if not permanent or not dest.device_uri:
        return None
    keys = _device_keys(dest.device_uri) | _device_keys(resolved_uri)
    for k in sorted(keys):
        if k in permanent:
            return permanent[k]
    return None


def _dnssd_service(uri: str | None) -> tuple[str, str] | None:
    """dnssd://Name._ipps._tcp.local/… → ("_ipps._tcp", "name")."""
    if not uri or not uri.lower().startswith("dnssd:"):
        return None
    m = _DNSSD_HOST_RE.match(unquote(urlsplit(uri).netloc))
    return (m.group("regtype").lower(), m.group("name").lower()) if m else None


def _browse_ipp_services() -> dict[tuple[str, str], str] | None:
    """
    EIN ippfind-Suchlauf über _ipp._tcp und _ipps._tcp.

    Rückgabe: {(regtype, dienstname_klein): aufgelöste ipp(s)://-URI}
    oder None, wenn ippfind fehlt bzw. der Suchlauf fehlschlägt.
    ({service_regtype} kennt ippfind 2.4.20 nicht → aus dem URI-Schema.)
    """
    cmd = ["ippfind", "-T", "3", "_ipp._tcp", "_ipps._tcp",
           "-x", "printf", "%s\\t%s\\n", "{service_name}", "{}", ";"]
    if not _check_ipp_tools(cmd):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception as e:
        log.debug(f"    ippfind browse failed: {e}")
        return None
    services: dict[tuple[str, str], str] = {}
    for line in r.stdout.splitlines():
        name, sep, uri = line.rpartition("\t")
        scheme = uri.split(":", 1)[0].lower()
        if not sep or not name or scheme not in ("ipp", "ipps"):
            continue
        services.setdefault((f"_{scheme}._tcp", name.lower()), uri)
    log.debug(f"  ippfind browse: {len(services)} service(s)")
    return services


def _resolve_temporary(dests: list["_Dest"]) -> dict[str, str]:
    """device_uri → aufgelöste ipp(s)-URI für temporäre Ziele (sofern möglich)."""
    resolved: dict[str, str] = {}
    need_browse = False
    for d in dests:
        if not d.device_uri:
            continue
        if d.device_uri.split(":", 1)[0].lower() in ("ipp", "ipps"):
            resolved[d.device_uri] = d.device_uri
        elif _dnssd_service(d.device_uri):
            need_browse = True
    if not need_browse:
        return resolved
    services = _browse_ipp_services() or {}
    for d in dests:
        key = _dnssd_service(d.device_uri)
        if key and key in services:
            resolved[d.device_uri] = services[key]
        elif key:
            log.debug(f"  {d.name}: not found in ippfind browse")
    return resolved


def _prefetch_ipp(dests: list["_Dest"], resolved: dict[str, str]) -> None:
    """IPP-Abfragen der verbliebenen temporären Ziele parallel vorab."""
    jobs = [d for d in dests if d.device_uri]
    if not jobs:
        return
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
        list(pool.map(
            lambda d: _ipp_lookup(d.device_uri, resolved.get(d.device_uri)),
            jobs,
        ))


# ── Orchestrierung ────────────────────────────────────────────────────────────

def _detect_caps(
    name: str,
    device_uri: str | None = None,
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
      5. Nur für temporäre Ziele (device_uri gesetzt): noch keine Queue,
         also auch keine PPD    → IPP-Attribute direkt vom Drucker

    Rückgabe: (caps | None, Quelle)
      caps   = (input_slot, media_type, page_size) oder None
      Quelle = "ppd" | "lpoptions" | "cups-http" | "ipp"
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
                f"    PPD exists but is not readable "
                f"(cups group?) → lpoptions"
            )
    else:
        log.debug(f"    No PPD for {name!r} (driverless?) → lpoptions")

    result = _query_via_lpoptions(name)
    if result is not None:
        return result, "lpoptions"

    log.debug(f"    lpoptions: no result → trying CUPS HTTP API")
    result = _query_via_cups_http(name)
    if result is not None or not device_uri:
        return result, "cups-http"

    log.debug(f"    CUPS HTTP: no result → IPP query {device_uri!r}")
    return _query_via_ipp(device_uri), "ipp"


# ── lpstat ───────────────────────────────────────────────────────────────────

class _Dest(NamedTuple):
    name: str
    temporary: bool = False         # nur via `lpstat -e` gefunden
    device_uri: str | None = None   # aus `lpstat -l -e` (falls verfügbar)


def _run_lpstat(args: list[str], *, check: bool = False) -> str | None:
    """Führt lpstat aus; None bei Fehler (bzw. Exit-Code ≠ 0 wenn check)."""
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    try:
        r = subprocess.run(
            ["lpstat", *args], capture_output=True, text=True,
            timeout=6, env=env,
        )
    except FileNotFoundError:
        log.error("lpstat not found; is CUPS installed?")
        return None
    except subprocess.TimeoutExpired:
        log.error(f"lpstat {' '.join(args)}: timeout")
        return None
    except Exception as e:
        log.error(f"lpstat {' '.join(args)}: error: {e}")
        return None
    if check and r.returncode != 0:
        log.warning(
            f"lpstat {' '.join(args)} failed (rc={r.returncode}): "
            f"{r.stderr.strip()}"
        )
        return None
    return r.stdout


def _parse_lpstat_p(out: str) -> list[str]:
    """`lpstat -p` → Queue-Namen ("printer <name> is …")."""
    names: list[str] = []
    for line in out.splitlines():
        if line.startswith("printer "):
            p = line.split()
            if len(p) >= 2:
                names.append(p[1])
    return names


def _parse_lpstat_e(out: str) -> list[tuple[str, str | None]]:
    """
    `lpstat -e` bzw. `lpstat -l -e` → [(name, device_uri | None)].

    Kurzform: eine Zeile pro Ziel ("name" oder "name/instanz").
    Langform: "name typ printer-uri device-uri".
    Instanzen ("name/instanz") werden auf den Basisnamen reduziert: sie
    teilen sich Queue und Gerät, unterscheiden sich nur in Default-Optionen,
    und disc-printer setzt alle relevanten Optionen ohnehin explizit.
    """
    result: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for line in out.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        name = tokens[0].split("/", 1)[0]
        if not name or name in seen:
            continue
        seen.add(name)
        uri = tokens[3] if len(tokens) >= 4 and tokens[3] != "none" else None
        result.append((name, uri))
    return result


def _merge_destinations(
    p_names: list[str],
    e_entries: list[tuple[str, str | None]],
) -> list[_Dest]:
    """
    Vereinigt `lpstat -p` und `lpstat -e` ohne Duplikate.

    Reihenfolge: zuerst die Queues aus -p (bisheriges Verhalten), danach
    Ziele, die nur -e kennt — das sind die temporären/treiberlosen.
    """
    dests: list[_Dest] = []
    seen: set[str] = set()
    e_uris = dict(e_entries)
    for name in p_names:
        if name not in seen:
            seen.add(name)
            dests.append(_Dest(name, device_uri=e_uris.get(name)))
    for name, uri in e_entries:
        if name not in seen:
            seen.add(name)
            dests.append(_Dest(name, temporary=True, device_uri=uri))
    return dests


def _lpstat_destinations() -> list[_Dest]:
    p_out = _run_lpstat(["-p"])
    p_names = _parse_lpstat_p(p_out) if p_out is not None else []

    # -e fehlt in alten CUPS-Versionen (< 2.2) → dann nur -p wie bisher
    e_out = _run_lpstat(["-l", "-e"], check=True)
    if e_out is None:
        log.info("lpstat -e not available → permanent queues only (lpstat -p)")
        return _merge_destinations(p_names, [])
    return _merge_destinations(p_names, _parse_lpstat_e(e_out))


def _lpstat_names() -> list[str]:
    return [d.name for d in _lpstat_destinations()]


# ── Öffentliche API ───────────────────────────────────────────────────────────

def detect_disc_printers() -> list[DiscPrinter]:
    """
    Gibt alle CUPS-Drucker zurück, die Disc-Druck unterstützen.

    Erkennung je Drucker: PPD-Parser zuerst, dann lpoptions-Fallback.
    Nur Drucker mit nachgewiesenem InputSlot oder MediaType für Discs
    erscheinen in der Liste — die GUI zeigt damit automatisch nur
    kompatible Geräte an.
    """
    log.info("=== Printer detection started ===")
    t0 = time.monotonic()
    dests = _lpstat_destinations()
    log.info(f"CUPS printers found: {[d.name for d in dests] or '(none)'}")
    temp = [d.name for d in dests if d.temporary]
    if temp:
        log.info(f"  of which temporary/driverless (lpstat -e only): {temp}")

    _ipp_cache.clear()
    permanent: dict[tuple[str, str], str] = {}
    for d in dests:
        if not d.temporary:
            for k in _device_keys(d.device_uri):
                permanent.setdefault(k, d.name)

    # Temporäre Ziele: erst EIN Suchlauf + Zwillinge aussortieren, dann nur
    # für die übrigen ipptool — parallel.
    temps = [d for d in dests if d.temporary]
    hidden: set[str] = set()
    if temps:
        resolved = _resolve_temporary(temps)
        for d in temps:
            twin = _find_permanent_twin(d, permanent, resolved.get(d.device_uri or ""))
            if twin is not None:
                hidden.add(d.name)
                log.info(
                    f"  ⊘ {d.name}: hidden; permanent queue {twin!r} "
                    f"points to the same device"
                )
        _prefetch_ipp([d for d in temps if d.name not in hidden], resolved)

    found: list[DiscPrinter] = []
    for dest in dests:
        name = dest.name
        if name in hidden:
            continue
        log.info(f"  Checking {name!r} …")
        result, source = _detect_caps(
            name, dest.device_uri if dest.temporary else None)
        if result:
            slot, mtype, msize = result
            ppd_path = str(_find_ppd(name) or f"/etc/cups/ppd/{name}.ppd")
            dp = DiscPrinter(name, ppd_path, slot, mtype, msize,
                             temporary=dest.temporary)
            found.append(dp)
            log.info(
                f"  ✓ {name} [{source}]: "
                f"InputSlot={slot!r}  MediaType={mtype!r}  media={msize!r}"
            )
        else:
            log.info(f"  ✗ {name}: no disc printing detected")

    log.info(
        f"Disc-capable printers: {len(found)}  "
        f"(took {time.monotonic() - t0:.1f} s)"
    )
    return found
