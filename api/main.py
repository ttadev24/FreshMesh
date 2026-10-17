"""FastAPI gateway: ``uv run uvicorn api.main:app --port 8100`` (see scripts/dev_api.sh).

Contract: docs/superpowers/plans/2026-10-13-freshmesh-master-plan.md "API contract"; additions and
deviations: docs/api-contract-notes.md.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent.audit import AuditLog
from agent.jev import DEFAULT_MODEL as JEV_DEFAULT_MODEL
from agent.jev import JevClient
from agent.llm import AnthropicClient, LLMClient, LLMUnavailableError, configured_model, llm_available
from agent.loop import AgentSession, AgentTurn
from agent.tools import ToolContext, ToolError
from api import provenance_view
from api.auth import User, authenticate, current_user, issue_token
from api.brief import BriefService
from api.chat_quota import ChatQuota, client_ip
from api.config import Settings
from api.drafts import DRAFT_KINDS, SqlDraftStore
from api.errors import ApiError, install_error_handlers
from api.network import build_network
from api.repo import ChainRepo, ensure_store_access, resolve_store_id
from api.road_path import RoadRouter
from api.routing_service import RoutingService, make_solver_client
from api.scenario import compare_scenario
from api.services import DEFAULT_NOW_HOUR, Services, assumptions_payload, fl_summary_payload
from api.tools import build_registry, make_edit_applier
from api.verify import run_all as run_verify
from data_sim import CHAIN_IDS, chain_db_path
from decision.frontier import GOAL_LIMITS
from forecasting.service import model_ready, resolve_model_kind
from routing.client import SolverClient
from routing.planner import Solver

log = logging.getLogger("freshmesh.api")
_DEFAULT = object()
HEALTH_TTL_S = 10.0


# ---------------------------------------------------------------- request bodies


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class InventoryBody(BaseModel):
    store_id: str | None = None
    sku_ids: list[str] | None = None
    categories: list[str] | None = None
    horizon_days: int = Field(default=1, ge=1, le=7)
    budget_vnd: float | None = Field(default=None, ge=0)
    cold_storage_units: float | None = Field(default=None, ge=0)
    # Owner goals: the cheapest frontier point meeting them is chosen, conflicts come back as a question.
    max_stockout_pct: float | None = Field(default=None, ge=0, le=100)
    min_service_pct: float | None = Field(default=None, ge=0, le=100)
    max_cost_vnd: float | None = Field(default=None, ge=0)
    max_leftover_units: float | None = Field(default=None, ge=0)


class ScenarioBody(BaseModel):
    store_id: str | None = None
    sku_ids: list[str] | None = None
    categories: list[str] | None = None
    horizon_days: int = Field(default=1, ge=1, le=7)
    promo: bool = False  # a promotion on every selected SKU
    is_holiday: bool = False  # a holiday / local event day


class StockBody(BaseModel):
    store_id: str | None = None
    sku_ids: list[str] | None = None
    categories: list[str] | None = None
    now_hour: int = Field(default=DEFAULT_NOW_HOUR, ge=6, le=21)


class MarkdownSimBody(BaseModel):
    store_id: str | None = None
    sku_id: str = Field(min_length=1, max_length=64)
    discount_pct: float = Field(ge=0, le=90)
    start_hour: int = Field(ge=6, le=21)
    now_hour: int = Field(default=DEFAULT_NOW_HOUR, ge=6, le=21)


class RoutingBody(BaseModel):
    store_id: str | None = None
    now_minute: int = Field(default=0, ge=0, le=240)


class DraftBody(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DraftPatch(BaseModel):
    payload: dict[str, Any]


class DecisionBody(BaseModel):
    note: str = Field(default="", max_length=500)


class ApproveBody(BaseModel):
    revision: int | None = Field(default=None, ge=0)  # payload.revision the approver saw (stale -> 409)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    store_id: str | None = None


# ---------------------------------------------------------------- helpers


def _csv(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _turn_dict(turn: AgentTurn, extra: dict[str, Any]) -> dict[str, Any]:
    return {**turn.to_dict(), "events": [e.to_dict() for e in turn.events], **extra}


def row_provenance(repo: ChainRepo, ids: list[str | None]) -> dict[str | None, dict[str, list[str]]]:
    """Per-row provenance with one registry load: raw row id → ``{sources, source_labels_vi}``."""
    distinct = list(dict.fromkeys(ids))
    labelled = repo.labelled(distinct)
    by_id = dict(zip(labelled["sources"], labelled["source_labels_vi"], strict=True))
    out = {}
    for raw in distinct:
        key = repo.labelled_id(raw)
        out[raw] = {"sources": [key], "source_labels_vi": [by_id[key]]}
    return out


def create_app(
    settings: Settings | None = None,
    solver: Solver | None | object = _DEFAULT,
    llm_client_factory: Callable[[], LLMClient] | None = None,
) -> FastAPI:
    """App factory. ``solver`` defaults to the routing-PL HTTP client at ``settings.solver_url``;
    tests pass a fake solver (or ``None`` = unreachable). ``llm_client_factory`` defaults to the real
    :class:`AnthropicClient` (raises :class:`LLMUnavailableError` without a key → 503 ``llm_unavailable``);
    tests inject a deterministic fake LLM. There is no scripted fallback."""
    settings = settings or Settings()
    solver_obj: Solver | None = make_solver_client(settings.solver_url) if solver is _DEFAULT else solver  # type: ignore[assignment]
    road = RoadRouter(settings.vietmap_route_key, settings.cache_dir) if settings.vietmap_route_key else None
    routing = RoutingService(
        settings.cache_dir,
        solver_obj,
        fleet_vehicles=settings.fleet_vehicles,
        fleet_capacity=settings.fleet_capacity,
        road=road,
    )
    services = Services(settings.data_dir, routing)
    jev_client: JevClient | None = (
        JevClient(settings.jev_api_key, model=settings.jev_model or JEV_DEFAULT_MODEL)
        if settings.jev_api_key
        else None
    )
    drafts = SqlDraftStore(settings.data_dir, settings.approval_policy)
    registry = build_registry(services, drafts)
    briefs = BriefService(services)
    chat_quota = ChatQuota(
        settings.data_dir / "usage.sqlite",
        settings.chat_per_ip_daily,
        settings.chat_global_daily,
        salt=settings.secret,
    )
    health_cache: dict[str, Any] = {"t": 0.0, "solver": False, "client": None}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
        kind = resolve_model_kind(None)
        for chain_id in CHAIN_IDS:
            path = chain_db_path(settings.data_dir, chain_id)
            if path.exists():
                AuditLog(path)  # create append-only triggers once
            if not model_ready(chain_id, settings.data_dir, kind):
                log.warning(
                    "forecast model (%s) for %s is missing under %s/models: forecasts for this chain return "
                    "503 model_not_ready. Run scripts/bootstrap.sh to generate data and train the models.",
                    kind,
                    chain_id,
                    settings.data_dir,
                )
        yield

    docs_on = os.environ.get("FRESHMESH_ENABLE_DOCS") == "1"
    app = FastAPI(
        title="FreshMesh API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_on else None,
    )
    app.state.settings = settings
    app.state.services = services
    app.state.drafts = drafts
    app.state.registry = registry
    install_error_handlers(app)

    def store_for(user: User, raw: str | None) -> str:
        repo = services.repo(user.chain_id)
        store_id = resolve_store_id(repo, raw, default=user.store_id)
        ensure_store_access(user.role, user.store_id, store_id)
        return store_id

    def tool_ctx(user: User, default_store_id: str | None = None) -> ToolContext:
        return ToolContext(
            chain_id=user.chain_id,
            actor=user.username,
            store_id=user.store_id,
            extras={"role": user.role, "default_store_id": default_store_id or user.store_id},
        )

    def solver_up() -> bool:
        now = time.monotonic()
        if now - health_cache["t"] > HEALTH_TTL_S:
            if solver_obj is None:
                ok = False
            elif routing.in_flight > 0:
                ok = True  # busy solving: reachable, /health is blocked until the solve ends
            elif isinstance(solver_obj, SolverClient):
                if health_cache["client"] is None:  # one short-timeout client, reused by every check
                    health_cache["client"] = SolverClient(settings.solver_url, timeout_s=2.0)
                ok = health_cache["client"].health()
            else:
                ok = bool(getattr(solver_obj, "health", lambda: True)())
            health_cache.update(t=now, solver=ok)
        return bool(health_cache["solver"])

    # ------------------------------------------------------------ public

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
            "chat_quota": {"per_ip_daily": chat_quota.per_ip_daily, "global_daily": chat_quota.global_daily},
        }

    @app.post("/api/auth/login")
    def login(body: LoginBody) -> dict[str, Any]:
        user = authenticate(settings.data_dir, body.username, body.password)
        token = issue_token(user, settings.secret, settings.token_ttl_s)
        return {
            "token": token,
            "token_type": "bearer",
            "expires_in": settings.token_ttl_s,
            "user": user.to_dict(),
        }

    # ------------------------------------------------------------ chain data

    @app.get("/api/me")
    def me(user: User = Depends(current_user)) -> dict[str, Any]:
        repo = services.repo(user.chain_id)
        store_name = repo.store(user.store_id).name if user.store_id else None
        return {
            **user.to_dict(),
            "chain_name": repo.chain_name(),
            "store_name": store_name,
            "approval": dataclasses.asdict(settings.approval_policy),  # limits after which the owner decides
        }

    @app.get("/api/brief")
    def brief(store_id: str | None = None, user: User = Depends(current_user)) -> dict[str, Any]:
        """Morning decision brief (api/brief.py); owners get chain scope, managers their own store."""
        store = services.repo(user.chain_id).store(store_for(user, store_id))
        return briefs.get(user.chain_id, store, user.is_owner)

    @app.get("/api/verify/run")
    def verify_run(user: User = Depends(current_user)) -> dict[str, Any]:
        """'Kiểm chứng 90 giây': the safety rules checked live on the real guard code (api/verify.py)."""
        return run_verify(settings.data_dir, settings.approval_policy)

    @app.get("/api/network")
    def network(user: User = Depends(current_user)) -> dict[str, Any]:
        own = None if user.is_owner else [user.store_id]
        return build_network(
            services, settings.data_dir, user.chain_id, own, briefs.flows_today(user.chain_id)
        )

    @app.get("/api/stores")
    def stores(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        repo = services.repo(user.chain_id)
        rows = [s for s in repo.stores() if user.is_owner or s.store_id == user.store_id]
        prov = row_provenance(repo, [s.source for s in rows])
        return [{**s.to_dict(), **prov[s.source]} for s in rows]

    @app.get("/api/skus")
    def skus(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        repo = services.repo(user.chain_id)
        rows = repo.skus()
        prov = row_provenance(repo, [s.source for s in rows])
        return [{**s.to_dict(), **prov[s.source]} for s in rows]

    @app.get("/api/forecast")
    def forecast(
        store_id: str | None = None,
        sku_ids: str | None = None,
        categories: str | None = None,
        horizon_days: int = 1,
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        sid = store_for(user, store_id)
        selected = services.repo(user.chain_id).select_skus(_csv(sku_ids), _csv(categories))
        return services.forecast(user.chain_id, sid, selected, horizon_days)

    @app.post("/api/inventory/plan")
    def inventory_plan(body: InventoryBody, user: User = Depends(current_user)) -> dict[str, Any]:
        sid = store_for(user, body.store_id)
        selected = services.repo(user.chain_id).select_skus(body.sku_ids, body.categories)
        return services.inventory_plan(
            user.chain_id,
            sid,
            selected,
            horizon_days=body.horizon_days,
            budget_vnd=body.budget_vnd,
            cold_storage_units=body.cold_storage_units,
            goal={k: getattr(body, k) for k in GOAL_LIMITS},
        )

    @app.post("/api/inventory/scenario")
    def inventory_scenario(body: ScenarioBody, user: User = Depends(current_user)) -> dict[str, Any]:
        sid = store_for(user, body.store_id)
        selected = services.repo(user.chain_id).select_skus(body.sku_ids, body.categories)
        scenario = {"promo": body.promo, "is_holiday": body.is_holiday}
        return compare_scenario(
            services, user.chain_id, sid, selected, horizon_days=body.horizon_days, scenario=scenario
        )

    @app.post("/api/markdown/suggest")
    def markdown_suggest(body: StockBody, user: User = Depends(current_user)) -> dict[str, Any]:
        sid = store_for(user, body.store_id)
        selected = services.repo(user.chain_id).select_skus(body.sku_ids, body.categories)
        return services.markdown(user.chain_id, sid, selected, now_hour=body.now_hour)

    @app.post("/api/markdown/simulate")
    def markdown_simulate(body: MarkdownSimBody, user: User = Depends(current_user)) -> dict[str, Any]:
        """What-if of one flat discount from start_hour, next to the recommended schedule (slider)."""
        sid = store_for(user, body.store_id)
        sku = services.repo(user.chain_id).select_skus([body.sku_id], [])[0]
        return services.markdown_simulate(
            user.chain_id, sid, sku, discount_pct=body.discount_pct, start_hour=body.start_hour,
            now_hour=body.now_hour,
        )  # fmt: skip

    @app.post("/api/transfer/plan")
    def transfer_plan(body: StockBody, user: User = Depends(current_user)) -> dict[str, Any]:
        sid = store_for(user, body.store_id)
        cats = body.categories if (body.categories or body.sku_ids) else ["vegetable"]
        selected = services.repo(user.chain_id).select_skus(body.sku_ids, cats)
        return services.transfer(user.chain_id, sid, selected, now_hour=body.now_hour)

    @app.post("/api/routing/plan")
    def routing_plan(body: RoutingBody, user: User = Depends(current_user)) -> dict[str, Any]:
        sid = store_for(user, body.store_id)
        return services.routing_plan(user.chain_id, sid, body.now_minute)

    # ------------------------------------------------------------ drafts

    @app.post("/api/drafts", status_code=201)
    def create_draft(body: DraftBody, user: User = Depends(current_user)) -> dict[str, Any]:
        if body.kind not in DRAFT_KINDS:
            raise ApiError(
                422, "bad_draft_kind", f"Loại bản nháp phải là một trong: {', '.join(DRAFT_KINDS)}."
            )
        sid = store_for(user, body.payload.get("store_id"))
        try:
            result = registry.call(body.kind, {**body.payload, "store_id": sid}, tool_ctx(user, sid))
        except ToolError as exc:
            raise ApiError(422, "draft_invalid", exc.message_vi) from None
        return {"draft": drafts.get(user, result.data["draft_id"])}

    @app.get("/api/drafts")
    def list_drafts(status: str | None = None, user: User = Depends(current_user)) -> dict[str, Any]:
        return {"drafts": drafts.list(user, status=status)}

    @app.get("/api/drafts/{draft_id}")
    def get_draft(draft_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        return {"draft": drafts.get(user, draft_id)}

    @app.post("/api/drafts/{draft_id}/approve")
    def approve(
        draft_id: str, body: ApproveBody | None = None, user: User = Depends(current_user)
    ) -> dict[str, Any]:
        draft = drafts.approve(user, draft_id, body.revision if body else None)
        return {"draft": draft, "execution": draft["payload"].get("execution")}

    @app.post("/api/drafts/{draft_id}/undo")
    def undo(draft_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        return {"draft": drafts.undo(user, draft_id)}

    @app.post("/api/drafts/{draft_id}/reject")
    def reject(draft_id: str, body: DecisionBody | None = None, user: User = Depends(current_user)) -> dict:
        return {"draft": drafts.reject(user, draft_id, (body.note if body else ""))}

    @app.patch("/api/drafts/{draft_id}")
    def patch_draft(draft_id: str, body: DraftPatch, user: User = Depends(current_user)) -> dict[str, Any]:
        draft = drafts.edit(user, draft_id, body.payload, make_edit_applier(services, user.chain_id))
        return {"draft": draft}

    # ------------------------------------------------------------ agent

    def stream_turn(session: AgentSession, message: str, extra: dict[str, Any]) -> Iterator[str]:
        gen = session.stream(message)
        try:
            for event in gen:
                yield _sse(event.type, event.data)
        except Exception:
            log.exception("agent turn failed")
            yield _sse(
                "error",
                {
                    "error": {
                        "code": "agent_error",
                        "message_vi": "Lượt trả lời bị lỗi giữa chừng, vui lòng thử lại.",
                    }
                },
            )
            return
        assert session.last_turn is not None
        yield _sse("final", _turn_dict(session.last_turn, extra))

    @app.post("/api/agent/chat")
    def chat(body: ChatBody, request: Request, user: User = Depends(current_user)):
        default_sid = store_for(user, body.store_id) if body.store_id else None
        try:
            client = llm_client_factory() if llm_client_factory is not None else AnthropicClient()
        except LLMUnavailableError as exc:
            raise ApiError(503, "llm_unavailable", exc.message_vi) from None
        # Counted only once the LLM is usable, so a 503 never costs the visitor a turn.
        peer = request.client.host if request.client else None
        decision = chat_quota.consume(client_ip(peer, request.headers))
        if not decision.allowed:
            raise ApiError(429, "chat_quota_exceeded", decision.message_vi())
        session = AgentSession(
            client,
            registry,
            tool_ctx(user, default_sid),
            audit=AuditLog(chain_db_path(settings.data_dir, user.chain_id)),
            jev_client=jev_client if settings.jev_guardrail else None,
        )
        extra = {"model": getattr(client, "model", getattr(client, "name", ""))}
        return StreamingResponse(stream_turn(session, body.message, extra), media_type="text/event-stream")

    # ------------------------------------------------------------ tabs

    @app.get("/api/audit")
    def audit(
        limit: int = 200, event: str | None = None, user: User = Depends(current_user)
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 1000))
        sql = "SELECT audit_id, chain_id, ts, actor, event, payload_json FROM audit_log WHERE chain_id = ?"
        params: list[Any] = [user.chain_id]
        if event:
            sql += " AND event = ?"
            params.append(event)
        if not user.is_owner:
            # Own entries, draft/decision entries of the manager's store, and tool calls whose server-computed
            # output is about that store (`output.store_id` is resolved and access-checked by the server; the
            # LLM-supplied `input.store_id` is never used for scoping).
            sql += (
                " AND (actor = ? OR json_extract(payload_json, '$.store_id') = ?"
                " OR (event = 'tool_call' AND json_extract(payload_json, '$.output.store_id') = ?))"
            )
            params += [user.username, user.store_id, user.store_id]
        sql += " ORDER BY audit_id DESC LIMIT ?"
        params.append(limit)
        with services.repo(user.chain_id).read() as con:
            rows = con.execute(sql, params).fetchall()
        entries = [
            {
                "audit_id": r["audit_id"],
                "chain_id": r["chain_id"],
                "ts": r["ts"],
                "actor": r["actor"],
                "event": r["event"],
                "payload": json.loads(r["payload_json"] or "{}"),
            }
            for r in rows
        ]
        return {"entries": entries}

    @app.get("/api/network/fl")
    def network_fl(user: User = Depends(current_user)) -> dict[str, Any]:
        return fl_summary_payload(settings.data_dir)

    @app.get("/api/provenance")
    def provenance_list(user: User = Depends(current_user)) -> dict[str, Any]:
        return {"datasets": provenance_view.datasets(settings.data_dir)}

    @app.get("/api/provenance/prompts/{prompt_id}")
    def provenance_prompt(prompt_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        # Documentation of how data was generated (no customer data): any authenticated role may read it.
        return provenance_view.prompt(prompt_id, settings.data_dir)

    @app.get("/api/provenance/{dataset_id}")
    def provenance_item(dataset_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        return provenance_view.dataset(dataset_id, settings.data_dir)

    @app.get("/api/assumptions")
    def assumptions(user: User = Depends(current_user)) -> dict[str, Any]:
        return assumptions_payload()

    @app.get("/")
    def root() -> JSONResponse:
        return JSONResponse({"name": "FreshMesh API"})

    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """Lazy ASGI entry point (`uvicorn api.main:app`): importing the module must not require the secret."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
