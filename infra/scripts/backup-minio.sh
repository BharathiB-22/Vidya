#!/usr/bin/env bash
# =============================================================================
# infra/scripts/backup-minio.sh  —  MinIO asset mirror backup
# =============================================================================
# Mirrors the application vidya-assets bucket to a dedicated backup bucket
# using mc mirror, then emits a JSON manifest with object count and metadata.
#
# BUCKET VERSIONING: backup buckets should have versioning enabled for point-in-
# time recovery of individual objects. Enable once before first backup:
#   mc version enable bk/vidya-backup-assets
#
# WORM / IMMUTABLE STORAGE: for production, also enable ILM Governance locks:
#   mc ilm add --expiry-days 7 --transition-days 30 bk/vidya-backup-assets
# See backup-restore-runbook.md §5 for the full configuration sequence.
#
# Usage:
#   S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   bash infra/scripts/backup-minio.sh
#
# Required env vars:
#   S3_ACCESS_KEY      — shared credential for both app and backup MinIO
#   S3_SECRET_KEY
# Optional env vars:
#   APP_S3_ENDPOINT    — default: http://localhost:9000
#   APP_BUCKET         — default: vidya-assets
#   BACKUP_S3_ENDPOINT — default: http://localhost:9000
#   BACKUP_BUCKET      — default: vidya-backup-assets
#   BACKUP_MANIFESTS   — default: vidya-backup-manifests
#   RETENTION_DAYS     — ILM expiry; default: 7
# =============================================================================
set -euo pipefail

: "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY must be set}"
APP_S3_ENDPOINT="${APP_S3_ENDPOINT:-http://localhost:9000}"
APP_BUCKET="${APP_BUCKET:-vidya-assets}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-http://localhost:9000}"
BACKUP_BUCKET="${BACKUP_BUCKET:-vidya-backup-assets}"
BACKUP_MANIFESTS="${BACKUP_MANIFESTS:-vidya-backup-manifests}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

log()  { echo "[backup-minio] $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "[backup-minio] FAIL: $*" >&2
         MANIFEST="{\"component\":\"minio\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"status\":\"failure\",\"error\":\"$*\"}"
         printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/minio_latest.json" 2>/dev/null || true
         exit 1; }

TIMESTAMP=$(date -u +%Y%m%d_%H%M%SZ)
START_TS=$(date +%s)

mc alias set app "$APP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet
mc alias set bk  "$BACKUP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet

mc mb --ignore-existing "bk/${BACKUP_BUCKET}"   || true
mc mb --ignore-existing "bk/${BACKUP_MANIFESTS}" || true

# Enable versioning on backup bucket (idempotent if already enabled)
mc version enable "bk/${BACKUP_BUCKET}" 2>/dev/null || true
mc ilm add --expiry-days "$RETENTION_DAYS" "bk/${BACKUP_BUCKET}" 2>/dev/null || true

BEFORE_COUNT=$(mc ls --recursive "app/${APP_BUCKET}" 2>/dev/null | wc -l || echo 0)
log "Mirroring app/${APP_BUCKET} (${BEFORE_COUNT} objects) → bk/${BACKUP_BUCKET}"

mc mirror --overwrite "app/${APP_BUCKET}" "bk/${BACKUP_BUCKET}" \
    || fail "mc mirror failed — check MinIO connectivity and credentials"

AFTER_COUNT=$(mc ls --recursive "bk/${BACKUP_BUCKET}" | wc -l)
END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

log "Mirror complete: ${AFTER_COUNT} objects in backup bucket"

MANIFEST="{\"component\":\"minio\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"duration_seconds\":${DURATION},\"object_count\":${AFTER_COUNT},\"source_object_count\":${BEFORE_COUNT},\"status\":\"success\"}"
printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/minio_latest.json"
printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/minio_${TIMESTAMP}.json"

log "Done. duration=${DURATION}s objects=${AFTER_COUNT}"
