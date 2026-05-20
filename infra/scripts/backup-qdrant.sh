#!/usr/bin/env bash
# =============================================================================
# infra/scripts/backup-qdrant.sh  —  Qdrant collection snapshot backup
# =============================================================================
# For each Qdrant collection:
#   1. POST /collections/{name}/snapshots  — create snapshot in /qdrant/snapshots/
#   2. GET  /collections/{name}/snapshots/{name}  — stream binary to local file
#   3. SHA256 checksum the downloaded file
#   4. Upload snapshot + checksum to MinIO backup bucket
#   5. DELETE /collections/{name}/snapshots/{name}  — free transient space
# Emits a JSON manifest per run.
#
# Note: /qdrant/snapshots in the StatefulSet is emptyDir (transient). Snapshots
# are streamed out immediately — the pod restart window is irrelevant.
#
# Usage:
#   QDRANT_URL=http://localhost:6333 \
#   S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   bash infra/scripts/backup-qdrant.sh
#
# Required env vars:
#   S3_ACCESS_KEY
#   S3_SECRET_KEY
# Optional env vars:
#   QDRANT_URL         — default: http://localhost:6333
#   BACKUP_S3_ENDPOINT — default: http://localhost:9000
#   BACKUP_BUCKET      — default: vidya-backup-qdrant
#   BACKUP_MANIFESTS   — default: vidya-backup-manifests
#   RETENTION_DAYS     — ILM expiry; default: 7
# =============================================================================
set -euo pipefail

: "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY must be set}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-http://localhost:9000}"
BACKUP_BUCKET="${BACKUP_BUCKET:-vidya-backup-qdrant}"
BACKUP_MANIFESTS="${BACKUP_MANIFESTS:-vidya-backup-manifests}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

log()  { echo "[backup-qdrant] $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "[backup-qdrant] FAIL: $*" >&2
         MANIFEST="{\"component\":\"qdrant\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"status\":\"failure\",\"error\":\"$*\"}"
         printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/qdrant_latest.json" 2>/dev/null || true
         exit 1; }

TIMESTAMP=$(date -u +%Y%m%d_%H%M%SZ)
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

START_TS=$(date +%s)

mc alias set bk "$BACKUP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet
mc mb --ignore-existing "bk/${BACKUP_BUCKET}"   || true
mc mb --ignore-existing "bk/${BACKUP_MANIFESTS}" || true
mc version enable "bk/${BACKUP_BUCKET}" 2>/dev/null || true
mc ilm add --expiry-days "$RETENTION_DAYS" "bk/${BACKUP_BUCKET}" 2>/dev/null || true

# Enumerate collections
COLLECTIONS_JSON=$(curl -sf "${QDRANT_URL}/collections") \
    || fail "Cannot reach Qdrant at ${QDRANT_URL}"
COLLECTIONS=$(echo "$COLLECTIONS_JSON" | python3 -c \
    "import json,sys; [print(c['name']) for c in json.load(sys.stdin)['result']['collections']]" 2>/dev/null \
    || echo "")

if [ -z "$COLLECTIONS" ]; then
    log "No collections found — emitting empty manifest"
    MANIFEST="{\"component\":\"qdrant\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"duration_seconds\":0,\"total_size_bytes\":0,\"collections\":\"\",\"status\":\"success\",\"note\":\"no collections\"}"
    printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/qdrant_latest.json"
    printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/qdrant_${TIMESTAMP}.json"
    log "Done (no collections)."
    exit 0
fi

TOTAL_SIZE=0
COLL_NAMES=""

for COLL in $COLLECTIONS; do
    log "Creating snapshot for collection: ${COLL}"

    # Create snapshot
    SNAP_RESP=$(curl -sf -X POST "${QDRANT_URL}/collections/${COLL}/snapshots") \
        || fail "POST /collections/${COLL}/snapshots failed"
    SNAP_NAME=$(echo "$SNAP_RESP" | python3 -c \
        "import json,sys; print(json.load(sys.stdin)['result']['name'])")
    log "Snapshot created: ${SNAP_NAME}"

    # Download snapshot binary
    SNAP_FILE="${TMP_DIR}/${COLL}.snapshot"
    curl -sf -o "$SNAP_FILE" "${QDRANT_URL}/collections/${COLL}/snapshots/${SNAP_NAME}" \
        || fail "GET snapshot download failed for ${COLL}"

    # Verify download succeeded (non-empty file)
    SIZE=$(stat -c %s "$SNAP_FILE")
    [ "$SIZE" -gt 0 ] || fail "Downloaded snapshot for ${COLL} is empty"

    # SHA256 checksum
    CHECKSUM=$(sha256sum "$SNAP_FILE" | awk '{print $1}')
    echo "$CHECKSUM  ${COLL}.snapshot" > "${SNAP_FILE}.sha256"
    log "${COLL}: ${SIZE}B sha256=${CHECKSUM}"

    # Upload to MinIO
    mc cp "$SNAP_FILE"         "bk/${BACKUP_BUCKET}/${TIMESTAMP}/${COLL}.snapshot"
    mc cp "${SNAP_FILE}.sha256" "bk/${BACKUP_BUCKET}/${TIMESTAMP}/${COLL}.snapshot.sha256"

    # Delete transient snapshot from Qdrant
    curl -sf -X DELETE "${QDRANT_URL}/collections/${COLL}/snapshots/${SNAP_NAME}" >/dev/null \
        || log "WARN: DELETE snapshot failed for ${COLL} — will be cleaned up on pod restart"

    TOTAL_SIZE=$((TOTAL_SIZE + SIZE))
    COLL_NAMES="${COLL_NAMES}${COLL} "
done

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))
COLL_NAMES=$(echo "$COLL_NAMES" | xargs)  # trim whitespace

MANIFEST="{\"component\":\"qdrant\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"duration_seconds\":${DURATION},\"total_size_bytes\":${TOTAL_SIZE},\"collections\":\"${COLL_NAMES}\",\"status\":\"success\"}"
printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/qdrant_latest.json"
printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/qdrant_${TIMESTAMP}.json"

log "Done. duration=${DURATION}s total_size=${TOTAL_SIZE}B collections=${COLL_NAMES}"
