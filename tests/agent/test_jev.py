from __future__ import annotations

import httpx
import pytest

from agent.jev import DEFAULT_MODEL, JEV_URL, JevClient

QUESTIONS = {"q1": {"type": "noul", "instructions": "Is this a test?"}}


def _client(handler, **kw) -> tuple[JevClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return JevClient("test-key", transport=httpx.MockTransport(wrapped), **kw), seen


def test_ask_posts_expected_body_and_returns_answers():
    body = {"answers": {"q1": {"type": "noul", "noul": 0.92}}, "model": DEFAULT_MODEL}
    client, seen = _client(lambda _: httpx.Response(200, json=body))
    got = client.ask("some text", QUESTIONS)
    assert got == {"q1": {"type": "noul", "noul": 0.92}}
    assert seen[0].url == JEV_URL
    assert seen[0].headers["authorization"] == "Bearer test-key"
    import json as _json

    sent = _json.loads(seen[0].content)
    assert sent == {"model": DEFAULT_MODEL, "state": "some text", "questions": QUESTIONS}


def test_ask_uses_the_given_model():
    client, seen = _client(lambda _: httpx.Response(200, json={"answers": {}}), model="typesafe/jev-latest")
    client.ask("x", QUESTIONS)
    import json as _json

    assert _json.loads(seen[0].content)["model"] == "typesafe/jev-latest"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="server error"),
        httpx.Response(401, text="bad key"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"no_answers_key": True}),
        httpx.Response(200, json={"answers": "not a dict"}),
        httpx.Response(200, json=["not", "an", "object"]),
    ],
)
def test_ask_returns_none_on_any_failure_response(response):
    client, _ = _client(lambda _: response)
    assert client.ask("x", QUESTIONS) is None


def test_ask_returns_none_on_network_error():
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client, _ = _client(boom)
    assert client.ask("x", QUESTIONS) is None


def test_ask_returns_none_on_timeout():
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow")

    client, _ = _client(boom)
    assert client.ask("x", QUESTIONS) is None


from agent.jev import EXECUTION_CLAIM_QUESTION_ID, execution_claim_flagged


def test_execution_claim_flagged_none_without_a_client():
    assert execution_claim_flagged(None, "Đã đặt hàng xong.") is None


def test_execution_claim_flagged_true_above_threshold():
    body = {"answers": {EXECUTION_CLAIM_QUESTION_ID: {"type": "noul", "noul": 0.87}}}
    client, seen = _client(lambda _: httpx.Response(200, json=body))
    assert execution_claim_flagged(client, "Đã đặt hàng xong.") is True
    import json as _json

    sent = _json.loads(seen[0].content)
    assert sent["state"] == "Đã đặt hàng xong."
    assert set(sent["questions"]) == {EXECUTION_CLAIM_QUESTION_ID}


def test_execution_claim_flagged_false_below_threshold():
    body = {"answers": {EXECUTION_CLAIM_QUESTION_ID: {"type": "noul", "noul": 0.1}}}
    client, _ = _client(lambda _: httpx.Response(200, json=body))
    assert execution_claim_flagged(client, "Đã tạo bản nháp.") is False


def test_execution_claim_flagged_none_when_jev_unavailable():
    client, _ = _client(lambda _: httpx.Response(500))
    assert execution_claim_flagged(client, "x") is None


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"other_id": {"noul": 0.9}},
        {EXECUTION_CLAIM_QUESTION_ID: {"noul": "high"}},
        {EXECUTION_CLAIM_QUESTION_ID: {}},
    ],
)
def test_execution_claim_flagged_none_on_malformed_answer(answers):
    client, _ = _client(lambda _: httpx.Response(200, json={"answers": answers}))
    assert execution_claim_flagged(client, "x") is None
