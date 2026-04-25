from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR  = Path.home() / ".config" / "disc-printer"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"


def load() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(data: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
