# Backup & Restore Runbook — Vidya

**Owner:** Srinivas / Fidelitus Corp  
**Last updated:** 2026-05-21  
**Applies to:** Local docker-compose (Phase 0) + Production Kubernetes (Phase 1+)

---

## 1. RTO / RPO Targets

| Tier | Target | Notes |
|------|--------|-------|
| **RPO** (data loss tolerance) | 24 hours | Daily backup covers one business day |
| **RTO local** (restore time) | < 30 minutes | PostgreSQL only; Qdrant vectors are re-generable |
| **RTO production** | < 4 hours | Full stack including Vault, ESO re-sync, smoke test |
| **RTO Qdrant** | < 2 hours additional | Or skip and re-generate embeddings from PG source data |

**Audit log invariant (non-negotiable):** `audit_logs` is append-only. It must never be partially restored. Full restores preserve it; per-tenant restores exclude it by design (see `restore-postgres.sh` for the safety gate).

**Fernet key invariant:** Sealed exam papers in the DB are Fernet-encrypted. The Vault raft snapshot must match the same point-in-time as the DB backup. Always restore Vault first, verify ESO sync, then restore PostgreSQL.

---

## 2. What Is Backed Up

| Component | Local method | Production method | Storage |
|-----------|-------------|-------------------|---------|
| **PostgreSQL** | `docker exec pg_dump` → local `.dump` file | `backup-postgres.sh` (pg_dump → MinIO) | `infra/backups/` (local), `vidya-backup-db` MinIO bucket (prod) |
| **MinIO assets** | `docker run alpine tar` on `vidya_minio_data` volume | `backup-minio.sh` (`mc mirror`) | `infra/backups/` (local), `vidya-backup-assets` MinIO bucket (prod) |
| **Qdrant snapshots** | REST API → local `.snapshot` file | `backup-qdrant.sh` (REST → MinIO) | `infra/backups/` (local), `vidya-backup-qdrant` MinIO bucket (prod) |
| **Vault raft** | **Not in local compose — skip** | `backup-vault.sh` | `vidya-backup-vault` MinIO bucket (prod) |

---

## 3. Local Backup Procedure

### Prerequisites
- Docker Desktop running
- `docker compose up -d` stack healthy (`docker compose ps`)
- PowerShell 5.1 or later

### Run a backup
```powershell
# From repo root:
powershell -ExecutionPolicy Bypass -File infra\scripts\local-backup.ps1
```

**What it does:**
1. `docker exec vidya-postgres-1 pg_dump` → `infra/backups/vidya_postgres_<ts>.dump`
2. Generates SHA256 checksum file alongside each backup
3. `docker run alpine tar` on `vidya_minio_data` volume → `infra/backups/vidya_minio_<ts>.tar.gz`
4. REST API snapshot per Qdrant collection (skips gracefully if empty)
5. Writes `infra/backups/manifest_<ts>.json`
6. Prunes files older than 7 days

### Optional parameters
```powershell
# Custom backup dir and 14-day retention
powershell -ExecutionPolicy Bypass -File infra\scripts\local-backup.ps1 `
    -BackupDir D:\vidya-backups -RetentionDays 14
```

### Expected output on a clean stack
```
[local-backup] ... Backup directory: C:\vidya\infra\backups
[local-backup] ... Step 1: PostgreSQL dump
[local-backup] ... PostgreSQL: DONE  size=... bytes
[local-backup] ... Step 2: MinIO volume backup
[local-backup] ... MinIO: DONE  size=... bytes
[local-backup] ... Step 3: Qdrant snapshot backup — no collections (skip)
[local-backup] ... Step 4: Vault — skipped
[local-backup] ... Backup complete.
```

---

## 4. Local Restore Drill

Run monthly (or before any major change) to verify backups are usable.

### Mode 1 — Validate only (zero risk, run anytime)
```powershell
powershell -ExecutionPolicy Bypass -File infra\scripts\local-restore-drill.ps1
```
Checks: files exist, SHA256 matches, manifest is readable. No data touched.

### Mode 2 — PostgreSQL test restore
```powershell
powershell -ExecutionPolicy Bypass -File infra\scripts\local-restore-drill.ps1 -PostgresTestRestore
```

**What it does:**
1. Prompts for `confirm-test-restore` before proceeding
2. Starts `vidya-postgres-restore-test` container on port **5433** (never port 5432)
3. Copies and restores the latest dump into the test container
4. Verifies `alembic_version`, tenant schema count, core table presence
5. Stops and removes the test container
6. `vidya-postgres-1` is **never touched**

**Record drill results** in your team incident log:
```
Date: YYYY-MM-DD
Backup file tested: vidya_postgres_<ts>.dump
Backup age at test: N minutes
Checksum: PASS
pg_restore: PASS
alembic_version: <version>
Tenant schemas: N
Signed off by: Srinivas
```

---

## 5. Production Restore Procedures

> Production restores use the bash scripts in `infra/scripts/`. These require
> `mc`, `pg_dump`/`pg_restore`, `psql`, and optionally `vault` and `kubectl`
> on PATH. Run from a Linux/Mac jump host or from inside a container with these tools.

### 5.1 PostgreSQL full restore
```bash
BACKUP_FILE=vidya_postgres_20260520_200000Z.dump \
DATABASE_URL=postgresql+asyncpg://vidya:pass@host:5432/vidya \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
bash infra/scripts/restore-postgres.sh
```
Requires typing `confirm-full-restore` at the interactive gate.

### 5.2 PostgreSQL per-tenant restore (audit_logs preserved)
```bash
RESTORE_MODE=tenant TENANT_SLUG=acme \
BACKUP_FILE=vidya_postgres_20260520_200000Z.dump \
DATABASE_URL=... S3_ACCESS_KEY=... S3_SECRET_KEY=... \
bash infra/scripts/restore-postgres.sh
```
Requires typing `confirm-tenant-restore`.

### 5.3 MinIO asset restore
```bash
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
bash infra/scripts/restore-minio.sh
```
Requires typing `confirm-minio-restore`.

### 5.4 Qdrant snapshot restore
```bash
SNAPSHOT_DATE=20260520_200000Z \
QDRANT_URL=http://localhost:6333 \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
bash infra/scripts/restore-qdrant.sh
```
> **Note:** Qdrant vectors are derived data — regeneratable from source text in PostgreSQL.
> If a Qdrant restore is impractical, re-run the embedding generation pipeline instead.
> Data loss = performance impact (cold vector cache), not functional data loss.

### 5.5 Full production drill
```bash
TARGET_HOST=staging.vidya.fidelitus.com \
BACKUP_DATE=20260520_200000Z \
DATABASE_URL=... S3_ACCESS_KEY=... S3_SECRET_KEY=... QDRANT_URL=... \
VAULT_ADDR=... VAULT_TOKEN=... \
bash infra/scripts/restore-drill.sh
```
Three human gates: manifest verification, data store state, final sign-off.

---

## 6. Recovery Scenarios

### Scenario A: Database corrupted, no other data loss
1. Run `local-backup.ps1` on current state if any recent data is recoverable
2. Scale down API: `docker compose stop vidya-api vidya-worker vidya-worker-heavy`
3. Drop and recreate the `vidya` database inside `vidya-postgres-1`
4. Run `pg_restore` inside the container:
   ```powershell
   docker cp infra\backups\vidya_postgres_<ts>.dump vidya-postgres-1:/tmp/restore.dump
   docker exec vidya-postgres-1 pg_restore -U vidya -d vidya --no-acl --no-owner --clean --if-exists /tmp/restore.dump
   ```
5. Scale up: `docker compose start vidya-api vidya-worker vidya-worker-heavy`
6. Verify with `local-restore-drill.ps1 -ValidateOnly`

### Scenario B: Full local stack loss (laptop wipe)
1. Re-clone repo, restore `.env` from 1Password
2. `docker compose up -d`
3. Copy latest backup files to `infra/backups/`
4. Run scenario A steps for PostgreSQL
5. For MinIO: `docker run --rm -v vidya_minio_data:/data -v <backup_dir>:/backup alpine sh -c "tar xzf /backup/vidya_minio_<ts>.tar.gz -C /data"` (requires stopping MinIO first)
6. For Qdrant: no action needed if no collections existed; or re-generate embeddings

### Scenario C: Single tenant data issue
- Use `restore-postgres.sh` with `RESTORE_MODE=tenant TENANT_SLUG=<slug>`
- Audit log is preserved; only tenant schema tables (excluding audit_logs) are restored
- Requires Srinivas sign-off before execution

### Scenario D: Qdrant vectors lost
- No data loss — vectors are derived from course material text stored in PostgreSQL
- Re-run the embedding generation background task for affected courses
- ETA: depends on collection size and AI provider rate limits

---

## 7. Backup File Layout

```
infra/backups/                        ← gitignored
  manifest_20260521_163000Z.json      ← per-run manifest
  vidya_postgres_20260521_163000Z.dump
  vidya_postgres_20260521_163000Z.dump.sha256
  vidya_minio_20260521_163000Z.tar.gz
  vidya_minio_20260521_163000Z.tar.gz.sha256
  vidya_qdrant_<collection>_<ts>.snapshot     ← if collections exist
  vidya_qdrant_<collection>_<ts>.snapshot.sha256
```

Files older than 7 days are pruned automatically by `local-backup.ps1`.

---

## 8. Checklist for Monthly Drill

- [ ] Run `local-backup.ps1` and confirm zero errors in output
- [ ] Run `local-restore-drill.ps1` (validate-only) — all checksums pass
- [ ] Run `local-restore-drill.ps1 -PostgresTestRestore` — alembic_version present, core tables verified
- [ ] Record drill date, backup file tested, and outcome in team log
- [ ] Srinivas signs off
- [ ] If RTO exceeded 30 minutes: file incident and investigate
