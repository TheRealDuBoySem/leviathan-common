"""Process identity and log-record context for Leviathan runtime logging."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

_SESSION_ENV = "LEVIATHAN_SESSION_ID"
_RESTART_GENERATION_ENV = "LEVIATHAN_RESTART_GENERATION"
_ROLE_ENV = "LEVIATHAN_ROLE"


class RuntimeContextFilter(logging.Filter):
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


def resolve_role(explicit_role: Optional[str] = None) -> str:
    """
    Resolve the process role for log context.

    Preference order: non-empty explicit_role, then LEVIATHAN_ROLE, else 'standalone'.
    """
    if explicit_role is not None:
        if not isinstance(explicit_role, str):
            raise TypeError("role must be a string or None")
        if explicit_role.strip():
            return explicit_role.strip()
    env_role = os.environ.get(_ROLE_ENV, "").strip()
    if env_role:
        return env_role
    return "standalone"
