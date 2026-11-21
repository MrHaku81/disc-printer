"""Maße anzeigen und eingeben (ohne GTK, damit testbar).

Intern ist alles in Millimetern; die Einheit (mm oder Zoll) betrifft nur die
Anzeige und die Eingabe. Das Dezimalzeichen folgt der Sprache der Oberfläche,
nicht der Einheit.
"""
from __future__ import annotations

MM_PER_INCH = 25.4
UNITS = ("mm", "in")

# Sprachen der Oberfläche mit Dezimalkomma; alle anderen mit Punkt. Arabisch
# und Persisch: die App zeigt lateinische Ziffern, dazu passt der Punkt.
_COMMA_LANGS = frozenset({
    "bg", "cs", "da", "de", "el", "es", "fi", "fr", "hr", "hu", "id", "it",
    "nb", "nl", "pl", "pt", "ro", "ru", "sk", "sr", "sv", "tr", "uk", "vi",
})

# Nachkommastellen je Einheit: 0,1 mm bzw. 0,01 in
_DIGITS = {"mm": 1, "in": 2}


def mm_to_inch(mm: float) -> float:
    """Millimeter in Zoll umrechnen."""
    return mm / MM_PER_INCH


def decimal_sep(lang: str) -> str:
    """Dezimalzeichen für die Sprache der Oberfläche."""
    return "," if lang in _COMMA_LANGS else "."


def format_number(mm: float, unit: str, lang: str, trim: bool = False) -> str:
    """Wert in der gewählten Einheit, ohne Einheitszeichen.

    mm mit einer, Zoll mit zwei Nachkommastellen. ``trim`` lässt bei mm eine
    Null nach dem Komma weg („5“ statt „5,0“).
    """
    value = mm if unit == "mm" else mm_to_inch(mm)
    text = f"{value:.{_DIGITS[unit]}f}"
    if trim and unit == "mm" and text.endswith(".0"):
        text = text[:-2]
    return text.replace(".", decimal_sep(lang))


def parse_number(text: str, unit: str) -> float | None:
    """Eingabe in der gewählten Einheit lesen; Ergebnis in mm (0,1 mm genau).

    Komma und Punkt (auch das arabische Dezimalzeichen) gelten beide als
    Dezimalzeichen; Leerzeichen und ein angehängtes „mm“/„in“/„"“ werden
    ignoriert. Ungültig: ``None``.
    """
    t = text.strip().replace(" ", "").replace(" ", "")
    for suffix in ("mm", "in", "″", '"'):
        if t.lower().endswith(suffix):
            t = t[: -len(suffix)]
            break
    t = t.replace("٫", ".").replace(",", ".")
    if not t or t.count(".") > 1:
        return None
    try:
        value = float(t)
    except ValueError:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    mm = value if unit == "mm" else value * MM_PER_INCH
    return round(mm, 1)


def snap(mm: float, step: float) -> float:
    """Auf das Raster ``step`` runden (Regler)."""
    return round(round(mm / step) * step, 1)


def clamp(mm: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, mm))
