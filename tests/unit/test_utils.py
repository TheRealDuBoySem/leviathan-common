import pytest
from leviathan_common.utils import format_price, parse_timeframe

def test_format_price_preconditions_and_formatting():
    """Verify format_price preconditions validation and formatting behavior."""
    # Test valid dynamic precision formatting when tick_size is None
    assert format_price(100.0) == "100.00"
    assert format_price(100.12345) == "100.12345"
    assert format_price(101.2) == "101.20"

    # Test formatting with various tick_size values
    assert format_price(1.34234, 0.0001) == "1.3423"
    assert format_price(1.34234, 0.01) == "1.34"
    assert format_price(1.34234, 0.5) == "1.3"
    assert format_price(1.34234, 1.0) == "1"
    assert format_price(1234.56, 10.0) == "1235"

    # Invalid price type
    with pytest.raises(TypeError, match="price must be a float or integer"):
        format_price("invalid")
    with pytest.raises(TypeError, match="price must be a float or integer"):
        format_price(None)

    # Invalid tick_size type
    with pytest.raises(TypeError, match="tick_size must be a float or integer"):
        format_price(100.0, "invalid")

    # Invalid tick_size value (<= 0)
    with pytest.raises(ValueError, match="tick_size must be strictly positive"):
        format_price(100.0, 0.0)
    with pytest.raises(ValueError, match="tick_size must be strictly positive"):
        format_price(100.0, -0.1)


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
    # Test invalid type
    with pytest.raises(TypeError, match="timeframe must be a string"):
        parse_timeframe(123)

    # Test empty string
    with pytest.raises(ValueError, match="timeframe string cannot be empty"):
        parse_timeframe("   ")

    # Test invalid format
    with pytest.raises(ValueError, match="Invalid timeframe format"):
        parse_timeframe("abc")

    # Test non-positive duration
    with pytest.raises(ValueError, match="timeframe must represent a positive duration"):
        parse_timeframe("-10s")
    with pytest.raises(ValueError, match="timeframe must represent a positive duration"):
        parse_timeframe("0ms")
