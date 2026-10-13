"""MED-6: internal (English) exception text must not reach users; it is logged instead."""

from __future__ import annotations

import logging

import pytest

import api.services as services_mod
from api.errors import ApiError
from api.routing_service import RoutingService
from api.services import Services

RAW = "internal english detail xyz"


def _boom(*_a, **_k):
    raise ValueError(RAW)


@pytest.fixture()
def svc(data_dir, fake_solver, tmp_path) -> Services:
    return Services(data_dir, RoutingService(tmp_path, fake_solver))


@pytest.mark.parametrize(
    "target,call",
    [
        ("forecast_demand", lambda s, veg: s.forecast("CHAIN_A", "A-CH1", veg)),
        ("plan_inventory", lambda s, veg: s.inventory_plan("CHAIN_A", "A-CH1", veg)),
        ("transfer_stock", lambda s, veg: s.transfer("CHAIN_A", "A-CH3", veg)),
    ],
)
def test_value_errors_are_vietnamese_and_logged(svc, monkeypatch, caplog, target, call):
    monkeypatch.setattr(services_mod, target, _boom)
    veg = svc.repo("CHAIN_A").select_skus(None, ["vegetable"])
    with caplog.at_level(logging.WARNING, logger="api.services"), pytest.raises(ApiError) as exc:
        call(svc, veg)
    assert exc.value.status == 422
    assert RAW not in exc.value.message_vi
    assert RAW in caplog.text


def test_missing_model_is_503_and_never_trained_in_request(data_dir, fake_solver, tmp_path, caplog):
    """MED-7: the API does not train inside a request; startup tells the operator to run bootstrap."""
    import shutil

    from fastapi.testclient import TestClient

    from api.main import create_app
    from tests.api.conftest import assert_error, login, make_settings

    copy = tmp_path / "data"
    shutil.copytree(data_dir, copy, ignore=shutil.ignore_patterns("cache"))
    for f in (copy / "models").glob("CHAIN_B.*"):
        f.unlink()
    app = create_app(make_settings(copy, tmp_path / "cache"), solver=fake_solver)
    with caplog.at_level(logging.WARNING, logger="freshmesh.api"), TestClient(app) as c:
        assert "CHAIN_B" in caplog.text and "scripts/bootstrap.sh" in caplog.text
        headers = login(c, "owner_b")
        err = assert_error(c.get("/api/forecast?store_id=CH1", headers=headers), 503, "model_not_ready")
        assert "bootstrap" in err["message_vi"]
        assert c.get("/api/forecast?store_id=CH1", headers=login(c, "owner_a")).status_code == 200
    assert not (copy / "models" / "CHAIN_B.npz").exists()
