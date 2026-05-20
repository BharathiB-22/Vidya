#!/usr/bin/env bash
# =============================================================================
# infra/scripts/migration-check.sh  —  Migration safety gate
# =============================================================================
# Runs four checks before any automated deploy:
#
#   1. Destructive DDL scan — fails hard if drop_table or drop_column appears
#      in any migration file (upgrade or downgrade), requiring DBA sign-off.
#
#   2. Public schema apply — alembic upgrade head on the public track.
#
#   3. Tenant schema apply + rollback + re-upgrade — verifies downgrade() is
#      implemented and migrations are idempotent.
#
#   4. Public schema rollback + re-upgrade — same verification for public track.
#
# Usage:
#   DATABASE_URL=postgresql+asyncpg://... bash infra/scripts/migration-check.sh
#
# Requirements:
#   - Python 3.12 with vidya-backend installed (pip install .)
#   - DATABASE_URL env var pointing to a writable PostgreSQL instance
#   - Run from repo root
# =============================================================================
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set (postgresql+asyncpg://user:pass@host:port/db)}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

log()  { echo "[migration-check] $*"; }
fail() { echo "[migration-check] FAIL: $*" >&2; exit 1; }

cd "$BACKEND_DIR"

# ── 1. Destructive DDL scan ──────────────────────────────────────────────────
# Flags any migration file containing op.drop_table or op.drop_column.
# These operations destroy data and require manual DBA review before deploy.
# False positives (downgrade sections) are intentional — a DBA must confirm.
log "Scanning migration files for destructive DDL patterns..."

DESTRUCTIVE=$(grep -rEl "(op\.drop_table|op\.drop_column)" \
    --include="*.py" \
    alembic/public_versions/ \
    alembic/tenant_versions/ 2>/dev/null || true)

if [ -n "$DESTRUCTIVE" ]; then
    echo ""
    echo "Files containing destructive DDL:"
    echo "$DESTRUCTIVE"
    echo ""
    fail "Destructive DDL (op.drop_table / op.drop_column) detected."$'\n'"  Manual DBA review and sign-off required before automated deploy."$'\n'"  If these are in downgrade() only, add a DBA-reviewed comment and update this check."
fi
log "Destructive DDL scan: PASS"

# ── 2. Apply public schema migrations ───────────────────────────────────────
log "Applying public schema migrations to head..."
ALEMBIC_TARGET=public alembic upgrade head \
    || fail "Public schema 'alembic upgrade head' failed — check migration SQL and DB connection"
log "Public upgrade: PASS"

# ── 3. Apply tenant schema migrations ───────────────────────────────────────
# Schema name must match ^tenant_[a-z0-9_]+$ per alembic/env.py validation.
TENANT_TEST_SCHEMA="tenant_ci_check"
log "Applying tenant schema migrations to $TENANT_TEST_SCHEMA..."
ALEMBIC_TARGET=tenant TENANT_SCHEMA="$TENANT_TEST_SCHEMA" alembic upgrade head \
    || fail "Tenant schema 'alembic upgrade head' failed"
log "Tenant upgrade: PASS"

# ── 4. Tenant rollback one step ──────────────────────────────────────────────
log "Rolling back tenant schema one step (downgrade -1)..."
ALEMBIC_TARGET=tenant TENANT_SCHEMA="$TENANT_TEST_SCHEMA" alembic downgrade -1 \
    || fail "Tenant 'alembic downgrade -1' failed — all downgrade() functions must be implemented"
log "Tenant rollback: PASS"

# ── 5. Re-upgrade tenant (idempotency) ───────────────────────────────────────
log "Re-upgrading tenant schema to head (idempotency check)..."
ALEMBIC_TARGET=tenant TENANT_SCHEMA="$TENANT_TEST_SCHEMA" alembic upgrade head \
    || fail "Tenant re-upgrade to head failed — migration is not idempotent"
log "Tenant idempotency: PASS"

# ── 6. Public rollback one step ──────────────────────────────────────────────
log "Rolling back public schema one step (downgrade -1)..."
ALEMBIC_TARGET=public alembic downgrade -1 \
    || fail "Public 'alembic downgrade -1' failed — all downgrade() functions must be implemented"
log "Public rollback: PASS"

# ── 7. Re-upgrade public (idempotency) ───────────────────────────────────────
log "Re-upgrading public schema to head (idempotency check)..."
ALEMBIC_TARGET=public alembic upgrade head \
    || fail "Public re-upgrade to head failed — migration is not idempotent"
log "Public idempotency: PASS"

log ""
log "============================================================"
log "All migration checks passed"
log "============================================================"
