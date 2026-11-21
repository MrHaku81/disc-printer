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


def shown_value(mm: float, unit: str) -> float:
    """Wert so, wie ihn die Anzeige in ``unit`` zeigt (gerundet wie format_number).

    Hinweis und Hervorhebung der Voreinstellungen vergleichen diese Werte: was
    in der gewählten Einheit gleich angezeigt wird, gilt als gleich.
    """
    value = mm if unit == "mm" else mm_to_inch(mm)
    return float(f"{value:.{_DIGITS[unit]}f}")


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


def parse_number(text: str, unit: str, grid: float = 0.5) -> float | None:
    """Eingabe in der gewählten Einheit lesen; Ergebnis in mm (0,1 mm genau).

    Zoll: Liegt ein Vielfaches von ``grid`` mm (Raster der Regler) auf
    demselben angezeigten Zoll-Wert, gilt dieses („4,65 in“ → 118,0 mm statt
    118,1 mm); sonst der exakte Wert auf 0,1 mm. So entspricht eine Eingabe,
    die wie eine Voreinstellung oder Schwelle aussieht, ihr auch in mm.

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
    if unit == "mm":
        return round(value, 1)
    mm = value * MM_PER_INCH
    on_grid = snap(mm, grid)
    if shown_value(on_grid, "in") == shown_value(mm, "in"):
        return on_grid
    return round(mm, 1)


def snap(mm: float, step: float) -> float:
    """Auf das Raster ``step`` runden (Regler)."""
    return round(round(mm / step) * step, 1)


def clamp(mm: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, mm))
