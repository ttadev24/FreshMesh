import json

import httpx
import pytest

from routing.client import SolverClient, SolverError

OK = {
    "objective": 12.5,
    "vehicles": 1,
    "runtime": 0.4,
    "routes": [["0", "1", "2(3)", "0"]],
    "raw_routes": [[0, 1, 3, 0]],
    "delivery_nodes": [1, 3],
    "success": True,
    "error_message": "",
}


def client_returning(status=200, body=None, exc=None, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if exc is not None:
            raise exc
        return httpx.Response(status, json=body if body is not None else OK)

    return SolverClient("http://solver", transport=httpx.MockTransport(handler))


def test_solve_posts_instance_and_parses_response():
    seen = []
    resp = client_returning(seen=seen).solve("2 1\n...", solver="paco", size="medium")
    payload = json.loads(seen[0].content)
    assert seen[0].url.path == "/solve"
    assert payload == {"instance_content": "2 1\n...", "solver": "paco", "size": "medium"}
    assert resp.objective == 12.5
    assert resp.routes == [["0", "1", "2(3)", "0"]]
    assert resp.delivery_nodes == [1, 3]


def test_solver_failure_flag_raises_with_message():
    body = dict(OK, success=False, error_message="Solver timed out after 5 minutes")
    with pytest.raises(SolverError, match="timed out"):
        client_returning(body=body).solve("x")


def test_http_error_status_raises():
    with pytest.raises(SolverError, match="HTTP 500"):
        client_returning(status=500, body={"detail": "boom"}).solve("x")


def test_timeout_raises():
    with pytest.raises(SolverError, match="timeout"):
        client_returning(exc=httpx.ReadTimeout("slow")).solve("x")


def test_connection_error_raises():
    with pytest.raises(SolverError, match="cannot reach"):
        client_returning(exc=httpx.ConnectError("refused")).solve("x")


def test_health():
    assert client_returning(body={"status": "ok"}).health() is True
    assert client_returning(exc=httpx.ConnectError("refused")).health() is False
