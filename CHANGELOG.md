# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Flatpak-Paket (2026-04-25)
- `flatpak/de.haku.disc-printer.yml`: Manifest für GNOME Platform 47;
  Module: python-numpy (manylinux wheel), cups-client-tools (CUPS 2.4.11,
  nur lp/lpstat/lpoptions), disc-printer (aus GitHub-Tag v0.1.0)
- `flatpak/de.haku.disc-printer.desktop`, `.metainfo.xml`, `.svg`: Desktop-
  Integration, AppStream-Metadaten, App-Icon
- `flatpak/disc-printer.flatpak`: Fertig gebautes Single-File-Bundle (13 MB)
- `flatpak/de.haku.disc-printer.flatpakref`: Referenzdatei für Flatpak-Install

### Fixed

#### Gettext-Shadowing in _on_detection_done (2026-04-25)
- `window.py`: Loop-Variable `_` in `for _ in range(n):` durch `_i` ersetzt,
  da `_` die gettext-Funktion überschrieb und `_("...")` im Rumpf abstürzte
  (TypeError: 'int' object is not callable) wenn keine Disc-Drucker gefunden

#### Helligkeit & Kontrast pro Bild-Element (2026-04-25)
- `model.py`: `ImageElement` erhält `brightness` (float, default 1.0) und
  `contrast` (float, default 1.0) als Konstruktor-Parameter; interne Felder
  `_adj_surf`, `_adj_b`, `_adj_c` für Render-Cache
- `canvas.py`: Modulhelferfunktion `_apply_bc(surface, brightness, contrast)` via
  numpy — un-premultipliziert, wendet Kontrast `(x-0.5)*c+0.5` dann Helligkeit
  `x*b` an, re-premultipliziert, gibt neue Cairo-Surface zurück; Cache-Hit
  wenn `brightness`/`contrast` unverändert
- `canvas.py`: `_draw_image_elem` verwendet gecachte adjustierte Surface falls
  `brightness != 1.0` oder `contrast != 1.0`; Originaloberfläche bleibt
  unverändert
- `file_format.py`: `brightness` und `contrast` werden in `design.json`
  gespeichert und rückwärtskompatibel geladen (fehlende Keys → 1.0)
- `window.py`: Pro Bild-Zeile zwei neue Slider „Helligkeit:" und „Kontrast:"
  (0.0–2.0, Anzeige als %, Reset-Button auf 100 %); Undo/Redo mit 600 ms
  Debounce (wie Opazität); `_img_rows`-Tupel auf 9 Elemente erweitert;
  `_on_img_brightness`, `_on_img_contrast`, `_on_reset_brightness`,
  `_on_reset_contrast` Handler; Duplizieren kopiert `brightness`/`contrast`

#### Undo/Redo-System (2026-04-25)
- `history.py`: neue Datei mit `Command` (description, undo_fn, redo_fn) und
  `History` (Undo/Redo-Stack, max. 50 Einträge, `on_change`-Callback)
- `window.py`: `History`-Instanz in `__init__`; Undo/Redo-Buttons in HeaderBar
  (initial deaktiviert, Tooltip zeigt Aktionsname); `Gtk.EventControllerKey`
  für Strg+Z (Undo) und Strg+Y / Strg+Shift+Z (Redo)
- `window.py`: `_on_history_changed()` aktualisiert Buttons und Tooltips
- `window.py`: `_rebuild_panel()` baut `_elem_list` und `_img_list` vollständig
  aus dem Model-Zustand neu (robuste Basis für Undo/Redo bei Add/Delete/Duplicate)
- `window.py`: `_find_img_row()` sucht Tupel in `_img_rows` nach Identität
- `canvas.py`: `on_transform_cb` / `on_img_zoom_cb` Callbacks; `_on_drag_end`
  ruft `on_transform_cb(elem, dict(drag_start), action)` auf; `_on_scroll` ruft
  `on_img_zoom_cb(img, old_sx, old_sy, new_sx, new_sy)` auf
- `window.py`: `_on_canvas_transform()` erstellt Command für Bewegen/Drehen/
  Skalieren von ImageElement und TextElement beim Loslassen der Maus
- `window.py`: `_on_canvas_zoom()` erstellt Command für Mausrad-Zoom mit
  600 ms Debounce (wie Opazitäts-Slider)
- `window.py`: `_apply_loaded_design()` bricht laufende Debounce-Timer ab und
  ruft `_history.clear()` auf → Stacks werden beim Öffnen geleert
- Alle undoable Aktionen: Hintergrundfarbe, Hintergrundbild laden/entfernen,
  Hub-Größe, Text hinzufügen/bearbeiten/löschen/duplizieren/sperren/sichtbar,
  Bild hinzufügen/löschen/duplizieren/sperren/sichtbar/z-Order/flip/opacity/
  Bewegen/Skalieren/Drehen/Zoom; Signalblocking-Flags verhindern rekursive
  Command-Erstellung beim programmatischen Setzen von Widgets

#### Element-Features: Sperren, Sichtbarkeit, Duplizieren (2026-04-25)
- `model.py`: `TextElement` und `ImageElement` erhalten `locked` (bool, default False)
  und `visible` (bool, default True) als Instanzvariablen
- `file_format.py`: `locked` und `visible` werden in `design.json` gespeichert und
  beim Laden rückwärtskompatibel wiederhergestellt (fehlende Keys → Defaults)
- `canvas.py`: Unsichtbare Elemente werden beim Rendern und beim Drucken übersprungen;
  Treffertest (`_hit_any`) ignoriert unsichtbare Elemente
- `canvas.py`: Gesperrte Elemente können selektiert werden, aber Drag (Move/Scale/Rotate)
  und Mausrad-Zoom werden blockiert; Handles zeigen grau gestrichelten Rahmen ohne
  interaktive Anfasser; Text-Selektion erscheint ebenfalls grau
- `canvas.py`: `render_for_print()` rendert unsichtbare Elemente nicht mit
- `window.py`: Panel-Zeile pro Element enthält jetzt Auge-Icon (Sichtbarkeit umschalten),
  Schloss-Icon (Sperren/Entsperren) und Duplizieren-Button (edit-copy-symbolic)
- `window.py`: Unsichtbare Elemente erscheinen im Panel mit 50 % Opazität
- `window.py`: Duplizieren erstellt Kopie mit +3 mm Versatz, nächstem freiem z-Wert,
  `locked=False` und `visible=True`; `ImageElement` teilt die Surface (kein Neu-Laden)

### Changed
- Canvas drag-and-drop now creates `ImageElement` instead of setting legacy background image
- Background section hint text updated to clarify its limitations (position & zoom only)

### Fixed
- Selection handles not visible after clicking on an image element:
  - Added robust `_draw_hw` fallback in `_draw` step 7 (recomputes from surface dimensions
    if `_draw_image_elem` hasn't set it yet)
  - Added `try/except` around `_draw_img_handles` with error logging

## [0.1.0] – 2026-04-24

### Added

#### Bild-Elemente mit vollem Transformations-Support (2026-04-24 19:18)
- `model.py`: neues `ImageElement` mit den Feldern `surface`, `x`, `y`, `scale_x`,
  `scale_y`, `rotation` (Grad), `opacity`, `z`, `flip_h`, `flip_v`
- `model.py`: `DesignState.images` (Liste), `selected_image` und `all_sorted()`
  (sortiert `ImageElement` + `TextElement` gemeinsam nach z-Wert)
- `canvas.py`: `ImageElement`-Rendering via Cairo (Rotation, Skalierung, Flip,
  Opazität, bilinearer Filter)
- `canvas.py`: 9-Handle-System für das selektierte Bild:
  4 Eckpunkte = proportionale Skalierung, 4 Seitenmittelpunkte = Achsenskalierung,
  1 Rotationskreis über der Oberkante
- `canvas.py`: Drag-Modi `move` / `scale` / `rotate` für `ImageElement`
- `canvas.py`: Mausrad zoomt das aktuell selektierte Bild (Strg nicht nötig)
- `window.py`: Panel „Bild-Elemente" mit Thumbnail, Opazitäts-Slider, z-Order-Buttons
  (↑/↓), Löschen-Button
- `window.py`: Spiegeln-Buttons „↔ H spiegeln" / „↕ V spiegeln" (eingeblendet wenn
  ein Bild selektiert ist)
- `file_format.py`: Format-Version 2 – `ImageElement`s werden als `img_0.png` …
  `img_N.png` in die ZIP-Datei eingebettet; `flip_h`/`flip_v` im JSON gespeichert;
  Hintergrundbild als separater `bg_image`-Schlüssel (`bg.png`)

#### Design Speichern & Laden (2026-04-24 18:46)
- `file_format.py`: neue Datei mit `save()` und `load()` für das `.discprint`-Format
  (ZIP-Datei: `design.json` + eingebettete PNG-Bilder); Rückwärtskompatibilität mit v1
- `file_format.py`: `DEFAULT_DIR = ~/Dokumente/DiscPrinter/` (wird beim Start
  automatisch angelegt)
- `window.py`: „Speichern"- und „Öffnen"-Buttons in der `HeaderBar`
- `window.py`: `Gtk.FileDialog` mit `.discprint`-Filter und Standardpfad `DEFAULT_DIR`
- `window.py`: `_apply_loaded_design()` lädt den kompletten Design-Zustand in die
  laufende GUI (in-place Update, kein Neustart nötig)

### Changed
- `model.py`: `TextElement` erhält `z`-Parameter für die Ebenensortierung
- `canvas.py`: alle Ebenen (`ImageElement` + `TextElement`) werden nach z-Wert
  sortiert gerendert (Bilder vor Text bei gleichem z)
- `window.py`: `_apply_loaded_design()` aktualisiert auch `images`-Liste und
  `_img_rows`

[Unreleased]: https://github.com/example/disc-printer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/example/disc-printer/releases/tag/v0.1.0
