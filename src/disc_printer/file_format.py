from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import cairo
from gi.repository import Pango

from ._log import log
from .model import DesignState, TextElement, ImageElement


DESIGN_JSON    = "design.json"
FORMAT_VERSION = 2
DEFAULT_DIR    = Path.home() / "Dokumente" / "DiscPrinter"


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        round(r * 255), round(g * 255), round(b * 255)
    )


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0


def save(path: str | Path, state: DesignState, hub_mm: float) -> None:
    """Speichert DesignState als .discprint ZIP-Datei (Format v2)."""
    img_files: dict[str, bytes] = {}
    elements:  list[dict]       = []

    # Neue ImageElements
    for i, img in enumerate(state.images):
        fname = f"img_{i}.png"
        buf = io.BytesIO()
        img.surface.write_to_png(buf)
        img_files[fname] = buf.getvalue()
        elements.append({
            "type":     "image",
            "file":     fname,
            "x":        img.x,
            "y":        img.y,
            "scale_x":  img.scale_x,
            "scale_y":  img.scale_y,
            "rotation": img.rotation,
            "z":        img.z,
            "opacity":  img.opacity,
            "flip_h":     img.flip_h,
            "flip_v":     img.flip_v,
            "locked":     img.locked,
            "visible":    img.visible,
            "brightness": img.brightness,
            "contrast":   img.contrast,
        })

    # TextElements
    for elem in state.elements:
        r, g, b, _a = elem.color
        elements.append({
            "type":     "text",
            "content":  elem.text,
            "x":        elem.x_mm,
            "y":        elem.y_mm,
            "font":     elem.font_desc_str,
            "color":    _rgb_to_hex(r, g, b),
            "rotation": 0.0,
            "z":        elem.z,
            "locked":   elem.locked,
            "visible":  elem.visible,
        })

    bg_r, bg_g, bg_b, _ = state.bg_color
    design: dict = {
        "version":          FORMAT_VERSION,
        "hub_size":         hub_mm,
        "background_color": _rgb_to_hex(bg_r, bg_g, bg_b),
        "elements":         elements,
    }

    # Legacy Hintergrundbild separat
    if state.bg_surface is not None:
        buf = io.BytesIO()
        state.bg_surface.write_to_png(buf)
        img_files["bg.png"] = buf.getvalue()
        design["bg_image"] = {
            "file":  "bg.png",
            "x":     state.bg_img_x_mm,
            "y":     state.bg_img_y_mm,
            "scale": state.bg_img_scale,
        }

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(DESIGN_JSON, json.dumps(design, indent=2, ensure_ascii=False))
        for name, data in img_files.items():
            zf.writestr(name, data)

    log.info(f"Design gespeichert: {path}")


def load(path: str | Path) -> tuple[DesignState, float]:
    """Lädt eine .discprint Datei. Gibt (DesignState, hub_mm) zurück."""
    with zipfile.ZipFile(path, "r") as zf:
        design: dict = json.loads(zf.read(DESIGN_JSON))
        img_data: dict[str, bytes] = {
            name: zf.read(name)
            for name in zf.namelist()
            if name != DESIGN_JSON
        }

    version  = int(design.get("version", 1))
    hub_mm   = float(design.get("hub_size", 50))
    bg_r, bg_g, bg_b = _hex_to_rgb(design.get("background_color", "#ffffff"))

    state = DesignState()
    state.set_bg_color(bg_r, bg_g, bg_b, 1.0)

    # Legacy Hintergrundbild (v2: eigener Schlüssel; v1: erstes type="image" Element)
    if version >= 2 and "bg_image" in design:
        info  = design["bg_image"]
        fname = info.get("file", "bg.png")
        if fname in img_data:
            state.set_bg_image(
                cairo.ImageSurface.create_from_png(io.BytesIO(img_data[fname])), "")
            state.bg_img_x_mm  = float(info.get("x", 0.0))
            state.bg_img_y_mm  = float(info.get("y", 0.0))
            state.bg_img_scale = float(info.get("scale", 1.0))

    for elem_d in sorted(design.get("elements", []), key=lambda e: e.get("z", 0)):
        etype = elem_d.get("type")

        if etype == "image":
            fname = elem_d.get("file", "")
            if fname not in img_data:
                continue
            surface = cairo.ImageSurface.create_from_png(io.BytesIO(img_data[fname]))

            if version == 1:
                # v1-Kompatibilität: Bild war das Legacy-Hintergrundbild
                state.set_bg_image(surface, "")
                state.bg_img_x_mm  = float(elem_d.get("x", 0.0))
                state.bg_img_y_mm  = float(elem_d.get("y", 0.0))
                state.bg_img_scale = float(elem_d.get("scale_x", 1.0))
            else:
                state.images.append(ImageElement(
                    surface   = surface,
                    file_path = fname,
                    x         = float(elem_d.get("x", 0.0)),
                    y         = float(elem_d.get("y", 0.0)),
                    scale_x   = float(elem_d.get("scale_x", 1.0)),
                    scale_y   = float(elem_d.get("scale_y", 1.0)),
                    rotation  = float(elem_d.get("rotation", 0.0)),
                    opacity   = float(elem_d.get("opacity", 1.0)),
                    z         = int(elem_d.get("z", 0)),
                    flip_h    = bool(elem_d.get("flip_h", False)),
                    flip_v    = bool(elem_d.get("flip_v", False)),
                    locked     = bool(elem_d.get("locked",     False)),
                    visible    = bool(elem_d.get("visible",    True)),
                    brightness = float(elem_d.get("brightness", 1.0)),
                    contrast   = float(elem_d.get("contrast",   1.0)),
                ))

        elif etype == "text":
            desc     = Pango.FontDescription.from_string(elem_d.get("font", "Sans 24"))
            family   = desc.get_family() or "Sans"
            raw_size = desc.get_size()
            size_pt  = (raw_size / Pango.SCALE) if raw_size > 0 else 24.0
            bold     = desc.get_weight() >= Pango.Weight.BOLD
            italic   = desc.get_style() == Pango.Style.ITALIC
            cr, cg, cb = _hex_to_rgb(elem_d.get("color", "#000000"))
            t = TextElement(
                text         = elem_d.get("content", ""),
                font_family  = family,
                font_size_pt = size_pt,
                bold         = bold,
                italic       = italic,
                color        = (cr, cg, cb, 1.0),
                x_mm         = float(elem_d.get("x", 0.0)),
                y_mm         = float(elem_d.get("y", 0.0)),
                z            = int(elem_d.get("z", 100)),
            )
            t.locked  = bool(elem_d.get("locked", False))
            t.visible = bool(elem_d.get("visible", True))
            state.elements.append(t)

    n_img = len(state.images)
    n_txt = len(state.elements)
    log.info(
        f"Design geladen: {path} "
        f"(v{version}, hub={hub_mm}mm, {n_img} Bild(er), {n_txt} Text(e))"
    )
    return state, hub_mm
