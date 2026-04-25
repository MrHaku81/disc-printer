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

**Tested printer:** Canon PIXMA TS700 series

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
| numpy *(recommended)* | `python-numpy` / `python3-numpy` |

> numpy is optional but required for brightness/contrast adjustment. Without it those
> sliders have no effect at runtime.

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

### Arch Linux / CachyOS / Manjaro

```bash
sudo pacman -S python-gobject python-cairo cups python-numpy
pip install --user disc-printer
```

### Debian / Ubuntu / Linux Mint

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
                 python3-cairo cups python3-numpy
pip install --user disc-printer
```

### From source

```bash
git clone git@github.com:MrHaku81/disc-printer.git
cd disc-printer
pip install -e . --break-system-packages
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
