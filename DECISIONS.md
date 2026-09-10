# SRGE AI Workspace — DECISIONS

Architecture decision records. Each entry records the decision, the verified
facts that justify it, the alternatives, and the consequences.

---

## D-001: Keep Coder as the workspace system (do not replace)

- **Status:** Accepted
- **Decision:** Use the existing Coder (1.44.6) for user accounts, workspace
  lifecycle, isolation, and browser apps. Do NOT build a replacement.
- **Facts (verified):**
  - `srge-coder` is up (Coder-Version 1.44.6 header present).
  - Coder web UI shows the dashboard (admin setup complete).
  - Coder provides per-user workspaces with the Docker provisioner.
- **Alternatives:**
  - Keep the legacy per-user OpenCode runtime manager (ADR 001, archived branch)
    — superseded by Coder for workspace lifecycle.
- **Consequences:**
  - Use Coder's web UI + CLI (per anti-loop rule 6), not a custom API client.
  - Workspaces get code-server (browser VS Code) + OpenCode CLI + LiteLLM access.

## D-002: LiteLLM as the single inference gateway

- **Status:** Accepted
- **Decision:** All Qwen requests must pass through LiteLLM. Workspaces must
  not reach vLLM directly.
- **Facts (verified):**
  - LiteLLM (`srge-litellm`) is up and healthy; routes `srge/qwen3.8-27b`
    to `http://qwen38:8000/v1`.
  - vLLM (`qwen38`) currently sits on the shared `srge` network, so workspaces
    could bypass LiteLLM.
- **Alternatives:**
  - Direct vLLM access from workspaces — rejected (no per-user quotas/keys).
- **Consequences (Phase 1/2):**
  - Move vLLM onto a dedicated `inference-backend` network; LiteLLM bridges
    `inference-backend` + `workspace`; workspaces on `workspace` cannot reach
    vLLM directly.
  - Per-user virtual keys with RPM/TPM/max-parallel limits.

## D-003: Network segmentation

- **Status:** Accepted
- **Decision:** Define separate Docker networks: `edge`, `workspace`,
  `inference-backend`, `monitoring`, `database`.
- **Facts (verified):**
  - Existing single shared `srge` network currently hosts all SRGE services.
- **Consequences:**
  - vLLM → `inference-backend` only.
  - LiteLLM → `inference-backend` + `workspace`.
  - User workspaces → `workspace` only (no direct vLLM path).
  - PostgreSQL/Redis → `database` (not exposed to host).
  - Monitoring → `monitoring` (internal / loopback).
  - Caddy = the only application-facing reverse proxy on `edge`.

## D-004: No public exposure; Tailscale-only remote access

- **Status:** Accepted
- **Decision:** No Cloudflare Tunnel. No public port publishing. Remote access
  exclusively via Tailscale Serve (private HTTPS).
- **Facts (verified):**
  - Tailscale connected (`spark-f0d1`, `dcs-macbook-pro` active);
    `tailscale serve status` → "No serve config".
  - Existing host ports bind to `127.0.0.1` except vLLM (0.0.0.0:8000).
- **Consequences:**
  - Expose only: SRGE portal, Coder web UI, optionally Grafana (admin).
  - Do NOT bind vLLM, LiteLLM, Postgres, Redis, Prometheus, DCGM, or internal
    control APIs to the tailnet.

## D-005: Workspace resource limits (configurable)

- **Status:** Accepted
- **Decision:** Apply configurable CPU / memory / PID limits to user workspaces.
  Defaults (dev): CPU 4 cores, memory 12 GiB, PIDs 512, max 1 workspace per
  standard user, idle shutdown 60 minutes.
- **Consequences:**
  - No Docker socket or NVIDIA GPU device exposed to workspaces.
  - Persistent per-user volume for project files; restart preserves files.

## D-006: Repository layout

- **Status:** Accepted
- **Decision:** Adapt the required `srge-ai-workspace/` tree to the existing
  `OpencodeHost` repo layout rather than moving everything.
- **Facts (verified):**
  - Existing repo already has `backend/`, `frontend/`, `deploy/`, `docs/`.
  - New dirs to add: `coder/templates/`, `gateway/litellm/` (existing
    `deploy/litellm/`), `monitoring/`, `proxy/`, `scripts/`, `tests/`.
- **Consequences:**
  - Keep `deploy/` as the compose root (existing `deploy/docker-compose.yml`).
  - Map required paths onto existing dirs; document the mapping in this file.

## D-007: Secrets handling

- **Status:** Accepted
- **Decision:** Store secrets outside Git (env files / Docker secrets), redact
  authorization headers and prompt contents from logs.
- **Consequences:**
  - `.env.example` holds placeholders only; real secrets live in `.env` (gitignored).
  - LiteLLM master key, Coder admin token, Postgres creds kept server-side.

## D-008: OpenCode usage model

- **Status:** Accepted
- **Decision:** Use OpenCode CLI inside the workspace terminal (not the
  experimental web server). Configure it to call LiteLLM with the user's
  virtual key + the actual served model name.
- **Facts (verified):**
  - Prior direct OpenCode-server integration hit SSE parsing problems (archived).
  - OpenCode is a native aarch64 binary; runs fine on the Spark.
- **Consequences:**
  - `OPENAI_BASE_URL=http://srge-litellm:4000/v1`, per-user key injected at
    workspace startup.
