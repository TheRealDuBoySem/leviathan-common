import pytest
from leviathan_common.time.timeframe import align_timestamp, parse_timeframe


def test_parse_timeframe():
    """Verify that timeframe strings are parsed correctly into milliseconds."""
    assert parse_timeframe("500ms") == 500
    assert parse_timeframe("10s") == 10000
    assert parse_timeframe("2m") == 120000
    assert parse_timeframe("1h") == 3600000
    assert parse_timeframe("3000") == 3000
    assert parse_timeframe("  5m  ") == 300000


def test_parse_timeframe_invalid_inputs():
    """Verify that parse_timeframe raises appropriate errors on invalid inputs."""
    with pytest.raises(TypeError, match="timeframe must be a string"):
        parse_timeframe(123)

    with pytest.raises(ValueError, match="timeframe string cannot be empty"):
        parse_timeframe("   ")

    with pytest.raises(ValueError, match="Invalid timeframe format"):
        parse_timeframe("abc")

    with pytest.raises(ValueError, match="timeframe must represent a positive duration"):
        parse_timeframe("-10s")
    with pytest.raises(ValueError, match="timeframe must represent a positive duration"):
        parse_timeframe("0ms")


def test_align_timestamp():
    """Verify that align_timestamp aligns timestamps correctly to timeframe boundaries."""
    assert align_timestamp(1500, 1000) == (1000, 2000)
    assert align_timestamp(1000, 1000) == (1000, 2000)
    assert align_timestamp(999, 1000) == (0, 1000)
    assert align_timestamp(2500, 5000) == (0, 5000)

    with pytest.raises(TypeError, match="ts must be an integer"):
        align_timestamp("1500", 1000)
    with pytest.raises(TypeError, match="timeframe_ms must be an integer"):
        align_timestamp(1500, "1000")

    with pytest.raises(ValueError, match="ts must be positive"):
        align_timestamp(0, 1000)
    with pytest.raises(ValueError, match="timeframe_ms must be positive"):
        align_timestamp(1500, 0)
    with pytest.raises(ValueError, match="timeframe_ms must be positive"):
        align_timestamp(1500, -1000)
