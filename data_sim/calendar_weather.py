"""Solar/lunar calendar, Vietnamese holidays and simulated HCMC rainfall."""

import datetime as dt
from dataclasses import dataclass

import numpy as np
from lunardate import LunarDate

# Solar public holidays (month, day). 2/9 is a two-day holiday since 2025 (1/9 or 3/9 added; we use 1/9).
SOLAR_HOLIDAYS = {(1, 1), (4, 30), (5, 1), (9, 1), (9, 2)}
TET_HOLIDAY_DAYS = 5  # lunar 1/1 .. 1/5
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


def build_calendar(dates: list[dt.date]) -> list[CalendarDay]:
    tets = _tet_dates(range(dates[0].year - 1, dates[-1].year + 2))
    out: list[CalendarDay] = []
    for d in dates:
        lun = LunarDate.from_solar_date(d.year, d.month, d.day)
        leap = bool(lun.is_leap_month)
        is_tet = (not leap) and lun.month == 1 and lun.day <= 3
        hung_vuong = (not leap) and lun.month == 3 and lun.day == 10
        tet_holiday = (not leap) and lun.month == 1 and lun.day <= TET_HOLIDAY_DAYS
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
                is_holiday=(d.month, d.day) in SOLAR_HOLIDAYS or hung_vuong or tet_holiday,
                days_to_tet=(nearest - d).days,
            )
        )
    return out


def simulate_rain(dates: list[dt.date], rng: np.random.Generator) -> np.ndarray:
    """Daily rainfall (mm) for HCMC: rainy season May–Nov, dry season Dec–Apr."""
    rain = np.zeros(len(dates))
    for i, d in enumerate(dates):
        wet = 5 <= d.month <= 11
        p_rain = 0.62 if wet else 0.10
        if rng.random() < p_rain:
            rain[i] = rng.gamma(0.9, 16.0) if wet else rng.gamma(0.6, 5.0)
    return np.round(rain, 1)
