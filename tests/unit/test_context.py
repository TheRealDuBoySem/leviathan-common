import logging
import os
from unittest.mock import patch

import pytest

from leviathan_common.infrastructure.runtime_logging.context import (
    RuntimeContextFilter,
    ensure_session_id,
    resolve_restart_generation,
    resolve_role,
)


def test_ensure_session_id_uses_existing_value():
    with patch.dict(os.environ, {}, clear=True):
        session_id = ensure_session_id("sess-alpha")
        assert session_id == "sess-alpha"
        assert os.environ["LEVIATHAN_SESSION_ID"] == "sess-alpha"


def test_ensure_session_id_reuses_environment_when_existing_blank():
    with patch.dict(os.environ, {"LEVIATHAN_SESSION_ID": "sess-env"}, clear=True):
        session_id = ensure_session_id("   ")
        assert session_id == "sess-env"


def test_ensure_session_id_generates_when_missing():
    with patch.dict(os.environ, {}, clear=True):
        session_id = ensure_session_id()
        assert len(session_id) == 12
        assert os.environ["LEVIATHAN_SESSION_ID"] == session_id


def test_ensure_session_id_rejects_non_string_existing():
    with pytest.raises(TypeError, match="existing must be a string or None"):
        ensure_session_id(123)  # type: ignore[arg-type]


def test_resolve_restart_generation_defaults_to_zero():
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_restart_generation() == "0"


def test_resolve_restart_generation_reads_environment():
    with patch.dict(os.environ, {"LEVIATHAN_RESTART_GENERATION": "3"}, clear=False):
        assert resolve_restart_generation() == "3"


def test_resolve_role_prefers_explicit_value():
    with patch.dict(os.environ, {"LEVIATHAN_ROLE": "engine"}, clear=False):
        assert resolve_role("supervisor") == "supervisor"


def test_resolve_role_uses_environment_when_explicit_blank():
    with patch.dict(os.environ, {"LEVIATHAN_ROLE": "engine"}, clear=True):
        assert resolve_role("   ") == "engine"


def test_resolve_role_defaults_to_standalone():
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_role() == "standalone"


def test_resolve_role_rejects_non_string():
    with pytest.raises(TypeError, match="role must be a string or None"):
        resolve_role(99)  # type: ignore[arg-type]


def test_runtime_context_filter_injects_fields():
    record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
    filt = RuntimeContextFilter("engine", "sess-1", "2")
    assert filt.filter(record) is True
    assert record.role == "engine"  # type: ignore[attr-defined]
    assert record.session_id == "sess-1"  # type: ignore[attr-defined]
    assert record.restart_generation == "2"  # type: ignore[attr-defined]
