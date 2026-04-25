from pathlib import Path

DISC_MM      = 120.0
PRINTABLE_MM = 118.0
HUB_LARGE_MM = 50.0
HUB_SMALL_MM = 33.0
PREVIEW_PX   = 420

# Pixels-per-mm bei 300 DPI (Referenz für Schriftgrößen-Skalierung)
PRINT_PPM = 300.0 / 25.4          # ≈ 11.81 px/mm
PRINT_PX  = round(DISC_MM * PRINT_PPM)  # 1417 px pro Achse bei 300 DPI

_PRINT_SAT      = 1.20   # Sättigungsboost für Druckausgabe
_PRINT_CONTRAST = 1.10   # Kontrastboost für Druckausgabe

APP_ID   = "de.haku.disc-printer"
LOG_FILE = Path.home() / "disc-printer.log"
