# Disc Printer

A universal disc label editor for Linux — design and print CD, DVD, and Blu-ray labels
directly from a GTK4 application, without proprietary software or manufacturer lock-in.

Disc Printer detects compatible printers automatically by analysing their installed PPD
files for disc-tray media support (Canon, Epson, and others). The print output is a
300 DPI PNG rendered at the exact printable area of the disc, sent to CUPS via `lp`.

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

### Per-element controls
| Control | Images | Text |
|---|---|---|
| Opacity | ✓ | — |
| Brightness | ✓ | — |
| Contrast | ✓ | — |
| Flip horizontal / vertical | ✓ | — |
| Z-order (↑ / ↓) | ✓ | ✓ |
| Lock (prevent move/scale/rotate) | ✓ | ✓ |
| Visibility toggle | ✓ | ✓ |
| Duplicate | ✓ | ✓ |

### Editing
- **Undo / Redo** (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z) — full command history, up to 50 steps,
  covering all canvas actions, slider changes (debounced), and panel operations
- Drag-and-drop images from a file manager directly onto the canvas
- Background image with independent position and zoom controls

### File format
- Save and load designs as `.discprint` files (ZIP archive containing `design.json` and
  embedded PNG images) — forward and backward compatible across versions

### Localisation
34 UI languages: Arabic, Bulgarian, Chinese (Simplified & Traditional), Croatian, Czech,
Danish, Dutch, English, Finnish, French, German, Greek, Hebrew, Hindi, Hungarian,
Indonesian, Italian, Japanese, Korean, Norwegian Bokmål, Persian, Polish, Portuguese,
Romanian, Russian, Serbian, Slovak, Spanish, Swedish, Thai, Turkish, Ukrainian, Vietnamese

## Requirements

| Dependency | Package (Arch / Debian) |
|---|---|
| Python ≥ 3.11 | `python` / `python3` |
| GTK 4 + PyGObject | `python-gobject` / `python3-gi python3-gi-cairo gir1.2-gtk-4.0` |
| pycairo | `python-cairo` / `python3-cairo` |
| CUPS | `cups` / `cups` |
| `ippfind`, `ipptool` *(recommended)* | part of `cups` / `cups-ipp-utils` |
| numpy *(recommended)* | `python-numpy` / `python3-numpy` |

> numpy is optional but required for brightness/contrast adjustment. Without it those
> sliders have no effect at runtime.

> `ippfind` and `ipptool` are needed to detect disc support on driverless network
> printers that have no permanent CUPS queue (CUPS creates a temporary queue only when
> printing). Without them such printers are not offered; printers with a configured
> queue are unaffected. A warning is written to the log if the tools are missing.

## Installation

### Flatpak (any distro)

Download the pre-built bundle from the [releases page](https://github.com/MrHaku81/disc-printer/releases)
or directly from the repository:

```bash
# Install the bundle
flatpak install --user disc-printer.flatpak

# Run
flatpak run de.haku.disc-printer
```

> The Flatpak bundle includes numpy, the CUPS client tools (`lp`, `lpstat`, `lpoptions`),
> and all Python dependencies. You only need the GNOME Platform 47 runtime:
> ```bash
> flatpak install flathub org.gnome.Platform//47
> ```

### From Git (pipx)

PyGObject and pycairo must come from the distribution package — building them
inside a pip-managed environment is painful and fragile. `pipx` with
`--system-site-packages` installs Disc Printer into an isolated venv that can
still see the distro-provided GTK bindings.

#### Arch Linux / CachyOS / Manjaro

```bash
sudo pacman -S python-gobject python-cairo cups python-numpy python-pipx
pipx install --system-site-packages git+https://github.com/MrHaku81/disc-printer.git
```

#### Debian / Ubuntu / Linux Mint

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
                 python3-cairo cups python3-numpy pipx
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

### Running

```bash
disc-printer
```

Or directly from the source tree:

```bash
python -m disc_printer
```

## How it works

1. **Printer detection** — on startup, Disc Printer queries CUPS for all installed
   printers and inspects their PPD files for disc-tray media keywords. Only matching
   printers are shown in the dropdown.
2. **Design** — place images and text on the circular canvas. The canvas represents the
   full 120 mm disc; the printable ring (outer–hub boundary) is highlighted.
3. **Print** — clicking Print renders the design to a 300 DPI PNG and submits it to CUPS
   with the correct media and tray options extracted from the PPD.

## Project layout

```
src/disc_printer/
├── gui/
│   ├── canvas.py      # Cairo drawing area, handles, drag/rotate/scale
│   ├── dialogs.py     # Text-edit dialog
│   └── window.py      # Main GTK4 window, panel, undo/redo wiring
├── history.py         # Command-pattern undo/redo stack
├── model.py           # DesignState, ImageElement, TextElement
├── file_format.py     # .discprint save / load (ZIP + JSON)
├── detection.py       # PPD-based printer discovery
├── printer.py         # DiscPrinter dataclass + lp options
├── i18n.py            # gettext localisation
└── locale/            # 34 language catalogues (.po / .mo)
```

## License

MIT — see [LICENSE](LICENSE) if present, otherwise assume MIT until a LICENSE file is added.
