"""Einzige Quelle der Versionsnummer.

pyproject.toml liest sie hier (hatch, ``dynamic = ["version"]``), ebenso
``make pot``. Das Flatpak kopiert ``src/`` und hat damit dieselbe Datei; AUR
und pipx bauen ein Wheel daraus; der Start aus dem Quelltext liest sie direkt.
Nicht über importlib.metadata: Im Flatpak gibt es keine dist-info, und beim
Start aus dem Quelltext fände es eine systemweit installierte andere Version.
"""
__version__ = "0.3.0"
