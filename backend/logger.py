"""
Structured logging for the IgniteAds backend.

Usage:
    from backend.logger import get_logger
    logger = get_logger(__name__)

    logger.info("Launch started", extra={"launch_id": launch_id, "user_id": uid})
"""

import logging
import json
import sys
import os


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for Cloud Run / GCP Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Merge any extra fields passed via extra={}
        for key in ("launch_id", "user_id", "platform", "step", "error",
                    "campaign_id", "ad_id", "credits"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        # Catch-all for other extras
        if hasattr(record, "data") and record.data:
            log_entry["data"] = record.data

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s:%(funcName)s:%(lineno)d — %(message)s"

    def __init__(self):
        super().__init__(fmt=self.FORMAT, datefmt="%H:%M:%S")


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger.

    In production (Cloud Run): JSON-structured logs for GCP Cloud Logging.
    In development (local): Human-readable logs.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if os.getenv("DEBUG") else logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)

    is_production = os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN")
    if is_production:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(HumanFormatter())

    logger.addHandler(handler)
    return logger
