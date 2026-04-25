from __future__ import annotations

from typing import Callable


class Command:
    """Eine atomare, rückgängig machbare Aktion."""

    __slots__ = ("description", "_undo_fn", "_redo_fn")

    def __init__(self, description: str,
                 undo_fn: Callable[[], None],
                 redo_fn: Callable[[], None]) -> None:
        self.description = description
        self._undo_fn    = undo_fn
        self._redo_fn    = redo_fn

    def undo(self) -> None:
        self._undo_fn()

    def redo(self) -> None:
        self._redo_fn()


class History:
    """Undo/Redo-Stack (max. 50 Einträge)."""

    _MAX = 50

    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self.on_change: Callable[[], None] | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def push(self, cmd: Command) -> None:
        """Führt einen Command aus (ist bereits ausgeführt) und merkt ihn für Undo."""
        self._undo.append(cmd)
        if len(self._undo) > self._MAX:
            del self._undo[0]
        self._redo.clear()
        self._fire()

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self._fire()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.redo()
        self._undo.append(cmd)
        self._fire()
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._fire()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].description if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].description if self._redo else ""

    def _fire(self) -> None:
        if self.on_change:
            self.on_change()
