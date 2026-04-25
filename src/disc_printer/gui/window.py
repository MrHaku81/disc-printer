import io
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import cairo
from gi.repository import Gtk, GLib, Gdk, Gio, GdkPixbuf

from .._log import log
from ..constants import APP_ID, PRINT_PX, HUB_LARGE_MM, HUB_SMALL_MM
from ..history import History, Command
from ..i18n import _
from .. import i18n as _i18n
from .. import settings as _settings
from .. import file_format as _fmt
from ..printer import DiscPrinter
from ..detection import detect_disc_printers
from ..model import TextElement, ImageElement, DesignState
from ..image_utils import pixbuf_to_cairo, write_print_png
from .canvas import DiscCanvas
from .dialogs import TextEditDialog


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Disc Printer")
        self.set_default_size(900, 720)
        self.set_icon_name("disc-printer")

        self._printers:          list[DiscPrinter] = []
        self._selected:          DiscPrinter | None = None
        self._state              = DesignState()
        self._block_scale_signal = False
        # (img, row, name_label, opacity_slider, opacity_label)
        self._img_rows: list[tuple] = []

        # Undo/Redo
        self._history              = History()
        self._block_opacity_signal = False
        self._block_color_signal   = False
        self._block_hub_signal     = False
        self._block_bc_signal      = False
        self._opacity_before:    dict[int, float]           = {}
        self._opacity_timer:     dict[int, int]             = {}
        self._brightness_before: dict[int, float]           = {}
        self._brightness_timer:  dict[int, int]             = {}
        self._contrast_before:   dict[int, float]           = {}
        self._contrast_timer:    dict[int, int]             = {}
        self._scroll_before:     dict[int, tuple[float, float]] = {}
        self._scroll_timer:      dict[int, int]             = {}

        _fmt.DEFAULT_DIR.mkdir(parents=True, exist_ok=True)

        self._build_ui()
        self._history.on_change = self._on_history_changed
        self._detect_async()

    # ── UI-Aufbau ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        hb = Gtk.HeaderBar()
        hb.set_show_title_buttons(True)

        open_btn = Gtk.Button(icon_name="document-open-symbolic")
        open_btn.set_tooltip_text(_("Design öffnen …"))
        open_btn.connect("clicked", self._on_open_clicked)
        hb.pack_start(open_btn)

        save_btn = Gtk.Button(icon_name="document-save-symbolic")
        save_btn.set_tooltip_text(_("Design speichern …"))
        save_btn.connect("clicked", self._on_save_clicked)
        hb.pack_start(save_btn)

        self._undo_btn = Gtk.Button(icon_name="edit-undo-symbolic")
        self._undo_btn.set_tooltip_text(_("Rückgängig"))
        self._undo_btn.set_sensitive(False)
        self._undo_btn.connect("clicked", lambda _b: self._do_undo())
        hb.pack_start(self._undo_btn)

        self._redo_btn = Gtk.Button(icon_name="edit-redo-symbolic")
        self._redo_btn.set_tooltip_text(_("Wiederherstellen"))
        self._redo_btn.set_sensitive(False)
        self._redo_btn.connect("clicked", lambda _b: self._do_redo())
        hb.pack_start(self._redo_btn)

        self._print_btn = Gtk.Button(icon_name="document-print-symbolic")
        self._print_btn.set_tooltip_text(_("Drucken …"))
        self._print_btn.connect("clicked", self._on_print_clicked)
        hb.pack_end(self._print_btn)

        self.set_titlebar(hb)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_top(12)
        outer.set_margin_bottom(12)
        outer.set_margin_start(14)
        outer.set_margin_end(14)
        self.set_child(outer)

        outer.append(self._build_printer_frame())

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        paned.set_position(450)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        outer.append(paned)

        canvas_frame = Gtk.Frame(label=f"  {_('Disc-Vorschau')}  ")
        canvas_frame.set_hexpand(True)
        canvas_frame.set_vexpand(True)

        ci = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        ci.set_margin_top(8)
        ci.set_margin_bottom(8)
        ci.set_margin_start(8)
        ci.set_margin_end(8)
        canvas_frame.set_child(ci)

        self._canvas = DiscCanvas(
            self._state,
            on_file_drop_cb     = self._add_image_from_path,
            on_scale_changed_cb = self._sync_scale_slider,
            on_edit_text_cb     = self._open_edit_dialog,
            on_img_select_cb    = self._on_canvas_img_selected,
            on_transform_cb     = self._on_canvas_transform,
            on_img_zoom_cb      = self._on_canvas_zoom,
        )
        ci.append(self._canvas)
        paned.set_start_child(canvas_frame)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_width(370)
        sw.set_vexpand(True)
        paned.set_end_child(sw)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        panel.set_margin_top(10)
        panel.set_margin_bottom(10)
        panel.set_margin_start(12)
        panel.set_margin_end(12)
        sw.set_child(panel)

        panel.append(self._build_disc_section())
        panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        panel.append(self._build_background_section())
        panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        panel.append(self._build_image_section())
        panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        panel.append(self._build_text_section())

    # ── Sprachauswahl ─────────────────────────────────────────────────────────

    def _build_lang_selector(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        lbl = Gtk.Label(label=_("Sprache:"), xalign=0.0)
        lbl.set_size_request(70, -1)
        row.append(lbl)

        langs         = _i18n.available_languages()
        display_names = [_i18n.LANG_NAMES.get(l, l) for l in langs]

        dd = Gtk.DropDown.new_from_strings(display_names)
        dd.set_hexpand(True)

        current = _i18n.get_current_lang()
        dd.set_selected(langs.index(current) if current in langs else 0)

        dd.connect("notify::selected",
                   lambda d, _p, ls=langs: self._on_language_changed(d, ls))
        row.append(dd)
        return row

    def _on_language_changed(self, dd: Gtk.DropDown, langs: list[str]) -> None:
        idx = dd.get_selected()
        if idx >= len(langs):
            return
        lang = langs[idx]
        if lang == (_i18n.get_current_lang() or "de"):
            return

        s = _settings.load()
        s["language"] = lang
        _settings.save(s)
        log.info(f"Sprache gewechselt: {lang}")

        _i18n.switch_language(lang if lang != "de" else None)

        app = self.get_application()
        MainWindow(app).present()
        self.close()

    # ── Drucker-Frame ─────────────────────────────────────────────────────────

    def _build_printer_frame(self) -> Gtk.Frame:
        frame = Gtk.Frame(label=f"  {_('Drucker')}  ")
        pbox  = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pbox.set_margin_top(8);  pbox.set_margin_bottom(8)
        pbox.set_margin_start(12); pbox.set_margin_end(12)
        frame.set_child(pbox)

        dd_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label=_("Drucker:"), xalign=0.0)
        lbl.set_size_request(70, -1)
        dd_row.append(lbl)

        self._str_list = Gtk.StringList.new([_("Erkenne Drucker …")])
        self._dropdown = Gtk.DropDown.new(self._str_list, None)
        self._dropdown.set_hexpand(True)
        self._dropdown.set_sensitive(False)
        self._dropdown.connect("notify::selected", self._on_printer_changed)
        dd_row.append(self._dropdown)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text(_("Drucker neu erkennen"))
        refresh_btn.connect("clicked", lambda _btn: self._detect_async())
        dd_row.append(refresh_btn)
        pbox.append(dd_row)

        st_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._led   = Gtk.Label()
        self._led.set_markup("<span color='#888888'>●</span>")
        self._stlbl = Gtk.Label(label=_("Initialisierung …"), xalign=0.0)
        self._stlbl.set_hexpand(True)
        st_row.append(self._led)
        st_row.append(self._stlbl)

        self._cups_info = Gtk.Label(xalign=0.0, wrap=True)
        self._cups_info.set_markup("<small><i>—</i></small>")
        pbox.append(st_row)
        pbox.append(self._cups_info)

        pbox.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        pbox.append(self._build_lang_selector())
        return frame

    # ── Disc-Optionen ─────────────────────────────────────────────────────────

    def _build_disc_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        title = Gtk.Label(xalign=0.0)
        title.set_markup(f"<b>{_('Disc-Optionen')}</b>")
        box.append(title)

        hub_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hub_row.set_margin_start(4)
        hub_row.append(Gtk.Label(label=_("Hub-Größe:"), xalign=0.0))

        # TRANSLATORS: Radio button label showing hub diameter, e.g. "Ø 50 mm"
        self._r50 = Gtk.CheckButton(label=_("Ø %.0f mm") % HUB_LARGE_MM)
        self._r33 = Gtk.CheckButton(label=_("Ø %.0f mm") % HUB_SMALL_MM)
        self._r33.set_group(self._r50)
        self._r50.set_active(True)
        self._r50.connect("toggled", self._on_hub_toggled)
        self._r33.connect("toggled", self._on_hub_toggled)
        hub_row.append(self._r50)
        hub_row.append(self._r33)
        box.append(hub_row)
        return box

    # ── Hintergrund-Bereich ───────────────────────────────────────────────────

    def _build_background_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        title = Gtk.Label(xalign=0.0)
        title.set_markup(f"<b>{_('Hintergrund')}</b>")
        box.append(title)

        cr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cr_row.set_margin_start(4)
        cr_row.append(Gtk.Label(label=_("Farbe:"), xalign=0.0, width_chars=8))
        cd = Gtk.ColorDialog(with_alpha=True, title=_("Hintergrundfarbe"))
        self._color_btn = Gtk.ColorDialogButton(dialog=cd)
        white = Gdk.RGBA()
        white.red = white.green = white.blue = white.alpha = 1.0
        self._color_btn.set_rgba(white)
        self._color_btn.connect("notify::rgba", self._on_color_changed)
        cr_row.append(self._color_btn)
        rst_c = Gtk.Button(icon_name="edit-undo-symbolic")
        rst_c.set_tooltip_text(_("Zurücksetzen auf Weiß"))
        rst_c.connect("clicked", self._on_reset_color)
        cr_row.append(rst_c)
        box.append(cr_row)

        img_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        img_row.set_margin_start(4)
        img_row.append(Gtk.Label(label=_("Bild:"), xalign=0.0, width_chars=8))
        load_btn = Gtk.Button(label=_("Laden …"))
        load_btn.set_icon_name("document-open-symbolic")
        load_btn.connect("clicked", self._on_load_image)
        img_row.append(load_btn)
        box.append(img_row)

        fr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fr_row.set_margin_start(4)
        self._bg_file_label = Gtk.Label(label=_("(kein Bild)"), xalign=0.0)
        self._bg_file_label.set_hexpand(True)
        self._bg_file_label.set_ellipsize(3)
        fr_row.append(self._bg_file_label)
        self._clear_img_btn = Gtk.Button(icon_name="edit-delete-symbolic")
        self._clear_img_btn.set_tooltip_text(_("Hintergrundbild entfernen"))
        self._clear_img_btn.set_sensitive(False)
        self._clear_img_btn.connect("clicked", self._on_clear_image)
        fr_row.append(self._clear_img_btn)
        box.append(fr_row)

        hint = Gtk.Label(xalign=0.0)
        hint.set_markup(
            f"<small><i>{_('Hintergrundbild: nur Position &amp; Zoom, kein Drehen/Spiegeln.')}</i></small>"
        )
        hint.set_margin_start(4)
        box.append(hint)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self._transform_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._transform_box.set_sensitive(False)

        t_title = Gtk.Label(xalign=0.0)
        # TRANSLATORS: Section title; "&" must stay as "&amp;" in Pango markup
        t_title.set_markup(f"<b>{GLib.markup_escape_text(_('Bild-Position & Zoom'))}</b>")
        self._transform_box.append(t_title)

        sc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sc_row.set_margin_start(4)
        sc_row.append(Gtk.Label(label=_("Zoom:"), xalign=0.0, width_chars=8))
        self._scale_slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            DiscCanvas._SCALE_MIN, DiscCanvas._SCALE_MAX, 0.05,
        )
        self._scale_slider.set_value(1.0)
        self._scale_slider.set_hexpand(True)
        self._scale_slider.set_draw_value(False)
        self._scale_slider.connect("value-changed", self._on_scale_slider_changed)
        sc_row.append(self._scale_slider)
        self._scale_lbl = Gtk.Label(label="1.00×", width_chars=6, xalign=1.0)
        sc_row.append(self._scale_lbl)
        self._transform_box.append(sc_row)

        nudge_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        nudge_row.set_margin_start(4)
        # TRANSLATORS: Arrow keys for nudging the image; keep the arrow symbols
        for lbl, tip, cb in [
            ("←", _("5 mm links"),  lambda _btn: self._nudge(-5, 0)),
            ("→", _("5 mm rechts"), lambda _btn: self._nudge( 5, 0)),
            ("↑", _("5 mm oben"),   lambda _btn: self._nudge( 0, -5)),
            ("↓", _("5 mm unten"),  lambda _btn: self._nudge( 0,  5)),
        ]:
            b = Gtk.Button(label=lbl)
            b.set_tooltip_text(tip)
            b.set_hexpand(True)
            b.connect("clicked", cb)
            nudge_row.append(b)
        rst_t = Gtk.Button(label=_("⌂ Zentrieren"))
        rst_t.set_tooltip_text(_("Zurücksetzen"))
        rst_t.set_hexpand(True)
        rst_t.connect("clicked", self._on_reset_transform)
        nudge_row.append(rst_t)
        self._transform_box.append(nudge_row)

        th = Gtk.Label(xalign=0.0)
        th.set_markup(
            f"<small><i>{_('Bild ziehen = verschieben · Mausrad = Zoom')}</i></small>"
        )
        th.set_margin_start(4)
        self._transform_box.append(th)
        box.append(self._transform_box)
        return box

    # ── Text-Bereich ──────────────────────────────────────────────────────────

    def _build_text_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(xalign=0.0)
        title.set_markup(f"<b>{_('Text-Elemente')}</b>")
        title.set_hexpand(True)
        hdr.append(title)
        add_btn = Gtk.Button(label=_("+ Hinzufügen"))
        add_btn.set_tooltip_text(_("Neues Text-Element hinzufügen"))
        add_btn.connect("clicked", self._on_add_text)
        hdr.append(add_btn)
        box.append(hdr)

        self._elem_list = Gtk.ListBox()
        self._elem_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._elem_list.add_css_class("boxed-list")

        placeholder = Gtk.Label(label=_("Keine Text-Elemente"))
        placeholder.set_margin_top(10)
        placeholder.set_margin_bottom(10)
        placeholder.add_css_class("dim-label")
        self._elem_list.set_placeholder(placeholder)

        box.append(self._elem_list)

        th = Gtk.Label(xalign=0.0)
        th.set_markup(
            f"<small><i>"
            f"{_('Klick = auswählen · Doppelklick = bearbeiten · Ziehen = verschieben')}"
            f"</i></small>"
        )
        th.set_margin_start(4)
        box.append(th)
        return box

    # ── Text-Element-Zeile ────────────────────────────────────────────────────

    def _add_element_row(self, elem: TextElement) -> None:
        row  = Gtk.ListBoxRow()
        rbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        rbox.set_margin_top(5)
        rbox.set_margin_bottom(5)
        rbox.set_margin_start(8)
        rbox.set_margin_end(8)

        icon = Gtk.Image.new_from_icon_name("format-text-bold-symbolic")
        rbox.append(icon)

        lbl = Gtk.Label(xalign=0.0, hexpand=True)
        lbl.set_ellipsize(3)
        lbl.set_markup(f"<b>{GLib.markup_escape_text(elem.display_text)}</b>")
        rbox.append(lbl)

        vis_icon = "view-reveal-symbolic" if elem.visible else "view-conceal-symbolic"
        vis_btn = Gtk.Button(icon_name=vis_icon)
        vis_btn.set_tooltip_text(_("Sichtbarkeit umschalten"))
        vis_btn.add_css_class("flat")
        vis_btn.connect("clicked",
                        lambda _b, e=elem, r=row, b=vis_btn:
                        self._toggle_element_visible(e, r, b))
        rbox.append(vis_btn)

        lock_icon = "changes-prevent-symbolic" if elem.locked else "changes-allow-symbolic"
        lock_btn = Gtk.Button(icon_name=lock_icon)
        lock_btn.set_tooltip_text(_("Sperren / Entsperren"))
        lock_btn.add_css_class("flat")
        lock_btn.connect("clicked",
                         lambda _b, e=elem, b=lock_btn:
                         self._toggle_element_locked(e, b))
        rbox.append(lock_btn)

        dup_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        dup_btn.set_tooltip_text(_("Element duplizieren"))
        dup_btn.add_css_class("flat")
        dup_btn.connect("clicked", lambda _b, e=elem: self._duplicate_element(e))
        rbox.append(dup_btn)

        edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
        edit_btn.set_tooltip_text(_("Text bearbeiten"))
        edit_btn.add_css_class("flat")
        edit_btn.connect("clicked",
                         lambda _btn, e=elem, r=row, l=lbl: self._edit_element(e, r, l))
        rbox.append(edit_btn)

        del_btn = Gtk.Button(icon_name="edit-delete-symbolic")
        del_btn.set_tooltip_text(_("Element löschen"))
        del_btn.add_css_class("flat")
        del_btn.connect("clicked",
                        lambda _btn, e=elem, r=row: self._delete_element(e, r))
        rbox.append(del_btn)

        if not elem.visible:
            row.set_opacity(0.5)

        row.set_child(rbox)
        self._elem_list.append(row)

    # ── Drucker-Erkennung ─────────────────────────────────────────────────────

    def _detect_async(self) -> None:
        self._dropdown.set_sensitive(False)
        self._set_led("gray", _("Erkenne Drucker …"))
        threading.Thread(target=self._detect_thread, daemon=True).start()

    def _detect_thread(self) -> None:
        GLib.idle_add(self._on_detection_done, detect_disc_printers())

    def _on_detection_done(self, printers: list[DiscPrinter]) -> bool:
        self._printers = printers
        n = self._str_list.get_n_items()
        for _ in range(n):
            self._str_list.remove(0)

        if not printers:
            self._str_list.append(_("(Kein Disc-Drucker gefunden)"))
            self._dropdown.set_sensitive(False)
            self._set_led("red", _("Kein Disc-fähiger Drucker gefunden"))
            self._cups_info.set_markup(
                f"<small><i>{_('Kein Disc-fähiger Drucker erkannt.')}</i></small>"
            )
            log.warning("Keine Disc-fähigen Drucker gefunden")
        else:
            for p in printers:
                self._str_list.append(p.name)
            self._dropdown.set_sensitive(True)
            self._dropdown.set_selected(0)
            self._on_printer_changed(self._dropdown, None)
            if len(printers) == 1:
                log.info(
                    f"Einziger Disc-Drucker automatisch gewählt: {printers[0].name}"
                )

        return GLib.SOURCE_REMOVE

    # ── Drucker-Handler ───────────────────────────────────────────────────────

    def _on_printer_changed(self, dd: Gtk.DropDown, _pspec) -> None:
        idx = dd.get_selected()
        if idx >= len(self._printers):
            return
        self._selected = self._printers[idx]
        p = self._selected
        log.info(f"Drucker gewählt: {p.name}")
        self._cups_info.set_markup(
            f"<small><tt>lp -d <b>{p.name}</b> "
            f"{' '.join(p.lp_options)} &lt;datei&gt;</tt></small>"
        )
        self._set_led("gray", _("Prüfe Status …"))
        threading.Thread(target=self._status_thread, args=(p.name,),
                         daemon=True).start()

    def _on_hub_toggled(self, btn: Gtk.CheckButton) -> None:
        if not btn.get_active() or self._block_hub_signal:
            return
        new_mm = HUB_LARGE_MM if btn is self._r50 else HUB_SMALL_MM
        old_mm = self._canvas.hub_mm
        if old_mm == new_mm:
            return
        self._canvas.set_hub(new_mm)
        log.info(f"Hub-Größe: {new_mm:.0f} mm")

        def set_hub(mm: float) -> None:
            self._block_hub_signal = True
            (self._r50 if mm == HUB_LARGE_MM else self._r33).set_active(True)
            self._block_hub_signal = False
            self._canvas.set_hub(mm)

        self._history.push(Command(
            _("Hub-Größe"),
            undo_fn=lambda: set_hub(old_mm),
            redo_fn=lambda: set_hub(new_mm),
        ))

    # ── Datei Speichern / Öffnen ──────────────────────────────────────────────

    def _on_save_clicked(self, _btn) -> None:
        dlg = Gtk.FileDialog(title=_("Design speichern"))
        f_dp = Gtk.FileFilter()
        f_dp.set_name(_("DiscPrint-Design (*.discprint)"))
        f_dp.add_pattern("*.discprint")
        f_all = Gtk.FileFilter()
        f_all.set_name(_("Alle Dateien"))
        f_all.add_pattern("*")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f_dp)
        store.append(f_all)
        dlg.set_filters(store)
        dlg.set_default_filter(f_dp)
        dlg.set_initial_folder(Gio.File.new_for_path(str(_fmt.DEFAULT_DIR)))
        dlg.set_initial_name("design.discprint")
        dlg.save(self, None, self._on_save_dialog_done)

    def _on_save_dialog_done(self, dlg, result) -> None:
        try:
            gfile = dlg.save_finish(result)
        except Exception:
            return
        path = Path(gfile.get_path())
        if path.suffix.lower() != ".discprint":
            path = path.with_suffix(".discprint")
        try:
            _fmt.save(path, self._state, self._canvas.hub_mm)
            log.info(f"Design gespeichert: {path}")
        except Exception as e:
            log.error(f"Speichern fehlgeschlagen: {e}")
            self._show_error(_("Design konnte nicht gespeichert werden:\n%s") % e)

    def _on_open_clicked(self, _btn) -> None:
        dlg = Gtk.FileDialog(title=_("Design öffnen"))
        f_dp = Gtk.FileFilter()
        f_dp.set_name(_("DiscPrint-Design (*.discprint)"))
        f_dp.add_pattern("*.discprint")
        f_all = Gtk.FileFilter()
        f_all.set_name(_("Alle Dateien"))
        f_all.add_pattern("*")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f_dp)
        store.append(f_all)
        dlg.set_filters(store)
        dlg.set_default_filter(f_dp)
        dlg.set_initial_folder(Gio.File.new_for_path(str(_fmt.DEFAULT_DIR)))
        dlg.open(self, None, self._on_open_dialog_done)

    def _on_open_dialog_done(self, dlg, result) -> None:
        try:
            gfile = dlg.open_finish(result)
        except Exception:
            return
        path = gfile.get_path()
        try:
            loaded_state, hub_mm = _fmt.load(path)
            self._apply_loaded_design(loaded_state, hub_mm)
            log.info(f"Design geöffnet: {path}")
        except Exception as e:
            log.error(f"Öffnen fehlgeschlagen: {e}")
            self._show_error(_("Design konnte nicht geöffnet werden:\n%s") % e)

    def _apply_loaded_design(self, loaded: DesignState, hub_mm: float) -> None:
        # Pending Debounce-Timer abbrechen
        for tid in list(self._opacity_timer.values()):
            GLib.source_remove(tid)
        self._opacity_before.clear();    self._opacity_timer.clear()
        for tid in list(self._brightness_timer.values()):
            GLib.source_remove(tid)
        self._brightness_before.clear(); self._brightness_timer.clear()
        for tid in list(self._contrast_timer.values()):
            GLib.source_remove(tid)
        self._contrast_before.clear();   self._contrast_timer.clear()
        for tid in list(self._scroll_timer.values()):
            GLib.source_remove(tid)
        self._scroll_before.clear();     self._scroll_timer.clear()

        s = self._state
        s.bg_color         = loaded.bg_color
        s.bg_surface       = loaded.bg_surface
        s.bg_path          = loaded.bg_path
        s.bg_img_x_mm      = loaded.bg_img_x_mm
        s.bg_img_y_mm      = loaded.bg_img_y_mm
        s.bg_img_scale     = loaded.bg_img_scale
        s.elements         = loaded.elements
        s.images           = loaded.images
        s.selected_element = None
        s.selected_image   = None

        self._block_hub_signal = True
        if abs(hub_mm - HUB_LARGE_MM) < 1.0:
            self._r50.set_active(True)
        else:
            self._r33.set_active(True)
        self._block_hub_signal = False
        self._canvas.set_hub(hub_mm)
        self._canvas._img_handles = []

        self._block_color_signal = True
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = s.bg_color
        self._color_btn.set_rgba(rgba)
        self._block_color_signal = False

        if s.bg_surface is not None:
            self._bg_file_label.set_text(_("(aus Datei geladen)"))
            self._clear_img_btn.set_sensitive(True)
            self._transform_box.set_sensitive(True)
        else:
            self._bg_file_label.set_text(_("(kein Bild)"))
            self._clear_img_btn.set_sensitive(False)
            self._transform_box.set_sensitive(False)
        self._sync_scale_slider(s.bg_img_scale)

        self._rebuild_panel()
        self._history.clear()

    # ── Bild-Elemente Sektion ─────────────────────────────────────────────────

    def _build_image_section(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(xalign=0.0)
        title.set_markup(f"<b>{_('Bild-Elemente')}</b>")
        title.set_hexpand(True)
        hdr.append(title)
        add_btn = Gtk.Button(label=_("+ Hinzufügen"))
        add_btn.set_tooltip_text(_("Bild-Element hinzufügen"))
        add_btn.connect("clicked", self._on_add_image)
        hdr.append(add_btn)
        box.append(hdr)

        self._flip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._flip_box.set_margin_start(4)
        fh = Gtk.Button(label="↔ " + _("H spiegeln"))
        fh.set_hexpand(True)
        fh.connect("clicked", lambda _: self._on_flip(horizontal=True))
        self._flip_box.append(fh)
        fv = Gtk.Button(label="↕ " + _("V spiegeln"))
        fv.set_hexpand(True)
        fv.connect("clicked", lambda _: self._on_flip(horizontal=False))
        self._flip_box.append(fv)
        self._flip_box.set_visible(False)
        box.append(self._flip_box)

        self._img_list = Gtk.ListBox()
        self._img_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._img_list.add_css_class("boxed-list")
        ph = Gtk.Label(label=_("Keine Bild-Elemente"))
        ph.set_margin_top(10); ph.set_margin_bottom(10)
        ph.add_css_class("dim-label")
        self._img_list.set_placeholder(ph)
        box.append(self._img_list)
        return box

    def _make_thumbnail(self, img: ImageElement) -> Gtk.Widget:
        THUMB = 32
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, THUMB, THUMB)
        cr   = cairo.Context(surf)
        cr.set_source_rgb(0.65, 0.65, 0.65)
        cr.paint()
        iw = img.surface.get_width()
        ih = img.surface.get_height()
        if iw > 0 and ih > 0:
            sc = min(THUMB / iw, THUMB / ih)
            cr.translate((THUMB - iw * sc) / 2, (THUMB - ih * sc) / 2)
            cr.scale(sc, sc)
            cr.set_source_surface(img.surface, 0, 0)
            cr.paint()
        buf = io.BytesIO()
        surf.write_to_png(buf)
        buf.seek(0)
        loader = GdkPixbuf.PixbufLoader()
        loader.write(buf.read())
        loader.close()
        pb = loader.get_pixbuf()
        return Gtk.Image.new_from_pixbuf(pb)

    def _add_image_row(self, img: ImageElement) -> None:
        row  = Gtk.ListBoxRow()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        vbox.set_margin_top(5); vbox.set_margin_bottom(5)
        vbox.set_margin_start(8); vbox.set_margin_end(8)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        top.append(self._make_thumbnail(img))

        name_lbl = Gtk.Label(xalign=0.0, hexpand=True)
        name_lbl.set_ellipsize(3)
        name_lbl.set_text(img.display_name)
        top.append(name_lbl)

        vis_icon = "view-reveal-symbolic" if img.visible else "view-conceal-symbolic"
        vis_btn = Gtk.Button(icon_name=vis_icon)
        vis_btn.add_css_class("flat")
        vis_btn.set_tooltip_text(_("Sichtbarkeit umschalten"))
        vis_btn.connect("clicked",
                        lambda _b, i=img, r=row, b=vis_btn:
                        self._toggle_image_visible(i, r, b))
        top.append(vis_btn)

        lock_icon = "changes-prevent-symbolic" if img.locked else "changes-allow-symbolic"
        lock_btn = Gtk.Button(icon_name=lock_icon)
        lock_btn.add_css_class("flat")
        lock_btn.set_tooltip_text(_("Sperren / Entsperren"))
        lock_btn.connect("clicked",
                         lambda _b, i=img, b=lock_btn:
                         self._toggle_image_locked(i, b))
        top.append(lock_btn)

        dup_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        dup_btn.add_css_class("flat")
        dup_btn.set_tooltip_text(_("Element duplizieren"))
        dup_btn.connect("clicked", lambda _b, i=img: self._duplicate_image(i))
        top.append(dup_btn)

        up_btn = Gtk.Button(icon_name="go-up-symbolic")
        up_btn.add_css_class("flat")
        up_btn.set_tooltip_text(_("Ebene nach oben"))
        up_btn.connect("clicked", lambda _b, i=img: self._img_z_change(i, +1))
        top.append(up_btn)

        dn_btn = Gtk.Button(icon_name="go-down-symbolic")
        dn_btn.add_css_class("flat")
        dn_btn.set_tooltip_text(_("Ebene nach unten"))
        dn_btn.connect("clicked", lambda _b, i=img: self._img_z_change(i, -1))
        top.append(dn_btn)

        del_btn = Gtk.Button(icon_name="edit-delete-symbolic")
        del_btn.add_css_class("flat")
        del_btn.set_tooltip_text(_("Element löschen"))
        del_btn.connect("clicked", lambda _b, i=img, r=row: self._delete_image(i, r))
        top.append(del_btn)

        vbox.append(top)

        def _make_slider_row(label_text: str, lo: float, hi: float,
                             value: float) -> tuple:
            srow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            srow.set_margin_start(4)
            srow.append(Gtk.Label(label=label_text, xalign=0.0, width_chars=10))
            sl = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 0.05)
            sl.set_value(value)
            sl.set_hexpand(True)
            sl.set_draw_value(False)
            srow.append(sl)
            lbl = Gtk.Label(label=f"{value*100:.0f}%", width_chars=5, xalign=1.0)
            srow.append(lbl)
            rst = Gtk.Button(icon_name="edit-undo-symbolic")
            rst.set_tooltip_text(_("Zurücksetzen auf 100 %"))
            rst.add_css_class("flat")
            srow.append(rst)
            vbox.append(srow)
            return sl, lbl, rst

        op_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        op_row.set_margin_start(4)
        op_row.append(Gtk.Label(label=_("Opazität:"), xalign=0.0, width_chars=10))
        op_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.05)
        op_slider.set_value(img.opacity)
        op_slider.set_hexpand(True)
        op_slider.set_draw_value(False)
        op_row.append(op_slider)
        op_lbl = Gtk.Label(label=f"{img.opacity*100:.0f}%", width_chars=5, xalign=1.0)
        op_row.append(op_lbl)
        op_slider.connect("value-changed",
                          lambda s, i=img, l=op_lbl: self._on_img_opacity(s, i, l))
        vbox.append(op_row)

        br_slider, br_lbl, br_rst = _make_slider_row(
            _("Helligkeit:"), 0.0, 2.0, img.brightness)
        br_slider.connect("value-changed",
                          lambda s, i=img, l=br_lbl: self._on_img_brightness(s, i, l))
        br_rst.connect("clicked", lambda _b, i=img: self._on_reset_brightness(i))

        co_slider, co_lbl, co_rst = _make_slider_row(
            _("Kontrast:"), 0.0, 2.0, img.contrast)
        co_slider.connect("value-changed",
                          lambda s, i=img, l=co_lbl: self._on_img_contrast(s, i, l))
        co_rst.connect("clicked", lambda _b, i=img: self._on_reset_contrast(i))

        gc = Gtk.GestureClick()
        gc.connect("pressed", lambda _g, _n, _x, _y, i=img: self._on_img_row_clicked(i))
        row.add_controller(gc)

        if not img.visible:
            row.set_opacity(0.5)

        row.set_child(vbox)
        self._img_list.append(row)
        self._img_rows.append(
            (img, row, name_lbl, op_slider, op_lbl, br_slider, br_lbl, co_slider, co_lbl)
        )

    # ── Bild-Handler ─────────────────────────────────────────────────────────

    def _on_add_image(self, _btn) -> None:
        dlg = Gtk.FileDialog(title=_("Bild hinzufügen"))
        f_img = Gtk.FileFilter()
        f_img.set_name(_("Bilder (PNG, JPG, WEBP …)"))
        for m in ("image/png", "image/jpeg", "image/webp",
                  "image/bmp", "image/tiff", "image/gif"):
            f_img.add_mime_type(m)
        f_all = Gtk.FileFilter()
        f_all.set_name(_("Alle Dateien"))
        f_all.add_pattern("*")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f_img); store.append(f_all)
        dlg.set_filters(store)
        dlg.set_default_filter(f_img)
        dlg.open(self, None, self._on_add_image_done)

    def _on_add_image_done(self, dlg, result) -> None:
        try:
            gfile = dlg.open_finish(result)
        except Exception:
            return
        if path := gfile.get_path():
            self._add_image_from_path(path)

    def _add_image_from_path(self, path: str) -> None:
        try:
            pixbuf  = GdkPixbuf.Pixbuf.new_from_file(path)
            surface = pixbuf_to_cairo(pixbuf)
            from ..constants import PRINTABLE_MM, PRINT_PPM
            target_px  = PRINTABLE_MM * 0.6 * PRINT_PPM
            iw = surface.get_width()
            init_scale = target_px / iw if iw > 0 else 1.0
            next_z = max((i.z for i in self._state.images), default=-1) + 1
            img = ImageElement(
                surface   = surface,
                file_path = path,
                scale_x   = init_scale,
                scale_y   = init_scale,
                z         = next_z,
            )
            self._state.images.append(img)
            self._add_image_row(img)
            self._canvas.update_cursor()
            self._canvas.refresh()
            log.info(f"Bild-Element hinzugefügt: {path} z={next_z}")

            def undo(i=img) -> None:
                if self._state.selected_image is i:
                    self._canvas._select_image(None)
                self._state.images.remove(i)
                self._rebuild_panel()

            def redo(i=img) -> None:
                self._state.images.append(i)
                self._rebuild_panel()

            self._history.push(Command(_("Bild hinzufügen"), undo, redo))
        except Exception as e:
            log.error(f"Bild laden fehlgeschlagen: {e}")
            self._show_error(_("Bild konnte nicht geladen werden:\n%s") % e)

    def _on_img_opacity(self, slider: Gtk.Scale,
                        img: ImageElement, lbl: Gtk.Label) -> None:
        if self._block_opacity_signal:
            return
        new_val = slider.get_value()
        # Vor der ersten Änderung: alten Wert sichern
        if img.id not in self._opacity_before:
            self._opacity_before[img.id] = img.opacity
        img.opacity = new_val
        lbl.set_text(f"{new_val*100:.0f}%")
        self._canvas.refresh()
        # Debounce: bei Ruhe nach 600 ms Command erstellen
        if img.id in self._opacity_timer:
            GLib.source_remove(self._opacity_timer.pop(img.id))

        def commit(img_id: int = img.id, img_ref: ImageElement = img) -> bool:
            before = self._opacity_before.pop(img_id, None)
            self._opacity_timer.pop(img_id, None)
            if before is None or abs(img_ref.opacity - before) < 0.005:
                return GLib.SOURCE_REMOVE
            b, a = before, img_ref.opacity

            def apply_opacity(v: float, i: ImageElement = img_ref) -> None:
                i.opacity = v
                t = self._find_img_row(i)
                if t:
                    self._block_opacity_signal = True
                    t[3].set_value(v)
                    t[4].set_text(f"{v*100:.0f}%")
                    self._block_opacity_signal = False
                self._canvas.refresh()

            self._history.push(Command(
                _("Opazität") + f": {img_ref.display_name}",
                undo_fn=lambda: apply_opacity(b),
                redo_fn=lambda: apply_opacity(a),
            ))
            return GLib.SOURCE_REMOVE

        self._opacity_timer[img.id] = GLib.timeout_add(600, commit)

    def _on_img_brightness(self, slider: Gtk.Scale,
                            img: ImageElement, lbl: Gtk.Label) -> None:
        if self._block_bc_signal:
            return
        new_val = slider.get_value()
        if img.id not in self._brightness_before:
            self._brightness_before[img.id] = img.brightness
        img.brightness = new_val
        lbl.set_text(f"{new_val*100:.0f}%")
        self._canvas.refresh()
        if img.id in self._brightness_timer:
            GLib.source_remove(self._brightness_timer.pop(img.id))

        def commit(img_id: int = img.id, img_ref: ImageElement = img) -> bool:
            before = self._brightness_before.pop(img_id, None)
            self._brightness_timer.pop(img_id, None)
            if before is None or abs(img_ref.brightness - before) < 0.005:
                return GLib.SOURCE_REMOVE
            b, a = before, img_ref.brightness

            def apply_brightness(v: float, i: ImageElement = img_ref) -> None:
                i.brightness = v
                t = self._find_img_row(i)
                if t:
                    self._block_bc_signal = True
                    t[5].set_value(v)
                    t[6].set_text(f"{v*100:.0f}%")
                    self._block_bc_signal = False
                self._canvas.refresh()

            self._history.push(Command(
                _("Helligkeit") + f": {img_ref.display_name}",
                undo_fn=lambda: apply_brightness(b),
                redo_fn=lambda: apply_brightness(a),
            ))
            return GLib.SOURCE_REMOVE

        self._brightness_timer[img.id] = GLib.timeout_add(600, commit)

    def _on_img_contrast(self, slider: Gtk.Scale,
                          img: ImageElement, lbl: Gtk.Label) -> None:
        if self._block_bc_signal:
            return
        new_val = slider.get_value()
        if img.id not in self._contrast_before:
            self._contrast_before[img.id] = img.contrast
        img.contrast = new_val
        lbl.set_text(f"{new_val*100:.0f}%")
        self._canvas.refresh()
        if img.id in self._contrast_timer:
            GLib.source_remove(self._contrast_timer.pop(img.id))

        def commit(img_id: int = img.id, img_ref: ImageElement = img) -> bool:
            before = self._contrast_before.pop(img_id, None)
            self._contrast_timer.pop(img_id, None)
            if before is None or abs(img_ref.contrast - before) < 0.005:
                return GLib.SOURCE_REMOVE
            b, a = before, img_ref.contrast

            def apply_contrast(v: float, i: ImageElement = img_ref) -> None:
                i.contrast = v
                t = self._find_img_row(i)
                if t:
                    self._block_bc_signal = True
                    t[7].set_value(v)
                    t[8].set_text(f"{v*100:.0f}%")
                    self._block_bc_signal = False
                self._canvas.refresh()

            self._history.push(Command(
                _("Kontrast") + f": {img_ref.display_name}",
                undo_fn=lambda: apply_contrast(b),
                redo_fn=lambda: apply_contrast(a),
            ))
            return GLib.SOURCE_REMOVE

        self._contrast_timer[img.id] = GLib.timeout_add(600, commit)

    def _on_reset_brightness(self, img: ImageElement) -> None:
        old_b = img.brightness
        if abs(old_b - 1.0) < 1e-4:
            return
        img.brightness = 1.0
        t = self._find_img_row(img)
        if t:
            self._block_bc_signal = True
            t[5].set_value(1.0)
            t[6].set_text("100%")
            self._block_bc_signal = False
        self._canvas.refresh()

        def apply_brightness(v: float, i: ImageElement = img) -> None:
            i.brightness = v
            tt = self._find_img_row(i)
            if tt:
                self._block_bc_signal = True
                tt[5].set_value(v)
                tt[6].set_text(f"{v*100:.0f}%")
                self._block_bc_signal = False
            self._canvas.refresh()

        self._history.push(Command(
            _("Helligkeit zurücksetzen") + f": {img.display_name}",
            undo_fn=lambda: apply_brightness(old_b),
            redo_fn=lambda: apply_brightness(1.0),
        ))

    def _on_reset_contrast(self, img: ImageElement) -> None:
        old_c = img.contrast
        if abs(old_c - 1.0) < 1e-4:
            return
        img.contrast = 1.0
        t = self._find_img_row(img)
        if t:
            self._block_bc_signal = True
            t[7].set_value(1.0)
            t[8].set_text("100%")
            self._block_bc_signal = False
        self._canvas.refresh()

        def apply_contrast(v: float, i: ImageElement = img) -> None:
            i.contrast = v
            tt = self._find_img_row(i)
            if tt:
                self._block_bc_signal = True
                tt[7].set_value(v)
                tt[8].set_text(f"{v*100:.0f}%")
                self._block_bc_signal = False
            self._canvas.refresh()

        self._history.push(Command(
            _("Kontrast zurücksetzen") + f": {img.display_name}",
            undo_fn=lambda: apply_contrast(old_c),
            redo_fn=lambda: apply_contrast(1.0),
        ))

    def _img_z_change(self, img: ImageElement, delta: int) -> None:
        old_z = img.z
        img.z += delta
        new_z = img.z
        self._canvas.refresh()
        log.info(f"Bild '{img.display_name}' z={img.z}")

        def apply_z(z: int, i: ImageElement = img) -> None:
            i.z = z
            self._canvas.refresh()

        self._history.push(Command(
            _("Ebene") + f": {img.display_name}",
            undo_fn=lambda: apply_z(old_z),
            redo_fn=lambda: apply_z(new_z),
        ))

    def _delete_image(self, img: ImageElement, row: Gtk.ListBoxRow) -> None:
        idx = self._state.images.index(img)
        if img is self._state.selected_image:
            self._canvas._select_image(None)
            self._flip_box.set_visible(False)
        self._state.images.remove(img)
        self._img_rows = [t for t in self._img_rows if t[0] is not img]
        self._img_list.remove(row)
        self._canvas.update_cursor()
        self._canvas.refresh()
        log.info(f"Bild-Element gelöscht: {img.display_name}")

        def undo(i=img, ix=idx) -> None:
            self._state.images.insert(ix, i)
            self._rebuild_panel()

        def redo(i=img) -> None:
            if self._state.selected_image is i:
                self._canvas._select_image(None)
            self._state.images.remove(i)
            self._rebuild_panel()

        self._history.push(Command(
            _("Bild löschen") + f": {img.display_name}", undo, redo
        ))

    def _on_img_row_clicked(self, img: ImageElement) -> None:
        self._canvas._select_any(img)
        self._canvas.refresh()

    def _on_canvas_img_selected(self, img: ImageElement | None) -> None:
        self._flip_box.set_visible(img is not None)
        for i, row, *_ in self._img_rows:
            if i is img:
                row.add_css_class("activatable")
            else:
                row.remove_css_class("activatable")

    def _on_flip(self, horizontal: bool) -> None:
        img = self._state.selected_image
        if img is None:
            return
        if horizontal:
            img.flip_h = not img.flip_h
            new_val = img.flip_h
            log.info(f"Bild '{img.display_name}' flip_h={new_val}")
            self._canvas.refresh()

            def apply_h(v: bool, i: ImageElement = img) -> None:
                i.flip_h = v; self._canvas.refresh()

            self._history.push(Command(
                _("H-Spiegeln") + f": {img.display_name}",
                undo_fn=lambda: apply_h(not new_val),
                redo_fn=lambda: apply_h(new_val),
            ))
        else:
            img.flip_v = not img.flip_v
            new_val = img.flip_v
            log.info(f"Bild '{img.display_name}' flip_v={new_val}")
            self._canvas.refresh()

            def apply_v(v: bool, i: ImageElement = img) -> None:
                i.flip_v = v; self._canvas.refresh()

            self._history.push(Command(
                _("V-Spiegeln") + f": {img.display_name}",
                undo_fn=lambda: apply_v(not new_val),
                redo_fn=lambda: apply_v(new_val),
            ))

    def _toggle_image_visible(self, img: ImageElement,
                               row: Gtk.ListBoxRow, btn: Gtk.Button) -> None:
        img.visible = not img.visible
        new_vis = img.visible
        btn.set_icon_name("view-reveal-symbolic" if new_vis else "view-conceal-symbolic")
        row.set_opacity(1.0 if new_vis else 0.5)
        self._canvas.refresh()
        log.info(f"Bild '{img.display_name}' visible={new_vis}")

        def apply_vis(v: bool, i: ImageElement = img) -> None:
            i.visible = v
            self._rebuild_panel()

        self._history.push(Command(
            _("Sichtbarkeit") + f": {img.display_name}",
            undo_fn=lambda: apply_vis(not new_vis),
            redo_fn=lambda: apply_vis(new_vis),
        ))

    def _toggle_image_locked(self, img: ImageElement, btn: Gtk.Button) -> None:
        img.locked = not img.locked
        new_locked = img.locked
        btn.set_icon_name(
            "changes-prevent-symbolic" if new_locked else "changes-allow-symbolic"
        )
        self._canvas.refresh()
        log.info(f"Bild '{img.display_name}' locked={new_locked}")

        def apply_lock(v: bool, i: ImageElement = img) -> None:
            i.locked = v
            self._rebuild_panel()

        self._history.push(Command(
            _("Sperren") + f": {img.display_name}",
            undo_fn=lambda: apply_lock(not new_locked),
            redo_fn=lambda: apply_lock(new_locked),
        ))

    def _duplicate_image(self, img: ImageElement) -> None:
        all_z  = [e.z for e in self._state.elements] + [i.z for i in self._state.images]
        next_z = max(all_z, default=-1) + 1
        offset = 3.0  # mm
        new_img = ImageElement(
            surface    = img.surface,
            file_path  = img.file_path,
            x          = img.x + offset,
            y          = img.y + offset,
            scale_x    = img.scale_x,
            scale_y    = img.scale_y,
            rotation   = img.rotation,
            opacity    = img.opacity,
            z          = next_z,
            flip_h     = img.flip_h,
            flip_v     = img.flip_v,
            locked     = False,
            visible    = True,
            brightness = img.brightness,
            contrast   = img.contrast,
        )
        self._state.images.append(new_img)
        self._add_image_row(new_img)
        self._canvas.update_cursor()
        self._canvas.refresh()
        log.info(f"Bild-Element dupliziert: '{img.display_name}' → z={next_z}")

        def undo(ni=new_img) -> None:
            if self._state.selected_image is ni:
                self._canvas._select_image(None)
            self._state.images.remove(ni)
            self._rebuild_panel()

        def redo(ni=new_img) -> None:
            self._state.images.append(ni)
            self._rebuild_panel()

        self._history.push(Command(
            _("Bild duplizieren") + f": {img.display_name}", undo, redo
        ))

    def _toggle_element_visible(self, elem: TextElement,
                                 row: Gtk.ListBoxRow, btn: Gtk.Button) -> None:
        elem.visible = not elem.visible
        new_vis = elem.visible
        btn.set_icon_name("view-reveal-symbolic" if new_vis else "view-conceal-symbolic")
        row.set_opacity(1.0 if new_vis else 0.5)
        self._canvas.refresh()
        log.info(f"Text '{elem.display_text}' visible={new_vis}")

        def apply_vis(v: bool, e: TextElement = elem) -> None:
            e.visible = v
            self._rebuild_panel()

        self._history.push(Command(
            _("Sichtbarkeit") + f": {elem.display_text}",
            undo_fn=lambda: apply_vis(not new_vis),
            redo_fn=lambda: apply_vis(new_vis),
        ))

    def _toggle_element_locked(self, elem: TextElement, btn: Gtk.Button) -> None:
        elem.locked = not elem.locked
        new_locked = elem.locked
        btn.set_icon_name(
            "changes-prevent-symbolic" if new_locked else "changes-allow-symbolic"
        )
        self._canvas.refresh()
        log.info(f"Text '{elem.display_text}' locked={new_locked}")

        def apply_lock(v: bool, e: TextElement = elem) -> None:
            e.locked = v
            self._rebuild_panel()

        self._history.push(Command(
            _("Sperren") + f": {elem.display_text}",
            undo_fn=lambda: apply_lock(not new_locked),
            redo_fn=lambda: apply_lock(new_locked),
        ))

    def _duplicate_element(self, elem: TextElement) -> None:
        all_z  = [e.z for e in self._state.elements] + [i.z for i in self._state.images]
        next_z = max(all_z, default=99) + 1
        offset = 3.0  # mm
        new_elem = TextElement(
            text         = elem.text,
            font_family  = elem.font_family,
            font_size_pt = elem.font_size_pt,
            bold         = elem.bold,
            italic       = elem.italic,
            color        = elem.color,
            x_mm         = elem.x_mm + offset,
            y_mm         = elem.y_mm + offset,
            z            = next_z,
        )
        new_elem.locked  = False
        new_elem.visible = True
        self._state.elements.append(new_elem)
        self._add_element_row(new_elem)
        self._canvas.update_cursor()
        self._canvas.refresh()
        log.info(f"Text-Element dupliziert: '{elem.display_text}' → z={next_z}")

        def undo(ne=new_elem) -> None:
            if self._state.selected_element is ne:
                self._state.selected_element = None
            self._state.elements.remove(ne)
            self._rebuild_panel()

        def redo(ne=new_elem) -> None:
            self._state.elements.append(ne)
            self._rebuild_panel()

        self._history.push(Command(
            _("Text duplizieren") + f": {elem.display_text}", undo, redo
        ))

    # ── Hintergrund-Handler ───────────────────────────────────────────────────

    def _on_color_changed(self, btn, _pspec) -> None:
        if self._block_color_signal:
            return
        old_color = self._state.bg_color
        rgba = btn.get_rgba()
        new_color = (rgba.red, rgba.green, rgba.blue, rgba.alpha)
        self._state.set_bg_color(*new_color)
        self._canvas.refresh()
        log.info(
            f"Hintergrundfarbe: rgba({rgba.red:.3f}, {rgba.green:.3f}, "
            f"{rgba.blue:.3f}, {rgba.alpha:.3f})"
        )
        if old_color == new_color:
            return

        def apply_color(c: tuple) -> None:
            self._state.set_bg_color(*c)
            r = Gdk.RGBA()
            r.red, r.green, r.blue, r.alpha = c
            self._block_color_signal = True
            self._color_btn.set_rgba(r)
            self._block_color_signal = False
            self._canvas.refresh()

        self._history.push(Command(
            _("Hintergrundfarbe"),
            undo_fn=lambda: apply_color(old_color),
            redo_fn=lambda: apply_color(new_color),
        ))

    def _on_reset_color(self, _btn) -> None:
        white = Gdk.RGBA()
        white.red = white.green = white.blue = white.alpha = 1.0
        self._color_btn.set_rgba(white)

    def _on_load_image(self, _btn) -> None:
        dlg = Gtk.FileDialog(title=_("Hintergrundbild wählen"))
        f_img = Gtk.FileFilter()
        # TRANSLATORS: File filter label in the image chooser dialog
        f_img.set_name(_("Bilder (PNG, JPG, WEBP …)"))
        for m in ("image/png", "image/jpeg", "image/webp",
                  "image/bmp", "image/tiff", "image/gif"):
            f_img.add_mime_type(m)
        f_all = Gtk.FileFilter()
        f_all.set_name(_("Alle Dateien"))
        f_all.add_pattern("*")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f_img)
        store.append(f_all)
        dlg.set_filters(store)
        dlg.set_default_filter(f_img)
        dlg.open(self, None, self._on_image_dialog_done)

    def _on_image_dialog_done(self, dlg, result) -> None:
        try:
            gfile = dlg.open_finish(result)
        except Exception:
            return
        if p := gfile.get_path():
            self._load_bg_image(p)

    def _load_bg_image(self, path: str) -> None:
        old_surface = self._state.bg_surface
        old_path    = self._state.bg_path
        old_x       = self._state.bg_img_x_mm
        old_y       = self._state.bg_img_y_mm
        old_scale   = self._state.bg_img_scale
        try:
            pixbuf  = GdkPixbuf.Pixbuf.new_from_file(path)
            surface = pixbuf_to_cairo(pixbuf)
            self._state.set_bg_image(surface, path)
            self._state.reset_bg_transform()
            self._bg_file_label.set_text(Path(path).name)
            self._clear_img_btn.set_sensitive(True)
            self._transform_box.set_sensitive(True)
            self._sync_scale_slider(1.0)
            self._canvas.update_cursor()
            self._canvas.refresh()
            log.info(
                f"Hintergrundbild geladen: {path} "
                f"({pixbuf.get_width()}×{pixbuf.get_height()} px)"
            )

            def undo() -> None:
                if old_surface is not None:
                    self._state.set_bg_image(old_surface, old_path)
                    self._state.bg_img_x_mm  = old_x
                    self._state.bg_img_y_mm  = old_y
                    self._state.bg_img_scale = old_scale
                    name = Path(old_path).name if old_path else _("(aus Datei geladen)")
                    self._bg_file_label.set_text(name)
                    self._clear_img_btn.set_sensitive(True)
                    self._transform_box.set_sensitive(True)
                    self._sync_scale_slider(old_scale)
                else:
                    self._state.clear_bg_image()
                    self._bg_file_label.set_text(_("(kein Bild)"))
                    self._clear_img_btn.set_sensitive(False)
                    self._transform_box.set_sensitive(False)
                    self._sync_scale_slider(1.0)
                self._canvas.update_cursor()
                self._canvas.refresh()

            def redo() -> None:
                self._state.set_bg_image(surface, path)
                self._state.reset_bg_transform()
                self._bg_file_label.set_text(Path(path).name)
                self._clear_img_btn.set_sensitive(True)
                self._transform_box.set_sensitive(True)
                self._sync_scale_slider(1.0)
                self._canvas.update_cursor()
                self._canvas.refresh()

            self._history.push(Command(_("Hintergrundbild laden"), undo, redo))
        except Exception as e:
            log.error(f"Fehler beim Laden von '{path}': {e}")
            self._show_error(_("Bild konnte nicht geladen werden:\n%s") % e)

    def _on_clear_image(self, _btn) -> None:
        old_surface = self._state.bg_surface
        old_path    = self._state.bg_path
        old_x       = self._state.bg_img_x_mm
        old_y       = self._state.bg_img_y_mm
        old_scale   = self._state.bg_img_scale
        self._state.clear_bg_image()
        self._bg_file_label.set_text(_("(kein Bild)"))
        self._clear_img_btn.set_sensitive(False)
        self._transform_box.set_sensitive(False)
        self._sync_scale_slider(1.0)
        self._canvas.update_cursor()
        self._canvas.refresh()
        log.info(f"Hintergrundbild entfernt: {old_path}")

        def undo() -> None:
            self._state.set_bg_image(old_surface, old_path)
            self._state.bg_img_x_mm  = old_x
            self._state.bg_img_y_mm  = old_y
            self._state.bg_img_scale = old_scale
            name = Path(old_path).name if old_path else _("(aus Datei geladen)")
            self._bg_file_label.set_text(name)
            self._clear_img_btn.set_sensitive(True)
            self._transform_box.set_sensitive(True)
            self._sync_scale_slider(old_scale)
            self._canvas.update_cursor()
            self._canvas.refresh()

        def redo() -> None:
            self._state.clear_bg_image()
            self._bg_file_label.set_text(_("(kein Bild)"))
            self._clear_img_btn.set_sensitive(False)
            self._transform_box.set_sensitive(False)
            self._sync_scale_slider(1.0)
            self._canvas.update_cursor()
            self._canvas.refresh()

        self._history.push(Command(_("Hintergrundbild entfernen"), undo, redo))

    def _on_scale_slider_changed(self, slider) -> None:
        if self._block_scale_signal:
            return
        v = slider.get_value()
        self._state.bg_img_scale = v
        self._scale_lbl.set_text(f"{v:.2f}×")
        self._canvas.refresh()
        log.info(f"Bild-Zoom (Slider): {v:.2f}×")

    def _sync_scale_slider(self, value: float) -> None:
        self._block_scale_signal = True
        self._scale_slider.set_value(value)
        self._scale_lbl.set_text(f"{value:.2f}×")
        self._block_scale_signal = False

    def _nudge(self, dx_mm: float, dy_mm: float) -> None:
        if self._state.bg_surface is None:
            return
        self._state.bg_img_x_mm += dx_mm
        self._state.bg_img_y_mm += dy_mm
        self._canvas.refresh()
        log.info(
            f"Bild-Nudge dx={dx_mm:+.0f}mm dy={dy_mm:+.0f}mm → "
            f"x={self._state.bg_img_x_mm:.1f}mm y={self._state.bg_img_y_mm:.1f}mm"
        )

    def _on_reset_transform(self, _btn) -> None:
        self._state.reset_bg_transform()
        self._sync_scale_slider(1.0)
        self._canvas.refresh()
        log.info("Bild-Transform zurückgesetzt")

    # ── Text-Handler ──────────────────────────────────────────────────────────

    def _on_add_text(self, _btn) -> None:
        dlg = TextEditDialog(self)
        dlg.connect("close-request", lambda w: self._on_add_dialog_closed(w))
        dlg.present()

    def _on_add_dialog_closed(self, dlg: TextEditDialog) -> bool:
        if dlg.result:
            r = dlg.result
            offset = len(self._state.elements) * 5.0
            elem = TextElement(
                text         = r["text"],
                font_family  = r["font_family"],
                font_size_pt = r["font_size_pt"],
                bold         = r["bold"],
                italic       = r["italic"],
                color        = r["color"],
                x_mm         = offset % 30 - 15,
                y_mm         = offset % 20 - 10,
            )
            self._state.elements.append(elem)
            self._add_element_row(elem)
            self._canvas.update_cursor()
            self._canvas.refresh()
            log.info(
                f"Text-Element hinzugefügt: '{elem.display_text}' [{elem.font_desc_str}]"
            )

            def undo(e=elem) -> None:
                if self._state.selected_element is e:
                    self._state.selected_element = None
                self._state.elements.remove(e)
                self._rebuild_panel()

            def redo(e=elem) -> None:
                self._state.elements.append(e)
                self._rebuild_panel()

            self._history.push(Command(_("Text hinzufügen"), undo, redo))
        return False

    def _open_edit_dialog(self, elem: TextElement) -> None:
        dlg = TextEditDialog(self, elem)
        dlg.connect("close-request",
                    lambda w, e=elem: self._on_edit_dialog_closed(w, e))
        dlg.present()

    def _edit_element(self, elem: TextElement,
                      row: Gtk.ListBoxRow, lbl: Gtk.Label) -> None:
        dlg = TextEditDialog(self, elem)
        dlg.connect("close-request",
                    lambda w, e=elem, r=row, l=lbl:
                    self._on_edit_dialog_closed(w, e, l))
        dlg.present()

    def _on_edit_dialog_closed(self, dlg: TextEditDialog,
                                elem: TextElement,
                                lbl: Gtk.Label | None = None) -> bool:
        if dlg.result:
            r = dlg.result
            old_state = {
                "text": elem.text, "font_family": elem.font_family,
                "font_size_pt": elem.font_size_pt, "bold": elem.bold,
                "italic": elem.italic, "color": elem.color,
            }
            new_state = {
                "text": r["text"], "font_family": r["font_family"],
                "font_size_pt": r["font_size_pt"], "bold": r["bold"],
                "italic": r["italic"], "color": r["color"],
            }
            elem.text         = new_state["text"]
            elem.font_family  = new_state["font_family"]
            elem.font_size_pt = new_state["font_size_pt"]
            elem.bold         = new_state["bold"]
            elem.italic       = new_state["italic"]
            elem.color        = new_state["color"]
            if lbl:
                lbl.set_markup(
                    f"<b>{GLib.markup_escape_text(elem.display_text)}</b>"
                )
            self._canvas.refresh()
            log.info(
                f"Text-Element bearbeitet: '{elem.display_text}' [{elem.font_desc_str}]"
            )

            def apply_text(s: dict, e: TextElement = elem) -> None:
                e.text = s["text"]; e.font_family  = s["font_family"]
                e.font_size_pt = s["font_size_pt"]; e.bold = s["bold"]
                e.italic = s["italic"];              e.color = s["color"]
                self._rebuild_panel()

            self._history.push(Command(
                _("Text bearbeiten") + f": {elem.display_text}",
                undo_fn=lambda os=old_state: apply_text(os),
                redo_fn=lambda ns=new_state: apply_text(ns),
            ))
        return False

    def _delete_element(self, elem: TextElement,
                         row: Gtk.ListBoxRow) -> None:
        idx = self._state.elements.index(elem)
        if elem is self._state.selected_element:
            self._state.selected_element = None
        self._state.elements.remove(elem)
        self._elem_list.remove(row)
        self._canvas.update_cursor()
        self._canvas.refresh()
        log.info(f"Text-Element gelöscht: '{elem.display_text}'")

        def undo(e=elem, i=idx) -> None:
            self._state.elements.insert(i, e)
            self._rebuild_panel()

        def redo(e=elem) -> None:
            if self._state.selected_element is e:
                self._state.selected_element = None
            self._state.elements.remove(e)
            self._rebuild_panel()

        self._history.push(Command(
            _("Text löschen") + f": {elem.display_text}", undo, redo
        ))

    # ── Drucker-Status ────────────────────────────────────────────────────────

    def _status_thread(self, name: str) -> None:
        env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
        try:
            r = subprocess.run(
                ["lpstat", "-p", name],
                capture_output=True, text=True, timeout=4, env=env,
            )
            out = r.stdout.lower()
            if "idle" in out or "ready" in out:
                GLib.idle_add(self._set_led, "green", _("Bereit"))
                log.info(f"Drucker {name}: bereit")
            elif "disabled" in out or "stopped" in out:
                GLib.idle_add(self._set_led, "red", _("Deaktiviert / gestoppt"))
                log.warning(f"Drucker {name}: deaktiviert/gestoppt")
            else:
                GLib.idle_add(self._set_led, "amber", _("Status unbekannt"))
        except subprocess.TimeoutExpired:
            GLib.idle_add(self._set_led, "red", _("Nicht erreichbar (Timeout)"))
            log.error(f"Drucker {name}: Status-Timeout")
        except Exception as e:
            GLib.idle_add(self._set_led, "red", _("Fehler: %s") % e)
            log.error(f"Drucker {name}: Status-Fehler: {e}")

    def _set_led(self, color: str, text: str) -> bool:
        _C = {"green": "#2ec27e", "red": "#e01b24",
              "amber": "#e5a50a", "gray": "#888888"}
        self._led.set_markup(f"<span color='{_C.get(color, '#888888')}'>●</span>")
        self._stlbl.set_text(text)
        return GLib.SOURCE_REMOVE

    # ── Drucken ───────────────────────────────────────────────────────────────

    def _on_print_clicked(self, _btn) -> None:
        log.info("Druckbutton geklickt")
        if self._selected is None:
            self._show_error(_("Kein Drucker ausgewählt."))
            return
        p   = self._selected
        cmd = f"lp -d {p.name} {' '.join(p.lp_options)} <disc.png>"
        dlg = Gtk.AlertDialog()
        dlg.set_message(_("Disc drucken?"))
        # TRANSLATORS: Print confirmation detail; %(name)s=printer name,
        # %(px)d=resolution in pixels, %(cmd)s=lp command line
        dlg.set_detail(
            _("Drucker:    %(name)s\n"
              "Auflösung:  %(px)d×%(px)d px  (300 DPI)\n\n"
              "%(cmd)s") % {"name": p.name, "px": PRINT_PX, "cmd": cmd}
        )
        dlg.set_buttons([_("Abbrechen"), _("Drucken")])
        dlg.set_cancel_button(0)
        dlg.set_default_button(1)
        dlg.choose(self, None, self._on_print_confirmed)
        log.info(f"Druckdialog geöffnet: {p.name}")

    def _on_print_confirmed(self, dlg: Gtk.AlertDialog, result) -> None:
        try:
            idx = dlg.choose_finish(result)
        except Exception:
            return
        if idx != 1:
            log.info("Drucken abgebrochen")
            return

        p      = self._selected
        hub_mm = self._canvas.hub_mm
        log.info(
            f"Rendere Design für Druck: {PRINT_PX}×{PRINT_PX} px, "
            f"Hub={hub_mm:.0f} mm, Drucker={p.name}"
        )
        try:
            surf = DiscCanvas.render_for_print(self._state, hub_mm)
        except Exception as e:
            log.error(f"Render-Fehler: {e}")
            self._show_error(_("Render-Fehler:\n%s") % e)
            return

        threading.Thread(
            target=self._print_thread, args=(p, surf), daemon=True
        ).start()

    def _print_thread(self, printer: DiscPrinter,
                      surf: cairo.ImageSurface) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            write_print_png(surf, tmp_path)

            cmd = ["lp", "-d", printer.name] + printer.lp_options + [tmp_path]
            log.info(f"lp: {' '.join(cmd)}")

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                job = r.stdout.strip()
                log.info(f"Druckauftrag gesendet: {job}")
                GLib.idle_add(self._on_print_success, job)
            else:
                err = (r.stderr or r.stdout).strip()
                log.error(f"lp Fehler (rc={r.returncode}): {err}")
                GLib.idle_add(self._show_error, _("Druckfehler:\n%s") % err)

        except subprocess.TimeoutExpired:
            log.error("lp Timeout (>30 s)")
            GLib.idle_add(self._show_error,
                          _("Timeout: Drucker antwortet nicht (>30 s)."))
        except Exception as e:
            log.error(f"Druckfehler: {e}")
            GLib.idle_add(self._show_error, _("Druckfehler:\n%s") % e)
        finally:
            try:
                os.unlink(tmp_path)
                log.info(f"Temp-PNG gelöscht: {tmp_path}")
            except Exception:
                pass

    def _on_print_success(self, job_info: str) -> bool:
        dlg = Gtk.AlertDialog()
        dlg.set_heading(_("Druckauftrag gesendet"))
        dlg.set_body(
            job_info or _("Druckauftrag erfolgreich in Warteschlange eingereiht.")
        )
        dlg.set_buttons([_("OK")])
        dlg.set_default_button(0)
        dlg.show(self)
        return GLib.SOURCE_REMOVE

    # ── Undo / Redo ────────────────────────────────────────────────────────────

    def _do_undo(self) -> None:
        self._history.undo()

    def _do_redo(self) -> None:
        self._history.redo()

    def _on_history_changed(self) -> None:
        self._undo_btn.set_sensitive(self._history.can_undo)
        self._redo_btn.set_sensitive(self._history.can_redo)
        tip_u = _("Rückgängig")
        if self._history.can_undo:
            tip_u += f": {self._history.undo_label}"
        tip_r = _("Wiederherstellen")
        if self._history.can_redo:
            tip_r += f": {self._history.redo_label}"
        self._undo_btn.set_tooltip_text(tip_u)
        self._redo_btn.set_tooltip_text(tip_r)

    def _on_key_pressed(self, _ctrl, keyval: int,
                        _keycode: int, state: Gdk.ModifierType) -> bool:
        ctrl  = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if ctrl and not shift and keyval == Gdk.KEY_z:
            self._do_undo()
            return True
        if ctrl and (keyval == Gdk.KEY_y or (shift and keyval == Gdk.KEY_z)):
            self._do_redo()
            return True
        return False

    def _rebuild_panel(self) -> None:
        while (row := self._elem_list.get_row_at_index(0)) is not None:
            self._elem_list.remove(row)
        for elem in self._state.elements:
            self._add_element_row(elem)
        while (row := self._img_list.get_row_at_index(0)) is not None:
            self._img_list.remove(row)
        self._img_rows.clear()
        for img in self._state.images:
            self._add_image_row(img)
        sel = self._state.selected_image
        if sel is not None and sel not in self._state.images:
            self._canvas._select_image(None)
            sel = None
        self._flip_box.set_visible(sel is not None)
        self._canvas.update_cursor()
        self._canvas.refresh()

    def _find_img_row(self, img: ImageElement) -> tuple | None:
        for t in self._img_rows:
            if t[0] is img:
                return t
        return None

    def _on_canvas_transform(self, elem, drag_start: dict, action: str) -> None:
        if isinstance(elem, ImageElement):
            after = {
                "x": elem.x, "y": elem.y,
                "scale_x": elem.scale_x, "scale_y": elem.scale_y,
                "rotation": elem.rotation,
            }
            if action == "move":
                desc = _("Bewegen") + f": {elem.display_name}"
            elif action == "rotate":
                desc = _("Drehen") + f": {elem.display_name}"
            else:
                desc = _("Skalieren") + f": {elem.display_name}"

            def apply_img(s: dict, i: ImageElement = elem) -> None:
                i.x = s["x"]; i.y = s["y"]
                i.scale_x = s["scale_x"]; i.scale_y = s["scale_y"]
                i.rotation = s["rotation"]
                self._canvas.refresh()

            self._history.push(Command(
                desc,
                undo_fn=lambda b=drag_start: apply_img(b),
                redo_fn=lambda a=after: apply_img(a),
            ))
        elif isinstance(elem, TextElement):
            after = {"x": elem.x_mm, "y": elem.y_mm}

            def apply_txt(s: dict, e: TextElement = elem) -> None:
                e.x_mm = s["x"]; e.y_mm = s["y"]
                self._canvas.refresh()

            self._history.push(Command(
                _("Bewegen") + f": {elem.display_text}",
                undo_fn=lambda b=drag_start: apply_txt(b),
                redo_fn=lambda a=after: apply_txt(a),
            ))

    def _on_canvas_zoom(self, img: ImageElement,
                        old_sx: float, old_sy: float,
                        new_sx: float, new_sy: float) -> None:
        img_id = img.id
        if img_id in self._scroll_timer:
            GLib.source_remove(self._scroll_timer.pop(img_id))
        if img_id not in self._scroll_before:
            self._scroll_before[img_id] = (old_sx, old_sy)

        def commit(img_ref: ImageElement = img, iid: int = img_id) -> bool:
            bef = self._scroll_before.pop(iid, None)
            self._scroll_timer.pop(iid, None)
            if bef is None:
                return GLib.SOURCE_REMOVE
            b_sx, b_sy = bef
            a_sx, a_sy = img_ref.scale_x, img_ref.scale_y
            if abs(a_sx - b_sx) < 1e-6 and abs(a_sy - b_sy) < 1e-6:
                return GLib.SOURCE_REMOVE

            def apply_zoom(sx: float, sy: float, i: ImageElement = img_ref) -> None:
                i.scale_x = sx; i.scale_y = sy
                self._canvas.refresh()

            self._history.push(Command(
                _("Zoom") + f": {img_ref.display_name}",
                undo_fn=lambda: apply_zoom(b_sx, b_sy),
                redo_fn=lambda: apply_zoom(a_sx, a_sy),
            ))
            return GLib.SOURCE_REMOVE

        self._scroll_timer[img_id] = GLib.timeout_add(600, commit)

    def _show_error(self, message: str) -> None:
        Gtk.AlertDialog(message=message).show(self)


# ── Application & Entry Point ─────────────────────────────────────────────────

class DiscPrinterApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app) -> None:
        log.info(f"=== Disc Printer gestartet (app_id={APP_ID}) ===")
        MainWindow(self).present()


def main() -> None:
    app  = DiscPrinterApp()
    code = app.run(sys.argv)
    log.info(f"=== Disc Printer beendet (exit={code}) ===")
    sys.exit(code)
