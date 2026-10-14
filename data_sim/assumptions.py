"""Assumptions consumed by decision/ and the API.

Most are program constants (GEN_PROGRAM_V1); the markdown elasticities, the hourly sales profile and the promo
parameters come from the AI-generated parameter files (`ASSUMPTION_SOURCES` names the dataset of every key).
The same values are written to the `assumptions` table of every chain DB (column `source`) and explained in
docs/data-assumptions.md.
"""

import datetime as dt
import re
from pathlib import Path
from typing import Any

from data_real.ai_params import CATEGORIES, load_all
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

_AI = load_all()


def _elasticity() -> dict[str, float]:
    """AI point estimates rounded to 1 decimal (the precision shown in docs/data-assumptions.md)."""
    e = _AI["elasticity"]["params"]["elasticity"]
    return {c: round(float(e[c]["value"]), 1) for c in CATEGORIES}


def _hourly_share() -> dict[str, dict[str, float]]:
    """AI hourly profile 6h–21h per area type, renormalised to sum 1 and rounded to 3 decimals."""
    out: dict[str, dict[str, float]] = {}
    for area, v in _AI["orders"]["params"]["hourly_share"].items():
        shares = [float(x) for x in v["shares_6_to_21"]]
        total = sum(shares)
        out[area] = {str(h): round(x / total, 3) for h, x in zip(range(6, 22), shares, strict=True)}
    return out


# key -> (value, Vietnamese description)
_ENTRIES: dict[str, tuple[Any, str]] = {
    "sim_as_of": (SIM_AS_OF.isoformat(), "Ngày cuối của lịch sử bán hàng giả lập (ngày 'hôm nay' của demo)."),
    "history_days": (HISTORY_DAYS, "Số ngày lịch sử của cửa hàng đã hoạt động."),
    "new_store_history_days": (NEW_STORE_HISTORY_DAYS, "Số ngày lịch sử của cửa hàng mới (cold-start)."),
    "markdown_elasticity": (
        _elasticity(),
        "Hệ số co giãn giá theo nhóm hàng (do AI đề xuất, AI_PARAMS_ELASTICITY; làm tròn 1 chữ số): "
        "lượng bán × (1 − mức giảm)^e, e < 0.",
    ),
    "markdown_discount_levels": (
        [0.0, 0.1, 0.2, 0.3, 0.5],
        "Các mức giảm giá được phép khi xả hàng cận hạn.",
    ),
    "hourly_sales_share": (
        _hourly_share(),
        "Tỷ trọng doanh số/đơn theo giờ (6h–21h) theo loại khu vực (do AI đề xuất, AI_PARAMS_ORDERS), "
        "dùng để chia dự báo ngày thành khung giờ và phân bố giờ đặt đơn online.",
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
        "Khuyến mãi trong dữ liệu sinh (do AI đề xuất, AI_PARAMS_DEMAND): số ngày mỗi đợt, hệ số giá, "
        "hệ số lượng bán.",
    ),
    "source": (
        "GEN_PROGRAM_V1",
        "Mã nguồn của các giả định do chương trình cố định. Doanh số, tồn kho, đơn online mang mã "
        "GEN_FROM_AI_PARAMS_V1 (sinh bằng chương trình từ tham số do AI tạo, không phải giao dịch thật); "
        "danh mục SKU mang mã AI_PARAMS_CATALOG. Vị trí (OpenStreetMap), lượng mưa (Open-Meteo) và ngày "
        "lễ là dữ liệu công khai thật; danh mục nguồn: docs/data-provenance.md, `python -m provenance show`.",
    ),
}

ASSUMPTIONS: dict[str, Any] = {k: v for k, (v, _) in _ENTRIES.items()}
ASSUMPTION_DESCRIPTIONS_VI: dict[str, str] = {k: d for k, (_, d) in _ENTRIES.items()}
_AI_KEYS = {
    "markdown_elasticity": "AI_PARAMS_ELASTICITY",
    "hourly_sales_share": "AI_PARAMS_ORDERS",
    "promo": "AI_PARAMS_DEMAND",
}
ASSUMPTION_SOURCES: dict[str, str] = {k: _AI_KEYS.get(k, "GEN_PROGRAM_V1") for k in _ENTRIES}


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
