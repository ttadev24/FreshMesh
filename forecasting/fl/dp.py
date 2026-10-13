"""Privacy accounting for client-level central DP on the shared body (Gaussian mechanism, zCDP).

Mechanism (what ``forecasting.fl`` runs through Flower's ``fixedclipping_mod`` +
``DifferentialPrivacyClientSideFixedClipping``): every round, each chain clips the L2 norm of its body update
to ``C`` before sending it; the server averages the ``n`` clipped updates with *equal* weights and adds ``N(0,
(z * C / n)^2)`` noise per coordinate. Equivalently, the sum of updates (sensitivity ``C`` when one chain is
added or removed) gets noise ``z * C``, i.e. each round is a Gaussian mechanism with noise multiplier ``z``.

Accounting: a Gaussian mechanism with multiplier ``z`` is ``rho = 1 / (2 z^2)``-zCDP (Bun & Steinke 2016);
zCDP composes additively over ``R`` rounds (``rho_R = R / (2 z^2)``) and converts to ``(epsilon, delta)``-DP
with ``epsilon = rho + 2 * sqrt(rho * ln(1 / delta))``. Every chain takes part in every round, so there is
**no** subsampling amplification. The conversion is a standard (slightly loose) bound, not the tightest
numerical RDP/PLD accountant. The guarantee is *client-level* (a whole chain's data) and covers only what
leaves the chain: the per-round aggregated body. Personal heads (FedPer) and conformal offsets never leave the
chain; reported evaluation metrics are aggregate statistics outside this guarantee."""

from __future__ import annotations

import math

DEFAULT_DELTA = 1e-5


def zcdp_epsilon(noise_multiplier: float, rounds: int, delta: float = DEFAULT_DELTA) -> float:
    """``epsilon`` at ``delta`` after ``rounds`` Gaussian releases with multiplier ``noise_multiplier``."""
    if noise_multiplier <= 0:
        return math.inf
    if rounds <= 0:
        return 0.0
    if not 0.0 < delta < 1.0:
        raise ValueError("delta must be in (0, 1)")
    rho = rounds / (2.0 * noise_multiplier**2)
    return rho + 2.0 * math.sqrt(rho * math.log(1.0 / delta))


def noise_multiplier_for_epsilon(epsilon: float, rounds: int, delta: float = DEFAULT_DELTA) -> float:
    """Smallest noise multiplier ``z`` such that ``zcdp_epsilon(z, rounds, delta) <= epsilon``."""
    if epsilon <= 0 or not math.isfinite(epsilon):
        raise ValueError("epsilon must be positive and finite")
    if rounds <= 0:
        raise ValueError("rounds must be positive")
    if not 0.0 < delta < 1.0:
        raise ValueError("delta must be in (0, 1)")
    log_inv_delta = math.log(1.0 / delta)
    rho = (math.sqrt(log_inv_delta + epsilon) - math.sqrt(log_inv_delta)) ** 2
    return math.sqrt(rounds / (2.0 * rho))
