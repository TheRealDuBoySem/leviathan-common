# Unix epoch values below this threshold are treated as legacy seconds (KI-04 ms UTC).
_LEGACY_SECONDS_EPOCH_THRESHOLD = 1e11


def current_epoch_ms() -> float:
    """Returns the current UTC epoch timestamp in milliseconds."""
    import time

    return time.time() * 1000.0


def normalize_epoch_ms(value: float) -> float:
    """
    Normalizes a persisted epoch timestamp to milliseconds UTC.

    Values below _LEGACY_SECONDS_EPOCH_THRESHOLD are multiplied by 1000 to
    migrate legacy second-based timestamps transparently.
    """
    if value < _LEGACY_SECONDS_EPOCH_THRESHOLD:
        return value * 1000.0
    return value
