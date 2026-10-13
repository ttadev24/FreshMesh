from forecasting.confidence import (
    HIGH,
    LOW,
    MEDIUM,
    confidence_level,
    drift_status_from_coverage,
    relative_width,
)


def test_relative_width_floor():
    assert relative_width(0.0, 0.5, 2.0) == 2.0
    assert relative_width(8.0, 10.0, 14.0) == 0.6


def test_short_history_is_low_and_says_so():
    level, reason = confidence_level(0.5, 14, 0.9)
    assert level == LOW
    assert "14 ngày lịch sử" in reason


def test_low_coverage_is_low():
    level, reason = confidence_level(0.5, 300, 0.6)
    assert level == LOW and "7 ngày" in reason


def test_wide_interval_is_low():
    assert confidence_level(2.5, 300, 0.85)[0] == LOW


def test_high_and_medium():
    assert confidence_level(0.6, 300, 0.85)[0] == HIGH
    assert confidence_level(0.6, 300, None)[0] == HIGH
    assert confidence_level(1.6, 300, 0.85)[0] == MEDIUM
    assert confidence_level(0.6, 60, 0.85)[0] == MEDIUM
    assert confidence_level(0.6, 300, 0.72)[0] == MEDIUM


def test_reason_is_one_vietnamese_sentence():
    for args in ((0.5, 14, 0.9), (0.5, 300, 0.6), (2.5, 300, 0.9), (0.6, 300, 0.85), (1.6, 300, 0.85)):
        reason = confidence_level(*args)[1]
        assert reason.endswith(".") and reason.count(". ") == 0


def test_drift_alert_below_70pct():
    ds = drift_status_from_coverage("C", "S", 0.6, 200)
    assert ds.alert and "An toàn" in ds.message_vi and not hasattr(ds, "source")
    ok = drift_status_from_coverage("C", "S", 0.8, 200)
    assert not ok.alert and "80%" in ok.message_vi
    none = drift_status_from_coverage("C", "S", None, 0)
    assert not none.alert and none.coverage_7d is None


def test_low_coverage_reason_counts_sku_day_points_not_days():
    """LOW-6: 7-day coverage is a share of (mặt hàng, ngày) points, not of days."""
    from forecasting.confidence import confidence_level, drift_status_from_coverage

    _, reason = confidence_level(1.0, 120, 0.5)
    assert "% ngày có" not in reason and "mặt hàng × ngày" in reason
    msg = drift_status_from_coverage("C", "S", 0.5, 70).message_vi
    assert "mặt hàng × ngày" in msg
