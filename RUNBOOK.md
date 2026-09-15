# SRGE AI Workspace — Runbook (external actions)

These four items each need an action **outside** the shell (a browser, the
Tailscale admin console, or root access). Everything runnable in the shell is
done.

## Phase 3 — Coder test-user login
- The test user's password must be set via the **Coder web UI** (`http://127.0.0.1:8081`),
  which computes the correct salted hash (the admin hash is 44 bytes, not the 32-byte
  plain SHA-256 I set directly in the DB).
- Then launch a workspace from the **Coder web UI** (template `srge-dev`).
- The Coder v0 API requires a browser session cookie, so the web UI is the supported path.

## Phases 4 & 7 — Tailscale-only remote access — DONE
- **Serve is enabled** and running in the background:
  `https://spark-f0d1.tail6c1096.ts.net/` → proxies `http://127.0.0.1:8080` (Caddy edge).
- Remote HTTPS access now works; no public ports are exposed.

## Phase 6 — LiteLLM metrics
- The LiteLLM build in use returns **404** for `/metrics` (the Prometheus metrics
  endpoint is not exposed in this build). To get the Prometheus `litellm` target UP,
  use a LiteLLM build/version that exposes `/metrics`, or enable it via config.

## Phase 8 — DCGM host engine — BLOCKED (package conflict)
- The apt package is **`datacenter-gpu-manager`** (not `nvidia-dcgm`).
- `sudo apt-get install -y datacenter-gpu-manager` fails: it pulls in glibc/libstdc++
  upgrades that **Break** the system's installed versions (libicu, libidn2, libpam,
  libstdc++6, libunistring, zlib). So the DCGM host engine cannot be installed cleanly
  on this DGX Spark without resolving the glibc conflict.
- GPU metrics remain provided by `nvidia-smi` (util/power/temp). The `dcgm-exporter`
  service stays commented out in `compose.yaml` until the DCGM host engine is available.
