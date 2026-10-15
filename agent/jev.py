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
