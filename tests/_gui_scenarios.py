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


class FakeOpenDialog:
    def __init__(self, path):
        self._path = path

    def open_finish(self, _result):
        return Gio.File.new_for_path(str(self._path))


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
    win._scale_slider.set_value(1.4)               # Hintergrund-Zoom → Timer
    win._nudge(5, 0)                               # Pfeilknopf → Timer
    tids = (list(win._opacity_timer.values()) + list(win._brightness_timer.values())
            + list(win._contrast_timer.values()) + list(win._scroll_timer.values())
            + [win._bg_zoom_timer, win._bg_nudge_timer])
    assert all(tids) and len(tids) == 6, f"erwartet 6 laufende Timer: {tids}"
    assert win._history.can_undo
    assert win._has_unsaved_changes()
    return {"tids": tids}


# ── Szenarien ────────────────────────────────────────────────────────────────

def scenario_reset(win):
    check_lang(win, "Start")
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
    assert win._bg_zoom_timer == 0 and win._bg_nudge_timer == 0
    assert win._bg_zoom_before is None and win._bg_nudge_before is None
    ctx = GLib.MainContext.default()
    for tid in info["tids"]:
        src = ctx.find_source_by_id(tid)
        assert src is None or src.is_destroyed(), f"Timer {tid} läuft noch"
    pump(900)                                       # später feuernde Commits?
    assert not win._history.can_undo, "verspäteter Regler-Commit nach Reset"
    # Unverändert
    assert win._selected is selected_before and win._dropdown.get_selected() == dd_before
    assert i18n.get_current_lang() == lang_before
    check_lang(win, "nach Neues Design")            # Feld, nicht nur interner Wert
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


class PromptSpy:
    """Ersetzt Gtk.AlertDialog: merkt sich Knöpfe und den echten Callback."""

    def __init__(self):
        self.calls = []
        spy = self
        real = w.Gtk.AlertDialog

        class SpyAlert(real):
            def choose(self, parent, cancellable, callback):
                spy.calls.append({"buttons": self.get_buttons(),
                                  "message": self.get_message(),
                                  "callback": callback})

        self.patch = mock.patch.object(w.Gtk, "AlertDialog", SpyAlert)

    def answer(self, idx):
        """Knopf ``idx`` "drücken": echten Callback der letzten Rückfrage aufrufen."""
        self.calls[-1]["callback"](FakeChoice(idx), None)

    def __enter__(self):
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()


def assert_prompt(spy, n):
    assert len(spy.calls) == n, f"erwartet {n} Rückfragen, waren {len(spy.calls)}"
    if n:
        c = spy.calls[-1]
        assert c["buttons"] == [i18n._("Abbrechen"), i18n._("Verwerfen"),
                                i18n._("Speichern …")], c["buttons"]
        assert c["message"] == i18n._("Ungespeicherte Änderungen verwerfen?")


def scenario_new_prompt(win):
    with PromptSpy() as spy:
        # sauber: kein Dialog, direkt zurücksetzen
        win._on_new_clicked(None)
        assert_prompt(spy, 0)
        # geändert: Dialog mit Abbrechen / Verwerfen / Speichern
        win._add_image_from_path(png("a.png"))
        win._on_new_clicked(None)
        assert_prompt(spy, 1)
        # Abbrechen: nichts passiert
        spy.answer(0)
        assert len(win._state.images) == 1 and win._has_unsaved_changes()
        # Speichern …: Speichern-Dialog mit Reset als Fortsetzung
        with mock.patch.object(win, "_start_save") as start_save:
            spy.answer(2)
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
        win._on_new_clicked(None)
        assert_prompt(spy, 2)
        spy.answer(1)
        assert win._state.images == [] and not win._has_unsaved_changes()


def scenario_open_prompt(win):
    with PromptSpy() as spy, \
         mock.patch.object(win, "_show_open_dialog") as show_open:
        # sauber: Öffnen-Dialog direkt
        win._on_open_clicked(None)
        assert_prompt(spy, 0)
        assert show_open.call_count == 1
        # geändert: erst Rückfrage
        win._add_image_from_path(png("a.png"))
        win._on_open_clicked(None)
        assert_prompt(spy, 1)
        assert show_open.call_count == 1, "Öffnen-Dialog vor der Rückfrage"
        spy.answer(0)                                   # Abbrechen
        assert show_open.call_count == 1 and len(win._state.images) == 1
        spy.answer(1)                                   # Verwerfen
        assert show_open.call_count == 2
        with mock.patch.object(win, "_start_save") as start_save:
            spy.answer(2)                               # Speichern …
        start_save.assert_called_once_with(on_saved=win._show_open_dialog)
        # Speichern gelingt -> danach Öffnen-Dialog
        win._on_save_dialog_done(FakeSaveDialog(WORK / "o.discprint"), None,
                                 win._show_open_dialog)
        assert show_open.call_count == 3


def scenario_close_prompt(win):
    app = win.get_application()

    def fresh(dirty: bool):
        nw = w.MainWindow(app)
        nw.present()
        if dirty:
            nw._add_image_from_path(png("c.png"))
        pump(30)
        return nw

    def is_open(x):
        return x in app.get_windows()

    with PromptSpy() as spy:
        # sauber: schließt ohne Rückfrage
        a = fresh(False)
        a.close()
        pump(30)
        assert not is_open(a) and spy.calls == []
        # geändert: Fenster bleibt offen, Rückfrage
        b = fresh(True)
        b.close()
        pump(30)
        assert is_open(b), "Fenster trotz ungespeicherter Änderungen geschlossen"
        assert_prompt(spy, 1)
        spy.answer(0)                                   # Abbrechen
        pump(30)
        assert is_open(b), "Abbrechen hat das Fenster geschlossen"
        b.close()                                       # erneut: wieder Rückfrage
        pump(30)
        assert_prompt(spy, 2)
        spy.answer(1)                                   # Verwerfen
        pump(30)
        assert not is_open(b), "Verwerfen schließt nicht"
        # Speichern …: Fehler -> offen; Erfolg -> zu
        c = fresh(True)
        c.close()
        pump(30)
        assert_prompt(spy, 3)
        with mock.patch.object(c, "_start_save") as start_save:
            spy.answer(2)
        start_save.assert_called_once_with(on_saved=c._close_now)
        with mock.patch.object(c, "_show_error"):
            c._on_save_dialog_done(FakeSaveDialog(WORK / "fehlt" / "c.discprint"),
                                   None, c._close_now)
        pump(30)
        assert is_open(c), "nach Speicherfehler geschlossen"
        c._on_save_dialog_done(FakeSaveDialog(WORK / "c.discprint"), None, c._close_now)
        pump(30)
        assert not is_open(c) and (WORK / "c.discprint").exists()
        assert len(spy.calls) == 3, "nach dem Speichern erneut gefragt"


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


# ── Log-Szenarien (B) ────────────────────────────────────────────────────────

LOG = Path(os.environ["DISC_PRINTER_LOG_FILE"])


def log_lines(needle: str) -> list[str]:
    return [l for l in LOG.read_text(encoding="utf-8").splitlines() if needle in l]


def scenario_printer_once(win):
    threads = []
    with mock.patch.object(w.threading, "Thread") as thread:
        thread.side_effect = lambda **kw: threads.append(kw) or mock.Mock()
        win._on_detection_done([PRINTER])
    assert len(log_lines("Printer selected: Canon_TS705a")) == 1, log_lines("Printer selected")
    assert len(threads) == 1, f"Status-Threads: {len(threads)}"
    assert win._selected is PRINTER and win._dropdown.get_selected() == 0
    # Auswahl durch den Benutzer funktioniert weiter (Signal nicht gesperrt)
    other = DiscPrinter("Other", "/y.ppd", "Disc", "Disc", "x")
    with mock.patch.object(w.threading, "Thread", return_value=mock.Mock()):
        win._on_detection_done([PRINTER, other])
        win._dropdown.set_selected(1)
    assert win._selected is other
    assert len(log_lines("Printer selected: Other")) == 1
    # Keine Drucker: kein Fehler, keine Auswahl-Zeile
    win._on_detection_done([])
    assert len(log_lines("Printer selected")) == 3


def scenario_save_logged_once(win):
    win._on_save_dialog_done(FakeSaveDialog(WORK / "x.discprint"), None)
    assert len(log_lines("Design saved:")) == 1, log_lines("Design saved")
    from disc_printer import file_format as fmt
    st, hub = fmt.load(WORK / "x.discprint")
    win._apply_loaded_design(st, hub)
    assert len(log_lines("Design loaded:")) == 1


def scenario_slider_final_value(win):
    win._add_image_from_path(png("a.png"))
    win._load_bg_image(png("bg.png"))
    img = win._state.images[0]
    row = win._find_img_row(img)
    for v in (1.1, 1.2, 1.3, 1.4):
        row[5].set_value(v)                    # Helligkeit
    for v in (0.9, 0.8, 0.7):
        row[7].set_value(v)                    # Kontrast
    for v in (0.9, 0.5):
        row[3].set_value(v)                    # Opazität
    for v in (1.1, 1.2, 1.3):
        win._scale_slider.set_value(v)         # Hintergrund-Zoom (Regler)
    win._canvas._select_image(img)
    for _ in range(3):
        win._canvas._on_scroll(None, 0, -1)    # Mausrad auf dem Bild
    pump(50)
    for needle in ("brightness", "contrast", "opacity", "zoom"):
        assert log_lines(needle) == [], f"Zwischenschritt geloggt: {log_lines(needle)}"
    pump(900)
    assert [l.split("] ", 2)[-1] for l in log_lines("brightness")] == ["Image 'a.png' brightness: 140%"], log_lines("brightness")
    assert [l.split("] ", 2)[-1] for l in log_lines("contrast")] == ["Image 'a.png' contrast: 70%"], log_lines("contrast")
    assert [l.split("] ", 2)[-1] for l in log_lines("opacity")] == ["Image 'a.png' opacity: 50%"], log_lines("opacity")
    assert [l.split("] ", 2)[-1] for l in log_lines("Background image zoom")] == ["Background image zoom: 1.30×"]
    assert len(log_lines("Image 'a.png' zoom:")) == 1, log_lines("zoom")
    # Mausrad auf dem Hintergrund (kein Bild ausgewählt)
    win._canvas._select_image(None)
    for _ in range(4):
        win._canvas._on_scroll(None, 0, -1)
    pump(900)
    assert len(log_lines("Background image zoom")) == 2, log_lines("Background image zoom")
    assert win._scale_slider.get_value() == win._state.bg_img_scale


def scenario_drag_only_when_moved(win):
    c = win._canvas
    win._load_bg_image(png("bg.png"))
    # Hintergrund: nur angeklickt
    c._drag_target = "bg"
    c._drag_start_bg_x, c._drag_start_bg_y = win._state.bg_img_x_mm, win._state.bg_img_y_mm
    c._on_drag_end(None, 0, 0)
    assert log_lines("Background image moved") == []
    # Hintergrund: wirklich verschoben
    c._drag_target = "bg"
    c._drag_start_bg_x, c._drag_start_bg_y = win._state.bg_img_x_mm, win._state.bg_img_y_mm
    win._state.bg_img_x_mm += 2.0
    c._on_drag_end(None, 10, 0)
    assert len(log_lines("Background image moved")) == 1
    # Bild: Klick ohne Bewegung -> kein Log, kein Undo-Eintrag
    win._add_image_from_path(png("a.png"))
    img = win._state.images[0]
    n_hist = len(win._history._undo)
    c._drag_target, c._drag_handle = img, -1
    c._drag_start = {"x": img.x, "y": img.y}
    c._on_drag_end(None, 0, 0)
    assert log_lines("Image 'a.png' moved") == []
    assert len(win._history._undo) == n_hist, "leerer Undo-Eintrag nach Klick"
    # Bild: verschoben -> Log und Undo-Eintrag
    c._drag_target, c._drag_handle = img, -1
    c._drag_start = {"x": img.x, "y": img.y}
    img.x += 3.0
    c._on_drag_end(None, 5, 0)
    assert len(log_lines("Image 'a.png' moved")) == 1
    assert len(win._history._undo) == n_hist + 1
    # Text: Klick ohne Bewegung
    t = TextElement("Hallo", "Sans", 20, False, False, (0, 0, 0, 1))
    win._state.elements.append(t)
    c._drag_target, c._drag_handle = t, -1
    c._drag_start = {"x": t.x_mm, "y": t.y_mm}
    c._on_drag_end(None, 0, 0)
    assert log_lines("Text 'Hallo' moved") == []
    assert len(win._history._undo) == n_hist + 1


# ── Undo für Hintergrund-Gesten (D) ──────────────────────────────────────────

def labels(win):
    return [c.description for c in win._history._undo]


def bg(win):
    st = win._state
    return (st.bg_img_x_mm, st.bg_img_y_mm, st.bg_img_scale)


def scenario_bg_undo(win):
    win._load_bg_image(png("bg.png"))
    base = len(labels(win))
    zoom = i18n._("Zoom") + ": " + i18n._("Hintergrund")
    move = i18n._("Bewegen") + ": " + i18n._("Hintergrund")
    reset = i18n._("Zurücksetzen") + ": " + i18n._("Hintergrund")

    # Regler: viele Schritte, ein Eintrag (Endwert)
    for v in (1.1, 1.2, 1.3, 1.4, 1.5):
        win._scale_slider.set_value(v)
    pump(50)
    assert len(labels(win)) == base, "Eintrag vor Ende der Geste"
    pump(700)
    assert labels(win)[base:] == [zoom], labels(win)
    win._do_undo()
    assert bg(win) == (0.0, 0.0, 1.0) and win._scale_slider.get_value() == 1.0
    win._do_redo()
    assert bg(win)[2] == 1.5 and win._scale_slider.get_value() == 1.5

    # Mausrad: ein Eintrag je Geste
    n = len(labels(win))
    win._canvas._select_image(None)
    for _ in range(4):
        win._canvas._on_scroll(None, 0, -1)
    pump(700)
    assert labels(win)[n:] == [zoom]
    after_wheel = bg(win)[2]
    win._do_undo()
    assert bg(win)[2] == 1.5 and win._scale_slider.get_value() == 1.5
    win._do_redo()
    assert bg(win)[2] == after_wheel

    # Pfeilknöpfe: Klicks kurz hintereinander -> ein Eintrag
    n = len(labels(win))
    win._nudge(5, 0); win._nudge(5, 0); win._nudge(0, -5)
    pump(700)
    assert labels(win)[n:] == [move], labels(win)[n:]
    assert bg(win)[:2] == (10.0, -5.0)
    win._do_undo()
    assert bg(win)[:2] == (0.0, 0.0)
    win._do_redo()
    # mit Pause -> zwei Einträge
    n = len(labels(win))
    win._nudge(5, 0); pump(700); win._nudge(5, 0); pump(700)
    assert labels(win)[n:] == [move, move]

    # Zentrieren: eigener Eintrag; offene Gesten werden vorher abgeschlossen
    n = len(labels(win))
    win._scale_slider.set_value(2.0)
    win._nudge(0, 5)
    win._on_reset_transform(None)                  # ohne Pause
    assert labels(win)[n:] == [zoom, move, reset], labels(win)[n:]
    assert bg(win) == (0.0, 0.0, 1.0) and win._scale_slider.get_value() == 1.0
    pump(700)
    assert labels(win)[n:] == [zoom, move, reset], "verspäteter Eintrag nach Reset"
    win._do_undo()
    assert bg(win) == (20.0, 0.0, 2.0), bg(win)
    win._do_undo()
    assert bg(win) == (20.0, -5.0, 2.0), bg(win)
    win._do_redo(); win._do_redo()
    # Zentrieren ohne Änderung: kein Eintrag
    n = len(labels(win))
    win._on_reset_transform(None)
    assert len(labels(win)) == n

    # Maus-Drag des Hintergrunds
    c = win._canvas
    c._drag_target = "bg"
    c._drag_start_bg_x, c._drag_start_bg_y = 0.0, 0.0
    win._state.bg_img_x_mm, win._state.bg_img_y_mm = 7.0, 3.0
    c._on_drag_end(None, 1, 1)
    assert labels(win)[-1] == move
    win._do_undo()
    assert bg(win)[:2] == (0.0, 0.0)
    win._do_redo()
    assert bg(win)[:2] == (7.0, 3.0)

    # Undo mitten in der Geste: die Geste selbst wird rückgängig gemacht
    win._scale_slider.set_value(1.8)
    win._do_undo()
    assert bg(win)[2] == 1.0 and win._history.redo_label == zoom
    pump(700)
    assert win._history.redo_label == zoom, "Geste nach Undo erneut eingetragen"


def scenario_img_slider_undo(win):
    _ = i18n._
    win._add_image_from_path(png("a.png"))
    win._load_bg_image(png("bg.png"))
    img = win._state.images[0]
    row = win._find_img_row(img)
    name = img.display_name
    L = {"op": _("Opazität") + f": {name}", "br": _("Helligkeit") + f": {name}",
         "co": _("Kontrast") + f": {name}", "zoom": _("Zoom") + f": {name}",
         "flip": _("H-Spiegeln") + f": {name}",
         "bgzoom": _("Zoom") + ": " + _("Hintergrund"),
         "reset": _("Zurücksetzen") + ": " + _("Hintergrund")}

    # 1. Undo mitten in der Geste nimmt genau diese Geste zurück
    for v in (1.2, 1.4, 1.6):
        row[5].set_value(v)
    win._do_undo()
    assert img.brightness == 1.0 and row[5].get_value() == 1.0
    assert win._history.redo_label == L["br"], win._history.redo_label
    pump(700)
    assert win._history.redo_label == L["br"], "Geste nach Undo erneut eingetragen"
    win._do_redo()
    assert img.brightness == 1.6 and row[5].get_value() == 1.6

    # 2. Andere Aktion mitten in der Geste: Geste zuerst
    n = len(labels(win))
    row[3].set_value(0.5)
    win._canvas._select_image(img)
    win._on_flip(True)
    assert labels(win)[n:] == [L["op"], L["flip"]], labels(win)[n:]
    pump(700)
    assert labels(win)[n:] == [L["op"], L["flip"]], "verspäteter Eintrag"

    # 3. Gemischt mit Hintergrund: Startreihenfolge
    n = len(labels(win))
    row[7].set_value(0.8)                       # Kontrast
    win._scale_slider.set_value(1.5)            # Hintergrund-Zoom
    win._canvas._select_image(img)
    sx0 = img.scale_x
    win._canvas._on_scroll(None, 0, -1)         # Mausrad auf dem Bild
    assert img.scale_x != sx0
    win._on_reset_transform(None)
    assert labels(win)[n:] == [L["co"], L["bgzoom"], L["zoom"], L["reset"]], labels(win)[n:]
    pump(700)
    assert len(labels(win)) == n + 4
    # rückwärts exakt: Reset, Bild-Zoom, Hintergrund-Zoom, Kontrast
    win._do_undo(); assert win._state.bg_img_scale == 1.5
    win._do_undo(); assert img.scale_x == sx0
    win._do_undo(); assert win._state.bg_img_scale == 1.0
    win._do_undo(); assert img.contrast == 1.0 and row[7].get_value() == 1.0
    for _i in range(4):
        win._do_redo()

    # 4. Eine Geste endet von selbst: andere laufende Geste bleibt offen
    n = len(labels(win))
    row[3].set_value(0.3)                       # Deckkraft startet
    pump(300)
    row[5].set_value(1.1)                       # Helligkeit startet später
    pump(400)                                   # Deckkraft fertig, Helligkeit offen
    assert labels(win)[n:] == [L["op"]], labels(win)[n:]
    assert ("brightness", img.id) in win._img_gestures
    pump(700)
    assert labels(win)[n:] == [L["op"], L["br"]], labels(win)[n:]
    assert win._img_gestures == {}


# ── Sprach-Auswahlfeld = tatsächliche Sprache ────────────────────────────────

def _compile_locales(codes):
    """Eigene .mo im Arbeitsordner: unabhängig von `make compile-mo`."""
    import shutil, subprocess
    src = Path(i18n.__file__).parent / "locale"
    dst = WORK / "locale"
    dst.mkdir()
    shutil.copy(src / "LINGUAS", dst / "LINGUAS")
    for c in codes:
        out = dst / c / "LC_MESSAGES"
        out.mkdir(parents=True)
        subprocess.run(["msgfmt", "-o", str(out / "disc_printer.mo"),
                        str(src / c / "LC_MESSAGES" / "disc_printer.po")], check=True)
    return dst


def _expected_ui(code, msgid):
    import gettext
    if code == "de":
        return msgid
    return gettext.translation("disc_printer", localedir=str(i18n._LOCALE_DIR),
                               languages=[code]).gettext(msgid)


def _main_window(app):
    wins = [x for x in app.get_windows() if isinstance(x, w.MainWindow) and x.get_visible()]
    assert len(wins) == 1, f"erwartet genau ein Hauptfenster: {wins}"
    return wins[0]


def check_lang(win, step):
    """Auswahlfeld, aktive Übersetzung und sichtbare Beschriftung stimmen überein."""
    langs = i18n.available_languages()
    dd = win._lang_dd
    idx = dd.get_selected()
    assert idx < len(langs), f"{step}: Feld ohne Auswahl ({idx})"
    shown = langs[idx]
    actual = i18n.effective_lang()
    assert shown == actual, f"{step}: Feld zeigt {shown}, Oberfläche ist {actual}"
    # tatsächlich angezeigter Text, unabhängig von i18n ermittelt
    assert win._lang_label.get_label() == _expected_ui(actual, "Sprache:"), \
        f"{step}: Beschriftung {win._lang_label.get_label()!r} passt nicht zu {actual}"
    assert dd.get_model().get_string(idx) == i18n.LANG_NAMES[actual]


def scenario_lang_selector(win):
    app = win.get_application()
    i18n._LOCALE_DIR = _compile_locales(["fr", "en", "ar"])
    i18n.switch_language(None)                      # Start ohne Sprache: Deutsch
    w.MainWindow(app).present(); win.close(); pump(50)   # Feld neu aufbauen
    win = _main_window(app)
    check_lang(win, "Start ohne Sprache")
    settings_file = Path(os.environ["HOME"]) / ".config" / "disc-printer" / "settings.json"

    for code in ("fr", "en", "de", "ar", "de"):     # zurück auf Deutsch = Fehlerfall
        win._lang_dd.set_selected(i18n.available_languages().index(code))
        pump(100)
        win = _main_window(app)
        check_lang(win, f"Wechsel -> {code}")
        import json
        assert json.loads(settings_file.read_text())["language"] == code
    assert i18n.get_current_lang() is None          # interner Deutsch-Fallback

    # Neues Design (mit Rückfrage, Verwerfen)
    win._add_image_from_path(png("a.png"))
    with PromptSpy() as spy:
        win._on_new_clicked(None)
        spy.answer(0); check_lang(win, "Neues Design -> Abbrechen")
        spy.answer(1); check_lang(win, "Neues Design -> Verwerfen")
    assert win._state.images == []

    # Öffnen einer gespeicherten Datei
    from disc_printer import file_format
    st = DesignState(); st.elements.append(TextElement("x", "Sans", 20, False, False, (0, 0, 0, 1)))
    f = WORK / "l.discprint"
    file_format.save(f, st, HUB_SMALL_MM)
    win._on_open_dialog_done(FakeOpenDialog(f), None)
    assert win._state.elements and win._state.elements[0].text == "x"
    check_lang(win, "Öffnen")

    # .mo fehlt: Oberfläche bleibt deutsch, Feld muss Deutsch zeigen
    i18n.switch_language("bg")
    assert i18n.effective_lang() == "de" and i18n._("Sprache:") == "Sprache:"
    i18n.switch_language(None)


# ── Sprachwechsel behält das Design (ein Fenster, keine Rückfrage) ──────────

def _fp(win):
    return design_fingerprint(win._state, win._canvas.hub_mm)


def _switch(win, code):
    app = win.get_application()
    win._lang_dd.set_selected(i18n.available_languages().index(code))
    pump(100)
    mains = [x for x in app.get_windows() if isinstance(x, w.MainWindow)]
    assert mains == [win], f"nach Wechsel -> {code}: Fenster {mains}"
    assert win.get_visible()
    check_lang(win, f"Wechsel -> {code}")
    assert _key_ctrls(win) == _KEYS["n"], \
        f"Tastatur-Controller: {_key_ctrls(win)} statt {_KEYS['n']} (Strg+Z mehrfach)"


_KEYS = {}


def _key_ctrls(win):
    ctrls = win.observe_controllers()
    return sum(isinstance(ctrls.get_item(i), w.Gtk.EventControllerKey)
               for i in range(ctrls.get_n_items()))


def _rgba(btn):
    c = btn.get_rgba()
    return (round(c.red, 3), round(c.green, 3), round(c.blue, 3), round(c.alpha, 3))


def scenario_lang_switch(win):
    app = win.get_application()
    i18n._LOCALE_DIR = _compile_locales(["fr", "en"])
    i18n.switch_language(None)
    w.MainWindow(app).present(); win.close(); pump(50)
    win = _main_window(app)
    other = DiscPrinter("Other", "/y.ppd", "Disc", "Disc", "x")
    _KEYS["n"] = _key_ctrls(win)                    # frisches Fenster (GTK + unserer)

    with PromptSpy() as spy:
        # 1. Ohne Änderungen
        _switch(win, "en")
        assert not win._has_unsaved_changes() and not win._history.can_undo
        _switch(win, "de")

        # 2. Mit ungespeicherten Änderungen, Undo- und Redo-Stapel, Druckerwahl
        win._on_detection_done([PRINTER, other])
        win._dropdown.set_selected(1)
        assert win._selected is other
        fps = [_fp(win)]
        win._add_image_from_path(png("a.png")); fps.append(_fp(win))
        win._load_bg_image(png("bg.png", (0, 0, 1))); fps.append(_fp(win))
        win._r33.set_active(True); fps.append(_fp(win))
        red = Gdk.RGBA(); red.red, red.green, red.blue, red.alpha = 1, 0, 0, 1
        win._color_btn.set_rgba(red); fps.append(_fp(win))
        img = win._state.images[0]
        win._find_img_row(img)[3].set_value(0.4); pump(700); fps.append(_fp(win))
        win._canvas._select_image(img)
        win._on_flip(True); fps.append(_fp(win))
        win._do_undo()                                  # Redo-Stapel: Spiegeln
        assert _fp(win) == fps[-2]
        name = img.display_name
        spec = [("Bild hinzufügen", None), ("Hintergrundbild laden", None),
                ("Hub-Größe", None), ("Hintergrundfarbe", None), ("Opazität", name)]

        def expected(code):
            return [_expected_ui(code, m) + (f": {n}" if n else "") for m, n in spec]

        assert labels(win) == expected("de"), labels(win)
        fp_before, clean_before = _fp(win), win._clean_fp
        selected_logs = len(log_lines("Printer selected"))

        _switch(win, "fr")
        # Design, Stand, Auswahl unverändert
        assert _fp(win) == fp_before and win._clean_fp == clean_before
        assert win._has_unsaved_changes()
        assert win._state.selected_image is img and win._flip_box.get_visible()
        # Widgets zeigen das Design
        assert win._r33.get_active() and win._canvas.hub_mm == HUB_SMALL_MM
        assert _rgba(win._color_btn) == (1, 0, 0, 1)
        assert win._bg_file_label.get_text() == "bg.png"
        assert win._clear_img_btn.get_sensitive() and win._transform_box.get_sensitive()
        assert win._find_img_row(img)[3].get_value() == 0.4
        # Drucker: gleiche Auswahl, kein erneutes "Printer selected"
        assert win._selected is other and win._dropdown.get_selected() == 1
        assert win._dropdown.get_sensitive()
        assert len(log_lines("Printer selected")) == selected_logs
        assert win._stlbl.get_text() == _expected_ui("fr", "Prüfe Status …"), win._stlbl.get_text()
        # Undo/Redo-Beschriftungen in der neuen Sprache
        assert labels(win) == expected("fr"), labels(win)
        assert win._history.redo_label == _expected_ui("fr", "H-Spiegeln") + f": {name}"
        assert win._undo_btn.get_tooltip_text() == \
            _expected_ui("fr", "Rückgängig") + ": " + expected("fr")[-1]
        assert win._redo_btn.get_tooltip_text() == \
            _expected_ui("fr", "Wiederherstellen") + ": " + win._history.redo_label

        # 3. Undo/Redo nach dem Wechsel: Einträge von vorher wirken auf die neuen Widgets
        win._do_redo(); assert _fp(win) == fps[-1]
        for k in range(len(fps) - 1, 0, -1):
            win._do_undo()
            assert _fp(win) == fps[k - 1], f"Undo {k}"
            if k == 5: assert win._find_img_row(img)[3].get_value() == 1.0
            if k == 4: assert _rgba(win._color_btn) == (1, 1, 1, 1)
            if k == 3: assert win._r50.get_active() and win._canvas.hub_mm == HUB_LARGE_MM
            if k == 2: assert win._bg_file_label.get_text() == _expected_ui("fr", "(kein Bild)")
        assert not win._history.can_undo
        assert not win._has_unsaved_changes(), "Ausgangsstand gilt wieder als gespeichert"
        for k in range(1, len(fps)):
            win._do_redo(); assert _fp(win) == fps[k], f"Redo {k}"
        assert win._r33.get_active() and _rgba(win._color_btn) == (1, 0, 0, 1)
        assert win._has_unsaved_changes()

        # 4. Laufende Geste beim Wechsel wird ein Eintrag (in der neuen Sprache)
        win._scale_slider.set_value(1.4)
        _switch(win, "en")
        assert win._history.undo_label == _expected_ui("en", "Zoom") + ": " + \
            _expected_ui("en", "Hintergrund")
        assert win._scale_slider.get_value() == 1.4
        win._do_undo()
        assert win._state.bg_img_scale == 1.0 and win._scale_slider.get_value() == 1.0
        pump(700)
        assert win._history.redo_label.startswith(_expected_ui("en", "Zoom")), "verspätet"

        # 5. Gespeicherter Stand bleibt gespeichert
        win._on_save_dialog_done(FakeSaveDialog(WORK / "s.discprint"), None)
        assert not win._has_unsaved_changes()
        _switch(win, "de")
        assert not win._has_unsaved_changes()
        assert win._r33.get_active()
        win._r50.set_active(True)                       # Änderung danach erkannt
        assert win._has_unsaved_changes()

    assert spy.calls == [], f"Rückfrage beim Sprachwechsel: {spy.calls}"


# ── Undo-Audit: jede Designaktion genau ein Eintrag, Undo/Redo exakt ─────────

class FakeTextDialog:
    def __init__(self, text):
        self.result = {"text": text, "font_family": "Sans", "font_size_pt": 18.0,
                       "bold": True, "italic": False, "color": (0.2, 0.3, 0.4, 1.0)}


def scenario_undo_audit(win):
    import random
    rnd = random.Random(1)
    fp = win._current_fingerprint
    c = win._canvas
    failures = []

    def img():
        return win._state.images[-1]

    def row_of(i):
        return win._find_img_row(i)

    def text():
        return win._state.elements[-1]

    def check(name, action, gesture=False):
        fp0, n0 = fp(), len(win._history._undo)
        action()
        if gesture:
            pump(700)                               # Geste abschließen (600 ms)
        fp1, n1 = fp(), len(win._history._undo)
        if fp1 == fp0:
            failures.append(f"{name}: keine Änderung"); return
        if n1 != n0 + 1:
            failures.append(f"{name}: {n1 - n0} Undo-Einträge statt 1"); return
        win._do_undo()
        if fp() != fp0:
            failures.append(f"{name}: Undo stellt den Zustand nicht exakt her"); return
        win._do_redo()
        if fp() != fp1:
            failures.append(f"{name}: Redo stellt den Zustand nicht exakt her")

    def color():
        r = Gdk.RGBA(); r.red, r.green, r.blue, r.alpha = rnd.random(), 0.5, 0.5, 1
        win._color_btn.set_rgba(r)

    def drag(target, start, apply):
        if target == "bg":
            c._drag_target = "bg"
            c._drag_start_bg_x, c._drag_start_bg_y = start
        else:
            c._drag_target, c._drag_handle, c._drag_start = target, -1, dict(start)
        apply()
        c._on_drag_end(None, 1, 1)

    def scroll(n):
        for _ in range(n):
            c._on_scroll(None, 0, -1)

    def bgdrag():
        st = win._state
        start = (st.bg_img_x_mm, st.bg_img_y_mm)
        drag("bg", start, lambda: (setattr(st, "bg_img_x_mm", start[0] + 4),
                                   setattr(st, "bg_img_y_mm", start[1] - 2)))

    def imgdrag():
        # Startzustand so, wie der Canvas ihn beim Ziehen am Bildkörper ablegt
        i = img()
        # Drag-Beginn über den echten Canvas-Code: Bild an seiner Mitte treffen
        with mock.patch.object(c, "_hit_any", return_value=i), \
             mock.patch.object(c, "_hit_handle_idx", return_value=-1):
            c._on_drag_begin(mock.Mock(), 0, 0)
        assert c._drag_target is i and c._drag_handle == -1, "Drag-Beginn traf nicht"
        i.x += 3
        c._on_drag_end(None, 1, 1)

    def txtdrag():
        t = text()
        drag(t, {"x": t.x_mm, "y": t.y_mm}, lambda: setattr(t, "y_mm", t.y_mm + 2))

    def select(i):
        c._select_image(i)

    actions = [
        ("Hub-Größe", lambda: (win._r33 if win._r50.get_active() else win._r50).set_active(True)),
        ("Hintergrundfarbe", color),
        ("Farbe zurücksetzen", lambda: win._on_reset_color(None)),
        ("Hintergrundbild laden", lambda: win._load_bg_image(png("bg.png"))),
        ("Hintergrund-Zoom (Regler)", lambda: [win._scale_slider.set_value(v) for v in (1.2, 1.4)]),
        ("Hintergrund-Zoom (Mausrad)", lambda: (select(None), scroll(3))),
        ("Hintergrund Pfeilknöpfe", lambda: [win._nudge(5, 0), win._nudge(0, 5)]),
        ("Hintergrund ziehen", bgdrag),
        ("Zentrieren", lambda: win._on_reset_transform(None)),
        ("Hintergrundbild entfernen", lambda: win._on_clear_image(None)),
        ("Bild hinzufügen", lambda: win._add_image_from_path(png("a.png"))),
        ("Opazität", lambda: row_of(img())[3].set_value(0.6)),
        ("Helligkeit", lambda: row_of(img())[5].set_value(1.3)),
        ("Kontrast", lambda: row_of(img())[7].set_value(0.7)),
        ("Helligkeit zurücksetzen", lambda: win._on_reset_brightness(img())),
        ("Kontrast zurücksetzen", lambda: win._on_reset_contrast(img())),
        ("Spiegeln H", lambda: (select(img()), win._on_flip(True))),
        ("Spiegeln V", lambda: (select(img()), win._on_flip(False))),
        ("Ebene", lambda: win._img_z_change(img(), +1)),
        ("Bild ziehen", imgdrag),
        ("Bild Mausrad-Zoom", lambda: (select(img()), scroll(3))),
        ("Bild duplizieren", lambda: win._duplicate_image(img())),
        ("Bild sichtbar", lambda: win._toggle_image_visible(img(), row_of(img())[1], w.Gtk.Button())),
        ("Bild sperren", lambda: win._toggle_image_locked(img(), w.Gtk.Button())),
        ("Bild löschen", lambda: win._delete_image(img(), row_of(img())[1])),
        ("Text hinzufügen", lambda: win._on_add_dialog_closed(FakeTextDialog("Hallo"))),
        ("Text bearbeiten", lambda: win._on_edit_dialog_closed(FakeTextDialog("Welt"), text())),
        ("Text ziehen", txtdrag),
        ("Text duplizieren", lambda: win._duplicate_element(text())),
        ("Text sichtbar", lambda: win._toggle_element_visible(
            text(), win._elem_list.get_row_at_index(0), w.Gtk.Button())),
        ("Text sperren", lambda: win._toggle_element_locked(text(), w.Gtk.Button())),
        ("Text löschen", lambda: win._delete_element(text(), win._elem_list.get_row_at_index(0))),
    ]
    gestures = {"Hintergrund-Zoom (Regler)", "Hintergrund-Zoom (Mausrad)",
                "Hintergrund Pfeilknöpfe", "Opazität", "Helligkeit", "Kontrast",
                "Bild Mausrad-Zoom"}
    for name, action in actions:
        try:
            check(name, action, name in gestures)
        except Exception as e:  # pragma: no cover - Diagnose
            failures.append(f"{name}: Ausnahme {type(e).__name__}: {e}")
    print(f"Audit: {len(actions)} Aktionen geprüft", flush=True)
    assert not failures, "\n".join(failures)

    # Alle Einträge nach einem Sprachwechsel: vorher angelegt, danach rückgängig
    n = len(win._history._undo)
    assert n >= len(actions) - 1, n                 # Verlauf hält max. 50
    ref = [fp()]
    for _i in range(n):
        win._do_undo(); ref.append(fp())
    for _i in range(n):
        win._do_redo()
    assert fp() == ref[0]
    i18n._LOCALE_DIR = _compile_locales(["en"])
    win._lang_dd.set_selected(i18n.available_languages().index("en"))
    pump(100)
    assert [x for x in win.get_application().get_windows()
            if isinstance(x, w.MainWindow)] == [win]
    check_lang(win, "Audit nach Wechsel")
    assert len(win._history._undo) == n and fp() == ref[0]

    def widgets_match_model():
        st = win._state
        c = win._color_btn.get_rgba()
        assert (c.red, c.green, c.blue, c.alpha) == pytest_approx(st.bg_color), "Farbknopf"
        assert win._scale_slider.get_value() == pytest_approx(st.bg_img_scale), "Zoom-Regler"
        assert win._r50.get_active() == (win._canvas.hub_mm == HUB_LARGE_MM), "Hub"
        for im in st.images:
            r = win._find_img_row(im)
            assert r is not None, "Bildzeile fehlt"
            assert abs(r[3].get_value() - im.opacity) < 1e-6, "Opazitätsregler"

    for k in range(1, n + 1):
        win._do_undo()
        assert fp() == ref[k], f"Undo {k} nach Sprachwechsel"
        widgets_match_model()
    for k in range(n - 1, -1, -1):
        win._do_redo()
        assert fp() == ref[k], f"Redo nach Sprachwechsel ({k})"
        widgets_match_model()
    print(f"Audit nach Sprachwechsel: {n} Einträge rückgängig/wiederhergestellt", flush=True)


def pytest_approx(v, tol=1e-3):
    """Kleiner Vergleich ohne pytest: Zahl oder Tupel mit Toleranz."""
    class _A:
        def __eq__(self, other):
            if isinstance(v, tuple):
                return len(other) == len(v) and all(abs(a - b) <= tol for a, b in zip(other, v))
            return abs(other - v) <= tol
    return _A()


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
