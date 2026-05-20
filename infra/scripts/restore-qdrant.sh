#!/usr/bin/env bash
# =============================================================================
# infra/scripts/restore-qdrant.sh  —  Qdrant collection restore from snapshot
# =============================================================================
# Downloads a Qdrant snapshot from MinIO, verifies checksum, uploads to Qdrant
# via the REST API, and triggers collection recovery.
#
# Qdrant vectors are derived data (embeddings of course material text stored in
# PostgreSQL). If snapshots are irrecoverably lost, re-run the embedding
# generation pipeline for all affected collections — no data loss occurs.
#
# Usage:
#   SNAPSHOT_DATE=20260520_200000Z \
#   QDRANT_URL=http://localhost:6333 \
#   S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   bash infra/scripts/restore-qdrant.sh
#
# Required env vars:
#   SNAPSHOT_DATE      — timestamp prefix in backup bucket (e.g. 20260520_200000Z)
#   S3_ACCESS_KEY / S3_SECRET_KEY
# Optional env vars:
#   QDRANT_URL         — default: http://localhost:6333
#   BACKUP_S3_ENDPOINT — default: http://localhost:9000
#   BACKUP_BUCKET      — default: vidya-backup-qdrant
# =============================================================================
set -euo pipefail

: "${SNAPSHOT_DATE:?SNAPSHOT_DATE must be set (e.g. 20260520_200000Z)}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY must be set}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-http://localhost:9000}"
BACKUP_BUCKET="${BACKUP_BUCKET:-vidya-backup-qdrant}"

log()  { echo "[restore-qdrant] $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "[restore-qdrant] FAIL: $*" >&2; exit 1; }

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

mc alias set bk "$BACKUP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet

# List collections in the snapshot date prefix
log "Listing snapshots for date: ${SNAPSHOT_DATE}"
SNAPSHOTS=$(mc ls "bk/${BACKUP_BUCKET}/${SNAPSHOT_DATE}/" 2>/dev/null \
    | awk '{print $NF}' | grep '\.snapshot$' | sed 's/\.snapshot$//' || true)

[ -n "$SNAPSHOTS" ] || fail "No snapshots found at bk/${BACKUP_BUCKET}/${SNAPSHOT_DATE}/"

echo ""
echo "Collections to restore: $(echo "$SNAPSHOTS" | tr '\n' ' ')"
echo "Qdrant endpoint: ${QDRANT_URL}"
echo ""
read -p "Type 'confirm-qdrant-restore' to proceed: " confirm
[ "$confirm" = "confirm-qdrant-restore" ] || { log "Aborted."; exit 0; }

for COLL in $SNAPSHOTS; do
    SNAP_FILE="${COLL}.snapshot"
    log "Restoring collection: ${COLL}"

    # Download snapshot + checksum
    mc cp "bk/${BACKUP_BUCKET}/${SNAPSHOT_DATE}/${SNAP_FILE}"       "${TMP_DIR}/${SNAP_FILE}"
    mc cp "bk/${BACKUP_BUCKET}/${SNAPSHOT_DATE}/${SNAP_FILE}.sha256" "${TMP_DIR}/${SNAP_FILE}.sha256" \
        || fail "Checksum file missing for ${COLL} — backup may be incomplete"

    # Verify checksum
    EXPECTED=$(awk '{print $1}' "${TMP_DIR}/${SNAP_FILE}.sha256")
    ACTUAL=$(sha256sum "${TMP_DIR}/${SNAP_FILE}" | awk '{print $1}')
    [ "$EXPECTED" = "$ACTUAL" ] \
        || fail "Checksum mismatch for ${COLL}: expected=${EXPECTED} actual=${ACTUAL}"
    log "${COLL}: checksum OK (${ACTUAL})"

    SIZE=$(stat -c %s "${TMP_DIR}/${SNAP_FILE}")
    log "${COLL}: ${SIZE} bytes"

    # Upload snapshot to Qdrant (multipart form upload)
    UPLOAD_RESP=$(curl -sf -X POST \
        -F "snapshot=@${TMP_DIR}/${SNAP_FILE}" \
        "${QDRANT_URL}/collections/${COLL}/snapshots/upload") \
        || fail "Snapshot upload to Qdrant failed for ${COLL}"
    log "${COLL}: snapshot uploaded"

    # Trigger recovery from uploaded snapshot
    SNAP_NAME=$(echo "$UPLOAD_RESP" | python3 -c \
        "import json,sys; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null \
        || echo "${SNAP_FILE}")
    RECOVER_RESP=$(curl -sf -X PUT \
        -H "Content-Type: application/json" \
        -d "{\"location\":\"file:///qdrant/snapshots/${SNAP_NAME}\"}" \
        "${QDRANT_URL}/collections/${COLL}/snapshots/recover") \
        || fail "Snapshot recovery failed for ${COLL}"
    log "${COLL}: recovery triggered — ${RECOVER_RESP}"

    # Verify collection is accessible
    sleep 2
    POINT_COUNT=$(curl -sf "${QDRANT_URL}/collections/${COLL}" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['points_count'])" 2>/dev/null \
        || echo "unknown")
    log "${COLL}: restored with ${POINT_COUNT} points"
done

log "Qdrant restore complete for snapshot date: ${SNAPSHOT_DATE}"
