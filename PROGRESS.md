# Arbeitsstand und Release-Notizen

Stand: 0.2.0 vorbereitet am 2026-11-21: main, Tag `v0.2.0`, Manifest mit
Archiv-Prüfsumme, Flatpak-Bundle in `/var/tmp/disc-printer-0.2.0/` zum Test
durch Klaus. GitHub-Release und AUR stehen noch aus (Schritt 7 unten erst nach
dem Test). Zuletzt veröffentlicht: 0.1.3 am 2026-11-19 (GitHub-Release mit
Flatpak-Bundle, AUR 0.1.3-1).

## Release-Ablauf (so lief 0.1.3, für 0.2.0 wiederholt)

1. **Vorbereiten auf einem Zweig** (`prep/<version>`): Version in
   `pyproject.toml`, `make pot` und `make update-po` (übernimmt die Version in
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
   Die Version steht im Flatpak nur in der Metainfo (das Paket wird ohne
   `dist-info` kopiert); zusätzlich das installierte Paket per `diff -r` mit
   den Quellen aus dem Archiv vergleichen. Seit 0.2.0 außerdem: Druckbild über
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
   Im Text unter den Notizen die sha256 des Bundles (Format wie bei 0.1.2).
   Danach: Asset wieder laden und sha256 vergleichen, `/releases/latest`
   prüfen, CHANGELOG-Link samt Sprungmarke prüfen.
8. Aufräumen: Bauordner, Test-Installation, `/var/tmp`-Ablage. Die Runtime im
   Konto bleibt für den nächsten Bau.

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
