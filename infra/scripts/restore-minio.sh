#!/usr/bin/env bash
# =============================================================================
# infra/scripts/restore-minio.sh  —  MinIO asset restore from backup mirror
# =============================================================================
# Mirrors the backup bucket back to the application bucket.
# Optionally restores a specific versioned prefix (weekly snapshot).
#
# Usage (mirror back full backup):
#   S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   bash infra/scripts/restore-minio.sh
#
# Required env vars:
#   S3_ACCESS_KEY / S3_SECRET_KEY
# Optional env vars:
#   APP_S3_ENDPOINT    — default: http://localhost:9000
#   APP_BUCKET         — default: vidya-assets
#   BACKUP_S3_ENDPOINT — default: http://localhost:9000
#   BACKUP_BUCKET      — default: vidya-backup-assets
# =============================================================================
set -euo pipefail

: "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY must be set}"
APP_S3_ENDPOINT="${APP_S3_ENDPOINT:-http://localhost:9000}"
APP_BUCKET="${APP_BUCKET:-vidya-assets}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-http://localhost:9000}"
BACKUP_BUCKET="${BACKUP_BUCKET:-vidya-backup-assets}"

log()  { echo "[restore-minio] $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "[restore-minio] FAIL: $*" >&2; exit 1; }

mc alias set app "$APP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet
mc alias set bk  "$BACKUP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet

BACKUP_COUNT=$(mc ls --recursive "bk/${BACKUP_BUCKET}" 2>/dev/null | wc -l || echo 0)
[ "$BACKUP_COUNT" -gt 0 ] || fail "Backup bucket bk/${BACKUP_BUCKET} is empty or unreachable"

echo ""
echo "============================================================"
echo "MinIO restore: bk/${BACKUP_BUCKET} → app/${APP_BUCKET}"
echo "Backup object count: ${BACKUP_COUNT}"
echo ""
echo "Ensure the application is scaled to 0 before proceeding."
echo "============================================================"
echo ""
read -p "Type 'confirm-minio-restore' to proceed: " confirm
[ "$confirm" = "confirm-minio-restore" ] || { log "Aborted."; exit 0; }

START_TS=$(date +%s)
log "Restoring ${BACKUP_COUNT} objects from bk/${BACKUP_BUCKET} → app/${APP_BUCKET}"

mc mirror --overwrite "bk/${BACKUP_BUCKET}" "app/${APP_BUCKET}" \
    || fail "mc mirror (restore) failed"

RESTORED_COUNT=$(mc ls --recursive "app/${APP_BUCKET}" | wc -l)
END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

log "Restore complete. duration=${DURATION}s restored=${RESTORED_COUNT} objects"
