import time

from leviathan_common.time.epoch import current_epoch_ms, normalize_epoch_ms


def test_current_epoch_ms_returns_milliseconds_near_now():
    """Verify current_epoch_ms returns a UTC epoch close to wall-clock ms."""
    before = time.time() * 1000.0
    result = current_epoch_ms()
    after = time.time() * 1000.0

    assert before <= result <= after
    # Milliseconds epoch for 2001+ is above the legacy-seconds threshold.
    assert result > 1e11


def test_normalize_epoch_ms_migrates_legacy_seconds():
    """Verify second-scale epochs are scaled to milliseconds UTC."""
    assert normalize_epoch_ms(1_700_000_000.0) == 1_700_000_000_000.0
    assert normalize_epoch_ms(1e10) == 1e13


def test_normalize_epoch_ms_preserves_millisecond_epochs():
    """Verify already-normalized millisecond epochs are left unchanged."""
    ms_epoch = 1_700_000_000_000.0
    assert normalize_epoch_ms(ms_epoch) == ms_epoch
    assert normalize_epoch_ms(1e11) == 1e11
