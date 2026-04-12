"""Logging configuration for Agent Geronimo."""
import logging
import sys
from pathlib import Path
from datetime import datetime

from rich.logging import RichHandler
from rich.console import Console

console = Console()


def setup_logging(log_level: str = "INFO", log_dir: str = None) -> logging.Logger:
    """Configure structured logging with Rich console output and file logging."""
    logger = logging.getLogger("geronimo")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Rich console handler
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
    )
    rich_handler.setLevel(logging.INFO)
    logger.addHandler(rich_handler)

    # File handler
    if log_dir:
        log_path = Path(log_dir).expanduser()
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_path / f"geronimo_{datetime.now():%Y%m%d_%H%M%S}.log"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
        logger.addHandler(file_handler)

    return logger
