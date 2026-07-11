"""Centralized runtime logging configuration for Leviathan."""

from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, TextIO

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_VALID_LOG_LEVEL_VALUES = frozenset(
    getattr(logging, name) for name in _VALID_LOG_LEVELS
)
_DEFAULT_LOG_DIR = "logs"
_LOG_FILENAME_PREFIX = "leviathan"
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
_SESSION_ENV = "LEVIATHAN_SESSION_ID"
_RESTART_GENERATION_ENV = "LEVIATHAN_RESTART_GENERATION"
_ROLE_ENV = "LEVIATHAN_ROLE"


class _RuntimeContextFilter(logging.Filter):
    """Inject role, session, and restart generation into every log record."""

    def __init__(
        self,
        role: str,
        session_id: str,
        restart_generation: str,
    ) -> None:
        super().__init__()
        self.__role = role
        self.__session_id = session_id
        self.__restart_generation = restart_generation

    def filter(self, record: logging.LogRecord) -> bool:
        record.role = self.__role  # type: ignore[attr-defined]
        record.session_id = self.__session_id  # type: ignore[attr-defined]
        record.restart_generation = self.__restart_generation  # type: ignore[attr-defined]
        return True


class HourlyCalendarFileHandler(logging.Handler):
    """
    Append-only file handler that rotates at each UTC calendar hour boundary.

    A process started at 15:26 UTC writes to leviathan_YYYY-MM-DD_15.log until 16:00 UTC,
    then opens leviathan_YYYY-MM-DD_16.log. Safe for multi-process append (no rename).
    """

    def __init__(
        self,
        log_dir: str,
        *,
        encoding: str = "utf-8",
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        super().__init__()
        if not isinstance(log_dir, str) or not log_dir.strip():
            raise ValueError("log_dir must be a non-empty string")
        if not isinstance(encoding, str) or not encoding.strip():
            raise ValueError("encoding must be a non-empty string")
        if now_provider is not None and not callable(now_provider):
            raise TypeError("now_provider must be callable or None")
        self.__log_dir = log_dir.strip()
        self.__encoding = encoding.strip()
        self.__now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.__current_hour_key: Optional[str] = None
        self.__stream: Optional[TextIO] = None

    @property
    def log_dir(self) -> str:
        return self.__log_dir

    def _hour_key(self, moment: datetime) -> str:
        utc = moment.astimezone(timezone.utc)
        return utc.strftime("%Y-%m-%d_%H")

    def _path_for_hour(self, hour_key: str) -> str:
        return os.path.join(self.__log_dir, f"{_LOG_FILENAME_PREFIX}_{hour_key}.log")

    def _ensure_stream_for_moment(self, moment: datetime) -> None:
        hour_key = self._hour_key(moment)
        if hour_key == self.__current_hour_key and self.__stream is not None:
            return
        if self.__stream is not None:
            self.__stream.close()
            self.__stream = None
        os.makedirs(self.__log_dir, exist_ok=True)
        path = self._path_for_hour(hour_key)
        self.__stream = open(path, mode="a", encoding=self.__encoding)
        self.__current_hour_key = hour_key

    def emit(self, record: logging.LogRecord) -> None:
        try:
            moment = self.__now_provider()
            self._ensure_stream_for_moment(moment)
            msg = self.format(record)
            stream = self.__stream
            if stream is None:
                raise RuntimeError("hourly log stream was not initialized")
            stream.write(msg + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self.__stream is not None:
            self.__stream.close()
            self.__stream = None
        self.__current_hour_key = None
        super().close()


def ensure_session_id(existing: Optional[str] = None) -> str:
    """
    Return a stable session identifier for the current supervised run.

    When existing is a non-empty string it is exported to LEVIATHAN_SESSION_ID;
    otherwise a pre-set environment value or a newly generated id is used.
    """
    if existing is not None:
        if not isinstance(existing, str):
            raise TypeError("existing must be a string or None")
        if existing.strip():
            session_id = existing.strip()
            os.environ[_SESSION_ENV] = session_id
            return session_id

    session_id = os.environ.get(_SESSION_ENV, "").strip()
    if not session_id:
        session_id = uuid.uuid4().hex[:12]
    os.environ[_SESSION_ENV] = session_id
    return session_id


def resolve_restart_generation() -> str:
    """Return restart generation from LEVIATHAN_RESTART_GENERATION (default 0)."""
    raw = os.environ.get(_RESTART_GENERATION_ENV, "0").strip()
    return raw if raw else "0"


def purge_old_hourly_logs(log_dir: str, max_age_days: Optional[int]) -> int:
    """
    Delete hourly log files older than max_age_days.

    Returns the number of deleted files. No-op when max_age_days is None or <= 0.
    """
    if not isinstance(log_dir, str) or not log_dir.strip():
        raise ValueError("log_dir must be a non-empty string")
    if max_age_days is None or max_age_days <= 0:
        return 0
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int):
        raise TypeError("max_age_days must be an integer or None")
    if not os.path.isdir(log_dir.strip()):
        return 0
    log_dir = log_dir.strip()

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    deleted = 0
    for entry in os.scandir(log_dir):
        if not entry.is_file():
            continue
        if not entry.name.startswith(f"{_LOG_FILENAME_PREFIX}_") or not entry.name.endswith(".log"):
            continue
        modified = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
        if modified < cutoff:
            os.remove(entry.path)
            deleted += 1
    return deleted


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


def _resolve_role(explicit_role: Optional[str]) -> str:
    if explicit_role is not None:
        if not isinstance(explicit_role, str):
            raise TypeError("role must be a string or None")
        if explicit_role.strip():
            return explicit_role.strip()
    env_role = os.environ.get(_ROLE_ENV, "").strip()
    if env_role:
        return env_role
    return "standalone"


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

    resolved_role = _resolve_role(role)
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
    context_filter = _RuntimeContextFilter(
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
