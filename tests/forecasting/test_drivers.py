import numpy as np
import pytest

from forecasting.drivers import apply_scenario, drivers
from forecasting.features import FEATURE_NAMES

COL = {n: i for i, n in enumerate(FEATURE_NAMES)}


def _row(**on: float) -> np.ndarray:
    x = np.zeros(len(FEATURE_NAMES))
    for name, value in on.items():
        x[COL[name]] = value
    return x


def predict(X: np.ndarray) -> np.ndarray:  # a known model: Rằm +5, Saturday +2 on a base of 10
    return 10 + 5 * X[:, COL["is_ram"]] + 2 * X[:, COL["dow_5"]]


def test_drivers_recover_the_effects_of_a_known_model():
    out = drivers(predict, np.stack([_row(is_ram=1, dow_5=1), _row(dow_0=1)]))
    ram, saturday = out[0]
    assert (ram["key"], ram["label_vi"], ram["delta_units"]) == ("is_ram", "Rằm", 5.0)
    assert ram["delta_pct"] == pytest.approx(100 * 5 / 12)  # vs the same Saturday without Rằm
    assert saturday["label_vi"] == "Thứ Bảy" and saturday["delta_units"] == pytest.approx(2 - 2 / 7, abs=0.05)
    assert out[1] == []  # Monday is 2,8% under the weekday mean: below the reporting threshold


def test_scenario_switches_known_covariates_on_and_rejects_others():
    X = np.stack([_row(dow_2=1)])
    on = apply_scenario(X, {"promo": True, "is_holiday": False})
    assert on[0, COL["promo"]] == 1 and on[0, COL["is_holiday"]] == 0 and X[0, COL["promo"]] == 0
    with pytest.raises(ValueError):
        apply_scenario(X, {"rain": True})
