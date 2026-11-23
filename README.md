# Disc Printer

A universal disc label editor for Linux — design and print CD, DVD, and Blu-ray labels
directly from a GTK4 application, without proprietary software or manufacturer lock-in.

Disc Printer detects compatible printers automatically by analysing their installed PPD
files for disc-tray media support (Canon, Epson, and others); driverless network printers
without a permanent CUPS queue are additionally detected via IPP (see
[Driverless printers](#driverless-printers-no-permanent-cups-queue)). The print output is a
300 DPI PNG of the 120 mm disc, masked to the adjustable print area (inner and outer
diameter), sent to CUPS via `lp`.

## Who is this for?

Linux users who own a disc-capable printer and want a native, lightweight label editor
that does not require Wine, a browser, or a cloud subscription. If your printer can print
directly onto printable CDs/DVDs/Blu-rays and has a CUPS driver installed, Disc Printer
should work with it.

See [Printer Compatibility](#printer-compatibility) for tested models.

## Printer Compatibility

Disc Printer does not use a hardcoded model list — it detects disc-capable printers by
scanning the PPD files of all printers configured in CUPS (looking for disc-tray
capabilities such as `InputSlot=Disc`, `MediaType=Disc`, 120x120mm media). In principle,
any printer whose CUPS/PPD setup exposes a disc tray should work.

### Tested & verified

| Printer | Detection | Disc printing | Notes |
|---|---|---|---|
| Canon PIXMA TS705a ("TS700 series" in CUPS) | ✅ | ✅ | Multi-purpose tray, full-surface color prints |

### Should work (untested)

Canon PIXMA models with a multi-purpose (disc) tray and Epson models with disc print
support — reports welcome!

**Tested a different model?** Please report it in
[Issue #1](https://github.com/MrHaku81/disc-printer/issues/1) — model name, whether
detection worked, and whether the print landed correctly on the disc. Every confirmed
report gets added here.

### Driverless printers (no permanent CUPS queue)

Network printers that CUPS only offers as driverless destinations (listed by
`lpstat -e`, but not by `lpstat -p`) are detected as well: their disc support is queried
directly from the printer via IPP (`ippfind`/`ipptool`, see [Requirements](#requirements)).

Printing to such a printer needs a *temporary* queue, which CUPS creates on demand.
**CUPS 2.4.20 has a bug here:** creating the temporary queue fails
(`Bad device URI "://"` in the CUPS error log), so printing fails
([OpenPrinting/cups#1751](https://github.com/OpenPrinting/cups/issues/1751), fixed on
the 2.4.x branch, not yet released). Disc Printer then shows an explanatory message.
Until a CUPS release with the fix is available, set the printer up as a permanent queue
(e.g. in your desktop's printer settings); it is then detected and printed to as usual.

## Features

### Canvas & layers
- Multiple image elements on a single canvas, sorted by configurable z-order
- Per-element 9-handle transform system: drag to move, corner handles to scale
  proportionally, edge handles for axis-only scale, circle handle to rotate freely
- Mouse-wheel zoom on the selected image element
- Text elements with full font, size, style, and colour control
- Double-click a text element on the canvas to edit it in-place

### Print area
- Inner and outer print diameter adjustable below the preview, each with a slider
  (0.5 mm steps) and a number field (0.1 mm; inches with two decimals): inner
  18–50 mm, outer 70–120 mm — for blanks with a different print start and for
  80 mm mini discs (not yet tested on a printer — feedback welcome)
- Presets as shortcuts: **Standard** (inner 50, outer 118 mm) and **Full face**
  (inner 33, outer 118 mm, hub-printable blanks); the matching preset is highlighted
- mm | in switch for all measurements in the app, remembered between starts; the
  decimal separator follows the UI language, input accepts comma and point
- A hint (not a lock) appears when the values leave the usual printable area
  (outer above 118 mm, inner below 21 mm): ink may end up on the disc tray
- The print is masked to the print area: the hub and everything outside the outer
  diameter stay white (no ink); the preview hides the same areas

> **Versions up to 0.1.3 printed into the centre of the disc.** The background and
> artwork reached through the hub; only the outer edge was trimmed at 118 mm. The
> printer does not leave the centre out by itself (confirmed on a Canon TS705a: ink
> residue in the middle of the disc tray), so ink could end up on the hub and, through
> the centre hole, on the tray. 0.2.0 fixes this. If you printed discs with an earlier
> version, clean the centre of the disc tray so dried ink is not transferred to new discs.

### Per-element controls
| Control | Images | Text |
|---|---|---|
| Opacity | ✓ | — |
| Brightness | ✓ | — |
| Contrast | ✓ | — |
| Flip horizontal / vertical | ✓ | — |
| Z-order (↑ / ↓) | ✓ | — |
| Lock (prevent move/scale/rotate) | ✓ | ✓ |
| Visibility toggle | ✓ | ✓ |
| Duplicate | ✓ | ✓ |

### Editing
- **New design** (header bar, left of Open) — starts over as after a fresh start:
  background, image and text elements, print area and undo history are reset; the
  selected printer and the language stay
- **Unsaved changes** — New, Open and closing the window ask first if the design has
  unsaved changes (Cancel / Discard / Save …); Cancel keeps the window open
- **Undo / Redo** (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z) — command history of up to 50 steps
  covering every change to the design: canvas actions (move, scale, rotate, mouse-wheel
  zoom), sliders, the background controls (zoom, arrow buttons, centre), the print area
  (presets, sliders, number fields) and panel operations. Sliders, mouse-wheel zoom and
  repeated arrow-button clicks count as one step per gesture. Not in the history: printer
  selection, language and unit (not part of the design); New and Open replace the design
  and start a fresh history
- Drag-and-drop images from a file manager directly onto the canvas
- Background image with independent position and zoom controls

### File format
- Save and load designs as `.discprint` files (ZIP archive containing `design.json` and
  embedded PNG images) — forward and backward compatible across versions. Since 0.2.0
  the file also stores the outer diameter; older files open with 118 mm, and 0.1.3 opens
  newer files but ignores the outer diameter

### Localisation
34 UI languages: Arabic, Bulgarian, Chinese (Simplified & Traditional), Croatian, Czech,
Danish, Dutch, English, Finnish, French, German, Greek, Hebrew, Hindi, Hungarian,
Indonesian, Italian, Japanese, Korean, Norwegian Bokmål, Persian, Polish, Portuguese,
Romanian, Russian, Serbian, Slovak, Spanish, Swedish, Thai, Turkish, Ukrainian, Vietnamese

#### Translation fixes welcome
German is the source language; the other 33 translations were created by machine and
may contain mistakes or clumsy wording. Corrections are very welcome. The translations
live in `src/disc_printer/locale/<language>/LC_MESSAGES/disc_printer.po` (template:
`src/disc_printer/locale/disc_printer.pot`). You do not need to edit files or send a pull
request — an [issue](https://github.com/MrHaku81/disc-printer/issues) naming the language,
the wrong text and your suggestion is enough.

## Requirements

| Dependency | Package (Arch / Debian) |
|---|---|
| Python ≥ 3.11 | `python` / `python3` |
| GTK 4 + PyGObject | `gtk4 python-gobject` / `python3-gi python3-gi-cairo gir1.2-gtk-4.0` |
| pycairo | `python-cairo` / `python3-cairo` |
| CUPS | `cups` / `cups` |
| numpy | `python-numpy` / `python3-numpy` |
| `ippfind`, `ipptool` *(recommended)* | part of `cups` / `cups-ipp-utils` |
| Pillow *(optional)* | `python-pillow` / `python3-pil` |

> numpy is required. It is used for brightness/contrast adjustment and for the colour
> boost applied to the print output. It is a regular package dependency: `pip`/`pipx`
> install it automatically if it is missing (or reuse the distro package via
> `--system-site-packages`). Only when running directly from the source tree without
> installing does it have to come from the distribution.

> Pillow embeds an sRGB colour profile in the print PNG (written with low compression).
> Without Pillow the PNG is written by Cairo instead — same pixels, lossless, but without
> an embedded colour profile; printing works either way. If the Pillow export fails, Disc
> Printer logs a warning and falls back to Cairo as well.

> `ippfind` and `ipptool` are needed to detect disc support on driverless network
> printers that have no permanent CUPS queue (CUPS creates a temporary queue only when
> printing). Without them such printers are not offered; printers with a configured
> queue are unaffected. A warning is written to the log if the tools are missing.

## Installation

### Flatpak (any distro)

Download `disc-printer.flatpak` from the
[latest release](https://github.com/MrHaku81/disc-printer/releases/latest), then:

```bash
# Install the bundle
flatpak install --user ./disc-printer.flatpak

# Run
flatpak run de.haku.disc-printer
```

> The Flatpak bundle includes numpy, Pillow, the CUPS client tools (`lp`, `lpstat`, `lpoptions`),
> and all Python dependencies. It runs on the GNOME Platform 51 runtime, which Flatpak
> downloads from Flathub automatically on the first install (a few hundred MB). Coming
> from an older version, `flatpak uninstall --unused` removes the previous runtime.

### Arch Linux / CachyOS / Manjaro (AUR)

Disc Printer is available in the AUR as
[`disc-printer`](https://aur.archlinux.org/packages/disc-printer). Install it with `yay`
(or any other AUR helper):

```bash
yay -S disc-printer
```

### From Git (pipx)

PyGObject and pycairo must come from the distribution package — building them
inside a pip-managed environment is painful and fragile. `pipx` with
`--system-site-packages` installs Disc Printer into an isolated venv that can
still see the distro-provided GTK bindings. numpy is installed automatically
(from PyPI, unless the distro package is already present).

#### Arch Linux / CachyOS / Manjaro

```bash
sudo pacman -S gtk4 python-gobject python-cairo cups python-pillow python-pipx
pipx install --system-site-packages git+https://github.com/MrHaku81/disc-printer.git
```

#### Debian / Ubuntu / Linux Mint

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
                 python3-cairo cups cups-ipp-utils python3-pil pipx
pipx install --system-site-packages git+https://github.com/MrHaku81/disc-printer.git
```

### From source

```bash
git clone https://github.com/MrHaku81/disc-printer.git
cd disc-printer
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e .
.venv/bin/disc-printer
```

`pip install -e .` compiles the translations (`.po` → `.mo`) automatically via the
Hatch build hook. After editing a `.po` file, run `make compile-mo` (or reinstall) to
pick up the change.

### Running

```bash
disc-printer
```

Or directly from the source tree, without installing. The package lives under `src/`,
so it has to be put on the module path. Translations are not stored in git, so compile
them first — otherwise the interface stays in German (the source language):

```bash
make compile-mo                      # needs msgfmt (GNU gettext)
PYTHONPATH=src python3 -m disc_printer
```

### Log file

For bug reports, please attach the log file:

| Installation | Log file |
|---|---|
| AUR, pipx, from source | `~/.local/state/disc-printer/disc-printer.log` |
| Flatpak | `~/.var/app/de.haku.disc-printer/.local/state/disc-printer/disc-printer.log` |

If `XDG_STATE_HOME` is set, the native path is `$XDG_STATE_HOME/disc-printer/disc-printer.log`.
The file is created on the first log entry. Version 0.1.2 and earlier wrote
`~/disc-printer.log`; that file is no longer written and can be deleted.
`DISC_PRINTER_LOG_FILE=/path/to/file` writes the log elsewhere; set but empty, it turns
the log file off.

## How it works

1. **Printer detection** — on startup, Disc Printer queries CUPS for all installed
   printers and inspects their PPD files for disc-tray media keywords; driverless network
   printers without a permanent queue are additionally queried via IPP (see
   [Driverless printers](#driverless-printers-no-permanent-cups-queue)). Only matching
   printers are shown in the dropdown.
2. **Design** — place images and text on the circular canvas. The canvas represents the
   full 120 mm disc; the hub and the ring outside the outer print diameter are covered,
   exactly as in the print.
3. **Print** — clicking Print renders the design to a 300 DPI PNG of the 120 mm disc,
   masked to the print area (white inside the inner and outside the outer diameter), and
   submits it to CUPS with the correct media and tray options extracted from the PPD.

## Project layout

```
src/disc_printer/
├── __init__.py        # GI version pinning (GTK 4), exports the logger
├── __main__.py        # `python -m disc_printer` entry point
├── gui/
│   ├── __init__.py
│   ├── canvas.py      # Cairo drawing area, handles, drag/rotate/scale
│   ├── dialogs.py     # Text-edit dialog
│   └── window.py      # Main GTK4 window, panel, undo/redo wiring, main()
├── constants.py       # Disc size, print-area ranges/presets/hints, print resolution, app ID
├── detection.py       # Printer discovery (lpstat, PPD, lpoptions, CUPS HTTP, IPP)
├── file_format.py     # .discprint save / load (ZIP + JSON)
├── history.py         # Command-pattern undo/redo stack
├── i18n.py            # gettext localisation
├── image_utils.py     # Pixbuf → Cairo, print colour boost, print PNG export
├── _log.py            # Logging to the log file (opened on first use) and the console
├── model.py           # DesignState, ImageElement, TextElement
├── paths.py           # Design folder (XDG documents dir, legacy ~/Dokumente), log file path
├── printer.py         # DiscPrinter dataclass + lp options
├── settings.py        # User settings (~/.config/disc-printer/settings.json)
├── units.py           # mm / inch display and input (decimal separator per language)
└── locale/            # 33 translations (.po; .mo compiled at build time),
                       # disc_printer.pot template, LINGUAS;
                       # German is the source language
tests/                 # unit tests (detection, print errors, i18n, units, print area,
                       # design folder, log file, start without display) and GUI
                       # scenarios on a private Broadway server
```

## License

MIT, see [LICENSE](LICENSE).

The application icon (`flatpak/de.haku.disc-printer.svg`, one drawing for all
sizes) was designed by Klaus together with Claude and is licensed under the
same MIT license as the project.
