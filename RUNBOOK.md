# SRGE AI Workspace — Runbook (external actions)

These four items each need an action **outside** the shell (a browser, the
Tailscale admin console, or root access). Everything runnable in the shell is
done.

## Phase 3 — Coder test-user login
- **Hash scheme (found in Coder source, `coderd/userpassword`)**: Coder hashes
  passwords with **PBKDF2-SHA256** (65535 iterations, 16-byte salt, 32-byte hash),
  stored in the `hashed_password` bytea column as a string of the form:
  `$pbkdf2-sha256$65535$<base64(salt)>$<base64(hash)>`.
- The admin user's stored hash (44 bytes) is the **base64 of the raw 32-byte PBKDF2
  hash** (no salt stored inline) — this is the 1.44.6 format.
- **To fix login**: open the **Coder web UI** (`http://127.0.0.1:8081` or
  `https://spark-f0d1.tail6c1096.ts.net/coder`), log in as `admin`, go to
  **Users → srge-testuser → Edit → set password**, and save. The web UI computes the
  correct 1.44.6 hash. Then launch a `srge-dev` workspace from the UI.
- The Coder v0 API endpoints require a browser session cookie, so the web UI is the
  supported path for password changes.

## Phases 4 & 7 — Tailscale-only remote access — DONE
- **Serve is enabled** and running in the background:
  `https://spark-f0d1.tail6c1096.ts.net/` → proxies `http://127.0.0.1:8080` (Caddy edge).
- Remote HTTPS access now works; no public ports are exposed.

## Phase 6 — LiteLLM metrics
- The LiteLLM build in use (`ghcr.io/berriai/litellm:main-latest`) returns **404** for
  `/metrics` (the Prometheus metrics endpoint is not exposed in this build).
- **To fix**: the Prometheus `litellm` target stays DOWN until you either:
  1. Upgrade the LiteLLM image to a build that exposes `/metrics`, OR
  2. Check the LiteLLM config/env for a flag to enable the Prometheus collector.
- The `litellm` Prometheus job in `monitoring/prometheus/prometheus.yaml` currently has no
  working `http_headers` (Prometheus 2.55 doesn't parse the field), so even if `/metrics`
  were up, the master-key auth header isn't being sent. The litellm job is DOWN.

## Phase 8 — DCGM host engine — BLOCKED (package conflict)
- The apt package is **`datacenter-gpu-manager`** (not `nvidia-dcgm`).
- `sudo apt-get install -y datacenter-gpu-manager` fails: it pulls in glibc/libstdc++
  upgrades that **Break** the system's installed versions (libicu74, libidn2-0, libpam0g,
  libstdc++6, libunistring5, zlib1g). Even `apt-get --fix-broken install` + explicit
  upgrade of those libs still fails on the same conflict.
- **To fix**: run as root: `apt-get install --fix-broken` after aligning the glibc/libstdc++
  versions, OR install the DCGM host engine from the NVIDIA data-center GPU manager
  `.run` file / static binary. Then start the DCGM host engine (`dcgmlister` /
  `nvidia-dcgm-engine`) and re-enable the `dcgm-exporter` service in `compose.yaml`.
- Until then, GPU metrics are provided by `nvidia-smi` (util/power/temp).
