"""Demand distribution reconstructed from three forecast quantiles (P10, P50, P90).

Method (see docs/decision-methods.md): a monotone inverse CDF Q(u)
- linear between (0.1, P10), (0.5, P50) and (0.9, P90);
- exponential tails outside [0.1, 0.9] whose slope matches the adjacent linear
  segment, so Q is continuous with a continuous derivative:
      u < 0.1:  Q(u) = P10 + b_lo · ln(u / 0.1),        b_lo = (P50 − P10) / 4
      u > 0.9:  Q(u) = P90 − b_hi · ln((1 − u) / 0.1),  b_hi = (P90 − P50) / 4
Sampling is inverse-transform: u ~ U(0, 1), x = Q(u), clipped at 0 and rounded
to the nearest integer (demand is counted in units).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class QuantileDistribution:
    p10: float
    p50: float
    p90: float

    def __post_init__(self) -> None:
        if not (self.p10 <= self.p50 <= self.p90):
            raise ValueError(f"need p10 <= p50 <= p90, got {self.p10}, {self.p50}, {self.p90}")

    def ppf(self, u: np.ndarray | float) -> np.ndarray | float:
        u_arr = np.clip(np.asarray(u, dtype=float), 1e-12, 1 - 1e-12)
        b_lo = (self.p50 - self.p10) / 4.0
        b_hi = (self.p90 - self.p50) / 4.0
        mid = np.interp(u_arr, [0.1, 0.5, 0.9], [self.p10, self.p50, self.p90])
        lo = self.p10 + b_lo * np.log(u_arr / 0.1)
        hi = self.p90 - b_hi * np.log((1.0 - u_arr) / 0.1)
        x = np.where(u_arr < 0.1, lo, np.where(u_arr > 0.9, hi, mid))
        return float(x) if np.ndim(u) == 0 else x


def sample_demand(dist: QuantileDistribution, rng: np.random.Generator, size: int) -> np.ndarray:
    """Draw `size` integer, non-negative demand samples."""
    x = dist.ppf(rng.random(size))
    return np.rint(np.maximum(x, 0.0)).astype(np.int64)
