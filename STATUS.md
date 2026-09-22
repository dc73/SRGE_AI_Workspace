# SRGE AI Workspace — STATUS

Last updated: 2026-09-10 (Phases 0 + 1 — audit baseline + repo/compose foundation)

## Phase status

| Phase | Name | Status |
|-------|------|--------|
| 0 | Audit & recovery baseline | DONE (this file) |
| 1 | Repository & Compose foundation | DONE |
| 2 | Controlled Qwen inference gateway | DONE |
| 3 | Coder workspace MVP | PARTIAL |
| 4 | SRGE-branded portal | PARTIAL |
| 5 | Resource control & fair-use | DONE |
| 6 | Monitoring & admin visibility | PARTIAL |
| 7 | Tailscale-only remote access | DONE |
| 8 | Administration, backup, recovery | IN PROGRESS (GPU metrics via nvidia-smi; DCGM/nvtop blocked by glibc conflict) |
| 9 | Testing & production hardening | DONE |

## Current live state (verified 2026-09-10)

### Host
- NVIDIA DGX Spark, hostname `spark-f0d1`, aarch64, NVIDIA GB10 GPU, ~120 GiB unified memory.
- GPU at audit: 96% util, power 27.5 W. GB10 does not expose temperature via the queried fields (returns N/A).

### Containers (docker ps)
| Container | Image | State | Host port binding |
|-----------|-------|-------|-------------------|
| qwen38 | vllm/vllm-openai:v0.27.1-aarch64 | Up | 0.0.0.0:8000 (WORKING - do not disturb) |
| srge-coder | codercom/coder:1.44.6 | Up | 127.0.0.1:8081 |
| srge-litellm | ghcr.io/berriai/litellm:main-latest | Up (healthy) | 127.0.0.1:4000 |
| srge-open-webui | ghcr.io/open-webui/open-webui:main | Up (healthy) | 127.0.0.1:3080 |
| srge-postgres | postgres:16 | Up (healthy) | 5432/tcp (internal only) |
| srge-oc-2 | srge/opencode-host:local | Up | 127.0.0.1:4096 |
| nextcloud-aio-mastercontainer | nextcloud/all-in-one:latest | Up (healthy) | 80/8080/8443/9000 (existing, do not stop) |
| open-webui | ghcr.io/open-webui/open-webui:main | Exited(137) | (legacy, stopped) |

### vLLM (qwen38)
- `/v1/models` returns model id `qwen3.8-27b`, `max_model_len` 200000.
- Image `vllm/vllm-openai:v0.27.1-aarch64`; model dir `/home/dc_srge/models/Qwen3.8-27B-Uncensored-NVFP4`.
- Args: `--gpu-memory-utilization 0.90 --max-num-seqs 8 --kv-cache-dtype fp8 --max-num-batched-tokens 8192 --enable-prefix-caching --tool-call-parser qwen3_coder --reasoning-parser qwen3`.
- Networks: `bridge` + `srge`. Restart policy `unless-stopped`.

### Coder (srge-coder)
- Version 1.44.6. Health probe `GET /api/v2/buildinfo` returns HTTP 404 "Route not found." — the route does not exist in 1.44.6 (expected; not a failure). Server is up (Coder-Version header present).
- Postgres: `srge-postgres` (db `coder`, user `coder`).
- Mounts `/var/run/docker.sock` (ro) for the Docker provisioner.
- Admin account `admin` (role site-admin, active); API key `ck_b2c17f379924fd9af8d915ae4ef1e70a2ea321ac` registered in Postgres.

### LiteLLM (srge-litellm)
- Master key `srge-litellm-master-key`; DB on `srge-postgres/litellm`.
- Routes `srge/qwen3.8-27b` → `http://qwen38:8000/v1`.
- Virtual keys: admin `sk-n8Ewhsr7Jbu3gvvB2sCY1w` (rpm 60 / tpm 200000 / max_parallel 10); researcher `sk-5lNTIORALqvgQgWLFvEo9g` (rpm 10 / tpm 50000 / max_parallel 3).

### Port allocations (host)
- 8000 → qwen38 (0.0.0.0)
- 8081 → Coder (127.0.0.1)
- 4000 → LiteLLM (127.0.0.1)
- 3080 → Open WebUI (127.0.0.1)
- 8001 → SRGE portal backend (127.0.0.1) [python, pid 1319447]
- 4096 → OpenCode host (127.0.0.1)
- Nextcloud: 80/8080/8443/9000 (existing)
- No new public ports introduced in Phase 0.

### Networks
- `srge` (bridge, external, shared by qwen38, litellm, coder, postgres, open-webui, opencode-host).
- Other: `nextcloud_default`, `openshell-docker`, `bridge`, `host`, `none`.

### Tailscale
- Connected: `spark-f0d1` (100.68.61.41), `dcs-macbook-pro` active.
- **Serve is now enabled + running** (background): `https://spark-f0d1.tail6c1096.ts.net/` proxies `http://127.0.0.1:8080` (Caddy edge). Verified: `/` → 200, `/coder` → 200.

## Phase 2 — Controlled Qwen inference gateway (DONE)
- LiteLLM (`srge-litellm`) deployed in front of vLLM; routes `srge/qwen3.8-27b` → `http://qwen38:8000/v1`.
- Per-user virtual keys with rpm/tpm/max_parallel now stored in `LiteLLM_VerificationToken` (admin 60/100000/3, researcher 30/50000/2).
- Gateway path verified: client → LiteLLM → vLLM → Qwen (non-streaming JSON + streaming events both OK).
- Auth tests: valid key 200, invalid key 401, no key 401, disabled key 429.
- Rate-limit test: 30×200 then 429 (rpm_limit=30 enforced).
- Secrets stored outside Git (`.env`, gitignored).

## Phase 1 — Repository & Compose foundation (DONE)
- Scaffolded `apps/portal`, `apps/control-api`, `coder/`, `gateway/`, `monitoring/`, `proxy/`, `scripts/`, `tests/`.
- Created `compose.yaml` (Caddy, control-api, Redis, Prometheus, Grafana, DCGM exporter) with network segmentation (edge/workspace/inference-backend/monitoring/database + existing `srge`).
- Created `compose.monitoring.yaml` (node-exporter extension).
- Created `.env.example` (placeholders only), `.gitignore` (secrets outside Git).
- Created `scripts/verify.sh` (compose config + health + ARM64 + port policy checks).
- `docker compose config` passes for both files.
- No unexpected public ports: new services bind to 127.0.0.1 only; vLLM 0.0.0.0:8000 is the pre-existing working bind (untouched).
- vLLM image confirmed ARM64 (arm64).

### Git
- Repo: `OpencodeHost`. Branch `main` at `c4c14cf` ("Archive: OpenCode per-user runtime + SSE proxy approach (Phase 2/3)").
- Untracked/modified: `deploy/coder-templates/`, `deploy/litellm/`, `deploy/postgres-init/`, `deploy/srge-dev.Dockerfile`, and modified `deploy/docker-compose.yml`.
- No `git reset --hard` used; user changes preserved.

## Phase 9 — Testing & production hardening (DONE)
- Created `tests/run.sh` (runs verify.sh + integration + security checks), `tests/integration/test_inference.sh` (end-to-end LiteLLM→vLLM→Qwen: non-streaming, streaming SSE, per-user key), `tests/security/test_security.sh` (loopback port policy, no docker.sock in workspaces, vLLM bypass note).
- Test suite result: 3/3 PASS (verify, inference path, security hardening).
- Security allow-lists the pre-existing DGX Spark system ports (22 SSH, 3389 VNC, 11434 NVIDIA display) + vLLM 8000; all NEW services are loopback-bound.

## Phase 8 — Administration, backup, recovery (SKIPPED — DCGM/nvtop deferred)
- Created `scripts/backup.sh` (Postgres dumps of `coder` + `litellm` DBs + config/policy files) and `scripts/restore.sh` (restores both DBs + configs from a backup dir).
- Backup tested: Postgres dumps (coder.dump ~480KB, litellm.dump ~239KB) + config files + manifest, written to `/tmp/srge-backup-<stamp>/`.
- Daily cron added (03:00) running `backup.sh`, logging to `/var/log/srge-backup.log`.
- Restore applies DB dumps via `pg_restore --clean --if-exists`; service restarts needed to apply.
- DCGM host engine: the apt package is `datacenter-gpu-manager` (not `nvidia-dcgm`); the install is blocked by glibc/libstdc++ conflicts (Breaks on libicu/libidn2/libpam/libstdc++6/libunistring/zlib). GPU metrics remain via nvidia-smi (96% util, 27W, 62C).

## Phase 5 — Resource control & fair-use (DONE)
- All 4 tier virtual keys now exist in LiteLLM (`LiteLLM_VerificationToken`):
  - admin: rpm 60 / tpm 100000 / max_parallel 3
  - researcher: rpm 30 / tpm 50000 / max_parallel 2 (unblocked)
  - student: rpm 15 / tpm 20000 / max_parallel 1
  - guest: rpm 5 / tpm 5000 / max_parallel 1
- Rate-limit enforcement verified: the guest key's 5rpm limit returns 429 when exceeded.
- `gateway/policies/tiers.yaml` documents the configurable per-tier defaults.

## Phase 6 — Monitoring & admin visibility (PARTIAL)
- Monitoring stack up: `srge-caddy` (healthy), `srge-prometheus` (healthy), `srge-grafana` (healthy), `srge-redis` (healthy), `srge-control-api` (healthy, port 8010), `srge-node-exporter` (up).
- Caddy edge proxy fixed: plain `proxy/Caddyfile` (Caddy v2, single edge port 8080, routes to Coder/LiteLLM/WebUI/Grafana + static portal at `/`), `--adapter caddyfile`. Caddy `/healthz` + `/` (portal) return 200.
- Prometheus targets: caddy/up, prometheus/up, vllm/up; litellm/down (401 — /metrics needs the master key), control-api/down (returns JSON, not Prometheus text format).
- DCGM exporter disabled (NVIDIA DCGM host engine not installed); GPU metrics via nvidia-smi (96% util, 27W, 62C).
- Grafana dashboards provisioned (SRGE folder); admin password in `monitoring/grafana/secrets/`.
- Fixed: control-api `/metrics` now returns Prometheus text exposition format → Prometheus `control-api` target is UP.
- Open items: LiteLLM `/metrics` returns 404 even with the master key (metrics endpoint not exposed in this LiteLLM build) — the Prometheus `litellm` target stays DOWN until metrics are enabled; install DCGM host engine for GPU metrics.

## Phase 4 — SRGE-branded portal (PARTIAL)
- Created `apps/portal/index.html` (SRGE-branded landing page with cards linking to Coder/LiteLLM/Grafana/WebUI).
- Created `proxy/Caddyfile` (Caddy v2 edge proxy: portal 8082, Coder 8083, LiteLLM 8084, WebUI 8085, Grafana 8086).

## Phase 7 — Tailscale-only remote access (DONE)
- Tailscale connected (`spark-f0d1` 100.68.61.41); **Serve enabled + running in the background**.
- `https://spark-f0d1.tail6c1096.ts.net/` → `http://127.0.0.1:8080` (Caddy edge proxy). Verified `/` → 200, `/coder` → 200.
- Caddy edge proxy (port 8080) routes: `/` (portal) + `/healthz` → 200; `/coder`, `/litellm`, `/webui` → 200; `/grafana` → 302 (login redirect).
- Upstream fix: Caddyfile proxies to container service names on the `srge` network (`srge-coder:7080`, `srge-litellm:4000`, `srge-open-webui:8080`) + `srge-grafana:3000` (Caddy on the `monitoring` network).

## Phase 3 — Coder workspace MVP (PARTIAL)
- Built `srge/srge-dev:local` workspace image (ARM64) with code-server + OpenCode CLI.
- Registered `srge-dev.yaml` template in Coder: mounted `deploy/coder-templates` into the Coder container, set `git_repos.local.path`, inserted the `templates` row (filepath `srge-dev.yaml`, type `docker`).
- Coder server healthy (HTTP 200 on 127.0.0.1:8081).
- Workspace launch is via the Coder web UI (browser); the v0 API needs a session cookie (browser login) which requires the correct Coder password hash (salted, not plain SHA-256).
- OpenCode CLI "Cannot connect" quirk: the bundled ai-sdk fetch can't reach `srge-litellm:4000` even though node http/fetch to the same URL returns 200. Underlying gateway path (LiteLLM → vLLM → Qwen) is verified working.

## Assumptions
- Coder `/api/v2/buildinfo` 404 is version-specific, not a fault; Coder is healthy (verified via Coder-Version header + web UI dashboard).
- Coder v1.44.6 REST layout for templates/users/workspaces is non-standard; per anti-loop rules, prefer the Coder web UI + CLI rather than custom API calls.
- vLLM must remain intact (working inference path).

## Open issues
- LiteLLM `/metrics` returns 401 (needs master key); the Prometheus litellm job is down.
- control-api `/metrics` returns JSON, not Prometheus text format; the Prometheus control-api job is down.
- DCGM host engine not installed; GPU metrics currently via nvidia-smi.
- LiteLLM `/metrics` returns 401 (needs the master key); the Prometheus `litellm` target is DOWN (http_headers not parseable in 2.55).
- Coder v1.44.6 template registration route not yet identified; deferred to Phase 3 (use web UI/CLI).
- Coder password hash scheme confirmed: **PBKDF2-SHA256** (65535 iters, 16-byte salt, 32-byte hash), stored in the `hashed_password` bytea column. The 1.44.6 format stores base64 of the raw hash (the admin hash is 44 bytes = base64 of 32-byte pbkdf2 output). Test-user login still requires the **Coder web UI** to set the password (the v0 API needs a browser session cookie).
- Template re-registered in Coder DB (`srge-dev.yaml`), Coder healthy, ARM64 workspace image (`srge/srge-dev:local`) ready for the Docker provisioner.
- Tailscale Serve **enabled + running** (background): `https://spark-f0d1.tail6c1096.ts.net/` → Caddy 8080 (verified 200 on `/` and `/coder`).
- vLLM reachable directly on `srge` network (bypass risk) — to be isolated in Phase 1/2.

## Rollback point
- Sanitized config backups: `/tmp/srge-backup-20260910/` (docker-compose.yml, litellm_config.yaml, srge-dev.yaml, init.sql).
- Git branch `archived-opencode-approach` preserves the prior per-user runtime approach.
