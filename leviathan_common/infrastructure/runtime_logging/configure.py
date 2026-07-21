"""Root logger configuration for Leviathan runtime processes."""

from __future__ import annotations

import logging
import sys
from typing import Optional

from leviathan_common.infrastructure.runtime_logging.context import (
    RuntimeContextFilter,
    ensure_session_id,
    resolve_restart_generation,
    resolve_role,
)
from leviathan_common.infrastructure.runtime_logging.hourly_files import (
    HourlyCalendarFileHandler,
    purge_old_hourly_logs,
)

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_VALID_LOG_LEVEL_VALUES = frozenset(
    getattr(logging, name) for name in _VALID_LOG_LEVELS
)
_DEFAULT_LOG_DIR = "logs"
_RUNTIME_LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] "
    "[session=%(session_id)s gen=%(restart_generation)s pid=%(process)d] "
    "[%(role)s] [%(name)s] %(message)s"
)
_NOISY_LOGGER_LEVELS = {
    "websockets": logging.WARNING,
    "asyncio": logging.WARNING,
    "aiohttp": logging.WARNING,
}


def resolve_log_level(level_name: str) -> int:
    """
    Resolve a logging level name to its numeric constant.

    Preconditions:
        level_name must be a non-empty string.
    Postconditions:
        Returns the logging module constant matching level_name (case-insensitive).
    Exceptions:
        TypeError: If level_name is not a string.
        ValueError: If level_name is empty or not a supported logging level.
    """
    if not isinstance(level_name, str):
        raise TypeError("level_name must be a string")
    normalized = level_name.strip().upper()
    if not normalized or normalized not in _VALID_LOG_LEVELS:
        supported = ", ".join(sorted(_VALID_LOG_LEVELS))
        raise ValueError(
            f"log level must be one of {supported}, got '{level_name}'"
        )
    return getattr(logging, normalized)


def _configure_noisy_loggers() -> None:
    for logger_name, level in _NOISY_LOGGER_LEVELS.items():
        logging.getLogger(logger_name).setLevel(level)


def configure_runtime_logging(
    log_level: int,
    *,
    display_mode: str = "complete",
    log_dir: str = _DEFAULT_LOG_DIR,
    log_to_file: bool = False,
    log_to_console: bool = True,
    log_retention_days: Optional[int] = None,
    role: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """
    Configure global logging for a Leviathan process.

    Preconditions:
        log_level must be a valid logging module level constant.
        display_mode must be 'complete' or 'zones'.
    Postconditions:
        Root logger handlers are replaced; file sink uses hourly UTC rotation when enabled.
    """
    if not isinstance(log_level, int) or isinstance(log_level, bool):
        raise TypeError("log_level must be an integer")
    if log_level not in _VALID_LOG_LEVEL_VALUES:
        supported = ", ".join(sorted(_VALID_LOG_LEVELS))
        raise ValueError(
            f"log_level must be one of {supported}, got {log_level}"
        )
    if not isinstance(display_mode, str):
        raise TypeError("display_mode must be a string")
    normalized_mode = display_mode.strip().lower()
    if normalized_mode not in {"complete", "zones"}:
        raise ValueError(
            f"display_mode must be one of complete, zones, got '{display_mode}'"
        )
    if not isinstance(log_dir, str) or not log_dir.strip():
        raise ValueError("log_dir must be a non-empty string")
    if not isinstance(log_to_file, bool):
        raise TypeError("log_to_file must be a boolean")
    if not isinstance(log_to_console, bool):
        raise TypeError("log_to_console must be a boolean")
    if log_retention_days is not None and (
        isinstance(log_retention_days, bool)
        or not isinstance(log_retention_days, int)
    ):
        raise TypeError("log_retention_days must be an integer or None")
    if session_id is not None and not isinstance(session_id, str):
        raise TypeError("session_id must be a string or None")

    resolved_role = resolve_role(role)
    resolved_session = ensure_session_id(session_id)
    restart_generation = resolve_restart_generation()
    write_to_file = log_to_file or normalized_mode == "zones"
    emit_console = log_to_console

    if write_to_file:
        purge_old_hourly_logs(log_dir.strip(), log_retention_days)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_RUNTIME_LOG_FORMAT)
    context_filter = RuntimeContextFilter(
        resolved_role,
        resolved_session,
        restart_generation,
    )

    handlers: list[logging.Handler] = []
    if write_to_file:
        file_handler = HourlyCalendarFileHandler(log_dir.strip())
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        handlers.append(file_handler)

    if emit_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(context_filter)
        handlers.append(console_handler)

    if not handlers:
        null_handler = logging.NullHandler()
        null_handler.addFilter(context_filter)
        handlers.append(null_handler)

    root.setLevel(log_level)
    for handler in handlers:
        root.addHandler(handler)

    _configure_noisy_loggers()
