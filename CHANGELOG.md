# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Neues Design
- Knopf „Neues Design“ in der Kopfleiste (links vor „Öffnen“): setzt das Design
  auf den Zustand eines frischen Starts zurück (Hintergrund, Bild- und
  Text-Elemente, Hub-Größe, Undo/Redo-Verlauf). Druckerauswahl und Sprache
  bleiben; laufende Regler-Timer werden verworfen
- Ungespeicherte Änderungen werden erkannt (Fingerabdruck des Designs, auch für
  Änderungen ohne Undo-Eintrag wie den Hintergrund-Zoom). Dann fragt die App
  vorher nach: Abbrechen / Verwerfen / Speichern … (nach erfolgreichem
  Speichern wird zurückgesetzt, bei Fehler oder Abbruch nicht)
- Dieselbe Rückfrage bei „Öffnen“ (vor dem Dateidialog) und beim Schließen
  des Fensters, nur bei ungespeicherten Änderungen. Abbrechen lässt das
  Fenster offen; „Speichern …“ schließt bzw. öffnet erst nach erfolgreichem
  Speichern. Alle Wege des Schließens (Titelleiste, Alt+F4, Taskleiste) laufen
  über `close-request`; ein eigenes Tastenkürzel zum Beenden gibt es nicht
- Sprachwechsel behält das Design: Die Oberfläche wird im selben Fenster neu
  aufgebaut statt in einem neuen. Hintergrund, Bilder, Texte, Hub, Auswahl,
  Undo/Redo-Verlauf, der Stand gespeichert/ungespeichert und die
  Druckerauswahl bleiben erhalten; es gibt keine Rückfrage und nie zwei
  Fenster. Undo-Beschriftungen und Druckerstatus erscheinen in der neuen
  Sprache; eine laufende Regler-Geste wird vorher als Eintrag abgeschlossen.
  Vorher (0.1.2) ging ein ungespeichertes Design beim Sprachwechsel
  kommentarlos verloren; mit der neuen Schließen-Rückfrage blieben nach
  „Abbrechen“ zwei Fenster offen
- Neue Texte in allen 33 Sprachen
- Tests: `tests/test_new_design.py`; die GUI-Tests laufen mit echten Widgets
  gegen einen privaten Broadway-Server (ohne `gtk4-broadwayd` übersprungen)

#### Pillow im Flatpak
- Manifest: neues Modul `python-pillow` (Pillow 13.0.0, manylinux-Wheel für
  CPython 3.14 / x86_64, sha256 gegen PyPI geprüft). Damit bettet auch die
  Flatpak-Version das sRGB-Farbprofil in die Druck-PNG ein (`PIL.ImageCms`; das
  Wheel bringt liblcms2 selbst mit). Lizenz: MIT-CMU
- Runtime bleibt GNOME Platform 51 (aktuellster Zweig auf Flathub)

### Changed

#### numpy ist eine feste Abhängigkeit
- `pyproject.toml`: numpy steht unter `dependencies` statt im Extra
  `enhanced` (die Zeichenfläche importiert es fest, ohne numpy startet die App
  nicht); Pillow bleibt optional. `pip`/`pipx` installieren numpy jetzt
  automatisch
- README: numpy ist in den pipx-Installationsbefehlen kein eigener Schritt mehr

#### Log-Meldungen auf Englisch
- Alle Log-Meldungen sind englisch, sachlich und knapp; sie sind für
  Fehlerberichte gedacht und werden nicht übersetzt. Texte der Oberfläche sind
  unverändert

#### Logdatei im XDG-State-Ordner
- Die Logdatei liegt nicht mehr lose im Home, sondern unter
  `~/.local/state/disc-printer/disc-printer.log` (bzw.
  `$XDG_STATE_HOME/disc-printer/`), im Flatpak unter
  `~/.var/app/de.haku.disc-printer/.local/state/disc-printer/disc-printer.log`.
  Ermittelt über `GLib.get_user_state_dir()` in `paths.py`; bei GLib < 2.72
  Rückfall nach XDG-Regel (`$XDG_STATE_HOME`, sonst `~/.local/state`)
- Die Datei wird erst beim ersten Log-Eintrag geöffnet, nicht schon beim Import;
  der Ordner wird bei Bedarf angelegt. Ist sie nicht schreibbar, läuft die App
  ohne Datei-Log weiter und meldet das einmal auf stderr
- `DISC_PRINTER_LOG_FILE` lenkt den Pfad um (leer: kein Datei-Log). Die Tests
  nutzen das und schreiben nicht mehr ins Home
- Die alte `~/disc-printer.log` (bis 0.1.2) wird nicht mehr geschrieben, aber
  auch nicht angerührt; sie kann von Hand gelöscht werden
- README: neuer Abschnitt „Log file“ für Fehlerberichte

#### Undo vollständig
- Hintergrund-Zoom (Regler und Mausrad), die Pfeilknöpfe, „Zentrieren“ und das
  Verschieben des Hintergrundbilds mit der Maus haben jetzt Undo-Einträge.
  Regler und Mausrad ergeben einen Eintrag je Geste (Endwert nach 600 ms Ruhe),
  mehrere Pfeilknopf-Klicks kurz hintereinander einen gemeinsamen Eintrag.
  Offene Gesten werden vor jedem anderen Eintrag und vor Undo/Redo
  abgeschlossen, damit die Reihenfolge stimmt
- Dieselbe Logik für die Bild-Regler (Deckkraft, Helligkeit, Kontrast) und den
  Mausrad-Zoom auf Bildern: eine laufende Geste wird vor Undo/Redo und vor
  jedem anderen Eintrag abgeschlossen (Strg+Z mitten in der Geste nimmt genau
  diese Geste zurück, nicht den vorigen Eintrag). Bild- und
  Hintergrund-Gesten werden in der Reihenfolge ihres Beginns eingetragen
- Fehler behoben (schon in 0.1.2): Undo nach dem Verschieben eines Bilds am
  Bildkörper scheiterte mit `KeyError`, weil nur die Position gemerkt wurde
- README: Undo-Beschreibung präzisiert; Ebenen-Reihenfolge (↑/↓) gibt es nur
  für Bilder, nicht für Text (Tabelle korrigiert)
- Tests: `tests/test_undo.py` mit einem Audit aller 32 Designaktionen (je genau
  ein Undo-Eintrag, Undo und Redo stellen den Zustand exakt her)

#### Log aufgeräumt
- „Printer selected“ und „Printer …: ready“ erschienen doppelt: Beim Befüllen
  der Druckerliste löste GTK `notify::selected` selbst aus, danach wurde der
  Handler noch einmal explizit aufgerufen (zwei Status-Threads). Das Signal ist
  beim Befüllen jetzt gesperrt; die Auswahl läuft genau einmal
- „Design saved“ erschien doppelt (in `file_format.save()` und im Fenster); das
  Fenster loggt nicht mehr selbst. Ebenso entfällt „Design opened“ neben
  „Design loaded“
- Regler (Helligkeit, Kontrast, Opazität, Hintergrund-Zoom) und Mausrad-Zoom
  loggen nur noch den Endwert nach 600 ms Ruhe statt jedes Zwischenschritts;
  Helligkeit, Kontrast und Opazität wurden bisher gar nicht geloggt
- Ein bloßer Klick auf Hintergrund, Bild oder Text (ohne Bewegung) loggt kein
  „moved“ mehr und legt keinen leeren Undo-Eintrag an
- Tests: `tests/test_log_cleanup.py` (echte Widgets, Broadway)

#### README
- Abschnitt „Project layout“ mit dem tatsächlichen Inhalt von
  `src/disc_printer` abgeglichen (u. a. `paths.py`, `constants.py`,
  `settings.py`, `image_utils.py`)

### Fixed

#### Sprach-Auswahlfeld
- Das Feld zeigte nach dem Zurückwechseln auf Deutsch „العربية“
  (ersten Listeneintrag), obwohl die Oberfläche deutsch war (schon in 0.1.2).
  Deutsch ist intern der Fallback ohne Sprache; das Feld suchte diesen Wert
  nicht in der Liste und fiel auf Eintrag 0 zurück. Dasselbe beim ersten Start
  ohne Einstellung, wenn die Systemsprache nicht übersetzt ist. Fehlt die
  Übersetzungsdatei einer Sprache (Start aus dem Quellcode ohne
  `make compile-mo`), zeigte das Feld diese Sprache, die Oberfläche blieb aber
  deutsch. In die Einstellungen wurde nie eine falsche Sprache geschrieben.
  Jetzt zeigt das Feld immer die tatsächlich angezeigte Sprache.
- Tests: Feld, aktive Übersetzung und sichtbare Beschriftung werden nach
  Sprachwechsel, Neues Design und Öffnen verglichen; die GUI-Tests laufen mit
  fester Systemsprache

#### Start ohne Anzeige (#2)
- Kann GTK keine Anzeige öffnen, endet die App mit einer einzeiligen Meldung
  auf stderr und Exit-Code 1 statt mit Traceback, GTK-Warnungen und
  `exit=0` im Log. Die Ursache steht zusätzlich in der Logdatei
- Tests: `tests/test_no_display.py`, inklusive eines echten Starts ohne Anzeige

#### Design-Ordner folgt dem System-Dokumente-Ordner (#2)
- Neues Modul `paths.py`: Der Speicherort für `.discprint`-Designs wird über
  `GLib.get_user_special_dir(DIRECTORY_DOCUMENTS)` ermittelt
  (`<Dokumente>/DiscPrinter`) statt fest `~/Dokumente/DiscPrinter`; ohne
  Dokumente-Ordner im System Rückfall auf `~/DiscPrinter`. Unabhängig von der
  App-Sprache. Auf nicht-deutschen Systemen entsteht kein Ordner „Dokumente“ mehr
- Abwärtskompatibel: Enthält `~/Dokumente/DiscPrinter` bereits Dateien und
  existiert der neue Ordner noch nicht, wird weiter der alte verwendet; es wird
  nichts verschoben oder gelöscht
- `window.py`: Der Ordner wird nicht mehr beim Programmstart angelegt, sondern
  erst beim Öffnen des Speichern-Dialogs; der Öffnen-Dialog startet im
  Dokumente-Ordner (bzw. im Home), solange der Unterordner fehlt
- `file_format.py`: Konstante `DEFAULT_DIR` entfernt
- Tests: `tests/test_paths.py` (hermetisch, temporäres Home)


## [0.1.2] – 2026-11-13

### Added

#### Treiberlose Drucker ohne feste CUPS-Queue (#2)
- `detection.py`: Die Druckersuche vereinigt `lpstat -p` mit `lpstat -l -e` und
  findet so auch temporäre Ziele, die CUPS erst beim Drucken anlegt (Instanzen
  `name/instanz` → Basisname; ohne `-e`-Unterstützung weiter nur `-p`)
- `detection.py`: Disc-Fähigkeit temporärer Ziele wird direkt beim Drucker per
  IPP abgefragt (`media-source-supported`, `media-type-supported`,
  `media-supported`): ein gemeinsamer `ippfind`-Suchlauf, danach `ipptool`
  parallel für alle verbliebenen Ziele; Werte im PPD-Format wie bei festen Queues
- `detection.py`: Temporäre Ziele, die auf dasselbe Gerät zeigen wie eine feste
  Queue (Vergleich über den Hostnamen), werden ausgeblendet und im Log vermerkt
- `window.py`: Statusanzeige für temporäre Ziele: „Im Netzwerk verfügbar
  (treiberlos)" bzw. „Nicht mehr im Netzwerk gefunden (treiberlos)" statt
  „Status unbekannt"
- `detection.py`: Einmalige Log-Warnung, wenn `ippfind`/`ipptool` fehlen
  (Debian/Ubuntu: `cups-ipp-utils`, Arch: `cups`); README-Abhängigkeiten ergänzt
- Übersetzungen der neuen Texte in 33 Sprachen

#### Disc-Maße in Millimetern und Zoll
- `canvas.py`/`window.py`: Vorschau und Hub-Auswahl zeigen die Maße in allen
  Sprachen in beiden Einheiten, z. B. „Ø 120 mm / 4.72 in", „Ø 118 mm / 4.65 in
  (bedruckbar)"; im Hub der Vorschau steht der Zoll-Wert in einer zweiten Zeile,
  damit die Beschriftung in den 33-mm-Hub passt
- `units.py`: Umrechnung an einer Stelle; übersetzbare Texte mit benannten
  Platzhaltern (`%(mm)`, `%(inch)`), damit Übersetzer die Reihenfolge ändern können

### Changed
- Übersetzungsvorlage `disc_printer.pot` erneuert: Sie enthielt seit 0.1.0
  47 Texte der Oberfläche nicht. Diese sind jetzt in allen 33 Sprachen
  übersetzt. Die Übersetzungen wurden maschinell erstellt; Korrekturen sind
  willkommen

### Fixed
- `window.py`/`printer.py`: Druck auf ein temporäres Ziel zeigte nur die rohe
  lp-Meldung („No such file or directory"). Jetzt erscheint eine verständliche
  Erklärung mit Abhilfe (Drucker fest einrichten). Ursache ist ein Fehler in
  cupsd 2.4.20 beim Anlegen temporärer Queues (OpenPrinting/cups#1751, im Zweig
  2.4.x behoben, noch kein Release); README-Abschnitt „Driverless printers"
- `window.py`: Die Erfolgsmeldung nach dem Druck stürzte mit `AttributeError`
  ab (`set_heading`/`set_body` gehören zu `Adw.AlertDialog`); jetzt
  `Gtk.AlertDialog.set_message`/`set_detail`. Fehler bestand seit 0.1.0
- Spanische Übersetzung: „Posición e zoom de la imagen" → „Posición y zoom de
  la imagen"

## [0.1.1] – 2026-11-04

### Fixed

- README documented a `pip install --user disc-printer` that never existed
  (the package was never published to PyPI), and translations were missing in
  installs from Git (`.mo` files are gitignored). Both fixed: README now
  documents `pipx install --system-site-packages git+https://...`, and a
  custom Hatch build hook compiles `.po` → `.mo` at wheel-build time.

### Changed

- Flatpak-Bundle und Prüfsumme im Manifest neu erzeugt, damit das Bundle den
  CUPS-HTTP-Fallback aus 0.1.0 enthält
- README: neuer Abschnitt „Printer Compatibility" mit getesteten Modellen
  (Canon PIXMA TS705a) und der Bitte um Rückmeldungen in Issue #1


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

#### Flatpak-Paket (2026-04-25)
- `flatpak/de.haku.disc-printer.yml`: Manifest für GNOME Platform 47;
  Module: python-numpy (manylinux wheel), cups-client-tools (CUPS 2.4.11,
  nur lp/lpstat/lpoptions), disc-printer (aus GitHub-Tag v0.1.0)
- `flatpak/de.haku.disc-printer.desktop`, `.metainfo.xml`, `.svg`: Desktop-
  Integration, AppStream-Metadaten, App-Icon
- `flatpak/disc-printer.flatpak`: Fertig gebautes Single-File-Bundle (13 MB)
- `flatpak/de.haku.disc-printer.flatpakref`: Referenzdatei für Flatpak-Install

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

#### CUPS-HTTP-Fallback für die Flatpak-Sandbox (2026-04-25)
- `detection.py`: `_fetch_ppd_via_cups_http()` holt die PPD über die CUPS-HTTP-API
  am Unix-Socket `/run/cups/cups.sock` (im Flatpak per `--socket=cups`
  verfügbar), weil `lpoptions -l` in der Sandbox `/etc/cups/ppd/` nicht lesen
  kann; Erkennungsreihenfolge: PPD-Datei → lpoptions → CUPS-HTTP-API

### Changed
- `model.py`: `TextElement` erhält `z`-Parameter für die Ebenensortierung
- `canvas.py`: alle Ebenen (`ImageElement` + `TextElement`) werden nach z-Wert
  sortiert gerendert (Bilder vor Text bei gleichem z)
- `window.py`: `_apply_loaded_design()` aktualisiert auch `images`-Liste und
  `_img_rows`
- Canvas drag-and-drop now creates `ImageElement` instead of setting legacy background image
- Background section hint text updated to clarify its limitations (position & zoom only)

### Fixed

- Selection handles not visible after clicking on an image element:
  - Added robust `_draw_hw` fallback in `_draw` step 7 (recomputes from surface dimensions
    if `_draw_image_elem` hasn't set it yet)
  - Added `try/except` around `_draw_img_handles` with error logging

#### Gettext-Shadowing in _on_detection_done (2026-04-25)
- `window.py`: Loop-Variable `_` in `for _ in range(n):` durch `_i` ersetzt,
  da `_` die gettext-Funktion überschrieb und `_("...")` im Rumpf abstürzte
  (TypeError: 'int' object is not callable) wenn keine Disc-Drucker gefunden


[Unreleased]: https://github.com/MrHaku81/disc-printer/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/MrHaku81/disc-printer/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/MrHaku81/disc-printer/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/MrHaku81/disc-printer/releases/tag/v0.1.0
