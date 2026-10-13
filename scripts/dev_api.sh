#!/usr/bin/env bash
# Run the FreshMesh API (FastAPI) on FRESHMESH_API_PORT (default 8100).
# FRESHMESH_API_RELOAD=1 enables auto-reload on code changes (off by default so a running demo/E2E session
# is not restarted while other modules are edited). Nothing is pre-computed at startup; routing results are
# cached by batch hash only after a real solve. The chat needs ANTHROPIC_API_KEY (no key: /api/health llm=false,
# chat answers 503 llm_unavailable; every other endpoint works). Data root: FRESHMESH_DATA_DIR (default data).
set -euo pipefail
cd "$(dirname "$0")/.."
# Optional local secrets (git-ignored, e.g. ANTHROPIC_API_KEY, FRESHMESH_LLM_MODEL); never printed.
if [[ -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env.local
  set +a
fi

PORT="${FRESHMESH_API_PORT:-8100}"
DATA="${FRESHMESH_DATA_DIR:-data}"
for chain in CHAIN_A CHAIN_B CHAIN_C; do
  if [[ ! -f "${DATA}/chains/${chain}.sqlite" ]]; then
    echo "Chưa có dữ liệu (${DATA}/chains/${chain}.sqlite). Chạy trước: scripts/bootstrap.sh" >&2
    exit 1
  fi
done
if [[ -z "${FRESHMESH_SECRET:-}" ]]; then
  echo "Cảnh báo: FRESHMESH_SECRET chưa đặt; dùng khóa dev cục bộ (chỉ lắng nghe 127.0.0.1)." >&2
  export FRESHMESH_ALLOW_DEV_SECRET=1
  export FRESHMESH_API_HOST="${FRESHMESH_API_HOST:-127.0.0.1}"
fi
RELOAD=()
if [[ "${FRESHMESH_API_RELOAD:-0}" == "1" ]]; then
  RELOAD=(--reload --reload-dir api --reload-dir agent --reload-dir decision --reload-dir forecasting
          --reload-dir routing --reload-dir data_sim --reload-dir provenance)
fi
exec uv run uvicorn api.main:app --host "${FRESHMESH_API_HOST:-127.0.0.1}" --port "$PORT" "${RELOAD[@]}"
