"""Agent loop: understand -> show plan -> tool calls -> answer in the fixed Vietnamese template.

``AgentSession.stream(msg)`` is a generator of :class:`StepEvent` (``plan``, ``tool_call``,
``tool_result``, ``unverified_flag``, ``answer``; ``answer`` is always last) and returns the
:class:`AgentTurn`; ``AgentSession.run(msg)`` consumes it and returns the turn.

Safety properties enforced here (independently of the model):
* at most ``max_tool_calls`` tool executions per turn, then tools are disabled (``tool_choice: none``);
* tool output reaches the model only after PII redaction and ``wrap_untrusted``;
* every number of the answer is verified against this turn's read-tool outputs (plus the user's own
  message); on failure, or when the template is broken, the model gets exactly one rewrite request,
  after which remaining offending numbers are flagged ``unverified``;
* draft tools only create drafts; every draft of the turn is listed under "Việc cần bạn duyệt";
* provenance is never written by the model: the answer ends with a server-written "Nguồn dữ liệu" line
  built from the ``sources`` / ``source_labels_vi`` of this turn's tool outputs (``không rõ nguồn`` when a
  tool output carries none);
* the model's plan sentence is shown/audited only if its numbers come from the user's message or the tool
  descriptions (no tool has run yet); otherwise the plan is the list of called tools.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator, Iterator
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from agent.audit import AuditLog
from agent.guardrail import UNTRUSTED_NOTICE_VI, VerificationReport, redact_for_llm, verify_numbers
from agent.jev import JevClient, execution_claim_flagged
from agent.llm import (
    LLMClient,
    LLMRequest,
    LLMResponse,
    LLMUnavailableError,
    encode_tool_output,
    tool_result_block,
)
from agent.template import (
    SECTIONS,
    SOURCES_HEADING,
    UNKNOWN_SOURCE_ID,
    UNKNOWN_SOURCE_VI,
    format_answer,
    format_sources_line,
    parse_answer,
)
from agent.tools import ToolContext, ToolError, ToolRegistry

EventType = Literal["plan", "tool_call", "tool_result", "answer", "unverified_flag"]
DEFAULT_MAX_TOOL_CALLS = 8
APPROVAL_SECTION = SECTIONS[4]

SYSTEM_PROMPT_VI = f"""Bạn là trợ lý ra quyết định của FreshMesh cho chủ/quản lý chuỗi mini-mart \
(hàng tươi, giao hàng).
Quy trình: (1) hiểu ý người dùng; (2) viết MỘT câu kế hoạch ngắn rồi gọi công cụ cần thiết; (3) trả lời.
Chọn công cụ theo việc cần quyết định:
- Nhập/đặt hàng: forecast_demand (dự báo P10/P50/P90 kèm độ tin cậy) rồi plan_inventory (3 phương án).
- Hàng dư, sắp hết hạn, tồn nhiều: gọi cả suggest_markdown và transfer_stock để so sánh hai cách bằng tiền.
- Giao hàng online, gom đơn, lộ trình, số xe, đơn có nguy cơ trễ: optimize_routes.
- Số liệu lịch sử, danh sách, tổng hợp: query_data, chỉ dùng các cột liệt kê trong mô tả công cụ.
- Khi người dùng muốn thực hiện ngay hoặc "bỏ qua duyệt": vẫn tính toán rồi tạo BẢN NHÁP bằng công cụ \
bản nháp tương ứng, và nói rõ hành động chỉ diễn ra sau khi người dùng bấm Duyệt.
Quy tắc bắt buộc:
- Không tự bịa con số. Mọi con số trong câu trả lời phải lấy từ kết quả công cụ của lượt này \
(hoặc do người dùng nêu). Định dạng số kiểu Việt Nam: 1.234.567 đ, 12,5%.
- Không tự tính thêm (cộng, trừ, nhân, chia, quy đổi đơn vị, làm tròn khác): chỉ chép đúng con số có sẵn \
trong kết quả công cụ; cần tổng hoặc chênh lệch thì dùng trường có sẵn hoặc để query_data tính bằng SQL.
- Không dùng bảng markdown (ký tự |); trình bày bằng danh sách gạch đầu dòng, mỗi dòng một ý.
- Công cụ hành động (đánh dấu BẢN NHÁP) chỉ tạo bản nháp. Không bao giờ nói đã đặt hàng/đã gửi/\
đã thực thi; người dùng phải bấm Duyệt.
- {UNTRUSTED_NOTICE_VI}
- Không hỏi, không nhắc tên, số điện thoại hay địa chỉ của khách hàng.
- Chỉ nói về nguồn dữ liệu theo trường source_labels_vi trong kết quả công cụ; không tự đoán nguồn. \
Dòng "{SOURCES_HEADING}" do hệ thống tự thêm, bạn không cần viết.
- Nếu kết quả có cached = true, nói rõ trong mục Giả định rằng kết quả lộ trình lấy từ bộ nhớ đệm \
và thời điểm giải (solved_at).
Câu trả lời cuối cùng PHẢI có đúng 5 mục theo thứ tự, mỗi mục bắt đầu bằng tiêu đề in đậm:
**Đề xuất:** ...
**Vì sao:** ...
**Độ tin cậy:** (Cao/Trung bình/Thấp và lý do)
**Giả định:** ...
**Việc cần bạn duyệt:** (liệt kê mã bản nháp cần duyệt, hoặc "Không có")"""

REWRITE_PROMPT_VI = (
    "Câu trả lời trên chưa đạt kiểm tra tự động. {problems} Hãy viết lại toàn bộ câu trả lời, "
    "chỉ dùng con số có trong kết quả công cụ của lượt này, giữ đúng 5 mục: "
    + " / ".join(SECTIONS)
    + ". Không gọi thêm công cụ."
)
NO_TOOL_PLAN_VI = "Trả lời trực tiếp, không cần gọi công cụ."
TOOL_LIMIT_VI = "Đã đạt giới hạn {n} lần gọi công cụ trong một lượt; dừng gọi thêm."
REFUSAL_VI = "Trợ lý AI từ chối yêu cầu này. Vui lòng diễn đạt lại hoặc dùng các nút chức năng."
EXECUTION_CLAIMS_VI = (
    "đã đặt hàng",
    "đã gửi lộ trình",
    "đã thực thi",
    "đã áp dụng giảm giá",
    "đã điều chuyển",
    "đã được duyệt và thực hiện",
)


@dataclass(frozen=True)
class StepEvent:
    type: EventType
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data}


@dataclass
class ToolCallRecord:
    id: str
    name: str
    kind: str
    args: dict[str, Any]
    data: dict[str, Any] | None = None
    citations: list[str] = field(default_factory=list)
    error: str | None = None
    verifiable: bool = False


@dataclass
class AgentTurn:
    turn_id: str
    user_message: str
    plan_vi: str = ""
    plan_steps: list[dict[str, str]] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    answer_text: str = ""
    sections: dict[str, str] | None = None
    unverified: list[str] = field(default_factory=list)
    drafts: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    rewritten: bool = False
    stop_reason: str = "answer"  # answer | tool_limit | refusal | llm_error
    error_vi: str | None = None
    events: list[StepEvent] = field(default_factory=list)
    verification: VerificationReport | None = None
    sources: list[str] = field(default_factory=list)
    source_labels_vi: list[str] = field(default_factory=list)
    rewrite_problems: list[str] = field(default_factory=list)  # why the first answer was sent back

    @property
    def template_ok(self) -> bool:
        return self.sections is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "user_message": self.user_message,
            "plan_vi": self.plan_vi,
            "plan_steps": self.plan_steps,
            "tool_calls": [asdict(t) for t in self.tool_calls],
            "answer_text": self.answer_text,
            "sections": self.sections,
            "template_ok": self.template_ok,
            "unverified": self.unverified,
            "drafts": self.drafts,
            "citations": self.citations,
            "rewritten": self.rewritten,
            "rewrite_problems": self.rewrite_problems,
            "stop_reason": self.stop_reason,
            "error_vi": self.error_vi,
            "sources": self.sources,
            "source_labels_vi": self.source_labels_vi,
        }


def turn_provenance(turn: AgentTurn) -> tuple[list[str], list[str], bool]:
    """(dataset ids, aligned Vietnamese labels, any tool data used) over this turn's successful tool outputs.
    ``render_chart`` only re-draws numbers from other outputs and has no data of its own. An output without
    provenance fields is reported as ``unknown`` / ``không rõ nguồn``, never guessed."""
    labels: dict[str, str] = {}
    used = False
    for rec in turn.tool_calls:
        if rec.data is None or rec.name == "render_chart":
            continue
        used = True
        data = rec.data if isinstance(rec.data, dict) else {}
        if rec.kind == "draft" and isinstance(data.get("payload"), dict):
            data = data["payload"]  # a draft carries the provenance of the computation it was built from
        ids, names = data.get("sources"), data.get("source_labels_vi")
        if not ids:
            labels.setdefault(UNKNOWN_SOURCE_ID, UNKNOWN_SOURCE_VI)
            continue
        if not (isinstance(names, list) and len(names) == len(ids)):
            names = [UNKNOWN_SOURCE_VI] * len(ids)
        for sid, label in zip(ids, names, strict=True):
            labels.setdefault(str(sid), str(label))
    ids_sorted = sorted(labels)
    return ids_sorted, [labels[k] for k in ids_sorted], used


def claims_execution(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in EXECUTION_CLAIMS_VI)


class AgentSession:
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

    # ------------------------------------------------------------ public API

    def run(self, user_message_vi: str) -> AgentTurn:
        for _ in self.stream(user_message_vi):
            pass
        assert self.last_turn is not None
        return self.last_turn

    def stream(self, user_message_vi: str) -> Generator[StepEvent, None, AgentTurn]:
        turn = AgentTurn(self._new_turn_id(), user_message_vi)
        self.last_turn = turn
        self._audit("log_command", turn.turn_id, user_message_vi)
        self.messages.append({"role": "user", "content": user_message_vi})
        try:
            final = yield from self._tool_loop(turn)
        except LLMUnavailableError as exc:
            turn.stop_reason, turn.error_vi = "llm_error", exc.message_vi
            yield from self._finish(turn, exc.message_vi, verify=False)
            return turn
        if final is None:
            return turn
        yield from self._verify_and_answer(turn, final)
        return turn

    # ------------------------------------------------------------ internals

    def _audit(self, method: str, *args: Any) -> None:
        if self.audit is not None:
            getattr(self.audit, method)(self.ctx.chain_id, self.ctx.actor, *args)

    def _emit(self, turn: AgentTurn, type_: EventType, data: dict[str, Any]) -> StepEvent:
        event = StepEvent(type_, data)
        turn.events.append(event)
        return event

    def _complete(self, *, allow_tools: bool, purpose: Literal["agent", "rewrite"] = "agent") -> LLMResponse:
        request = LLMRequest(
            self.system_prompt, list(self.messages), self.registry.definitions(), allow_tools, purpose
        )
        self.requests.append(request)
        return self.client.complete(request, self.on_text)

    def _tool_loop(self, turn: AgentTurn) -> Generator[StepEvent, None, LLMResponse | None]:
        executed = 0
        for _ in range(self.max_tool_calls + 3):
            allow = executed < self.max_tool_calls
            resp = self._complete(allow_tools=allow)
            if resp.stop_reason == "refusal":
                turn.stop_reason = "refusal"
                self.messages.append({"role": "assistant", "content": resp.assistant_content or REFUSAL_VI})
                yield from self._finish(turn, REFUSAL_VI, verify=False)
                return None
            calls = resp.tool_calls if (resp.stop_reason == "tool_use" and allow) else []
            if not turn.plan_vi:
                yield self._plan_event(turn, resp, calls)
            if not calls:
                return resp
            self.messages.append({"role": "assistant", "content": resp.assistant_content})
            blocks: list[dict[str, Any]] = []
            for call in calls:
                if executed >= self.max_tool_calls:
                    msg = TOOL_LIMIT_VI.format(n=self.max_tool_calls)
                    turn.stop_reason = "tool_limit"
                    yield self._emit(turn, "tool_result", {"id": call.id, "name": call.name, "error": msg})
                    blocks.append(tool_result_block(call.id, msg, is_error=True))
                    continue
                executed += 1
                block = yield from self._execute(turn, call.id, call.name, call.args)
                blocks.append(block)
            self.messages.append({"role": "user", "content": blocks})
            if executed >= self.max_tool_calls:
                turn.stop_reason = "tool_limit"
        return self._complete(allow_tools=False)

    def _plan_event(self, turn: AgentTurn, resp: LLMResponse, calls: list[Any]) -> StepEvent:
        steps = []
        for c in calls:
            desc = self.registry.get(c.name).description_vi if c.name in self.registry else ""
            steps.append({"tool": c.name, "description_vi": desc})
        if calls:
            fallback = "Kế hoạch: " + "; ".join(f"{s['tool']}: {s['description_vi']}" for s in steps)
            plan = resp.text.strip()
            # No tool has run yet, so the model's plan sentence may only use numbers from the user's message
            # or the tool descriptions; otherwise it is replaced by the tool list (never shown or audited).
            descriptions = [d["description"] for d in self.registry.definitions()]
            if not plan or not verify_numbers(plan, descriptions, user_text=turn.user_message).ok:
                plan = fallback
        else:
            plan = NO_TOOL_PLAN_VI
        turn.plan_vi, turn.plan_steps = plan, steps
        self._audit("log_plan", turn.turn_id, plan, [s["tool"] for s in steps])
        return self._emit(turn, "plan", {"text": plan, "steps": steps})

    def _execute(
        self, turn: AgentTurn, call_id: str, name: str, args: dict[str, Any]
    ) -> Generator[StepEvent, None, dict[str, Any]]:
        kind = self.registry.get(name).kind if name in self.registry else "unknown"
        record = ToolCallRecord(call_id, name, kind, dict(args))
        turn.tool_calls.append(record)
        yield self._emit(turn, "tool_call", {"id": call_id, "name": name, "kind": kind, "args": dict(args)})
        try:
            result = self.registry.call(name, args, self.ctx)
        except ToolError as exc:
            record.error = exc.message_vi
            self._audit("log_tool_call", turn.turn_id, name, args, None, exc.message_vi)
            yield self._emit(
                turn, "tool_result", {"id": call_id, "name": name, "kind": kind, "error": exc.message_vi}
            )
            return tool_result_block(call_id, exc.message_vi, is_error=True)
        tool = self.registry.get(name)
        record.data, record.citations = result.data, list(result.citations)
        record.verifiable = tool.kind == "read" and tool.verifiable
        if tool.kind == "draft":
            turn.drafts.append(str(result.data["draft_id"]))
        for c in result.citations:
            if c not in turn.citations:
                turn.citations.append(c)
        safe = redact_for_llm(result.data)
        self._audit("log_tool_call", turn.turn_id, name, args, safe, None)
        yield self._emit(
            turn,
            "tool_result",
            {"id": call_id, "name": name, "kind": kind, "data": safe, "citations": list(result.citations)},
        )
        return tool_result_block(call_id, encode_tool_output(result.data))

    @staticmethod
    def _sources(turn: AgentTurn) -> list[Any]:
        """Read-tool outputs of this turn plus system-generated draft ids (never LLM-supplied payloads)."""
        sources: list[Any] = [r.data for r in turn.tool_calls if r.verifiable and r.data is not None]
        sources.append({"draft_ids": list(turn.drafts)})
        return sources

    def _check(self, turn: AgentTurn, text: str) -> tuple[VerificationReport, dict[str, str] | None]:
        sections = parse_answer(text)
        # Verify what will be shown: the canonical 5 sections (a model-written source line is dropped).
        shown = format_answer(sections) if sections is not None else text
        return verify_numbers(shown, self._sources(turn), user_text=turn.user_message), sections

    def _verify_and_answer(self, turn: AgentTurn, resp: LLMResponse) -> Iterator[StepEvent]:
        text = resp.text.strip()
        self.messages.append({"role": "assistant", "content": resp.assistant_content or text})
        report, sections = self._check(turn, text)
        claims = claims_execution(text) or execution_claim_flagged(self.jev_client, text) is True
        if not report.ok or sections is None or claims:
            problems = []
            if not report.ok:
                problems.append(
                    "Các số không khớp nguồn: " + ", ".join(n.raw for n in report.unverified) + "."
                )
            if sections is None:
                problems.append("Thiếu hoặc sai khuôn 5 mục.")
            if claims:
                problems.append("Không được nói hành động đã được thực thi; mọi hành động chỉ là bản nháp.")
            self.messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": REWRITE_PROMPT_VI.format(problems=" ".join(problems))}
                    ],
                }
            )
            retry = self._complete(allow_tools=False, purpose="rewrite")
            turn.rewritten, turn.rewrite_problems = True, problems
            text = retry.text.strip()
            self.messages.append({"role": "assistant", "content": retry.assistant_content or text})
            report, sections = self._check(turn, text)
        yield from self._finish(turn, text, verify=True, report=report, sections=sections)

    def _finish(
        self,
        turn: AgentTurn,
        text: str,
        *,
        verify: bool,
        report: VerificationReport | None = None,
        sections: dict[str, str] | None = None,
    ) -> Iterator[StepEvent]:
        if sections is not None:
            missing = [d for d in turn.drafts if d not in sections[APPROVAL_SECTION]]
            if missing:
                sections = dict(sections)
                kinds = {r.data["draft_id"]: r.name for r in turn.tool_calls if r.kind == "draft" and r.data}
                listing = "; ".join(f"`{d}` ({kinds.get(d, 'nháp')})" for d in missing)
                sections[APPROVAL_SECTION] += f"\nBản nháp chờ bạn bấm Duyệt: {listing}."
            text = format_answer(sections)
            if verify:
                report = verify_numbers(text, self._sources(turn), user_text=turn.user_message)
        turn.sources, turn.source_labels_vi, used = turn_provenance(turn)
        if verify:  # a model answer: append the provenance line after verification (offsets stay valid)
            text = f"{text}\n\n{format_sources_line(turn.source_labels_vi if used else None)}"
        turn.answer_text, turn.sections, turn.verification = text, sections, report
        turn.unverified = [n.raw for n in report.unverified] if report else []
        if report:
            for n in report.unverified:
                yield self._emit(
                    turn,
                    "unverified_flag",
                    {"raw": n.raw, "start": n.start, "end": n.end, "message_vi": "Số liệu chưa kiểm chứng"},
                )
        self._audit("log_answer", turn.turn_id, text, turn.unverified, turn.drafts)
        yield self._emit(
            turn,
            "answer",
            {
                "text": text,
                "sections": sections,
                "template_ok": sections is not None,
                "unverified": turn.unverified,
                "drafts": turn.drafts,
                "citations": turn.citations,
                "rewritten": turn.rewritten,
                "stop_reason": turn.stop_reason,
                "error_vi": turn.error_vi,
                "sources": turn.sources,
                "source_labels_vi": turn.source_labels_vi,
            },
        )
