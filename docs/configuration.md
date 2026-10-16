# Configuration and troubleshooting

The default local stack is **web :3100 → API :8100 → solver :8000**. Run commands from the repository root unless indicated otherwise.

## Environment files

| File | Loaded by | Purpose |
| --- | --- | --- |
| `.env` | Docker Compose; selected solver settings are also read by Python | Solver host port and URL |
| `.env.local` | `scripts/dev_api.sh` | API secrets and optional integrations |
| `web/.env.local` | Next.js | Web API proxy and browser map key |

Examples are committed as `.env.example`, `.env.local.example`, and `web/.env.local.example`. Copy only the examples you need, and preserve any existing local files. Do not commit filled-in credentials. The API launcher sources `.env.local` as Bash, so values must be shell-safe and the file must be trusted.

For the default local demo, none of these files is required. Optional integrations are disabled until configured.

## API settings

| Variable | Default / requirement | Purpose |
| --- | --- | --- |
| `FRESHMESH_API_PORT` | `8100` | Port used by `scripts/dev_api.sh` |
| `FRESHMESH_API_HOST` | `127.0.0.1` | API bind address in the development script |
| `FRESHMESH_API_RELOAD` | `0` | Set to `1` for development reload |
| `FRESHMESH_DATA_DIR` | `data` | Chain databases and models; also used by bootstrap |
| `FRESHMESH_SECRET` | At least 32 characters | Token-signing secret; required for direct API startup unless development mode is explicitly enabled |
| `FRESHMESH_ALLOW_DEV_SECRET` | Unset | `1` allows the built-in local development secret |
| `FRESHMESH_TOKEN_TTL_S` | `28800` | Token lifetime in seconds |
| `FRESHMESH_ENABLE_DOCS` | Unset | `1` enables `/docs` and `/openapi.json` |
| `FRESHMESH_SOLVER_URL` | `http://localhost:8000` | Solver endpoint; can also be discovered from root `.env` |
| `FRESHMESH_CACHE_DIR` | `<data directory>/cache` | Route and related cache storage |
| `FRESHMESH_VIETMAP_ROUTE_KEY` | Empty | Private VietMap key for motorcycle road geometry |
| `ANTHROPIC_API_KEY` | Empty | Required for Claude chat |
| `FRESHMESH_LLM_MODEL` | `claude-sonnet-5-5` in the code | Claude model identifier; use a model supported by your account and this client |
| `FRESHMESH_LLM_EFFORT` | `medium` | Requested model effort |
| `FRESHMESH_JEV_API_KEY` | Empty | Optional OpenRouter credential for Jev |
| `FRESHMESH_JEV_MODEL` | `typesafe/jev-1.13` in the client | Optional Jev model override |
| `FRESHMESH_JEV_GUARDRAIL` | Unset | `1` enables the guardrail when credentials are present |
| `FRESHMESH_CHAT_PER_IP_DAILY` | `20` | Daily chat quota per client address; `0` disables it |
| `FRESHMESH_CHAT_GLOBAL_DAILY` | `300` | Daily chat quota across the site; `0` disables it |

Generate a signing secret with `openssl rand -hex 32` and store it locally. The development script allows its built-in secret if none is provided; use that only for a local demo.

Running `uv run uvicorn api.main:app` directly does **not** source the root `.env.local`. Export required variables yourself when bypassing the script.

## Web and solver settings

| Variable | Location | Default / behavior |
| --- | --- | --- |
| `FRESHMESH_API_URL` | Web environment | `http://localhost:8100`; target of the `/api/*` rewrite |
| `NEXT_PUBLIC_VIETMAP_API_KEY` | Web environment | Browser-visible key for map tiles/style |
| `HOST` | Web command environment | `127.0.0.1` for `npm run dev` and `npm run start` |
| `FRESHMESH_SOLVER_PORT` | Root `.env` / Compose environment | `8000` on the host |
| `FRESHMESH_STREAMLIT_PORT` | Root `.env` / Compose environment | `8501`; upstream solver comparison interface |

If changing the solver port, keep its URL consistent:

```dotenv
FRESHMESH_SOLVER_PORT=8001
FRESHMESH_SOLVER_URL=http://localhost:8001
FRESHMESH_STREAMLIT_PORT=8501
```

The Python API checks an exported solver URL, then an exported solver port, then the URL in `.env`, then port 8000. Setting only a port inside `.env` does not change the API URL.

A browser map key is public by design; restrict it in the provider console. The route key is separate and must stay server-side. Neither key changes the solver's distance/arrival-time estimates.

## Production web build

```bash
(cd web && npm run build && npm run start)
```

Build with the intended web environment. Changing `NEXT_PUBLIC_*` requires rebuilding. Configure the API origin before building as well. Review [Security](../SECURITY.md) before exposing the application beyond localhost; these commands alone do not configure a complete hosted deployment.

## Health and troubleshooting

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8100/api/health
```

| Symptom | What to check |
| --- | --- |
| Docker build cannot find solver files | Run `git submodule update --init --recursive`. |
| Port is already allocated | Update the host port and solver URL together, then recreate the Compose service. |
| API reports missing chain databases | Run `scripts/bootstrap.sh --skip-fl`; ensure API and bootstrap use the same data directory. |
| API refuses to start without a secret | Use `scripts/dev_api.sh` for a local demo or export a valid `FRESHMESH_SECRET`. |
| Chat returns `503 llm_unavailable` | Add `ANTHROPIC_API_KEY` to root `.env.local`, confirm account/model access, and restart the API. |
| Map shows missing configuration | Configure the web map key and restart/rebuild Next.js. |
| Map has straight connections | Configure the server route key; inspect `path_source` for the fallback reason. |
| FL endpoint returns `503 fl_not_ready` | Generate FL models with the full bootstrap; local forecasts are separate. |
| Browser API calls fail after changing the API port | Update `FRESHMESH_API_URL` in the web environment and restart/rebuild. |
| Initial route request is slow | Check solver logs with `docker compose logs solver`; a cold solve is computed on demand. |

Most API endpoints, including provenance, require authentication. Use the UI or an authenticated client. The provenance CLI can inspect local source records without an API login.
