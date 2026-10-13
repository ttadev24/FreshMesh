"""FastAPI gateway: ``uv run uvicorn api.main:app --port 8100`` (see scripts/dev_api.sh).

Contract: docs/superpowers/plans/2026-10-13-freshmesh-master-plan.md "API contract"; additions and
deviations: docs/api-contract-notes.md.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent.audit import AuditLog
from agent.llm import AnthropicClient, LLMUnavailableError, ScriptedClient, llm_available
from agent.loop import AgentSession, AgentTurn
from agent.tools import ToolContext, ToolError
from api.auth import User, authenticate, current_user, issue_token
from api.config import Settings
from api.drafts import DRAFT_KINDS, SqlDraftStore
from api.errors import ApiError, install_error_handlers
from api.repo import ensure_store_access, resolve_store_id
from api.routing_service import RoutingService, make_solver_client
from api.scenarios import (
    FLOW_TITLES_VI,
    UNKNOWN_INTENT_VI,
    build_scenario,
    default_store,
    detect_intent,
    flow_message,
)
from api.services import DEFAULT_NOW_HOUR, Services, assumptions_payload, fl_summary_payload
from api.tools import build_registry, make_edit_applier
from data_sim import CHAIN_IDS, SOURCE, chain_db_path
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


class StockBody(BaseModel):
    store_id: str | None = None
    sku_ids: list[str] | None = None
    categories: list[str] | None = None
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


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    mode: Literal["llm", "scripted"] | None = None
    store_id: str | None = None


class ScenarioBody(BaseModel):
    store_id: str | None = None
    now_minute: int = Field(default=0, ge=0, le=240)


# ---------------------------------------------------------------- helpers


def _csv(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _turn_dict(turn: AgentTurn, extra: dict[str, Any]) -> dict[str, Any]:
    return {**turn.to_dict(), "events": [e.to_dict() for e in turn.events], **extra}


def create_app(settings: Settings | None = None, solver: Solver | None | object = _DEFAULT) -> FastAPI:
    """App factory. ``solver`` defaults to the routing-PL HTTP client at ``settings.solver_url``;
    tests pass a fake solver (or ``None`` = unreachable)."""
    settings = settings or Settings()
    solver_obj: Solver | None = make_solver_client(settings.solver_url) if solver is _DEFAULT else solver  # type: ignore[assignment]
    routing = RoutingService(
        settings.cache_dir,
        solver_obj,
        fleet_vehicles=settings.fleet_vehicles,
        fleet_capacity=settings.fleet_capacity,
    )
    services = Services(settings.data_dir, routing)
    drafts = SqlDraftStore(settings.data_dir)
    registry = build_registry(services, drafts)
    health_cache: dict[str, Any] = {"t": 0.0, "solver": False, "client": None}

    warm_status: dict[str, Any] = {"state": "idle", "done": 0, "total": 0, "failed": 0, "seconds": None}

    def warm_cache() -> None:
        """Pre-solve demo batches in priority order: flow 3 of each chain's first store, flow 2 transfer
        from CH3, then flow 3 of every other store (CHAIN_A first). Results persist in the routing cache."""
        jobs: list[tuple[str, str, str]] = []  # (chain_id, kind, store_id)
        rest: list[tuple[str, str, str]] = []
        for chain_id in CHAIN_IDS:
            if not chain_db_path(settings.data_dir, chain_id).exists():
                continue
            stores = [st.store_id for st in services.repo(chain_id).stores()]
            if not stores:
                continue
            jobs.append((chain_id, "routes", stores[0]))
            ch3 = [sid for sid in stores if sid.endswith("-CH3")]
            jobs += [(chain_id, "transfer", sid) for sid in ch3]
            rest += [(chain_id, "routes", sid) for sid in stores[1:]]
        jobs += rest
        warm_status.update(state="running", total=len(jobs))
        t0 = time.perf_counter()
        for chain_id, kind, store_id in jobs:
            try:
                if kind == "routes":
                    services.routing_plan(chain_id, store_id)
                else:
                    veg = services.repo(chain_id).select_skus(None, ["vegetable"])
                    services.transfer(chain_id, store_id, veg)
            except Exception as exc:  # warm-up must never break the server
                warm_status["failed"] += 1
                log.warning("cache warm-up %s %s/%s failed: %s", kind, chain_id, store_id, exc)
            warm_status["done"] += 1
        warm_status.update(state="finished", seconds=round(time.perf_counter() - t0, 1))
        log.info("routing cache warm-up: %d jobs in %.1fs", len(jobs), warm_status["seconds"])

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
        if settings.warm_cache and solver_obj is not None:
            threading.Thread(target=warm_cache, name="routing-warmup", daemon=True).start()
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
    app.state.warm_cache = warm_cache
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
        llm = llm_available()
        data_ready = all(chain_db_path(settings.data_dir, c).exists() for c in CHAIN_IDS)
        return {
            "status": "ok" if data_ready else "degraded",
            "solver": solver_up(),
            "llm": llm,
            "mode": "llm" if llm else "scripted",
            "data": data_ready,
            "routing_cache_warmup": dict(warm_status),
            "source": SOURCE,
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
        return {**user.to_dict(), "chain_name": repo.chain_name(), "store_name": store_name, "source": SOURCE}

    @app.get("/api/stores")
    def stores(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        rows = services.repo(user.chain_id).stores()
        return [s.to_dict() for s in rows if user.is_owner or s.store_id == user.store_id]

    @app.get("/api/skus")
    def skus(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        return [s.to_dict() for s in services.repo(user.chain_id).skus()]

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
        )

    @app.post("/api/markdown/suggest")
    def markdown_suggest(body: StockBody, user: User = Depends(current_user)) -> dict[str, Any]:
        sid = store_for(user, body.store_id)
        selected = services.repo(user.chain_id).select_skus(body.sku_ids, body.categories)
        return services.markdown(user.chain_id, sid, selected, now_hour=body.now_hour)

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
        return {"draft": drafts.get(user, result.data["draft_id"]), "source": SOURCE}

    @app.get("/api/drafts")
    def list_drafts(status: str | None = None, user: User = Depends(current_user)) -> dict[str, Any]:
        return {"drafts": drafts.list(user, status=status), "source": SOURCE}

    @app.get("/api/drafts/{draft_id}")
    def get_draft(draft_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        return {"draft": drafts.get(user, draft_id), "source": SOURCE}

    @app.post("/api/drafts/{draft_id}/approve")
    def approve(draft_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        draft = drafts.approve(user, draft_id)
        return {"draft": draft, "execution": draft["payload"].get("execution"), "source": SOURCE}

    @app.post("/api/drafts/{draft_id}/reject")
    def reject(draft_id: str, body: DecisionBody | None = None, user: User = Depends(current_user)) -> dict:
        return {"draft": drafts.reject(user, draft_id, (body.note if body else "")), "source": SOURCE}

    @app.patch("/api/drafts/{draft_id}")
    def patch_draft(draft_id: str, body: DraftPatch, user: User = Depends(current_user)) -> dict[str, Any]:
        draft = drafts.edit(user, draft_id, body.payload, make_edit_applier(services, user.chain_id))
        return {"draft": draft, "source": SOURCE}

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

    def scripted_session(
        user: User, flow: int, store_id: str, categories=(), now_minute: int = 0
    ) -> AgentSession:
        scenario = build_scenario(
            flow,
            services,
            chain_id=user.chain_id,
            store_id=store_id,
            categories=tuple(categories),
            now_minute=now_minute,
        )
        return AgentSession(
            ScriptedClient(scenario),
            registry,
            tool_ctx(user, store_id),
            audit=AuditLog(chain_db_path(settings.data_dir, user.chain_id)),
            max_tool_calls=len(scenario.steps) + 1,
        )

    def scripted_extra(flow: int, store_id: str) -> dict[str, Any]:
        return {
            "mode": "scripted",
            "scenario": {"flow": flow, "title_vi": FLOW_TITLES_VI[flow], "store_id": store_id},
        }

    def wants_sse(request: Request) -> bool:
        return (
            "text/event-stream" in request.headers.get("accept", "")
            or request.query_params.get("stream") == "1"
        )

    @app.post("/api/agent/scenario/{flow}")
    def scenario(
        flow: int, request: Request, body: ScenarioBody | None = None, user: User = Depends(current_user)
    ):
        if flow not in (1, 2, 3):
            raise ApiError(404, "unknown_scenario", "Kịch bản chỉ có 1, 2 hoặc 3.")
        body = body or ScenarioBody()
        repo = services.repo(user.chain_id)
        sid = default_store(flow, repo, role=user.role, own_store=user.store_id, requested=body.store_id)
        ensure_store_access(user.role, user.store_id, sid)
        session = scripted_session(user, flow, sid, now_minute=body.now_minute)
        message = flow_message(flow, sid)
        extra = scripted_extra(flow, sid)
        if wants_sse(request):
            return StreamingResponse(stream_turn(session, message, extra), media_type="text/event-stream")
        turn = session.run(message)
        return _turn_dict(turn, extra)

    @app.post("/api/agent/chat")
    def chat(body: ChatBody, user: User = Depends(current_user)):
        mode = body.mode or ("llm" if llm_available() else "scripted")
        repo = services.repo(user.chain_id)
        default_sid = store_for(user, body.store_id) if body.store_id else None
        if mode == "llm":
            try:
                client = AnthropicClient()
            except LLMUnavailableError as exc:
                raise ApiError(503, "llm_unavailable", exc.message_vi) from None
            session = AgentSession(
                client,
                registry,
                tool_ctx(user, default_sid),
                audit=AuditLog(chain_db_path(settings.data_dir, user.chain_id)),
            )
            extra: dict[str, Any] = {"mode": "llm"}
        else:
            intent = detect_intent(body.message)
            if intent is None:
                raise ApiError(422, "scripted_intent_unknown", UNKNOWN_INTENT_VI)
            requested = intent.store or body.store_id
            sid = default_store(
                intent.flow, repo, role=user.role, own_store=user.store_id, requested=requested
            )
            ensure_store_access(user.role, user.store_id, sid)
            session = scripted_session(user, intent.flow, sid, intent.categories)
            extra = scripted_extra(intent.flow, sid)
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
        return {"entries": entries, "source": SOURCE}

    @app.get("/api/network/fl")
    def network_fl(user: User = Depends(current_user)) -> dict[str, Any]:
        return fl_summary_payload(settings.data_dir)

    @app.get("/api/assumptions")
    def assumptions(user: User = Depends(current_user)) -> dict[str, Any]:
        return assumptions_payload()

    @app.get("/")
    def root() -> JSONResponse:
        return JSONResponse({"name": "FreshMesh API", "source": SOURCE})

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
