"""Logging setup shared by the client, coordinator and worker.

Text lines look like ``2026-11-03T12:00:00Z INFO mulebox.worker message`` (UTC, second
precision); JSON lines carry ``ts``, ``level``, ``logger``, ``msg`` and, when present,
``exc``.

Choices where docs/interfaces.md is silent:

- Only the ``mulebox`` logger is configured, never the root logger, and it does not
  propagate, so libraries and test runners keep their own logging untouched.
- Output goes to stderr, or only to ``file`` (appended, UTF-8) when one is given.
- "Idempotent" means each call replaces the handler installed by the previous call, so
  repeated calls never duplicate lines; the newest call's settings win.
- An unknown level name raises :class:`ValueError`.
- :func:`get_logger` puts names outside the ``mulebox`` tree under ``mulebox.``, so
  ``get_logger(__name__)`` and ``get_logger("worker")`` both work.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

ROOT_LOGGER = "mulebox"
_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_HANDLER_MARK = "_mulebox_handler"


class _UTCFormatter(logging.Formatter):
    converter = time.gmtime

    def __init__(self) -> None:
        super().__init__(_TEXT_FORMAT, _DATE_FORMAT)


class _JSONFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, _DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, sort_keys=True)


def _parse_level(level: str) -> int:
    value = logging.getLevelNamesMapping().get(str(level).upper())
    if value is None:
        raise ValueError(f"unknown log level {level!r}")
    return value


def _make_handler(file: Path | None) -> logging.Handler:
    if file is None:
        return logging.StreamHandler(sys.stderr)
    return logging.FileHandler(file, mode="a", encoding="utf-8")


def _remove_own_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            logger.removeHandler(handler)
            handler.close()


def setup_logging(
    level: str = "INFO", *, json_lines: bool = False, file: Path | None = None
) -> None:
    """Configure the ``mulebox`` logger; safe to call more than once."""
    numeric_level = _parse_level(level)
    handler = _make_handler(file)
    handler.setFormatter(_JSONFormatter() if json_lines else _UTCFormatter())
    setattr(handler, _HANDLER_MARK, True)
    logger = logging.getLogger(ROOT_LOGGER)
    _remove_own_handlers(logger)
    logger.addHandler(handler)
    logger.setLevel(numeric_level)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger in the ``mulebox`` tree (``worker`` becomes ``mulebox.worker``)."""
    if not name:
        raise ValueError("logger name must not be empty")
    if name == ROOT_LOGGER or name.startswith(ROOT_LOGGER + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER}.{name}")
