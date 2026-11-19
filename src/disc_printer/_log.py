import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable


class _TimeFmt(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")


# log.error(..., extra=FILE_ONLY) writes only to the log file, not to the
# console; used when a message is already printed to the terminal in a
# different form.
FILE_ONLY = {"console": False}


def _console_filter(record: logging.LogRecord) -> bool:
    return getattr(record, "console", True)


def _default_log_path() -> Path | None:
    from .paths import log_file
    return log_file()


class _LazyFileHandler(logging.Handler):
    """File handler that opens its file on the first record, not on import.

    The path comes from ``resolve`` (default: paths.log_file()); its folder is
    created if needed. ``None`` means file logging is off. If the file cannot
    be opened, this is reported once on stderr and the handler stays silent;
    the console log keeps working.
    """

    def __init__(self, resolve: Callable[[], Path | None] = _default_log_path):
        super().__init__()
        self._resolve = resolve
        self._file: logging.FileHandler | None = None
        self._disabled = False
        self.path: Path | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if self._disabled:
            return
        if self._file is None and not self._open():
            return
        self._file.emit(record)

    def _open(self) -> bool:
        self._disabled = True  # also guards against re-entry while opening
        try:
            path = self._resolve()
            if path is None:
                return False
            self.path = path
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(path, encoding="utf-8")
        except Exception as e:
            where = f" {self.path}" if self.path else ""
            print(f"disc-printer: cannot write log file{where} ({e}); "
                  f"continuing without a log file", file=sys.stderr)
            return False
        fh.setFormatter(self.formatter)
        self._file = fh
        self._disabled = False
        return True

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
        super().close()


def _setup() -> logging.Logger:
    logger = logging.getLogger("disc_printer")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = _TimeFmt("[%(asctime)s] [%(levelname)-7s] %(message)s")
    file_handler = _LazyFileHandler()
    console = logging.StreamHandler(sys.stdout)
    console.addFilter(_console_filter)
    for h in (file_handler, console):
        h.setFormatter(fmt)
        logger.addHandler(h)
    return logger


log = _setup()
