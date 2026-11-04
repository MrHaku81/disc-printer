"""
Hatch custom build hook: compile .po -> .mo before the wheel is packed.

Keeps translations out of git (they are generated artefacts) while ensuring
every install that goes through hatchling (pip install ., pip install -e .,
python -m build) ships a fully localised package.

Compilation strategy:
  1. GNU msgfmt --check if available on PATH
  2. built-in pure-Python compiler otherwise (no babel dependency)

Both paths skip fuzzy entries and support msgctxt and plural forms.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


DOMAIN = "disc_printer"


class CompileMoBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        locale_dir = root / "src" / DOMAIN / "locale"
        if not locale_dir.is_dir():
            return

        use_msgfmt = shutil.which("msgfmt") is not None
        tool = "msgfmt" if use_msgfmt else "built-in compiler"

        compiled = 0
        for po in sorted(locale_dir.glob(f"*/LC_MESSAGES/{DOMAIN}.po")):
            mo = po.with_suffix(".mo")
            if use_msgfmt:
                _compile_with_msgfmt(po, mo)
            else:
                _compile_pure_python(po, mo)
            compiled += 1

        self.app.display_info(
            f"disc-printer: compiled {compiled} .mo file(s) via {tool}"
        )


def _compile_with_msgfmt(po: Path, mo: Path) -> None:
    subprocess.run(
        ["msgfmt", "--check", str(po), "-o", str(mo)],
        check=True,
    )


# ── Pure-Python .po → .mo compiler ─────────────────────────────────────────────
# Format reference: https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html


def _compile_pure_python(po: Path, mo: Path) -> None:
    entries = _parse_po(po)
    _write_mo(mo, entries)


def _parse_po(path: Path) -> list[tuple[bytes, bytes]]:
    """
    Parse a .po file into [(msgid_bytes, msgstr_bytes), ...].

    - fuzzy entries are skipped
    - obsolete entries (``#~`` prefix) are skipped
    - msgctxt yields ``<ctxt>\\x04<msgid>``
    - plurals combine ``msgid\\x00msgid_plural`` and ``msgstr[0]\\x00msgstr[1]...``
    - the header entry (empty msgid) is always included
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    n = len(lines)
    entries: list[tuple[bytes, bytes]] = []

    i = 0
    while i < n:
        fuzzy = False
        msgctxt: str | None = None
        msgid = ""
        msgid_plural: str | None = None
        msgstrs: dict[int, str] = {}

        # Consume blank lines, comments, flag lines; detect fuzzy flag.
        while i < n:
            stripped = lines[i].strip()
            if stripped.startswith("#,"):
                flags = [f.strip() for f in stripped[2:].split(",")]
                if "fuzzy" in flags:
                    fuzzy = True
                i += 1
                continue
            if stripped.startswith("#") or stripped == "":
                i += 1
                continue
            break

        if i >= n:
            break

        # Optional msgctxt
        if lines[i].lstrip().startswith("msgctxt"):
            msgctxt, i = _read_string(lines, i, "msgctxt")

        # Required msgid
        if i < n and lines[i].lstrip().startswith("msgid"):
            msgid, i = _read_string(lines, i, "msgid")
        else:
            i += 1
            continue

        # Optional msgid_plural
        if i < n and lines[i].lstrip().startswith("msgid_plural"):
            msgid_plural, i = _read_string(lines, i, "msgid_plural")

        # One or more msgstr / msgstr[N]
        while i < n and lines[i].lstrip().startswith("msgstr"):
            head = lines[i].lstrip().split(None, 1)[0]
            if head == "msgstr":
                s, i = _read_string(lines, i, "msgstr")
                msgstrs[0] = s
            else:
                idx = int(head[head.index("[") + 1 : head.index("]")])
                s, i = _read_string(lines, i, head)
                msgstrs[idx] = s

        if fuzzy:
            continue

        # Skip entries with empty translation, except the header.
        if msgid != "" and all(v == "" for v in msgstrs.values()):
            continue

        msgid_b = msgid.encode("utf-8")
        if msgctxt is not None:
            msgid_b = msgctxt.encode("utf-8") + b"\x04" + msgid_b
        if msgid_plural is not None:
            msgid_b = msgid_b + b"\x00" + msgid_plural.encode("utf-8")

        if msgid_plural is not None:
            parts = [msgstrs[k].encode("utf-8") for k in sorted(msgstrs)]
            msgstr_b = b"\x00".join(parts)
        else:
            msgstr_b = msgstrs.get(0, "").encode("utf-8")

        entries.append((msgid_b, msgstr_b))

    return entries


def _read_string(lines: list[str], i: int, keyword: str) -> tuple[str, int]:
    """
    Read a possibly multi-line gettext string starting at ``lines[i]``.
    Returns (decoded_text, new_i).
    """
    first = lines[i].lstrip()
    rest = first[len(keyword):].lstrip()
    chunks: list[str] = [_unquote(rest)]
    i += 1
    while i < len(lines) and lines[i].lstrip().startswith('"'):
        chunks.append(_unquote(lines[i].lstrip()))
        i += 1
    return "".join(chunks), i


_ESCAPE_MAP = {
    "n": "\n", "t": "\t", "r": "\r",
    "a": "\a", "b": "\b", "f": "\f", "v": "\v",
    "\\": "\\", '"': '"', "'": "'", "?": "?", "0": "\0",
}


def _unquote(s: str) -> str:
    if not s.startswith('"'):
        raise ValueError(f"expected quoted string, got: {s!r}")
    out: list[str] = []
    i = 1
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append(_ESCAPE_MAP.get(s[i + 1], s[i + 1]))
            i += 2
            continue
        if c == '"':
            return "".join(out)
        out.append(c)
        i += 1
    raise ValueError(f"unterminated string: {s!r}")


def _write_mo(path: Path, entries: list[tuple[bytes, bytes]]) -> None:
    entries = sorted(entries, key=lambda e: e[0])
    n = len(entries)

    header_size = 7 * 4
    orig_table_offset = header_size
    trans_table_offset = header_size + n * 8
    keys_start = trans_table_offset + n * 8

    orig_offsets: list[tuple[int, int]] = []
    keys_data = bytearray()
    off = keys_start
    for msgid_b, _ in entries:
        orig_offsets.append((len(msgid_b), off))
        keys_data.extend(msgid_b)
        keys_data.append(0)
        off += len(msgid_b) + 1

    trans_start = keys_start + len(keys_data)
    trans_offsets: list[tuple[int, int]] = []
    vals_data = bytearray()
    off = trans_start
    for _, msgstr_b in entries:
        trans_offsets.append((len(msgstr_b), off))
        vals_data.extend(msgstr_b)
        vals_data.append(0)
        off += len(msgstr_b) + 1

    with path.open("wb") as f:
        f.write(struct.pack(
            "<Iiiiiii",
            0x950412DE, 0, n,
            orig_table_offset, trans_table_offset,
            0, 0,
        ))
        for length, offset in orig_offsets:
            f.write(struct.pack("<ii", length, offset))
        for length, offset in trans_offsets:
            f.write(struct.pack("<ii", length, offset))
        f.write(keys_data)
        f.write(vals_data)
