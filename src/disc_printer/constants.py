DISC_MM      = 120.0
PREVIEW_PX   = 420

# Druckbereich (Innen- und Außendurchmesser) in mm; einstellbar im Bereich
# „Druckbereich“ unter der Vorschau, gespeichert im Design.
INNER_MIN_MM = 18.0
INNER_MAX_MM = 50.0
OUTER_MIN_MM = 70.0
OUTER_MAX_MM = 120.0
SLIDER_STEP_MM = 0.5          # Regler; Zahlenfelder sind auf 0,1 mm genau

# Voreinstellungen: (innen, außen). „Neues Design“ und alte Dateien ohne
# Außendurchmesser nutzen „Standard“.
PRESET_STANDARD = (50.0, 118.0)
PRESET_FULL     = (33.0, 118.0)
DEFAULT_INNER_MM, DEFAULT_OUTER_MM = PRESET_STANDARD

# Hinweis (keine Sperre), wenn der Druck den üblichen bedruckbaren Bereich
# verlässt: außen über 118 mm liegt der unbeschichtete Rand von 12-cm-Rohlingen,
# innen unter 21 mm der Stapelring bzw. das 15-mm-Loch (hub-bedruckbare
# Rohlinge beginnen je nach Marke bei etwa 21–25 mm).
HINT_OUTER_MAX_MM = 118.0
HINT_INNER_MIN_MM = 21.0

# Hintergrundbild wird fest auf diesen Durchmesser eingepasst (unabhängig vom
# eingestellten Druckbereich, damit gespeicherte Designs gleich aussehen).
BG_FIT_MM = 118.0

# Pixels-per-mm bei 300 DPI (Referenz für Schriftgrößen-Skalierung)
PRINT_PPM = 300.0 / 25.4          # ≈ 11.81 px/mm
PRINT_PX  = round(DISC_MM * PRINT_PPM)  # 1417 px pro Achse bei 300 DPI

_PRINT_SAT      = 1.20   # Sättigungsboost für Druckausgabe
_PRINT_CONTRAST = 1.10   # Kontrastboost für Druckausgabe

APP_ID   = "de.haku.disc-printer"
