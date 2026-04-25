"""
Gettext-Einrichtung für disc-printer.

Alle UI-Module importieren _ und ngettext ausschließlich von hier:

    from ..i18n import _, ngettext   # aus gui/-Subpackage
    from  .i18n import _, ngettext   # aus disc_printer/-Top-Level

_ und ngettext sind echte Wrapper-Funktionen (nicht gebundene Methoden),
damit switch_language() das aktive _t ersetzen kann, ohne dass importierte
Referenzen in anderen Modulen veralten.

Sprachauswahl-Priorität beim Start:
  1. ~/.config/disc-printer/settings.json  →  "language": "<code>"
  2. Systemumgebung: LANGUAGE > LC_ALL > LC_MESSAGES > LANG
  3. Fallback: NullTranslations (Originalstrings auf Deutsch)

Neue Sprache hinzufügen:
  1.  make pot
  2.  make init-po LANG=<code>
  3.  # .po übersetzen …
  4.  make compile-mo
  5.  Code in locale/LINGUAS eintragen
"""
from __future__ import annotations

import gettext
import os
from pathlib import Path

_DOMAIN     = "disc_printer"
_LOCALE_DIR = Path(__file__).parent / "locale"

# Native Bezeichnungen für die Sprachauswahl
LANG_NAMES: dict[str, str] = {
    "ar":    "العربية",
    "bg":    "Български",
    "cs":    "Čeština",
    "da":    "Dansk",
    "de":    "Deutsch",
    "el":    "Ελληνικά",
    "en":    "English",
    "es":    "Español",
    "fa":    "فارسی",
    "fi":    "Suomi",
    "fr":    "Français",
    "he":    "עברית",
    "hi":    "हिन्दी",
    "hr":    "Hrvatski",
    "hu":    "Magyar",
    "id":    "Indonesia",
    "it":    "Italiano",
    "ja":    "日本語",
    "ko":    "한국어",
    "nb":    "Norsk (bokmål)",
    "nl":    "Nederlands",
    "pl":    "Polski",
    "pt":    "Português",
    "ro":    "Română",
    "ru":    "Русский",
    "sk":    "Slovenčina",
    "sr":    "Српски",
    "sv":    "Svenska",
    "th":    "ภาษาไทย",
    "tr":    "Türkçe",
    "uk":    "Українська",
    "vi":    "Tiếng Việt",
    "zh_CN": "中文（简体）",
    "zh_TW": "中文（繁體）",
}

_t: gettext.NullTranslations = gettext.NullTranslations()
_current_lang: str | None    = None


# ── Öffentliche API ────────────────────────────────────────────────────────────

def _(msgid: str) -> str:
    return _t.gettext(msgid)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _t.ngettext(singular, plural, n)


def switch_language(lang: str | None) -> None:
    """Wechselt die aktive Übersetzung; None → Deutsch-Fallback."""
    global _t, _current_lang
    _current_lang = lang
    if lang:
        try:
            _t = gettext.translation(
                _DOMAIN, localedir=str(_LOCALE_DIR), languages=[lang]
            )
            return
        except FileNotFoundError:
            pass
    _t = gettext.NullTranslations()


def available_languages() -> list[str]:
    """Liest verfügbare Sprach-Codes aus locale/LINGUAS."""
    linguas = _LOCALE_DIR / "LINGUAS"
    langs: list[str] = []
    try:
        for line in linguas.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                langs.append(line)
    except OSError:
        pass
    return langs


def get_current_lang() -> str | None:
    """Gibt den aktiven Sprach-Code zurück (None = Deutsch-Fallback)."""
    return _current_lang


# ── Initialisierung beim Import ────────────────────────────────────────────────

def _detect_system_lang(available: list[str]) -> str | None:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        for part in val.split(":"):
            code = part.split("_")[0].split(".")[0]
            if code in available:
                return code
    return None


def _init() -> None:
    from . import settings
    s    = settings.load()
    lang = s.get("language")
    if not lang:
        lang = _detect_system_lang(available_languages())
    switch_language(lang)


_init()
