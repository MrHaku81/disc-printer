from gi.repository import Gtk, Gdk, Pango

from ..i18n import _
from ..model import TextElement


class TextEditDialog(Gtk.Window):
    """Modales Fenster zum Hinzufügen/Bearbeiten eines TextElement.

    Nach dem Schließen: `self.result` (dict) oder None wenn abgebrochen.
    """

    def __init__(self, parent: Gtk.Window, elem: TextElement | None = None):
        super().__init__(
            modal=True,
            transient_for=parent,
            title=_("Text bearbeiten") if elem else _("Text hinzufügen"),
            default_width=440,
            resizable=False,
        )
        self.result: dict | None = None
        self._elem = elem

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_margin_top(18)
        outer.set_margin_bottom(14)
        outer.set_margin_start(20)
        outer.set_margin_end(20)
        self.set_child(outer)

        outer.append(self._field(_("Text:"), self._make_entry(elem)))

        font_dialog = Gtk.FontDialog(title=_("Schriftart wählen"))
        self._font_btn = Gtk.FontDialogButton(dialog=font_dialog)
        init_desc = (
            Pango.FontDescription.from_string(elem.font_desc_str)
            if elem else Pango.FontDescription.from_string("Sans 24")
        )
        self._font_btn.set_font_desc(init_desc)
        self._font_btn.set_hexpand(True)
        outer.append(self._field(_("Schrift:"), self._font_btn))

        color_dialog = Gtk.ColorDialog(with_alpha=True, title=_("Textfarbe"))
        self._color_btn = Gtk.ColorDialogButton(dialog=color_dialog)
        rgba = Gdk.RGBA()
        if elem:
            rgba.red, rgba.green, rgba.blue, rgba.alpha = elem.color
        else:
            rgba.red = rgba.green = rgba.blue = 0.0
            rgba.alpha = 1.0
        self._color_btn.set_rgba(rgba)
        outer.append(self._field(_("Farbe:"), self._color_btn))

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        btn_row.set_margin_top(4)

        cancel = Gtk.Button(label=_("Abbrechen"))
        cancel.connect("clicked", lambda _btn: self.close())
        btn_row.append(cancel)

        ok = Gtk.Button(label=_("OK"))
        ok.add_css_class("suggested-action")
        ok.connect("clicked", self._on_ok)
        btn_row.append(ok)
        outer.append(btn_row)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)

    def _make_entry(self, elem: TextElement | None) -> Gtk.Entry:
        self._entry = Gtk.Entry()
        self._entry.set_hexpand(True)
        self._entry.set_activates_default(True)
        if elem:
            self._entry.set_text(elem.text)
        self._entry.grab_focus()
        return self._entry

    @staticmethod
    def _field(label: str, widget: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(label=label, xalign=0.0, width_chars=9)
        row.append(lbl)
        row.append(widget)
        return row

    def _on_ok(self, _btn) -> None:
        text = self._entry.get_text().strip()
        if not text:
            return
        desc  = self._font_btn.get_font_desc()
        rgba  = self._color_btn.get_rgba()
        size  = desc.get_size() / Pango.SCALE if desc.get_size() > 0 else 24.0
        self.result = {
            "text":         text,
            "font_family":  desc.get_family() or "Sans",
            "font_size_pt": float(size),
            "bold":         (desc.get_weight() >= Pango.Weight.BOLD),
            "italic":       (desc.get_style() == Pango.Style.ITALIC),
            "color":        (rgba.red, rgba.green, rgba.blue, rgba.alpha),
        }
        self.close()

    def _on_key(self, ctrl, keyval, keycode, state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False
