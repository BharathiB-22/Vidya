#!/usr/bin/env bash
# =============================================================================
# infra/scripts/backup-vault.sh  —  Vault raft snapshot backup
# =============================================================================
# Saves a Vault raft snapshot, generates SHA256 checksum, uploads to MinIO,
# and emits a JSON manifest.
#
# Vault encrypts the snapshot with its own seal key before writing to disk.
# The snapshot is opaque binary — decryptable only by a Vault instance with
# the matching seal key. Keep the unseal keys and root token separately from
# the snapshot itself (e.g. in a password manager or 1Password vault).
#
# Usage:
#   VAULT_ADDR=https://vault.example.com \
#   VAULT_TOKEN=s.xxxx \
#   S3_ACCESS_KEY=... S3_SECRET_KEY=... \
#   bash infra/scripts/backup-vault.sh
#
# Required env vars:
#   VAULT_ADDR         — Vault server URL
#   VAULT_TOKEN        — Vault token with sys/storage/raft/snapshot permissions
#   S3_ACCESS_KEY
#   S3_SECRET_KEY
# Optional env vars:
#   BACKUP_S3_ENDPOINT — default: http://localhost:9000
#   BACKUP_BUCKET      — default: vidya-backup-vault
#   BACKUP_MANIFESTS   — default: vidya-backup-manifests
#   RETENTION_DAYS     — ILM expiry; default: 7
# =============================================================================
set -euo pipefail

: "${VAULT_ADDR:?VAULT_ADDR must be set}"
: "${VAULT_TOKEN:?VAULT_TOKEN must be set}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY must be set}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-http://localhost:9000}"
BACKUP_BUCKET="${BACKUP_BUCKET:-vidya-backup-vault}"
BACKUP_MANIFESTS="${BACKUP_MANIFESTS:-vidya-backup-manifests}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

log()  { echo "[backup-vault] $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "[backup-vault] FAIL: $*" >&2
         MANIFEST="{\"component\":\"vault\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"status\":\"failure\",\"error\":\"$*\"}"
         printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/vault_latest.json" 2>/dev/null || true
         exit 1; }

TIMESTAMP=$(date -u +%Y%m%d_%H%M%SZ)
SNAP_FILE="vault_snapshot_${TIMESTAMP}.snap"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

START_TS=$(date +%s)

mc alias set bk "$BACKUP_S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" --quiet
mc mb --ignore-existing "bk/${BACKUP_BUCKET}"   || true
mc mb --ignore-existing "bk/${BACKUP_MANIFESTS}" || true
mc ilm add --expiry-days "$RETENTION_DAYS" "bk/${BACKUP_BUCKET}" 2>/dev/null || true

log "Saving Vault raft snapshot to ${TMP_DIR}/${SNAP_FILE}"
vault operator raft snapshot save "${TMP_DIR}/${SNAP_FILE}" \
    || fail "vault operator raft snapshot save failed"

SIZE=$(stat -c %s "${TMP_DIR}/${SNAP_FILE}")
[ "$SIZE" -gt 0 ] || fail "Vault snapshot file is empty — check Vault raft configuration"

CHECKSUM=$(sha256sum "${TMP_DIR}/${SNAP_FILE}" | awk '{print $1}')
echo "$CHECKSUM  ${SNAP_FILE}" > "${TMP_DIR}/${SNAP_FILE}.sha256"
log "Checksum: ${CHECKSUM}  Size: ${SIZE} bytes"

mc cp "${TMP_DIR}/${SNAP_FILE}"       "bk/${BACKUP_BUCKET}/${SNAP_FILE}"
mc cp "${TMP_DIR}/${SNAP_FILE}.sha256" "bk/${BACKUP_BUCKET}/${SNAP_FILE}.sha256"

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

MANIFEST="{\"component\":\"vault\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"duration_seconds\":${DURATION},\"size_bytes\":${SIZE},\"checksum_sha256\":\"${CHECKSUM}\",\"backup_file\":\"${SNAP_FILE}\",\"status\":\"success\"}"
printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/vault_latest.json"
printf '%s\n' "$MANIFEST" | mc pipe "bk/${BACKUP_MANIFESTS}/vault_${TIMESTAMP}.json"

log "Done. duration=${DURATION}s size=${SIZE}B sha256=${CHECKSUM}"
log "Snapshot: bk/${BACKUP_BUCKET}/${SNAP_FILE}"
log "REMINDER: Store Vault unseal keys and root token separately from this snapshot."
