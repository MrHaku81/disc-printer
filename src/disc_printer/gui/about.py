"""Fenster „Nach neuer Version suchen“ und „Über Disc Printer“.

Beide gehören nicht zum Design: kein Undo-Eintrag, keine ungespeicherte
Änderung. Das Programm geht dabei nicht selbst ins Internet; Links öffnet der
Browser des Systems (im Flatpak über das OpenURI-Portal, ohne Netzrecht).
"""
from __future__ import annotations

from gi.repository import Gdk, Gtk, GLib

from .._log import log
from .._version import __version__
from ..constants import APP_ID, README_UPDATING_URL, RELEASES_URL, REPO_URL
from ..i18n import _
from ..install_kind import install_kind

# Befehle werden nicht übersetzt
CMD_FLATPAK = "flatpak install --user ./disc-printer.flatpak"
CMD_AUR     = "yay -Syu disc-printer"


def open_uri(parent: Gtk.Window, uri: str) -> None:
    """Adresse im Browser des Systems öffnen."""
    log.info(f"Opening {uri}")

    def done(launcher, result):
        try:
            launcher.launch_finish(result)
        except GLib.Error as e:
            log.warning(f"Could not open {uri}: {e.message}")

    Gtk.UriLauncher(uri=uri).launch(parent, None, done)


def _link(parent: Gtk.Window, text: str, uri: str) -> Gtk.Label:
    lbl = Gtk.Label(xalign=0.0, wrap=True)
    lbl.set_markup(f'<a href="{GLib.markup_escape_text(uri)}">'
                   f'{GLib.markup_escape_text(text)}</a>')
    lbl.connect("activate-link", lambda _l, u: (open_uri(parent, u), True)[1])
    return lbl


class _SmallWindow(Gtk.Window):
    """Modal, Escape schließt; Inhalt in einer senkrechten Box."""

    def __init__(self, parent: Gtk.Window, title: str):
        super().__init__(modal=True, transient_for=parent, title=title,
                         resizable=False, default_width=440)
        self._parent = parent
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.box, f"set_margin_{side}")(18)
        self.set_child(self.box)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    def _on_key(self, _c, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def add_text(self, text: str, markup: bool = False) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0.0, wrap=True, max_width_chars=50)
        if markup:
            lbl.set_markup(text)
        else:
            lbl.set_text(text)
        self.box.append(lbl)
        return lbl

    def add_buttons(self, *buttons: Gtk.Button) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                      halign=Gtk.Align.END, margin_top=8)
        for b in buttons:
            row.append(b)
        self.box.append(row)
        # Fokus auf den letzten Knopf („Schließen“): sonst bekäme ein
        # markierbarer Befehl den Fokus und stünde beim Öffnen markiert da
        self.set_default_widget(buttons[-1])
        self.set_focus(buttons[-1])


class UpdateWindow(_SmallWindow):
    """Installierte Version und wie man aktualisiert. Fragt nirgends nach."""

    def __init__(self, parent: Gtk.Window, kind: str | None = None):
        super().__init__(parent, _("Nach neuer Version suchen"))
        self.kind = kind or install_kind()
        self.commands: dict[str, Gtk.Label] = {}     # Befehl -> Label (Tests)
        self.copy_buttons: dict[str, Gtk.Button] = {}

        version = _("Installiert: Version %(version)s") % {"version": __version__}
        self.heading = self.add_text(
            f"<b>{GLib.markup_escape_text(version)}</b>", markup=True)
        self.add_text(_("Auf der Release-Seite siehst du die neueste Version."))

        if self.kind == "flatpak":
            self.add_text(_("Datei herunterladen, dann im Terminal:"))
            self._add_command(CMD_FLATPAK)
        elif self.kind == "pacman":
            self.add_text(_("Aus dem AUR aktualisierst du im Terminal mit:"))
            self._add_command(CMD_AUR)
            self.add_text(_("Mit jedem anderen AUR-Helfer geht es genauso."))
            self.readme_link = _link(parent, _("Andere Installationsarten: siehe README"),
                                     README_UPDATING_URL)
            self.box.append(self.readme_link)
        else:
            self.readme_link = _link(parent, _("So aktualisierst du: siehe README"),
                                     README_UPDATING_URL)
            self.box.append(self.readme_link)

        self.release_btn = Gtk.Button(label=_("Release-Seite öffnen"))
        self.release_btn.connect("clicked", lambda _b: open_uri(parent, RELEASES_URL))
        self.close_btn = Gtk.Button(label=_("Schließen"))
        self.close_btn.connect("clicked", lambda _b: self.close())
        self.add_buttons(self.release_btn, self.close_btn)

    def _add_command(self, cmd: str) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label(label=cmd, xalign=0.0, selectable=True, hexpand=True)
        lbl.add_css_class("monospace")
        btn = Gtk.Button(icon_name="edit-copy-symbolic")
        btn.set_tooltip_text(_("Befehl kopieren"))
        btn.connect("clicked", lambda _b: self.get_clipboard().set(cmd))
        row.append(lbl)
        row.append(btn)
        self.box.append(row)
        self.commands[cmd] = lbl
        self.copy_buttons[cmd] = btn


class AboutWindow(_SmallWindow):
    """Name, Version, Symbol, Lizenz, Link zum Repository."""

    def __init__(self, parent: Gtk.Window):
        super().__init__(parent, _("Über Disc Printer"))
        self.box.set_halign(Gtk.Align.FILL)
        theme = Gtk.IconTheme.get_for_display(parent.get_display())
        # Beim Start aus dem Quelltext ist das Programmsymbol nicht installiert
        icon = APP_ID if theme.has_icon(APP_ID) else "media-optical"
        self.icon = Gtk.Image(icon_name=icon, pixel_size=96)
        self.box.append(self.icon)
        self.name_lbl = Gtk.Label()
        self.name_lbl.set_markup("<span size='x-large' weight='bold'>Disc Printer</span>")
        self.box.append(self.name_lbl)
        self.version_lbl = Gtk.Label(
            label=_("Version %(version)s") % {"version": __version__})
        self.box.append(self.version_lbl)
        self.license_lbl = Gtk.Label(label=_("Lizenz: MIT"))
        self.box.append(self.license_lbl)
        self.repo_link = _link(parent, REPO_URL.removeprefix("https://"), REPO_URL)
        self.repo_link.set_xalign(0.5)
        self.box.append(self.repo_link)
        self.close_btn = Gtk.Button(label=_("Schließen"))
        self.close_btn.connect("clicked", lambda _b: self.close())
        self.add_buttons(self.close_btn)
