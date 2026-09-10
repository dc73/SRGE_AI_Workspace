# SRGE AI Workspace — Architecture

## Overview

SRGE AI Workspace is a self-hosted platform on the Embry-Riddle Space Robotics
and Generative Estimation (SRGE) Lab's NVIDIA DGX Spark. It lets approved lab
users access OpenCode and the locally hosted Qwen model from anywhere via
Tailscale.

## Component map (current, verified live)

| Component | Container / process | Role |
|-----------|---------------------|------|
| vLLM | `qwen38` (vllm-openai:v0.27.1-aarch64) | Shared Qwen3.8-27B inference |
| LiteLLM | `srge-litellm` | Authenticated inference gateway, per-user keys & limits |
| Coder | `srge-coder` (coder:1.44.6) | User accounts, workspace lifecycle, browser apps |
| code-server | inside each workspace | Browser-based VS Code |
| OpenCode CLI | inside each workspace | Agent that calls Qwen via LiteLLM |
| PostgreSQL | `srge-postgres` (postgres:16) | Persistent data for Coder + LiteLLM |
| Open WebUI | `srge-open-webui` | Human chat UI (existing, do not stop) |
| SRGE portal | `srge-portal` (build ./portal) | Branded Next.js frontend + control API |
| Nextcloud | `nextcloud-aio-mastercontainer` | Existing file service (do not stop) |

## Target network topology

```
edge        : Caddy (reverse proxy) + SRGE portal + Coder web UI
workspace    : user workspaces (code-server + OpenCode) + LiteLLM
inference-backend : vLLM + LiteLLM
monitoring   : Prometheus, Grafana, DCGM exporter, vLLM metrics
database     : PostgreSQL, Redis
```

Rules:
- vLLM lives only on `inference-backend`.
- LiteLLM lives on `inference-backend` AND `workspace`.
- Workspaces live on `workspace` and cannot reach vLLM directly.
- PostgreSQL/Redis live on `database` (not host-exposed).
- Monitoring services are internal / loopback-bound.
- Caddy is the only app-facing reverse proxy.

## Mermaid architecture diagram

```mermaid
flowchart LR
  subgraph Remote["Authorized device (tailnet)"]
    DEV[User device]
  end
  TS[Tailscale Serve (private HTTPS)]
  subgraph Edge["edge network"]
    CADDY[Caddy reverse proxy]
    PORTAL[SRGE Portal (Next.js)]
    CODER_UI[Coder Web UI :8081]
  end
  subgraph WS["workspace network"]
    WS1[User workspace\n(code-server + OpenCode CLI)]
    WS2[User workspace N]
  end
  subgraph IB["inference-backend"]
    VLLM[vLLM qwen38 :8000]
  end
  subgraph DB["database network"]
    PG[(PostgreSQL)]
    REDIS[(Redis)]
  end
  MON[Prometheus + Grafana + DCGM]

  DEV -->|Tailscale| TS
  TS --> CADDY
  CADDY --> PORTAL
  CADDY --> CODER_UI
  WS1 -->|OpenCode -> LiteLLM| LLM[LiteLLM]
  LLM --> VLLM
  LLM --> PG
  LLM --> REDIS
  CODER_UI -.manages.-> WS1
  MON -.scrapes.-> VLLM
  MON -.scrapes.-> LLM
```

## Request path (Qwen inference)

```
User device -> Tailscale -> SRGE Portal -> Coder login -> isolated workspace
-> code-server terminal -> OpenCode CLI -> per-user LiteLLM virtual key
-> LiteLLM (limits/queue) -> vLLM -> Qwen3.8-27B
```

## Isolation guarantees
- Workspaces: no Docker socket, no NVIDIA device, no host root mounts,
  no other users' volumes.
- Inference: only via LiteLLM; no direct vLLM path from workspace network.
- Remote: only via Tailscale Serve; no public ports, no Funnel, no Cloudflare Tunnel.

## Assumptions
- Coder 1.44.6 `buildinfo` 404 is version-specific (route not present), not a fault.
- GB10 GPU temperature is not exposed via the queried nvidia-smi fields (N/A).
- vLLM currently on shared `srge` network (bypass risk) to be fixed in Phase 1/2.

## Open items
- Register `srge-dev` template in Coder (Phase 3).
- Tailscale Serve config (Phase 7).
- Monitoring stack deploy (Phase 6).
