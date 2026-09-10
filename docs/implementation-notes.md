# SRGE AI Workspace — implementation notes

Status: Phase 3 in progress. This is an independent project, **not maintained
by or affiliated with the OpenCode project**.

## Phase 3 — done this session
- **`/user/opencode/{path}` proxy route**: forwards to the user's runtime with
  the stored `OPENCODE_SERVER_PASSWORD` (basic auth), streams SSE responses.
  Verified: session list, `/config/providers` (shows `srge` provider + `qwen3.8-27b`
  model), session creation all work through the proxy.
- **Idle reaper**: background thread marks runtimes `idle` after
  `SRGE_IDLE_REAP_MINUTES` of inactivity (touched by proxy calls).
- **`/metrics` (Prometheus)**: `srge_llm_*` counters from `UsageRecord`, plus
  `nvidia-smi` GPU utilization/memory and `srge_runtimes_total`. Admin-only
  dashboard per ADR 009.
- **Runtime reachability fix**: the runtime image now binds OpenCode to
  `--hostname 0.0.0.0` (was `127.0.0.1`), so the backend reaches it via the
  container's bridge IP (`Runtime.container_ip`). The `127.0.0.1:4096` host port
  mapping is flaky (connection reset); container-IP reachability is reliable.
- **Shared `srge` Docker network**: vLLM engine (`qwen38`) and runtimes are both
  attached, so the agent reaches vLLM by service alias `http://qwen38:8000/v1`.
  The host's bridge gateway IP is not the host, so the alias is the correct path.
- **OpenCode provider config**: `configure_opencode_vllm` writes
  `/root/.config/opencode/opencode.jsonc` registering the `srge` provider
  (`@ai-sdk/openai-compatible`, baseURL `http://qwen38:8000/v1`).
- **open-design** referenced for frontend design (nexu-io/open-design): design
  systems, plugins, and agent-native design artifacts to inform the Next.js UI
  later.

## Phase 3 — open / blocked
- **OpenCode message-send root-caused**: `POST /session/{id}/message` returns
  `UnknownError`. Server log shows two issues:
  1. `failed to load plugin @ai-sdk/openai-compatible: "Plugin export is not a
     function"` — the npm package exports `createOpenAICompatible` (a factory),
     not a plugin function, so OpenCode's plugin loader rejects it. Resolved by
     moving the provider config out of the `plugin` array into the `provider`
     section (with `npm` + `options.baseURL`).
  2. `SyntaxError: JSON Parse error: Expected '}'` — the OpenCode SSE stream
     parser chokes on vLLM's extra response fields (`token_ids`, `stop_reason`,
     `system_fingerprint`). vLLM access log confirms the provider IS reaching
     vLLM (200 OK), so the failure is purely in OpenCode's stream parser, not
     network. This is an OpenCode bug with vLLM's non-standard fields.
- **Fix applied to the image**: added `nodejs` + `npm` to `deploy/opencode.Dockerfile`
  so the `@ai-sdk/openai-compatible` package can be installed into
  `/root/.config/opencode/node_modules` (and `/node_modules`).
- DCGM exporter / Prometheus deployment + Caddy + Tailscale wiring still to do.

## What exists now

- `backend/` — FastAPI app (JWT auth, admin user management, per-user OpenCode
  runtime provisioning via docker-py, vLLM proxy with `UsageRecord` token
  accounting). SQLite for dev (`SRGE_DB`), Postgres in prod.
- `frontend/` — Next.js 15 login + usage panel (reads `/user/usage`).
- `deploy/` — `docker-compose.yml`, `caddy.json`, `opencode.Dockerfile`.
- `docs/` — `upstream-research.md`, `architecture-decisions.md`.

## Verified working on the DGX Spark (this session)

- Backend up on `127.0.0.1:8001`; bootstrap admin created; admin created a
  regular user; login returns JWT.
- `/v1/chat/completions` proxies to vLLM (`http://localhost:8000/v1`), writes a
  `UsageRecord` (prompt/completion/total tokens + latency). Confirmed 20+15=35
  tokens recorded for a real call to `qwen3.8-27b`.
- Per-user OpenCode runtime: built `srge/opencode-host:local` image (static
  `opencode` binary 1.18.30 on debian-slim + curl). Container `srge-oc-2` runs
  on the shared `srge` Docker network (with the `qwen38` vLLM engine), binds
  OpenCode to `0.0.0.0`, and its API responds only with the per-user basic-auth
  password. The backend reaches it via the container's bridge IP.
- vLLM facts reused from research: v0.27.1, `qwen3.8-27b`, streaming/tools/
  reasoning all live-verified.

## Open items / caveats

- OpenCode host image has no `node`/`wget`; `curl` added. The OpenCode server
  now binds `0.0.0.0` (image rebuilt with `--hostname 0.0.0.0`). The backend
  reaches the runtime via the container's bridge IP (stored in
  `Runtime.container_ip`), since the `127.0.0.1:4096` host port mapping proved
  flaky (connection reset).
- The OpenCode runtime container is **hardened** (no-new-privileges, cap_drop
  ALL, 4g mem, 2 CPU, pids 512). `seccomp=default` was removed because the
  Docker daemon (rootful, no userland seccomp) mis-parses it.
- DB is SQLite at `/tmp/srge-e2e.db` for the e2e test; production uses Postgres
  via compose.
- Caddy config targets `srge-backend:8001`; wire it into compose when the
  full stack is deployed.

## Suggested next

1. Fix the OpenCode SSE parser bug with vLLM (or configure vLLM to omit extra
   fields) so `POST /session/{id}/message` streams the model's reply.
2. Add DCGM exporter + Prometheus (ADR 007/009) on the internal tailnet.
3. Wire Caddy + Tailscale Serve (ADR 005/012) and test the browser login →
   runtime → vLLM → usage panel path end-to-end.
4. Apply open-design systems to the Next.js frontend (login + usage panel) as a
   later design pass.
