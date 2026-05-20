#!/usr/bin/env bash
# =============================================================================
# infra/scripts/backup-postgres.sh  —  PostgreSQL backup (self-hosted path)
# =============================================================================
# Runs pg_dump, generates SHA256 checksum, uploads to MinIO backup bucket,
# and emits a JSON manifest with timestamp/duration/size/checksum/status.
#
# For managed PostgreSQL (Cloud SQL / RDS / Azure DB) this script is not used
# for the actual dump — the managed service owns backup execution. Use the
# backup verification procedure in backup-restore-runbook.md §3.1 instead.
#
# Usage:
#   DATABASE_URL=postgresql+asyncpg://vidya:pass@host:5432/vidya \
#   S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   bash infra/scripts/backup-postgres.sh
#
# Required env vars:
#   DATABASE_URL       — postgresql+asyncpg:// URL (asyncpg prefix is stripped)
#   S3_ACCESS_KEY      — MinIO/S3 access key
#   S3_SECRET_KEY      — MinIO/S3 secret key
# Optional env vars:
#   BACKUP_S3_ENDPOINT — default: http://localhost:9000
#   BACKUP_BUCKET_DB   — default: vidya-backup-db
#   BACKUP_MANIFESTS   — default: vidya-backup-manifests
#   RETENTION_DAYS     — ILM expiry; default: 7
# =============================================================================
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY must be set}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-http://localhost:9000}"
BACKUP_BUCKET_DB="${BACKUP_BUCKET_DB:-vidya-backup-db}"
BACKUP_MANIFESTS="${BACKUP_MANIFESTS:-vidya-backup-manifests}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

log()  { echo "[backup-postgres] $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "[backup-postgres] FAIL: $*" >&2
         # Emit failure manifest before exiting
         MANIFEST="{\"component\":\"postgres\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"status\":\"failure\",\"error\":\"$*\"}"
         printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/postgres_latest.json" 2>/dev/null || true
         exit 1; }

TIMESTAMP=$(date -u +%Y%m%d_%H%M%SZ)
DUMP_FILE="vidya_postgres_${TIMESTAMP}.dump"
SHA_FILE="${DUMP_FILE}.sha256"
MANIFEST_FILE="manifest_postgres_${TIMESTAMP}.json"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

START_TS=$(date +%s)

# Configure mc
mc alias set bk "$BACKUP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet
mc mb --ignore-existing "bk/${BACKUP_BUCKET_DB}"   || true
mc mb --ignore-existing "bk/${BACKUP_MANIFESTS}" || true
mc ilm add --expiry-days "$RETENTION_DAYS" "bk/${BACKUP_BUCKET_DB}" 2>/dev/null || true

# pg_dump — strip +asyncpg driver prefix for pg_dump compatibility
PG_URL=$(echo "$DATABASE_URL" | sed 's|postgresql+asyncpg://|postgresql://|')
log "Starting pg_dump to ${TMP_DIR}/${DUMP_FILE}"
pg_dump --format=custom --no-acl --no-owner "$PG_URL" -f "${TMP_DIR}/${DUMP_FILE}" \
    || fail "pg_dump failed — check DATABASE_URL and PostgreSQL connectivity"

# Generate and verify SHA256 checksum
CHECKSUM=$(sha256sum "${TMP_DIR}/${DUMP_FILE}" | awk '{print $1}')
echo "$CHECKSUM  ${DUMP_FILE}" > "${TMP_DIR}/${SHA_FILE}"
SIZE=$(stat -c %s "${TMP_DIR}/${DUMP_FILE}")
log "Checksum: ${CHECKSUM}  Size: ${SIZE} bytes"

# Upload dump + checksum file
log "Uploading ${DUMP_FILE}..."
mc cp "${TMP_DIR}/${DUMP_FILE}" "bk/${BACKUP_BUCKET_DB}/${DUMP_FILE}"
mc cp "${TMP_DIR}/${SHA_FILE}"  "bk/${BACKUP_BUCKET_DB}/${SHA_FILE}"

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

# Emit manifest (latest + timestamped)
MANIFEST="{\"component\":\"postgres\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"duration_seconds\":${DURATION},\"size_bytes\":${SIZE},\"checksum_sha256\":\"${CHECKSUM}\",\"backup_file\":\"${DUMP_FILE}\",\"status\":\"success\"}"
printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/postgres_latest.json"
printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/${MANIFEST_FILE}"

log "Done. duration=${DURATION}s size=${SIZE}B sha256=${CHECKSUM}"
log "Backup: bk/${BACKUP_BUCKET_DB}/${DUMP_FILE}"
