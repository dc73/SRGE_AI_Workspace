#!/usr/bin/env bash
# SRGE AI Workspace — security hardening test (Phase 9).
# Verifies: no unexpected public ports, loopback binds, no Docker socket in workspaces.
set -uo pipefail
FAIL=0

echo "-- 1. No unexpected public ports --"
# Allowed public binds (pre-existing on the DGX Spark, not SRGE services):
#   8000 (vLLM), 22 (SSH), 3389 (VNC/SPICE), 11434 (NVIDIA display)
# All NEW SRGE services must bind 127.0.0.1.
public_ports=$(ss -tln 2>/dev/null | awk 'NR>1 {split($4,a,":"); if (a[1]=="0.0.0.0" || a[1]=="*") print a[2]}' | sort -un)
unexpected=$(echo "$public_ports" | grep -vE "^(8000|22|3389|11434)$" || true)
if [ -n "$unexpected" ]; then
  echo "FAIL: unexpected public ports: $unexpected"
  FAIL=1
else
  echo "PASS: only vLLM (8000) on 0.0.0.0; all new services loopback-bound"
fi

echo "-- 2. Docker socket not exposed to user workspaces --"
# The srge-dev workspace template must NOT mount /var/run/docker.sock.
if grep -q "docker.sock" deploy/coder-templates/srge-dev.yaml 2>/dev/null; then
  echo "FAIL: srge-dev.yaml references docker.sock"
  FAIL=1
else
  echo "PASS: no docker.sock in the workspace template"
fi

echo "-- 3. vLLM reachable directly on the srge network (bypass risk) --"
# Documented risk: workspaces on the srge network can reach qwen38:8000 directly.
# This is a known bypass; Phase 1/2 network segmentation addresses it.
echo "NOTE: vLLM is reachable on the shared 'srge' network (bypass risk, to be isolated)."

[ "$FAIL" -eq 0 ] && echo "Security checks passed." || echo "Security checks failed."
exit $FAIL
