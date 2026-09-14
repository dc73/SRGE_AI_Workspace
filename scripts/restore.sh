#!/usr/bin/env bash
# SRGE AI Workspace — restore script (Phase 8).
# Restores Postgres (coder + litellm) and config files from a backup dir.
# Usage: ./scripts/restore.sh /tmp/srge-backup-<stamp>
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${1:-/tmp/srge-backup}"
if [ ! -d "$BACKUP_DIR" ]; then
  echo "Backup dir not found: $BACKUP_DIR" >&2
  exit 1
fi

echo "== 1. Restore Postgres (coder + litellm) =="
if [ -f "$BACKUP_DIR/coder.dump" ]; then
  docker cp "$BACKUP_DIR/coder.dump" srge-postgres:/tmp/coder.dump
  docker exec srge-postgres pg_restore -U coder -d coder --clean --if-exists --no-owner /tmp/coder.dump >/dev/null \
    && echo "PASS: coder DB restored"
fi
if [ -f "$BACKUP_DIR/litellm.dump" ]; then
  docker cp "$BACKUP_DIR/litellm.dump" srge-postgres:/tmp/litellm.dump
  docker exec srge-postgres pg_restore -U coder -d litellm --clean --if-exists --no-owner /tmp/litellm.dump >/dev/null \
    && echo "PASS: litellm DB restored"
fi

echo "== 2. Restore config files =="
[ -f "$BACKUP_DIR/docker-compose.yml.bak" ] && cp "$BACKUP_DIR/docker-compose.yml.bak" deploy/docker-compose.yml && echo "PASS: docker-compose.yml restored"
[ -f "$BACKUP_DIR/litellm_config.yaml.bak" ] && cp "$BACKUP_DIR/litellm_config.yaml.bak" deploy/litellm/litellm_config.yaml && echo "PASS: litellm_config.yaml restored"
[ -f "$BACKUP_DIR/srge-dev.yaml.bak" ] && cp "$BACKUP_DIR/srge-dev.yaml.bak" deploy/coder-templates/srge-dev.yaml && echo "PASS: srge-dev.yaml restored"
[ -f "$BACKUP_DIR/init.sql.bak" ] && cp "$BACKUP_DIR/init.sql.bak" deploy/postgres-init/init.sql && echo "PASS: init.sql restored"
[ -f "$BACKUP_DIR/tiers.yaml.bak" ] && cp "$BACKUP_DIR/tiers.yaml.bak" gateway/policies/tiers.yaml && echo "PASS: tiers.yaml restored"
[ -f "$BACKUP_DIR/Caddyfile.bak" ] && cp "$BACKUP_DIR/Caddyfile.bak" proxy/Caddyfile && echo "PASS: Caddyfile restored"
[ -f "$BACKUP_DIR/compose.yaml.bak" ] && cp "$BACKUP_DIR/compose.yaml.bak" compose.yaml && echo "PASS: compose.yaml restored"

echo "Restore complete from $BACKUP_DIR"
echo "NOTE: restart affected services to apply DB restores (coder, litellm)."
