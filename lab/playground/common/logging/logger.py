import os
import sys
import logging
from json import dumps
from datetime import datetime, timezone
from typing import Optional, Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        result = {
            "@timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "system": "cpnginx-playground",
            "module": record.name,
            "message": record.getMessage(),
            "app": getattr(record, "app", {}),
        }

        # Add exception info if present
        if record.exc_info:
            result["exception"] = self.formatException(record.exc_info)

        return dumps(result, ensure_ascii=False, default=str)


def configure_logger(level: Optional[int] = None) -> None:
    # Determine log level
    if level is None:
        level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_str, logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(level)

    # Skip if already configured with our formatter
    if logger.handlers:
        # Check if any handler already has JsonFormatter
        for handler in logger.handlers:
            if isinstance(handler.formatter, JsonFormatter):
                return
        # If no JsonFormatter found, remove existing handlers
        logger.handlers.clear()

    # Create and configure handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)


class AppLogger:

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message with context."""
        self.logger.debug(message, extra={"app": kwargs})

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message with context."""
        self.logger.info(message, extra={"app": kwargs})

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message with context."""
        self.logger.warning(message, extra={"app": kwargs})

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message with context."""
        self.logger.error(message, extra={"app": kwargs})

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message with context."""
        self.logger.critical(message, extra={"app": kwargs})

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception message with traceback."""
        self.logger.exception(message, extra={"app": kwargs})
