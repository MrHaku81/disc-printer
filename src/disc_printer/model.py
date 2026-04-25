from __future__ import annotations

from pathlib import Path

import cairo
from gi.repository import Pango


class TextElement:
    """Ein Text-Label auf der Disc. Positions- und Größenangaben in mm bzw. pt."""

    _counter = 0

    def __init__(self, text: str,
                 font_family: str, font_size_pt: float,
                 bold: bool, italic: bool,
                 color: tuple[float, float, float, float],
                 x_mm: float = 0.0, y_mm: float = 0.0,
                 z: int = 100):
        TextElement._counter += 1
        self.id           = TextElement._counter
        self.text         = text
        self.font_family  = font_family
        self.font_size_pt = font_size_pt
        self.bold         = bold
        self.italic       = italic
        self.color        = color
        self.x_mm         = x_mm
        self.y_mm         = y_mm
        self.z            = z
        self.selected     = False
        self.locked       = False
        self.visible      = True
        self._bbox: tuple[float, float, float, float] | None = None

    @property
    def font_desc_str(self) -> str:
        style = ""
        if self.bold:   style += " Bold"
        if self.italic: style += " Italic"
        return f"{self.font_family}{style} {self.font_size_pt:.0f}"

    @property
    def display_text(self) -> str:
        preview = self.text.replace("\n", " ")
        return preview[:28] + ("…" if len(preview) > 28 else "")

    def pango_desc(self, scale: float = 1.0) -> Pango.FontDescription:
        desc = Pango.FontDescription()
        desc.set_family(self.font_family)
        desc.set_size(round(self.font_size_pt * scale * Pango.SCALE))
        desc.set_weight(Pango.Weight.BOLD   if self.bold   else Pango.Weight.NORMAL)
        desc.set_style(Pango.Style.ITALIC   if self.italic else Pango.Style.NORMAL)
        return desc


class ImageElement:
    """Ein Bildelement auf der Disc mit vollem Transformations-Support."""

    _counter = 0

    def __init__(self, surface: cairo.ImageSurface, file_path: str = "",
                 x: float = 0.0, y: float = 0.0,
                 scale_x: float = 1.0, scale_y: float = 1.0,
                 rotation: float = 0.0, opacity: float = 1.0,
                 z: int = 0, flip_h: bool = False, flip_v: bool = False,
                 locked: bool = False, visible: bool = True,
                 brightness: float = 1.0, contrast: float = 1.0):
        ImageElement._counter += 1
        self.id         = ImageElement._counter
        self.surface    = surface
        self.file_path  = file_path
        self.x          = x
        self.y          = y
        self.scale_x    = scale_x
        self.scale_y    = scale_y
        self.rotation   = rotation   # Grad
        self.opacity    = opacity
        self.z          = z
        self.flip_h     = flip_h
        self.flip_v     = flip_v
        self.locked     = locked
        self.visible    = visible
        self.brightness = brightness
        self.contrast   = contrast
        self.selected   = False
        # Wird während _draw gesetzt für Hit-Testing und Handles
        self._bbox:     tuple[float, float, float, float] | None = None
        self._draw_cx:  float = 0.0   # Mittelpunkt in Screen-Px
        self._draw_cy:  float = 0.0
        self._draw_hw:  float = 0.0   # Halbbreite in Screen-Px (ohne Rotation)
        self._draw_hh:  float = 0.0   # Halbhöhe in Screen-Px (ohne Rotation)
        self._draw_rot: float = 0.0   # Rotation in Radiant
        # Render-Cache für Helligkeit/Kontrast
        self._adj_surf: cairo.ImageSurface | None = None
        self._adj_b:    float = -1.0
        self._adj_c:    float = -1.0

    @property
    def display_name(self) -> str:
        name = Path(self.file_path).name if self.file_path else "Bild"
        return name[:30] + ("…" if len(name) > 30 else "")


class DesignState:
    """Hält den gesamten Designzustand (Hintergrund + Bilder + Text-Elemente)."""

    def __init__(self):
        self.bg_color:   tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
        # Legacy Hintergrundbild (einfaches bg ohne Rotation/Flip)
        self.bg_surface: cairo.ImageSurface | None = None
        self.bg_path:    str   = ""
        self.bg_img_x_mm:  float = 0.0
        self.bg_img_y_mm:  float = 0.0
        self.bg_img_scale: float = 1.0
        # Ebenen-Elemente
        self.elements:   list[TextElement]  = []
        self.images:     list[ImageElement] = []
        # Selektion
        self.selected_element: TextElement  | None = None
        self.selected_image:   ImageElement | None = None

    def set_bg_color(self, r: float, g: float, b: float, a: float = 1.0) -> None:
        self.bg_color = (r, g, b, a)

    def set_bg_image(self, surface: cairo.ImageSurface, path: str) -> None:
        self.bg_surface = surface
        self.bg_path    = path

    def clear_bg_image(self) -> None:
        self.bg_surface = None
        self.bg_path    = ""
        self.reset_bg_transform()

    def reset_bg_transform(self) -> None:
        self.bg_img_x_mm  = 0.0
        self.bg_img_y_mm  = 0.0
        self.bg_img_scale = 1.0

    def all_sorted(self) -> list:
        """Alle ImageElement und TextElement nach z-Wert sortiert (Bilder vor Text bei gleichem z)."""
        def key(e: ImageElement | TextElement):
            return (e.z, isinstance(e, TextElement))
        return sorted(list(self.images) + list(self.elements), key=key)
