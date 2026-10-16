"""Morning decision brief (``GET /api/brief``): the day's three decisions, a revenue KPI and a 7-day demand
strip, so the owner sees what to decide before asking anything (cards in ``api/brief_cards.py``).

A card whose tool fails is left out and reported in ``errors``; the rest of the brief still answers.
Results are cached per (chain, store, scope) for ``CACHE_TTL_S`` because the first build solves two PACO
batches (~30 s).
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections.abc import Callable
from typing import Any

from api.brief_cards import (
    REPLENISH_CATEGORIES,
    SURPLUS_CATEGORIES,
    delivery_card,
    replenish_card,
    surplus_card,
)
from api.errors import ApiError
from api.repo import ChainRepo, StoreInfo
from api.services import FIRST_DAY, Services
from data_sim import SIM_AS_OF

CACHE_TTL_S = 3600.0
PAST_DAYS = 4
FORECAST_DAYS = 3


def _merge_sources(parts: list[dict[str, Any]]) -> dict[str, list[str]]:
    labels: dict[str, str] = {}
    for p in parts:
        for sid, label in zip(p.get("sources", []), p.get("source_labels_vi", []), strict=False):
            labels.setdefault(sid, label)
    return {"sources": list(labels), "source_labels_vi": list(labels.values())}


def revenue_kpis(repo: ChainRepo, store_id: str | None, online_orders: int | None) -> dict[str, Any]:
    """Revenue of the last closed day (the demo day has no sales yet) vs the same weekday a week earlier."""
    last, prev = SIM_AS_OF, SIM_AS_OF - dt.timedelta(days=7)
    sql = "SELECT date, SUM(units * price) FROM daily_sales WHERE date IN (?, ?)"
    args: list[Any] = [last.isoformat(), prev.isoformat()]
    if store_id is not None:
        sql += " AND store_id = ?"
        args.append(store_id)
    with repo.read() as con:
        by_day = {d: float(v or 0) for d, v in con.execute(sql + " GROUP BY date", args)}
    rev, rev_prev = round(by_day.get(last.isoformat(), 0.0)), round(by_day.get(prev.isoformat(), 0.0))
    return {
        "revenue_date": last.isoformat(),
        "revenue_vnd": rev,
        "revenue_prev_week_vnd": rev_prev,
        "revenue_delta_pct": round(100 * (rev - rev_prev) / rev_prev, 1) if rev_prev > 0 else None,
        "online_orders_batch": online_orders,
        "scope": "store" if store_id else "chain",
        **repo.provenance(("daily_sales", "stores")),
    }


def demand_7d(services: Services, chain_id: str, store: StoreInfo) -> dict[str, Any] | None:
    """Actual sales of the store's top fresh SKU (last ``PAST_DAYS`` days) followed by its forecast."""
    repo = services.repo(chain_id)
    since = (SIM_AS_OF - dt.timedelta(days=7)).isoformat()
    with repo.read() as con:
        top = con.execute(
            "SELECT d.sku_id FROM daily_sales d JOIN skus k ON k.sku_id = d.sku_id "
            "WHERE d.store_id = ? AND k.is_fresh = 1 AND d.date > ? "
            "GROUP BY d.sku_id ORDER BY SUM(d.units) DESC, d.sku_id LIMIT 1",
            (store.store_id, since),
        ).fetchone()
        if top is None:
            return None
        start = (SIM_AS_OF - dt.timedelta(days=PAST_DAYS)).isoformat()
        actual = con.execute(
            "SELECT date, units FROM daily_sales WHERE store_id = ? AND sku_id = ? AND date > ? "
            "ORDER BY date",
            (store.store_id, top[0], start),
        ).fetchall()
    sku = repo.select_skus([top[0]], [])[0]
    fc = services.forecast(chain_id, store.store_id, [sku], horizon_days=FORECAST_DAYS)
    empty = {"p10": None, "p50": None, "p90": None}
    points = [{"date": d, "actual": u, **empty} for d, u in actual]
    for r in fc["rows"]:
        points.append({"date": r["date"], "actual": None, "p10": r["p10"], "p50": r["p50"], "p90": r["p90"]})
    return {
        "store_id": store.store_id,
        "sku_id": sku.sku_id,
        "sku_name": sku.name,
        "points": points,
        "sources": fc["sources"],
        "source_labels_vi": fc["source_labels_vi"],
    }


class BriefService:
    def __init__(
        self, services: Services, ttl_s: float = CACHE_TTL_S, clock: Callable[[], float] = time.time
    ):
        self.services = services
        self.ttl_s = ttl_s
        self.clock = clock
        self._cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
        self._locks: dict[tuple[str, str, str], threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, key: tuple[str, str, str]) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def get(self, chain_id: str, store: StoreInfo, is_owner: bool) -> dict[str, Any]:
        """One build per key at a time (concurrent callers wait for it instead of solving again)."""
        key = (chain_id, store.store_id, "chain" if is_owner else "store")
        with self._lock(key):
            hit = self._cache.get(key)
            if hit is not None and self.clock() - hit[0] < self.ttl_s:
                return {**hit[1], "cached": True}
            payload = self._build(chain_id, store, is_owner)
            self._cache[key] = (self.clock(), payload)
            return {**payload, "cached": False}

    def flows_today(self, chain_id: str) -> list[dict[str, Any]]:
        """Transfer flows of the most recent cached brief of the chain ([] before any brief was built)."""
        hits = [v for k, v in self._cache.items() if k[0] == chain_id and self.clock() - v[0] < self.ttl_s]
        return max(hits, key=lambda v: v[0])[1]["flows_today"] if hits else []

    def _build(self, chain_id: str, store: StoreInfo, is_owner: bool) -> dict[str, Any]:
        svc, repo = self.services, self.services.repo(chain_id)
        errors: list[dict[str, Any]] = []

        def run(kind: str, fn: Callable[[], Any]) -> Any:
            try:
                return fn()
            except ApiError as exc:
                errors.append({"kind": kind, "code": exc.code, "message_vi": exc.message_vi})
                return None

        store_ids = [s.store_id for s in repo.stores()] if is_owner else [store.store_id]
        replenish = run("replenish", lambda: replenish_card(
            svc, chain_id, store, repo.select_skus([], list(REPLENISH_CATEGORIES))))  # fmt: skip
        surplus = run("surplus", lambda: surplus_card(
            svc, chain_id, store_ids, repo.select_skus([], list(SURPLUS_CATEGORIES))))  # fmt: skip
        delivery = run("delivery", lambda: delivery_card(svc, chain_id, store))
        cards = [c for c in (replenish, surplus[0] if surplus else None, delivery) if c is not None]
        orders = None
        if delivery:
            orders = next((m["value"] for m in delivery["metrics"] if m["key"] == "orders"), None)
        kpis = run("kpis", lambda: revenue_kpis(repo, None if is_owner else store.store_id, orders))
        demand = run("demand_7d", lambda: demand_7d(svc, chain_id, store))
        return {
            "as_of": FIRST_DAY.isoformat(),
            "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "chain_id": chain_id,
            "store_id": store.store_id,
            "store_name": store.name,
            "scope": "chain" if is_owner else "store",
            "kpis": kpis,
            "demand_7d": demand,
            "cards": cards,
            "errors": errors,
            "flows_today": surplus[1] if surplus else [],
            **_merge_sources([*cards, *(x for x in (kpis, demand) if x)]),
        }
