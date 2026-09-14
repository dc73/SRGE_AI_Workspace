#!/usr/bin/env bash
# SRGE AI Workspace — integration test (Phase 9).
# Verifies the end-to-end inference path: client -> LiteLLM -> vLLM -> Qwen.
set -uo pipefail

MASTER_KEY="srge-litellm-master-key"
BASE="http://127.0.0.1:4000"
MODEL="srge/qwen3.8-27b"

echo "-- 1. LiteLLM /v1/models returns the model --"
models=$(curl -s -H "Authorization: Bearer $MASTER_KEY" "$BASE/v1/models")
echo "$models" | grep -q "$MODEL" && echo "PASS: model listed" || { echo "FAIL: model not listed"; exit 1; }

echo "-- 2. Non-streaming chat completion --"
code=$(curl -s -o /tmp/srge_infer_out.json -w "%{http_code}" -X POST "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in 3 words.\"}],\"max_tokens\":40}")
if [ "$code" = "200" ]; then
  echo "PASS: non-streaming completion (HTTP 200)"
  python3 -c "import json;d=json.load(open('/tmp/srge_infer_out.json'));print('model:',d.get('model'));print('content:',d['choices'][0]['message']['content'][:60])" 2>/dev/null || cat /tmp/srge_infer_out.json | head -c 120
else
  echo "FAIL: completion returned HTTP $code"; exit 1
fi

echo "-- 3. Streaming (SSE) completion --"
sse=$(curl -sN -X POST "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":true,\"max_tokens\":20}" | head -c 200)
echo "$sse" | grep -q "data:" && echo "PASS: streaming SSE events received" || { echo "FAIL: no SSE events"; exit 1; }

echo "-- 4. Per-user virtual key (rate limit) --"
# Use the admin tier key (rpm 60). A single request should 200.
ADMIN_KEY=$(docker exec srge-postgres psql -U coder -d litellm -t -A -c "SELECT token FROM \"LiteLLM_VerificationToken\" WHERE key_name LIKE '%CY1w';" | xargs)
# The 'token' column is a hash; the raw admin key is known from Phase 2.
ADMIN_KEY="sk-n8Ewhsr7Jbu3gvvB2sCY1w"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $ADMIN_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":10}")
[ "$code" = "200" ] && echo "PASS: virtual key auth (HTTP 200)" || { echo "FAIL: virtual key returned $code"; exit 1; }

echo "All integration checks passed."
