"""Wie wurde Disc Printer installiert? (für „Nach neuer Version suchen“)

Drei Fälle, jeweils mit eigenem Hinweis zum Aktualisieren:

- ``"flatpak"``: ``/.flatpak-info`` gibt es nur in der Flatpak-Sandbox.
- ``"pacman"``: Die pacman-Datenbank (``/var/lib/pacman/local/<paket>/files``)
  führt genau die Datei, aus der das Programm gerade läuft. Das trifft auch
  dann richtig, wenn daneben eine pipx- oder Quelltext-Fassung liegt. Das
  Paket kommt aus dem AUR; welcher AUR-Helfer benutzt wird, ist nicht
  erkennbar.
- ``"other"``: alles andere (pipx, Quelltext).

Nur Dateizugriffe, kein Unterprozess, kein Netz.
"""
from __future__ import annotations

from pathlib import Path

FLATPAK_INFO = Path("/.flatpak-info")
PACMAN_LOCAL = Path("/var/lib/pacman/local")
PACKAGE      = "disc-printer"


def _module_file() -> Path:
    from . import __file__ as init_file
    return Path(init_file)


def _owned_by_pacman(module_file: Path, pacman_local: Path) -> bool:
    try:
        wanted = str(module_file.resolve()).lstrip("/")
        # Einträge heißen <name>-<pkgver>-<pkgrel>; nur genau dieses Paket
        dirs = [d for d in pacman_local.glob(f"{PACKAGE}-*-*")
                if d.name.rsplit("-", 2)[0] == PACKAGE]
    except OSError:
        return False
    for d in dirs:
        try:
            with open(d / "files", encoding="utf-8", errors="replace") as f:
                if any(line.rstrip("\n") == wanted for line in f):
                    return True
        except OSError:
            continue
    return False


def install_kind(
    module_file: Path | None = None,
    flatpak_info: Path = FLATPAK_INFO,
    pacman_local: Path = PACMAN_LOCAL,
) -> str:
    """``"flatpak"``, ``"pacman"`` oder ``"other"``."""
    if flatpak_info.exists():
        return "flatpak"
    if _owned_by_pacman(module_file or _module_file(), pacman_local):
        return "pacman"
    return "other"
