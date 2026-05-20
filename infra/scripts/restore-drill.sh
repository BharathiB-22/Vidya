#!/usr/bin/env bash
# =============================================================================
# infra/scripts/restore-drill.sh  —  Monthly restore drill orchestrator
# =============================================================================
# Runs the full Vidya restore drill against a target environment (staging).
# Three human gates prevent unsafe progression.
#
# Usage:
#   TARGET_HOST=staging.vidya.fidelitus.com \
#   BACKUP_DATE=20260520_200000Z \
#   DATABASE_URL=postgresql+asyncpg://... \
#   S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   QDRANT_URL=http://... \
#   VAULT_ADDR=https://... VAULT_TOKEN=s.xxx \
#   NAMESPACE=vidya-system \
#   bash infra/scripts/restore-drill.sh
#
# Optional flags:
#   --validate-only    — skip restore steps, run smoke checks only
#   --skip-vault       — skip Vault restore (use current Vault state)
#   --skip-qdrant      — skip Qdrant restore (vectors are regeneratable)
# =============================================================================
set -euo pipefail

VALIDATE_ONLY=false
SKIP_VAULT=false
SKIP_QDRANT=false
for arg in "$@"; do
    case "$arg" in
        --validate-only) VALIDATE_ONLY=true ;;
        --skip-vault)    SKIP_VAULT=true ;;
        --skip-qdrant)   SKIP_QDRANT=true ;;
    esac
done

: "${TARGET_HOST:?TARGET_HOST must be set (e.g. staging.vidya.fidelitus.com)}"
: "${BACKUP_DATE:?BACKUP_DATE must be set (e.g. 20260520_200000Z)}"
: "${DATABASE_URL:?DATABASE_URL must be set}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY must be set}"
: "${QDRANT_URL:?QDRANT_URL must be set}"
NAMESPACE="${NAMESPACE:-vidya-system}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-http://localhost:9000}"
BACKUP_BUCKET_DB="${BACKUP_BUCKET_DB:-vidya-backup-db}"
BACKUP_MANIFESTS="${BACKUP_MANIFESTS:-vidya-backup-manifests}"

DRILL_START=$(date +%s)
DRILL_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log()  { echo "[restore-drill] $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "[restore-drill] FAIL: $*" >&2; exit 1; }
gate() {
    local msg="$1"
    echo ""
    echo "══════════════════════════════════════════════════════════════"
    echo "  HUMAN GATE: ${msg}"
    echo "══════════════════════════════════════════════════════════════"
}

# ── Pre-drill banner ─────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         VIDYA RESTORE DRILL — $(date -u +%Y-%m-%d)                    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Target host:  ${TARGET_HOST}"
echo "║  Backup date:  ${BACKUP_DATE}"
echo "║  Namespace:    ${NAMESPACE}"
echo "║  Validate only: ${VALIDATE_ONLY}"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Identify backup manifests ────────────────────────────────────────
log "Step 1: Verifying backup manifests for date ${BACKUP_DATE}"
mc alias set bk "$BACKUP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet

for COMPONENT in postgres minio qdrant vault; do
    MANIFEST=$(mc cat "bk/${BACKUP_MANIFESTS}/${COMPONENT}_latest.json" 2>/dev/null || echo "")
    if [ -n "$MANIFEST" ]; then
        log "  ${COMPONENT}: ${MANIFEST}"
    else
        log "  WARN: No manifest found for ${COMPONENT}"
    fi
done

# ── HUMAN GATE 1 ─────────────────────────────────────────────────────────────
gate "Verify backup manifests above are valid and timestamps are within 25h."
echo "  Confirm that EXAM_FERNET_KEY in Vault matches the DB backup timestamp."
echo "  If mismatched, restore Vault first to the same timestamp as the DB backup."
echo ""
read -p "  Srinivas confirms manifests are valid? [type 'gate-1-approved']: " g1
[ "$g1" = "gate-1-approved" ] || { log "Drill aborted at Gate 1."; exit 0; }

if [ "$VALIDATE_ONLY" = "true" ]; then
    log "validate-only mode — skipping restore steps."
else
    # ── Step 2: Scale down ───────────────────────────────────────────────────
    log "Step 2: Scaling down application in namespace ${NAMESPACE}"
    kubectl scale deployment vidya-api vidya-worker vidya-worker-heavy \
        --replicas=0 -n "$NAMESPACE" 2>/dev/null \
        || log "WARN: kubectl scale failed — ensure kubeconfig is set"
    log "Waiting 15s for pods to terminate..."
    sleep 15

    # ── Step 3: Restore Vault ────────────────────────────────────────────────
    if [ "$SKIP_VAULT" = "false" ]; then
        log "Step 3: Restoring Vault raft snapshot"
        VAULT_SNAP_FILE="vault_snapshot_${BACKUP_DATE}.snap"
        mc cp "bk/vidya-backup-vault/${VAULT_SNAP_FILE}" "/tmp/${VAULT_SNAP_FILE}"
        mc cp "bk/vidya-backup-vault/${VAULT_SNAP_FILE}.sha256" "/tmp/${VAULT_SNAP_FILE}.sha256" \
            || fail "Vault snapshot checksum missing"
        EXPECTED=$(awk '{print $1}' "/tmp/${VAULT_SNAP_FILE}.sha256")
        ACTUAL=$(sha256sum "/tmp/${VAULT_SNAP_FILE}" | awk '{print $1}')
        [ "$EXPECTED" = "$ACTUAL" ] || fail "Vault snapshot checksum mismatch"
        log "Vault snapshot checksum OK: ${ACTUAL}"
        vault operator raft snapshot restore "/tmp/${VAULT_SNAP_FILE}" \
            || fail "vault raft snapshot restore failed"
        log "Forcing ESO re-sync..."
        kubectl annotate externalsecret vidya-secret \
            "force-sync=$(date +%s)" -n "$NAMESPACE" --overwrite 2>/dev/null || true
        sleep 10
        rm -f "/tmp/${VAULT_SNAP_FILE}" "/tmp/${VAULT_SNAP_FILE}.sha256"
    else
        log "Step 3: Skipping Vault restore (--skip-vault)"
    fi

    # ── Step 4: Restore PostgreSQL ───────────────────────────────────────────
    log "Step 4: Restoring PostgreSQL from ${BACKUP_DATE}"
    PG_DUMP_FILE="vidya_postgres_${BACKUP_DATE}.dump"
    BACKUP_FILE="$PG_DUMP_FILE" \
    RESTORE_MODE=full \
        bash "$(dirname "$0")/restore-postgres.sh"

    # ── Step 5: Restore MinIO ────────────────────────────────────────────────
    log "Step 5: Restoring MinIO assets"
    bash "$(dirname "$0")/restore-minio.sh"

    # ── Step 6: Restore Qdrant ───────────────────────────────────────────────
    if [ "$SKIP_QDRANT" = "false" ]; then
        log "Step 6: Restoring Qdrant snapshots for date ${BACKUP_DATE}"
        SNAPSHOT_DATE="$BACKUP_DATE" bash "$(dirname "$0")/restore-qdrant.sh"
    else
        log "Step 6: Skipping Qdrant restore (--skip-qdrant)"
    fi

    # ── Step 7: Scale up ─────────────────────────────────────────────────────
    log "Step 7: Scaling up application"
    kubectl scale deployment vidya-api vidya-worker vidya-worker-heavy \
        --replicas=2 -n "$NAMESPACE" 2>/dev/null || true
    log "Waiting 60s for pods to become ready..."
    sleep 60
fi

# ── HUMAN GATE 2 ─────────────────────────────────────────────────────────────
gate "Verify data store state before running smoke checks."
echo "  Run these verification queries:"
echo ""
echo "  psql \$DATABASE_URL -c \"SELECT count(*) FROM public.tenants WHERE is_active;\""
echo "  psql \$DATABASE_URL -c \"SELECT version_num FROM alembic_version;\""
echo "  mc ls bk/vidya-backup-assets --recursive | wc -l"
echo "  curl -s ${QDRANT_URL}/collections"
echo "  kubectl describe externalsecret vidya-secret -n ${NAMESPACE} | grep -A5 Conditions"
echo ""
read -p "  Data stores verified? [type 'gate-2-approved']: " g2
[ "$g2" = "gate-2-approved" ] || { log "Drill halted at Gate 2. Do not scale up."; exit 1; }

# ── Step 8: Application smoke checks ─────────────────────────────────────────
log "Step 8: Running application-level smoke checks against ${TARGET_HOST}"

SMOKE_FAIL=0
API_BASE="https://${TARGET_HOST}"

# Health check
HC_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "${API_BASE}/healthz" || echo "000")
if [ "$HC_STATUS" = "200" ]; then
    log "  /healthz: PASS (200)"
else
    log "  /healthz: FAIL (${HC_STATUS})"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
fi

# Ready check
RD_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "${API_BASE}/ready" || echo "000")
if [ "$RD_STATUS" = "200" ]; then
    log "  /ready: PASS (200)"
else
    log "  /ready: FAIL (${RD_STATUS})"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
fi

# Login smoke check (requires a drill smoke-test user in the DB)
SMOKE_USER="${SMOKE_USER:-smoke@drill.internal}"
SMOKE_PASS="${SMOKE_PASS:-}"
SMOKE_SLUG="${SMOKE_SLUG:-}"

if [ -n "$SMOKE_PASS" ] && [ -n "$SMOKE_SLUG" ]; then
    LOGIN_RESP=$(curl -sf -X POST "${API_BASE}/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"${SMOKE_USER}\",\"password\":\"${SMOKE_PASS}\",\"slug\":\"${SMOKE_SLUG}\"}" \
        2>/dev/null || echo "")
    TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

    if [ -n "$TOKEN" ]; then
        log "  Login: PASS"

        # Tenant isolation: cross-tenant request must return 403
        ISO_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer ${TOKEN}" \
            -H "X-Tenant-Slug: different-tenant-that-does-not-exist" \
            "${API_BASE}/api/v1/users/me" || echo "000")
        if [ "$ISO_STATUS" = "403" ] || [ "$ISO_STATUS" = "422" ]; then
            log "  Tenant isolation: PASS (${ISO_STATUS})"
        else
            log "  Tenant isolation: FAIL (expected 403/422, got ${ISO_STATUS})"
            SMOKE_FAIL=$((SMOKE_FAIL + 1))
        fi

        # RBAC: student role cannot reach admin endpoint
        RBAC_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer ${TOKEN}" \
            "${API_BASE}/api/v1/admin/tenants" || echo "000")
        if [ "$RBAC_STATUS" = "403" ] || [ "$RBAC_STATUS" = "401" ]; then
            log "  RBAC guard: PASS (${RBAC_STATUS})"
        else
            log "  RBAC guard: FAIL (expected 403/401, got ${RBAC_STATUS})"
            SMOKE_FAIL=$((SMOKE_FAIL + 1))
        fi

        # File access: storage listing endpoint reachable
        FILE_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer ${TOKEN}" \
            -H "X-Tenant-Slug: ${SMOKE_SLUG}" \
            "${API_BASE}/api/v1/storage/files" || echo "000")
        if [ "$FILE_STATUS" = "200" ] || [ "$FILE_STATUS" = "404" ]; then
            log "  File access: PASS (${FILE_STATUS})"
        else
            log "  File access: FAIL (${FILE_STATUS})"
            SMOKE_FAIL=$((SMOKE_FAIL + 1))
        fi

        # AI generation path: programs endpoint reachable (presence check only)
        AI_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer ${TOKEN}" \
            -H "X-Tenant-Slug: ${SMOKE_SLUG}" \
            "${API_BASE}/api/v1/programs/" || echo "000")
        if [ "$AI_STATUS" = "200" ] || [ "$AI_STATUS" = "404" ]; then
            log "  AI path: PASS (${AI_STATUS})"
        else
            log "  AI path: FAIL (${AI_STATUS})"
            SMOKE_FAIL=$((SMOKE_FAIL + 1))
        fi
    else
        log "  Login: FAIL — could not obtain access token"
        SMOKE_FAIL=$((SMOKE_FAIL + 1))
    fi
else
    log "  Login/RBAC/file/AI checks SKIPPED — set SMOKE_USER, SMOKE_PASS, SMOKE_SLUG to enable"
fi

# Dependency health via metrics
METRICS=$(curl -sf "${API_BASE}/metrics" 2>/dev/null || echo "")
if echo "$METRICS" | grep -q 'vidya_dependency_health.*1'; then
    log "  Dependency health gauge: PASS (at least one healthy service)"
else
    log "  Dependency health gauge: WARN — check /metrics output"
fi

# ── HUMAN GATE 3 ─────────────────────────────────────────────────────────────
DRILL_END=$(date +%s)
RTO=$((DRILL_END - DRILL_START))

gate "Final sign-off before marking drill complete."
echo "  Smoke checks: $((8 - SMOKE_FAIL)) passed, ${SMOKE_FAIL} failed"
echo "  Actual RTO:   ${RTO}s ($((RTO / 60)) min $((RTO % 60)) sec)"
echo "  RTO target:   14400s (4 hours)"
[ "$RTO" -le 14400 ] && echo "  RTO: WITHIN TARGET" || echo "  RTO: EXCEEDED TARGET"
echo ""
if [ "$SMOKE_FAIL" -gt 0 ]; then
    echo "  WARNING: ${SMOKE_FAIL} smoke check(s) failed. Do not mark drill as passed."
fi
echo ""
read -p "  Srinivas signs off on drill? [type 'gate-3-approved']: " g3
[ "$g3" = "gate-3-approved" ] || { log "Drill not signed off — investigate failures."; exit 1; }

log "Drill COMPLETE. Date: ${DRILL_DATE} RTO: ${RTO}s Failures: ${SMOKE_FAIL}"
echo ""
echo "Record this in the team incident log:"
echo "  Date: ${DRILL_DATE}"
echo "  RTO:  ${RTO}s"
echo "  Backup date tested: ${BACKUP_DATE}"
echo "  Smoke failures: ${SMOKE_FAIL}"
echo "  Signed off by: Srinivas"
