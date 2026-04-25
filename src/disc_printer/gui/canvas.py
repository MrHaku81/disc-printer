from __future__ import annotations

import math

import cairo
import numpy as np
from gi.repository import Gtk, Gdk, Gio, Pango, PangoCairo

from .._log import log
from ..constants import (
    DISC_MM, PRINTABLE_MM, HUB_LARGE_MM, PREVIEW_PX, PRINT_PPM, PRINT_PX,
)
from ..i18n import _
from ..model import TextElement, ImageElement, DesignState
from ..image_utils import boost_cairo_surface, is_image_path


def _apply_bc(surface: cairo.ImageSurface,
              brightness: float, contrast: float) -> cairo.ImageSurface:
    """Return a new surface with brightness/contrast applied. Original unchanged.

    Cairo ARGB32 stores pre-multiplied BGRA bytes (little-endian).
    We un-premultiply, apply adjustments, then re-premultiply.
    """
    w = surface.get_width()
    h = surface.get_height()
    stride = surface.get_stride()

    src = np.frombuffer(bytes(surface.get_data()), dtype=np.uint8)
    src = src.reshape(h, stride // 4, 4)[:, :w, :].copy().astype(np.float32)

    bgr = src[:, :, :3]
    alpha = src[:, :, 3]
    a_n = alpha / 255.0                         # normalised alpha

    # Unpremultiply RGB
    safe = np.where(a_n > 0, a_n, 1.0)
    straight = np.where(
        a_n[:, :, None] > 0,
        bgr / (safe[:, :, None] * 255.0),
        0.0,
    )

    # Contrast: (x - 0.5) * c + 0.5, then brightness: x * b
    adj = (straight - 0.5) * contrast + 0.5
    adj = np.clip(adj * brightness, 0.0, 1.0)

    # Repremultiply and convert back to uint8
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[:, :, :3] = (adj * a_n[:, :, None] * 255.0 + 0.5).astype(np.uint8)
    out[:, :, 3]  = alpha.astype(np.uint8)

    new_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    dst_stride = new_surf.get_stride()
    dst = np.frombuffer(new_surf.get_data(), dtype=np.uint8).reshape(h, dst_stride)
    dst[:, :w * 4] = out.reshape(h, w * 4)
    new_surf.mark_dirty()
    return new_surf


# Handle-Indizes (9 gesamt)
_H_TL, _H_TC, _H_TR = 0, 1, 2
_H_ML, _H_MR        = 3, 4
_H_BL, _H_BC, _H_BR = 5, 6, 7
_H_ROT               = 8

_HANDLE_HALF = 5    # halbe Handle-Quadratgröße in Px
_ROT_OFFSET  = 22   # Abstand Rotations-Handle über Oberkante in Px


def _in_rotated_rect(mx: float, my: float,
                     cx: float, cy: float,
                     hw: float, hh: float, rot: float) -> bool:
    """Prüft ob (mx,my) im rotierten Rechteck liegt."""
    dx = mx - cx
    dy = my - cy
    lx =  dx * math.cos(rot) + dy * math.sin(rot)
    ly = -dx * math.sin(rot) + dy * math.cos(rot)
    return abs(lx) <= hw and abs(ly) <= hh


def _handle_positions(cx: float, cy: float,
                      hw: float, hh: float, rot: float) -> list[tuple[float, float]]:
    """9 Handle-Positionen für ein Bild-Element."""
    def rp(lx: float, ly: float) -> tuple[float, float]:
        c, s = math.cos(rot), math.sin(rot)
        return (cx + lx * c - ly * s, cy + lx * s + ly * c)
    return [
        rp(-hw, -hh),                   # 0 TL
        rp(  0, -hh),                   # 1 TC
        rp( hw, -hh),                   # 2 TR
        rp(-hw,   0),                   # 3 ML
        rp( hw,   0),                   # 4 MR
        rp(-hw,  hh),                   # 5 BL
        rp(  0,  hh),                   # 6 BC
        rp( hw,  hh),                   # 7 BR
        rp(  0, -hh - _ROT_OFFSET),     # 8 ROT
    ]


class DiscCanvas(Gtk.DrawingArea):
    """Interaktive Cairo-Disc-Vorschau mit Multi-Bild/Text-Ebenen und Handle-System."""

    _PAD       = 18
    _SCALE_MIN = 0.20
    _SCALE_MAX = 8.0
    _ZOOM_STEP = 0.12

    def __init__(self, state: DesignState,
                 on_file_drop_cb=None,
                 on_scale_changed_cb=None,
                 on_edit_text_cb=None,
                 on_img_select_cb=None,
                 on_transform_cb=None,
                 on_img_zoom_cb=None):
        super().__init__()
        self._state               = state
        self._hub_mm              = HUB_LARGE_MM
        self._on_file_drop_cb     = on_file_drop_cb
        self._on_scale_changed_cb = on_scale_changed_cb
        self._on_edit_text_cb     = on_edit_text_cb
        self._on_img_select_cb    = on_img_select_cb
        self._on_transform_cb     = on_transform_cb   # (elem, start_dict, action_str)
        self._on_img_zoom_cb      = on_img_zoom_cb    # (img, old_sx, old_sy, new_sx, new_sy)

        self._cx:      float = 0.0
        self._cy:      float = 0.0
        self._r_print: float = 0.0
        self._ppm:     float = 1.0

        # Drag-Zustand
        self._drag_target:     object = None   # "bg", TextElement, ImageElement
        self._drag_handle:     int    = -1     # -1=bewegen, 0-7=skalieren, 8=rotieren
        self._drag_sx:         float  = 0.0   # Screen-Startpos beim Drag
        self._drag_sy:         float  = 0.0
        self._drag_start:      dict   = {}    # Snapshot des Elements beim Drag-Beginn
        # Legacy bg-drag
        self._drag_start_bg_x: float  = 0.0
        self._drag_start_bg_y: float  = 0.0

        # Aktuelle Handle-Positionen des selektierten Bild-Elements
        self._img_handles: list[tuple[float, float]] = []

        self.set_content_width(PREVIEW_PX)
        self.set_content_height(PREVIEW_PX)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self._draw)
        self._setup_controllers()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def hub_mm(self) -> float:
        return self._hub_mm

    def set_hub(self, mm: float) -> None:
        self._hub_mm = mm
        self.queue_draw()

    def refresh(self) -> None:
        self.queue_draw()

    def update_cursor(self) -> None:
        has = (self._state.bg_surface is not None
               or self._state.elements
               or self._state.images)
        self.set_cursor(Gdk.Cursor.new_from_name("grab") if has else None)

    # ── Controllers ───────────────────────────────────────────────────────────

    def _setup_controllers(self) -> None:
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_click)
        self.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin",  self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end",    self._on_drag_end)
        self.add_controller(drag)

        scroll = Gtk.EventControllerScroll()
        scroll.set_flags(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_hover_enter)
        motion.connect("leave", self._on_hover_leave)
        self.add_controller(motion)

        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_file_drop)
        self.add_controller(drop)

    # ── Hauptzeichnung ────────────────────────────────────────────────────────

    def _draw(self, _area, cr: cairo.Context, w: int, h: int) -> None:
        size = min(w, h) - 2 * self._PAD
        cx   = w / 2
        cy   = h / 2
        ppm  = size / DISC_MM

        self._cx      = cx
        self._cy      = cy
        self._ppm     = ppm
        self._r_print = PRINTABLE_MM / 2 * ppm

        r_disc  = DISC_MM      / 2 * ppm
        r_print = PRINTABLE_MM / 2 * ppm
        r_hub   = self._hub_mm / 2 * ppm

        # 1 ── Canvas-Hintergrund
        cr.set_source_rgb(0.14, 0.14, 0.16)
        cr.paint()

        # 2 ── Disc-Körper
        cr.set_source_rgb(0.22, 0.22, 0.25)
        cr.arc(cx, cy, r_disc, 0, 2 * math.pi)
        cr.fill()

        # 3 ── Bedruckbare Zone (geclippt)
        cr.save()
        cr.arc(cx, cy, r_print, 0, 2 * math.pi)
        cr.clip()

        cr.set_source_rgba(*self._state.bg_color)
        cr.paint()

        if self._state.bg_surface is not None:
            DiscCanvas._draw_bg_image(cr, self._state, cx, cy, r_print, ppm)

        # Alle Ebenen nach z sortiert rendern (unsichtbare überspringen)
        for elem in self._state.all_sorted():
            if isinstance(elem, ImageElement):
                if elem.visible:
                    DiscCanvas._draw_image_elem(cr, elem, cx, cy, ppm)
            elif isinstance(elem, TextElement):
                if elem.visible:
                    DiscCanvas._draw_text(cr, elem, cx, cy, ppm)

        cr.restore()

        # 4 ── Hub
        DiscCanvas._draw_hub(cr, cx, cy, r_hub)

        # 5 ── Führungslinie bedruckbare Zone
        cr.set_source_rgba(0.45, 0.45, 0.50, 0.45)
        cr.set_line_width(0.8)
        cr.set_dash([5.0, 4.0])
        cr.arc(cx, cy, r_print, 0, 2 * math.pi)
        cr.stroke()
        cr.set_dash([])

        # 6 ── Außenrand
        cr.set_source_rgba(0.50, 0.50, 0.55, 0.50)
        cr.set_line_width(1.2)
        cr.arc(cx, cy, r_disc, 0, 2 * math.pi)
        cr.stroke()

        # 7 ── Selektionsrahmen / Handles (außerhalb Clip)
        for elem in self._state.elements:
            if elem.selected and elem._bbox and elem.visible:
                self._draw_text_selection(cr, elem._bbox, locked=elem.locked)

        sel_img = self._state.selected_image
        if sel_img is not None and sel_img.surface is not None and sel_img.visible:
            # Robuster Fallback: _draw_hw neu berechnen falls _draw_image_elem
            # es noch nicht gesetzt hat (z. B. Element außerhalb des Clipping-Bereichs)
            if sel_img._draw_hw == 0:
                iw = sel_img.surface.get_width()
                ih = sel_img.surface.get_height()
                sel_img._draw_cx  = cx + sel_img.x * ppm
                sel_img._draw_cy  = cy + sel_img.y * ppm
                sel_img._draw_rot = math.radians(sel_img.rotation)
                sel_img._draw_hw  = iw * abs(sel_img.scale_x) * ppm / PRINT_PPM / 2
                sel_img._draw_hh  = ih * abs(sel_img.scale_y) * ppm / PRINT_PPM / 2
                log.debug(
                    f"Handle-Fallback: '{sel_img.display_name}' "
                    f"cx={sel_img._draw_cx:.1f} cy={sel_img._draw_cy:.1f} "
                    f"hw={sel_img._draw_hw:.1f} hh={sel_img._draw_hh:.1f}"
                )
            try:
                self._img_handles = self._draw_img_handles(
                    cr, sel_img, locked=sel_img.locked
                )
            except Exception as exc:
                log.error(f"Handle-Drawing fehlgeschlagen: {exc}")
                self._img_handles = []
        else:
            self._img_handles = []

        # 8 ── Maß-Labels
        self._labels(cr, cx, cy, size, r_disc, r_hub)

    # ── Bild-Element Rendering ────────────────────────────────────────────────

    @staticmethod
    def _draw_image_elem(cr: cairo.Context,
                         elem: ImageElement,
                         cx: float, cy: float, ppm: float) -> None:
        iw = elem.surface.get_width()
        ih = elem.surface.get_height()

        # scale_x/y = 1.0 → Bild hat natürliche Druckgröße (1 Bildpx = 1 Druckpx)
        sc_x = elem.scale_x * ppm / PRINT_PPM
        sc_y = elem.scale_y * ppm / PRINT_PPM
        if elem.flip_h: sc_x = -sc_x
        if elem.flip_v: sc_y = -sc_y

        px  = cx + elem.x * ppm
        py  = cy + elem.y * ppm
        rad = math.radians(elem.rotation)

        hw = iw * abs(elem.scale_x * ppm / PRINT_PPM) / 2
        hh = ih * abs(elem.scale_y * ppm / PRINT_PPM) / 2
        cos_r = abs(math.cos(rad))
        sin_r = abs(math.sin(rad))

        elem._bbox     = (px - hw*cos_r - hh*sin_r, py - hw*sin_r - hh*cos_r,
                          (hw*cos_r + hh*sin_r)*2,  (hw*sin_r + hh*cos_r)*2)
        elem._draw_cx  = px
        elem._draw_cy  = py
        elem._draw_hw  = hw
        elem._draw_hh  = hh
        elem._draw_rot = rad

        # Helligkeit/Kontrast — gecachte angepasste Surface verwenden
        surf = elem.surface
        if abs(elem.brightness - 1.0) > 1e-4 or abs(elem.contrast - 1.0) > 1e-4:
            if (elem._adj_surf is None
                    or abs(elem._adj_b - elem.brightness) > 1e-6
                    or abs(elem._adj_c - elem.contrast) > 1e-6):
                elem._adj_surf = _apply_bc(elem.surface, elem.brightness, elem.contrast)
                elem._adj_b    = elem.brightness
                elem._adj_c    = elem.contrast
            surf = elem._adj_surf

        cr.save()
        cr.translate(px, py)
        cr.rotate(rad)
        cr.scale(sc_x, sc_y)
        cr.translate(-iw / 2, -ih / 2)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.Filter.BILINEAR)
        cr.paint_with_alpha(elem.opacity)
        cr.restore()

    # ── Handle-System ─────────────────────────────────────────────────────────

    def _draw_img_handles(self, cr: cairo.Context,
                          elem: ImageElement,
                          locked: bool = False) -> list[tuple[float, float]]:
        handles = _handle_positions(
            elem._draw_cx, elem._draw_cy,
            elem._draw_hw, elem._draw_hh, elem._draw_rot
        )
        hs = _HANDLE_HALF

        # Rahmen (gestrichelt) – grau bei gesperrtem Element
        cr.save()
        if locked:
            cr.set_source_rgba(0.55, 0.55, 0.60, 0.70)
        else:
            cr.set_source_rgba(0.25, 0.55, 1.0, 0.75)
        cr.set_line_width(1.5)
        cr.set_dash([4.0, 3.0])
        order = [_H_TL, _H_TR, _H_BR, _H_BL]
        cr.move_to(*handles[order[0]])
        for i in order[1:]:
            cr.line_to(*handles[i])
        cr.close_path()
        cr.stroke()
        cr.set_dash([])
        cr.restore()

        if locked:
            # Kein Rotations-Handle, keine interaktiven Handles
            return []

        cr.save()
        # Linie TC → ROT
        cr.set_source_rgba(0.25, 0.55, 1.0, 0.75)
        cr.set_line_width(1.2)
        cr.move_to(*handles[_H_TC])
        cr.line_to(*handles[_H_ROT])
        cr.stroke()
        cr.restore()

        # Eck- und Seiten-Handles (Quadrate)
        for hx, hy in handles[:8]:
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.92)
            cr.rectangle(hx - hs, hy - hs, hs * 2, hs * 2)
            cr.fill()
            cr.set_source_rgba(0.25, 0.55, 1.0, 1.0)
            cr.set_line_width(1.2)
            cr.rectangle(hx - hs, hy - hs, hs * 2, hs * 2)
            cr.stroke()

        # Rotations-Handle (Kreis)
        rx, ry = handles[_H_ROT]
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.92)
        cr.arc(rx, ry, hs + 2, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(0.35, 0.65, 1.0, 1.0)
        cr.set_line_width(1.5)
        cr.arc(rx, ry, hs + 2, 0, 2 * math.pi)
        cr.stroke()

        return handles

    def _hit_handle_idx(self, x: float, y: float) -> int:
        """Gibt Handle-Index zurück oder -1 wenn kein Treffer."""
        if not self._img_handles:
            return -1
        hs = _HANDLE_HALF + 3
        for i, (hx, hy) in enumerate(self._img_handles):
            r = hs + 2 if i == _H_ROT else hs
            if abs(x - hx) <= r and abs(y - hy) <= r:
                return i
        return -1

    # ── Hintergrundbild (Legacy) ───────────────────────────────────────────────

    @staticmethod
    def _draw_bg_image(cr: cairo.Context, state: DesignState,
                       cx: float, cy: float,
                       r_print: float, ppm: float) -> None:
        surf = state.bg_surface
        iw   = surf.get_width()
        ih   = surf.get_height()
        diam = r_print * 2
        base = max(diam / iw, diam / ih)
        sc   = base * state.bg_img_scale
        ox   = state.bg_img_x_mm * ppm
        oy   = state.bg_img_y_mm * ppm

        cr.save()
        cr.translate(cx + ox, cy + oy)
        cr.scale(sc, sc)
        cr.translate(-iw / 2, -ih / 2)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.Filter.BILINEAR)
        cr.paint()
        cr.restore()

    # ── Text-Rendering ────────────────────────────────────────────────────────

    @staticmethod
    def _draw_text(cr: cairo.Context,
                   elem: TextElement, cx: float, cy: float, ppm: float) -> None:
        if not elem.text.strip():
            return

        pt_scale = ppm / PRINT_PPM
        layout = PangoCairo.create_layout(cr)
        layout.set_text(elem.text, -1)
        layout.set_font_description(elem.pango_desc(pt_scale))

        _ink, logical = layout.get_extents()
        tw   = logical.width  / Pango.SCALE
        th   = logical.height / Pango.SCALE
        lo_x = logical.x / Pango.SCALE
        lo_y = logical.y / Pango.SCALE

        ex = cx + elem.x_mm * ppm - tw / 2 - lo_x
        ey = cy + elem.y_mm * ppm - th / 2 - lo_y

        elem._bbox = (ex + lo_x, ey + lo_y, tw, th)

        cr.save()
        cr.translate(ex, ey)
        cr.set_source_rgba(*elem.color)
        PangoCairo.show_layout(cr, layout)
        cr.restore()

    @staticmethod
    def _draw_text_selection(cr: cairo.Context,
                             bbox: tuple[float, float, float, float],
                             locked: bool = False) -> None:
        bx, by, bw, bh = bbox
        m = 4.0
        cr.save()
        if locked:
            cr.set_source_rgba(0.55, 0.55, 0.60, 0.70)
        else:
            cr.set_source_rgba(0.25, 0.55, 1.0, 0.85)
        cr.set_line_width(1.6)
        cr.set_dash([5.0, 3.0])
        cr.rectangle(bx - m, by - m, bw + 2*m, bh + 2*m)
        cr.stroke()
        cr.set_dash([])
        cr.restore()

    # ── Hub ───────────────────────────────────────────────────────────────────

    @staticmethod
    def _draw_hub(cr: cairo.Context, cx: float, cy: float, r_hub: float) -> None:
        grad = cairo.RadialGradient(
            cx - r_hub * 0.30, cy - r_hub * 0.30, 0,
            cx, cy, r_hub,
        )
        grad.add_color_stop_rgb(0.0, 0.80, 0.80, 0.83)
        grad.add_color_stop_rgb(0.6, 0.64, 0.64, 0.68)
        grad.add_color_stop_rgb(1.0, 0.48, 0.48, 0.52)
        cr.set_source(grad)
        cr.arc(cx, cy, r_hub, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgba(0.30, 0.30, 0.34, 0.90)
        cr.set_line_width(1.4)
        cr.arc(cx, cy, r_hub, 0, 2 * math.pi)
        cr.stroke()

        cr.set_source_rgba(0.18, 0.18, 0.20, 0.80)
        cr.arc(cx, cy, 3.0, 0, 2 * math.pi)
        cr.fill()

    # ── Druck-Rendering ───────────────────────────────────────────────────────

    @staticmethod
    def render_for_print(state: DesignState, hub_mm: float) -> cairo.ImageSurface:
        size    = PRINT_PX
        surf    = cairo.ImageSurface(cairo.FORMAT_RGB24, size, size)
        cr      = cairo.Context(surf)
        cx = cy = size / 2.0
        ppm     = PRINT_PPM
        r_print = PRINTABLE_MM / 2 * ppm

        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.paint()

        cr.save()
        cr.arc(cx, cy, r_print, 0, 2 * math.pi)
        cr.clip()

        cr.set_source_rgba(*state.bg_color)
        cr.paint()

        if state.bg_surface is not None:
            orig = state.bg_surface
            state.bg_surface = boost_cairo_surface(orig)
            DiscCanvas._draw_bg_image(cr, state, cx, cy, r_print, ppm)
            state.bg_surface = orig

        for elem in state.all_sorted():
            if isinstance(elem, ImageElement):
                if elem.visible:
                    boosted = boost_cairo_surface(elem.surface)
                    orig_surf = elem.surface
                    elem.surface = boosted
                    DiscCanvas._draw_image_elem(cr, elem, cx, cy, ppm)
                    elem.surface = orig_surf
            elif isinstance(elem, TextElement):
                if elem.visible:
                    DiscCanvas._draw_text(cr, elem, cx, cy, ppm)

        cr.restore()
        return surf

    # ── Maß-Labels ────────────────────────────────────────────────────────────

    def _labels(self, cr: cairo.Context,
                cx: float, cy: float, size: float,
                r_disc: float, r_hub: float) -> None:
        fp = max(10.0, size * 0.038)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)

        def label(text: str, y: float, fs: float = fp,
                  bg_alpha: float = 0.52) -> None:
            cr.set_font_size(fs)
            te    = cr.text_extents(text)
            tx    = cx - te.width / 2 - te.x_bearing
            pad_x = fs * 0.50
            pad_y = fs * 0.28
            rx    = cx - te.width / 2 - pad_x
            ry    = y + te.y_bearing - pad_y
            rw    = te.width  + 2 * pad_x
            rh    = te.height + 2 * pad_y
            rc    = rh / 2

            cr.save()
            cr.set_source_rgba(0.0, 0.0, 0.0, bg_alpha)
            cr.new_path()
            cr.arc(rx + rc,      ry + rc,      rc, math.pi,            3*math.pi/2)
            cr.arc(rx + rw - rc, ry + rc,      rc, 3*math.pi/2,        2*math.pi)
            cr.arc(rx + rw - rc, ry + rh - rc, rc, 0,                  math.pi/2)
            cr.arc(rx + rc,      ry + rh - rc, rc, math.pi/2,          math.pi)
            cr.close_path()
            cr.fill()
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.92)
            cr.move_to(tx, y)
            cr.show_text(text)
            cr.restore()

        label(_("Ø %.0f mm") % self._hub_mm,   cy + fp * 0.35)
        label(_("Hub · nicht bedruckbar"),       cy + fp * 1.55, fp * 0.72, 0.40)

        py = cy + r_hub + fp * 2.5
        if py + fp < cy + r_disc - fp * 0.5:
            label(_("Ø %.0f mm  (bedruckbar)") % PRINTABLE_MM, py, fp * 0.78)

        label(_("Ø %.0f mm") % DISC_MM, cy - r_disc + fp * 1.8, fp * 0.82)

    # ── Hit-Testing ───────────────────────────────────────────────────────────

    @staticmethod
    def _in_bbox(x: float, y: float,
                 bbox: tuple[float, float, float, float]) -> bool:
        bx, by, bw, bh = bbox
        return bx <= x <= bx + bw and by <= y <= by + bh

    def _hit_any(self, x: float, y: float) -> ImageElement | TextElement | None:
        """Treffertest auf alle Elemente, z-sortiert von oben nach unten."""
        for elem in reversed(self._state.all_sorted()):
            if not elem.visible:
                continue
            if isinstance(elem, ImageElement):
                if (elem._draw_hw > 0
                        and _in_rotated_rect(x, y, elem._draw_cx, elem._draw_cy,
                                             elem._draw_hw, elem._draw_hh, elem._draw_rot)):
                    return elem
            elif isinstance(elem, TextElement):
                if elem._bbox and self._in_bbox(x, y, elem._bbox):
                    return elem
        return None

    # ── Selektion ─────────────────────────────────────────────────────────────

    def _select_text(self, elem: TextElement | None) -> None:
        for e in self._state.elements:
            e.selected = False
        if elem is not None:
            elem.selected = True
        self._state.selected_element = elem

    def _select_image(self, elem: ImageElement | None) -> None:
        for e in self._state.images:
            e.selected = False
        if elem is not None:
            elem.selected = True
        self._state.selected_image = elem
        log.debug(
            f"select_image → '{elem.display_name if elem else 'None'}' "
            f"(selected_image is {'set' if self._state.selected_image else 'None'})"
        )
        if self._on_img_select_cb:
            self._on_img_select_cb(elem)

    def _select_any(self, hit: ImageElement | TextElement | None) -> None:
        if isinstance(hit, ImageElement):
            self._select_text(None)
            self._select_image(hit)
        elif isinstance(hit, TextElement):
            self._select_image(None)
            self._select_text(hit)
        else:
            self._select_text(None)
            self._select_image(None)
        self.queue_draw()

    # ── Click-Handler ─────────────────────────────────────────────────────────

    def _on_click(self, gesture: Gtk.GestureClick,
                  n_press: int, x: float, y: float) -> None:
        # Klick auf Handle des selektierten Bilds → Selektion beibehalten
        if self._state.selected_image is not None and self._hit_handle_idx(x, y) >= 0:
            return

        hit = self._hit_any(x, y)
        log.debug(
            f"Click ({x:.0f},{y:.0f}) n={n_press} → "
            f"hit={type(hit).__name__ if hit else 'None'} "
            f"n_imgs={len(self._state.images)} "
            f"hw_list={[f'{e._draw_hw:.1f}' for e in self._state.images]}"
        )

        if n_press == 2 and isinstance(hit, TextElement):
            if self._on_edit_text_cb:
                self._on_edit_text_cb(hit)
            return

        self._select_any(hit)

    # ── Drag-Handler ──────────────────────────────────────────────────────────

    def _on_drag_begin(self, gesture: Gtk.GestureDrag,
                       sx: float, sy: float) -> None:
        self._drag_sx = sx
        self._drag_sy = sy

        # Priorität 1: Handle des selektierten Bilds (nur wenn nicht gesperrt)
        sel_img = self._state.selected_image
        if sel_img is not None and not sel_img.locked and self._img_handles:
            idx = self._hit_handle_idx(sx, sy)
            if idx >= 0:
                self._drag_target = sel_img
                self._drag_handle = idx
                self._drag_start  = {
                    "x": sel_img.x, "y": sel_img.y,
                    "scale_x": sel_img.scale_x, "scale_y": sel_img.scale_y,
                    "rotation": sel_img.rotation,
                    "iw": sel_img.surface.get_width(),
                    "ih": sel_img.surface.get_height(),
                }
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                self.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
                return

        # Priorität 2: Treffertest auf alle Elemente (z-sortiert)
        hit = self._hit_any(sx, sy)

        if isinstance(hit, ImageElement):
            if hit is not sel_img:
                self._select_any(hit)
            if not hit.locked:
                self._drag_target = hit
                self._drag_handle = -1
                self._drag_start  = {"x": hit.x, "y": hit.y}
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                self.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
            return

        if isinstance(hit, TextElement):
            if hit is not self._state.selected_element:
                self._select_any(hit)
            if not hit.locked:
                self._drag_target = hit
                self._drag_handle = -1
                self._drag_start  = {"x": hit.x_mm, "y": hit.y_mm}
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                self.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
            return

        # Priorität 3: Legacy-Hintergrundbild
        if self._state.bg_surface is not None:
            self._drag_target    = "bg"
            self._drag_start_bg_x = self._state.bg_img_x_mm
            self._drag_start_bg_y = self._state.bg_img_y_mm
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
            return

        self._drag_target = None
        gesture.set_state(Gtk.EventSequenceState.DENIED)

    def _on_drag_update(self, gesture: Gtk.GestureDrag,
                        dx: float, dy: float) -> None:
        if self._ppm == 0 or self._drag_target is None:
            return

        if self._drag_target == "bg":
            self._state.bg_img_x_mm = self._drag_start_bg_x + dx / self._ppm
            self._state.bg_img_y_mm = self._drag_start_bg_y + dy / self._ppm
            self.queue_draw()
            return

        if isinstance(self._drag_target, TextElement):
            self._drag_target.x_mm = self._drag_start["x"] + dx / self._ppm
            self._drag_target.y_mm = self._drag_start["y"] + dy / self._ppm
            self.queue_draw()
            return

        if isinstance(self._drag_target, ImageElement):
            img   = self._drag_target
            start = self._drag_start
            h     = self._drag_handle

            if h == -1:
                # Bewegen
                img.x = start["x"] + dx / self._ppm
                img.y = start["y"] + dy / self._ppm

            elif h == _H_ROT:
                # Rotieren
                cx_e = self._cx + start["x"] * self._ppm
                cy_e = self._cy + start["y"] * self._ppm
                a0   = math.atan2(self._drag_sy - cy_e, self._drag_sx - cx_e)
                a1   = math.atan2(self._drag_sy + dy - cy_e,
                                   self._drag_sx + dx - cx_e)
                img.rotation = start["rotation"] + math.degrees(a1 - a0)

            else:
                # Skalieren: Maus in Bild-lokale Koordinaten transformieren
                cx_e   = self._cx + start["x"] * self._ppm
                cy_e   = self._cy + start["y"] * self._ppm
                cur_sx = self._drag_sx + dx
                cur_sy = self._drag_sy + dy
                rel_x  = cur_sx - cx_e
                rel_y  = cur_sy - cy_e
                rot    = math.radians(start["rotation"])
                lx     =  rel_x * math.cos(rot) + rel_y * math.sin(rot)
                ly     = -rel_x * math.sin(rot) + rel_y * math.cos(rot)

                iw, ih = start["iw"], start["ih"]
                ppm    = self._ppm
                MIN_PX = 10.0  # Mindestgröße in Px

                if h in (_H_TL, _H_ML, _H_BL):
                    new_hw = max(MIN_PX, abs(lx))
                    img.scale_x = new_hw * 2 * PRINT_PPM / (iw * ppm)
                if h in (_H_TR, _H_MR, _H_BR):
                    new_hw = max(MIN_PX, abs(lx))
                    img.scale_x = new_hw * 2 * PRINT_PPM / (iw * ppm)
                if h in (_H_TL, _H_TC, _H_TR):
                    new_hh = max(MIN_PX, abs(ly))
                    img.scale_y = new_hh * 2 * PRINT_PPM / (ih * ppm)
                if h in (_H_BL, _H_BC, _H_BR):
                    new_hh = max(MIN_PX, abs(ly))
                    img.scale_y = new_hh * 2 * PRINT_PPM / (ih * ppm)

            self.queue_draw()

    def _on_drag_end(self, gesture: Gtk.GestureDrag,
                     dx: float, dy: float) -> None:
        if self._drag_target == "bg":
            log.info(
                f"Hintergrundbild verschoben: "
                f"x={self._state.bg_img_x_mm:.1f} mm, "
                f"y={self._state.bg_img_y_mm:.1f} mm"
            )
        elif isinstance(self._drag_target, TextElement):
            e = self._drag_target
            log.info(f"Text '{e.display_text}' verschoben: x={e.x_mm:.1f} mm, y={e.y_mm:.1f} mm")
        elif isinstance(self._drag_target, ImageElement):
            img = self._drag_target
            h   = self._drag_handle
            if h == -1:
                log.info(f"Bild '{img.display_name}' verschoben: x={img.x:.1f}, y={img.y:.1f} mm")
            elif h == _H_ROT:
                log.info(f"Bild '{img.display_name}' rotiert: {img.rotation:.1f}°")
            else:
                log.info(f"Bild '{img.display_name}' skaliert: sx={img.scale_x:.3f} sy={img.scale_y:.3f}")

        # Undo/Redo-Callback: Snapshot + Aktion an window.py übergeben
        if (self._on_transform_cb
                and isinstance(self._drag_target, (ImageElement, TextElement))):
            h = self._drag_handle
            if isinstance(self._drag_target, ImageElement):
                if h == -1:        action = "move"
                elif h == _H_ROT:  action = "rotate"
                else:              action = "scale"
            else:
                action = "move"
            self._on_transform_cb(self._drag_target, dict(self._drag_start), action)

        self._drag_target = None
        self._drag_handle = -1
        self.update_cursor()

    # ── Scroll (Zoom) ─────────────────────────────────────────────────────────

    def _on_scroll(self, ctrl, dx: float, dy: float) -> bool:
        factor = 1.0 - dy * self._ZOOM_STEP

        # Selektiertes Bild zoomen (nur wenn nicht gesperrt)
        img = self._state.selected_image
        if img is not None and not img.locked:
            old_sx, old_sy = img.scale_x, img.scale_y
            new_sx = max(self._SCALE_MIN, min(self._SCALE_MAX, img.scale_x * factor))
            new_sy = max(self._SCALE_MIN, min(self._SCALE_MAX, img.scale_y * factor))
            if new_sx != img.scale_x or new_sy != img.scale_y:
                img.scale_x = new_sx
                img.scale_y = new_sy
                self.queue_draw()
                log.info(f"Bild '{img.display_name}' Zoom: sx={new_sx:.2f}×")
                if self._on_img_zoom_cb:
                    self._on_img_zoom_cb(img, old_sx, old_sy, new_sx, new_sy)
            return True

        # Legacy Hintergrundbild zoomen
        if self._state.bg_surface is not None:
            new_scale = max(self._SCALE_MIN,
                            min(self._SCALE_MAX,
                                self._state.bg_img_scale * factor))
            if new_scale != self._state.bg_img_scale:
                self._state.bg_img_scale = new_scale
                self.queue_draw()
                if self._on_scale_changed_cb:
                    self._on_scale_changed_cb(new_scale)
                log.info(f"Bild-Zoom: {new_scale:.2f}×")
            return True

        return False

    # ── Hover ─────────────────────────────────────────────────────────────────

    def _on_hover_enter(self, ctrl, x: float, y: float) -> None:
        has = (self._state.bg_surface is not None
               or self._state.elements or self._state.images)
        if has:
            self.set_cursor(Gdk.Cursor.new_from_name("grab"))

    def _on_hover_leave(self, ctrl) -> None:
        self.set_cursor(None)

    # ── File Drop ─────────────────────────────────────────────────────────────

    def _on_file_drop(self, target, value: Gio.File,
                      x: float, y: float) -> bool:
        path = value.get_path()
        if path and is_image_path(path) and self._on_file_drop_cb:
            log.info(f"Datei auf Canvas gedroppt: {path}")
            self._on_file_drop_cb(path)
            return True
        return False
