"""Confidence card (Cao / Trung bình / Thấp) and drift alert, with Vietnamese explanations.

Rules (spec §4.3), evaluated in order:

* **Thấp** if history is short (``< SHORT_HISTORY_DAYS``), the interval is very wide relative to the median
  (``rel_width > WIDE_REL_WIDTH``), or the realised 7-day coverage is below ``DRIFT_COVERAGE``.
* **Cao** if history is long (``>= LONG_HISTORY_DAYS``), the interval is narrow
  (``rel_width <= NARROW_REL_WIDTH``) and the 7-day coverage (when known) is at least ``GOOD_COVERAGE``.
* otherwise **Trung bình**.

``rel_width = (P90 - P10) / max(P50, 1)``. Width thresholds were set on the simulated chains, where daily
demand is negative-binomial: an honest 80% interval for a SKU selling ~20/day is already ~1.0–1.4 × P50.
"""

from __future__ import annotations

from dataclasses import dataclass

SHORT_HISTORY_DAYS = 28
LONG_HISTORY_DAYS = 90
NARROW_REL_WIDTH = 1.2
WIDE_REL_WIDTH = 2.2
DRIFT_COVERAGE = 0.70
GOOD_COVERAGE = 0.75

HIGH, MEDIUM, LOW = "Cao", "Trung bình", "Thấp"


def relative_width(p10: float, p50: float, p90: float) -> float:
    return float((p90 - p10) / max(p50, 1.0))


def _pct(x: float) -> str:
    return f"{round(100 * x)}%"


def confidence_level(rel_width: float, history_days: int, coverage_7d: float | None) -> tuple[str, str]:
    """Return ``(level, reason_vi)``; the reason is one Vietnamese sentence naming the deciding factor."""
    if history_days < SHORT_HISTORY_DAYS:
        return LOW, (
            f"Cửa hàng mới chỉ có {history_days} ngày lịch sử bán hàng nên mô hình chưa học đủ, "
            f"khoảng dự báo rộng ({_pct(rel_width)} so với P50)."
        )
    if coverage_7d is not None and coverage_7d < DRIFT_COVERAGE:
        return LOW, (
            f"Trong 7 ngày gần nhất chỉ {_pct(coverage_7d)} điểm (mặt hàng × ngày) có doanh số thực "
            "nằm trong khoảng P10–P90 (mục tiêu 80%), nhu cầu có thể đang thay đổi."
        )
    if rel_width > WIDE_REL_WIDTH:
        return LOW, (
            f"Khoảng dự báo P10–P90 rất rộng ({_pct(rel_width)} so với P50) do nhu cầu biến động mạnh "
            f"và doanh số nhỏ."
        )
    cov_ok = coverage_7d is None or coverage_7d >= GOOD_COVERAGE
    if history_days >= LONG_HISTORY_DAYS and rel_width <= NARROW_REL_WIDTH and cov_ok:
        cov_txt = "" if coverage_7d is None else f", độ phủ 7 ngày gần nhất {_pct(coverage_7d)}"
        return HIGH, (
            f"Có {history_days} ngày lịch sử, khoảng dự báo tương đối hẹp "
            f"({_pct(rel_width)} so với P50){cov_txt}."
        )
    cov_txt = "" if coverage_7d is None else f", độ phủ 7 ngày gần nhất {_pct(coverage_7d)}"
    return MEDIUM, (
        f"Khoảng dự báo ở mức vừa phải ({_pct(rel_width)} so với P50) với {history_days} ngày lịch sử"
        f"{cov_txt}."
    )


@dataclass(frozen=True)
class DriftStatus:
    chain_id: str
    store_id: str
    coverage_7d: float | None  # share of (sku, day) actuals inside the calibrated P10–P90, last 7 days
    n_points: int
    alert: bool
    message_vi: str


def drift_status_from_coverage(
    chain_id: str, store_id: str, coverage_7d: float | None, n_points: int
) -> DriftStatus:
    """Alert when realised 7-day coverage drops below 70%, suggesting the "An toàn" plan."""
    if coverage_7d is None or n_points == 0:
        return DriftStatus(
            chain_id,
            store_id,
            None,
            0,
            False,
            "Chưa đủ dữ liệu 7 ngày gần nhất để kiểm tra độ phủ dự báo.",
        )
    if coverage_7d < DRIFT_COVERAGE:
        msg = (
            f"Cảnh báo: độ phủ P10–P90 trong 7 ngày gần nhất (tính trên các điểm mặt hàng × ngày) chỉ đạt "
            f"{_pct(coverage_7d)} (dưới 70%), "
            f'dự báo đang lệch so với thực tế — nên chọn phương án "An toàn" khi đặt hàng.'
        )
        return DriftStatus(chain_id, store_id, coverage_7d, n_points, True, msg)
    msg = (
        f"Độ phủ P10–P90 trong 7 ngày gần nhất (tính trên các điểm mặt hàng × ngày) đạt {_pct(coverage_7d)}, "
        "dự báo ổn định."
    )
    return DriftStatus(chain_id, store_id, coverage_7d, n_points, False, msg)
