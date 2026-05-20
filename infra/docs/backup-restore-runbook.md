# Backup and Restore Runbook — Vidya

Owner: Srinivas / Fidelitus Corp  
Applies to: staging and prod environments  
Dev path: ephemeral — no backup required  
Last updated: 2026-05-20

---

## 1. Overview

### RTO / RPO Targets

| Component | RPO | RTO | Owner |
|---|---|---|---|
| PostgreSQL (managed, prod) | 1 hour (PITR) | 2 hours | Cloud provider + ops |
| PostgreSQL (self-hosted) | 24 hours (daily dump) | 3 hours | Ops |
| MinIO (object storage) | 24 hours (daily mirror) | 1 hour | Ops |
| Qdrant (vector DB) | 24 hours (daily snapshot) | 30 min | Ops |
| Vault (secrets) | 24 hours (daily raft snapshot) | 1 hour | Ops |
| **System overall** | **1 hour** | **4 hours** | Srinivas |

### Redis — No Backup (by design)

Redis holds Celery task queues and KEDA queue depth counters only. No user data, no session state, no Celery results (outcomes land in PostgreSQL `audit_logs`). In-flight task loss during Redis failure is accepted. Managed Redis services offer PITR — do not enable it for queue workloads.

### Audit Log Invariant (non-negotiable)

`audit_logs` is an append-only table enforced by a database trigger. **Never partially restore `audit_logs`.** Only a full database restore (point-in-time or complete pg_dump) preserves audit integrity. Per-tenant partial restores explicitly exclude `audit_logs`.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│              Vidya Backup Architecture               │
├─────────────────────────────────────────────────────┤
│  Managed PostgreSQL ──PITR──► Cloud provider storage │
│  MinIO (app) ───daily─────► MinIO backup (separate) │
│  Qdrant ─────daily─────────► MinIO backup (separate) │
│  Vault ──────daily─────────► MinIO backup (separate) │
│                                                      │
│  CronJob schedule (UTC, staggered):                  │
│  20:00 — PostgreSQL backup / verification            │
│  20:30 — MinIO mirror                                │
│  21:00 — Qdrant snapshot                             │
│  21:30 — Vault raft snapshot                         │
└─────────────────────────────────────────────────────┘
```

### Manifest format (emitted by every backup job)

Every backup job writes a JSON manifest to `vidya-backup-manifests/`:

```json
{
  "component": "postgres",
  "timestamp": "2026-05-20T20:00:00Z",
  "duration_seconds": 42,
  "size_bytes": 123456789,
  "checksum_sha256": "abc123...",
  "backup_file": "vidya_postgres_20260520_200000Z.dump",
  "status": "success"
}
```

Fields: `component`, `timestamp`, `duration_seconds`, `size_bytes` (or `object_count` for MinIO), `checksum_sha256`, `backup_file`, `status` (`success` or `failure`), `error` (on failure only).

Two copies are written: `{component}_latest.json` (always overwritten) and `{component}_{timestamp}.json` (permanent record).

---

## 3. Component Backup Strategies

### 3.1 PostgreSQL

**Prod (managed — Cloud SQL / RDS / Azure DB):**

The managed service owns backup execution. Verify before production onboarding:

```bash
# Cloud SQL
gcloud sql instances describe vidya-prod --format='value(settings.backupConfiguration)'
# Expected: enabled: true, pointInTimeRecoveryEnabled: true, retentionDays >= 7

# RDS
aws rds describe-db-instances --db-instance-identifier vidya-prod \
  --query 'DBInstances[0].BackupRetentionPeriod'
# Expected: >= 7
```

The Kubernetes CronJob for managed PostgreSQL runs a verification-only job: it confirms DB connectivity, reads `alembic_version`, and emits a success manifest.

**Self-hosted (kind dev / selfhosted.yaml):**

```bash
# Manual backup (operator-triggered)
DATABASE_URL=postgresql+asyncpg://vidya:pass@localhost:5432/vidya \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
BACKUP_S3_ENDPOINT=http://localhost:9000 \
bash infra/scripts/backup-postgres.sh
```

**Schema enumeration note:** `pg_dump` with custom format includes all schemas matching the configured patterns. The `--no-acl --no-owner` flags ensure portability across environments.

**Retention:** 7 daily, 4 weekly, 3 monthly. Managed by MinIO ILM expiry on `vidya-backup-db`.

### 3.2 MinIO Object Storage

MinIO is self-hosted across all environments. The backup uses `mc mirror`:

```bash
# Manual backup
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
APP_S3_ENDPOINT=http://localhost:9000 \
APP_BUCKET=vidya-assets \
BACKUP_S3_ENDPOINT=http://backup-minio:9000 \
BACKUP_BUCKET=vidya-backup-assets \
bash infra/scripts/backup-minio.sh
```

`--overwrite` updates changed objects. Bucket versioning is enabled on `vidya-backup-assets` for point-in-time recovery of individual objects (see §5).

### 3.3 Qdrant Snapshots

Qdrant's `/qdrant/snapshots` directory is an `emptyDir` in the StatefulSet (by design — transient staging). The backup CronJob uses the Qdrant REST API to create and immediately download snapshots:

```
POST  /collections/{name}/snapshots   → create snapshot in emptyDir
GET   /collections/{name}/snapshots/{name} → stream binary to backup job
mc cp → upload to MinIO backup bucket
DELETE /collections/{name}/snapshots/{name} → free emptyDir space
```

```bash
# Manual backup
QDRANT_URL=http://localhost:6333 \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
BACKUP_S3_ENDPOINT=http://backup-minio:9000 \
bash infra/scripts/backup-qdrant.sh
```

**Degraded path:** If Qdrant snapshots are irrecoverably lost, re-run the embedding generation pipeline for all course collections. Qdrant vectors are derived from content stored in PostgreSQL — no irreplaceable data is lost.

### 3.4 Vault Raft Snapshots

Vault encrypts the snapshot with its own seal key before writing to disk. The snapshot is opaque binary.

```bash
# Manual backup
VAULT_ADDR=https://vault.example.com \
VAULT_TOKEN=s.xxxx \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
bash infra/scripts/backup-vault.sh
```

**CRITICAL:** Store Vault unseal keys and root token separately from the snapshot (e.g. in a hardware security module or password manager). A snapshot without the unseal key is unrestorable.

**Vault token permissions required:** `sys/storage/raft/snapshot` read permission.

---

## 4. Restore Procedures

### 4.1 PostgreSQL Restore

**Prerequisites:**
1. Scale the application to 0 replicas.
2. Restore Vault first (§4.4) to ensure EXAM_FERNET_KEY matches the DB backup timestamp.
3. Identify the backup file from the manifest.

**Full restore (managed PostgreSQL):**

Follow the cloud provider's console restore procedure to restore to the target point-in-time. After the managed restore completes, run:

```bash
# Verify alembic versions
psql $DATABASE_URL -c "SELECT version_num FROM alembic_version;"
# For each tenant schema:
psql $DATABASE_URL -c "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'tenant_%';" \
  | while read schema; do
    psql $DATABASE_URL -c "SELECT version_num FROM ${schema}.alembic_version;"
  done
```

**Full restore (self-hosted):**

```bash
BACKUP_FILE=vidya_postgres_20260520_200000Z.dump \
DATABASE_URL=postgresql+asyncpg://vidya:pass@localhost:5432/vidya \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
bash infra/scripts/restore-postgres.sh
```

The script verifies the SHA256 checksum before restoring.

**Per-tenant restore (partial, audit_logs excluded):**

```bash
BACKUP_FILE=vidya_postgres_20260520_200000Z.dump \
RESTORE_MODE=tenant \
TENANT_SLUG=acme \
DATABASE_URL=... \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
bash infra/scripts/restore-postgres.sh
```

The operator must confirm the `audit_logs` exclusion before the script proceeds.

### 4.2 MinIO Restore

```bash
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
APP_S3_ENDPOINT=http://localhost:9000 \
BACKUP_S3_ENDPOINT=http://backup-minio:9000 \
bash infra/scripts/restore-minio.sh
```

### 4.3 Qdrant Restore

```bash
SNAPSHOT_DATE=20260520_200000Z \
QDRANT_URL=http://localhost:6333 \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
BACKUP_S3_ENDPOINT=http://backup-minio:9000 \
bash infra/scripts/restore-qdrant.sh
```

The script verifies SHA256 checksums before uploading each snapshot to Qdrant.

### 4.4 Vault Restore

```bash
# 1. Download and verify snapshot
mc alias set bk http://backup-minio:9000 $S3_ACCESS_KEY $S3_SECRET_KEY
mc cp bk/vidya-backup-vault/vault_snapshot_20260520_213000Z.snap /tmp/
mc cp bk/vidya-backup-vault/vault_snapshot_20260520_213000Z.snap.sha256 /tmp/
sha256sum -c /tmp/vault_snapshot_20260520_213000Z.snap.sha256

# 2. Restore snapshot
vault operator raft snapshot restore /tmp/vault_snapshot_20260520_213000Z.snap

# 3. Force ESO re-sync
kubectl annotate externalsecret vidya-secret \
  force-sync=$(date +%s) -n vidya-system --overwrite

# 4. Verify sync
kubectl describe externalsecret vidya-secret -n vidya-system | grep -A5 Conditions
# Expected: Type=Ready, Status=True, Reason=SecretSynced
```

---

## 5. Encryption at Rest and WORM Storage

### 5.1 Backup Bucket Encryption (MinIO)

Enable server-side encryption on all backup buckets before the first backup. Run once per bucket:

```bash
# Enable SSE-S3 encryption (requires KMS configured in MinIO)
mc encrypt set sse-s3 bk/vidya-backup-db
mc encrypt set sse-s3 bk/vidya-backup-assets
mc encrypt set sse-s3 bk/vidya-backup-qdrant
mc encrypt set sse-s3 bk/vidya-backup-vault
mc encrypt set sse-s3 bk/vidya-backup-manifests

# Verify
mc encrypt info bk/vidya-backup-db
```

For cloud object stores: GCS encrypts by default (CMEK optional). S3 encrypts by default (SSE-S3 or SSE-KMS). Azure Blob encrypts by default with optional BYOK.

### 5.2 Managed Database Encryption

Cloud SQL, RDS, and Azure DB for PostgreSQL encrypt at rest by default. Verify before production:

```bash
# Cloud SQL
gcloud sql instances describe vidya-prod \
  --format='value(diskEncryptionConfiguration)'

# RDS
aws rds describe-db-instances --db-instance-identifier vidya-prod \
  --query 'DBInstances[0].StorageEncrypted'
# Expected: true
```

### 5.3 Vault Snapshot Encryption

Vault raft snapshots are encrypted by Vault before writing, using the configured seal key. No additional encryption is needed. Verify the seal is healthy:

```bash
vault status | grep Sealed
# Expected: Sealed  false
vault operator key-status
```

### 5.4 WORM / Immutable Storage (Production Recommendation)

For production backup buckets, enable object lock in Governance mode to prevent deletion or overwrite during the retention window. This protects against ransomware and accidental deletion.

**MinIO (self-hosted backup instance):**

```bash
# WORM must be enabled at bucket creation — cannot be added to existing buckets
mc mb --with-lock bk/vidya-backup-db
mc retention set --default governance 7d bk/vidya-backup-db

# Enable bucket versioning (required for object lock)
mc version enable bk/vidya-backup-db
```

**AWS S3:**
Enable S3 Object Lock on the bucket at creation. Select Governance mode with a 7-day retention period.

**GCS:**
Enable Retention Policy on the bucket with a 7-day minimum retention period.

**Azure Blob:**
Enable Immutable Blob Storage with a time-based retention policy of 7 days.

**Bucket versioning (all platforms):**

Bucket versioning is enabled by the backup scripts on first run (`mc version enable`). Versioning protects against accidental object deletion — deleted objects are soft-deleted and recoverable for the ILM expiry window.

---

## 6. Monthly Restore Drill

Run against staging environment. Never drill against production.

### 6.1 Prerequisites

- Staging cluster running and accessible via `kubectl`
- Backup manifests readable (verify via `mc ls bk/vidya-backup-manifests/`)
- Vault accessible from the operator machine
- Smoke test user credentials available (`SMOKE_USER`, `SMOKE_PASS`, `SMOKE_SLUG`)

### 6.2 Drill Command

```bash
TARGET_HOST=staging.vidya.fidelitus.com \
BACKUP_DATE=20260520_200000Z \
DATABASE_URL=postgresql+asyncpg://... \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
QDRANT_URL=http://localhost:6333 \
VAULT_ADDR=https://vault.example.com \
VAULT_TOKEN=s.xxxx \
NAMESPACE=vidya-system \
SMOKE_USER=smoke@drill.internal \
SMOKE_PASS=SmokePass123! \
SMOKE_SLUG=smoke-tenant \
bash infra/scripts/restore-drill.sh
```

For validate-only (smoke checks without restore):

```bash
TARGET_HOST=staging.vidya.fidelitus.com BACKUP_DATE=... \
  bash infra/scripts/restore-drill.sh --validate-only
```

### 6.3 Human Gates

| Gate | Who approves | What is verified |
|---|---|---|
| Gate 1 | Srinivas | Manifests are valid; EXAM_FERNET_KEY matches backup timestamp |
| Gate 2 | Srinivas | Row counts, alembic_version, MinIO object count, Qdrant point counts |
| Gate 3 | Srinivas | All smoke checks pass; RTO within 4h target |

### 6.4 Post-Restore Validation Checklist

Run after every restore (drill or production incident):

```bash
# 1. Health probes
curl -f https://${TARGET_HOST}/healthz
curl -f https://${TARGET_HOST}/ready

# 2. PostgreSQL
psql $DATABASE_URL -c "SELECT count(*) FROM public.tenants WHERE is_active;"
psql $DATABASE_URL -c "SELECT version_num FROM alembic_version;"
# Audit log row count must not decrease from pre-restore count
psql $DATABASE_URL -c \
  "SELECT schemaname, count(*) FROM (
     SELECT schemaname FROM pg_stat_user_tables
     WHERE schemaname LIKE 'tenant_%' AND relname='audit_logs'
   ) t JOIN LATERAL (SELECT count(*) FROM pg_stat_user_tables ...) ..." \
  # Simplified: run per-tenant manually if automated count unavailable

# 3. MinIO
mc ls bk/vidya-assets --recursive | wc -l
mc stat bk/vidya-assets/<known-reference-file>

# 4. Qdrant
curl -s ${QDRANT_URL}/collections | python3 -m json.tool
# For each collection, verify point count matches pre-restore count

# 5. Vault / ESO
kubectl describe externalsecret vidya-secret -n vidya-system | grep -A5 Conditions
kubectl get secret vidya-secret -n vidya-system -o json | jq '.data | keys | length'
# Expected: >= 14 keys

# 6. Metrics
curl -s https://${TARGET_HOST}/metrics | grep vidya_dependency_health
# Expected: vidya_dependency_health{service="db"} 1
#           vidya_dependency_health{service="redis"} 1
#           vidya_dependency_health{service="s3"} 1

# 7. Application smoke (automated by restore-drill.sh)
#    Login → tenant isolation → RBAC → file access → AI path
```

---

## 7. Retention Policy Summary

| Component | Daily | Weekly | Monthly | Enforced by |
|---|---|---|---|---|
| PostgreSQL dump | 7 | 4 | 3 | MinIO ILM expiry on `vidya-backup-db` |
| MinIO assets | 7 daily mirrors | 4 weekly prefixes | — | MinIO ILM + versioning |
| Qdrant snapshots | 7 per collection | — | — | MinIO ILM expiry on `vidya-backup-qdrant` |
| Vault raft snapshot | 7 | 4 | — | MinIO ILM expiry on `vidya-backup-vault` |
| Backup manifests | 7 | — | — | MinIO ILM expiry on `vidya-backup-manifests` |

ILM rules are applied automatically by backup jobs on first run. To verify:

```bash
mc ilm ls bk/vidya-backup-db
mc ilm ls bk/vidya-backup-assets
mc ilm ls bk/vidya-backup-qdrant
mc ilm ls bk/vidya-backup-vault
```

---

## 8. Monitoring and Alerting

The `VidyaBackupStale` PrometheusRule alert fires when no backup CronJob has completed successfully within 25 hours. Requires `kube-state-metrics` (ships with `kube-prometheus-stack`).

Check backup status manually:

```bash
# Latest manifests
mc cat bk/vidya-backup-manifests/postgres_latest.json
mc cat bk/vidya-backup-manifests/minio_latest.json
mc cat bk/vidya-backup-manifests/qdrant_latest.json
mc cat bk/vidya-backup-manifests/vault_latest.json

# CronJob history
kubectl get jobs -n vidya-system -l app.kubernetes.io/component=backup
kubectl logs job/vidya-backup-postgres-<hash> -n vidya-system
```

---

## 9. Disaster Recovery Scenarios

| Scenario | Recovery path | Estimated time |
|---|---|---|
| PostgreSQL data corruption (managed) | Cloud console PITR restore → alembic verify → app restart | 2h |
| PostgreSQL total loss (self-hosted) | `restore-postgres.sh` from latest dump | 3h |
| MinIO data loss | `restore-minio.sh` from backup mirror | 1h |
| Qdrant collection corruption | `restore-qdrant.sh` OR re-run embedding pipeline | 30m / 2h |
| Vault total loss | `vault raft snapshot restore` → ESO re-sync → app restart | 1h |
| EXAM_FERNET_KEY + DB mismatch | Restore Vault snapshot from same timestamp as DB backup | +30m |
| All data loss (full disaster) | Sequential: Vault → DB → MinIO → Qdrant → smoke | 4h |

**EXAM_FERNET_KEY mismatch handling:**  
If Vault and DB are from different timestamps, sealed exam papers will fail to decrypt after restore. Mitigation: always restore Vault and DB from the same backup window. If a mismatch occurs, the `ExamPaper` records remain in the database unmodified — decrypt with the old key by temporarily restoring an older Vault snapshot.
