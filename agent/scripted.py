"""Recorded demo scenarios that run without an LLM or network.

A :class:`Scenario` is an ordered list of ``(tool_name, args)`` steps (``args`` may be a function of the
previous outputs) plus an ``answer`` function that fills the five template sections from the tool
outputs. It is replayed by :class:`agent.llm.ScriptedClient` through the normal :class:`AgentSession`,
so outputs come from the *real* registered tools, numbers pass the same guardrail and every step is
audited. The Wave-2 backend registers the three demo flows under keys ``"1"``, ``"2"``, ``"3"``::

    register_scenario(Scenario(key="1", title_vi=..., prompt_vi=..., plan_vi=..., steps=(...), answer=fn))
    turn = run_scenario("1", registry, ctx, audit=audit_log)
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent.audit import AuditLog
from agent.llm import ScriptedClient, TurnOutput
from agent.loop import AgentSession, AgentTurn, StepEvent
from agent.template import format_answer
from agent.tools import ToolContext, ToolRegistry


@dataclass(frozen=True)
class ScenarioContext:
    user_message: str
    outputs: list[TurnOutput]

    def output(self, tool: str) -> Any:
        """Data of the last successful call of ``tool`` in this turn."""
        for o in reversed(self.outputs):
            if o.tool == tool and o.error is None:
                return o.data
        raise KeyError(f"no successful output for tool {tool!r}")


ArgsBuilder = Mapping[str, Any] | Callable[[ScenarioContext], Mapping[str, Any]]


@dataclass(frozen=True)
class ScenarioStep:
    tool: str
    args: ArgsBuilder = field(default_factory=dict)

    def build_args(self, user_message: str, outputs: list[TurnOutput]) -> dict[str, Any]:
        args = self.args(ScenarioContext(user_message, outputs)) if callable(self.args) else self.args
        return dict(args)


@dataclass(frozen=True)
class Scenario:
    key: str
    title_vi: str
    prompt_vi: str
    plan_vi: str
    steps: tuple[ScenarioStep, ...]
    answer: Callable[[ScenarioContext], Mapping[str, str]]

    def build_answer(self, user_message: str, outputs: list[TurnOutput]) -> str:
        failed = next((o for o in outputs if o.error is not None), None)
        if failed is not None:
            return format_answer(
                {
                    "Đề xuất": "Chưa thể đưa ra đề xuất cho luồng này.",
                    "Vì sao": f"Bước '{failed.tool}' gặp lỗi: {failed.error}",
                    "Độ tin cậy": "Thấp, vì thiếu kết quả công cụ.",
                    "Giả định": "Không có.",
                    "Việc cần bạn duyệt": "Không có. Vui lòng kiểm tra dữ liệu hoặc thử lại.",
                }
            )
        return format_answer(self.answer(ScenarioContext(user_message, outputs)))


class ScenarioRegistry:
    def __init__(self) -> None:
        self._scenarios: dict[str, Scenario] = {}

    def register(self, scenario: Scenario, *, replace: bool = False) -> Scenario:
        if not scenario.steps:
            raise ValueError("scenario needs at least one step")
        if scenario.key in self._scenarios and not replace:
            raise ValueError(f"scenario {scenario.key!r} already registered")
        self._scenarios[scenario.key] = scenario
        return scenario

    def get(self, key: str) -> Scenario:
        if key not in self._scenarios:
            raise KeyError(f"Kịch bản '{key}' chưa được đăng ký.")
        return self._scenarios[key]

    def keys(self) -> list[str]:
        return list(self._scenarios)


DEFAULT_SCENARIOS = ScenarioRegistry()


def register_scenario(
    scenario: Scenario, *, replace: bool = False, scenarios: ScenarioRegistry = DEFAULT_SCENARIOS
) -> Scenario:
    return scenarios.register(scenario, replace=replace)


def _session(
    scenario: Scenario,
    registry: ToolRegistry,
    ctx: ToolContext,
    audit: AuditLog | None,
    turn_id_factory: Callable[[], str] | None,
) -> AgentSession:
    missing = [s.tool for s in scenario.steps if s.tool not in registry]
    if missing:
        raise ValueError(f"scenario {scenario.key!r} uses unregistered tools: {missing}")
    return AgentSession(
        ScriptedClient(scenario),
        registry,
        ctx,
        audit=audit,
        max_tool_calls=len(scenario.steps) + 1,
        turn_id_factory=turn_id_factory,
    )


def stream_scenario(
    scenario: Scenario | str,
    registry: ToolRegistry,
    ctx: ToolContext,
    *,
    audit: AuditLog | None = None,
    scenarios: ScenarioRegistry = DEFAULT_SCENARIOS,
    turn_id_factory: Callable[[], str] | None = None,
) -> Generator[StepEvent, None, AgentTurn]:
    sc = scenarios.get(scenario) if isinstance(scenario, str) else scenario
    return _session(sc, registry, ctx, audit, turn_id_factory).stream(sc.prompt_vi)


def run_scenario(
    scenario: Scenario | str,
    registry: ToolRegistry,
    ctx: ToolContext,
    *,
    audit: AuditLog | None = None,
    scenarios: ScenarioRegistry = DEFAULT_SCENARIOS,
    turn_id_factory: Callable[[], str] | None = None,
) -> AgentTurn:
    sc = scenarios.get(scenario) if isinstance(scenario, str) else scenario
    return _session(sc, registry, ctx, audit, turn_id_factory).run(sc.prompt_vi)
