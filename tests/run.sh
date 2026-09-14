#!/usr/bin/env bash
# SRGE AI Workspace — test runner (Phase 9).
# Runs the verification script, integration checks, and security hardening checks.
# Safe to run; does not restart the working stack.
set -uo pipefail
cd "$(dirname "$0")/.."

PASS=0
FAIL=0

run_check() {
  local name="$1"; shift
  echo "== $name =="
  if "$@"; then
    echo "PASS: $name"
    PASS=$((PASS+1))
  else
    echo "FAIL: $name"
    FAIL=$((FAIL+1))
  fi
}

# 1. Compose + health + ARM64 + port policy
run_check "verify.sh (compose/health/arm64/ports)" bash scripts/verify.sh

# 2. Integration: end-to-end inference path (LiteLLM -> vLLM -> Qwen)
run_check "inference path" bash tests/integration/test_inference.sh

# 3. Security: no public ports, loopback binds, no Docker socket in workspaces
run_check "security hardening" bash tests/security/test_security.sh

echo "======================"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] && echo "All checks passed." || echo "Some checks failed."
exit $FAIL
