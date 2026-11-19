"""GUI-Szenarien mit echten GTK-Widgets.

Läuft als eigener Prozess gegen einen privaten Broadway-Server (siehe
tests/_gui.py): GTK legt sein Backend beim Start des Prozesses fest, und so
öffnet sich kein Fenster auf dem Bildschirm.

Aufruf: python3 _gui_scenarios.py <szenario> <arbeitsordner>
Ausgabe: "SCENARIO OK" bzw. Traceback; Exit-Code 0/1.
"""
import os
import sys
import time
import traceback
from pathlib import Path
from unittest import mock

import cairo
from gi.repository import Gdk, Gio, GLib

from disc_printer import i18n
from disc_printer.constants import HUB_LARGE_MM, HUB_SMALL_MM
from disc_printer.gui import window as w
from disc_printer.model import DesignState, TextElement, design_fingerprint
from disc_printer.printer import DiscPrinter

WORK = Path(sys.argv[2])
PRINTER = DiscPrinter("Canon_TS705a", "/x.ppd", "Disc", "Disc", "om_square_120x120mm")


def pump(ms: int) -> None:
    """Hauptschleife ``ms`` Millisekunden laufen lassen (Timer feuern)."""
    ctx = GLib.MainContext.default()
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.005)


def png(name: str, rgb=(1, 0, 0)) -> str:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 40, 30)
    cr = cairo.Context(surf)
    cr.set_source_rgb(*rgb)
    cr.paint()
    path = WORK / name
    surf.write_to_png(str(path))
    return str(path)


def first_row(listbox):
    return listbox.get_row_at_index(0)


def fresh_fp() -> str:
    return design_fingerprint(DesignState(), HUB_LARGE_MM)


class FakeSaveDialog:
    def __init__(self, path):
        self._path = path

    def save_finish(self, _result):
        return Gio.File.new_for_path(str(self._path))


class FakeChoice:
    def __init__(self, idx):
        self._idx = idx

    def choose_finish(self, _result):
        return self._idx


def make_dirty(win) -> dict:
    """Alles ändern, was zum Design gehört; Regler-Timer laufen lassen."""
    win._on_detection_done([PRINTER])
    win._add_image_from_path(png("a.png"))
    win._load_bg_image(png("bg.png", (0, 0, 1)))
    elem = TextElement("Hallo", "Sans", 20, False, False, (0, 0, 0, 1))
    win._state.elements.append(elem)
    win._rebuild_panel()
    win._r33.set_active(True)                       # Hub 33 mm (mit Undo-Eintrag)
    red = Gdk.RGBA()
    red.red, red.green, red.blue, red.alpha = 1, 0, 0, 1
    win._color_btn.set_rgba(red)                   # Hintergrundfarbe
    img = win._state.images[0]
    row = win._find_img_row(img)
    row[3].set_value(0.4)                          # Opazität  → Timer
    row[5].set_value(1.3)                          # Helligkeit → Timer
    row[7].set_value(0.8)                          # Kontrast  → Timer
    win._on_canvas_zoom(img, 1.0, 1.0, 1.5, 1.5)   # Scroll-Zoom → Timer
    tids = (list(win._opacity_timer.values()) + list(win._brightness_timer.values())
            + list(win._contrast_timer.values()) + list(win._scroll_timer.values()))
    assert len(tids) == 4, f"erwartet 4 laufende Regler-Timer, gefunden {len(tids)}"
    assert win._history.can_undo
    assert win._has_unsaved_changes()
    return {"tids": tids}


# ── Szenarien ────────────────────────────────────────────────────────────────

def scenario_reset(win):
    info = make_dirty(win)
    lang_before = i18n.get_current_lang()
    selected_before = win._selected
    dd_before = win._dropdown.get_selected()
    win._do_undo()                                  # Redo-Stapel befüllen
    assert win._history.can_redo

    win._reset_design()

    s = win._state
    assert design_fingerprint(s, win._canvas.hub_mm) == fresh_fp(), "Design nicht frisch"
    assert s.images == [] and s.elements == [] and s.bg_surface is None
    assert s.bg_path == "" and s.bg_color == (1.0, 1.0, 1.0, 1.0)
    assert (s.bg_img_x_mm, s.bg_img_y_mm, s.bg_img_scale) == (0.0, 0.0, 1.0)
    assert s.selected_image is None and s.selected_element is None
    rgba = win._color_btn.get_rgba()
    assert (rgba.red, rgba.green, rgba.blue, rgba.alpha) == (1, 1, 1, 1), "Farbknopf"
    assert win._canvas.hub_mm == HUB_LARGE_MM and win._r50.get_active()
    assert first_row(win._img_list) is None and first_row(win._elem_list) is None
    assert win._img_rows == []
    assert win._bg_file_label.get_text() == i18n._("(kein Bild)")
    assert not win._clear_img_btn.get_sensitive()
    assert not win._transform_box.get_sensitive()
    assert win._scale_slider.get_value() == 1.0
    assert not win._history.can_undo and not win._history.can_redo
    assert not win._undo_btn.get_sensitive() and not win._redo_btn.get_sensitive()
    # Timer weg, auch als GLib-Quelle
    for d in (win._opacity_timer, win._brightness_timer, win._contrast_timer,
              win._scroll_timer, win._opacity_before, win._brightness_before,
              win._contrast_before, win._scroll_before):
        assert d == {}, f"Timer-Zustand nicht leer: {d}"
    ctx = GLib.MainContext.default()
    for tid in info["tids"]:
        src = ctx.find_source_by_id(tid)
        assert src is None or src.is_destroyed(), f"Timer {tid} läuft noch"
    pump(900)                                       # später feuernde Commits?
    assert not win._history.can_undo, "verspäteter Regler-Commit nach Reset"
    # Unverändert
    assert win._selected is selected_before and win._dropdown.get_selected() == dd_before
    assert i18n.get_current_lang() == lang_before
    assert not win._has_unsaved_changes()


def scenario_dirty_detection(win):
    assert not win._has_unsaved_changes(), "frischer Start gilt als geändert"
    win._r33.set_active(True)
    assert win._has_unsaved_changes()
    win._do_undo()
    assert not win._has_unsaved_changes(), "Undo zurück auf gespeicherten Stand"
    # Änderung ohne Undo-Eintrag (Hintergrund-Zoom-Regler) wird auch erkannt
    win._load_bg_image(png("bg.png"))
    win._clean_fp = win._current_fingerprint()
    win._scale_slider.set_value(1.7)
    assert win._has_unsaved_changes(), "Zoom-Regler nicht erkannt"
    # Erfolgreiches Speichern: sauber, Fortsetzung läuft
    called = []
    win._on_save_dialog_done(FakeSaveDialog(WORK / "d.discprint"), None,
                             lambda: called.append(1))
    assert called == [1] and not win._has_unsaved_changes()
    # Öffnen: sauber
    win._r33.set_active(True)
    from disc_printer import file_format as fmt
    st, hub = fmt.load(WORK / "d.discprint")
    win._apply_loaded_design(st, hub)
    assert not win._has_unsaved_changes()


def scenario_new_prompt(win):
    created = []
    real_alert = w.Gtk.AlertDialog

    class SpyAlert(real_alert):
        def choose(self, *a):
            created.append(self.get_buttons())

    with mock.patch.object(w.Gtk, "AlertDialog", SpyAlert):
        # sauber: kein Dialog, direkt zurücksetzen
        win._on_new_clicked(None)
        assert created == []
        # geändert: Dialog mit Abbrechen / Verwerfen / Speichern
        win._add_image_from_path(png("a.png"))
        win._on_new_clicked(None)
        assert len(created) == 1 and len(created[0]) == 3, created
    # Abbrechen: nichts passiert
    win._on_new_confirmed(FakeChoice(0), None)
    assert len(win._state.images) == 1 and win._has_unsaved_changes()
    # Speichern …: Speichern-Dialog mit Reset als Fortsetzung
    with mock.patch.object(win, "_start_save") as start_save:
        win._on_new_confirmed(FakeChoice(2), None)
    start_save.assert_called_once_with(on_saved=win._reset_design)
    # Speichern schlägt fehl: kein Reset
    with mock.patch.object(win, "_show_error") as err:
        win._on_save_dialog_done(FakeSaveDialog(WORK / "fehlt" / "x.discprint"),
                                 None, win._reset_design)
    err.assert_called_once()
    assert len(win._state.images) == 1, "Reset trotz Speicherfehler"
    # Speichern gelingt: danach Reset
    win._on_save_dialog_done(FakeSaveDialog(WORK / "ok.discprint"), None,
                             win._reset_design)
    assert (WORK / "ok.discprint").exists() and win._state.images == []
    # Verwerfen: Reset
    win._add_image_from_path(png("b.png"))
    win._on_new_confirmed(FakeChoice(1), None)
    assert win._state.images == [] and not win._has_unsaved_changes()


def scenario_new_button(win):
    hb = win.get_titlebar()
    icons = []
    child = hb.get_first_child()
    stack = [child]
    while stack:
        c = stack.pop()
        while c is not None:
            if isinstance(c, w.Gtk.Button) and c.get_icon_name():
                icons.append((c.get_icon_name(), c.get_tooltip_text()))
            stack.append(c.get_first_child())
            c = c.get_next_sibling()
    names = [n for n, _t in icons]
    assert "document-new-symbolic" in names, names
    assert names.index("document-new-symbolic") < names.index("document-open-symbolic"), names
    tip = dict(icons)["document-new-symbolic"]
    assert tip == i18n._("Neues Design"), tip


# ── Ablauf ───────────────────────────────────────────────────────────────────

def main() -> int:
    name = sys.argv[1]
    fn = globals()[f"scenario_{name}"]
    result = {"rc": 1}
    app = w.DiscPrinterApp()

    def run(_data=None):
        try:
            fn(app.get_active_window())
            print(f"{name} OK", flush=True)
            result["rc"] = 0
        except Exception:
            traceback.print_exc()
        app.quit()
        return False

    app.connect("activate", lambda _a: GLib.idle_add(run))
    with mock.patch.object(w.MainWindow, "_detect_async", lambda self: None), \
         mock.patch.object(w.MainWindow, "_status_thread", lambda self, *a: None):
        app.run([])
    return result["rc"]


if __name__ == "__main__":
    sys.exit(main())
