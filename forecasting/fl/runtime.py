"""Run Flower FedAvg + FedPer (+ optional central DP) across chains, in one process.

Flower mode used (``flwr`` 1.39): the message-based ``flwr.serverapp.strategy.FedAvg`` (wrapped in
``DifferentialPrivacyClientSideFixedClipping`` when DP is on) drives real ``flwr.clientapp.ClientApp`` objects
(with Flower's ``fixedclipping_mod``). The transport is ``InProcessGrid``, a small implementation of Flower's
``Grid`` interface that hands each ``Message`` to the destination ``ClientApp`` in the same process and deep-
copies contents at the boundary, so server and clients never share objects. Flower's own simulation engine
needs Ray, which is not installed (``flwr/server/superlink/fleet/vce/backend`` only ships ``raybackend``); a
SuperLink/SuperNode deployment would run the same ``ClientApp`` and strategy code over gRPC but needs one
long-lived process per chain, which this demo does not start."""

from __future__ import annotations

import copy
import json
import logging
import math
import uuid
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from flwr.app import ArrayRecord, ConfigRecord, Context, Message, RecordDict
from flwr.clientapp import ClientApp
from flwr.common.constant import SUPERLINK_NODE_ID
from flwr.serverapp.grid import Grid
from flwr.serverapp.strategy import DifferentialPrivacyClientSideFixedClipping, FedAvg
from flwr.supercore.run import Run
from flwr.supercore.task_identity import TaskIdentity

from forecasting.fl.client import (
    ChainClient,
    FLConfig,
    add_sums,
    body_size,
    build_client_app,
    new_model,
)
from forecasting.fl.dp import noise_multiplier_for_epsilon, zcdp_epsilon

RUN_ID = 1


class InProcessGrid(Grid):
    """Flower ``Grid`` that delivers messages to in-process ``ClientApp`` objects (one ``Context`` per
    node, so ``context.state`` persists across rounds exactly as on a SuperNode)."""

    def __init__(self, apps: dict[int, tuple[ClientApp, dict]]) -> None:
        self._apps = {nid: app for nid, (app, _) in apps.items()}
        self._contexts = {
            nid: Context(run_id=RUN_ID, node_id=nid, node_config=dict(cfg), state=RecordDict(), run_config={})
            for nid, (_, cfg) in apps.items()
        }
        self._replies: dict[str, Message] = {}
        self._run: Run | None = None

    def set_run(self, run: Run) -> None:
        self._run = run

    @property
    def run(self) -> Run:
        if self._run is None:
            raise RuntimeError("run is not set")
        return self._run

    def create_message(
        self,
        content: RecordDict,
        message_type: str,
        dst_node_id: int,
        group_id: str,
        ttl: float | None = None,
    ) -> Message:
        return Message(content, dst_node_id, message_type, ttl=ttl, group_id=group_id)

    def get_node_ids(self) -> Iterable[int]:
        return list(self._apps)

    def push_messages(self, messages: Iterable[Message]) -> Iterable[str]:
        ids = []
        for msg in messages:
            msg.metadata.__dict__["_message_id"] = str(uuid.uuid4())
            dst = msg.metadata.dst_node_id
            inbound = Message(
                copy.deepcopy(msg.content), dst, msg.metadata.message_type, group_id=msg.metadata.group_id
            )
            inbound.metadata.__dict__["_message_id"] = msg.metadata.message_id
            reply = self._apps[dst](inbound, self._contexts[dst])
            out = Message(copy.deepcopy(reply.content), reply_to=msg)
            self._replies[msg.metadata.message_id] = out
            ids.append(msg.metadata.message_id)
        return ids

    def pull_messages(self, message_ids: Iterable[str]) -> Iterable[Message]:
        # Flower samples nodes with ``random.sample``; replies are returned in node order so that the
        # floating-point aggregation (and hence every run) is deterministic.
        replies = [self._replies.pop(i) for i in list(message_ids) if i in self._replies]
        return sorted(replies, key=lambda m: m.metadata.src_node_id)

    def send_and_receive(
        self, messages: Iterable[Message], *, timeout: float | None = None
    ) -> Iterable[Message]:
        return self.pull_messages(self.push_messages(messages))


@contextmanager
def _flower_task(level: int = logging.WARNING):
    """Set Flower's per-process task identity (as ``flwr.server.compat.app`` does for a ServerApp) and
    quiet its INFO logging for the duration of the run."""
    logger = logging.getLogger("flwr")
    old_level = logger.level
    logger.setLevel(level)
    TaskIdentity.task_id = 1
    TaskIdentity.run_id = RUN_ID
    TaskIdentity.node_id = SUPERLINK_NODE_ID
    try:
        yield
    finally:
        logger.setLevel(old_level)


@dataclass
class FLResult:
    chain_ids: list[str]
    sums: dict[str, dict[str, float]]  # per chain, aggregate evaluation sums (see client.eval_sums)
    pooled: dict[str, float]
    train_loss: list[float]  # weighted mean client training loss per round
    update_norms: list[float]  # weighted mean L2 norm of client body updates per round (non-DP runs only)
    epsilon: float | None
    noise_multiplier: float | None
    config: FLConfig
    seed: int
    window: str


def round_lr(cfg: FLConfig, rnd: int) -> float:
    """Cosine decay of the local learning rate over rounds (round 1 uses ``cfg.lr``)."""
    return cfg.lr * 0.5 * (1.0 + math.cos(math.pi * (rnd - 1) / max(cfg.rounds, 1)))


class _ScheduledFedAvg(FedAvg):
    """FedAvg that sends the per-round learning rate (cosine schedule) in the train ``ConfigRecord``."""

    def __init__(self, cfg: FLConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cfg = cfg

    def configure_train(self, server_round: int, arrays: ArrayRecord, config: ConfigRecord, grid: Grid):
        config["lr"] = round_lr(self._cfg, server_round)
        return super().configure_train(server_round, arrays, config, grid)


def run_federated(
    chain_ids: Sequence[str],
    data_dir: Path,
    *,
    config: FLConfig | None = None,
    seed: int = 0,
    window: str = "test",
    save: bool = False,
    clients: dict[str, ChainClient] | None = None,
) -> FLResult:
    """FedAvg on the shared body + FedPer heads for ``chain_ids``; returns evaluation sums per chain.

    ``save=True`` makes every client write ``data_dir/models/<chain>.fl.npz/.json`` (only sensible on the
    ``test`` window). ``clients`` lets callers reuse prepared ``ChainClient`` objects (must match
    seed/window).
    """
    cfg = config or FLConfig()
    data_dir = Path(data_dir)
    chain_ids = list(chain_ids)
    if not chain_ids:
        raise ValueError("need at least one chain")
    prepared = {
        c: (clients or {}).get(c)
        or ChainClient.load(c, data_dir, window=window, seed=seed, max_train_rows=cfg.max_train_rows)
        for c in chain_ids
    }
    n = len(chain_ids)
    dp = cfg.dp_epsilon is not None
    z = noise_multiplier_for_epsilon(cfg.dp_epsilon, cfg.rounds, cfg.dp_delta) if dp else None
    eps = zcdp_epsilon(z, cfg.rounds, cfg.dp_delta) if z is not None else None
    uniform = dp or cfg.weighting == "uniform"
    if cfg.weighting not in ("samples", "uniform"):
        raise ValueError(f"unknown weighting {cfg.weighting!r}")

    node_of = {c: i + 1 for i, c in enumerate(chain_ids)}
    apps = {
        node_of[c]: (
            build_client_app(prepared[c], cfg, seed=seed, dp=dp),
            {"chain-id": c, "data-dir": str(data_dir)},
        )
        for c in chain_ids
    }
    grid = InProcessGrid(apps)
    init = new_model(cfg, seed).get_weights()[: body_size(cfg.hidden)]
    train_config = ConfigRecord({"local-epochs": cfg.local_epochs, "uniform-weight": uniform, "lr": cfg.lr})
    run_info = {
        "strategy": "FedAvg (shared body) + FedPer (local head)",
        "flower_mode": "flwr ServerApp strategy + ClientApp over an in-process Grid (no Ray)",
        "chains": chain_ids,
        "rounds": cfg.rounds,
        "config": cfg.to_json(),
        "dp": None
        if z is None
        else {
            "epsilon": eps,
            "delta": cfg.dp_delta,
            "noise_multiplier": z,
            "clip_norm": cfg.clip_norm,
            "accountant": "zCDP of the Gaussian mechanism, R rounds, no subsampling",
        },
    }
    # Flower's DP wrapper draws its noise from numpy's global generator; seed it for reproducibility.
    np.random.seed(seed)
    with _flower_task():
        fedavg = _ScheduledFedAvg(
            cfg,
            fraction_train=1.0,
            fraction_evaluate=0.0,
            min_train_nodes=n,
            min_evaluate_nodes=0,
            min_available_nodes=n,
        )
        strategy = (
            DifferentialPrivacyClientSideFixedClipping(fedavg, z, cfg.clip_norm, n)
            if z is not None
            else fedavg
        )
        result = strategy.start(
            grid=grid, initial_arrays=ArrayRecord(init), num_rounds=cfg.rounds, train_config=train_config
        )
        final = result.arrays
        msgs = [
            Message(
                RecordDict(
                    {
                        "arrays": final,
                        "config": ConfigRecord({"save": save, "run-info": json.dumps(run_info)}),
                    }
                ),
                node_of[c],
                "query.finalize",
            )
            for c in chain_ids
        ]
        replies = list(grid.send_and_receive(msgs))
    chain_of = {v: k for k, v in node_of.items()}
    sums: dict[str, dict[str, float]] = {}
    for reply in replies:
        if reply.has_error():
            raise RuntimeError(f"client {chain_of[reply.metadata.src_node_id]} failed: {reply.error.reason}")
        sums[chain_of[reply.metadata.src_node_id]] = dict(reply.content["metrics"])
    rounds_metrics = [m for _, m in sorted(result.train_metrics_clientapp.items())]
    losses = [float(m["train-loss"]) for m in rounds_metrics]
    norms = [float(m["update-norm"]) for m in rounds_metrics if "update-norm" in m]
    return FLResult(
        chain_ids=chain_ids,
        sums={c: sums[c] for c in chain_ids},
        pooled=add_sums(*sums.values()),
        train_loss=losses,
        update_norms=norms,
        epsilon=eps,
        noise_multiplier=z,
        config=cfg,
        seed=seed,
        window=window,
    )
