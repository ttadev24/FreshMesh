"""Split conformal calibration of P10–P90 intervals (CQR, Romano et al. 2019).

On a calibration holdout that the model never trained on, the conformity score is
``E_i = max(lo_i - y_i, y_i - hi_i)`` (negative when inside, positive when outside). The offset ``Q`` is the
``ceil((n + 1)(1 - alpha)) / n`` empirical quantile of ``E``; the calibrated interval ``[lo - Q, hi + Q]``
covers a new exchangeable point with probability ``>= 1 - alpha``. FreshMesh computes scores in the
model's scaled space (``y / scale``), so one offset per chain and horizon fits slow and fast SKUs alike.
"""

from __future__ import annotations

import math

import numpy as np

TARGET_COVERAGE = 0.8


def cqr_offset(
    lo: np.ndarray, hi: np.ndarray, y: np.ndarray, *, alpha: float = 1.0 - TARGET_COVERAGE
) -> float:
    """Conformal offset ``Q`` for interval ``[lo, hi]`` at miscoverage ``alpha``."""
    lo, hi, y = (np.asarray(a, dtype=np.float64) for a in (lo, hi, y))
    n = len(y)
    if n == 0:
        raise ValueError("calibration set is empty")
    scores = np.sort(np.maximum(lo - y, y - hi))
    k = math.ceil((n + 1) * (1.0 - alpha))
    # With fewer than ~1/alpha points the exact conformal quantile is +inf; use the largest observed score
    # instead (conservative, finite, JSON-safe) — the finite-sample guarantee does not hold in that case.
    return float(scores[min(k, n) - 1])


def apply_offset(q: np.ndarray, offset: float | np.ndarray) -> np.ndarray:
    """Widen (or shrink, if ``offset < 0``) P10/P90 by ``offset``; clamp at 0 and keep P10<=P50<=P90.

    Shrinking is symmetric and stops at P50, so P50 is never moved by the offset (only by the clamp at 0).
    ``q`` has shape ``(n, 3)``; ``offset`` is a scalar or per-row array of finite values.
    """
    q = np.asarray(q, dtype=np.float64)
    off = np.broadcast_to(np.asarray(offset, dtype=np.float64), (q.shape[0],))
    if not np.all(np.isfinite(off)):
        raise ValueError("conformal offset must be finite; recalibrate the model")
    p50 = np.maximum(q[:, 1], 0.0)
    out = np.empty_like(q)
    out[:, 1] = p50
    out[:, 0] = np.clip(np.minimum(q[:, 0] - off, p50), 0.0, None)
    out[:, 2] = np.maximum(q[:, 2] + off, p50)
    return out


def interval_coverage(lo: np.ndarray, hi: np.ndarray, y: np.ndarray) -> float:
    lo, hi, y = (np.asarray(a, dtype=np.float64) for a in (lo, hi, y))
    if len(y) == 0:
        return float("nan")
    return float(np.mean((y >= lo) & (y <= hi)))
