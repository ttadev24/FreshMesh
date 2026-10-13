"""Read access to one chain database (tenant = DB file) plus store resolution and role checks."""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.errors import ApiError
from data_sim import SOURCE, chain_db_path, open_chain_db
from decision.types import SkuEconomics, StockLot

# Vietnamese / ASCII item words → SKU categories (the agent and the CLI accept both).
CATEGORY_ALIASES: dict[str, str] = {
    "rau": "vegetable",
    "rau củ": "vegetable",
    "vegetable": "vegetable",
    "thit": "meat",
    "thịt": "meat",
    "meat": "meat",
    "ca": "seafood",
    "cá": "seafood",
    "hai_san": "seafood",
    "hải sản": "seafood",
    "seafood": "seafood",
    "trung": "egg",
    "trứng": "egg",
    "egg": "egg",
    "sua": "dairy",
    "sữa": "dairy",
    "sua_chua": "dairy",
    "dairy": "dairy",
    "dau_hu": "tofu",
    "đậu hũ": "tofu",
    "tofu": "tofu",
}
_SHORT_STORE = re.compile(r"^\s*CH\s*(\d+)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class StoreInfo:
    store_id: str
    name: str
    lat: float
    lng: float
    area_type: str
    is_new: bool
    history_days: int
    opened_date: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "store_id": self.store_id,
            "name": self.name,
            "lat": self.lat,
            "lng": self.lng,
            "area_type": self.area_type,
            "is_new": self.is_new,
            "history_days": self.history_days,
            "opened_date": self.opened_date,
            "source": SOURCE,
        }


@dataclass(frozen=True)
class SkuInfo:
    sku_id: str
    name: str
    category: str
    is_fresh: bool
    shelf_life_days: int
    unit_cost: float
    unit_price: float
    salvage_price: float
    moq: int
    supplier_id: str
    cold_storage_units: float

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "source": SOURCE}

    def economics(self, *, price: float | None = None) -> SkuEconomics:
        return SkuEconomics(
            sku_id=self.sku_id,
            name=self.name,
            unit_cost=self.unit_cost,
            unit_price=self.unit_price if price is None else price,
            salvage_price=self.salvage_price,
            shelf_life_days=self.shelf_life_days,
            moq=self.moq,
            cold_storage_units=self.cold_storage_units,
        )


class ChainRepo:
    """Read helpers for one chain DB. Every query is scoped to that tenant's file."""

    def __init__(self, data_dir: Path, chain_id: str):
        self.data_dir = Path(data_dir)
        self.chain_id = chain_id
        if not chain_db_path(self.data_dir, chain_id).exists():
            raise ApiError(
                503,
                "data_not_ready",
                "Chưa có dữ liệu giả lập cho chuỗi này; hãy chạy scripts/bootstrap.sh trước.",
            )

    @property
    def db_path(self) -> Path:
        return chain_db_path(self.data_dir, self.chain_id)

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        con = open_chain_db(self.data_dir, self.chain_id, readonly=True)
        try:
            yield con
        finally:
            con.close()

    def chain_name(self) -> str:
        with self.read() as con:
            row = con.execute("SELECT name FROM chains WHERE chain_id = ?", (self.chain_id,)).fetchone()
        return row["name"] if row else self.chain_id

    def stores(self) -> list[StoreInfo]:
        with self.read() as con:
            rows = con.execute(
                "SELECT store_id, name, lat, lng, area_type, is_new, history_days, opened_date "
                "FROM stores WHERE chain_id = ? ORDER BY store_id",
                (self.chain_id,),
            ).fetchall()
        return [
            StoreInfo(
                r["store_id"],
                r["name"],
                r["lat"],
                r["lng"],
                r["area_type"],
                bool(r["is_new"]),
                r["history_days"],
                r["opened_date"],
            )
            for r in rows
        ]

    def store(self, store_id: str) -> StoreInfo:
        for s in self.stores():
            if s.store_id == store_id:
                return s
        raise ApiError(404, "unknown_store", f"Cửa hàng '{store_id}' không thuộc chuỗi của bạn.")

    def skus(self) -> list[SkuInfo]:
        with self.read() as con:
            rows = con.execute(
                "SELECT sku_id, name, category, is_fresh, shelf_life_days, unit_cost, unit_price, "
                "salvage_price, moq, supplier_id, cold_storage_units FROM skus ORDER BY sku_id"
            ).fetchall()
        return [
            SkuInfo(
                r["sku_id"],
                r["name"],
                r["category"],
                bool(r["is_fresh"]),
                r["shelf_life_days"],
                r["unit_cost"],
                r["unit_price"],
                r["salvage_price"],
                r["moq"],
                r["supplier_id"],
                r["cold_storage_units"],
            )
            for r in rows
        ]

    def sku_map(self) -> dict[str, SkuInfo]:
        return {s.sku_id: s for s in self.skus()}

    def select_skus(
        self, sku_ids: Sequence[str] | None = None, categories: Sequence[str] | None = None
    ) -> list[SkuInfo]:
        """SKUs by id and/or category (aliases such as 'rau', 'thit'); default: every fresh SKU."""
        all_skus = self.sku_map()
        chosen: dict[str, SkuInfo] = {}
        for sku_id in sku_ids or []:
            if sku_id not in all_skus:
                raise ApiError(404, "unknown_sku", f"Mặt hàng '{sku_id}' không tồn tại.")
            chosen[sku_id] = all_skus[sku_id]
        known = {s.category for s in all_skus.values()}
        for raw in categories or []:
            cat = CATEGORY_ALIASES.get(raw.strip().lower(), raw.strip().lower())
            if cat not in known:
                raise ApiError(404, "unknown_category", f"Nhóm hàng '{raw}' không tồn tại.")
            chosen.update({s.sku_id: s for s in all_skus.values() if s.category == cat})
        if not sku_ids and not categories:
            chosen = {k: s for k, s in all_skus.items() if s.is_fresh}
        return sorted(chosen.values(), key=lambda s: s.sku_id)

    def stock(
        self, store_ids: Sequence[str] | None = None, sku_ids: Sequence[str] | None = None
    ) -> list[StockLot]:
        with self.read() as con:
            rows = con.execute("SELECT store_id, sku_id, qty, expires_on FROM inventory_lots").fetchall()
        return [
            StockLot(r["store_id"], r["sku_id"], int(r["qty"]), dt.date.fromisoformat(r["expires_on"]))
            for r in rows
            if (store_ids is None or r["store_id"] in store_ids)
            and (sku_ids is None or r["sku_id"] in sku_ids)
        ]

    def pickup_points(self, store_id: str) -> list[dict[str, Any]]:
        with self.read() as con:
            rows = con.execute(
                "SELECT pickup_point_id, name, lat, lng FROM pickup_points WHERE store_id = ? "
                "ORDER BY pickup_point_id",
                (store_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def batch_orders(self, store_id: str, created_from: str, created_to: str) -> list[dict[str, Any]]:
        with self.read() as con:
            rows = con.execute(
                "SELECT order_id, created_at, lat, lng, demand, earliest, latest, service, delivery_mode, "
                "pickup_point_id FROM online_orders "
                "WHERE store_id = ? AND created_at >= ? AND created_at < ? "
                "ORDER BY created_at, order_id",
                (store_id, created_from, created_to),
            ).fetchall()
        return [dict(r) for r in rows]


def resolve_store_id(repo: ChainRepo, raw: str | None, *, default: str | None) -> str:
    """Accept 'A-CH3', 'CH3' or 'ch 3' (resolved inside the caller's chain)."""
    value = (raw or "").strip() or (default or "")
    if not value:
        stores = repo.stores()
        if not stores:
            raise ApiError(404, "unknown_store", "Chuỗi chưa có cửa hàng nào.")
        return stores[0].store_id
    ids = {s.store_id for s in repo.stores()}
    if value in ids:
        return value
    m = _SHORT_STORE.match(value)
    if m:
        for sid in ids:
            if sid.split("-", 1)[-1].upper() == f"CH{int(m.group(1))}":
                return sid
    raise ApiError(404, "unknown_store", f"Cửa hàng '{value}' không thuộc chuỗi của bạn.")


def ensure_store_access(role: str, own_store: str | None, store_id: str) -> None:
    if role == "owner":
        return
    if store_id != own_store:
        raise ApiError(
            403,
            "forbidden_store",
            f"Tài khoản quản lý cửa hàng chỉ được thao tác trên cửa hàng {own_store}, "
            f"không được xem {store_id}.",
        )
