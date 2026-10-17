"""Why a forecast is what it is, and what a known event would change: counterfactuals on the known-ahead
calendar covariates of the quantile model.

* **Drivers.** For each row, one covariate at a time is switched to its ordinary-day value and the model is
  asked again: ``effect = P50(as forecast) − P50(counterfactual)``. Tết / holiday / Rằm / mùng 1 / promo
  flags are switched off. The weekday reaches the model twice (its one-hot and the same-weekday lags), so
  its counterfactual is an "ordinary day": same-weekday lags set to the 7-day mean and the prediction
  averaged over the seven weekday flags. These are the effects
  the model learned from the chain's history (association, not proven cause); effects under
  ``MIN_EFFECT_PCT`` are dropped.
* **Scenarios.** The same covariates switched on for every forecast day (a planned promotion, an event day).
  Rain is not offered: the model sees monthly rain climatology, not daily rain (see ``features``), so a
  "heavy rain tomorrow" what-if would be extrapolation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np

from forecasting.features import FEATURE_NAMES

FLAG_DRIVERS: tuple[tuple[str, str], ...] = (
    ("is_tet", "Tết"),
    ("is_holiday", "Ngày lễ"),
    ("is_ram", "Rằm"),
    ("is_mung1", "Mùng 1"),
    ("promo", "Khuyến mãi"),
)
WEEKDAY_VI = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật")
SCENARIO_FEATURES = {"promo": "Khuyến mãi", "is_holiday": "Ngày lễ / sự kiện"}
MIN_EFFECT_PCT = 3.0
_COL = {name: i for i, name in enumerate(FEATURE_NAMES)}
_DOW = [_COL[f"dow_{d}"] for d in range(7)]
_SDOW_LAGS = [_COL["lag_sdow1"], _COL["lag_sdow2"]]

Predict = Callable[[np.ndarray], np.ndarray]  # features (n, N_FEATURES) -> P50 units (n,)


def _effect(key: str, label: str, p50: float, cf: float) -> dict | None:
    delta = p50 - cf
    rel = 100.0 * delta / max(cf, 1.0)
    if abs(rel) < MIN_EFFECT_PCT:
        return None
    return {"key": key, "label_vi": label, "delta_units": round(delta, 1), "delta_pct": round(rel, 1)}


def drivers(predict: Predict, X: np.ndarray) -> list[list[dict]]:
    """Per row, the covariate effects on P50, largest first."""
    base = predict(X)
    out: list[list[dict]] = [[] for _ in range(len(X))]
    for name, label in FLAG_DRIVERS:
        on = np.flatnonzero(X[:, _COL[name]] != 0)
        if not on.size:
            continue
        off = X[on].copy()
        off[:, _COL[name]] = 0.0
        for i, cf in zip(on, predict(off), strict=True):
            if e := _effect(name, label, float(base[i]), float(cf)):
                out[i].append(e)
    ordinary = X.copy()
    ordinary[:, _SDOW_LAGS] = X[:, [_COL["roll_mean7"]]]
    per_day = []
    for d in range(7):
        Xd = ordinary.copy()
        Xd[:, _DOW] = 0.0
        Xd[:, _DOW[d]] = 1.0
        per_day.append(predict(Xd))
    mean_day = np.mean(per_day, axis=0)
    for i, d in enumerate(np.argmax(X[:, _DOW], axis=1)):
        if e := _effect(f"dow_{d}", WEEKDAY_VI[d], float(base[i]), float(mean_day[i])):
            out[i].append(e)
    for row in out:
        row.sort(key=lambda e: -abs(e["delta_pct"]))
    return out


def apply_scenario(X: np.ndarray, scenario: Mapping[str, bool]) -> np.ndarray:
    """Features with the scenario's covariates switched on (keys of ``SCENARIO_FEATURES``)."""
    unknown = set(scenario) - set(SCENARIO_FEATURES)
    if unknown:
        raise ValueError(f"unknown scenario keys: {sorted(unknown)}")
    out = X.copy()
    for name, on in scenario.items():
        if on:
            out[:, _COL[name]] = 1.0
    return out
