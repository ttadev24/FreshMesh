# Jev integration — Phase 1 (adapter + guardrail check) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-safe adapter for Jev (TypeSafe AI, via OpenRouter) and use it as a second, optional
check that an agent answer doesn't falsely claim a real action already happened — on top of the existing
keyword-based `claims_execution()`, never instead of it.

**Architecture:** `agent/jev.py` is a small, self-contained adapter: a `JevClient` class that makes one
HTTP call and never raises (mirrors the existing `api/road_path.py::RoadRouter` pattern — same
constructor-injected `transport` for tests, same "a failure just means no data" contract), plus a pure
function `execution_claim_flagged(client, text)` that asks Jev one yes/no question and returns
`True`/`False`/`None` (`None` = no signal, from a disabled feature or any failure). `agent/loop.py` ORs this
into the existing `claims` check. `api/config.py` reads the three new env vars; `api/main.py` builds the
client once and decides, per the `FRESHMESH_JEV_GUARDRAIL` flag, whether to hand it to each chat turn.

**Tech Stack:** Python 3.12, `httpx` (already a dependency), `pytest`, FastAPI `TestClient` (already used
throughout `tests/api/`).

**Spec:** `docs/superpowers/specs/2026-10-15-jev-integration-design.md` (sections 2.1, 2.2 row 1, 3.1, 4)

## Global Constraints

- Every function that touches Jev must be unable to raise out to its caller: a missing key, HTTP error,
  timeout, or malformed response all become `None` / "disabled", never an exception (spec §2.1, §4).
- `FRESHMESH_JEV_API_KEY` missing ⇒ the whole feature is off, `/api/health` reports `jev: false`, and the
  rest of the app behaves exactly as it does today (spec §4).
- The guardrail is gated by its **own** flag, `FRESHMESH_JEV_GUARDRAIL=1`, separate from "is a key
  configured" — a configured key with the flag off must not call Jev at all (spec §2.2).
- Jev is never a source of numbers shown to the user and is never added to anything
  `agent/guardrail.py::verify_numbers` treats as a source (spec §1.1) — phase 1 doesn't touch
  `verify_numbers` at all, so this is satisfied by construction; a later phase that adds Jev output to any
  user-visible text must re-check this constraint.
- Follow existing code style: `from __future__ import annotations`, `log = logging.getLogger(__name__)`,
  dataclass/plain-function style already used in `agent/` and `api/` (no new abstractions beyond what's
  specified here).

## Review Focus

- A configured `FRESHMESH_JEV_API_KEY` with `FRESHMESH_JEV_GUARDRAIL` unset (the single most likely
  misconfiguration — someone adds the key expecting the guardrail to "just work") must leave answers
  byte-for-byte identical to today. Covered in Task 4.
- OpenRouter times out or the network is down mid-request: the chat turn must still finish and answer
  normally, not hang or 500. Covered in Task 1.
- A malformed Jev response (missing `answers`, missing the question id, `noul` as a non-numeric type) must
  be treated as "no signal", not crash the turn. Covered in Task 1 and Task 2.
- Jev flags a false positive on an answer that's already correct: the existing one-shot rewrite must still
  terminate with a usable answer (no infinite loop), exactly as it does for a `claims_execution()` false
  positive today. Covered in Task 3.
- `/api/health`'s `jev` field reflects "is a client configured" (key present), independent of whether the
  guardrail feature itself is enabled — the two must not be conflated. Covered in Task 4.

---

## Task 1: `JevClient` — the HTTP adapter

**Files:**
- Create: `agent/jev.py`
- Test: `tests/agent/test_jev.py`

**Interfaces:**
- Produces: `class JevClient.__init__(self, api_key: str, *, model: str = DEFAULT_MODEL, timeout_s: float
  = 5.0, transport: httpx.BaseTransport | None = None)`; `JevClient.ask(self, state: str, questions:
  dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]] | None`; module constant `DEFAULT_MODEL: str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/agent/test_jev.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_jev.py -v`
Expected: FAIL / ERROR — `agent.jev` doesn't exist yet (`ModuleNotFoundError`).

- [ ] **Step 3: Write `agent/jev.py`**

```python
"""Jev (TypeSafe AI decision model, via OpenRouter) — a thin, fail-safe adapter used by optional
FreshMesh features. Jev answers closed questions (yes/no, multiple choice, a score) about a piece of
text with a probability; it never generates numbers shown to the user and never replaces anything
FreshMesh already computes (see docs/superpowers/specs/2026-10-15-jev-integration-design.md).

Every feature built on this module must treat a Jev failure exactly like "Jev doesn't exist": a missing
key, network error, timeout or unexpected response all surface as ``None``, never an exception.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"


class JevClient:
    """One HTTP call to Jev's OpenRouter "decisions" endpoint. ``ask()`` never raises."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._key = api_key
        self._model = model
        self._http = httpx.Client(timeout=timeout_s, transport=transport)

    def ask(self, state: str, questions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]] | None:
        """``questions``: ``{question_id: {"type": "noul"|"choice"|"score", "instructions": str, ...}}``.
        Returns ``{question_id: {...answer}}`` on success, ``None`` on any failure."""
        try:
            resp = self._http.post(
                JEV_URL,
                headers={"Authorization": f"Bearer {self._key}"},
                json={"model": self._model, "state": state, "questions": questions},
            )
            resp.raise_for_status()
            answers = resp.json()["answers"]
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            # TypeError: a top-level JSON array (`resp.json()` returns a list, `list["answers"]` raises
            # TypeError, not KeyError) — one more shape of "not the object we expected", same handling.
            log.warning("jev: request failed (%s)", type(exc).__name__)
            return None
        if not isinstance(answers, dict):
            log.warning("jev: unexpected response shape")
            return None
        return answers
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_jev.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Lint**

Run: `uv run ruff check agent/jev.py tests/agent/test_jev.py`
Expected: no findings.

- [ ] **Step 6: Commit**

```bash
git add agent/jev.py tests/agent/test_jev.py
git commit -m "feat(agent): add fail-safe Jev HTTP adapter"
```

---

## Task 2: `execution_claim_flagged` — the guardrail question

**Files:**
- Modify: `agent/jev.py` (append)
- Test: `tests/agent/test_jev.py` (append)

**Interfaces:**
- Consumes: `agent.jev.JevClient` (Task 1).
- Produces: `agent.jev.execution_claim_flagged(client: JevClient | None, answer_text: str) -> bool | None`;
  module constant `EXECUTION_CLAIM_QUESTION_ID: str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/agent/test_jev.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_jev.py -v`
Expected: FAIL — `execution_claim_flagged` / `EXECUTION_CLAIM_QUESTION_ID` not defined.

- [ ] **Step 3: Append to `agent/jev.py`**

```python
EXECUTION_CLAIM_QUESTION_ID = "execution_claim"
_EXECUTION_CLAIM_QUESTION = {
    "type": "noul",
    "instructions": (
        "Câu trả lời của trợ lý khẳng định rằng một hành động thật (đặt hàng, gửi lộ trình, giảm giá, "
        "điều chuyển hàng) ĐÃ được thực hiện, thay vì chỉ tạo bản nháp chờ người dùng duyệt."
    ),
}


def execution_claim_flagged(client: JevClient | None, answer_text: str) -> bool | None:
    """``True``: Jev thinks ``answer_text`` claims a real action already happened. ``False``: Jev thinks
    it doesn't. ``None``: no client, or Jev's answer couldn't be read — callers must treat ``None`` as "no
    additional signal" (never as ``False``), so a disabled or unavailable Jev never changes behaviour."""
    if client is None:
        return None
    answers = client.ask(answer_text, {EXECUTION_CLAIM_QUESTION_ID: _EXECUTION_CLAIM_QUESTION})
    if not answers:
        return None
    try:
        return float(answers[EXECUTION_CLAIM_QUESTION_ID]["noul"]) >= 0.5
    except (KeyError, TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_jev.py -v`
Expected: PASS (13 tests total).

- [ ] **Step 5: Lint**

Run: `uv run ruff check agent/jev.py tests/agent/test_jev.py`
Expected: no findings.

- [ ] **Step 6: Commit**

```bash
git add agent/jev.py tests/agent/test_jev.py
git commit -m "feat(agent): add Jev execution-claim guardrail question"
```

---

## Task 3: Wire into `agent/loop.py`

**Files:**
- Modify: `agent/loop.py:201-224` (`AgentSession.__init__`), `agent/loop.py:365-369` (`_verify_and_answer`)
- Test: `tests/agent/test_loop.py`

**Interfaces:**
- Consumes: `agent.jev.JevClient`, `agent.jev.execution_claim_flagged` (Task 1, 2).
- Produces: `AgentSession.__init__(..., jev_client: JevClient | None = None)` (new keyword-only param,
  default `None` — every existing call site keeps working unchanged).

- [ ] **Step 1: Write the failing test**

Append to the end of `tests/agent/test_loop.py` (its existing imports already cover `AgentSession`,
`SequenceClient`, `text_response`, `CTX`, `_answer` and `_registry`; only the import shown below is new):

```python
from agent.jev import EXECUTION_CLAIM_QUESTION_ID


class _StubJevClient:
    """Always flags the given question as True, regardless of input — used to prove the OR wiring."""

    def ask(self, state, questions):
        return {EXECUTION_CLAIM_QUESTION_ID: {"noul": 0.99}}


# `vi_sao` is overridden on every call below to drop `_answer()`'s default "Dự báo P50 là 118,4 kg." —
# that number isn't backed by any tool output in these tool-free turns, so it would fail
# `verify_numbers` on its own and trigger a rewrite regardless of the Jev/claims logic under test. Using
# a number-free `vi_sao` isolates the behaviour these two tests actually check.


def test_jev_flag_triggers_rewrite_even_without_a_keyword_match():
    # No EXECUTION_CLAIMS_VI phrase in this text, so claims_execution() alone would miss it.
    first = _answer(de_xuat="Xong rồi nhé, không cần làm gì thêm.", vi_sao="Theo yêu cầu của bạn.")
    second = _answer(
        de_xuat="Đã tạo bản nháp `draft-1`, chờ bạn bấm Duyệt.", vi_sao="Theo yêu cầu của bạn."
    )
    client = SequenceClient([text_response(first), text_response(second)])
    session = AgentSession(client, _registry(), CTX, jev_client=_StubJevClient())
    turn = session.run("Nhập rau cho mai.")
    assert turn.rewritten is True
    assert "đã được thực thi" in " ".join(turn.rewrite_problems).lower()
    assert "draft-1" in turn.answer_text


def test_no_jev_client_means_unchanged_behaviour():
    # Same first answer as above, but with no jev_client: claims_execution() also won't catch it (no
    # EXECUTION_CLAIMS_VI phrase), so this must NOT be rewritten.
    only = _answer(de_xuat="Xong rồi nhé, không cần làm gì thêm.", vi_sao="Theo yêu cầu của bạn.")
    client = SequenceClient([text_response(only)])
    session = AgentSession(client, _registry(), CTX)  # jev_client defaults to None
    turn = session.run("Nhập rau cho mai.")
    assert turn.rewritten is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent/test_loop.py -k jev -v`
Expected: FAIL — `AgentSession.__init__()` raises `TypeError: unexpected keyword argument 'jev_client'`.

- [ ] **Step 3: Modify `AgentSession.__init__`**

In `agent/loop.py`, add the import near the other `agent.*` imports:

```python
from agent.jev import JevClient, execution_claim_flagged
```

Change the constructor signature (`agent/loop.py:201-224`) by adding one parameter and one assignment:

```python
    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        ctx: ToolContext,
        *,
        audit: AuditLog | None = None,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        system_prompt: str = SYSTEM_PROMPT_VI,
        on_text: Callable[[str], None] | None = None,
        turn_id_factory: Callable[[], str] | None = None,
        jev_client: JevClient | None = None,
    ):
        self.client = client
        self.registry = registry
        self.ctx = ctx
        self.audit = audit
        self.max_tool_calls = max_tool_calls
        self.system_prompt = system_prompt
        self.on_text = on_text
        self._new_turn_id = turn_id_factory or (lambda: uuid.uuid4().hex)
        self.jev_client = jev_client
        self.messages: list[dict[str, Any]] = []
        self.requests: list[LLMRequest] = []  # every request sent to the model (privacy checks, debugging)
        self.last_turn: AgentTurn | None = None
```

- [ ] **Step 4: Modify `_verify_and_answer`**

In `agent/loop.py`, change this line (around line 369):

```python
        claims = claims_execution(text)
```

to:

```python
        claims = claims_execution(text) or execution_claim_flagged(self.jev_client, text) is True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/agent/test_loop.py -v`
Expected: PASS, including the 2 new tests and every pre-existing test in the file (the new parameter is
additive and defaults to `None`, so no existing behaviour changes).

- [ ] **Step 6: Run the full agent test suite**

Run: `uv run pytest tests/agent/ -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Lint**

Run: `uv run ruff check agent/loop.py tests/agent/test_loop.py`
Expected: no findings.

- [ ] **Step 8: Commit**

```bash
git add agent/loop.py tests/agent/test_loop.py
git commit -m "feat(agent): OR Jev's execution-claim check into the rewrite guardrail"
```

---

## Task 4: Settings, API wiring, `/api/health`, README

**Files:**
- Modify: `api/config.py:59-74` (`Settings`)
- Modify: `api/main.py` (`create_app`, `health()`, `chat()`)
- Modify: `README.md` (env var table)
- Test: `tests/api/test_health.py`, `tests/api/test_agent.py`

**Interfaces:**
- Consumes: `agent.jev.JevClient`, `agent.jev.DEFAULT_MODEL` (Task 1); `AgentSession(..., jev_client=...)`
  (Task 3).
- Produces: `Settings.jev_api_key: str`, `Settings.jev_model: str`, `Settings.jev_guardrail: bool`;
  `/api/health` gains a `"jev": bool` field.

- [ ] **Step 1: Write the failing tests**

Add to `tests/api/test_health.py` (the file already imports `TestClient`, `create_app` and `make_settings`;
`client`, `fake_solver` and `data_dir` are session fixtures from `tests/api/conftest.py`, already in scope
with no new import needed):

```python
def test_health_reports_jev_false_without_a_key(client):
    assert client.get("/api/health").json()["jev"] is False


def test_health_reports_jev_true_with_a_key(data_dir, fake_solver, tmp_path):
    app = create_app(make_settings(data_dir, tmp_path, jev_api_key="fake-key"), solver=fake_solver)
    with TestClient(app) as c:
        assert c.get("/api/health").json()["jev"] is True
```

Add to `tests/api/test_agent.py`. First change its existing import line

```python
from tests.api.conftest import assert_error, login
```

to

```python
from fastapi.testclient import TestClient

from agent.jev import JevClient
from api.main import create_app
from tests.agent.fake_llm import PlannedFakeClient
from tests.api.conftest import assert_error, login, make_settings
```

(keep `from agent.guardrail import verify_numbers`, `from agent.template import SECTIONS, parse_answer`,
`from agent.tools import ToolContext, ToolError` and `from tests.api.helpers import FORECAST_SOURCES,
ROUTING_SOURCES, TEST_DATASETS` exactly as they already are). Then append:

```python
def test_guardrail_flag_off_ignores_a_configured_jev_key(data_dir, fake_solver, tmp_path):
    """A configured FRESHMESH_JEV_API_KEY with FRESHMESH_JEV_GUARDRAIL unset must not call Jev at all."""
    called: list[int] = []
    orig_ask = JevClient.ask
    JevClient.ask = lambda self, *a, **kw: called.append(1) or orig_ask(self, *a, **kw)
    try:
        app = create_app(
            make_settings(data_dir, tmp_path, jev_api_key="fake-key"),
            solver=fake_solver,
            llm_client_factory=lambda: PlannedFakeClient([]),
        )
        with TestClient(app) as c:
            headers = login(c, "owner_a")
            r = c.post("/api/agent/chat", json={"message": "Xin chào"}, headers=headers)
            assert r.status_code == 200, r.text
    finally:
        JevClient.ask = orig_ask
    assert called == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_health.py tests/api/test_agent.py -k jev -v`
Expected: FAIL — `make_settings()` doesn't accept `jev_api_key`, and `/api/health` has no `"jev"` key.

- [ ] **Step 3: Add the three fields to `Settings`**

In `api/config.py`, add after the existing `vietmap_route_key` field (around line 68):

```python
    # Jev (TypeSafe AI decision model, via OpenRouter): optional, never required. See
    # docs/superpowers/specs/2026-10-15-jev-integration-design.md.
    jev_api_key: str = field(default_factory=lambda: os.environ.get("FRESHMESH_JEV_API_KEY", "").strip(), repr=False)
    jev_model: str = field(default_factory=lambda: os.environ.get("FRESHMESH_JEV_MODEL", "").strip())
    jev_guardrail: bool = field(default_factory=lambda: os.environ.get("FRESHMESH_JEV_GUARDRAIL") == "1")
```

- [ ] **Step 4: Build the client and wire it into `api/main.py`**

Add the import near the other `agent.*` imports in `api/main.py`:

```python
from agent.jev import DEFAULT_MODEL as JEV_DEFAULT_MODEL, JevClient
```

In `create_app`, right after `services = Services(settings.data_dir, routing)` (or any point before
`health()`/`chat()` are defined — both close over it), add:

```python
    jev_client: JevClient | None = (
        JevClient(settings.jev_api_key, model=settings.jev_model or JEV_DEFAULT_MODEL)
        if settings.jev_api_key
        else None
    )
```

In `health()`, add one key to the returned dict:

```python
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        data_ready = all(chain_db_path(settings.data_dir, c).exists() for c in CHAIN_IDS)
        return {
            "status": "ok" if data_ready else "degraded",
            "solver": solver_up(),
            "llm": llm_client_factory is not None or llm_available(),
            "llm_required": True,
            "llm_model": configured_model(),
            "data": data_ready,
            "jev": jev_client is not None,
        }
```

In `chat()`, pass the client only when the guardrail flag is on:

```python
        session = AgentSession(
            client,
            registry,
            tool_ctx(user, default_sid),
            audit=AuditLog(chain_db_path(settings.data_dir, user.chain_id)),
            jev_client=jev_client if settings.jev_guardrail else None,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_health.py tests/api/test_agent.py -v`
Expected: PASS, including every pre-existing test in both files.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest`
Expected: PASS (unit tests only; this doesn't need the solver container or a real LLM key).

- [ ] **Step 7: Lint**

Run: `uv run ruff check api/config.py api/main.py tests/api/test_health.py tests/api/test_agent.py`
Expected: no findings.

- [ ] **Step 8: Document the new env vars in README.md**

In `README.md`, in the "Biến môi trường của API" table (after the `FRESHMESH_LLM_EFFORT` row), add:

```markdown
| `FRESHMESH_JEV_API_KEY` | (trống) | khóa OpenRouter cho Jev (TypeSafe AI); thiếu khóa thì mọi tính năng Jev tắt, `/api/health` báo `jev: false` |
| `FRESHMESH_JEV_MODEL` | `typesafe/jev-1.13` | model Jev dùng qua OpenRouter |
| `FRESHMESH_JEV_GUARDRAIL` | (trống) | `1` = bật kiểm tra câu trả lời agent bằng Jev (cần `FRESHMESH_JEV_API_KEY`) |
```

- [ ] **Step 9: Commit**

```bash
git add api/config.py api/main.py README.md tests/api/test_health.py tests/api/test_agent.py
git commit -m "feat(api): wire Jev guardrail behind its own flag, report jev in /api/health"
```

---

## After this plan

Phase 1 is done when all 4 tasks are committed and `uv run pytest` passes with no network access. Before
starting Phase 2 (spec §3.2, the audit log), stop and confirm with a real `FRESHMESH_JEV_API_KEY` +
`FRESHMESH_JEV_GUARDRAIL=1` that Jev's Vietnamese understanding is good enough in practice — manually, with
explicit confirmation before any call that spends real money, never run automatically.
