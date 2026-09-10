# Architecture Decision Records

Scope: SRGE AI Workspace. Each ADR records the decision, the verified facts
that justify it, the alternatives, and the consequences. All runtime facts
were verified live on the DGX Spark (see `upstream-research.md`).

**Not affiliated with OpenCode** — SRGE is an independent project.

---

## ADR 001: OpenCode runtime isolation

- **Status:** Accepted
- **Decision:** Run one OpenCode runtime instance per user, each in its own
  hardened container, managed by the SRGE runtime manager. No shared/
  multi-tenant OpenCode server.
- **Facts (verified):**
  - OpenCode 1.18.30 runs natively on the Spark (aarch64, GB10).
  - OpenCode's only built-in auth is basic auth via `OPENCODE_SERVER_PASSWORD`
    — a single shared credential; it provides no per-user isolation of
    sessions, files, or config.
  - OpenCode's API surface (sessions, events/SSE, permissions, providers) is
    stable and documented; per-user instances avoid cross-user state leakage
    (open sessions, file access, provider credentials).
- **Alternatives considered:**
  - Single shared OpenCode instance: rejected — no per-user isolation, and
    provider/basic-auth is global.
  - JupyterHub-style per-user servers via DockerSpawner pattern: this IS the
    pattern adopted (hub→spawner), but implemented directly in the SRGE
    runtime manager rather than installing JupyterHub.
- **Consequences:**
  - `OPENCODE_SERVER_PASSWORD` is generated per user and kept server-side
    (never in the browser or the frontend bundle).
  - Containers: rootless user, `no-new-privileges`, dropped capabilities,
    seccomp, AppArmor profile, PID/CPU/memory limits, restricted network.
  - Idle runtimes are reaped by the runtime manager (DockerSpawner pattern).

## ADR 002: Docker control boundary

- **Status:** Accepted
- **Decision:** The SRGE runtime manager (backend process) is the only
  component allowed to talk to the Docker Engine API. User-facing containers
  never receive the Docker socket.
- **Facts (verified):**
  - `docker-py` (Apache-2.0) is the typed SDK for the Docker Engine API.
  - DockerSpawner (Revised BSD) demonstrates per-user container lifecycle:
    naming, volume ownership, resource limits, idle cleanup.
- **Reason:** Giving the socket to user containers grants root-equivalent
  host control; keeping it in the manager is the least-privilege boundary.
- **Consequences:**
  - Runtime manager uses `docker-py` (no shell-string `docker` commands built
    from user input).
  - Container names, labels, paths, and volume mounts are validated
    server-side.
  - Per-user named volumes are owned by that user's runtime only.

## ADR 003: Authentication boundary

- **Status:** Accepted
- **Decision:** Authentication = SRGE app login (JWT/DB users) + Tailscale
  tailnet as transport. OpenCode basic-auth credentials and the vLLM master
  key stay server-side; the browser never sees them.
- **Facts (verified):**
  - OpenCode 1.18.30 auth = `OPENCODE_SERVER_PASSWORD` basic auth only.
  - Tailscale installed & online on Spark (`spark-f0d1`, 100.68.61.41),
    3 devices on tailnet.
- **Alternatives:**
  - Expose OpenCode's `/doc` + basic auth directly: rejected (credential in
    browser bundle risk).
  - Full Tailscale identity as the only auth: rejected — Tailscale ACLs are
    coarse (device/tag-based), not per-user app-level RBAC.
- **Consequences:**
  - SRGE backend issues per-user OpenCode `OPENCODE_SERVER_PASSWORD`, stores it
    in DB (encrypted at rest), injects it into that user's runtime env.
  - Tailscale Serve terminates TLS; Caddy binds to localhost/internal; no
    public cert issuance.

## ADR 004: RBAC model

- **Status:** Accepted
- **Decision:** RBAC lives in the SRGE backend: roles `admin` and `user`.
  No delegation of authorization to OpenCode/vLLM/LiteLLM/Grafana.
- **Facts (verified):**
  - OpenCode exposes a permissions concept but no role model.
  - Grafana has its own RBAC; keeping it admin-only and (default) disabled
    means app-level RBAC is the single source of truth.
- **Reason:** One authorization boundary avoids split-brain permission
  state across five components.
- **Consequences:**
  - Admin: user management, role assignment, runtime lifecycle ops,
    Grafana access, metrics.
  - User: own sessions/runtime, own usage, own vLLM access.
  - Enforced in the backend middleware on every route; roles stored in SRGE
    DB.

## ADR 005: Tailscale access model

- **Status:** Accepted
- **Decision:** Use **Tailscale Serve** (private HTTPS on the tailnet), tag-
  based ACLs, **no Funnel**.
- **Facts (verified):** Tailscale is installed and the tailnet is active
  (`tailscale status`). Docs at tailscale.com/docs/reference/tailscale-cli/serve.
- **Reason:** Serve keeps traffic on the private tailnet (IP 100.64/10
  space); Funnel opens a public path that the app login + RBAC must fully
  cover.
- **Consequences:**
  - `tailscale serve` maps public host/port to internal services.
  - ACLs: admin tag → admin panel + Grafana; user tag → app + vLLM.
  - TLS is terminated by Tailscale; Caddy must not issue public certs.

## ADR 006: Direct vLLM vs LiteLLM

- **Status:** Accepted
- **Decision:** v1 connects **directly** to the existing vLLM OpenAI-
  compatible endpoint (`http://localhost:8000/v1`). LiteLLM is optional and
  only introduced if per-user virtual keys, spend, or rate limiting become
  required.
- **Facts (verified live on Spark):**
  - vLLM v0.27.1 (image `vllm/vllm-openai:v0.27.1-aarch64`) serves
    `qwen3.8-27b` from `/home/dc_srge/models/Qwen3.8-27B-Uncensored-NVFP4`
    (read-only bind mount at `/model`).
  - Verified: streaming SSE, tool calling (multi-step), `reasoning` field via
    `chat_template_kwargs.enable_thinking=true`, `/metrics` Prometheus format
    (`vllm:*` names).
  - `--max-model-len 131072`, `--kv-cache-dtype fp8`,
    `--gpu-memory-utilization 0.85`.
- **Reason:** LiteLLM would add a network hop and an extra failure point
  before every token; the SRGE backend can implement quotas/ownership/usage
  (UsageRecord) directly. vLLM already provides per-request `usage` token
  counts.
- **Consequences:**
  - SRGE backend holds the single vLLM master key (server-side).
  - Per-user concurrency + token accounting implemented in the backend queue
    (see ADR 008), not delegated to LiteLLM.
  - Revisit only if multi-model routing / spend caps are requested.

## ADR 007: GPU monitoring strategy

- **Status:** Accepted
- **Decision:** Primary = NVIDIA DCGM exporter (Prometheus format, internal
  network). Fallback = `nvidia-smi` structured queries. Whole-GPU
  utilization ≠ per-user usage; per-user attribution comes from the vLLM
  request queue (token counts), not GPU counters.
- **Facts (verified):**
  - GPU: NVIDIA GB10, driver 580.126.09, CUDA 13.0, 121.7 GiB unified pool,
    temp 62C, 27.49 W (nvidia-smi live).
  - DCGM exporter (BSD-3 assumed) exposes GPU telemetry; its example uses
    `--cap-add SYS_ADMIN` (grant only if testing on GB10 confirms it's
    needed).
- **Reason:** DCGM gives structured, scrapeable metrics; `nvidia-smi
  --query-gpu=...` is the no-dependency fallback.
- **Consequences:**
  - DCGM binds metrics to localhost/internal; no pprof endpoints public.
  - Per-user "GPU time" is derived from vLLM usage tokens + request durations
    (e2e latency histograms are available in `/metrics`).
  - Whole-GPU % is a coarse signal, shown only in the admin panel.

## ADR 008: Request queue & usage accounting

- **Status:** Accepted
- **Decision:** The SRGE backend owns a request queue with per-user
  concurrency limits and a `UsageRecord` (prompt/completion/total tokens per
  request, user, model, timestamp). No LiteLLM as the sole boundary.
- **Facts (verified):**
  - vLLM `/v1/chat/completions` returns `usage` per request (live-verified).
  - vLLM `/metrics` provides `vllm:num_requests_running`,
    `vllm:num_requests_waiting`, `vllm:e2e_request_latency_seconds`,
    `vllm:tool_call_parser_invocations_total`.
  - `--max-num-seqs` caps concurrent sequences (visible in container args).
- **Reason:** A single backend queue gives deterministic per-user limits and
  clean attribution; vLLM's `--max-num-seqs` is the hard ceiling.
- **Consequences:**
  - Queue stores `{user_id, prompt_tokens, completion_tokens, model, ts}`.
  - User panel shows own tokens/requests; admin panel shows per-user
    breakdown + queue depth (`vllm:num_requests_waiting` mirror).
  - Limits enforced before calling vLLM; rejected requests are accounted as
    queued, not lost.

## ADR 009: Prometheus & Grafana strategy

- **Status:** Accepted
- **Decision:** Prometheus (v3.14.0) always enabled, **private**, bounded
  retention. Grafana (v13.2.1) is **optional, admin-only, disabled by
  default**.
- **Facts (verified):** Latest stable tags: Prometheus `v3.14.0`,
  Grafana `v13.2.1`.
- **Reason:** Operational metrics (system, vLLM, DCGM) must never carry
  prompts, code, or secrets in labels. Grafana's AGPL-3.0-only license and
  admin RBAC make it an optional add-on, not a user-facing panel.
- **Consequences:**
  - Prometheus scrapes: vLLM `:8000/metrics`, DCGM exporter, node_exporter.
  - Retention bounded (e.g., 30d) for a single Spark.
  - User-facing resource/usage panel is implemented directly in the SRGE
    frontend (Next.js) — no Grafana dependency for end users.

## ADR 010: Langfuse strategy

- **Status:** Accepted
- **Decision:** Langfuse is **optional**; v1 ships the internal `UsageRecord`
  system. No external Langfuse transmission by default.
- **Facts (verified):** Langfuse (MIT except `ee/`) offers tracing, evals,
  prompt management.
- **Reason:** Avoids a new network dependency + data-egress question;
  `UsageRecord` already covers token accounting (ADR 008).
- **Consequences:**
  - If enabled later: redact secrets in payloads, configurable retention,
    self-hosted on the tailnet only.
  - Default = off; feature-flagged.

## ADR 011: gVisor sandboxing strategy

- **Status:** Accepted
- **Decision:** gVisor is **optional / rejected for v1**. v1 ships
  hardened containers (rootless, dropped caps, seccomp, AppArmor,
  no-new-privileges, PID/CPU/memory limits, restricted net). gVisor only
  after GB10 compatibility with OpenCode workloads is proven.
- **Facts (verified):** gVisor README states x86_64 + ARM64 builds exist,
  but OpenCode + Git + LSP under `runsc` on GB10 is untested.
- **Reason:** `runsc` adds kernel-level isolation at the cost of syscall-
  compatibility risk for a coding agent that shells out to git/LSP.
- **Consequences:**
  - v1 = hardening profile on runc (least surprise).
  - Gate: prove OpenCode, Git, and LSP work under `runsc` on the Spark
    before enabling; keep it behind a feature flag.

## ADR 012: Frontend & reverse proxy

- **Status:** Accepted
- **Decision:** Frontend = **Next.js** (user-facing). Full-Stack FastAPI
  template = backend structure reference only. Reverse proxy = **Caddy**
  (Apache-2.0): binds to localhost/private, explicit route allowlists,
  SSE-safe, no public cert issuance (TLS terminated by Tailscale Serve).
- **Facts (verified):** Caddy supports SSE proxying and security headers;
  the FastAPI template (MIT) provides backend layout/tests to mirror.
- **Reason:** Caddy is the lightest correct proxy for SSE (OpenCode events,
  vLLM streaming) with automatic security headers; Next.js gives a user-
  facing UI without a new framework decision.
- **Consequences:**
  - Caddy config: allowlist routes (app, vLLM, OpenCode, metrics); disable
    public auto-cert when Tailscale terminates TLS.
  - Request-size limits + timeouts set explicitly.
  - Frontend shows: sessions, usage (from `UsageRecord`), resource panel
    (whole-GPU %), admin panel (users, roles, runtimes).

---

## Cross-cutting statement

SRGE AI Workspace is an independent project, **not maintained by or
affiliated with the OpenCode project** or any upstream listed above. Upstream
code was used only for the patterns listed in `upstream-research.md`; no code
was copied in wholesale.
