"""Structured JSON logging for production (Cloud Run, GCP, etc.).

When PS_LOG_FORMAT=json, all log output is JSON-lines — one object per line,
compatible with Cloud Logging, Datadog, and most log aggregators.

When PS_LOG_FORMAT=text (default), standard human-readable format is used.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line.

    Follows the structured logging convention expected by GCP Cloud Logging:
    - `severity` (not `levelname`) so Cloud Logging picks up the level
    - `message` for the log message
    - `timestamp` in RFC-3339
    - `logger` for the logger name
    - extra fields are merged at top level
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge any extra fields that were passed via `extra={…}` kwarg
        for key in ("request_id", "user_id", "method", "path", "status_code",
                     "duration_ms", "ip", "machine_id", "doc_id", "error_type"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        # Include exception info if present
        if record.exc_info and record.exc_info[2]:
            payload["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Exception",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                "stacktrace": "".join(traceback.format_exception(*record.exc_info)),
            }

        return json.dumps(payload, default=str, ensure_ascii=False)


def setup_logging(log_format: str = "text", level: str = "INFO") -> None:
    """Configure root logging based on the desired format.

    Args:
        log_format: "json" for structured JSON lines, "text" for human-readable.
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers (avoid duplicates on reload)
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if log_format.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
        ))

    root.addHandler(handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
