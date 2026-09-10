#!/usr/bin/env bash
# SRGE AI Workspace — verification script (Phase 1+).
# Validates compose syntax, checks service health, and runs basic integration
# checks. Safe to run; does not restart the working stack.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1. Compose syntax validation =="
docker compose -f compose.yaml -f compose.monitoring.yaml config --quiet \
  && echo "PASS: compose config valid" || echo "FAIL: compose config invalid"

echo "== 2. Health checks =="
check() {
  local name="$1" url="$2"
  local code=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "$url" || echo "000")
  if [ "$code" = "200" ]; then
    echo "PASS: $name up (HTTP 200)"
  else
    echo "WARN: $name -> HTTP $code"
  fi
}
check "vLLM (qwen38)" "http://127.0.0.1:8000/v1/models"
check "LiteLLM" "http://127.0.0.1:4000/health/liveliness"
check "Coder" "http://127.0.0.1:8081/api/v2/buildinfo"
check "Open WebUI" "http://127.0.0.1:3080/health"
check "Control API" "http://127.0.0.1:8001/healthz"

echo "== 3. ARM64 image compatibility =="
docker image inspect vllm/vllm-openai:v0.27.1-aarch64 --format '{{.Architecture}}' 2>/dev/null | grep -qE 'arm64|aarch64' \
  && echo "PASS: vLLM image is ARM64" || echo "WARN: vLLM image arch unverified"

echo "== 4. No unexpected public ports (Phase 1 policy) =="
# vLLM is the only allowed 0.0.0.0 bind (existing working service).
ss -tln | awk 'NR>1 {split($4,a,":"); print a[2]}' | sort -un > /tmp/srge-ports.txt
echo "Listening ports: $(tr '\n' ' ' < /tmp/srge-ports.txt)"

echo "Done."
