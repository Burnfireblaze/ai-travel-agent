from __future__ import annotations

import logging
from typing import Any, Mapping

from .logger import LogContext, get_logger, log_event


logger = get_logger(__name__)


def send_to_aura(*, payload: Mapping[str, Any], context: LogContext | None = None) -> None:
    """
    Placeholder sink for Aura integration.
    Replace this with an actual API call when Aura is ready.
    """
    log_event(
        logger,
        level=logging.INFO,
        message="Aura sink placeholder invoked",
        event="aura_sink",
        context=context,
        data={"payload": dict(payload)},
    )
