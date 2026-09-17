"""TidalTwin - Central logging configuration (Phase 9).

One place to configure logging so important backend failures are diagnosable
without ever writing secrets or credentials to the logs.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger once, with a concise, timestamped format."""
    root = logging.getLogger()
    if root.handlers:
        # Already configured (e.g. uvicorn) - only adjust the level.
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
    # Tame noisy third-party loggers we do not need for debugging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
