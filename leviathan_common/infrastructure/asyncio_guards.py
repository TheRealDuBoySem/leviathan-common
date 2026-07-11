"""Asyncio resilience helpers for Leviathan runtime processes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from leviathan_common.infrastructure.task_guard import TaskFailurePolicy

_UNHANDLED_ASYNCIO_PREFIX = "Unhandled asyncio exception"


def install_unhandled_task_logger(
    loop: asyncio.AbstractEventLoop,
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Register a global asyncio exception handler that logs unhandled task failures.

    Preconditions:
        loop must be an asyncio.AbstractEventLoop instance.
        logger, when provided, must be a logging.Logger instance.

    Unhandled task exceptions are treated as TOLERANT at the asyncio layer: they are
    logged with ERROR and do not trigger orchestrator shutdown. Restart generation
    and session context come from the active runtime logging filters when configured.
    Component-specific BackgroundTaskGuard policies remain authoritative.
    """
    if not isinstance(loop, asyncio.AbstractEventLoop):
        raise TypeError("loop must be an asyncio.AbstractEventLoop instance")
    if logger is not None and not isinstance(logger, logging.Logger):
        raise TypeError("logger must be a logging.Logger instance")

    log = logger or logging.getLogger(__name__)

    def _handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        message = context.get("message")
        if not isinstance(message, str) or not message.strip():
            message = _UNHANDLED_ASYNCIO_PREFIX
        exception = context.get("exception")
        policy = TaskFailurePolicy.TOLERANT.value
        formatted = f"{_UNHANDLED_ASYNCIO_PREFIX} (policy={policy}): {message}"
        if exception is not None:
            log.error(formatted, exc_info=exception)
        else:
            log.error(formatted)

    loop.set_exception_handler(_handler)
