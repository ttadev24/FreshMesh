from dataclasses import dataclass

import httpx


class SolverError(RuntimeError):
    pass


@dataclass(frozen=True)
class SolverResponse:
    objective: float
    vehicles: int
    runtime: float
    routes: list[list[str]]
    raw_routes: list[list[int]]
    delivery_nodes: list[int]


class SolverClient:
    """Client for the routing-PL FastAPI service (POST /solve)."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 320.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._http = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def solve(self, instance_text: str, solver: str = "paco", size: str = "small") -> SolverResponse:
        payload = {"instance_content": instance_text, "solver": solver, "size": size}
        try:
            resp = self._http.post("/solve", json=payload)
        except httpx.TimeoutException as e:
            raise SolverError(f"solver timeout: {e}") from e
        except httpx.HTTPError as e:
            raise SolverError(f"cannot reach solver: {e}") from e
        if resp.status_code != 200:
            raise SolverError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if not data.get("success"):
            raise SolverError(data.get("error_message") or "solver reported failure")
        return SolverResponse(
            objective=float(data["objective"]),
            vehicles=int(data["vehicles"]),
            runtime=float(data["runtime"]),
            routes=data["routes"],
            raw_routes=data["raw_routes"],
            delivery_nodes=data["delivery_nodes"],
        )

    def health(self) -> bool:
        try:
            return self._http.get("/health").status_code == 200
        except httpx.HTTPError:
            return False
