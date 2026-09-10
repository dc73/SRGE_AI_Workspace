# SRGE AI Workspace

Self-hosted AI development platform for the Embry-Riddle **Space Robotics and
Generative Estimation (SRGE) Lab**, running on the lab's NVIDIA DGX Spark
(aarch64). Approved lab users get a Coder workspace (browser code-server +
OpenCode CLI) wired to the locally hosted **Qwen3.8-27B** model through a
**LiteLLM** inference gateway, reachable from anywhere over **Tailscale** —
with no public ports.

```
User (Tailscale)
   │  HTTPS via Caddy edge proxy (127.0.0.1:8080)
   ▼
Coder workspace ── code-server (:8443) + OpenCode CLI
   │
   ▼
LiteLLM (virtual keys, per-tier rpm/tpm/max-parallel)
   │
   ▼
vLLM (qwen38) → Qwen3.8-27B (NVFP4, 200k context)
```

> **Note:** The archived per-user OpenCode host binary (`deploy/opencode`,
> ~175 MB) is kept locally on the Spark but is not committed — it exceeds
> GitHub's 100 MB per-file limit. The current stack builds OpenCode from the
> install script inside the workspace image, so the binary is a legacy artifact
> from the archived approach (see `archived-opencode-approach` branch).

## What's in the repo

| Path | Purpose |
|------|---------|
| `compose.yaml` | Base stack: Caddy, control-api, Redis, Prometheus, Grafana, DCGM exporter |
| `compose.monitoring.yaml` | Monitoring add-on (node-exporter) |
| `deploy/docker-compose.yml` | Live service definitions: LiteLLM, Open WebUI, Coder, Postgres, portal backend |
| `deploy/litellm/` | LiteLLM config routing `srge/qwen3.8-27b` → vLLM |
| `deploy/coder-templates/` | `srge-dev.yaml` Coder workspace template (code-server + OpenCode) |
| `proxy/Caddyfile` | Caddy v2 edge proxy (single edge port 8080) |
| `apps/portal/index.html` | SRGE-branded landing page |
| `apps/control-api/` | FastAPI health-aggregation + SRGE resource metrics |
| `monitoring/` | Prometheus + Grafana (dashboards, datasources, secrets) |
| `gateway/policies/tiers.yaml` | Per-tier AI limits (admin/researcher/student/guest) |
| `scripts/verify.sh` | Compose validation + health + ARM64 + port-policy checks |
| `STATUS.md` / `DECISIONS.md` | Phase status + ADRs |
| `docs/architecture.md` | Component map + target network topology |

## Quick start

```bash
# 1. Copy the env template and fill in real secrets
cp .env.example .env   # .env is gitignored

# 2. Validate the compose files (no services started)
docker compose -f compose.yaml -f compose.monitoring.yaml config

# 3. Bring up the monitoring stack
docker compose -f compose.yaml -f compose.monitoring.yaml up -d

# 4. Verify
./scripts/verify.sh
```

The live inference stack (LiteLLM, Coder, Postgres, Open WebUI, vLLM) is
defined in `deploy/docker-compose.yml` and runs independently.

## Constraints

- **No public ports.** Every new service binds to `127.0.0.1`; only the
  SRGE portal, Coder web UI, and Grafana are exposed, and only through
  Tailscale Serve. vLLM's `0.0.0.0:8000` is pre-existing and untouched.
- **Tailscale-only remote access.** Configure `tailscale serve` once Serve is
  enabled in the Tailscale admin console.
- **Do not disturb** `qwen38` (working vLLM), `srge-open-webui`, or
  `nextcloud-aio-mastercontainer`.

## Status

Phases 0–2 done (audit, compose foundation, inference gateway). Phase 3
(Coder MVP) and Phase 4 (portal) are partial; Phase 6 (monitoring) is live
with two open items: the LiteLLM metrics endpoint needs the master key for
Prometheus, and the control-api metrics need conversion to Prometheus
exposition format. See `STATUS.md` for the full phase tracker.
