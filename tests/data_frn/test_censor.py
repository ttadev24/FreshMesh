import numpy as np

from data_frn import DAY_HOURS
from data_frn.censor import MIN_SHARE, daytime_profiles, instock_share, observed_demand, recovered_demand

N_DAY = DAY_HOURS.stop - DAY_HOURS.start  # 16 daytime hours (6..21)


def _day(morning: float, afternoon: float, night: float = 0.0) -> np.ndarray:
    """24 hourly sales: ``morning`` spread over 6..13, ``afternoon`` over 14..21, ``night`` at hour 23."""
    h = np.zeros(24, dtype=np.float32)
    h[6:14] = morning / 8
    h[14:22] = afternoon / 8
    h[23] = night
    return h


def test_observed_demand_drops_days_with_any_daytime_stockout():
    out = observed_demand(np.array([3.0, 4.0, 0.0]), np.array([0, 2, 0]))
    assert out[0] == 3.0 and np.isnan(out[1]) and out[2] == 0.0


def test_profiles_use_own_clean_days_or_fall_back_to_pooled():
    series = np.array([0, 0, 0, 1, 1])  # series 1 has only 2 clean days → pooled profile
    hours = np.stack([_day(8, 0), _day(8, 0), _day(8, 0), _day(0, 8), _day(0, 8)])
    prof = daytime_profiles(series, 2, hours, np.zeros(5, dtype=int))
    assert np.allclose(prof[0, :8], 1 / 8) and np.allclose(prof[0, 8:], 0)
    pooled = hours[:, DAY_HOURS].sum(0) / hours[:, DAY_HOURS].sum()
    assert np.allclose(prof[1], pooled)
    assert np.allclose(prof.sum(axis=1), 1.0)


def test_recovered_demand_scales_daytime_sales_by_the_in_stock_share():
    profile = np.full((3, N_DAY), 1 / N_DAY)  # flat profile: each daytime hour = 1/16 of daytime sales
    status = np.zeros((3, 24), dtype=np.int8)
    status[1, 14:22] = 1  # afternoon out of stock → in-stock share 0.5
    status[2, 6:20] = 1  # 14 of 16 daytime hours out of stock → share 0.125 < MIN_SHARE
    hours = np.stack([_day(8, 8, night=1), _day(8, 0, night=1), _day(1, 0)])
    stock = (status[:, DAY_HOURS] == 1).sum(axis=1)
    share = instock_share(profile, status)
    assert np.allclose(share, [1.0, 0.5, 0.125]) and share[2] < MIN_SHARE
    est = recovered_demand(hours, status, stock, profile)
    assert est[0] == 17.0  # fully stocked: recorded sales (incl. night)
    assert est[1] == 8 / 0.5 + 1  # daytime 8 recovered to 16, night 1 kept
    assert np.isnan(est[2])
