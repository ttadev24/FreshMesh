import datetime as dt
import os
from pathlib import Path

import pytest

from decision.transfer import transfer_stock
from decision.types import ForecastQuantiles, SkuEconomics, StockLot
from routing.client import SolverClient
from routing.models import Store
from routing.planner import optimize_routes
from tests.routing.helpers import point_at

pytestmark = pytest.mark.integration


def _solver_url() -> str:
    url = os.environ.get("FRESHMESH_SOLVER_URL")
    if url:
        return url
    port = os.environ.get("FRESHMESH_SOLVER_PORT")
    if port:
        return f"http://localhost:{port}"
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("FRESHMESH_SOLVER_URL="):
                return line.split("=", 1)[1].strip()
    return "http://localhost:8000"


URL = _solver_url()


def test_transfer_with_real_solver():
    client = SolverClient(URL)
    assert client.health(), f"solver not reachable at {URL}; run: docker compose up -d solver"
    now = dt.datetime(2026, 10, 1, 14, 0)
    day = now.date()
    sku = SkuEconomics("RAU", "Rau muống", 20_000, 30_000, 2_000, 1, 1, 1.0)
    stores = {
        "S3": Store("S3", *point_at(0, 0)),
        "S1": Store("S1", *point_at(2, 0)),
        "S2": Store("S2", *point_at(0, 3)),
        "S4": Store("S4", *point_at(-1.5, -2)),
    }
    forecasts = [
        ForecastQuantiles("S3", "RAU", day, 30, 40, 50),
        ForecastQuantiles("S1", "RAU", day, 20, 30, 40),
        ForecastQuantiles("S2", "RAU", day, 28, 40, 55),
        ForecastQuantiles("S4", "RAU", day, 10, 15, 20),
    ]
    stock = [StockLot("S3", "RAU", 110, day), StockLot("S1", "RAU", 5, day)]
    plan = transfer_stock(
        forecasts, stock, stores, {"RAU": sku}, router=lambda b: optimize_routes(b, client), now=now
    )
    assert plan.routed and plan.recommended
    assert plan.unserved_store_ids == []
    assert {line.to_store_id for line in plan.lines} == {"S1", "S2", "S4"}
    assert plan.km > 0 and plan.vehicles >= 1
    assert plan.net_saving_vnd == plan.saved_value_vnd - plan.trip_cost_vnd
