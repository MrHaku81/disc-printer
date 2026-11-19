"""Speicherort für .discprint-Designs.

Der Ordner liegt im Dokumente-Verzeichnis des Systems (XDG, über GLib), nicht
fest unter ~/Dokumente. Er ist unabhängig von der App-Sprache.

Alle Funktionen nehmen ``home`` und ``documents`` optional entgegen, damit die
Tests ohne echtes Home-Verzeichnis und ohne echte user-dirs.dirs laufen.
"""
from __future__ import annotations

from pathlib import Path

from ._log import log

APP_SUBDIR = "DiscPrinter"
# Bis 0.1.2 fest verdrahtet; wird nur noch gelesen, nie neu angelegt.
LEGACY_DOCUMENTS_NAME = "Dokumente"

_UNSET = object()


def _system_documents_dir() -> Path | None:
    from gi.repository import GLib

    d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
    return Path(d) if d else None


def documents_dir(home: Path | None = None, documents=_UNSET) -> Path | None:
    """Dokumente-Ordner laut System, oder None, wenn keiner festgelegt ist.

    xdg-user-dirs meldet das Home-Verzeichnis selbst, wenn der Eintrag
    deaktiviert ist; das zählt ebenfalls als "kein Dokumente-Ordner".
    """
    home = Path.home() if home is None else Path(home)
    docs = _system_documents_dir() if documents is _UNSET else documents
    if not docs:
        return None
    docs = Path(docs)
    if docs == home:
        return None
    return docs


def _has_files(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def design_dir(home: Path | None = None, documents=_UNSET) -> Path:
    """Ordner für Designs. Legt nichts an.

    Reihenfolge:
    1. <Dokumente>/DiscPrinter, Rückfall ~/DiscPrinter ohne Dokumente-Ordner
    2. ~/Dokumente/DiscPrinter, falls er Dateien enthält und der neue Ordner
       noch nicht existiert (Abwärtskompatibilität bis 0.1.2)
    """
    home = Path.home() if home is None else Path(home)
    docs = documents_dir(home, documents)
    new = (docs if docs is not None else home) / APP_SUBDIR
    legacy = home / LEGACY_DOCUMENTS_NAME / APP_SUBDIR
    if new != legacy and not new.exists() and _has_files(legacy):
        return legacy
    return new


def open_dialog_folder(home: Path | None = None, documents=_UNSET) -> Path:
    """Startordner für den Öffnen-Dialog; legt nichts an."""
    home = Path.home() if home is None else Path(home)
    docs = documents_dir(home, documents)
    target = design_dir(home, docs)
    if target.is_dir():
        return target
    if docs is not None and docs.is_dir():
        return docs
    return home


def ensure_design_dir(home: Path | None = None, documents=_UNSET) -> Path:
    """Ordner für den Speichern-Dialog; legt ihn bei Bedarf an.

    Schlägt das Anlegen fehl, wird der Öffnen-Startordner verwendet.
    """
    home = Path.home() if home is None else Path(home)
    docs = documents_dir(home, documents)
    target = design_dir(home, docs)
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError as e:
        log.warning(f"Cannot create design folder {target}: {e}")
        return open_dialog_folder(home, docs)
