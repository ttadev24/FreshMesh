# ruff: noqa: E501  (one-row-per-SKU data table reads better unwrapped)
"""Static simulation catalogue: SKUs, chain profiles, area-type effects.

Every number here is a simulation assumption (documented in docs/data-assumptions.md).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SkuSpec:
    sku_id: str
    name: str
    category: str
    is_fresh: bool
    shelf_life_days: int
    unit_cost: int  # VND
    unit_price: int  # VND
    salvage_price: int  # VND, what an expiring unit still recovers (staff meal / animal feed / partner)
    moq: int
    supplier_id: str
    cold_storage_units: float  # cold-room slots per unit (0 = shelf)
    base_daily_units: float  # mean daily units in a reference residential store


# Categories (identifiers stay English; names are Vietnamese).
FRESH_CATEGORIES = ("vegetable", "meat", "seafood", "egg", "dairy", "tofu")
DRY_CATEGORIES = ("staple", "condiment", "beverage", "snack", "household")

SKUS: tuple[SkuSpec, ...] = (
    # ---- fresh (14) ----
    SkuSpec("SKU_RAU_MUONG", "Rau muống (bó 500g)", "vegetable", True, 2, 8000, 12000, 2000, 10, "SUP_RAU_DALAT", 0.5, 28),
    SkuSpec("SKU_CAI_NGOT", "Cải ngọt (bó 500g)", "vegetable", True, 2, 9000, 14000, 2000, 10, "SUP_RAU_DALAT", 0.5, 22),
    SkuSpec("SKU_XA_LACH", "Xà lách Đà Lạt (300g)", "vegetable", True, 2, 11000, 17000, 2500, 10, "SUP_RAU_DALAT", 0.5, 14),
    SkuSpec("SKU_CA_CHUA", "Cà chua (1kg)", "vegetable", True, 3, 18000, 26000, 5000, 5, "SUP_RAU_DALAT", 0.5, 16),
    SkuSpec("SKU_RAU_THOM", "Rau thơm các loại (100g)", "vegetable", True, 1, 4000, 7000, 0, 10, "SUP_RAU_DALAT", 0.2, 20),
    SkuSpec("SKU_THIT_BA_ROI", "Thịt heo ba rọi (500g)", "meat", True, 2, 68000, 89000, 25000, 5, "SUP_THIT_VISSAN", 1.0, 12),
    SkuSpec("SKU_THIT_NAC_VAI", "Thịt heo nạc vai (500g)", "meat", True, 2, 62000, 82000, 22000, 5, "SUP_THIT_VISSAN", 1.0, 10),
    SkuSpec("SKU_BO_THAN", "Thịt bò thăn (300g)", "meat", True, 2, 98000, 129000, 35000, 3, "SUP_THIT_VISSAN", 1.0, 5),
    SkuSpec("SKU_UC_GA", "Ức gà phi lê (500g)", "meat", True, 2, 45000, 62000, 15000, 5, "SUP_GA_CP", 1.0, 9),
    SkuSpec("SKU_CA_BASA", "Cá basa phi lê (500g)", "seafood", True, 1, 38000, 55000, 10000, 5, "SUP_HAISAN_MEKONG", 1.0, 8),
    SkuSpec("SKU_TOM_THE", "Tôm thẻ tươi (300g)", "seafood", True, 1, 72000, 99000, 20000, 3, "SUP_HAISAN_MEKONG", 1.0, 5),
    SkuSpec("SKU_TRUNG_GA", "Trứng gà ta (hộp 10 quả)", "egg", True, 3, 32000, 42000, 15000, 6, "SUP_TRUNG_BAHUAN", 0.3, 11),
    SkuSpec("SKU_SUA_CHUA", "Sữa chua có đường (lốc 4 hộp)", "dairy", True, 3, 21000, 28000, 6000, 12, "SUP_SUA_VNM", 0.4, 13),
    SkuSpec("SKU_DAU_HU", "Đậu hũ non (hộp 300g)", "tofu", True, 2, 7000, 11000, 1500, 10, "SUP_DAUHU_NHA", 0.4, 15),
    # ---- dry (16) ----
    SkuSpec("SKU_GAO_ST25", "Gạo ST25 (túi 5kg)", "staple", False, 365, 165000, 195000, 150000, 4, "SUP_GAO_SOCTRANG", 0.0, 3),
    SkuSpec("SKU_MI_GOI", "Mì gói tôm chua cay (gói 75g)", "staple", False, 180, 3600, 5000, 3000, 30, "SUP_TAPHOA_TONG", 0.0, 30),
    SkuSpec("SKU_NUOC_MAM", "Nước mắm cá cơm (chai 500ml)", "condiment", False, 540, 32000, 42000, 28000, 12, "SUP_TAPHOA_TONG", 0.0, 4),
    SkuSpec("SKU_DAU_AN", "Dầu ăn đậu nành (chai 1L)", "condiment", False, 365, 45000, 56000, 40000, 12, "SUP_TAPHOA_TONG", 0.0, 4),
    SkuSpec("SKU_DUONG", "Đường cát trắng (túi 1kg)", "condiment", False, 540, 22000, 28000, 20000, 10, "SUP_TAPHOA_TONG", 0.0, 3),
    SkuSpec("SKU_NUOC_TUONG", "Nước tương (chai 500ml)", "condiment", False, 365, 15000, 21000, 12000, 12, "SUP_TAPHOA_TONG", 0.0, 3),
    SkuSpec("SKU_HAT_NEM", "Hạt nêm (gói 400g)", "condiment", False, 365, 30000, 39000, 26000, 10, "SUP_TAPHOA_TONG", 0.0, 3),
    SkuSpec("SKU_SUA_TUOI", "Sữa tươi tiệt trùng (lốc 4 hộp 180ml)", "beverage", False, 180, 26000, 33000, 22000, 12, "SUP_SUA_VNM", 0.0, 14),
    SkuSpec("SKU_NUOC_SUOI", "Nước suối (chai 500ml)", "beverage", False, 365, 3500, 6000, 3000, 24, "SUP_NUOC_GIAIKHAT", 0.0, 25),
    SkuSpec("SKU_TRA_XANH", "Trà xanh đóng chai (chai 455ml)", "beverage", False, 270, 7000, 10000, 6000, 24, "SUP_NUOC_GIAIKHAT", 0.0, 15),
    SkuSpec("SKU_CA_PHE", "Cà phê hòa tan 3in1 (hộp 18 gói)", "beverage", False, 365, 42000, 54000, 38000, 10, "SUP_TAPHOA_TONG", 0.0, 3),
    SkuSpec("SKU_BANH_QUY", "Bánh quy bơ (hộp 300g)", "snack", False, 270, 38000, 49000, 33000, 10, "SUP_BANHKEO", 0.0, 3),
    SkuSpec("SKU_SNACK", "Snack khoai tây (gói 50g)", "snack", False, 180, 9000, 13000, 7000, 20, "SUP_BANHKEO", 0.0, 10),
    SkuSpec("SKU_NUOC_RUA_CHEN", "Nước rửa chén (chai 750g)", "household", False, 730, 25000, 33000, 22000, 12, "SUP_HOAPHAM", 0.0, 3),
    SkuSpec("SKU_GIAY_VS", "Giấy vệ sinh (lốc 10 cuộn)", "household", False, 730, 52000, 68000, 47000, 6, "SUP_HOAPHAM", 0.0, 3),
    SkuSpec("SKU_BOT_GIAT", "Bột giặt (túi 800g)", "household", False, 730, 33000, 43000, 30000, 10, "SUP_HOAPHAM", 0.0, 2),
)

DOW_FACTORS: dict[str, tuple[float, ...]] = {  # Monday .. Sunday
    "residential": (0.95, 0.93, 0.95, 0.97, 1.03, 1.15, 1.20),
    "market": (1.00, 0.97, 0.98, 1.00, 1.05, 1.12, 1.10),
    "office": (1.12, 1.10, 1.10, 1.12, 1.08, 0.60, 0.45),
}

AREA_VOLUME: dict[str, float] = {"residential": 1.0, "market": 1.25, "office": 0.8}

# Office stores sell relatively more drinks/snacks and less raw meat/fish.
AREA_CATEGORY_MIX: dict[str, dict[str, float]] = {
    "residential": {},
    "market": {"vegetable": 1.25, "meat": 1.2, "seafood": 1.3, "tofu": 1.2},
    "office": {"meat": 0.6, "seafood": 0.5, "vegetable": 0.7, "beverage": 1.8, "snack": 1.6, "dairy": 1.3},
}

# Heavy rain (> 20 mm) keeps walk-in customers home; markets are open-air so they suffer most.
HEAVY_RAIN_MM = 20.0
RAIN_FACTORS: dict[str, tuple[float, float]] = {  # (light rain, heavy rain)
    "residential": (0.97, 0.85),
    "market": (0.93, 0.72),
    "office": (0.96, 0.80),
}


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
    promo_rate: float  # probability per SKU per day that a 3-day promo starts
    price_multiplier: float  # chain positioning vs. catalogue price
    trend_per_year: float  # growth over the history window


CHAINS: tuple[ChainProfile, ...] = (
    ChainProfile(
        chain_id="CHAIN_A",
        letter="a",
        name="Bếp Xanh Mart",
        customer_profile_vi="Hộ gia đình khu dân cư, mua đồ tươi nấu cơm tối, cuối tuần đông",
        area_types=("residential", "residential", "market", "residential", "office", "residential"),
        new_store_index=5,
        volume_scale=1.0,
        fresh_affinity=1.15,
        lunar_sensitivity=1.0,
        rain_sensitivity=1.0,
        dispersion_k=8.0,
        promo_rate=0.020,
        price_multiplier=1.00,
        trend_per_year=0.06,
    ),
    ChainProfile(
        chain_id="CHAIN_B",
        letter="b",
        name="Tiện Lợi Phố",
        customer_profile_vi="Nhân viên văn phòng, mua nhanh giờ trưa, đồ uống và đồ ăn liền, vắng cuối tuần",
        area_types=("office", "office", "residential", "office", "market"),
        new_store_index=None,
        volume_scale=0.85,
        fresh_affinity=0.75,
        lunar_sensitivity=0.6,
        rain_sensitivity=0.8,
        dispersion_k=5.0,
        promo_rate=0.035,
        price_multiplier=1.06,
        trend_per_year=0.10,
    ),
    ChainProfile(
        chain_id="CHAIN_C",
        letter="c",
        name="Chợ Nhà",
        customer_profile_vi="Khách đi chợ truyền thống, nhạy với rằm/mùng 1 và mưa, mua sáng sớm",
        area_types=("market", "market", "residential", "market", "residential", "office", "market"),
        new_store_index=6,
        volume_scale=1.2,
        fresh_affinity=1.35,
        lunar_sensitivity=1.5,
        rain_sensitivity=1.3,
        dispersion_k=3.5,
        promo_rate=0.012,
        price_multiplier=0.95,
        trend_per_year=0.03,
    ),
)

# Index of the surplus store ("nhiều rau ở CH3") in every chain; the shortage store is the
# nearest established store to it.
SURPLUS_STORE_INDEX = 2

# Promo: 3-day promotions, price × PROMO_PRICE_FACTOR, demand × uplift.
PROMO_DAYS = 3
PROMO_PRICE_FACTOR = 0.85
PROMO_UPLIFT = 1.45
