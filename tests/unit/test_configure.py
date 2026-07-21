import logging
import os
from unittest.mock import patch

import pytest

from leviathan_common.infrastructure.runtime_logging.configure import (
    configure_runtime_logging,
    resolve_log_level,
)


def test_resolve_log_level_contract():
    assert resolve_log_level("info") == logging.INFO
    assert resolve_log_level("DEBUG") == logging.DEBUG
    with pytest.raises(TypeError, match="level_name must be a string"):
        resolve_log_level(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="log level must be one of"):
        resolve_log_level("verbose")


def test_configure_runtime_logging_includes_session_role_and_logger_name(tmp_path):
    with patch.dict(
        os.environ,
        {
            "LEVIATHAN_ROLE": "engine",
            "LEVIATHAN_SESSION_ID": "sess-beta-1",
            "LEVIATHAN_RESTART_GENERATION": "2",
        },
        clear=False,
    ):
        configure_runtime_logging(
            logging.DEBUG,
            display_mode="zones",
            log_dir=str(tmp_path),
            log_to_console=False,
            session_id="sess-beta-1",
        )

    logging.getLogger("leviathan.test").info("configured")
    log_files = list(tmp_path.glob("leviathan_*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "[session=sess-beta-1 gen=2" in content
    assert "[engine]" in content
    assert "leviathan.test" in content


def test_configure_runtime_logging_complete_mode_with_file_and_console(tmp_path, capsys):
    configure_runtime_logging(
        logging.INFO,
        display_mode="complete",
        log_dir=str(tmp_path),
        log_to_file=True,
        log_to_console=True,
        session_id="sess-complete",
    )
    logging.getLogger("leviathan.test.complete").warning("dual-sink")
    captured = capsys.readouterr()
    assert "dual-sink" in captured.out
    assert list(tmp_path.glob("leviathan_*.log"))


def test_configure_runtime_logging_suppresses_noisy_third_party_loggers(tmp_path):
    configure_runtime_logging(
        logging.DEBUG,
        display_mode="zones",
        log_dir=str(tmp_path),
        log_to_console=False,
    )
    assert logging.getLogger("websockets").level == logging.WARNING
    assert logging.getLogger("asyncio").level == logging.WARNING
    assert logging.getLogger("aiohttp").level == logging.WARNING


def test_configure_runtime_logging_complete_mode_uses_console_only(capsys):
    configure_runtime_logging(
        logging.INFO,
        display_mode="complete",
        log_to_console=True,
        session_id="sess-standalone",
    )
    logging.getLogger("leviathan.test.console").warning("console-only")
    captured = capsys.readouterr()
    assert "console-only" in captured.out
    assert "[standalone]" in captured.out


def test_configure_runtime_logging_rejects_invalid_display_mode():
    with pytest.raises(ValueError, match="display_mode must be one of"):
        configure_runtime_logging(logging.INFO, display_mode="invalid")


def test_configure_runtime_logging_rejects_invalid_log_level_value():
    with pytest.raises(ValueError, match="log_level must be one of"):
        configure_runtime_logging(42, display_mode="complete")


def test_configure_runtime_logging_rejects_bool_log_level():
    with pytest.raises(TypeError, match="log_level must be an integer"):
        configure_runtime_logging(True, display_mode="complete")  # type: ignore[arg-type]


def test_configure_runtime_logging_rejects_non_boolean_sink_flags():
    with pytest.raises(TypeError, match="log_to_file must be a boolean"):
        configure_runtime_logging(
            logging.INFO,
            display_mode="complete",
            log_to_file="yes",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="log_to_console must be a boolean"):
        configure_runtime_logging(
            logging.INFO,
            display_mode="complete",
            log_to_console=1,  # type: ignore[arg-type]
        )


def test_configure_runtime_logging_rejects_invalid_session_id_type():
    with pytest.raises(TypeError, match="session_id must be a string or None"):
        configure_runtime_logging(
            logging.INFO,
            display_mode="complete",
            session_id=99,  # type: ignore[arg-type]
        )


def test_configure_runtime_logging_null_handler_when_sinks_disabled(tmp_path):
    configure_runtime_logging(
        logging.INFO,
        display_mode="complete",
        log_dir=str(tmp_path),
        log_to_file=False,
        log_to_console=False,
        session_id="sess-null",
    )
    logging.getLogger("leviathan.test.null").error("swallowed")
    assert list(tmp_path.glob("leviathan_*.log")) == []


def test_configure_runtime_logging_rejects_non_string_display_mode():
    with pytest.raises(TypeError, match="display_mode must be a string"):
        configure_runtime_logging(logging.INFO, display_mode=123)  # type: ignore[arg-type]


def test_configure_runtime_logging_rejects_non_string_log_dir():
    with pytest.raises(ValueError, match="log_dir must be a non-empty string"):
        configure_runtime_logging(logging.INFO, display_mode="complete", log_dir=123)  # type: ignore[arg-type]


def test_configure_runtime_logging_rejects_bool_log_retention_days():
    with pytest.raises(TypeError, match="log_retention_days must be an integer or None"):
        configure_runtime_logging(
            logging.INFO,
            display_mode="complete",
            log_retention_days=True,  # type: ignore[arg-type]
        )


def test_configure_runtime_logging_rejects_invalid_role_type(tmp_path):
    with pytest.raises(TypeError, match="role must be a string or None"):
        configure_runtime_logging(
            logging.INFO,
            display_mode="zones",
            log_dir=str(tmp_path),
            log_to_console=False,
            role=99,  # type: ignore[arg-type]
        )
