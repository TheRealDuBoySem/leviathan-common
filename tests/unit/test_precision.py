import pytest
from leviathan_common.pricing.precision import format_price, get_decimal_precision


def test_format_price_preconditions_and_formatting():
    """Verify format_price preconditions validation and formatting behavior."""
    assert format_price(100.0) == "100.00"
    assert format_price(100.12345) == "100.12345"
    assert format_price(101.2) == "101.20"

    assert format_price(1.34234, 0.0001) == "1.3423"
    assert format_price(1.34234, 0.01) == "1.34"
    assert format_price(1.34234, 0.5) == "1.3"
    assert format_price(1.34234, 1.0) == "1"
    assert format_price(1234.56, 10.0) == "1235"

    with pytest.raises(TypeError, match="price must be a float or integer"):
        format_price("invalid")
    with pytest.raises(TypeError, match="price must be a float or integer"):
        format_price(None)

    with pytest.raises(TypeError, match="tick_size must be a float or integer"):
        format_price(100.0, "invalid")

    with pytest.raises(ValueError, match="tick_size must be strictly positive"):
        format_price(100.0, 0.0)
    with pytest.raises(ValueError, match="tick_size must be strictly positive"):
        format_price(100.0, -0.1)


def test_get_decimal_precision():
    """Verify that get_decimal_precision computes decimal length correctly."""
    assert get_decimal_precision(0.0001) == 4
    assert get_decimal_precision(0.01) == 2
    assert get_decimal_precision(0.5) == 1
    assert get_decimal_precision(1.0) == 0
    assert get_decimal_precision(10) == 0
    assert get_decimal_precision(0.0000000001) == 10

    with pytest.raises(TypeError, match="val must be a float or integer"):
        get_decimal_precision("invalid")
    with pytest.raises(TypeError, match="val must be a float or integer"):
        get_decimal_precision(None)
