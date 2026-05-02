from __future__ import annotations

import logging
import os
import sys


def setup_logging(*, verbose: bool, quiet: bool) -> None:
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    if quiet:
        level = logging.WARNING

    env_level = os.environ.get("PIVO_LOG_LEVEL")
    if env_level:
        normalized = env_level.strip().upper()
        if normalized in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            level = getattr(logging, normalized)

    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

