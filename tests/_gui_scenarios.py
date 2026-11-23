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
from disc_printer.constants import PRESET_FULL, PRESET_STANDARD
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
    return design_fingerprint(DesignState())


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


# ── Druckbereich: Bedienung über die echten Widgets ──────────────────────────

def preset(win, key):
    """Voreinstellungs-Knopf anklicken."""
    win._preset_btns[key].emit("clicked")


def slide(win, kind, *values):
    """Regler bewegen (value-changed wie beim Ziehen)."""
    for v in values:
        win._area_widgets[kind][0].set_value(v)


def type_in(win, kind, text):
    """Text ins Zahlenfeld tippen und Enter drücken."""
    entry = win._area_widgets[kind][1]
    entry.set_text(text)
    entry.emit("activate")


def area(win):
    return (win._state.inner_mm, win._state.outer_mm)


def highlighted(win):
    return [k for k, b in win._preset_btns.items() if b.get_active()]


def area_widgets(win):
    """Angezeigte Feldwerte (innen, außen)."""
    return tuple(win._area_widgets[k][1].get_text() for k in ("inner", "outer"))


def make_dirty(win) -> dict:
    """Alles ändern, was zum Design gehört; Regler-Timer laufen lassen."""
    win._on_detection_done([PRINTER])
    win._add_image_from_path(png("a.png"))
    win._load_bg_image(png("bg.png", (0, 0, 1)))
    elem = TextElement("Hallo", "Sans", 20, False, False, (0, 0, 0, 1))
    win._state.elements.append(elem)
    win._rebuild_panel()
    preset(win, "full")                             # Druckbereich (mit Undo-Eintrag)
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
    slide(win, "outer", 116)                       # Außen-Regler → Timer
    tids = (list(win._opacity_timer.values()) + list(win._brightness_timer.values())
            + list(win._contrast_timer.values()) + list(win._scroll_timer.values())
            + [win._bg_zoom_timer, win._bg_nudge_timer, win._area_timer["outer"]])
    assert all(tids) and len(tids) == 7, f"erwartet 7 laufende Timer: {tids}"
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
    assert design_fingerprint(s) == fresh_fp(), "Design nicht frisch"
    assert s.images == [] and s.elements == [] and s.bg_surface is None
    assert s.bg_path == "" and s.bg_color == (1.0, 1.0, 1.0, 1.0)
    assert (s.bg_img_x_mm, s.bg_img_y_mm, s.bg_img_scale) == (0.0, 0.0, 1.0)
    assert s.selected_image is None and s.selected_element is None
    rgba = win._color_btn.get_rgba()
    assert (rgba.red, rgba.green, rgba.blue, rgba.alpha) == (1, 1, 1, 1), "Farbknopf"
    assert area(win) == PRESET_STANDARD and highlighted(win) == ["standard"]
    assert area_widgets(win) == ("50,0", "118,0"), area_widgets(win)
    assert win._area_timer == {"outer": 0} or not any(win._area_timer.values())
    assert win._area_before == {}
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
    preset(win, "full")
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
    preset(win, "full")
    from disc_printer import file_format as fmt
    win._apply_loaded_design(fmt.load(WORK / "d.discprint"))
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
    win._apply_loaded_design(fmt.load(WORK / "x.discprint"))
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
    st.inner_mm = 33.0
    file_format.save(f, st)
    win._on_open_dialog_done(FakeOpenDialog(f), None)
    assert win._state.elements and win._state.elements[0].text == "x"
    check_lang(win, "Öffnen")

    # .mo fehlt: Oberfläche bleibt deutsch, Feld muss Deutsch zeigen
    i18n.switch_language("bg")
    assert i18n.effective_lang() == "de" and i18n._("Sprache:") == "Sprache:"
    i18n.switch_language(None)


# ── Sprachwechsel behält das Design (ein Fenster, keine Rückfrage) ──────────

def _fp(win):
    return design_fingerprint(win._state)


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
        preset(win, "full"); fps.append(_fp(win))
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
                ("Druckbereich", ("Vollflächig",)), ("Hintergrundfarbe", None),
                ("Opazität", name)]

        def expected(code):
            def tail(n):
                if isinstance(n, tuple):            # übersetzter Zusatz
                    n = _expected_ui(code, n[0])
                return f": {n}" if n else ""
            return [_expected_ui(code, m) + tail(n) for m, n in spec]

        assert labels(win) == expected("de"), labels(win)
        fp_before, clean_before = _fp(win), win._clean_fp
        selected_logs = len(log_lines("Printer selected"))

        _switch(win, "fr")
        # Design, Stand, Auswahl unverändert
        assert _fp(win) == fp_before and win._clean_fp == clean_before
        assert win._has_unsaved_changes()
        assert win._state.selected_image is img and win._flip_box.get_visible()
        # Widgets zeigen das Design
        assert highlighted(win) == ["full"] and area(win) == PRESET_FULL
        assert area_widgets(win) == ("33,0", "118,0"), area_widgets(win)
        assert win._preset_btns["full"].get_label() == _expected_ui("fr", "Vollflächig")
        assert _rgba(win._color_btn) == (1, 0, 0, 1)
        assert win._bg_file_label.get_text() == "bg.png"
        assert win._clear_img_btn.get_sensitive() and win._transform_box.get_sensitive()
        assert win._find_img_row(img)[3].get_value() == 0.4
        # Drucker: gleiche Auswahl, kein erneutes "Printer selected"
        assert win._selected is other and win._dropdown.get_selected() == 1
        assert win._dropdown.get_sensitive()
        # Druckbefehl-Anzeige mit übersetztem Platzhalter
        cmd = win._cups_info.get_text()
        assert cmd.startswith("lp -d Other") and cmd.endswith(
            "<" + _expected_ui("fr", "datei") + ">"), cmd
        assert _expected_ui("fr", "datei") == "fichier"
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
            if k == 3: assert highlighted(win) == ["standard"] and area(win) == PRESET_STANDARD
            if k == 2: assert win._bg_file_label.get_text() == _expected_ui("fr", "(kein Bild)")
        assert not win._history.can_undo
        assert not win._has_unsaved_changes(), "Ausgangsstand gilt wieder als gespeichert"
        for k in range(1, len(fps)):
            win._do_redo(); assert _fp(win) == fps[k], f"Redo {k}"
        assert highlighted(win) == ["full"] and _rgba(win._color_btn) == (1, 0, 0, 1)
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
        assert highlighted(win) == ["full"]
        preset(win, "standard")                         # Änderung danach erkannt
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
        ("Voreinstellung", lambda: preset(win, "standard" if highlighted(win) == ["full"]
                                          else "full")),
        ("Innen-Regler", lambda: slide(win, "inner", 40, 38.3, 36)),
        ("Außen-Regler", lambda: slide(win, "outer", 110, 105.5)),
        ("Innen-Feld", lambda: type_in(win, "inner", "41,7")),
        ("Außen-Feld", lambda: type_in(win, "outer", "119.2")),
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
    gestures = {"Innen-Regler", "Außen-Regler", "Hintergrund-Zoom (Regler)", "Hintergrund-Zoom (Mausrad)",
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
        for k in ("inner", "outer"):
            sl, entry, _u = win._area_widgets[k]
            v = getattr(st, f"{k}_mm")
            assert sl.get_value() == pytest_approx(v), f"Regler {k}"
            assert w.parse_number(entry.get_text(), win._unit) == pytest_approx(v, 0.06), \
                f"Feld {k}: {entry.get_text()!r} statt {v}"
        assert highlighted(win) == [k for k in ("standard", "full") if win._preset_matches(k)], \
            "Hervorhebung der Voreinstellungen"
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


# ── Druckbereich ─────────────────────────────────────────────────────────────

def _settings_unit():
    import json
    f = Path(os.environ["HOME"]) / ".config" / "disc-printer" / "settings.json"
    return json.loads(f.read_text()).get("unit") if f.exists() else None


def _saved_standard(win):
    """Datei mit frischem Design (Standard) anlegen, ohne das Fenster zu ändern."""
    from disc_printer import file_format as fmt
    p = WORK / "standard.discprint"
    fmt.save(p, DesignState())
    return p


def _hint(win):
    return win._area_hint.get_visible()


def scenario_print_area(win):
    import json
    import zipfile
    from disc_printer import file_format as fmt
    _ = i18n._
    U = lambda: len(win._history._undo)
    fp = win._current_fingerprint
    sensitive = lambda: all(b.get_sensitive() for b in win._preset_btns.values())

    # 1. Erster Start (ohne Einstellungsdatei): mm, Standard, kein Hinweis
    f = Path(os.environ["HOME"]) / ".config" / "disc-printer" / "settings.json"
    f.unlink(missing_ok=True)
    i18n.switch_language(None)                      # Deutsch: Dezimalkomma
    app = win.get_application()
    w.MainWindow(app).present(); win.close(); pump(50)
    win = _main_window(app)
    assert _settings_unit() is None
    assert win._unit == "mm" and win._unit_btns["mm"].get_active()
    assert not win._unit_btns["in"].get_active()
    assert area(win) == PRESET_STANDARD and highlighted(win) == ["standard"]
    assert area_widgets(win) == ("50,0", "118,0"), area_widgets(win)
    assert [win._area_widgets[k][2].get_text() for k in ("inner", "outer")] == ["mm", "mm"]
    assert not _hint(win) and sensitive()
    for k, lo, hi in (("inner", 18, 50), ("outer", 70, 120)):
        adj = win._area_widgets[k][0].get_adjustment()
        assert (adj.get_lower(), adj.get_upper()) == (lo, hi), k

    # 2. Voreinstellungen: ein Schritt je Klick, Hervorhebung nach Werten
    preset(win, "full")
    assert area(win) == PRESET_FULL and highlighted(win) == ["full"] and U() == 1
    assert area_widgets(win) == ("33,0", "118,0")
    assert win._history.undo_label == _("Druckbereich") + ": " + _("Vollflächig")
    preset(win, "full")                              # schon eingestellt
    assert U() == 1 and highlighted(win) == ["full"] and sensitive()
    win._do_undo()
    assert area(win) == PRESET_STANDARD and highlighted(win) == ["standard"]
    win._do_redo()
    assert area(win) == PRESET_FULL and highlighted(win) == ["full"]
    slide(win, "inner", 40); pump(700)
    assert highlighted(win) == [] and sensitive()
    slide(win, "inner", 50); pump(700)
    assert highlighted(win) == ["standard"], "Hand-Einstellung = Standard"
    type_in(win, "outer", "117,9")
    assert highlighted(win) == []
    type_in(win, "outer", "118")
    assert highlighted(win) == ["standard"]
    assert U() == 5, U()

    # 3. Regler: 0,5-mm-Raster, eine Geste = ein Schritt, Undo mitten in der Geste
    n = U()
    slide(win, "outer", 110.2, 108.3, 105.6)
    assert area(win)[1] == 105.5 and area_widgets(win)[1] == "105,5"
    assert win._area_widgets["outer"][0].get_value() == 105.5
    assert U() == n, "Eintrag vor Ende der Geste"
    pump(700)
    assert U() == n + 1 and win._history.undo_label == _("Außendurchmesser")
    win._do_undo()
    assert area(win)[1] == 118.0 and area_widgets(win)[1] == "118,0"
    assert win._area_widgets["outer"][0].get_value() == 118.0
    win._do_redo()
    assert area(win)[1] == 105.5
    slide(win, "inner", 30, 29)
    win._do_undo()                                  # Geste läuft noch
    assert area(win)[0] == 50.0 and win._area_widgets["inner"][0].get_value() == 50.0
    pump(700)
    assert win._history.redo_label == _("Innendurchmesser"), "Geste nach Undo erneut eingetragen"
    win._do_redo()
    assert area(win)[0] == 29.0
    # Geste, dann andere Aktion: Geste zuerst
    n = U()
    slide(win, "inner", 31)
    preset(win, "standard")
    assert [c.description for c in win._history._undo[n:]] == [
        _("Innendurchmesser"), _("Druckbereich") + ": " + _("Standard")]
    win._do_undo()
    assert area(win) == (31.0, 105.5)
    win._do_redo()

    # 4. Felder in mm: Komma/Punkt, Rundung, Begrenzung, ungültige Eingabe
    n = U()
    type_in(win, "inner", "22.5")
    assert area(win)[0] == 22.5 and area_widgets(win)[0] == "22,5" and U() == n + 1
    assert win._area_widgets["inner"][0].get_value() == 22.5
    type_in(win, "inner", "22,46")                  # = 22,5: kein Schritt
    assert U() == n + 1 and area_widgets(win)[0] == "22,5"
    type_in(win, "inner", "22,44")
    assert area(win)[0] == 22.4 and U() == n + 2
    assert win._area_widgets["inner"][0].get_value() == 22.4, "Feldwert nicht ins Raster"
    type_in(win, "outer", "200")
    assert area(win)[1] == 120.0 and area_widgets(win)[1] == "120,0"
    type_in(win, "inner", "5")
    assert area(win)[0] == 18.0
    n = U()
    for bad in ("abc", "", "1,2,3"):
        type_in(win, "outer", bad)
        assert area(win)[1] == 120.0 and area_widgets(win)[1] == "120,0", bad
    win._area_widgets["outer"][1].emit("activate")  # unverändert
    assert U() == n
    win._do_undo(); assert area(win)[0] == 22.4
    win._do_undo(); assert area(win)[1] == 118.0    # vor "200" (Standard)
    win._do_redo(); win._do_redo()

    # 5. Hinweis: außen über 118, innen unter 21
    for inner, outer, want in (("21", "118", False), ("21", "118,1", True),
                               ("20,9", "118", True), ("21", "70", False),
                               ("50", "118", False), ("18", "120", True)):
        type_in(win, "inner", inner); type_in(win, "outer", outer)
        assert _hint(win) == want, (inner, outer)
        assert sensitive()
    type_in(win, "inner", "21"); type_in(win, "outer", "118")

    # 6. Einheit: kein Undo, keine Änderung am Design, Regler bleiben stehen
    fp0, n, dirty0 = fp(), U(), win._has_unsaved_changes()
    win._unit_btns["in"].set_active(True)
    assert win._unit == "in" and _settings_unit() == "in"
    assert U() == n and fp() == fp0 and win._has_unsaved_changes() == dirty0
    assert area_widgets(win) == ("0,83", "4,65"), area_widgets(win)
    assert [win._area_widgets[k][2].get_text() for k in ("inner", "outer")] == ["in", "in"]
    assert [win._area_widgets[k][0].get_value() for k in ("inner", "outer")] == [21.0, 118.0]
    assert not win._unit_btns["mm"].get_active()
    win._area_widgets["outer"][1].emit("activate")  # unverändert, nicht 118,1
    assert area(win) == (21.0, 118.0) and U() == n
    type_in(win, "outer", "4,5")
    assert area(win)[1] == 114.3 and area_widgets(win)[1] == "4,50" and U() == n + 1
    type_in(win, "inner", '1.3"')
    assert area(win)[0] == 33.0 and area_widgets(win)[0] == "1,30"
    slide(win, "outer", 100.2); pump(700)
    assert area(win)[1] == 100.0 and area_widgets(win)[1] == "3,94"
    win._do_undo()
    assert area(win)[1] == 114.3 and area_widgets(win)[1] == "4,50"
    win._do_redo()
    win._unit_btns["mm"].set_active(True)
    assert win._unit == "mm" and _settings_unit() == "mm" and area_widgets(win) == ("33,0", "100,0")
    win._unit_btns["in"].set_active(True)
    w2 = w.MainWindow(app)
    assert w2._unit == "in" and w2._unit_btns["in"].get_active(), "Einheit nicht gespeichert"
    assert area_widgets(w2) == ("1,97", "4,65")
    w2.destroy()
    win._unit_btns["mm"].set_active(True)

    # 6b. Gleich angezeigt = gleich (Hinweis und Hervorhebung), beide Einheiten
    win._unit_btns["in"].set_active(True)
    n = U()
    type_in(win, "inner", "1,97"); type_in(win, "outer", "4,65")
    assert area(win) == PRESET_STANDARD, area(win)          # nicht 50,0/118,1
    assert area_widgets(win) == ("1,97", "4,65")
    assert highlighted(win) == ["standard"] and not _hint(win)
    type_in(win, "outer", "4,66")
    assert area(win)[1] == 118.4 and highlighted(win) == [] and _hint(win)
    type_in(win, "outer", "4,65"); type_in(win, "inner", "0,83")
    assert area(win) == (21.0, 118.0) and not _hint(win), area(win)   # Innenschwelle
    type_in(win, "inner", "0,82")
    assert area(win)[0] == 20.8 and _hint(win)
    type_in(win, "inner", "1,30")
    assert area(win) == PRESET_FULL and highlighted(win) == ["full"] and not _hint(win)
    win._unit_btns["mm"].set_active(True)                    # nach mm: dieselben Werte
    assert area_widgets(win) == ("33,0", "118,0") and highlighted(win) == ["full"]
    assert not _hint(win)
    # in mm feiner eingegeben, in Zoll gleich angezeigt
    type_in(win, "inner", "50"); type_in(win, "outer", "118,1")
    assert _hint(win) and highlighted(win) == []
    fp0 = fp()
    win._unit_btns["in"].set_active(True)
    assert area_widgets(win) == ("1,97", "4,65")
    assert not _hint(win) and highlighted(win) == ["standard"], "Zoll: 4,65 = Schwelle/Standard"
    assert fp() == fp0 and area(win) == (50.0, 118.1)
    win._unit_btns["mm"].set_active(True)
    assert _hint(win) and highlighted(win) == []
    type_in(win, "inner", "20,9")                            # Innenschwelle in mm
    assert _hint(win)
    win._unit_btns["in"].set_active(True)
    assert area_widgets(win)[0] == "0,82" and _hint(win)    # in Zoll ebenfalls darunter
    type_in(win, "inner", "1,97")
    m = U()
    preset(win, "standard")                                  # hervorgehoben, Werte leicht anders
    assert area(win) == PRESET_STANDARD and U() == m + 1
    preset(win, "standard")
    assert U() == m + 1
    win._unit_btns["mm"].set_active(True)
    type_in(win, "inner", "21"); type_in(win, "outer", "118")

    # 7. Laufende Reglergeste bei „Neues Design“/Öffnen: kein verspäteter Eintrag
    slide(win, "outer", 90)
    win._reset_design()
    assert area(win) == PRESET_STANDARD and highlighted(win) == ["standard"] and U() == 0
    pump(800)
    assert U() == 0 and area(win) == PRESET_STANDARD, "verspäteter Regler-Commit nach Neu"
    slide(win, "inner", 30)
    win._on_open_dialog_done(FakeOpenDialog(_saved_standard(win)), None)
    pump(800)
    assert U() == 0 and area(win) == PRESET_STANDARD, "verspäteter Regler-Commit nach Öffnen"

    # 8. Speichern/Laden neu und alt
    win._reset_design()
    type_in(win, "inner", "41,5"); type_in(win, "outer", "117")
    f = WORK / "new.discprint"
    win._on_save_dialog_done(FakeSaveDialog(f), None)
    d = json.loads(zipfile.ZipFile(f).read("design.json"))
    assert d["version"] == 2 and d["hub_size"] == 41.5 and d["outer_diameter"] == 117.0, d
    assert not win._has_unsaved_changes()
    win._reset_design()
    win._on_open_dialog_done(FakeOpenDialog(f), None)
    assert area(win) == (41.5, 117.0) and area_widgets(win) == ("41,5", "117,0")
    assert highlighted(win) == [] and not win._has_unsaved_changes() and U() == 0
    type_in(win, "outer", "116")
    assert win._has_unsaved_changes()
    win._do_undo()
    assert not win._has_unsaved_changes()

    def old_file(name, design):
        p = WORK / name
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("design.json", json.dumps(design))
        return p

    for hub, want in ((50, "standard"), (33, "full")):
        p = old_file(f"old{hub}.discprint", {"version": 2, "hub_size": hub,
                                             "background_color": "#ffffff", "elements": []})
        win._on_open_dialog_done(FakeOpenDialog(p), None)
        assert area(win) == (float(hub), 118.0), area(win)
        assert highlighted(win) == [want] and not win._has_unsaved_changes()
    p = old_file("v1.discprint", {"version": 1, "hub_size": 33})
    win._on_open_dialog_done(FakeOpenDialog(p), None)
    assert area(win) == PRESET_FULL
    p = old_file("odd.discprint", {"version": 2, "hub_size": 5, "outer_diameter": 300})
    win._on_open_dialog_done(FakeOpenDialog(p), None)
    assert area(win) == (18.0, 120.0) and _hint(win)

    # 9. Neue Elemente: Bildgröße nach Außendurchmesser, Text im Ring
    from disc_printer.constants import PRINT_PPM
    import math
    win._reset_design()
    for inner, outer in (("50", "118"), ("40", "100"), ("33", "78")):
        type_in(win, "inner", inner); type_in(win, "outer", outer)
        win._add_image_from_path(png("a.png"))
        im = win._state.images[-1]
        width_mm = im.surface.get_width() * im.scale_x / PRINT_PPM
        assert abs(width_mm - 0.6 * float(outer)) < 0.01, width_mm
        for _i in range(3):
            win._on_add_dialog_closed(FakeTextDialog("T"))
            t = win._state.elements[-1]
            r = math.hypot(t.x_mm, t.y_mm)
            assert float(inner) / 2 < r < float(outer) / 2, (inner, outer, r)
            assert abs(r - (float(inner) + float(outer)) / 4) < 0.1

    # 10. Druckbild über den echten Druckweg: Maske innen und außen
    import threading
    red = Gdk.RGBA(); red.red, red.green, red.blue, red.alpha = 1, 0, 0, 1
    win._reset_design()
    win._color_btn.set_rgba(red)
    win._on_detection_done([PRINTER])
    captured = []

    def fake_lp(cmd, **_kw):
        import shutil, subprocess
        dst = WORK / f"print{len(captured)}.png"
        shutil.copy(cmd[-1], dst)
        captured.append((cmd, dst))
        return subprocess.CompletedProcess(cmd, 0, "request id is X-1", "")

    def printed(inner, outer):
        type_in(win, "inner", inner); type_in(win, "outer", outer)
        n = len(captured)
        with mock.patch.object(w.subprocess, "run", fake_lp), \
             mock.patch.object(w.MainWindow, "_on_print_success", lambda *a: False):
            win._on_print_confirmed(FakeChoice(1), None)
            end = time.monotonic() + 20
            while len(captured) == n and time.monotonic() < end:
                pump(50)
        assert len(captured) == n + 1, "kein Druck"
        cmd, path = captured[-1]
        assert cmd[:3] == ["lp", "-d", PRINTER.name] and cmd[3:-1] == PRINTER.lp_options
        return cairo.ImageSurface.create_from_png(str(path))

    def pixel(surf, r_mm):
        import struct
        size = surf.get_width()
        x = round(size / 2 + r_mm * PRINT_PPM)
        y = size // 2
        surf.flush()
        b, g, r_, _a = surf.get_data()[y * surf.get_stride() + 4 * x:][:4]
        return (r_, g, b)

    WHITE, RED = (255, 255, 255), (255, 0, 0)
    for inner, outer in ((50, 118), (33, 118), (40, 100), (18, 120), (21, 78)):
        surf = printed(str(inner), str(outer))
        assert surf.get_width() == surf.get_height() == w.PRINT_PX, "Seitengröße"
        ri, ro = inner / 2, outer / 2
        for r_mm, want in ((0, WHITE), (ri - 0.5, WHITE), (ri + 0.5, RED),
                           ((ri + ro) / 2, RED), (ro - 0.5, RED)):
            assert pixel(surf, r_mm) == want, (inner, outer, r_mm, pixel(surf, r_mm))
        if ro + 0.5 < 60:
            assert pixel(surf, ro + 0.5) == WHITE, (inner, outer, "außen")
        assert pixel(surf, 59.9) == (WHITE if outer < 119.8 else RED), (inner, outer, 59.9)

    # 11. Vorschau verdeckt dieselben Bereiche
    type_in(win, "inner", "40"); type_in(win, "outer", "100")
    size = 456
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    win._canvas._draw(None, cairo.Context(surf), size, size)
    ppm = (size - 2 * win._canvas._PAD) / 120
    surf.flush()
    data, stride = surf.get_data(), surf.get_stride()

    def prev(r_mm):
        x = round(size / 2 + r_mm * ppm); y = size // 2
        b, g, r_, _a = data[y * stride + 4 * x:][:4]
        return (r_, g, b)
    for r_mm in (0.5, 10, 19):
        assert prev(r_mm) != RED and prev(r_mm)[0] < 240, ("Hub", r_mm, prev(r_mm))
    for r_mm in (21, 35, 49):
        assert prev(r_mm) == RED, ("Ring", r_mm, prev(r_mm))
    for r_mm in (51, 55, 59):
        assert prev(r_mm)[0] < 120, ("außen", r_mm, prev(r_mm))


def scenario_area_lang(win):
    """Dezimalzeichen und Einheit in Tooltips und Feldern, Sprachwechsel."""
    app = win.get_application()
    i18n._LOCALE_DIR = _compile_locales(["en", "fr"])
    i18n.switch_language(None)
    w.MainWindow(app).present(); win.close(); pump(50)
    win = _main_window(app)
    _KEYS["n"] = _key_ctrls(win)
    NB = " "

    def tips():
        return [b.get_tooltip_text() for b, _d in win._nudge_btns]

    def want_tips(code, length):
        return [_expected_ui(code, m) % {"length": length}
                for m in ("%(length)s links", "%(length)s rechts",
                          "%(length)s oben", "%(length)s unten")]

    def preset_tip(code, inner, outer):
        return _expected_ui(code, "Innen %(inner)s, außen %(outer)s") % {
            "inner": inner, "outer": outer}

    # Deutsch, mm und in
    assert tips() == want_tips("de", f"5{NB}mm") == [
        f"5{NB}mm links", f"5{NB}mm rechts", f"5{NB}mm oben", f"5{NB}mm unten"], tips()
    assert win._preset_btns["full"].get_tooltip_text() == \
        preset_tip("de", f"33{NB}mm", f"118{NB}mm")
    win._unit_btns["in"].set_active(True)
    assert tips() == want_tips("de", f"0,20{NB}in"), tips()
    assert tips()[0] == f"0,20{NB}in links"
    assert area_widgets(win) == ("1,97", "4,65")
    assert win._preset_btns["full"].get_tooltip_text() == \
        preset_tip("de", f"1,30{NB}in", f"4,65{NB}in")
    assert f"0,83{NB}in" in win._area_hint_lbl.get_text(), win._area_hint_lbl.get_text()

    # Werte ändern, Geste läuft beim Wechsel
    preset(win, "full")
    type_in(win, "outer", "4,6")                     # 116,8 mm
    slide(win, "inner", 30.5)
    fp0 = design_fingerprint(win._state)
    n = len(win._history._undo)

    # Englisch, in: Punkt, Werte und Einheit bleiben
    _switch(win, "en")
    assert win._unit == "in" and win._unit_btns["in"].get_active()
    assert area(win) == (30.5, 116.8) and design_fingerprint(win._state) == fp0
    assert len(win._history._undo) == n + 1, "laufende Geste nicht eingetragen"
    assert win._history.undo_label == _expected_ui("en", "Innendurchmesser")
    assert area_widgets(win) == ("1.20", "4.60"), area_widgets(win)
    assert [win._area_widgets[k][0].get_value() for k in ("inner", "outer")] == [30.5, 116.8]
    assert tips() == want_tips("en", f"0.20{NB}in") and tips()[0] == f"0.20{NB}in left", tips()
    assert win._preset_btns["standard"].get_label() == _expected_ui("en", "Standard")
    assert win._preset_btns["full"].get_label() == _expected_ui("en", "Vollflächig")
    assert highlighted(win) == []
    type_in(win, "outer", "4,66")                    # Komma auch auf Englisch
    assert area(win)[1] == 118.4
    type_in(win, "outer", "4.60")
    assert area(win)[1] == 116.8

    # Englisch, mm
    win._unit_btns["mm"].set_active(True)
    assert tips() == want_tips("en", f"5{NB}mm") and tips()[0] == f"5{NB}mm left", tips()
    assert area_widgets(win) == ("30.5", "116.8")
    assert win._preset_btns["full"].get_tooltip_text() == \
        preset_tip("en", f"33{NB}mm", f"118{NB}mm")

    # Undo nach dem Wechsel wirkt auf die neuen Widgets
    win._do_undo(); win._do_undo(); win._do_undo()
    assert area(win) == (33.0, 116.8) and area_widgets(win) == ("33.0", "116.8")
    win._do_undo(); win._do_undo()
    assert area(win) == PRESET_STANDARD and highlighted(win) == ["standard"]

    # Französisch: Komma
    _switch(win, "fr")
    assert area_widgets(win) == ("50,0", "118,0")
    _switch(win, "de")
    assert area_widgets(win) == ("50,0", "118,0") and win._unit == "mm"


# ── Menü: Nach neuer Version suchen, Über ────────────────────────────────────

def _menu_items(win):
    m = win._menu_btn.get_menu_model()
    return [(m.get_item_attribute_value(i, "label").get_string(),
             m.get_item_attribute_value(i, "action").get_string())
            for i in range(m.get_n_items())]


def _open_windows(cls):
    return [x for x in w.Gtk.Window.list_toplevels()
            if isinstance(x, cls) and x.get_visible()]


def _activate(win, action, cls):
    assert not _open_windows(cls)
    win.activate_action(action, None)
    pump(50)
    found = _open_windows(cls)
    assert len(found) == 1, f"{action}: {found}"
    dlg = found[0]
    assert dlg.get_modal() and dlg.get_transient_for() is win
    return dlg


def _close(dlg, cls):
    dlg.close_btn.emit("clicked")
    pump(50)
    assert not _open_windows(cls)


def _clipboard_text(widget):
    out = {}
    widget.get_clipboard().read_text_async(
        None, lambda cb, res: out.setdefault("t", cb.read_text_finish(res)))
    for _ in range(100):
        if "t" in out:
            break
        pump(10)
    return out.get("t")


def _menu_lang(win, code):
    exp = lambda m: _expected_ui(code, m)
    assert _menu_items(win) == [(exp("Nach neuer Version suchen"), "win.check-update"),
                                (exp("Über Disc Printer"), "win.about")], _menu_items(win)
    assert win._menu_btn.get_tooltip_text() == exp("Hauptmenü")
    # ganz rechts, direkt neben „Drucken“
    assert win._print_btn.get_parent() is win._menu_btn.get_parent()
    assert win._print_btn.get_next_sibling() is win._menu_btn
    # danach nur noch die Fensterknöpfe (Schließen usw.)
    nxt = win._menu_btn.get_next_sibling()
    assert nxt is None or (isinstance(nxt, w.Gtk.WindowControls)
                           and nxt.get_next_sibling() is None), nxt


def scenario_update_menu(win):
    from disc_printer.gui import about
    from disc_printer._version import __version__
    from disc_printer.constants import README_UPDATING_URL, RELEASES_URL, REPO_URL
    app = win.get_application()
    i18n._LOCALE_DIR = _compile_locales(["en", "ja"])
    i18n.switch_language(None)
    w.MainWindow(app).present(); win.close(); pump(50)
    win = _main_window(app)
    _KEYS["n"] = _key_ctrls(win)
    opened = []

    # Design mit Undo-Eintrag und ungespeicherter Änderung: bleibt unverändert
    win._add_image_from_path(png("u.png"))
    pump(50)
    fp0, n_undo = _fp(win), len(win._history._undo)
    assert win._has_unsaved_changes() and n_undo >= 1

    def unchanged(step):
        assert _fp(win) == fp0, f"{step}: Design geändert"
        assert len(win._history._undo) == n_undo, f"{step}: Undo-Eintrag"
        assert not win._history.can_redo, f"{step}: Redo-Stapel"
        assert win._has_unsaved_changes()

    with mock.patch.object(about, "open_uri", lambda parent, uri: opened.append((parent, uri))):
        _menu_lang(win, "de")

        # Quelltext-Start: weder Flatpak noch pacman
        dlg = _activate(win, "win.check-update", about.UpdateWindow)
        assert dlg.kind == "other" and dlg.commands == {}
        assert dlg.get_title() == "Nach neuer Version suchen"
        assert dlg.heading.get_text() == f"Installiert: Version {__version__}"
        assert dlg.readme_link.get_text() == "So aktualisierst du: siehe README"
        dlg.readme_link.emit("activate-link", README_UPDATING_URL)
        dlg.release_btn.emit("clicked")
        assert opened == [(win, README_UPDATING_URL), (win, RELEASES_URL)], opened
        _close(dlg, about.UpdateWindow)
        unchanged("Update-Fenster")

        # Flatpak und pacman: Befehl markierbar, Kopierknopf
        for kind, cmd, extra in (
                ("flatpak", "flatpak install --user ./disc-printer.flatpak",
                 "Datei herunterladen, dann im Terminal:"),
                ("pacman", "yay -Syu disc-printer",
                 "Aus dem AUR aktualisierst du im Terminal mit:")):
            dlg = about.UpdateWindow(win, kind=kind)
            dlg.present(); pump(50)
            texts = []
            child = dlg.box.get_first_child()
            while child is not None:
                if isinstance(child, w.Gtk.Label):
                    texts.append(child.get_text())
                child = child.get_next_sibling()
            assert extra in texts, (kind, texts)
            assert list(dlg.commands) == [cmd]
            assert dlg.commands[cmd].get_selectable()
            # Fokus auf „Schließen“, der Befehl steht nicht vorab markiert da
            assert dlg.get_focus() is dlg.close_btn, dlg.get_focus()
            assert dlg.commands[cmd].get_selection_bounds()[0] is False
            assert dlg.copy_buttons[cmd].get_tooltip_text() == "Befehl kopieren"
            btn = dlg.copy_buttons[cmd]
            assert btn.get_icon_name() == about.ICON_COPY
            btn.emit("clicked")
            assert _clipboard_text(dlg) == cmd, kind
            if kind == "flatpak":
                # Häkchen für etwa 1,5 s, dann wieder das Kopier-Symbol
                assert about.COPIED_MS == 1500
                assert btn.get_icon_name() == about.ICON_COPIED
                pump(800)
                btn.emit("clicked")                 # erneuter Klick: Zeit neu
                pump(1100)
                assert btn.get_icon_name() == about.ICON_COPIED, "zu früh zurück"
                pump(600)
                assert btn.get_icon_name() == about.ICON_COPY, btn.get_icon_name()
            else:
                # Schließen mit laufendem Häkchen: Zeitgeber wird entfernt
                assert btn.get_icon_name() == about.ICON_COPIED
            if kind == "pacman":
                assert "Mit jedem anderen AUR-Helfer geht es genauso." in texts
                assert dlg.readme_link.get_text() == "Andere Installationsarten: siehe README"
            else:
                assert not hasattr(dlg, "readme_link")
            _close(dlg, about.UpdateWindow)
        pump(1700)                                  # kein Zeitgeber feuert mehr
        unchanged("Befehle kopiert")

        # Testhilfe DISC_PRINTER_INSTALL_KIND bestimmt die Fassung des Fensters
        for value, want in (("pacman", "pacman"), ("flatpak", "flatpak"),
                            ("other", "other"), ("aur", "other")):
            with mock.patch.dict(os.environ, {"DISC_PRINTER_INSTALL_KIND": value}):
                dlg = _activate(win, "win.check-update", about.UpdateWindow)
                assert dlg.kind == want, (value, dlg.kind)
                _close(dlg, about.UpdateWindow)

        # Über
        dlg = _activate(win, "win.about", about.AboutWindow)
        assert dlg.get_title() == "Über Disc Printer"
        assert dlg.version_lbl.get_text() == f"Version {__version__}"
        assert dlg.license_lbl.get_text() == "Lizenz: MIT"
        assert dlg.name_lbl.get_text() == "Disc Printer"
        assert dlg.icon.get_icon_name() in ("de.haku.disc-printer", "media-optical")
        opened.clear()
        dlg.repo_link.emit("activate-link", REPO_URL)
        assert opened == [(win, REPO_URL)]
        _close(dlg, about.AboutWindow)
        unchanged("Über-Fenster")

        # Sprachwechsel: Menü und Fenster in der neuen Sprache, Aktionen einmal
        for code in ("en", "ja", "de"):
            _switch(win, code)
            _menu_lang(win, code)
            dlg = _activate(win, "win.check-update", about.UpdateWindow)
            assert dlg.heading.get_text() == \
                _expected_ui(code, "Installiert: Version %(version)s") % {"version": __version__}
            assert dlg.release_btn.get_label() == _expected_ui(code, "Release-Seite öffnen")
            _close(dlg, about.UpdateWindow)
            dlg = _activate(win, "win.about", about.AboutWindow)
            assert dlg.license_lbl.get_text() == _expected_ui(code, "Lizenz: MIT")
            _close(dlg, about.AboutWindow)
        assert sorted(a for a in win.list_actions() if a in ("check-update", "about")) == \
            ["about", "check-update"]
        assert _fp(win) == fp0 and win._has_unsaved_changes()


def scenario_update_escape(win):
    from disc_printer.gui import about
    for cls, action in ((about.UpdateWindow, "win.check-update"),
                        (about.AboutWindow, "win.about")):
        dlg = _activate(win, action, cls)
        dlg._on_key(None, w.Gdk.KEY_Escape, 0, 0)
        pump(50)
        assert not _open_windows(cls), cls
    assert not win._has_unsaved_changes() and not win._history.can_undo


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
