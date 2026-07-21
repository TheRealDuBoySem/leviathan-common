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


def align_timestamp(ts: int, timeframe_ms: int) -> tuple[int, int]:
    """
    Aligns a timestamp to a timeframe boundary.
    Returns a tuple of (start_ts, end_ts).

    Preconditions:
        - ts must be a positive integer.
        - timeframe_ms must be a positive integer.
    """
    if not isinstance(ts, int) or ts <= 0:
        raise TypeError("ts must be an integer") if not isinstance(ts, int) else ValueError("ts must be positive")
    if not isinstance(timeframe_ms, int) or timeframe_ms <= 0:
        raise TypeError("timeframe_ms must be an integer") if not isinstance(timeframe_ms, int) else ValueError("timeframe_ms must be positive")

    start_ts = (ts // timeframe_ms) * timeframe_ms
    end_ts = start_ts + timeframe_ms
    return start_ts, end_ts
