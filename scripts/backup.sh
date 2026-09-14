#!/usr/bin/env bash
# SRGE AI Workspace — backup script (Phase 8).
# Backs up Postgres (coder + litellm DBs), config files, and the tiers policy.
# Safe to run; does not touch the running services.
set -euo pipefail
cd "$(dirname "$0")/.."

STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/srge-backup-${STAMP}"
mkdir -p "$BACKUP_DIR"

echo "== 1. Postgres dumps (coder + litellm) =="
docker exec srge-postgres pg_dump -U coder -d coder --format=custom --file=/tmp/coder.dump \
  && docker cp srge-postgres:/tmp/coder.dump "$BACKUP_DIR/coder.dump" \
  && echo "PASS: coder DB dumped"

docker exec srge-postgres pg_dump -U coder -d litellm --format=custom --file=/tmp/litellm.dump \
  && docker cp srge-postgres:/tmp/litellm.dump "$BACKUP_DIR/litellm.dump" \
  && echo "PASS: litellm DB dumped"

echo "== 2. Config + policy files =="
cp deploy/docker-compose.yml "$BACKUP_DIR/docker-compose.yml.bak"
cp deploy/litellm/litellm_config.yaml "$BACKUP_DIR/litellm_config.yaml.bak"
cp deploy/coder-templates/srge-dev.yaml "$BACKUP_DIR/srge-dev.yaml.bak"
cp deploy/postgres-init/init.sql "$BACKUP_DIR/init.sql.bak"
cp gateway/policies/tiers.yaml "$BACKUP_DIR/tiers.yaml.bak"
cp proxy/Caddyfile "$BACKUP_DIR/Caddyfile.bak"
cp compose.yaml "$BACKUP_DIR/compose.yaml.bak"
echo "PASS: config files backed up"

echo "== 3. Backup manifest =="
cat > "$BACKUP_DIR/MANIFEST.txt" <<EOF
SRGE AI Workspace backup — $STAMP
Postgres dumps: coder.dump, litellm.dump
Configs: docker-compose.yml, litellm_config.yaml, srge-dev.yaml, init.sql, tiers.yaml, Caddyfile, compose.yaml
Restore: ./scripts/restore.sh $BACKUP_DIR
EOF
ls -la "$BACKUP_DIR"
echo "Backup complete: $BACKUP_DIR"
