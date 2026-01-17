"""Logging configuration."""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """Set up logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        format_string: Optional custom format string

    Returns:
        Root logger
    """
    # Default format
    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Convert level string to logging level
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter
    formatter = logging.Formatter(format_string)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(
            log_path,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_log_filename(prefix: str = "static_analysis") -> str:
    """Generate a timestamped log filename.

    Args:
        prefix: Prefix for the log filename

    Returns:
        Log filename with timestamp
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.log"


class ProgressLogger:
    """Helper class for logging progress."""

    def __init__(
        self,
        total: int,
        logger: Optional[logging.Logger] = None,
        log_interval: int = 10
    ):
        """Initialize progress logger.

        Args:
            total: Total number of items
            logger: Logger to use
            log_interval: Interval for progress updates
        """
        self.total = total
        self.current = 0
        self.logger = logger or logging.getLogger(__name__)
        self.log_interval = log_interval

    def update(self, message: Optional[str] = None) -> None:
        """Update progress.

        Args:
            message: Optional message to include
        """
        self.current += 1
        progress = self.current / self.total * 100

        if self.current % self.log_interval == 0 or self.current == self.total:
            msg = f"Progress: {self.current}/{self.total} ({progress:.1f}%)"
            if message:
                msg += f" - {message}"
            self.logger.info(msg)

    def complete(self, message: str = "Complete") -> None:
        """Mark progress as complete.

        Args:
            message: Completion message
        """
        self.logger.info(f"{message}: {self.total} items processed")
