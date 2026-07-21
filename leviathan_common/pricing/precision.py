from typing import Optional


def get_decimal_precision(val: float) -> int:
    """
    Calculates the decimal precision (number of digits after the decimal point)
    of a floating point number up to 12 decimal places.

    Preconditions:
        - val must be a float or integer.
    """
    if not isinstance(val, (int, float)):
        raise TypeError("val must be a float or integer")
    s_val = f"{val:.12f}".rstrip('0')
    decimals = s_val.split('.')[-1]
    return len(decimals)


def format_price(price: float, tick_size: Optional[float] = None) -> str:
    """
    Formats price to string based on the tick_size precision, falling back to dynamic precision.

    Preconditions:
        - price must be a float or integer.
        - tick_size must be a positive float or integer if provided.
    Postconditions:
        - Returns a formatted string representing the price.
    """
    if not isinstance(price, (int, float)):
        raise TypeError("price must be a float or integer")
    if tick_size is not None:
        if not isinstance(tick_size, (int, float)):
            raise TypeError("tick_size must be a float or integer")
        if tick_size <= 0:
            raise ValueError("tick_size must be strictly positive")

        decimals_count = get_decimal_precision(tick_size)
        return f"{price:.{decimals_count}f}"

    s = f"{price:.8f}".rstrip('0')
    if s.endswith('.'):
        s += '00'
    else:
        decimals = s.split('.')[-1]
        if len(decimals) < 2:
            s += '0' * (2 - len(decimals))
    return s
