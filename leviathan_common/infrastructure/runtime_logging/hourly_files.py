"""Hourly UTC log file handler and retention for Leviathan."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, TextIO

_LOG_FILENAME_PREFIX = "leviathan"


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
