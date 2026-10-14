"""Simulation catalogue: SKUs, chain profiles and demand effects, built from the committed AI-generated
parameter files in `data_real/generated/` (datasets AI_PARAMS_*; see `data_real.ai_params`).

Program-fixed structure (GEN_PROGRAM_V1): category taxonomy, the 30 product slots / sku_ids, chain layout,
rain thresholds and the demo surplus store. Loading fails with a Vietnamese error if a parameter file is
missing (no fallback to built-in numbers).
"""

from dataclasses import dataclass

from data_real.ai_params import CHAIN_LAYOUT, FRESH_CATEGORIES, SKU_SLOTS, ChainLayout, load_all

_PARAMS = load_all()
_CAT = _PARAMS["catalog"]["params"]
_DEM = _PARAMS["demand"]["params"]
_CHN = _PARAMS["chains"]["params"]["chains"]

CATALOG_SOURCE = "AI_PARAMS_CATALOG"


@dataclass(frozen=True)
class SkuSpec:
    sku_id: str
    name: str
    category: str
    is_fresh: bool
    shelf_life_days: int
    unit_cost: int  # VND
    unit_price: int  # VND
    salvage_price: int  # VND, what an expiring unit still recovers (staff meal / partner / supplier return)
    moq: int
    supplier_id: str
    cold_storage_units: float  # cold-room slots per unit (0 = shelf)
    category_share: float  # share of its category's units (demand_weight normalised within the category)


def _skus() -> tuple[SkuSpec, ...]:
    by_id = {s["sku_id"]: s for s in _CAT["skus"]}
    weight_sum: dict[str, float] = {}
    for sku_id, _, cat in SKU_SLOTS:
        weight_sum[cat] = weight_sum.get(cat, 0.0) + by_id[sku_id]["demand_weight"]
    out = []
    for sku_id, _, cat in SKU_SLOTS:
        s = by_id[sku_id]
        out.append(
            SkuSpec(sku_id, s["name_vi"], cat, cat in FRESH_CATEGORIES, int(s["shelf_life_days"]),
                    int(s["unit_cost_vnd"]), int(s["unit_price_vnd"]), int(s["salvage_price_vnd"]),
                    int(s["moq"]), s["supplier_id"], float(s["cold_storage_units"]),
                    s["demand_weight"] / weight_sum[cat])
        )
    return tuple(out)


SKUS: tuple[SkuSpec, ...] = _skus()

# Units/day of a whole category in one store of each area type (reference chain, plain weekday).
CATEGORY_BASE_UNITS: dict[str, dict[str, float]] = {
    c: {a: float(v[a]) for a in ("residential", "market", "office")}
    for c, v in _DEM["category_base_units"].items()
}
DOW_FACTORS: dict[str, tuple[float, ...]] = {  # Monday .. Sunday
    a: tuple(float(x) for x in v["mon_to_sun"]) for a, v in _DEM["weekday_factors"].items()
}
LIGHT_RAIN_MM = 2.0  # program thresholds (GEN_PROGRAM_V1)
HEAVY_RAIN_MM = 20.0
RAIN_FACTORS: dict[str, tuple[float, float]] = {  # (light rain, heavy rain)
    a: (float(v["light_factor"]), float(v["heavy_factor"])) for a, v in _DEM["rain_factors"].items()
}
CALENDAR_EFFECTS: dict[str, float] = {k: float(v["value"]) for k, v in _DEM["calendar"].items()}
STORE_SCALE_RANGE = (float(_DEM["store_scale"]["min"]), float(_DEM["store_scale"]["max"]))
SKU_LEVEL_SIGMA = float(_DEM["sku_level_sigma"]["value"])

# Promo: PROMO_DAYS-day promotions, price × PROMO_PRICE_FACTOR, demand × PROMO_UPLIFT.
PROMO_DAYS = int(_DEM["promo"]["duration_days"]["value"])
PROMO_PRICE_FACTOR = float(_DEM["promo"]["price_factor"]["value"])
PROMO_UPLIFT = float(_DEM["promo"]["uplift"]["value"])


@dataclass(frozen=True)
class ChainProfile:
    chain_id: str
    letter: str
    name: str
    customer_profile_vi: str
    area_types: tuple[str, ...]  # one per store, in order CH1..CHn
    new_store_index: int | None  # index into area_types of the cold-start store
    volume_scale: float
    fresh_affinity: float  # multiplier on fresh SKUs
    lunar_sensitivity: float  # scales the rằm / mùng 1 / Tết effects
    rain_sensitivity: float  # scales (1 - rain factor)
    dispersion_k: float  # NegBin shape; smaller = noisier
    promo_rate: float  # probability per SKU per day that a promo starts
    price_multiplier: float  # chain positioning vs. catalogue price
    trend_per_year: float  # growth over the history window


def _chain(layout: ChainLayout) -> ChainProfile:
    p = {k: float(v["value"]) for k, v in _CHN[layout.chain_id].items()}
    return ChainProfile(
        chain_id=layout.chain_id,
        letter=layout.letter,
        name=layout.name,
        customer_profile_vi=layout.customer_profile_vi,
        area_types=layout.area_types,
        new_store_index=layout.new_store_index,
        volume_scale=p["volume_scale"],
        fresh_affinity=p["fresh_affinity"],
        lunar_sensitivity=p["lunar_sensitivity"],
        rain_sensitivity=p["rain_sensitivity"],
        dispersion_k=p["dispersion_k"],
        promo_rate=p["promo_rate_per_day"],
        price_multiplier=p["price_multiplier"],
        trend_per_year=p["trend_per_year"],
    )


CHAINS: tuple[ChainProfile, ...] = tuple(_chain(c) for c in CHAIN_LAYOUT)

# Index of the surplus store ("nhiều rau ở CH3") in every chain; the shortage store is the
# nearest established store to it (demo scenario, GEN_PROGRAM_V1).
SURPLUS_STORE_INDEX = 2
