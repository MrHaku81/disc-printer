# Arbeitsstand und Release-Notizen

Stand: 0.2.0 ist seit 2026-11-21 veröffentlicht (GitHub-Release mit
Flatpak-Bundle, AUR 0.2.0-2). 0.3.0 vorbereitet am 2026-11-24: main, Tag
`v0.3.0`, Manifest mit Archiv-Prüfsumme, Flatpak-Bundle in
`/var/tmp/disc-printer-0.3.0/` zum Test durch Klaus. GitHub-Release und AUR
stehen noch aus (Schritt 7 unten erst nach dem Probedruck).

## Geklärt

Entschiedene Fragen, jeweils mit Datum und Begründung. Nicht erneut
vorschlagen; neue Entscheidungen am Ende eines Auftrags hier eintragen.

- **2026-11-13 (0.1.2), treiberlose Drucker:** Die Antwort ist eine feste
  CUPS-Warteschlange, so steht es im README; damit ist das Problem für alle
  Installationsarten gelöst. Im Flatpak läuft die IPP-Erkennung nicht
  (`ippfind`/`ipptool` nicht im Bundle, CUPS dort ohne Avahi gebaut, kein
  Netzrecht; geprüft am 2026-11-23 in der Runtime ohne Netz), derselbe Rat gilt
  dort. Nichts ändern, weder am Manifest noch am README.
- **2026-11-23, Programmsymbol:** nur ein Symbol für alle Größen, die
  vereinfachte Fassung (Entscheidung von Klaus). Eine Fassung hält Manifest
  und AUR-Paket einfach: keine festen Größenordner, keine Zusatzzeilen.
- **2026-11-23, Updates:** Das Programm sucht nicht selbst nach Updates und
  geht nicht ins Internet; das Menü „Nach neuer Version suchen“ öffnet nur die
  Release-Seite im Browser. So bleibt die App ohne Netzverkehr, und das
  Flatpak bekommt kein Netzrecht.
- **2026-11-23, Flathub:** wird vorerst nicht verfolgt, wegen der dortigen
  KI-Regel und weil dafür eine neue App-ID nötig wäre.
- **2026-11-24, CLAUDE.md:** bleibt lokal, `.gitignore` bleibt wie sie ist
  (Entscheidung von Klaus); die Datei ist eine Arbeitshilfe für Claude, nicht
  für Mitwirkende.
- **2026-11-24, Versionsnummer 0.3.0:** Das Menü mit „Nach neuer Version
  suchen“ und „Über Disc Printer“ ist eine neue Funktion, deshalb steigt die
  mittlere Stelle (Semantic Versioning); am Drucken ändert sich nichts.

## Release-Ablauf (so lief 0.1.3, für 0.2.0 und 0.3.0 wiederholt)

1. **Vorbereiten auf einem Zweig** (`prep/<version>`): Version in
   `src/disc_printer/_version.py` (einzige Quelle; `pyproject.toml` und
   `make pot` lesen sie dort, ein Test vergleicht sie mit der Metainfo),
   `make pot` und `make update-po` (übernimmt die Version in
   die `.pot`; die Köpfe der `.po` von Hand anpassen), Release-Eintrag mit
   Datum in `flatpak/de.haku.disc-printer.metainfo.xml`
   (`appstreamcli validate --no-net --pedantic`), CHANGELOG: „Unreleased“ →
   Version mit Datum, Vergleichslinks unten. Kataloge prüfen: jede Sprache
   vollständig, 0 fuzzy, 0 leer, 0 veraltet (`msgfmt --statistics`,
   `msgattrib --only-fuzzy/--untranslated`, `msgcmp`). Alle Tests.
2. **main per Fast-Forward** auf den Release-Commit, kein Force. Annotierten
   Tag `v<version>` auf diesen Commit setzen und pushen; den prep-Zweig auf
   origin löschen.
3. **Erst nach dem Tag: Manifest-Prüfsumme.** Archiv
   `https://github.com/MrHaku81/disc-printer/archive/refs/tags/v<version>.tar.gz`
   laden (zweimal, Prüfsumme muss gleich sein; Inhalt mit
   `git archive v<version>` vergleichen), `url` und `sha256` in
   `flatpak/de.haku.disc-printer.yml` eintragen, eigener Commit auf main.
   Das Manifest im Tag kann die Prüfsumme seines eigenen Archivs nicht
   enthalten; das ist so gewollt.
4. **Flatpak bauen** mit GNOME-Runtime 51. Runtime und SDK sind im Konto
   `discprinter` als `--user` installiert (Flathub als `--user`-Remote);
   nichts systemweit, kein sudo. Bauordner außerhalb des Repos:
   ```
   flatpak-builder --user --force-clean --disable-rofiles-fuse \
     --state-dir=<tmp>/state --repo=<tmp>/repo <tmp>/build \
     flatpak/de.haku.disc-printer.yml
   flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
     <tmp>/repo <tmp>/disc-printer.flatpak de.haku.disc-printer
   ```
   Das Bundle nie ins Repo legen.
5. **Bundle prüfen**, ohne es ins eigene Konto zu installieren: Installation
   mit `FLATPAK_USER_DIR=<tmp>/inst` (holt die Runtime über `--runtime-repo`
   selbst), Läufe mit einem Scratch-`HOME`. Prüfen: Start ohne Anzeige gibt
   die einzeilige Meldung mit Exit 1; numpy, Pillow und `PIL.ImageCms`
   importierbar; alle `.mo` enthalten. sha256 des Bundles notieren.
   Das Paket wird ohne `dist-info` kopiert; die Version liest das Programm
   aus `_version.py` (Menü → „Über Disc Printer“ muss sie zeigen). Zusätzlich
   das installierte Paket per `diff -r` mit den Quellen aus dem Archiv
   vergleichen. Die drei Fassungen des Fensters „Nach neuer Version suchen“
   lassen sich mit der Testhilfe `DISC_PRINTER_INSTALL_KIND=flatpak|pacman|other`
   erzwingen (im Flatpak:
   `flatpak run --env=DISC_PRINTER_INSTALL_KIND=pacman de.haku.disc-printer`);
   andere Werte werden ignoriert, dann gilt die Erkennung. Seit 0.2.0
   außerdem: Druckbild über
   `MainWindow._print_thread` mit abgefangenem `lp` erzeugen und die Maske
   innen und außen per Pixel prüfen (Skript mit `--filesystem=<tmp>` und
   `--command=python3` im Sandbox-Python).
6. **Ablage für den Tester** (Benutzer `haku`): Die Homes sind `700`, eine
   gemeinsame Gruppe gibt es nicht, `/tmp` ist tmpfs. Deshalb
   `/var/tmp/disc-printer-<version>/` (Ordner `755`, Dateien `644`) mit
   Bundle, `SHA256SUMS` und Release-Notizen. `/var/tmp` wird nach 30 Tagen
   geleert; der Tester kann dort lesen, aber nicht löschen.
7. **GitHub-Release über `gh`** (angemeldet als MrHaku81), erst nach dem Test
   durch den Tester:
   `gh release create v<version> --verify-tag --title "Disc Printer <version>" --notes-file <body> --latest <bundle>`.
   Am Ende der Notizen die Vorlage „So aktualisierst du“ (unten), darunter
   die sha256 des Bundles (Format wie bei 0.1.2).
   Danach: Asset wieder laden und sha256 vergleichen, `/releases/latest`
   prüfen, CHANGELOG-Link samt Sprungmarke prüfen.
8. Aufräumen: Bauordner, Test-Installation, `/var/tmp`-Ablage. Die Runtime im
   Konto bleibt für den nächsten Bau.

### Vorlage „So aktualisierst du“ (Ende jeder Release-Notiz)

Fest übernehmen, nur bei geänderten Befehlen anpassen (gleiche Befehle wie im
README-Abschnitt „Updating“ und im Menü „Nach neuer Version suchen“):

````markdown
## How to update

- **Flatpak:** download `disc-printer.flatpak` below, then
  `flatpak install --user ./disc-printer.flatpak`
- **AUR:** `yay -Syu disc-printer` (any other AUR helper works the same way)
- **pipx:** `pipx upgrade disc-printer`; if it reports the package as unchanged:
  `pipx install --force --system-site-packages git+https://github.com/MrHaku81/disc-printer.git`
- **From source:** `git pull`, then `.venv/bin/pip install -e .`
  (or `make compile-mo` when running from the source tree)

More details: [Updating](https://github.com/MrHaku81/disc-printer#updating)
````

## AUR-Paket hängt am Ordner `flatpak/`

Seit dem 2026-11-21 installiert das AUR-Paket Menüeintrag, Symbol und
Metainfo aus dem Ordner `flatpak/` des Quellarchivs:
`flatpak/de.haku.disc-printer.desktop`, `flatpak/de.haku.disc-printer.svg`,
`flatpak/de.haku.disc-printer.metainfo.xml`. **Diese Dateien nicht umbenennen
oder verschieben**, sonst bricht der AUR-Bau. Wer es doch tut, muss das
PKGBUILD im selben Zug anpassen.

Symbolname, App-ID und Menüeintrag hängen zusammen (geprüft durch
`tests/test_desktop_integration.py`): App-ID `de.haku.disc-printer` =
Wayland-`app_id` = Name der `.desktop`-Datei = `Icon=` = Symboldateiname.
`StartupWMClass=disc-printer` passt zum X11-`WM_CLASS`-Namen, den GTK aus dem
Programmnamen `disc-printer` (Startskript) bildet. Das Fenster setzt keinen
eigenen Symbolnamen (siehe `MainWindow.__init__`).

Seit `feat/new-icon` gibt es nur noch ein Symbol für alle Größen:
`flatpak/de.haku.disc-printer.svg` (die vereinfachte Zeichnung), installiert
nach `hicolor/scalable/apps/`. Die frühere `-klein.svg` und die festen
Größenordner 16/22/24/32 entfallen. **Das AUR-Paket braucht keine
Zusatzzeilen für kleine Größen mehr**; die bestehende Zeile für das Symbol
genügt.

## Offene Punkte

- **Mini-Discs (80 mm):** einstellbar (außen 70–80 mm), aber nicht am Drucker
  getestet. Der Canon TS705a nimmt nur 12-cm-Discs; JPinTX will am Epson
  prüfen, ob der Druck zentriert landet (#3).
- Notiz, nicht geplant: Idee eines 80-mm-Adapters für das Canon-Fach, um
  Mini-Discs auch hier testen zu können.

## Befunde

- Der Canon TS705a (treiberlos, IPP Everywhere) spart die Disc-Mitte nicht
  selbst aus: Klaus fand Tintenreste in der Mitte des Fachs. Alle Versionen bis
  0.1.3 haben durch den Hub gedruckt; seit 0.2.0 maskiert die App das
  Druckbild innen und außen. Ein Probedruck mit 0.2.0 ließ die Mitte frei.

## Offene Kleinigkeiten

- Datum von 0.1.0 unterscheidet sich: CHANGELOG 2026-04-24, AppStream-Metainfo
  2026-04-25.
- `appstreamcli validate --pedantic` meldet zwei Hinweise:
  `developer-name-tag-deprecated` (das `<developer_name>`-Tag ist veraltet)
  und `developer-info-missing` (es fehlt ein `<developer>`-Block).
- Die Druckererkennung braucht beim Start aus dem Quellcode rund 8 Sekunden.
