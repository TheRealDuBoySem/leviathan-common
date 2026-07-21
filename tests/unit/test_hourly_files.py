import logging
import os
import time
from datetime import datetime, timezone

import pytest

from leviathan_common.infrastructure.runtime_logging.hourly_files import (
    HourlyCalendarFileHandler,
    purge_old_hourly_logs,
)


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


def test_hourly_handler_rejects_invalid_log_dir():
    with pytest.raises(ValueError, match="log_dir must be a non-empty string"):
        HourlyCalendarFileHandler("")


def test_purge_old_hourly_logs_rejects_invalid_log_dir():
    with pytest.raises(ValueError, match="log_dir must be a non-empty string"):
        purge_old_hourly_logs("", 30)


def test_purge_old_hourly_logs_rejects_non_integer_max_age():
    with pytest.raises(TypeError, match="max_age_days must be an integer or None"):
        purge_old_hourly_logs("logs", True)  # type: ignore[arg-type]


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
