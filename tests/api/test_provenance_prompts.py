"""GET /api/provenance/prompts/{prompt_id}: evidence of one logged AI call, on a throwaway data root."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.auth import User, current_user
from api.main import create_app
from provenance import log_prompt, write_registry
from provenance.prompts import prompts_path
from tests.api.conftest import assert_error, make_settings

NOTE = "temperature không được gửi: mô hình thử chỉ nhận giá trị mặc định."


@pytest.fixture()
def prompt_env(tmp_path: Path):
    data = tmp_path / "data"
    write_registry(
        data,
        {
            "T_AI": {
                "id": "T_AI",
                "name_vi": "Tham số AI thử nghiệm",
                "kind": "ai_generated",
                "url": None,
                "license": "Nội bộ",
                "retrieved_at": "2026-10-14T00:00:00+00:00",
                "description_vi": "Bộ AI thử.",
                "details": {"temperature_note_vi": NOTE, "file": "data_real/generated/x.json"},
            },
            "T_DERIVED": {
                "id": "T_DERIVED",
                "name_vi": "Sinh từ tham số AI thử",
                "kind": "derived",
                "url": None,
                "license": "Mã nguồn",
                "retrieved_at": None,
                "description_vi": "Dẫn xuất.",
                "prompt_ids": [],
            },
        },
    )
    common = {
        "purpose": "ai_params:test",
        "dataset_id": "T_AI",
        "model": "claude-test",
        "data_dir": data,
        "system": "Hệ thống thử.",
        "task": "catalog",
        "parameters": {
            "model": "claude-test",
            "max_tokens": 100,
            "output_config": {"format": {"schema": {}}},
        },
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    bad = log_prompt(
        prompt="Prompt lần 1", response="khong phai json", status="invalid", error="sai", **common
    )
    good = log_prompt(
        prompt="Prompt lần 2", response='{"a": 1}', attempt=2, parsed_path="data_real/x.json", **common
    )
    # The derived dataset lists the accepted prompt (as GEN_FROM_AI_PARAMS_V1 does).
    reg = json.loads((data / "provenance" / "registry.json").read_text(encoding="utf-8"))
    for d in reg["datasets"]:
        if d["id"] == "T_DERIVED":
            d["prompt_ids"] = [good["id"]]
    (data / "provenance" / "registry.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

    app = create_app(make_settings(data, tmp_path / "cache"), solver=None)
    app.dependency_overrides[current_user] = lambda: User(
        "u_x", "manager_x", "store_manager", "CHAIN_A", "A-CH1"
    )
    with TestClient(app) as c:
        yield c, data, bad, good


def test_prompt_found_with_verified_hash(prompt_env):
    client, _, bad, good = prompt_env
    r = client.get(f"/api/provenance/prompts/{good['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["prompt_id"] == good["id"] and body["task"] == "catalog" and body["model"] == "claude-test"
    assert body["status"] == "accepted" and body["attempt"] == 2 and body["ts"] == good["ts"]
    assert body["prompt_text"] == "Prompt lần 2" and body["system_text"] == "Hệ thống thử."
    assert body["response_text"] == '{"a": 1}' and body["response_sha256"] == good["response_sha256"]
    assert body["sha256_ok"] is True and body["prompt_sha256_ok"] is True
    assert body["params"]["max_tokens"] == 100 and body["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert body["dataset_ids"] == ["T_AI", "T_DERIVED"]
    assert body["notes_vi"] == [NOTE]  # from the registry details, not hard-coded
    assert [a["id"] for a in body["attempts"]] == [bad["id"], good["id"]]
    # No file path is ever exposed (response_path / parsed_path / details.file stay server-side).
    raw = r.text
    assert "response_path" not in body and "parsed_path" not in body
    assert "provenance/responses" not in raw and "data_real" not in raw


def test_list_endpoint_is_light(prompt_env):
    client, _, bad, good = prompt_env
    by_id = {d["id"]: d for d in client.get("/api/provenance").json()["datasets"]}
    assert [p["id"] for p in by_id["T_AI"]["prompts"]] == [bad["id"], good["id"]]
    for p in by_id["T_AI"]["prompts"]:
        assert set(p) == {"id", "task", "ts", "model", "status", "attempt"}
    assert by_id["T_AI"]["prompts"][0]["status"] == "invalid"


def test_unknown_and_malformed_ids_are_404(prompt_env):
    client, *_ = prompt_env
    r = client.get("/api/provenance/prompts/P20990101T000000-0123456789")
    assert_error(r, 404, "unknown_prompt")
    assert "prompt" in r.json()["error"]["message_vi"]
    for bad in ("nope", "P20990101T000000-ZZZZZZZZZZ", "...", "P20990101T000000-0123456789.txt"):
        assert_error(client.get(f"/api/provenance/prompts/{bad}"), 404, "unknown_prompt")


def test_path_traversal_is_rejected(prompt_env):
    client, data, _, good = prompt_env
    # Encoded slashes are decoded by the router: the request never reaches the handler.
    for url in (
        "/api/provenance/prompts/..%2F..%2Fregistry.json",
        "/api/provenance/prompts/../../etc/passwd",
    ):
        assert client.get(url).status_code == 404
    # A tampered log record pointing outside data/provenance: the file is not read, the hash check fails.
    secret = data / "secret.txt"
    secret.write_text("BÍ MẬT", encoding="utf-8")
    rec = {**json.loads(prompts_path(data).read_text(encoding="utf-8").splitlines()[-1])}
    rec.update(id="P20261014T010101-abcdefabcd", response_path="provenance/../secret.txt")
    with prompts_path(data).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    body = client.get("/api/provenance/prompts/P20261014T010101-abcdefabcd").json()
    assert body["response_text"] is None and body["sha256_ok"] is False
    assert "BÍ MẬT" not in json.dumps(body, ensure_ascii=False)
    assert client.get(f"/api/provenance/prompts/{good['id']}").json()["sha256_ok"] is True


def test_sha_mismatch_is_reported(prompt_env):
    client, data, _, good = prompt_env
    (data / "provenance" / "responses" / f"{good['id']}.txt").write_text('{"a": 2}', encoding="utf-8")
    body = client.get(f"/api/provenance/prompts/{good['id']}").json()
    assert body["response_text"] == '{"a": 2}' and body["sha256_ok"] is False
    (data / "provenance" / "responses" / f"{good['id']}.txt").unlink()
    body = client.get(f"/api/provenance/prompts/{good['id']}").json()
    assert body["response_text"] is None and body["sha256_ok"] is False


def test_requires_auth(tmp_path):
    app = create_app(make_settings(tmp_path / "data", tmp_path / "cache"), solver=None)
    with TestClient(app) as c:
        assert_error(c.get("/api/provenance/prompts/P20990101T000000-0123456789"), 401)


def test_every_role_may_read(client, owner_a, manager_a):
    for headers in (owner_a, manager_a):
        # The fixture data root has no prompt log: well-formed unknown id → 404 unknown_prompt (not 403).
        assert_error(
            client.get("/api/provenance/prompts/P20990101T000000-0123456789", headers=headers),
            404,
            "unknown_prompt",
        )


def test_dataset_detail_does_not_serve_internal_file_paths(client, owner_a):
    r = client.get("/api/provenance", headers=owner_a)
    ai = [d for d in r.json()["datasets"] if d["prompts"]] if r.status_code == 200 else []
    assert r.status_code == 200
    ds_id = ai[0]["id"] if ai else next(d["id"] for d in r.json()["datasets"])
    detail = client.get(f"/api/provenance/{ds_id}", headers=owner_a).json()
    text = str(detail)
    assert "parsed_path" not in text and "response_path" not in text
