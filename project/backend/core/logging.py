"""Structured logging configuration for the Agent system."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from core.config import settings


# ---------------------------------------------------------------------------
# JSON Formatter for Structured Logging
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Logger Setup
# ---------------------------------------------------------------------------

def setup_logging(log_level: str | None = None) -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR).
    """
    level = (log_level or settings.log_level).upper()

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel("WARNING")
    logging.getLogger("sqlalchemy.engine").setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Log Context Helper
# ---------------------------------------------------------------------------

class LogContext:
    """Context manager for adding structured data to log records."""

    def __init__(self, logger: logging.Logger, **kwargs: Any) -> None:
        self.logger = logger
        self.extra = kwargs
        self._original_extra: dict[str, Any] = {}

    def __enter__(self) -> LogContext:
        self._original_extra = getattr(self.logger, "_context_extra", {})
        current = dict(self._original_extra)
        current.update(self.extra)
        self.logger._context_extra = current  # type: ignore[attr-defined]
        return self

    def __exit__(self, *args: Any) -> None:
        self.logger._context_extra = self._original_extra  # type: ignore[attr-defined]

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra = dict(getattr(self.logger, "_context_extra", {}))
        extra.update(kwargs)
        record = self.logger.makeRecord(
            self.logger.name,
            level,
            "",
            0,
            msg,
            (),
            None,
        )
        record.extra = extra  # type: ignore[attr-defined]
        self.logger.handle(record)
