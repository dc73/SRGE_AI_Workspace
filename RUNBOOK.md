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

## Phases 4 & 7 — Tailscale-only remote access
- Enable **Serve** in the Tailscale admin console (it is not enabled on the tailnet).
- Then run: `tailscale serve --bg 8080` to front-end the Caddy edge proxy (port 8080)
  with HTTPS on the tailnet. No public ports are exposed.

## Phase 6 — LiteLLM metrics
- The LiteLLM build in use returns **404** for `/metrics` (the Prometheus metrics
  endpoint is not exposed in this build). To get the Prometheus `litellm` target UP,
  use a LiteLLM build/version that exposes `/metrics`, or enable it via config.

## Phase 8 — DCGM host engine
- Install the NVIDIA DCGM host engine (needs **root/sudo**):
  `sudo apt-get install -y nvidia-dcgm` (or the NVIDIA data-center GPU manager package).
- Then re-enable the `dcgm-exporter` service in `compose.yaml` (currently commented out).
- Until then, GPU metrics are provided by `nvidia-smi` (util/power/temp).
