"""
logger.py

Central logging configuration for the B2B RAG chatbot.

All modules import get_logger() from here to ensure consistent formatting
and that every log entry ends up in the same rotating log file.

Log file location: logs/app.log (relative to project root)
Rotation: 5 MB per file, 3 backups kept -> max ~20 MB on disk
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LOG_FILE = LOG_DIR / "app.log"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Module-level flag so setup runs only once even if get_logger() is called
# from multiple modules in the same process.
_configured = False


def _setup() -> None:
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — never grows unbounded.
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Console handler only for WARNING and above — keeps the terminal clean
    # during normal chat use while still surfacing unexpected problems.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    # Suppress verbose third-party loggers that would flood the log file.
    for noisy in ("httpx", "httpcore", "openai", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, initialising the logging system on first call."""
    _setup()
    return logging.getLogger(name)
