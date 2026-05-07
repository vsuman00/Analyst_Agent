"""
logger.py — Structured Pipeline Logger
----------------------------------------
Replaces all print() calls throughout the codebase.

Usage:
    from app.utils.logger import get_logger, log
    logger = get_logger(__name__)
    log(logger.info, "stage.complete", stage="FeatureExtraction", count=7)
    log(logger.error, "llm.failed", error=str(e), fallback="deterministic")

Note: Python's logging.Logger does not natively support keyword-args on
      logger.info("msg", key=val). We use a helper `log()` that serialises
      extra fields into the message string for maximum compatibility.
"""
from __future__ import annotations

import logging
import sys
import time
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Formatter — human-readable colored console output for development
# ---------------------------------------------------------------------------

class _DevFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color  = self.COLORS.get(record.levelname, "")
        ts     = self.formatTime(record, "%H:%M:%S")
        module = record.name.split(".")[-1].ljust(20)
        msg    = record.getMessage()
        line   = f"{color}[{ts}] {record.levelname:<8}{self.RESET} {module} {msg}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


# ---------------------------------------------------------------------------
# Singleton root configuration
# ---------------------------------------------------------------------------

_configured = False


def _configure_root(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_DevFormatter())
    root = logging.getLogger("app")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
    _configured = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the 'app' hierarchy."""
    _configure_root()
    return logging.getLogger(name if name.startswith("app.") else f"app.{name}")


def log(
    method: Callable,
    event: str,
    **fields: Any,
) -> None:
    """
    Structured log call compatible with standard Python logging.

    Example:
        log(logger.info, "phase.complete", features=7, duration_ms=1200)
        # Outputs: [10:30:01] INFO     runner               phase.complete  features=7  duration_ms=1200
    """
    extras = "  ".join(f"{k}={v}" for k, v in fields.items())
    msg    = f"{event}  {extras}" if extras else event
    method(msg)


class StageTimer:
    """Context manager that logs stage start and duration on exit."""

    def __init__(self, logger: logging.Logger, stage: str):
        self._log   = logger
        self._stage = stage
        self._start = 0.0

    def __enter__(self) -> "StageTimer":
        self._start = time.perf_counter()
        log(self._log.info, "stage.start", stage=self._stage)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        ms = round((time.perf_counter() - self._start) * 1000, 1)
        if exc_type:
            log(self._log.error, "stage.failed",
                stage=self._stage, duration_ms=ms, error=str(exc_val))
        else:
            log(self._log.info, "stage.complete", stage=self._stage, duration_ms=ms)
        return False  # never suppress exceptions
