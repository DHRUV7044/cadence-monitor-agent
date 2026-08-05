"""
Centralized logging configuration.

Usage:
    from logger import setup_logger

    logger = setup_logger(__name__)
    logger.info("Application started")
"""

from __future__ import annotations

import logging
from pathlib import Path

import settings


_LOGGER_INITIALIZED = False


def _initialize_logging() -> None:
    """Configure the root logger only once."""

    global _LOGGER_INITIALIZED

    if _LOGGER_INITIALIZED:
        return

    log_file = Path(settings.LOG_FILE)

    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    _LOGGER_INITIALIZED = True


def setup_logger(name: str) -> logging.Logger:
    """
    Return a configured logger.

    Parameters
    ----------
    name:
        Usually __name__.

    Returns
    -------
    logging.Logger
    """

    _initialize_logging()

    return logging.getLogger(name)