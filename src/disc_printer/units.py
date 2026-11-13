"""Maß-Umrechnung für die Anzeige (ohne GTK, damit testbar)."""
from __future__ import annotations

MM_PER_INCH = 25.4


def mm_to_inch(mm: float) -> float:
    """Millimeter in Zoll umrechnen."""
    return mm / MM_PER_INCH


def dimension_args(mm: float) -> dict[str, float]:
    """Werte für Maß-Texte mit den benannten Platzhaltern ``%(mm)`` und ``%(inch)``."""
    return {"mm": mm, "inch": mm_to_inch(mm)}


def format_dimension(template: str, mm: float) -> str:
    """Übersetzten Maß-Text füllen, z. B. ``"Ø %(mm).0f mm / %(inch).2f in"``."""
    return template % dimension_args(mm)
