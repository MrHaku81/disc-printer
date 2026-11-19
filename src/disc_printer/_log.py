import logging
import sys
from datetime import datetime

from .constants import LOG_FILE


class _TimeFmt(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")


# log.error(..., extra=FILE_ONLY) writes only to the log file, not to the
# console; used when a message is already printed to the terminal in a
# different form.
FILE_ONLY = {"console": False}


def _console_filter(record: logging.LogRecord) -> bool:
    return getattr(record, "console", True)


def _setup() -> logging.Logger:
    logger = logging.getLogger("disc_printer")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = _TimeFmt("[%(asctime)s] [%(levelname)-7s] %(message)s")
    for h in (
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ):
        h.setFormatter(fmt)
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.addFilter(_console_filter)
        logger.addHandler(h)
    return logger


log = _setup()
