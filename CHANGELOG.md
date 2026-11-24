# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **README mit Bildschirmfotos:** Hauptfenster oben, neuer Abschnitt
  „Screenshots“ (Druckbereich mit Foto der bedruckten Disc, Bild- und
  Textelemente, Zoll-Angaben, die beiden Menüfenster, Japanisch und Deutsch).
  Die Bilder liegen in `docs/screenshots/` und gehören nicht zum Paket

## [0.3.0] – 2026-11-24

Neues Symbol und ein Menü in der Kopfleiste; am Drucken hat sich nichts
geändert.

### Added
- **Menü in der Kopfleiste** (ganz rechts, neben „Drucken“) mit „Nach neuer
  Version suchen“ und „Über Disc Printer“. Das Programm geht dafür nicht ins
  Internet: Das Fenster zeigt die installierte Version, den passenden Befehl
  zum Aktualisieren (Flatpak bzw. AUR, mit Knopf zum Kopieren) und öffnet auf
  Wunsch die Release-Seite im Browser. Im Flatpak ohne zusätzliches Recht.
  Alle neuen Texte in allen 34 Sprachen
- **README:** neuer Abschnitt „Updating“ für Flatpak, AUR, pipx und Quelltext

### Changed
- **Versionsnummer an einer Stelle:** `src/disc_printer/_version.py`;
  `pyproject.toml` und `make pot` lesen sie dort
- **Neues Programmsymbol:** eine Disc in Schrägansicht mit Klecksen in
  Magenta, Cyan und Gelb, darüber fällt ein schwarzer Tropfen. Entworfen von
  Klaus mit Claude, Lizenz MIT wie das Projekt. Eine vereinfachte Zeichnung
  für alle Größen, installiert nur nach `hicolor/scalable/apps`

### Fixed
- **Rotes Platzhaltersymbol in der Titelleiste:** Das Fenster fragte nach dem
  Symbol `disc-printer`, installiert ist es aber als `de.haku.disc-printer`.
  GTK fand nichts und zeigte `image-missing`. Das Fenster setzt jetzt keinen
  eigenen Namen mehr; GTK nimmt die App-ID, sobald das Symbol installiert ist

## [0.2.0] – 2026-11-21

Zuerst die Korrektur beim Druck, dann die Änderungen, die man beim Arbeiten mit
der App bemerkt; danach Technisches.

### Fixed

#### Kein Druck mehr in die Disc-Mitte
- **Alle Versionen bis 0.1.3 haben bis in die Mitte der Disc gedruckt.**
  Hintergrundfarbe und Motive reichten durch den Hub, beschnitten wurde nur
  außen bei 118 mm. Der Drucker spart die Mitte nicht selbst aus (geprüft am
  Canon TS705a, treiberlos über IPP Everywhere: Tintenreste in der Mitte des
  Disc-Fachs). Tinte konnte so auf dem Hub und durch das Loch auf dem Fach
  landen
- Ab 0.2.0 wird das Druckbild mit dem eingestellten Innen- und
  Außendurchmesser maskiert; innen und außen bleibt es weiß, dort kommt keine
  Tinte hin. Seitengröße (120 × 120 mm, 300 DPI) und lp-Optionen sind
  unverändert
- **Empfehlung:** Wer mit einer älteren Version Discs bedruckt hat, sollte das
  Disc-Fach in der Mitte reinigen, damit getrocknete Tinte nicht auf neue
  Discs übertragen wird
- Die Vorschau zeigt genau, was gedruckt wird: Motive im Hub und außerhalb des
  Außendurchmessers sind verdeckt, der nicht bedruckte Ring am Rand ist
  schraffiert

### Added

#### Einstellbarer Druckbereich (#3, Vorschlag von JPinTX)
- Neuer Bereich „Druckbereich“ unter der Vorschau: Innen- und Außendurchmesser
  sind frei einstellbar, je mit Schieberegler (0,5-mm-Schritte) und Zahlenfeld
  (0,1 mm genau, in Zoll zwei Nachkommastellen). Innen 18–50 mm, außen
  70–120 mm. Damit lassen sich Rohlinge mit anderem Druckbeginn und
  Mini-Discs (80 mm) einstellen; 80-mm-Discs sind noch nicht am Drucker
  getestet
- Zwei Voreinstellungen als Abkürzung: „Standard“ (innen 50, außen 118 mm) und
  „Vollflächig“ (innen 33, außen 118 mm). Hervorgehoben ist ein Knopf, wenn die
  aktuellen Werte seiner Voreinstellung entsprechen, auch nach
  Hand-Einstellung oder nach dem Laden einer Datei
- Hinweis, keine Sperre: außen über 118 mm oder innen unter 21 mm erscheint
  „Außerhalb des üblichen Druckbereichs … Tinte kann auf dem Disc-Fach landen“
- Jede Reglerbewegung, jede Feldeingabe und jeder Klick auf eine
  Voreinstellung ist genau ein Undo-Schritt. Neues Design setzt auf „Standard“
  zurück, ein Sprachwechsel behält die Werte

#### Millimeter oder Zoll
- Schalter mm | in im Druckbereich: gilt für alle Maßangaben der App (auch die
  Tooltips der Pfeilknöpfe), wird gespeichert, beim ersten Start mm. Das
  Dezimalzeichen folgt der Sprache der Oberfläche; Eingaben mit Komma und
  Punkt werden beide verstanden. Die Einheit gehört nicht zum Design (kein
  Undo-Schritt, keine ungespeicherte Änderung)
- Was in der gewählten Einheit gleich angezeigt wird wie eine Voreinstellung
  oder Schwelle, gilt auch als gleich: „4,65 in“ ist „Standard“ außen und
  löst keinen Hinweis aus. Eine Zoll-Eingabe wird dazu auf das nächste
  0,5-mm-Vielfache gelegt, wenn es denselben Zoll-Wert zeigt (4,65 in →
  118,0 mm; 4,66 in bleibt 118,4 mm)

### Changed

#### Vorschau und Seitenleiste
- Die Maßtexte auf der Vorschau (Ø 120 mm, Hub-Maß, „bedruckbar“) sind
  entfallen; sie verdeckten das Motiv. Hub und Außenrand bleiben als Flächen
  sichtbar
- Der Bereich „Disc-Optionen / Hub-Größe“ in der rechten Spalte entfällt; er
  ist im Druckbereich aufgegangen

#### Neue Elemente richten sich nach dem Druckbereich
- Neue Texte starten in der Mitte des sichtbaren Rings (oben, jeder weitere
  Text 45° weiter) statt teils im Hub
- Neue Bilder starten mit 60 % des eingestellten Außendurchmessers statt fest
  60 % von 118 mm. Das Hintergrundbild wird weiterhin fest auf 118 mm
  eingepasst; bestehende Designs sehen unverändert aus

#### Dateiformat
- `.discprint` speichert zusätzlich `outer_diameter`; der Innendurchmesser steht
  weiter unter `hub_size`. Formatversion bleibt 2. Ältere Dateien laden mit
  118 mm außen. 0.1.3 öffnet neue Dateien ohne Fehler, ignoriert aber den
  Außendurchmesser und zeigt einen Innendurchmesser ungleich 50 mm unter dem
  33-mm-Knopf an
- Werte außerhalb der einstellbaren Bereiche oder ungültige Werte in einer
  Datei werden begrenzt bzw. durch die Vorgabe ersetzt (mit Eintrag im Log)

### Technisches
- `DesignState` enthält `inner_mm`/`outer_mm`; `design_fingerprint`,
  `file_format.save/load` und `DiscCanvas.render_for_print` nehmen keinen
  Hub-Parameter mehr. `PRINTABLE_MM`, `HUB_LARGE_MM`, `HUB_SMALL_MM` und
  `units.format_dimension` sind entfernt; neu sind die Bereichs-, Voreinstellungs-
  und Hinweis-Konstanten in `constants.py` und Zahlenformat/-eingabe in
  `units.py`
- Übersetzungen: 16 neue Texte in allen 33 Sprachen, 11 nicht mehr gebrauchte
  entfernt (Maßtexte, Hub-Größe, „5 mm links“ usw.)
- Tests: GUI-Szenarien `print_area` und `area_lang` (Voreinstellungen und
  Hervorhebung, Regler und Felder in mm und Zoll, gleich angezeigte Werte,
  Undo, Speichern/Laden alt und neu, Sprachwechsel, Druckmaske über den echten
  Druckweg, Vorschau-Maske); der Undo-Prüftest deckt Voreinstellung, Regler
  und Felder ab

## [0.1.3] – 2026-11-19

Zuerst die Änderungen, die man beim Arbeiten mit der App bemerkt; danach
Technisches für Installation, Fehlerberichte und Entwicklung.

### Added

#### Neues Design
- Knopf „Neues Design“ in der Kopfleiste (links vor „Öffnen“): setzt das Design
  auf den Zustand eines frischen Starts zurück (Hintergrund, Bild- und
  Text-Elemente, Hub-Größe, Undo/Redo-Verlauf). Druckerauswahl und Sprache
  bleiben

#### Rückfrage bei ungespeicherten Änderungen
- Vor „Neues Design“, vor „Öffnen“ und beim Schließen des Fensters fragt die
  App nach, wenn es ungespeicherte Änderungen gibt: Abbrechen / Verwerfen /
  Speichern …. „Abbrechen“ lässt alles, wie es war (beim Schließen bleibt das
  Fenster offen); „Speichern …“ macht erst nach erfolgreichem Speichern weiter.
  Ohne Änderungen kommt keine Rückfrage
- Gilt für jeden Weg des Schließens: Titelleiste, Alt+F4, Taskleiste

### Changed

#### Undo vollständig
- Hintergrund-Zoom (Regler und Mausrad), die Pfeilknöpfe, „Zentrieren“ und das
  Verschieben des Hintergrundbilds mit der Maus lassen sich jetzt rückgängig
  machen. Eine Regler- oder Mausrad-Bewegung ist ein Schritt; mehrere
  Pfeilknopf-Klicks kurz hintereinander sind ein gemeinsamer Schritt
- Strg+Z mitten in einer Regler-Bewegung (auch Deckkraft, Helligkeit, Kontrast
  und Mausrad-Zoom auf Bildern) nimmt genau diese Bewegung zurück, nicht den
  Schritt davor

#### Design-Ordner folgt dem Dokumente-Ordner des Systems (#2)
- Designs werden in `<Dokumente>/DiscPrinter` gespeichert, wobei
  `<Dokumente>` der Dokumente-Ordner des Systems ist (z. B. `~/Documents`),
  statt fest in `~/Dokumente/DiscPrinter`. Auf nicht-deutschen Systemen entsteht
  kein Ordner „Dokumente“ mehr; ohne Dokumente-Ordner wird `~/DiscPrinter`
  verwendet
- Wer schon `.discprint`-Designs in `~/Dokumente/DiscPrinter` hat, arbeitet
  dort weiter, solange der neue Ordner noch nicht existiert; nichts wird
  verschoben oder gelöscht
- Der Ordner wird erst beim Speichern angelegt, nicht schon beim Start

#### Sprachwechsel behält das Design
- Beim Wechsel der Sprache bleiben Design, Undo/Redo-Verlauf, der Stand
  gespeichert/ungespeichert und die Druckerauswahl erhalten; die Oberfläche
  erscheint im selben Fenster in der neuen Sprache, ohne Rückfrage. Bisher ging
  ein ungespeichertes Design beim Sprachwechsel verloren

### Fixed

#### Sprach-Auswahlfeld
- Nach dem Zurückwechseln auf Deutsch zeigte das Feld „العربية“, obwohl die
  Oberfläche deutsch war (schon in 0.1.2; ebenso beim ersten Start, wenn die
  Systemsprache nicht übersetzt ist). Jetzt zeigt das Feld immer die
  tatsächlich angezeigte Sprache. In die Einstellungen wurde nie eine falsche
  Sprache geschrieben

#### Undo nach dem Verschieben eines Bilds
- Undo nach dem Verschieben eines Bilds am Bildkörper funktionierte nicht
  (Fehler `KeyError`, schon in 0.1.2)

#### Start ohne Anzeige (#2)
- Kann die App keine Anzeige öffnen (z. B. Start über SSH ohne Grafik), endet
  sie mit einer einzeiligen Meldung und Exit-Code 1 statt mit Traceback und
  GTK-Warnungen (und `exit=0` im Log). Die Ursache steht zusätzlich in der
  Logdatei

#### Kleinigkeiten
- Der Platzhalter `<datei>` in der Druckbefehl-Anzeige unter der
  Druckerauswahl ist jetzt übersetzt
- README: Ebenen-Reihenfolge (↑/↓) gibt es nur für Bilder, nicht für Text
  (Tabelle korrigiert); Undo-Beschreibung präzisiert

### Technisches

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
- `DISC_PRINTER_LOG_FILE` lenkt den Pfad um (leer: kein Datei-Log)
- Die alte `~/disc-printer.log` (bis 0.1.2) wird nicht mehr geschrieben, aber
  auch nicht angerührt; sie kann von Hand gelöscht werden
- README: neuer Abschnitt „Log file“ für Fehlerberichte

#### Log-Meldungen
- Alle Log-Meldungen sind englisch, sachlich und knapp; sie sind für
  Fehlerberichte gedacht und werden nicht übersetzt
- Doppelte Zeilen entfernt: „Printer selected“ und „Printer …: ready“ (GTK
  löste beim Befüllen der Druckerliste `notify::selected` selbst aus; das
  Signal ist dabei jetzt gesperrt, die Auswahl läuft genau einmal, ein
  Status-Thread), „Design saved“ (stand in `file_format.save()` und im Fenster)
  und „Design opened“ neben „Design loaded“
- Regler (Helligkeit, Kontrast, Opazität, Hintergrund-Zoom) und Mausrad-Zoom
  loggen nur noch den Endwert nach 600 ms Ruhe; Helligkeit, Kontrast und
  Opazität wurden bisher gar nicht geloggt
- Ein bloßer Klick auf Hintergrund, Bild oder Text (ohne Bewegung) loggt kein
  „moved“ mehr und legt keinen leeren Undo-Eintrag an

#### Installation
- `pyproject.toml`: numpy steht unter `dependencies` statt im Extra
  `enhanced` (die Zeichenfläche importiert es fest, ohne numpy startet die App
  nicht); Pillow bleibt optional. `pip`/`pipx` installieren numpy jetzt
  automatisch; in der README ist numpy kein eigener Schritt mehr
- Flatpak-Manifest: neues Modul `python-pillow` (Pillow 13.0.0, manylinux-Wheel
  für CPython 3.14 / x86_64, sha256 gegen PyPI geprüft). Damit bettet auch die
  Flatpak-Version das sRGB-Farbprofil in die Druck-PNG ein (`PIL.ImageCms`; das
  Wheel bringt liblcms2 selbst mit). Lizenz: MIT-CMU. Runtime bleibt GNOME
  Platform 51

#### Umsetzung
- Ungespeicherte Änderungen werden über einen Fingerabdruck des Designs
  erkannt, auch Änderungen ohne Undo-Eintrag. Schließen läuft über
  `close-request`; ein eigenes Tastenkürzel zum Beenden gibt es nicht
- Undo: Regler- und Mausrad-Gesten (Bild und Hintergrund) ergeben einen
  Eintrag je Geste (Endwert nach 600 ms Ruhe). Offene Gesten werden über
  `History.before_change` vor jedem anderen Eintrag und vor Undo/Redo
  abgeschlossen, in der Reihenfolge ihres Beginns. Beim Ziehen eines Bilds
  wird der vollständige Zustand (Position, Größe, Drehung) gemerkt
- Sprachwechsel: Die Oberfläche wird im selben Fenster neu aufgebaut
  (`_retranslate`) statt in einem neuen; Undo-Beschriftungen und Druckerstatus
  werden erst beim Anzeigen übersetzt. Vorher entstand ein neues Fenster; mit
  der Schließen-Rückfrage blieben nach „Abbrechen“ zwei Fenster offen
- Sprach-Auswahlfeld: Deutsch ist intern der Fallback ohne Sprache; das Feld
  suchte diesen Wert nicht in der Liste und fiel auf Eintrag 0 zurück
  (`i18n.effective_lang()`). Fehlt die Übersetzungsdatei einer Sprache (Start
  aus dem Quellcode ohne `make compile-mo`), zeigt das Feld jetzt Deutsch, wie
  die Oberfläche
- `paths.py`: Design-Ordner über
  `GLib.get_user_special_dir(DIRECTORY_DOCUMENTS)`, unabhängig von der
  App-Sprache; `window.py` legt ihn erst beim Speichern-Dialog an, der
  Öffnen-Dialog startet im Dokumente-Ordner (bzw. im Home), solange der
  Unterordner fehlt; `file_format.py`: Konstante `DEFAULT_DIR` entfernt
- „Neues Design“ verwirft laufende Regler-Timer, damit kein verspäteter
  Undo-Eintrag im frischen Design landet
- Übersetzungen: neue Texte in allen 33 Sprachen; veraltete Katalogeinträge
  entfernt, Zeilenverweise und Versionsangaben der Kataloge aufgefrischt
- README: Abschnitt „Project layout“ mit dem tatsächlichen Inhalt von
  `src/disc_printer` abgeglichen (u. a. `paths.py`, `constants.py`,
  `settings.py`, `image_utils.py`)

#### Tests
- GUI-Tests mit echten Widgets gegen einen privaten Broadway-Server (ohne
  `gtk4-broadwayd` übersprungen), mit fester Systemsprache:
  `tests/test_new_design.py`, `tests/test_undo.py` (Audit aller 32
  Designaktionen: je genau ein Undo-Eintrag, Undo und Redo exakt, auch nach
  einem Sprachwechsel), `tests/test_log_cleanup.py`
- `tests/test_paths.py`, `tests/test_logfile.py`, `tests/test_no_display.py`
  (inklusive eines echten Starts ohne Anzeige)
- Die Tests schreiben nichts ins Home (`DISC_PRINTER_LOG_FILE`, temporäres Home)


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


[Unreleased]: https://github.com/MrHaku81/disc-printer/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/MrHaku81/disc-printer/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MrHaku81/disc-printer/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/MrHaku81/disc-printer/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/MrHaku81/disc-printer/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/MrHaku81/disc-printer/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/MrHaku81/disc-printer/releases/tag/v0.1.0
