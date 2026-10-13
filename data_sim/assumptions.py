"""Program assumptions (dataset GEN_PROGRAM_V1) consumed by decision/ and the API.

The same values are written to the `assumptions` table of every chain DB and explained
in docs/data-assumptions.md.
"""

import datetime as dt
import re
from pathlib import Path
from typing import Any

from data_sim.catalog import HEAVY_RAIN_MM, PROMO_DAYS, PROMO_PRICE_FACTOR, PROMO_UPLIFT
from routing.config import RoutingConfig

SIM_AS_OF = dt.date(2026, 9, 30)
HISTORY_DAYS = 365
NEW_STORE_HISTORY_DAYS = 14

# The "current" online batch: orders created in [start - window, start) are routed together.
SIM_BATCH_START = dt.datetime(2026, 10, 1, 9, 0)
SIM_BATCH_WINDOW_MINUTES = 45

_ROUTING = RoutingConfig()

ASSUMPTIONS_MD_PATH = Path(__file__).resolve().parent.parent / "docs" / "data-assumptions.md"

# key -> (value, Vietnamese description)
_ENTRIES: dict[str, tuple[Any, str]] = {
    "sim_as_of": (SIM_AS_OF.isoformat(), "Ngày cuối của lịch sử bán hàng giả lập (ngày 'hôm nay' của demo)."),
    "history_days": (HISTORY_DAYS, "Số ngày lịch sử của cửa hàng đã hoạt động."),
    "new_store_history_days": (NEW_STORE_HISTORY_DAYS, "Số ngày lịch sử của cửa hàng mới (cold-start)."),
    "markdown_elasticity": (
        {
            "vegetable": -2.2,
            "tofu": -2.0,
            "seafood": -1.9,
            "meat": -1.6,
            "dairy": -1.5,
            "egg": -1.2,
            "staple": -0.8,
            "condiment": -0.6,
            "beverage": -1.1,
            "snack": -1.3,
            "household": -0.7,
        },
        "Hệ số co giãn giá theo nhóm hàng (giả định): lượng bán × (1 − mức giảm)^e, e < 0.",
    ),
    "markdown_discount_levels": (
        [0.0, 0.1, 0.2, 0.3, 0.5],
        "Các mức giảm giá được phép khi xả hàng cận hạn.",
    ),
    "hourly_sales_share": (
        {
            "residential": {"6": 0.06, "7": 0.07, "8": 0.06, "9": 0.05, "10": 0.05, "11": 0.06, "12": 0.05,
                            "13": 0.04, "14": 0.04, "15": 0.05, "16": 0.07, "17": 0.11, "18": 0.12,
                            "19": 0.09, "20": 0.05, "21": 0.03},
            "market": {"6": 0.12, "7": 0.13, "8": 0.11, "9": 0.08, "10": 0.06, "11": 0.05, "12": 0.04,
                       "13": 0.03, "14": 0.03, "15": 0.05, "16": 0.08, "17": 0.10, "18": 0.07,
                       "19": 0.03, "20": 0.01, "21": 0.01},
            "office": {"6": 0.02, "7": 0.07, "8": 0.08, "9": 0.05, "10": 0.06, "11": 0.13, "12": 0.14,
                       "13": 0.07, "14": 0.05, "15": 0.06, "16": 0.07, "17": 0.10, "18": 0.06,
                       "19": 0.02, "20": 0.01, "21": 0.01},
        },
        "Tỷ trọng doanh số theo giờ (6h–21h) theo loại khu vực, dùng để chia dự báo ngày thành khung giờ.",
    ),
    "stockout_penalty_ratio": (
        0.5,
        "Phạt mất khách khi hết hàng = tỷ lệ này × biên lợi nhuận đơn vị (cộng thêm vào biên lợi nhuận mất).",
    ),
    "transfer_cost_per_km_vnd": (
        5000,
        "Chi phí xe máy điều chuyển hàng mỗi km đường (xăng + hao mòn + công).",
    ),
    "transfer_fixed_cost_vnd": (
        20000,
        "Chi phí cố định mỗi chuyến điều chuyển (bốc xếp, thời gian nhân viên).",
    ),
    "speed_kmh": (
        _ROUTING.speed_kmh,
        "Tốc độ trung bình xe máy nội thành (km/h), khớp RoutingConfig.speed_kmh.",
    ),
    "detour_factor": (_ROUTING.detour_factor, "Hệ số đường vòng: quãng đường thực ≈ hệ số × đường chim bay."),
    "shift_minutes": (
        _ROUTING.shift_minutes,
        "Độ dài một ca giao (phút) — khung giờ tối đa của đơn trong một đợt.",
    ),
    "pickup_radius_km": (_ROUTING.pickup_radius_km, "Bán kính để đơn linh hoạt được gán điểm nhận gần đó."),
    "max_orders_per_batch": (_ROUTING.max_orders_per_batch, "Số đơn tối đa mỗi đợt định tuyến."),
    "batch_window_minutes": (
        {"min": 30, "max": 60, "simulated": SIM_BATCH_WINDOW_MINUTES},
        "Gom đơn online theo đợt 30–60 phút; dữ liệu giả lập dùng đợt 45 phút.",
    ),
    "sim_batch_start": (
        SIM_BATCH_START.isoformat(),
        "Thời điểm bắt đầu đợt giao hiện tại (mốc phút 0 của khung giờ).",
    ),
    "heavy_rain_mm": (HEAVY_RAIN_MM, "Ngưỡng mưa lớn trong ngày (mm)."),
    "promo": (
        {"days": PROMO_DAYS, "price_factor": PROMO_PRICE_FACTOR, "uplift": PROMO_UPLIFT},
        "Khuyến mãi giả lập: kéo dài 3 ngày, giá × 0,85, lượng bán × 1,45.",
    ),
    "source": (
        "GEN_PROGRAM_V1",
        "Mã nguồn của các giả định này và của các lớp dữ liệu do chương trình sinh (doanh số, giá, tồn kho, "
        "đơn online). Vị trí (OpenStreetMap), lượng mưa (Open-Meteo) và ngày lễ là dữ liệu công khai thật; "
        "danh mục nguồn: docs/data-provenance.md, `python -m provenance show`.",
    ),
}

ASSUMPTIONS: dict[str, Any] = {k: v for k, (v, _) in _ENTRIES.items()}
ASSUMPTION_DESCRIPTIONS_VI: dict[str, str] = {k: d for k, (_, d) in _ENTRIES.items()}


def assumptions_markdown(path: Path | None = None) -> str:
    """Return the text of docs/data-assumptions.md."""
    return (path or ASSUMPTIONS_MD_PATH).read_text(encoding="utf-8")


def assumptions_sections(path: Path | None = None) -> list[dict[str, str]]:
    """Split docs/data-assumptions.md into `[{"title", "body_md"}]` by `## ` headings."""
    text = assumptions_markdown(path)
    sections: list[dict[str, str]] = []
    for chunk in re.split(r"(?m)^## ", text)[1:]:
        title, _, body = chunk.partition("\n")
        sections.append({"title": title.strip(), "body_md": body.strip()})
    return sections
