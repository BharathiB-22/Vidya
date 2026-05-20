#!/usr/bin/env bash
# =============================================================================
# infra/scripts/restore-postgres.sh  —  PostgreSQL restore from backup
# =============================================================================
# Downloads a pg_dump backup from MinIO, verifies its SHA256 checksum,
# and restores it to the target PostgreSQL instance.
#
# AUDIT LOG INVARIANT (NON-NEGOTIABLE):
#   audit_logs is append-only and must never be partially restored.
#   This script performs FULL database restores only.
#   For per-tenant schema restores, audit_logs is explicitly excluded and
#   the operator is warned before proceeding.
#
# EXAM_FERNET_KEY INVARIANT:
#   Sealed exam papers in the DB are Fernet-encrypted. The Vault raft snapshot
#   must match the same point-in-time as the DB backup. Restore Vault first,
#   verify ESO sync, then restore PostgreSQL.
#
# Usage (full restore):
#   BACKUP_FILE=vidya_postgres_20260520_200000Z.dump \
#   DATABASE_URL=postgresql+asyncpg://vidya:pass@host:5432/vidya \
#   S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   bash infra/scripts/restore-postgres.sh
#
# Usage (per-tenant schema, excludes audit_logs):
#   RESTORE_MODE=tenant TENANT_SLUG=acme \
#   BACKUP_FILE=vidya_postgres_20260520_200000Z.dump \
#   DATABASE_URL=... S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   bash infra/scripts/restore-postgres.sh
#
# Required env vars:
#   BACKUP_FILE        — dump filename in the backup bucket
#   DATABASE_URL       — target DB URL (postgresql+asyncpg:// or postgresql://)
#   S3_ACCESS_KEY / S3_SECRET_KEY
# Optional env vars:
#   RESTORE_MODE       — "full" (default) or "tenant"
#   TENANT_SLUG        — required when RESTORE_MODE=tenant
#   BACKUP_S3_ENDPOINT — default: http://localhost:9000
#   BACKUP_BUCKET_DB   — default: vidya-backup-db
#   BACKUP_MANIFESTS   — default: vidya-backup-manifests
# =============================================================================
set -euo pipefail

: "${BACKUP_FILE:?BACKUP_FILE must be set (e.g. vidya_postgres_20260520_200000Z.dump)}"
: "${DATABASE_URL:?DATABASE_URL must be set}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY must be set}"
RESTORE_MODE="${RESTORE_MODE:-full}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-http://localhost:9000}"
BACKUP_BUCKET_DB="${BACKUP_BUCKET_DB:-vidya-backup-db}"
BACKUP_MANIFESTS="${BACKUP_MANIFESTS:-vidya-backup-manifests}"

log()  { echo "[restore-postgres] $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "[restore-postgres] FAIL: $*" >&2; exit 1; }

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

PG_URL=$(echo "$DATABASE_URL" | sed 's|postgresql+asyncpg://|postgresql://|')

# ── Per-tenant mode safety warning ──────────────────────────────────────────
if [ "$RESTORE_MODE" = "tenant" ]; then
    : "${TENANT_SLUG:?TENANT_SLUG must be set when RESTORE_MODE=tenant}"
    SCHEMA="tenant_${TENANT_SLUG}"
    echo ""
    echo "============================================================"
    echo "WARNING: Per-tenant schema restore requested."
    echo "  Schema:    ${SCHEMA}"
    echo "  Target DB: ${PG_URL%%@*}@..."
    echo ""
    echo "AUDIT LOG INVARIANT: audit_logs will NOT be restored."
    echo "Only tables other than audit_logs in ${SCHEMA} will be restored."
    echo ""
    echo "This may leave the tenant in an inconsistent state if audit_logs"
    echo "referenced the restored data. Verify manually after restore."
    echo "============================================================"
    echo ""
    read -p "Type 'confirm-tenant-restore' to proceed: " confirm
    [ "$confirm" = "confirm-tenant-restore" ] || { log "Aborted."; exit 0; }
fi

# ── Download backup ──────────────────────────────────────────────────────────
mc alias set bk "$BACKUP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet

log "Downloading ${BACKUP_FILE} from bk/${BACKUP_BUCKET_DB}/"
mc cp "bk/${BACKUP_BUCKET_DB}/${BACKUP_FILE}"       "${TMP_DIR}/${BACKUP_FILE}"
mc cp "bk/${BACKUP_BUCKET_DB}/${BACKUP_FILE}.sha256" "${TMP_DIR}/${BACKUP_FILE}.sha256" \
    || fail "Checksum file ${BACKUP_FILE}.sha256 not found — backup may be corrupt"

# ── Verify SHA256 checksum ───────────────────────────────────────────────────
log "Verifying SHA256 checksum..."
EXPECTED=$(awk '{print $1}' "${TMP_DIR}/${BACKUP_FILE}.sha256")
ACTUAL=$(sha256sum "${TMP_DIR}/${BACKUP_FILE}" | awk '{print $1}')

if [ "$EXPECTED" != "$ACTUAL" ]; then
    fail "Checksum mismatch! expected=${EXPECTED} actual=${ACTUAL} — backup file is corrupt, do not restore"
fi
log "Checksum verified: ${ACTUAL}"

# ── Restore ──────────────────────────────────────────────────────────────────
if [ "$RESTORE_MODE" = "full" ]; then
    log "Performing FULL database restore to ${PG_URL%%:*}..."
    echo ""
    echo "============================================================"
    echo "WARNING: Full database restore will OVERWRITE all data."
    echo "  Target: ${PG_URL%%@*}@..."
    echo "  Backup: ${BACKUP_FILE}"
    echo ""
    echo "Ensure the application is scaled to 0 replicas before proceeding."
    echo "  kubectl scale deployment vidya-api vidya-worker vidya-worker-heavy \\"
    echo "    --replicas=0 -n vidya-system"
    echo "============================================================"
    echo ""
    read -p "Type 'confirm-full-restore' to proceed: " confirm
    [ "$confirm" = "confirm-full-restore" ] || { log "Aborted."; exit 0; }

    pg_restore --format=custom --no-acl --no-owner \
        --clean --if-exists \
        -d "$PG_URL" \
        "${TMP_DIR}/${BACKUP_FILE}" \
        || fail "pg_restore failed — check PostgreSQL connectivity and permissions"
    log "Full restore complete."

else
    # Per-tenant schema restore — audit_logs excluded
    log "Performing per-tenant schema restore: ${SCHEMA} (audit_logs excluded)..."
    pg_restore --format=custom --no-acl --no-owner \
        --schema="${SCHEMA}" \
        --exclude-table="${SCHEMA}.audit_logs" \
        -d "$PG_URL" \
        "${TMP_DIR}/${BACKUP_FILE}" \
        || fail "pg_restore (tenant schema) failed"
    log "Per-tenant restore complete (audit_logs preserved)."
fi

# ── Post-restore verification ────────────────────────────────────────────────
log "Verifying alembic_version in public schema..."
psql "$PG_URL" -c "SELECT version_num FROM alembic_version;" \
    || log "WARN: Could not read alembic_version — verify migration state manually"

if [ "$RESTORE_MODE" = "full" ]; then
    log "Checking tenant schemas..."
    TENANT_COUNT=$(psql "$PG_URL" -t -c \
        "SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname LIKE 'tenant_%';" | xargs)
    log "Tenant schema count: ${TENANT_COUNT}"
    AUDIT_COUNT=$(psql "$PG_URL" -t -c \
        "SELECT sum(n_live_tup) FROM pg_stat_user_tables WHERE schemaname LIKE 'tenant_%' AND relname='audit_logs';" | xargs)
    log "Total audit_log rows across all tenant schemas: ${AUDIT_COUNT}"
fi

log "Restore complete. Run: bash infra/scripts/restore-drill.sh --validate-only to run full smoke checks."
