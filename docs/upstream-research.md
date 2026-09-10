# Upstream Research Report

Research date: 2026-09-09. All facts below were verified against live endpoints
(DGX Spark) and current upstream documentation. Assumptions are explicitly
flagged. No code was copied into the application; each repository was used
only for the specific architectural pattern listed.

## Environment detected on the DGX Spark (verified)

| Item | Verified value | Source |
|---|---|---|
| OpenCode version | **1.18.30** | `opencode --version` |
| vLLM container | name `qwen38`, image `vllm/vllm-openai:v0.27.1-aarch64` | `docker ps` |
| vLLM in-container version | `vllm.__version__ = 0.27.1` (system_fingerprint `vllm-0.27.1-e4541917`) | live API |
| Model | `Qwen3.8-27B-Uncensored-NVFP4`, served as `qwen3.8-27b` | `docker inspect` + `GET /v1/models` |
| vLLM startup args | `--served-model-name qwen3.8-27b --max-model-len 131072 --gpu-memory-utilization 0.85 --kv-cache-dtype fp8 --max-num-seqs ...` | `docker inspect qwen38` |
| GPU | NVIDIA GB10, driver 580.126.09, CUDA 13.0, 121.7 GiB unified pool, temp 62C, 27.49 W | `nvidia-smi` |
| Tailscale | installed; device `spark-f0d1` (100.68.61.41) online | `tailscale status` |

### vLLM behavior verified live (HTTP, port 8000)

- `GET /v1/models` returns one model: `qwen3.8-27b`, `max_model_len=131072`.
- `POST /v1/chat/completions` non-streaming: returns `message.content`,
  `message.tool_calls[]` when tools are used, `finish_reason` = `stop` /
  `tool_calls`, and a `usage` block with `prompt_tokens`,
  `completion_tokens`, `total_tokens`.
- Streaming: SSE `data:` chunks ending in `data: [DONE]`; first chunk has an
  empty `delta.content`, later chunks carry content, final chunk has
  `finish_reason:"stop"`.
- Tool calling works: with a `tools` array and `tool_choice:"auto"`, the model
  emitted a well-formed `tool_calls` entry with JSON-string `arguments`.
  Multi-step: assistant `tool_calls` + `role:"tool"` result + follow-up user
  message produced a second `tool_calls` finish reason; after a tool result the
  model answered `content: "12"` with `finish_reason:"stop"`.
  **Gotcha:** if `tool_choice` is set, `tools` **must** also be set
  (400 error otherwise).
- Thinking: `chat_template_kwargs: {"enable_thinking": true}` (a vLLM
  extension to the OpenAI schema) makes the response carry a `message.reasoning`
  field with the thinking content. Without it, `reasoning` is `null`.
- Prometheus metrics live at `GET /metrics`. vLLM exposes OpenMetrics with
  colon-formatted names, e.g.
  - `vllm:num_requests_running` / `vllm:num_requests_waiting` (gauge)
  - `vllm:kv_cache_usage_perc` (gauge)
  - `vllm:prompt_tokens_total`, `vllm:generation_tokens_total` (counters)
  - `vllm:e2e_request_latency_seconds`, `vllm:request_queue_time_seconds`,
    `vllm:time_to_first_token_seconds`, `vllm:inter_token_latency_seconds`
    (histograms)
  - `vllm:tool_call_parser_invocations_total` (counter)
  Metric labels are `engine` and `model_name` only — low cardinality, safe for
  Prometheus.

### Model checkpoint facts (verified from local files + model card)

- Local path: `/home/dc_srge/models/Qwen3.8-27B-Uncensored-NVFP4`, mounted
  read-only at `/model`.
- `config.json`: `Qwen3_5ForConditionalGeneration`, `model_type: qwen3_5`,
  64 layers, hidden 5120, 24 attn heads / 4 KV heads, vocab 248320,
  `max_position_embeddings=262144`, NVFP4 quantization config present.
- `chat_template.jinja` is shipped in the checkpoint (authority for chat
  template). Sampling recommendations from the model card: thinking mode
  `temperature=1.0, top_p=0.95, top_k=20, min_p=0.0`; non-thinking
  `temperature=0.7, top_p=0.80, top_k=20, presence_penalty=1.5`.
- **Assumption:** "Uncensored" variant is a fine-tuned/merged derivative of
  `Qwen3.8-27B`; the model card claims are upstream's, not re-verified on this
  checkpoint.

## Upstream repository table

| Repository | URL | Version / tag / commit inspected | License | Relevant features | Relevant files / docs | Decision | Reason | Security implications | ARM64 / DGX Spark compatibility | Maintenance risk |
|---|---|---|---|---|---|---|---|---|---|---|
| OpenCode | https://github.com/anomalyco/opencode | v1.18.30 (installed); docs page + `serve.ts` on `dev` branch | MIT (assumed — verify LICENSE before reuse) | headless server, OpenAPI spec at `/doc`, sessions, SSE events, permissions, providers | `packages/opencode/src/cli/cmd/serve.ts`, opencode.ai/docs/server | **Adopt** (primary runtime) | Verified running at 1.18.30; full API surface confirmed in current docs; OpenCode is the coding-agent layer | `OPENCODE_SERVER_PASSWORD` basic auth is the only built-in auth; expose only allowlisted routes via SRGE backend, never the raw server | aarch64 image exists and runs on Spark (host runs it natively) | Active; 1.18.x line |
| vLLM | https://github.com/vllm-project/vllm | v0.27.1 (image `vllm/vllm-openai:v0.27.1-aarch64`) | Apache-2.0 | OpenAI-compatible API, streaming, tool-calling parser, reasoning parser, Prometheus metrics | live container `qwen38`; `setup.py` at tag v0.27.1 | **Adopt** (existing, do not modify) | Already serving `qwen3.8-27b` correctly with tools, thinking, streaming — verified | Keep vLLM master key internal; only the SRGE backend talks to it | aarch64 image confirmed running on GB10 | Low (NVIDIA-published image) |
| Qwen3 (Qwen) | https://github.com/QwenLM/Qwen3 | `main` README (Qwen3-2507 era) | Apache-2.0 | chat template, thinking/non-thinking modes, tool use, sampling recommendations | README.md (main) | **Adapt** (reference only) | Authority for template/thinking conventions | n/a (models are Apache-2.0) | Qwen3 models run on aarch64 via vLLM | Low |
| Qwen-Agent | https://github.com/QwenLM/Qwen-Agent | `main` README | Apache-2.0 | Agent framework, code interpreter (Docker), MCP support, function calling | README.md (main) | **Optional** | OpenCode already provides the agent loop + tools; Qwen-Agent would only add a competing runtime | Code interpreter sandbox is "not for production" per its own README | runs on Python 3.10+; fine on ARM64 | Medium (fast-moving) |
| JupyterHub | https://github.com/jupyterhub/jupyterhub | `master` README | Revised BSD | hub auth, per-user server lifecycle, proxy routing, idle shutdown, REST admin API | README.md (master) | **Adapt pattern** | Hub→proxy→spawner architecture maps cleanly onto SRGE backend → OpenCode runtimes | Hub must run privileged; do NOT install JupyterHub, reimplement the pattern | JupyterHub is Linux-only; pattern is portable | Low |
| DockerSpawner | https://github.com/jupyterhub/dockerspawner | `master` README | Revised BSD | per-user Docker containers, volume ownership, lifecycle, resource limits, idle cleanup | README.md (master) | **Adapt pattern** | Study container naming, user→volume mapping, cleanup; reimplement in SRGE runtime manager | Never mount the Docker socket into user containers; isolate the runtime manager | Runs on ARM64 (pure Python) | Low |
| docker-py | https://github.com/docker/docker-py | `main` README | Apache-2.0 | Typed Docker Engine API (containers, images, logs) | README.md (main) | **Adopt** | Use SDK in the runtime manager instead of shell `docker` commands built from user input | All names/paths/labels validated server-side | Pure Python, arch-independent | Low |
| gVisor | https://github.com/google/gvisor | `master` README | Apache-2.0 | `runsc` OCI runtime for stronger isolation | README.md (master) | **Optional / reject-for-now** | README explicitly supports x86_64 and ARM64 builds, but unverified on GB10 + OpenCode workloads; containers will be hardened instead | If used, each sandboxed container gains kernel-level isolation | Builds on ARM64 per README; compatibility with OpenCode/Git/LSP untested | Medium |
| Open WebUI | https://github.com/open-webui/open-webui | `main` README + local image `ghcr.io/open-webui/open-webui:main` | **Open WebUI License (proprietary, branding requirement)** | RBAC, user groups, model visibility, streaming chat, admin settings | README.md (main); local container already running | **Reject** (not the coding-workspace manager) | It's a model-chat UI, not a workspace manager; license restricts code reuse | Self-hosted; image already on the Spark | Medium (licensing) |
| LiteLLM | https://github.com/BerriAI/litellm | `main` README | MIT (core); enterprise features commercial | Virtual keys, per-user spend, rate limits, model routing, guardrails | README.md (main) | **Optional** | Adds a failure point; SRGE backend can implement quotas/ownership directly — recommended default | If used: internal virtual key per user; never expose vLLM master key | Python-based, ARM64 OK | Medium (feature split OSS vs enterprise) |
| NVIDIA DCGM Exporter | https://github.com/NVIDIA/dcgm-exporter | `master` README | BSD-3 (assumed) | GPU telemetry (clocks, temp, power, memory) in Prometheus format | README.md (master) | **Adopt with fallback** | GB10 support is plausible (NVIDIA GPU telemetry stack), but `--cap-add SYS_ADMIN` is the default example flag — grant only if testing confirms it | Bind metrics to localhost/internal network only; no pprof endpoints publicly | aarch64 images exist (k8s/dcgm-exporter) | Low |
| Prometheus | https://github.com/prometheus/prometheus | v3.14.0 (latest stable tag) | Apache-2.0 | Time-series storage, alerting, service health | README + tags via GitHub API | **Adopt** (private) | Operational metrics only; keep out prompts/code/secrets from labels | Private scrape config; retention bounded for one Spark | Low |
| Grafana | https://github.com/grafana/grafana | v13.2.1 (latest stable tag) | AGPL-3.0-only (Apache-2.0 exceptions) | Admin-only dashboards, GPU/system/vLLM/queue visualization | README.md + tags via GitHub API | **Optional / disabled by default** | User-facing resource panel is built into SRGE itself; Grafana is for admins | Private network only; separate admin auth | Medium (AGPL) |
| Langfuse | https://github.com/langfuse/langfuse | `main` README | MIT (except `ee/` folders) | LLM observability, tracing, evaluations, prompt management | README.md (main) | **Optional** | Lightweight internal `UsageRecord` system preferred for v1; no external Langfuse transmission | If enabled: redact secrets, configurable retention, self-hosted | Node/ClickHouse; ARM64 OK | Medium |
| Tailscale | https://github.com/tailscale/tailscale | installed; CLI docs at tailscale.com/docs/reference/tailscale-cli/serve | BSD-3-Clause | Tailscale Serve (private HTTPS, tailnet ACLs), tag-based access | docs/reference/tailscale-cli/serve | **Adopt** | Use Serve (not Funnel); keep app login + RBAC as the real security boundary; Tailscale is only the transport | ACLs by tag; don't rely on Tailscale identity alone | Verified installed & online on Spark | Low |
| Caddy | https://github.com/caddyserver/caddy | `master` README | Apache-2.0 | Reverse proxy, security headers, request-size limits, timeouts, SSE proxying | README.md (master) | **Adopt** | Caddy binds to localhost/private interface; do NOT expose OpenCode/vLLM/Postgres/Redis/Prometheus/DCGM through it | Explicit route allowlists; disable public auto-certs when TLS is terminated by Tailscale Serve | Go, no libc deps — fine on ARM64 | Low |
| Full-Stack FastAPI Template | https://github.com/fastapi/full-stack-fastapi-template | `master` README | MIT | FastAPI + SQLModel + Pydantic, React frontend, Docker Compose, JWT auth, Playwright tests | README.md (master) | **Adapt (structure only)** | Use as a structural reference for backend layout/tests; keep SRGE frontend on Next.js unless complexity drops materially | Don't inherit its example secrets/permissive CORS | Runs anywhere | Low |

## Cross-cutting decisions (summary — details in architecture-decisions.md)

1. **OpenCode runtime isolation**: one OpenCode runtime per user, spawned by
   the SRGE runtime manager; no shared instance.
2. **Docker control boundary**: runtime manager holds the Docker socket;
   user containers never get it.
3. **Authentication**: SRGE app login (JWT/DB users) + Tailscale tailnet as
   transport; OpenCode basic-auth credentials stay server-side.
4. **RBAC**: app-level roles (admin / user), enforced in the SRGE backend,
   not delegated to any upstream component.
5. **Tailscale access**: Serve (private), tag-based ACLs, no Funnel.
6. **vLLM vs LiteLLM**: direct configurable vLLM endpoint; LiteLLM optional
   only if per-user virtual keys/quotas are required.
7. **GPU monitoring**: DCGM exporter on internal network; `nvidia-smi`
   structured-query fallback; whole-GPU utilization ≠ per-user usage.
8. **Queue**: SRGE backend request queue with per-user concurrency limits and
   token accounting (UsageRecord) instead of LiteLLM as the sole boundary.
9. **Prometheus & Grafana**: Prometheus always (private, bounded retention);
   Grafana optional, admin-only, disabled by default.
10. **Langfuse**: optional; v1 uses internal UsageRecord; no external
    transmission.
11. **gVisor**: optional; v1 ships hardened containers (rootless, dropped
    caps, seccomp, AppArmor, no-new-privileges, PID/CPU/memory limits,
    restricted net); gVisor only after GB10 compatibility is proven.
12. **Frontend**: Next.js (user-facing); FastAPI template used for backend
    structure only.
13. **Reverse proxy**: Caddy, localhost/private bind, SSE-safe, no public
    cert issuance when Tailscale terminates TLS.

## Statement

SRGE AI Workspace is an independent project. It is **not maintained by or
affiliated with the OpenCode project** (or any other upstream project listed
above).
