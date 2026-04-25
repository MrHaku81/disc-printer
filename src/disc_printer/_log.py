import logging
import sys
from datetime import datetime

from .constants import LOG_FILE


class _TimeFmt(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")


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
        logger.addHandler(h)
    return logger


log = _setup()
