import logging
import os
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from leviathan_common.infrastructure.runtime_logging import (
    HourlyCalendarFileHandler,
    configure_runtime_logging,
    ensure_session_id,
    purge_old_hourly_logs,
    resolve_log_level,
    resolve_restart_generation,
)


def test_resolve_log_level_contract():
    assert resolve_log_level("info") == logging.INFO
    assert resolve_log_level("DEBUG") == logging.DEBUG
    with pytest.raises(TypeError, match="level_name must be a string"):
        resolve_log_level(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="log level must be one of"):
        resolve_log_level("verbose")


def test_hourly_handler_creates_file_with_utc_hour_key(tmp_path):
    fixed = datetime(2026, 7, 11, 15, 26, tzinfo=timezone.utc)
    handler = HourlyCalendarFileHandler(
        str(tmp_path),
        now_provider=lambda: fixed,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
    handler.emit(record)
    handler.close()

    expected = tmp_path / "leviathan_2026-07-11_15.log"
    assert expected.exists()
    assert expected.read_text(encoding="utf-8").strip() == "hello"


def test_hourly_handler_rotates_on_utc_hour_change(tmp_path):
    moments = [
        datetime(2026, 7, 11, 15, 59, tzinfo=timezone.utc),
        datetime(2026, 7, 11, 16, 0, tzinfo=timezone.utc),
    ]
    index = {"i": 0}

    def now_provider() -> datetime:
        moment = moments[index["i"]]
        index["i"] += 1
        return moment

    handler = HourlyCalendarFileHandler(str(tmp_path), now_provider=now_provider)
    handler.setFormatter(logging.Formatter("%(message)s"))

    handler.emit(logging.LogRecord("test", logging.INFO, "", 0, "before", (), None))
    handler.emit(logging.LogRecord("test", logging.INFO, "", 0, "after", (), None))
    handler.close()

    first = tmp_path / "leviathan_2026-07-11_15.log"
    second = tmp_path / "leviathan_2026-07-11_16.log"
    assert first.read_text(encoding="utf-8").strip() == "before"
    assert second.read_text(encoding="utf-8").strip() == "after"


def test_hourly_handler_partial_first_hour_uses_start_hour(tmp_path):
    fixed = datetime(2026, 7, 11, 15, 26, tzinfo=timezone.utc)
    handler = HourlyCalendarFileHandler(
        str(tmp_path),
        now_provider=lambda: fixed,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.LogRecord("test", logging.DEBUG, "", 0, "partial", (), None))
    handler.close()

    assert (tmp_path / "leviathan_2026-07-11_15.log").exists()


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


def test_purge_old_hourly_logs_deletes_stale_files(tmp_path):
    old_file = tmp_path / "leviathan_2020-01-01_00.log"
    old_file.write_text("stale", encoding="utf-8")
    stale_ts = time.time() - (40 * 86400)
    os.utime(old_file, (stale_ts, stale_ts))

    fresh_file = tmp_path / "leviathan_2026-07-11_15.log"
    fresh_file.write_text("fresh", encoding="utf-8")

    deleted = purge_old_hourly_logs(str(tmp_path), 30)
    assert deleted == 1
    assert not old_file.exists()
    assert fresh_file.exists()


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


def test_hourly_handler_rejects_invalid_log_dir():
    with pytest.raises(ValueError, match="log_dir must be a non-empty string"):
        HourlyCalendarFileHandler("")


def test_purge_old_hourly_logs_rejects_invalid_log_dir():
    with pytest.raises(ValueError, match="log_dir must be a non-empty string"):
        purge_old_hourly_logs("", 30)


def test_purge_old_hourly_logs_rejects_non_integer_max_age():
    with pytest.raises(TypeError, match="max_age_days must be an integer or None"):
        purge_old_hourly_logs("logs", True)  # type: ignore[arg-type]


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


def test_hourly_handler_rejects_invalid_encoding():
    with pytest.raises(ValueError, match="encoding must be a non-empty string"):
        HourlyCalendarFileHandler("logs", encoding="")


def test_hourly_handler_rejects_invalid_now_provider():
    with pytest.raises(TypeError, match="now_provider must be callable or None"):
        HourlyCalendarFileHandler("logs", now_provider=123)  # type: ignore[arg-type]


def test_hourly_handler_reuses_open_stream_for_same_hour(tmp_path):
    fixed = datetime(2026, 7, 11, 15, 26, tzinfo=timezone.utc)
    handler = HourlyCalendarFileHandler(
        str(tmp_path),
        now_provider=lambda: fixed,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord("test", logging.INFO, "", 0, "one", (), None)
    handler.emit(record)
    handler.emit(record)
    handler.close()
    assert (tmp_path / "leviathan_2026-07-11_15.log").read_text(encoding="utf-8").count("one") == 2


def test_hourly_handler_exposes_log_dir_property(tmp_path):
    handler = HourlyCalendarFileHandler(str(tmp_path))
    assert handler.log_dir == str(tmp_path)
    handler.close()


def test_hourly_handler_emit_raises_when_stream_uninitialized(tmp_path, mocker):
    handler = HourlyCalendarFileHandler(str(tmp_path))
    handler.setFormatter(logging.Formatter("%(message)s"))
    mocker.patch.object(handler, "_ensure_stream_for_moment")
    record = logging.LogRecord("test", logging.INFO, "", 0, "orphan", (), None)
    handler.emit(record)
    handler.close()


def test_hourly_handler_emit_handles_formatter_errors(tmp_path):
    handler = HourlyCalendarFileHandler(str(tmp_path))
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord("test", logging.INFO, "", 0, "ok", (), None)
    handler.format = lambda _record: (_ for _ in ()).throw(RuntimeError("format failed"))  # type: ignore[method-assign, assignment]
    handler.emit(record)
    handler.close()


def test_purge_old_hourly_logs_skips_missing_directory():
    assert purge_old_hourly_logs("missing-log-dir-9999", 30) == 0


def test_purge_old_hourly_logs_skips_non_matching_files(tmp_path):
    (tmp_path / "other.log").write_text("keep", encoding="utf-8")
    deleted = purge_old_hourly_logs(str(tmp_path), 30)
    assert deleted == 0
    assert (tmp_path / "other.log").exists()


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
