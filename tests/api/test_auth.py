import base64
import json

import pytest

from api.auth import User, issue_token, verify_token
from tests.api.conftest import SECRET, assert_error, login


def test_health_is_public_and_reports_llm_requirement(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("FRESHMESH_LLM_MODEL", raising=False)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "status": "ok",
        "solver": True,
        "llm": False,
        "llm_required": True,
        "llm_model": "claude-sonnet-5-5",
        "data": True,
    }
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert client.get("/api/health").json()["llm"] is True


def test_login_returns_token_and_user(client):
    r = client.post("/api/auth/login", json={"username": "manager_a1", "password": "demo123"})
    assert r.status_code == 200
    user = r.json()["user"]
    assert user == {
        "user_id": "CHAIN_A-manager1",
        "username": "manager_a1",
        "role": "store_manager",
        "chain_id": "CHAIN_A",
        "store_id": "A-CH1",
    }


def test_wrong_password_and_unknown_user(client):
    assert_error(
        client.post("/api/auth/login", json={"username": "owner_a", "password": "x"}),
        401,
        "invalid_credentials",
    )
    assert_error(
        client.post("/api/auth/login", json={"username": "nobody", "password": "demo123"}),
        401,
        "invalid_credentials",
    )


def test_missing_and_garbage_tokens(client):
    assert_error(client.get("/api/stores"), 401, "unauthorized")
    assert_error(
        client.get("/api/stores", headers={"Authorization": "Bearer abc.def.ghi"}), 401, "invalid_token"
    )


def test_expired_token():
    user = User("u", "owner_a", "owner", "CHAIN_A", None)
    token = issue_token(user, SECRET, 60, now=1000)
    assert verify_token(token, SECRET, now=1059).chain_id == "CHAIN_A"
    try:
        verify_token(token, SECRET, now=1060)
    except Exception as exc:
        assert getattr(exc, "code", "") == "token_expired"
    else:
        raise AssertionError("expired token accepted")


def test_tampered_chain_claim_is_rejected(client, owner_a):
    token = owner_a["Authorization"].split()[1]
    header, payload, sig = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["chain_id"] = "CHAIN_B"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    r = client.get("/api/stores", headers={"Authorization": f"Bearer {header}.{forged}.{sig}"})
    assert_error(r, 401, "invalid_token")


def test_tenant_isolation_chain_a_never_reads_chain_b(client, owner_a, owner_b):
    a_stores = {s["store_id"] for s in client.get("/api/stores", headers=owner_a).json()}
    b_stores = {s["store_id"] for s in client.get("/api/stores", headers=owner_b).json()}
    assert a_stores and b_stores and not (a_stores & b_stores)
    assert all(s.startswith("A-") for s in a_stores)
    # Naming a CHAIN_B store with a CHAIN_A token is "not in your chain", never data.
    assert_error(client.get("/api/forecast?store_id=B-CH1", headers=owner_a), 404, "unknown_store")
    assert_error(
        client.post("/api/routing/plan", json={"store_id": "B-CH1"}, headers=owner_a), 404, "unknown_store"
    )
    # A chain_id in the body is ignored: the tenant comes from the token.
    r = client.post(
        "/api/inventory/plan",
        json={"store_id": "CH2", "categories": ["rau"], "chain_id": "CHAIN_B"},
        headers=owner_a,
    )
    assert r.status_code == 200 and r.json()["store_id"] == "A-CH2"


def test_me_has_chain_name(client):
    headers = login(client, "owner_c")
    body = client.get("/api/me", headers=headers).json()
    assert body["chain_id"] == "CHAIN_C" and body["chain_name"] and "source" not in body


def test_secret_is_required_unless_dev_flag(monkeypatch):
    from api.config import DEV_SECRET, MIN_SECRET_LEN, Settings

    monkeypatch.delenv("FRESHMESH_SECRET", raising=False)
    monkeypatch.delenv("FRESHMESH_ALLOW_DEV_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        Settings()
    monkeypatch.setenv("FRESHMESH_SECRET", "x" * (MIN_SECRET_LEN - 1))
    with pytest.raises(RuntimeError):
        Settings()
    monkeypatch.setenv("FRESHMESH_SECRET", "y" * MIN_SECRET_LEN)
    assert Settings().secret == "y" * MIN_SECRET_LEN
    monkeypatch.delenv("FRESHMESH_SECRET")
    monkeypatch.setenv("FRESHMESH_ALLOW_DEV_SECRET", "1")
    assert Settings().secret == DEV_SECRET


def test_openapi_docs_hidden_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
