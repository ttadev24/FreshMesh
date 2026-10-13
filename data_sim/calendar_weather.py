"""Solar/lunar calendar, official Vietnamese holidays and real HCMC rainfall.

* Holidays: `data_real/holidays_vn.json` (Labor Code 2019 Art. 112 + yearly government notices, dataset
  CALENDAR_VN). Dates in a year that file does not cover raise ``ValueError`` (nothing is guessed).
* Lunar fields: `lunardate`.
* Rain: `real_rain` reads the committed Open-Meteo snapshot (`data_real/snapshot/weather_hcmc.json`).
  `simulate_rain` is the former synthetic generator, kept only for out-of-sample experiments in
  `simulation/` (future days that have no observation); the chain DBs never use it.
"""

import datetime as dt
from dataclasses import dataclass

import numpy as np
from lunardate import LunarDate

from data_real import snapshot

PRE_TET_DAYS = 10  # shopping rush before Tết


@dataclass(frozen=True)
class CalendarDay:
    date: dt.date
    dow: int  # 0 = Monday
    lunar_month: int
    lunar_day: int
    is_leap_month: bool
    is_tet: bool
    is_ram: bool
    is_mung1: bool
    is_holiday: bool
    days_to_tet: int  # days until the next lunar new year (0 on Tết day 1); negative after it


def _tet_dates(years: range) -> list[dt.date]:
    return [LunarDate(y, 1, 1).to_solar_date() for y in years]


def official_holidays(years: set[int]) -> set[dt.date]:
    """Statutory + compensatory days off (CALENDAR_VN) for `years`; raises for uncovered years."""
    data = snapshot.holidays()
    missing = sorted(years - set(data["years_covered"]))
    if missing:
        raise ValueError(f"no official holiday data for years {missing} in data_real/holidays_vn.json")
    return {dt.date.fromisoformat(h["date"]) for h in data["holidays"]}


def build_calendar(dates: list[dt.date]) -> list[CalendarDay]:
    holidays = official_holidays({d.year for d in dates})
    tets = _tet_dates(range(dates[0].year - 1, dates[-1].year + 2))
    out: list[CalendarDay] = []
    for d in dates:
        lun = LunarDate.from_solar_date(d.year, d.month, d.day)
        leap = bool(lun.is_leap_month)
        is_tet = (not leap) and lun.month == 1 and lun.day <= 3
        nearest = min(tets, key=lambda t: abs((t - d).days))
        out.append(
            CalendarDay(
                date=d,
                dow=d.weekday(),
                lunar_month=lun.month,
                lunar_day=lun.day,
                is_leap_month=leap,
                is_tet=is_tet,
                is_ram=lun.day == 15,
                is_mung1=lun.day == 1,
                is_holiday=d in holidays,
                days_to_tet=(nearest - d).days,
            )
        )
    return out


def real_rain(dates: list[dt.date]) -> tuple[np.ndarray, dict[str, str]]:
    """Daily precipitation (mm) from the Open-Meteo snapshot and the dataset id of each date.

    Raises ``ValueError`` if a date has no observation/forecast in the snapshot."""
    rows = {t: (float(v), src) for t, v, src in snapshot.weather()["daily"]}
    missing = [d.isoformat() for d in dates if d.isoformat() not in rows]
    if missing:
        raise ValueError(f"no real weather for {missing[0]}..{missing[-1]} ({len(missing)} days); "
                         "run `uv run python -m data_real fetch --only weather`")
    return (np.array([rows[d.isoformat()][0] for d in dates]),
            {d.isoformat(): rows[d.isoformat()][1] for d in dates})


def simulate_rain(dates: list[dt.date], rng: np.random.Generator) -> np.ndarray:
    """Synthetic daily rainfall (mm) for HCMC: rainy season May–Nov, dry season Dec–Apr. Not used for the
    chain DBs (see module docstring)."""
    rain = np.zeros(len(dates))
    for i, d in enumerate(dates):
        wet = 5 <= d.month <= 11
        p_rain = 0.62 if wet else 0.10
        if rng.random() < p_rain:
            rain[i] = rng.gamma(0.9, 16.0) if wet else rng.gamma(0.6, 5.0)
    return np.round(rain, 1)
