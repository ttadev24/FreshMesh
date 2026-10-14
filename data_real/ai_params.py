# ruff: noqa: E501  (prompt texts and data tables read better unwrapped)
"""AI-generated simulation parameters (catalog, demand, chain profiles, online orders, elasticity, stock lots).

There is no public store × SKU sales data for Vietnam, so the numbers that drive the seeded data generator are
proposed by an LLM (Claude Haiku 5.5) under a strict JSON schema, validated here, and committed to
`data_real/generated/<task>.json`. Every attempt (accepted, invalid or failed) is logged by
`provenance.llm_generate` in `data/provenance/prompts.jsonl` with the full prompt, the full response
(`data/provenance/responses/<id>.txt`), its SHA-256, token usage and the request parameters, so organizers
can inspect exactly what was asked and answered.

What the program fixes (GEN_PROGRAM_V1, not asked from the model): the category taxonomy, the 30 product slots
and their `sku_id`s (other modules and the demo reference them), the chain layout (names, store area types,
cold-start store) and the validation ranges below.

CLI: `uv run python -m data_real generate-params [--task NAME] [--force]`.
This module must not import `data_sim` (data_sim loads these files at import time).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

GENERATED_DIR = Path(__file__).resolve().parent / "generated"
DEFAULT_MODEL = "claude-haiku-5-5"
MODEL_LABEL_VI = "Claude Haiku 5.5"
MAX_ATTEMPTS = 3
EFFORT = "medium"
TEMPERATURE_NOTE = (
    "temperature không được gửi: Claude Haiku 5.5 chỉ chấp nhận giá trị mặc định 1 (giá trị khác trả lỗi 400). "
    "Tính tái lập dựa trên câu trả lời đã lưu (SHA-256), không dựa trên việc gọi lại mô hình."
)
DERIVED_ID = "GEN_FROM_AI_PARAMS_V1"

# ---------------------------------------------------------------- program-fixed structure (GEN_PROGRAM_V1)

FRESH_CATEGORIES = ("vegetable", "meat", "seafood", "egg", "dairy", "tofu")
DRY_CATEGORIES = ("staple", "condiment", "beverage", "snack", "household")
CATEGORIES = FRESH_CATEGORIES + DRY_CATEGORIES
CATEGORY_VI = {
    "vegetable": "rau củ",
    "meat": "thịt heo/bò/gà",
    "seafood": "cá, tôm",
    "egg": "trứng",
    "dairy": "sữa chua",
    "tofu": "đậu hũ",
    "staple": "gạo, mì gói",
    "condiment": "gia vị, dầu ăn",
    "beverage": "đồ uống đóng chai/hộp, cà phê hòa tan",
    "snack": "bánh kẹo, snack",
    "household": "hóa phẩm gia dụng",
}
AREA_TYPES = ("residential", "market", "office")
AREA_VI = {"residential": "khu dân cư", "market": "gần chợ truyền thống", "office": "khu văn phòng"}
SHIFT_MINUTES = 240  # routing.config.RoutingConfig.shift_minutes (checked in tests)


@dataclass(frozen=True)
class ChainLayout:
    chain_id: str
    letter: str
    name: str
    customer_profile_vi: str
    area_types: tuple[str, ...]  # one per store, CH1..CHn
    new_store_index: int | None  # cold-start store


CHAIN_LAYOUT: tuple[ChainLayout, ...] = (
    ChainLayout("CHAIN_A", "a", "Bếp Xanh Mart", "Hộ gia đình khu dân cư, mua đồ tươi nấu cơm tối, cuối tuần đông",
                ("residential", "residential", "market", "residential", "office", "residential"), 5),
    ChainLayout("CHAIN_B", "b", "Tiện Lợi Phố",
                "Nhân viên văn phòng, mua nhanh giờ trưa, đồ uống và đồ ăn liền, vắng cuối tuần",
                ("office", "office", "residential", "office", "market"), None),
    ChainLayout("CHAIN_C", "c", "Chợ Nhà", "Khách đi chợ truyền thống, nhạy với rằm/mùng 1 và mưa, mua sáng sớm",
                ("market", "market", "residential", "market", "residential", "office", "market"), 6),
)
CHAIN_IDS = tuple(c.chain_id for c in CHAIN_LAYOUT)

# (sku_id, generic product name the AI name must start with, category)
SKU_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("SKU_RAU_MUONG", "Rau muống", "vegetable"),
    ("SKU_CAI_NGOT", "Cải ngọt", "vegetable"),
    ("SKU_XA_LACH", "Xà lách", "vegetable"),
    ("SKU_CA_CHUA", "Cà chua", "vegetable"),
    ("SKU_RAU_THOM", "Rau thơm", "vegetable"),
    ("SKU_THIT_BA_ROI", "Thịt heo ba rọi", "meat"),
    ("SKU_THIT_NAC_VAI", "Thịt heo nạc vai", "meat"),
    ("SKU_BO_THAN", "Thịt bò thăn", "meat"),
    ("SKU_UC_GA", "Ức gà phi lê", "meat"),
    ("SKU_CA_BASA", "Cá basa phi lê", "seafood"),
    ("SKU_TOM_THE", "Tôm thẻ", "seafood"),
    ("SKU_TRUNG_GA", "Trứng gà", "egg"),
    ("SKU_SUA_CHUA", "Sữa chua", "dairy"),
    ("SKU_DAU_HU", "Đậu hũ non", "tofu"),
    ("SKU_GAO_ST25", "Gạo ST25", "staple"),
    ("SKU_MI_GOI", "Mì gói", "staple"),
    ("SKU_NUOC_MAM", "Nước mắm", "condiment"),
    ("SKU_DAU_AN", "Dầu ăn", "condiment"),
    ("SKU_DUONG", "Đường", "condiment"),
    ("SKU_NUOC_TUONG", "Nước tương", "condiment"),
    ("SKU_HAT_NEM", "Hạt nêm", "condiment"),
    ("SKU_SUA_TUOI", "Sữa tươi tiệt trùng", "beverage"),
    ("SKU_NUOC_SUOI", "Nước suối", "beverage"),
    ("SKU_TRA_XANH", "Trà xanh", "beverage"),
    ("SKU_CA_PHE", "Cà phê hòa tan", "beverage"),
    ("SKU_BANH_QUY", "Bánh quy", "snack"),
    ("SKU_SNACK", "Snack khoai tây", "snack"),
    ("SKU_NUOC_RUA_CHEN", "Nước rửa chén", "household"),
    ("SKU_GIAY_VS", "Giấy vệ sinh", "household"),
    ("SKU_BOT_GIAT", "Bột giặt", "household"),
)
SKU_IDS = tuple(s[0] for s in SKU_SLOTS)


class MissingParamsError(FileNotFoundError):
    """A committed parameter file is missing; message is Vietnamese and says how to regenerate it."""


class InvalidParamsError(ValueError):
    pass


# ---------------------------------------------------------------- schemas (pydantic = validator + API schema)

Confidence = Literal["low", "medium", "high"]
BASIS = "Lý do ngắn (≤ 30 từ, tiếng Việt), không URL/không trích nguồn"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Num(_M):
    value: float
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


class Span(_M):
    min: float
    max: float
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


def _by(keys: tuple[str, ...], typ: type, name: str) -> type[BaseModel]:
    return create_model(name, __base__=_M, **{k: (typ, ...) for k in keys})  # type: ignore[call-overload]


# catalog
class SkuBasis(_M):
    price: str = Field(description="Căn cứ giá vốn/giá bán/giá thu hồi")
    shelf_life: str
    moq_supplier: str
    demand_weight: str


GuessField = Literal["unit_cost_vnd", "unit_price_vnd", "salvage_price_vnd", "shelf_life_days", "moq",
                     "cold_storage_units", "demand_weight"]


class SkuParams(_M):
    sku_id: Literal[SKU_IDS]  # type: ignore[valid-type]
    name_vi: str = Field(description="Tên hiển thị, bắt đầu bằng tên sản phẩm cho sẵn, kèm quy cách trong ngoặc")
    unit_cost_vnd: int
    unit_price_vnd: int
    salvage_price_vnd: int
    shelf_life_days: int
    moq: int
    supplier_id: str = Field(description="Mã nhà cung cấp dạng SUP_<CHỮ_HOA>, không dùng thương hiệu thật")
    cold_storage_units: float
    demand_weight: float = Field(description="Độ phổ biến tương đối trong nhóm hàng (0,1–10)")
    basis_vi: SkuBasis
    confidence: Confidence
    guessed_fields: list[GuessField]


class CatalogParams(_M):
    skus: list[SkuParams]
    notes_vi: str


# demand
class CategoryBase(_M):
    residential: float
    market: float
    office: float
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


class Weekday(_M):
    mon_to_sun: list[float] = Field(description="7 hệ số, Thứ Hai → Chủ Nhật, trung bình ≈ 1")
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


class Rain(_M):
    light_factor: float = Field(description="Ngày mưa 2–20 mm")
    heavy_factor: float = Field(description="Ngày mưa ≥ 20 mm")
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


class CalendarEffects(_M):
    tet_days_1_3_drop: Num
    tet_days_1_3_floor: Num
    tet_days_4_7_factor: Num
    pre_tet_peak_meat_seafood: Num
    pre_tet_peak_other: Num
    ram_mung1_plant_uplift: Num
    ram_mung1_meat_seafood_drop: Num
    holiday_office_factor: Num
    holiday_other_factor: Num


class Promo(_M):
    duration_days: Num
    price_factor: Num
    uplift: Num


CategoryBaseAll = _by(CATEGORIES, CategoryBase, "CategoryBaseAll")
WeekdayByArea = _by(AREA_TYPES, Weekday, "WeekdayByArea")
RainByArea = _by(AREA_TYPES, Rain, "RainByArea")


class DemandParams(_M):
    category_base_units: CategoryBaseAll  # type: ignore[valid-type]
    weekday_factors: WeekdayByArea  # type: ignore[valid-type]
    rain_factors: RainByArea  # type: ignore[valid-type]
    calendar: CalendarEffects
    promo: Promo
    store_scale: Span
    sku_level_sigma: Num
    notes_vi: str


# chains
class ChainParams(_M):
    volume_scale: Num
    fresh_affinity: Num
    lunar_sensitivity: Num
    rain_sensitivity: Num
    dispersion_k: Num
    promo_rate_per_day: Num
    price_multiplier: Num
    trend_per_year: Num


ChainsAll = _by(CHAIN_IDS, ChainParams, "ChainsAll")


class ChainsParams(_M):
    chains: ChainsAll  # type: ignore[valid-type]
    notes_vi: str


# orders
class HourShare(_M):
    shares_6_to_21: list[float] = Field(description="16 tỷ trọng cho các giờ 6,7,…,21; tổng = 1")
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


class Basket(_M):
    p_1: float
    p_2: float
    p_3: float
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


class ModeMix(_M):
    home: float
    pickup: float
    flexible: float
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


HourlyByArea = _by(AREA_TYPES, HourShare, "HourlyByArea")
SpanByArea = _by(AREA_TYPES, Span, "SpanByArea")


class OrdersParams(_M):
    hourly_share: HourlyByArea  # type: ignore[valid-type]
    daily_orders: SpanByArea  # type: ignore[valid-type]
    batch_orders_45min: SpanByArea  # type: ignore[valid-type]
    basket_units: Basket
    delivery_mode_mix: ModeMix
    pickup_at_store_counter_share: Num
    earliest_start_max_minutes: Num
    window_length_minutes: Span
    service_minutes_home: Span
    service_minutes_pickup: Num
    tight_window_share: Num
    new_store_order_factor: Num
    notes_vi: str


# elasticity
class Elasticity(_M):
    value: float
    low: float
    high: float
    basis_vi: str = Field(description=BASIS)
    confidence: Confidence
    is_guess: bool


ElasticityAll = _by(CATEGORIES, Elasticity, "ElasticityAll")


class ElasticityParams(_M):
    elasticity: ElasticityAll  # type: ignore[valid-type]
    notes_vi: str


# lots
class LotsParams(_M):
    fresh_newest_lot_frac: Span
    fresh_middle_lot_frac: Span
    fresh_oldest_lot_frac: Span
    dry_lots_count: Span
    dry_lot_age_days: Span
    dry_lot_qty_days_of_sales: Span
    notes_vi: str


# ---------------------------------------------------------------- semantic checks (return Vietnamese errors)

SOURCE_RE = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|vn|org|net|gov|edu|io)\b", re.IGNORECASE)


def _strings(obj: Any, path: str = "") -> list[tuple[str, str]]:
    if isinstance(obj, str):
        return [(path, obj)]
    if isinstance(obj, dict):
        return [x for k, v in obj.items() for x in _strings(v, f"{path}.{k}" if path else k)]
    if isinstance(obj, list):
        return [x for i, v in enumerate(obj) for x in _strings(v, f"{path}[{i}]")]
    return []


def _between(errors: list[str], name: str, x: float, lo: float, hi: float) -> None:
    if not lo <= x <= hi:
        errors.append(f"{name} = {x} nằm ngoài khoảng [{lo}; {hi}]")


def _check_span(errors: list[str], name: str, s: Span, lo: float, hi: float, integer: bool = False) -> None:
    _between(errors, f"{name}.min", s.min, lo, hi)
    _between(errors, f"{name}.max", s.max, lo, hi)
    if s.min > s.max:
        errors.append(f"{name}: min ({s.min}) > max ({s.max})")
    if integer and (s.min != int(s.min) or s.max != int(s.max)):
        errors.append(f"{name}: min/max phải là số nguyên")


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def check_catalog(p: CatalogParams) -> list[str]:
    e: list[str] = []
    ids = [s.sku_id for s in p.skus]
    if sorted(ids) != sorted(SKU_IDS):
        missing = sorted(set(SKU_IDS) - set(ids))
        dup = sorted({i for i in ids if ids.count(i) > 1})
        e.append(f"phải có đúng {len(SKU_IDS)} SKU, mỗi sku_id một lần; thiếu {missing}, lặp {dup}")
    slots = {s[0]: s for s in SKU_SLOTS}
    for s in p.skus:
        _, product, category = slots[s.sku_id]
        n = s.sku_id
        if not _norm(s.name_vi).startswith(_norm(product)):
            e.append(f"{n}: name_vi phải bắt đầu bằng '{product}'")
        if not s.unit_price_vnd > s.unit_cost_vnd > s.salvage_price_vnd >= 0:
            e.append(f"{n}: cần unit_price_vnd > unit_cost_vnd > salvage_price_vnd ≥ 0")
        _between(e, f"{n}.unit_price_vnd", s.unit_price_vnd, 2_000, 600_000)
        if s.unit_price_vnd % 500:
            e.append(f"{n}: unit_price_vnd phải là bội số của 500")
        if s.unit_cost_vnd % 100 or s.salvage_price_vnd % 100:
            e.append(f"{n}: unit_cost_vnd và salvage_price_vnd phải là bội số của 100")
        margin = (s.unit_price_vnd - s.unit_cost_vnd) / s.unit_price_vnd
        _between(e, f"{n}.biên lợi nhuận gộp (giá bán − giá vốn)/giá bán", round(margin, 3), 0.12, 0.6)
        if category in FRESH_CATEGORIES:
            _between(e, f"{n}.shelf_life_days (hàng tươi)", s.shelf_life_days, 1, 3)
            _between(e, f"{n}.cold_storage_units (hàng tươi)", s.cold_storage_units, 0.1, 2.0)
        else:
            _between(e, f"{n}.shelf_life_days (hàng khô)", s.shelf_life_days, 60, 1095)
            if s.cold_storage_units != 0:
                e.append(f"{n}: hàng khô phải có cold_storage_units = 0")
        _between(e, f"{n}.moq", s.moq, 1, 200)
        if not re.fullmatch(r"SUP_[A-Z0-9_]{2,30}", s.supplier_id):
            e.append(f"{n}: supplier_id phải có dạng SUP_<CHỮ_HOA_SỐ_GẠCH_DƯỚI>")
        _between(e, f"{n}.demand_weight", s.demand_weight, 0.1, 10.0)
    return e


def weekend_ratio(values: list[float]) -> float:
    return (sum(values[5:]) / 2) / (sum(values[:5]) / 5)


def check_demand(p: DemandParams) -> list[str]:
    e: list[str] = []
    for c in CATEGORIES:
        b = getattr(p.category_base_units, c)
        for a in AREA_TYPES:
            _between(e, f"category_base_units.{c}.{a}", getattr(b, a), 0.5, 400)
    for a in AREA_TYPES:
        w = getattr(p.weekday_factors, a).mon_to_sun
        if len(w) != 7:
            e.append(f"weekday_factors.{a}: cần đúng 7 giá trị")
            continue
        for i, x in enumerate(w):
            _between(e, f"weekday_factors.{a}[{i}]", x, 0.2, 1.6)
        _between(e, f"weekday_factors.{a}: trung bình", round(sum(w) / 7, 3), 0.85, 1.15)
    for a, lo, hi in (("office", 0.2, 0.65), ("residential", 1.12, 1.6), ("market", 0.9, 1.4)):
        w = getattr(p.weekday_factors, a).mon_to_sun
        if len(w) == 7:
            _between(e, f"weekday_factors.{a}: tỷ số TB(T7,CN)/TB(T2–T6)", round(weekend_ratio(w), 3), lo, hi)
    for a in AREA_TYPES:
        r = getattr(p.rain_factors, a)
        _between(e, f"rain_factors.{a}.light_factor", r.light_factor, 0.6, 1.0)
        _between(e, f"rain_factors.{a}.heavy_factor", r.heavy_factor, 0.4, 0.97)
        if r.heavy_factor >= r.light_factor:
            e.append(f"rain_factors.{a}: heavy_factor phải nhỏ hơn light_factor")
    c = p.calendar
    for name, lo, hi in (
        ("tet_days_1_3_drop", 0.5, 0.95), ("tet_days_1_3_floor", 0.05, 0.4), ("tet_days_4_7_factor", 0.5, 1.0),
        ("pre_tet_peak_meat_seafood", 0.2, 1.5), ("pre_tet_peak_other", 0.1, 1.2),
        ("ram_mung1_plant_uplift", 0.2, 0.8), ("ram_mung1_meat_seafood_drop", 0.05, 0.4),
        ("holiday_office_factor", 0.2, 0.9), ("holiday_other_factor", 0.8, 1.4),
    ):
        _between(e, f"calendar.{name}", getattr(c, name).value, lo, hi)
    _between(e, "promo.duration_days", p.promo.duration_days.value, 2, 7)
    if p.promo.duration_days.value != int(p.promo.duration_days.value):
        e.append("promo.duration_days phải là số nguyên")
    _between(e, "promo.price_factor", p.promo.price_factor.value, 0.7, 0.95)
    _between(e, "promo.uplift", p.promo.uplift.value, 1.1, 2.5)
    _check_span(e, "store_scale", p.store_scale, 0.5, 1.6)
    _between(e, "sku_level_sigma", p.sku_level_sigma.value, 0.05, 0.4)
    return e


def check_chains(p: ChainsParams) -> list[str]:
    e: list[str] = []
    ranges = {
        "volume_scale": (0.5, 1.6), "fresh_affinity": (0.5, 1.6), "lunar_sensitivity": (0.3, 2.0),
        "rain_sensitivity": (0.3, 2.0), "dispersion_k": (2.0, 20.0), "promo_rate_per_day": (0.003, 0.06),
        "price_multiplier": (0.95, 1.12), "trend_per_year": (-0.05, 0.2),
    }
    for cid in CHAIN_IDS:
        ch = getattr(p.chains, cid)
        for f, (lo, hi) in ranges.items():
            _between(e, f"chains.{cid}.{f}", getattr(ch, f).value, lo, hi)
    fa = {cid: getattr(p.chains, cid).fresh_affinity.value for cid in CHAIN_IDS}
    if not fa["CHAIN_C"] > fa["CHAIN_A"] > fa["CHAIN_B"]:
        e.append("fresh_affinity phải theo thứ tự CHAIN_C > CHAIN_A > CHAIN_B (theo mô tả tệp khách)")
    lunar = {cid: getattr(p.chains, cid).lunar_sensitivity.value for cid in CHAIN_IDS}
    if not lunar["CHAIN_C"] >= 1.2:
        e.append("chains.CHAIN_C.lunar_sensitivity phải ≥ 1,2 (khách chợ truyền thống nhạy rằm/mùng 1)")
    return e


def check_orders(p: OrdersParams) -> list[str]:
    e: list[str] = []
    for a in AREA_TYPES:
        h = getattr(p.hourly_share, a).shares_6_to_21
        if len(h) != 16:
            e.append(f"hourly_share.{a}: cần đúng 16 giá trị (giờ 6–21)")
            continue
        if any(x < 0.002 or x > 0.25 for x in h):
            e.append(f"hourly_share.{a}: mỗi tỷ trọng phải trong [0,002; 0,25]")
        _between(e, f"hourly_share.{a}: tổng", round(sum(h), 3), 0.97, 1.03)
        _check_span(e, f"daily_orders.{a}", getattr(p.daily_orders, a), 10, 300, integer=True)
        _check_span(e, f"batch_orders_45min.{a}", getattr(p.batch_orders_45min, a), 12, 40, integer=True)
    b = p.basket_units
    _between(e, "basket_units: tổng p_1+p_2+p_3", round(b.p_1 + b.p_2 + b.p_3, 3), 0.99, 1.01)
    for f in ("p_1", "p_2", "p_3"):
        _between(e, f"basket_units.{f}", getattr(b, f), 0.02, 0.95)
    m = p.delivery_mode_mix
    _between(e, "delivery_mode_mix: tổng", round(m.home + m.pickup + m.flexible, 3), 0.99, 1.01)
    for f in ("home", "pickup", "flexible"):
        _between(e, f"delivery_mode_mix.{f}", getattr(m, f), 0.05, 0.9)
    _between(e, "pickup_at_store_counter_share", p.pickup_at_store_counter_share.value, 0.0, 1.0)
    em = p.earliest_start_max_minutes.value
    _between(e, "earliest_start_max_minutes", em, 0, 150)
    if em % 15:
        e.append("earliest_start_max_minutes phải là bội số của 15")
    _check_span(e, "window_length_minutes", p.window_length_minutes, 30, 120, integer=True)
    if em + p.window_length_minutes.max > SHIFT_MINUTES:
        e.append(f"earliest_start_max_minutes + window_length_minutes.max phải ≤ {SHIFT_MINUTES} (ca giao)")
    _check_span(e, "service_minutes_home", p.service_minutes_home, 1, 15, integer=True)
    _between(e, "service_minutes_pickup", p.service_minutes_pickup.value, 1, 10)
    if p.service_minutes_pickup.value != int(p.service_minutes_pickup.value):
        e.append("service_minutes_pickup phải là số nguyên")
    _between(e, "tight_window_share", p.tight_window_share.value, 0.005, 0.1)
    _between(e, "new_store_order_factor", p.new_store_order_factor.value, 0.2, 1.0)
    return e


def check_elasticity(p: ElasticityParams) -> list[str]:
    e: list[str] = []
    for c in CATEGORIES:
        x = getattr(p.elasticity, c)
        _between(e, f"elasticity.{c}.value", x.value, -4.0, -0.2)
        if not -4.0 <= x.low <= x.value <= x.high < 0:
            e.append(f"elasticity.{c}: cần −4 ≤ low ≤ value ≤ high < 0")
    fresh = sum(getattr(p.elasticity, c).value for c in FRESH_CATEGORIES) / len(FRESH_CATEGORIES)
    dry = sum(getattr(p.elasticity, c).value for c in DRY_CATEGORIES) / len(DRY_CATEGORIES)
    if not fresh < dry:
        e.append("hàng tươi (cận hạn) phải co giãn mạnh hơn hàng khô: trung bình value nhóm tươi < nhóm khô")
    return e


def check_lots(p: LotsParams) -> list[str]:
    e: list[str] = []
    _check_span(e, "fresh_newest_lot_frac", p.fresh_newest_lot_frac, 0.2, 2.0)
    _check_span(e, "fresh_middle_lot_frac", p.fresh_middle_lot_frac, 0.05, 1.5)
    _check_span(e, "fresh_oldest_lot_frac", p.fresh_oldest_lot_frac, 0.05, 1.0)
    if p.fresh_oldest_lot_frac.max > p.fresh_newest_lot_frac.max:
        e.append("fresh_oldest_lot_frac.max phải ≤ fresh_newest_lot_frac.max")
    _check_span(e, "dry_lots_count", p.dry_lots_count, 1, 4, integer=True)
    _check_span(e, "dry_lot_age_days", p.dry_lot_age_days, 0, 59, integer=True)
    _check_span(e, "dry_lot_qty_days_of_sales", p.dry_lot_qty_days_of_sales, 1, 30)
    return e


# ---------------------------------------------------------------- prompts

SYSTEM_VI = (
    "Bạn là chuyên gia vận hành bán lẻ hàng tiêu dùng nhanh tại TP.HCM. Nhiệm vụ: đề xuất THAM SỐ cho một mô phỏng "
    "dữ liệu (không phải dữ liệu thật) của phần mềm FreshMesh. Bạn không truy cập Internet; mọi con số là ước lượng "
    "theo hiểu biết chung. Trả lời bằng đúng một đối tượng JSON theo schema, không thêm chữ nào khác."
)

_CHAIN_LINES = "\n".join(
    f"- {c.chain_id} \"{c.name}\" (tên hư cấu): {c.customer_profile_vi}; {len(c.area_types)} cửa hàng: "
    + ", ".join(f"{AREA_VI[a]}" for a in c.area_types)
    + (f"; cửa hàng CH{c.new_store_index + 1} mới mở 14 ngày" if c.new_store_index is not None else "")
    for c in CHAIN_LAYOUT
)

CONTEXT_VI = f"""BỐI CẢNH
FreshMesh phục vụ các chuỗi mini-mart nhỏ (60–150 m²) ở nội thành TP.HCM, năm 2026. Mỗi cửa hàng bán hàng tươi
(rau, thịt, cá/tôm, trứng, sữa chua, đậu hũ) và hàng khô/tạp hóa; có đơn online giao bằng xe máy trong bán kính ~3 km,
gom theo đợt 45 phút, ca giao dài {SHIFT_MINUTES} phút. Ba chuỗi:
{_CHAIN_LINES}
Loại khu vực (area type): residential = {AREA_VI['residential']}; market = {AREA_VI['market']}; office = {AREA_VI['office']}.
Nhóm hàng (category, cố định): {', '.join(f'{c} ({CATEGORY_VI[c]})' for c in CATEGORIES)}.
Hàng tươi: {', '.join(FRESH_CATEGORIES)}. Hàng khô: {', '.join(DRY_CATEGORIES)}.
"""

RULES_VI = """QUY TẮC BẮT BUỘC
1. Chỉ trả về một đối tượng JSON đúng schema (schema được hệ thống áp dụng).
2. Mỗi tham số có basis_vi: lý do ngắn (≤ 30 từ, tiếng Việt) theo hiểu biết chung về bán lẻ TP.HCM;
   confidence: low | medium | high; is_guess = true nếu đó là phỏng đoán, không có căn cứ chắc chắn.
3. KHÔNG bịa nguồn: không ghi URL, tên miền, tên báo cáo/khảo sát/tổ chức nghiên cứu, không nêu số thống kê cụ thể
   như thể đã tra cứu. Nếu không chắc, hãy nói rõ là ước lượng/phỏng đoán.
4. Không dùng tên thương hiệu thật (sản phẩm, nhà cung cấp, chuỗi bán lẻ).
5. Mọi giá trị phải nằm trong khoảng hợp lệ ghi dưới đây; giá trị ngoài khoảng sẽ bị từ chối và phải làm lại.
6. notes_vi: 2–4 câu nêu giới hạn của các ước lượng và những giá trị nào là phỏng đoán nhiều nhất.
"""

_SLOT_LINES = "\n".join(
    f"- {sid}: {product} [{cat}, {'tươi' if cat in FRESH_CATEGORIES else 'khô'}]" for sid, product, cat in SKU_SLOTS
)

CATALOG_VI = f"""NHIỆM VỤ: danh mục 30 SKU dùng chung cho cả 3 chuỗi (giá niêm yết tham chiếu, chuỗi sẽ nhân hệ số riêng).
Danh sách mặt hàng (sku_id cố định, tên sản phẩm cố định):
{_SLOT_LINES}

Với MỖI sku_id ở trên, trả về đúng một phần tử trong "skus":
- name_vi: bắt đầu bằng đúng tên sản phẩm cho sẵn, rồi quy cách đóng gói thường gặp trong ngoặc, ví dụ "Rau muống (bó 500g)".
- unit_price_vnd: giá bán lẻ một đơn vị tại mini-mart TP.HCM năm 2026 (VND, bội số của 500, 2.000–600.000).
- unit_cost_vnd: giá nhập (bội số của 100); biên lợi nhuận gộp (giá bán − giá vốn)/giá bán trong 12%–60%.
- salvage_price_vnd: số tiền một đơn vị còn thu hồi được khi hết hạn bán (bán thanh lý cho đối tác, suất ăn nhân viên,
  trả nhà cung cấp; hàng khô thường thu hồi gần giá vốn, rau lá có thể ≈ 0); bội số của 100;
  bắt buộc unit_price_vnd > unit_cost_vnd > salvage_price_vnd ≥ 0.
- shelf_life_days: số ngày được bày bán theo chính sách hàng tươi của chuỗi; hàng tươi 1–3 ngày (số nguyên);
  hàng khô 60–1095 ngày.
- moq: số lượng đặt tối thiểu mỗi lần theo quy cách thùng/lốc của nhà cung cấp (1–200).
- supplier_id: mã nhà cung cấp hư cấu dạng SUP_RAU_DALAT, SUP_THIT, SUP_HAISAN, SUP_TAPHOA… (chỉ chữ in hoa, số, "_").
- cold_storage_units: số "ô kho lạnh" một đơn vị chiếm (hàng tươi 0,1–2,0; hàng khô bằng 0).
- demand_weight: độ phổ biến tương đối của SKU trong nhóm hàng của nó (0,1–10; chương trình chuẩn hóa trong nhóm).
- basis_vi: căn cứ cho giá, hạn bán, MOQ/nhà cung cấp, độ phổ biến; confidence; guessed_fields: các trường là phỏng đoán.
"""

DEMAND_VI = """NHIỆM VỤ: tham số nhu cầu bán tại quầy theo ngày cho mô phỏng (đơn vị = đơn vị bán của SKU).
Mô hình: lượng bán ngày ~ NegBin(trung bình μ), μ = nền nhóm hàng × tỷ trọng SKU trong nhóm × hệ số thứ × hệ số lịch
âm/lễ × hệ số mưa × khuyến mãi × xu hướng × hệ số chuỗi. Trả về:
- category_base_units.<category>.{residential, market, office}: tổng số đơn vị/ngày của CẢ nhóm hàng tại MỘT cửa hàng
  điển hình ở loại khu vực đó (chuỗi tham chiếu, ngày thường, không mưa, không khuyến mãi); 0,5–400.
  Gợi ý: cửa hàng văn phòng bán ít thịt/cá sống hơn, nhiều đồ uống/snack hơn; gần chợ bán nhiều đồ tươi hơn.
- weekday_factors.<area>.mon_to_sun: 7 hệ số Thứ Hai→Chủ Nhật (0,2–1,6; trung bình 0,85–1,15). Ràng buộc kiểm tra:
  tỷ số TB(T7,CN)/TB(T2–T6) — office 0,2–0,65 (văn phòng vắng cuối tuần); residential 1,12–1,6; market 0,9–1,4.
- rain_factors.<area>: light_factor (mưa 2–20 mm, 0,6–1,0) và heavy_factor (mưa ≥ 20 mm, 0,4–0,97), heavy < light.
- calendar (mỗi mục là {value, basis_vi, confidence, is_guess}); s là độ nhạy lịch âm của chuỗi (khoảng 0,3–2):
  - tet_days_1_3_drop (0,5–0,95): mùng 1–3 Tết, hệ số = max(tet_days_1_3_floor, 1 − drop × s).
  - tet_days_1_3_floor (0,05–0,4); tet_days_4_7_factor (0,5–1,0): mùng 4–7.
  - pre_tet_peak_meat_seafood (0,2–1,5) và pre_tet_peak_other (0,1–1,2): 10 ngày trước Tết tăng dần tới × (1 + peak × s).
  - ram_mung1_plant_uplift (0,2–0,8): rằm/mùng 1 âm lịch, rau và đậu hũ × (1 + uplift × s) do ăn chay.
  - ram_mung1_meat_seafood_drop (0,05–0,4): rằm/mùng 1, thịt/hải sản × (1 − drop × s).
  - holiday_office_factor (0,2–0,9) và holiday_other_factor (0,8–1,4): ngày nghỉ lễ chính thức (ngoài Tết).
- promo: duration_days (số nguyên 2–7), price_factor (giá khuyến mãi = giá × hệ số, 0,7–0,95), uplift (lượng bán × hệ số, 1,1–2,5).
- store_scale {min, max}: khoảng hệ số quy mô riêng của từng cửa hàng (0,5–1,6), rút đều ngẫu nhiên.
- sku_level_sigma (0,05–0,4): độ lệch chuẩn log của mức nền riêng từng cửa hàng–SKU.
"""

CHAINS_VI = """NHIỆM VỤ: hồ sơ hành vi của 3 chuỗi (khác biệt giữa chuỗi phục vụ thí nghiệm học liên kết non-IID).
Với mỗi chuỗi trong chains.{CHAIN_A, CHAIN_B, CHAIN_C}, mỗi tham số là {value, basis_vi, confidence, is_guess}:
- volume_scale (0,5–1,6): quy mô lượng bán so với chuỗi tham chiếu 1,0.
- fresh_affinity (0,5–1,6): hệ số nhân với lượng bán hàng tươi; phải theo thứ tự CHAIN_C > CHAIN_A > CHAIN_B.
- lunar_sensitivity (0,3–2,0): độ nhạy với Tết/rằm/mùng 1 (s); CHAIN_C ≥ 1,2.
- rain_sensitivity (0,3–2,0): nhân mức giảm do mưa.
- dispersion_k (2–20): tham số hình dạng Negative Binomial (nhỏ = nhiễu nhiều; khách vãng lai, đơn lẻ → nhiễu hơn).
- promo_rate_per_day (0,003–0,06): xác suất mỗi ngày một SKU bắt đầu một đợt khuyến mãi.
- price_multiplier (0,95–1,12): giá niêm yết của chuỗi so với giá tham chiếu (tiện lợi cao hơn, giá chợ thấp hơn).
- trend_per_year (−0,05–0,2): tăng trưởng lượng bán mỗi năm.
"""

ORDERS_VI = f"""NHIỆM VỤ: hành vi đơn hàng online (đặt qua app/Zalo, giao xe máy hoặc nhận tại điểm nhận).
- hourly_share.<area>.shares_6_to_21: 16 tỷ trọng đơn/doanh số theo giờ 6h,7h,…,21h (mỗi giá trị 0,002–0,25; tổng = 1).
  Dùng chung để chia doanh số ngày theo giờ.
- daily_orders.<area> {{min, max}}: số đơn online/ngày của một cửa hàng (số nguyên, 10–300).
- batch_orders_45min.<area> {{min, max}}: số đơn trong đợt gom 45 phút buổi sáng 8:15–9:00 (số nguyên, 12–40).
- basket_units: xác suất đơn cần 1, 2, 3 "đơn vị tải" (túi/thùng trên xe máy): p_1 + p_2 + p_3 = 1.
- delivery_mode_mix: tỷ lệ giao tận nhà (home), nhận tại điểm nhận (pickup), linh hoạt — giao nhà hoặc điểm nhận
  gần (flexible); mỗi giá trị 0,05–0,9, tổng = 1.
- pickup_at_store_counter_share (0–1): trong đơn pickup, tỷ lệ nhận tại quầy cửa hàng (còn lại ở sảnh chung cư).
- earliest_start_max_minutes (0–150, bội số của 15): thời điểm sớm nhất khách muốn nhận, tính từ đầu đợt.
- window_length_minutes {{min, max}} (số nguyên 30–120): độ dài khung giờ nhận; earliest_start_max + max ≤ {SHIFT_MINUTES}.
- service_minutes_home {{min, max}} (số nguyên 1–15): thời gian giao tận tay; service_minutes_pickup (số nguyên 1–10).
- tight_window_share (0,005–0,1): tỷ lệ đơn "gấp" ở xa yêu cầu khung giờ quá hẹp để kịp giao.
- new_store_order_factor (0,2–1,0): số đơn của cửa hàng mới mở so với cửa hàng đã ổn định.
"""

ELASTICITY_VI = """NHIỆM VỤ: hệ số co giãn giá khi GIẢM GIÁ HÀNG CẬN HẠN (markdown) theo nhóm hàng.
Mô hình: lượng bán sau giảm = lượng bán gốc × (1 − mức giảm)^e, e < 0 (mức giảm 10–50%, chỉ trong ngày).
Với mỗi category trong elasticity.<category>: value (ước lượng điểm, −4 ≤ value ≤ −0,2), low và high (khoảng hợp lý,
low ≤ value ≤ high < 0), basis_vi, confidence, is_guess. Hàng tươi cận hạn thường co giãn mạnh hơn hàng khô
(trung bình nhóm tươi phải âm hơn nhóm khô).
"""

LOTS_VI = """NHIỆM VỤ: cơ cấu tồn kho theo lô cuối ngày (sau giờ đóng cửa) tại mini-mart, tính theo m = lượng bán trung bình/ngày
của cửa hàng–SKU. Mỗi mục là {min, max, basis_vi, confidence, is_guess}; chương trình rút đều trong [min, max].
- Hàng tươi hạn L ngày có một lô cho mỗi ngày nhập trong L ngày gần nhất:
  fresh_newest_lot_frac (0,2–2,0): lô nhập hôm nay còn lại bao nhiêu × m;
  fresh_middle_lot_frac (0,05–1,5): lô giữa; fresh_oldest_lot_frac (0,05–1,0, max không lớn hơn max của lô mới nhất):
  lô cũ nhất, hết hạn bán ngày mai.
- Hàng khô: dry_lots_count (số nguyên 1–4 lô), dry_lot_age_days (số nguyên 0–59, tuổi lô tính từ ngày nhập),
  dry_lot_qty_days_of_sales (1–30): mỗi lô bằng bao nhiêu ngày bán (× m).
"""


@dataclass(frozen=True)
class TaskSpec:
    name: str
    dataset_id: str
    title_vi: str
    model: type[BaseModel]
    check: Callable[[Any], list[str]]
    body_vi: str
    max_tokens: int

    def prompt(self) -> str:
        return f"{CONTEXT_VI}\n{RULES_VI}\n{self.body_vi}"


TASKS: dict[str, TaskSpec] = {
    t.name: t
    for t in (
        TaskSpec("catalog", "AI_PARAMS_CATALOG", "Danh mục SKU, giá, hạn bán, MOQ", CatalogParams, check_catalog,
                 CATALOG_VI, 48000),
        TaskSpec("demand", "AI_PARAMS_DEMAND", "Mức nhu cầu nền theo nhóm hàng và hệ số thứ/lịch âm/lễ/mưa/khuyến mãi",
                 DemandParams, check_demand, DEMAND_VI, 32000),
        TaskSpec("chains", "AI_PARAMS_CHAINS", "Hồ sơ hành vi 3 chuỗi (quy mô, độ ưa hàng tươi, độ nhạy, nhiễu)",
                 ChainsParams, check_chains, CHAINS_VI, 24000),
        TaskSpec("orders", "AI_PARAMS_ORDERS", "Hành vi đơn online (theo giờ, số đơn, giỏ, hình thức nhận, khung giờ)",
                 OrdersParams, check_orders, ORDERS_VI, 24000),
        TaskSpec("elasticity", "AI_PARAMS_ELASTICITY", "Hệ số co giãn giá khi giảm giá cận hạn theo nhóm hàng",
                 ElasticityParams, check_elasticity, ELASTICITY_VI, 16000),
        TaskSpec("lots", "AI_PARAMS_LOTS", "Cơ cấu tuổi lô tồn kho cuối ngày", LotsParams, check_lots, LOTS_VI, 16000),
    )
}

# ---------------------------------------------------------------- API schema + validation

_DROP_KEYS = {"title", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
              "minItems", "maxItems", "default", "pattern"}


def _clean(node: Any) -> Any:
    if isinstance(node, dict):
        out = {k: _clean(v) for k, v in node.items() if k not in _DROP_KEYS}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out
    if isinstance(node, list):
        return [_clean(v) for v in node]
    return node


def api_schema(task: str) -> dict[str, Any]:
    """JSON schema sent as `output_config.format` (numeric ranges are checked locally, not by the API)."""
    return _clean(TASKS[task].model.model_json_schema())


def request_params(task: str) -> dict[str, Any]:
    return {
        "max_tokens": TASKS[task].max_tokens,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": api_schema(task)}},
    }


def validate(task: str, data: Any) -> list[str]:
    """Vietnamese error list (empty = valid) for a parsed response of `task`."""
    spec = TASKS[task]
    try:
        model = spec.model.model_validate(data)
    except ValidationError as exc:
        return [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in exc.errors()[:30]]
    errors = spec.check(model)
    for path, text in _strings(data):
        if SOURCE_RE.search(text):
            errors.append(f"{path}: không được ghi URL/tên miền/nguồn trích dẫn")
    return errors


def validate_text(task: str, text: str) -> str | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return f"Không phải JSON hợp lệ: {exc}"
    errors = validate(task, data)
    if not errors:
        return None
    shown = errors[:25]
    more = f"\n… và {len(errors) - len(shown)} lỗi khác" if len(errors) > len(shown) else ""
    return "\n".join(f"- {x}" for x in shown) + more


def retry_prompt(base: str, error: str) -> str:
    return (
        f"{base}\nLẦN TRẢ LỜI TRƯỚC BỊ TỪ CHỐI vì các lỗi sau:\n{error}\n"
        "Hãy trả lời lại TOÀN BỘ đối tượng JSON, sửa các lỗi trên và vẫn tuân thủ mọi quy tắc."
    )


# ---------------------------------------------------------------- generation

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def param_path(task: str, gen_dir: Path | None = None) -> Path:
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; one of {sorted(TASKS)}")
    return (gen_dir or GENERATED_DIR) / f"{task}.json"


def generate(
    task: str,
    *,
    data_dir: Path | str = Path("data"),
    gen_dir: Path | None = None,
    llm: Any = None,
    model: str | None = None,
    force: bool = False,
    max_attempts: int = MAX_ATTEMPTS,
) -> Path:
    """Generate one parameter file. Every attempt is logged; on an invalid answer the validation errors are
    appended to the prompt and the model is asked again (up to `max_attempts`). `llm` is injectable (tests)."""
    from provenance.prompts import MSG_NO_KEY_VI, LLMGenerationError, llm_generate

    spec = TASKS[task]
    out = param_path(task, gen_dir)
    if out.exists() and not force:
        return out
    base = spec.prompt()
    prompt = base
    attempts: list[dict[str, Any]] = []
    try:
        rel_out = out.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        rel_out = out.as_posix()
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            gen = llm_generate(
                prompt, f"ai_params:{task}", spec.dataset_id, model or DEFAULT_MODEL, system=SYSTEM_VI,
                data_dir=data_dir, llm=llm, params=request_params(task), task=task, attempt=attempt,
                validate=lambda text: validate_text(task, text), parsed_path=rel_out,
            )
        except LLMGenerationError as exc:
            if exc.message_vi == MSG_NO_KEY_VI or getattr(exc, "record", None) is None:
                raise
            attempts.append(exc.record)  # type: ignore[attr-defined]
            last_error = exc.message_vi
            continue
        attempts.append(gen.record)
        if gen.accepted:
            _write_param_file(out, task, gen.record, gen.text or "", attempts, data_dir)
            return out
        last_error = gen.record["error"] or ""
        prompt = retry_prompt(base, last_error)
    raise LLMGenerationError(
        f"Sinh tham số '{task}' thất bại sau {max_attempts} lần (mọi lần đều đã ghi nhật ký): {last_error[:500]}"
    )


def _write_param_file(out: Path, task: str, rec: dict[str, Any], text: str, attempts: list[dict[str, Any]],
                      data_dir: Path | str) -> None:
    spec = TASKS[task]
    params = rec["parameters"]
    schema = params["output_config"]["format"]["schema"]
    header = {
        "task": task,
        "dataset_id": spec.dataset_id,
        "title_vi": spec.title_vi,
        "model": rec["model"],
        "generated_at": rec["ts"],
        "prompt_id": rec["id"],
        "attempt_prompt_ids": [a["id"] for a in attempts],
        "attempt_statuses": [a["status"] for a in attempts],
        "prompt_sha256": rec["prompt_sha256"],
        "response_sha256": rec["response_sha256"],
        "response_path": (Path(data_dir) / rec["response_path"]).as_posix(),
        "prompt_log": (Path(data_dir) / "provenance" / "prompts.jsonl").as_posix(),
        "request": {k: v for k, v in params.items() if k != "output_config"}
        | {"output_config": {"effort": params["output_config"].get("effort"), "format": "json_schema"}},
        "schema_sha256": _sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False)),
        "temperature_note_vi": TEMPERATURE_NOTE,
        "usage": rec["usage"],
        "note_vi": (
            f"Tham số do AI ({MODEL_LABEL_VI}) đề xuất theo hiểu biết chung; là ước lượng hợp lý, KHÔNG phải số đo "
            "hay giao dịch thật. Mỗi số có basis_vi/confidence/is_guess. Không chỉnh tay: 'params' phải bằng đúng "
            "câu trả lời đã lưu (kiểm tra bằng response_sha256)."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    body = {"header": header, "params": json.loads(text)}
    out.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- loading (used by data_sim)

def _missing_msg(task: str, path: Path) -> str:
    return (
        f"Thiếu tệp tham số do AI sinh: {path}. Hãy chạy `uv run python -m data_real generate-params --task {task}` "
        "(cần ANTHROPIC_API_KEY) rồi dựng lại dữ liệu; chương trình không dùng số mặc định thay thế."
    )


def load_file(task: str, gen_dir: Path | None = None) -> dict[str, Any]:
    """`{"header", "params"}` of one committed file; re-validated (a hand-edited invalid file is rejected)."""
    path = param_path(task, gen_dir)
    if not path.exists():
        raise MissingParamsError(_missing_msg(task, path))
    body = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(task, body.get("params"))
    if errors:
        raise InvalidParamsError(f"Tệp {path} không hợp lệ: " + "; ".join(errors[:10]))
    return body


@cache
def _load_all_cached(gen_dir: str) -> dict[str, dict[str, Any]]:
    return {t: load_file(t, Path(gen_dir)) for t in TASKS}


def load_all(gen_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """{task: {"header", "params"}} for every task; raises MissingParamsError (Vietnamese) if one is missing."""
    return _load_all_cached(str((gen_dir or GENERATED_DIR).resolve()))


def registry_updates(gen_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Registry fields for the AI_PARAMS_* datasets and the derived GEN_FROM_AI_PARAMS_V1 (prompt ids, dates)."""
    files = load_all(gen_dir)
    out: dict[str, dict[str, Any]] = {}
    union: list[str] = []
    for task, body in files.items():
        h = body["header"]
        out[h["dataset_id"]] = {
            "retrieved_at": h["generated_at"],
            "prompt_ids": list(h["attempt_prompt_ids"]),
            "details": {
                "file": f"data_real/generated/{task}.json",
                "model": h["model"],
                "accepted_prompt_id": h["prompt_id"],
                "response_sha256": h["response_sha256"],
                "request": h["request"],
                "temperature_note_vi": h["temperature_note_vi"],
            },
        }
        union += [p for p in h["attempt_prompt_ids"] if p not in union]
    parents = sorted(out)
    out[DERIVED_ID] = {
        "prompt_ids": union,
        "details": {"parents": parents + ["GEN_PROGRAM_V1", "OSM_HCMC", "WEATHER_OPENMETEO_ARCHIVE", "CALENDAR_VN"]},
    }
    return out
