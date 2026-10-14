"""Runtime settings of the API, read from environment variables (see README "Chạy toàn bộ hệ thống")."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_SECRET = "freshmesh-dev-secret-change-me-local-only"
MIN_SECRET_LEN = 32
DEFAULT_SOLVER_URL = "http://localhost:8000"

# Delivery fleet per store for the online batch (not in the simulated data; API-level assumption,
# documented in docs/api-contract-notes.md): 4 motorbikes, 30 units each.
FLEET_VEHICLES = 4
FLEET_CAPACITY = 30


def _env_file_value(key: str) -> str | None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def default_solver_url() -> str:
    """Same discovery order as routing.cli: env URL, env port, `.env`, then the compose default."""
    url = os.environ.get("FRESHMESH_SOLVER_URL", "").strip()
    if url:
        return url
    port = os.environ.get("FRESHMESH_SOLVER_PORT", "").strip()
    if port:
        return f"http://localhost:{port}"
    return _env_file_value("FRESHMESH_SOLVER_URL") or DEFAULT_SOLVER_URL


def _secret() -> str:
    secret = os.environ.get("FRESHMESH_SECRET", "").strip()
    if secret:
        if len(secret) < MIN_SECRET_LEN:
            raise RuntimeError(f"FRESHMESH_SECRET phải có ít nhất {MIN_SECRET_LEN} ký tự.")
        return secret
    if os.environ.get("FRESHMESH_ALLOW_DEV_SECRET") == "1":
        log.warning("FRESHMESH_ALLOW_DEV_SECRET=1: using the development secret (local use only)")
        return DEV_SECRET
    raise RuntimeError(
        "FRESHMESH_SECRET chưa được đặt. Đặt khóa ký token (>= 32 ký tự) hoặc dùng "
        "FRESHMESH_ALLOW_DEV_SECRET=1 cho môi trường dev cục bộ."
    )


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("FRESHMESH_DATA_DIR", "data")))
    secret: str = field(default_factory=_secret)
    token_ttl_s: int = field(default_factory=lambda: int(os.environ.get("FRESHMESH_TOKEN_TTL_S", "28800")))
    solver_url: str = field(default_factory=default_solver_url)
    # VietMap Route API key (server-side secret): road paths on the map; empty = labelled straight segments.
    vietmap_route_key: str = field(
        default_factory=lambda: os.environ.get("FRESHMESH_VIETMAP_ROUTE_KEY", "").strip(), repr=False
    )
    fleet_vehicles: int = FLEET_VEHICLES
    fleet_capacity: int = FLEET_CAPACITY

    cache_root: Path | None = field(
        default_factory=lambda: (
            Path(os.environ["FRESHMESH_CACHE_DIR"]) if os.environ.get("FRESHMESH_CACHE_DIR") else None
        )
    )

    @property
    def cache_dir(self) -> Path:
        return self.cache_root or self.data_dir / "cache"
