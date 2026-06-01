from typing import Optional

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

        s_tick = f"{tick_size:.12f}".rstrip('0')
        decimals_count = len(s_tick.split('.')[-1])
        return f"{price:.{decimals_count}f}"

    s = f"{price:.8f}".rstrip('0')
    if s.endswith('.'):
        s += '00'
    else:
        decimals = s.split('.')[-1]
        if len(decimals) < 2:
            s += '0' * (2 - len(decimals))
    return s


def parse_timeframe(tf_str: str) -> int:
    """
    Parses timeframe string like '10s', '1m', '1h' into milliseconds.

    Preconditions:
        - tf_str must be a non-empty string.
    Postconditions:
        - Returns the parsed timeframe in milliseconds as a positive integer.
    """
    if not isinstance(tf_str, str):
        raise TypeError("timeframe must be a string")
    tf_str_clean = tf_str.strip().lower()
    if not tf_str_clean:
        raise ValueError("timeframe string cannot be empty")

    try:
        if tf_str_clean.endswith("ms"):
            res = int(tf_str_clean[:-2])
        elif tf_str_clean.endswith("s"):
            res = int(tf_str_clean[:-1]) * 1000
        elif tf_str_clean.endswith("m"):
            res = int(tf_str_clean[:-1]) * 60000
        elif tf_str_clean.endswith("h"):
            res = int(tf_str_clean[:-1]) * 3600000
        else:
            res = int(tf_str_clean)
    except ValueError as e:
        raise ValueError(f"Invalid timeframe format: '{tf_str}'") from e

    if res <= 0:
        raise ValueError("timeframe must represent a positive duration")
    return res
