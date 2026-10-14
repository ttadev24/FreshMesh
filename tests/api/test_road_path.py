"""Road geometry of the route map: VietMap client (HTTP faked, no network) and its use by /api/routing/plan."""

from __future__ import annotations

import logging
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.road_path import COOLDOWN_S, RoadPath, RoadRouter
from tests.api.conftest import login, make_settings

KEY = "secret-route-key-0123"
POINTS = [[10.80, 106.68], [10.79, 106.67], [10.80, 106.68]]
# GeoJSON order from the provider: [lng, lat]
OK_BODY = {
    "code": "OK",
    "paths": [
        {"distance": 4321.0, "points": {"coordinates": [[106.68, 10.80], [106.675, 10.795], [106.67, 10.79]]}}
    ],
}


def router(tmp_path, handler) -> tuple[RoadRouter, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return RoadRouter(KEY, tmp_path, transport=httpx.MockTransport(wrapped)), seen


def test_parses_provider_answer_and_flips_to_lat_lng(tmp_path):
    r, seen = router(tmp_path, lambda _: httpx.Response(200, json=OK_BODY))
    got = r.path(POINTS)
    assert got == RoadPath([[10.80, 106.68], [10.795, 106.675], [10.79, 106.67]], 4.321)
    q = seen[0].url.params
    assert q["vehicle"] == "motorcycle" and q["points_encoded"] == "false" and q["apikey"] == KEY
    assert q.get_list("point") == ["10.8,106.68", "10.79,106.67", "10.8,106.68"]


def test_real_answers_are_cached_on_disk(tmp_path):
    r, seen = router(tmp_path, lambda _: httpx.Response(200, json=OK_BODY))
    first = r.path(POINTS)
    again, seen2 = router(tmp_path, lambda _: httpx.Response(500))  # fresh process, same cache dir
    assert again.path(POINTS) == first and len(seen) == 1 and seen2 == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(423, text="Your request is limited"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"code": "OK", "paths": []}),
        httpx.Response(200, json={**OK_BODY, "code": "ERROR"}),
    ],
)
def test_failures_give_none_never_a_made_up_path(tmp_path, response):
    r, _ = router(tmp_path, lambda _: response)
    assert r.path(POINTS) is None
    assert list(tmp_path.rglob("*.json")) == []  # a failure is never cached


def test_network_error_pauses_requests_then_logs_no_key(tmp_path, caplog, monkeypatch):
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    r, seen = router(tmp_path, boom)
    with caplog.at_level(logging.WARNING, logger="api.road_path"):
        assert r.path(POINTS) is None
        assert r.path([[10.7, 106.6], [10.71, 106.61]]) is None  # still cooling down: no second request
    assert len(seen) == 1
    assert KEY not in caplog.text and "apikey" not in caplog.text
    now = time.monotonic()
    monkeypatch.setattr("api.road_path.time.monotonic", lambda: now + COOLDOWN_S + 1)
    r.path(POINTS)
    assert len(seen) == 2


def test_needs_two_points(tmp_path):
    r, seen = router(tmp_path, lambda _: httpx.Response(200, json=OK_BODY))
    assert r.path([[10.8, 106.68]]) is None and seen == []


# ------------------------------------------------------------------ through the API


@pytest.fixture()
def road_client(data_dir, fake_solver, tmp_path) -> TestClient:
    app = create_app(make_settings(data_dir, tmp_path / "cache", vietmap_route_key=KEY), solver=fake_solver)
    with TestClient(app) as c:
        yield c


def test_plan_uses_road_path_and_names_the_source(road_client, monkeypatch):
    drawn = [[10.8, 106.7], [10.81, 106.71], [10.82, 106.72]]
    monkeypatch.setattr(RoadRouter, "_fetch", lambda self, pts: RoadPath(drawn, 7.25))
    h = login(road_client, "owner_a")
    body = road_client.post("/api/routing/plan", json={"store_id": "A-CH2"}, headers=h).json()
    assert body["path_source"] == "road"
    assert all(
        r["path"] == drawn and r["path_source"] == "road" and r["road_path_km"] == 7.2 for r in body["routes"]
    )
    assert "VIETMAP_ROUTE" in body["sources"]
    assert len(body["sources"]) == len(body["source_labels_vi"])
    assert any("đường bộ thật" in a and "chim bay" in a for a in body["assumptions_vi"])
    assert KEY not in road_client.post("/api/routing/plan", json={"store_id": "A-CH2"}, headers=h).text


def test_plan_falls_back_to_labelled_straight_segments(road_client, monkeypatch):
    monkeypatch.setattr(RoadRouter, "_fetch", lambda self, pts: None)
    h = login(road_client, "owner_a")
    body = road_client.post("/api/routing/plan", json={"store_id": "A-CH2"}, headers=h).json()
    assert body["path_source"] == "straight"
    for r in body["routes"]:
        assert r["path_source"] == "straight" and r["road_path_km"] is None
        assert r["path"][0] == r["path"][-1] and len(r["path"]) >= 2  # home -> stops -> home, straight
    assert "VIETMAP_ROUTE" not in body["sources"]
    assert any("nối thẳng" in a for a in body["assumptions_vi"])


def test_plan_without_a_configured_key_is_straight(client, owner_a):
    body = client.post("/api/routing/plan", json={"store_id": "A-CH2"}, headers=owner_a).json()
    assert body["path_source"] == "straight" and "VIETMAP_ROUTE" not in body["sources"]
