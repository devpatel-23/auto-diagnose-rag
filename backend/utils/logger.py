"""
backend/utils/logger.py
------------------------
Centralised logging configuration using loguru.

WHY LOGURU INSTEAD OF PYTHON'S BUILT-IN LOGGING?
Python's `logging` module works but is verbose to configure and the output
is ugly by default. Loguru gives us:
  - Coloured, human-readable output in development
  - Structured JSON output in production (easier to parse in log aggregators)
  - Zero-config — just `from loguru import logger; logger.info("...")`
  - Automatic context (file name, line number, function)

USAGE THROUGHOUT THE APP:
    from backend.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Processing document: {}", filename)
    logger.error("Database connection failed: {}", error)
    logger.debug("Embedding dimensions: {}", len(vector))

Or just import directly from loguru anywhere:
    from loguru import logger
    logger.info("Hello")
"""

import sys
import json
from loguru import logger as _loguru_logger
from backend.config import settings

# ─────────────────────────────────────────────
# Configure loguru
# ─────────────────────────────────────────────

# Remove the default handler (plain text to stderr)
_loguru_logger.remove()

if settings.app_env == "production":
    # Production: JSON structured logs
    # JSON format is what cloud log aggregators (Datadog, Papertrail, Render Logs) expect.
    # Each log line is a parseable JSON object, making it easy to search/filter.
    def _json_sink(message):
        record = message.record
        log_entry = {
            "time": record["time"].isoformat(),
            "level": record["level"].name,
            "message": record["message"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
        }
        # Include exception info if present
        if record["exception"]:
            log_entry["exception"] = str(record["exception"])

        print(json.dumps(log_entry), file=sys.stdout, flush=True)

    _loguru_logger.add(
        _json_sink,
        level="INFO",
        format="{message}",  # The actual formatting is done inside _json_sink
        backtrace=False,     # Don't include full stack trace in JSON (too noisy)
        diagnose=False,
    )
else:
    # Development: beautiful coloured human-readable logs
    _loguru_logger.add(
        sys.stdout,
        level="DEBUG",
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,   # Show full traceback in dev
        diagnose=True,    # Show variable values in tracebacks
    )


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def get_logger(name: str):
    """
    Returns a logger bound to a specific module name.

    USAGE:
        # At the top of any file:
        logger = get_logger(__name__)

        # Then use it:
        logger.info("Starting ingestion for {}", filename)
        logger.warning("Low similarity score: {:.4f}", score)
        logger.error("Failed to connect: {}", error)

    The `name` appears in the log output so you can trace exactly
    which file/module produced each log line.

    Args:
        name: Usually __name__ (Python fills this in automatically)

    Returns:
        A loguru logger with the module name bound as context
    """
    return _loguru_logger.bind(module=name)
