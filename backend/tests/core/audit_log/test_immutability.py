"""H05-06: Database-level audit log immutability integration tests.

Verifies that the PostgreSQL triggers installed by migration 0005pub on
public.audit_logs enforce append-only semantics at the database layer,
independent of any application-layer guards.

Security note: PostgreSQL superusers can still disable or drop these
triggers directly (e.g. via ALTER TABLE ... DISABLE TRIGGER). This
protection guarantees append-only behavior against application-level
tampering and normal database user operations. It does not protect
against a malicious or compromised superuser. Vault access controls and
audit of DDL operations are the complementary controls for that threat.
"""
import uuid

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.audit_log.models import AuditEventType, AuditLog
from app.core.audit_log.service import AuditService
from app.database import AsyncSessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ── Internal helper ───────────────────────────────────────────────────────────

async def _committed_row() -> dict:
    """Insert one audit row via AuditService (commits in its own session).

    Returns id and original event_type for use in mutation tests. Uses a
    unique target_id as a correlation key so the row can be found reliably
    even across concurrent test runs.
    """
    marker = f"h05-immut-{uuid.uuid4().hex}"
    await AuditService.log(
        AuditEventType.AUTH_LOGIN_SUCCESS,
        target_id=marker,
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.target_id == marker).limit(1)
        )
        row = result.scalar_one_or_none()

    assert row is not None, (
        f"Setup failed: AuditService.log() did not persist row (marker={marker}). "
        "Check that the DB is reachable and the trigger does not block INSERT."
    )
    return {"id": row.id, "event_type": row.event_type}


# ── Trigger definition verification (QA: refinement #4) ──────────────────────

async def test_trigger_definitions_match_migration():
    """pg_get_triggerdef() must show correct timing and scope for all 3 triggers.

    Uses pg_trigger directly because information_schema.triggers does not
    expose TRUNCATE triggers — that omission is a known PostgreSQL behaviour,
    not a sign the trigger is missing.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT t.tgname, pg_get_triggerdef(t.oid)
                FROM pg_trigger t
                JOIN pg_class c ON t.tgrelid = c.oid
                WHERE c.relname = 'audit_logs'
                  AND NOT t.tgisinternal
                ORDER BY t.tgname
            """)
        )
        rows = result.fetchall()

    by_name = {r[0]: r[1].upper() for r in rows}

    assert set(by_name.keys()) == {
        "audit_logs_block_update",
        "audit_logs_block_delete",
        "audit_logs_block_truncate",
    }, f"Expected exactly 3 non-internal triggers, found: {list(by_name.keys())}"

    # UPDATE: BEFORE, FOR EACH ROW
    upd = by_name["audit_logs_block_update"]
    assert "BEFORE" in upd,      "UPDATE trigger must be BEFORE"
    assert "UPDATE" in upd,      "UPDATE trigger must fire on UPDATE"
    assert "FOR EACH ROW" in upd, "UPDATE trigger must be row-level"

    # DELETE: BEFORE, FOR EACH ROW
    dlt = by_name["audit_logs_block_delete"]
    assert "BEFORE" in dlt,      "DELETE trigger must be BEFORE"
    assert "DELETE" in dlt,      "DELETE trigger must fire on DELETE"
    assert "FOR EACH ROW" in dlt, "DELETE trigger must be row-level"

    # TRUNCATE: BEFORE, FOR EACH STATEMENT (statement-level — no OLD/NEW row)
    trunc = by_name["audit_logs_block_truncate"]
    assert "BEFORE" in trunc,         "TRUNCATE trigger must be BEFORE"
    assert "TRUNCATE" in trunc,        "TRUNCATE trigger must fire on TRUNCATE"
    assert "FOR EACH STATEMENT" in trunc, "TRUNCATE trigger must be statement-level"


# ── INSERT still works ────────────────────────────────────────────────────────

async def test_audit_service_insert_still_works():
    """AuditService.log() (INSERT path) must succeed with triggers active."""
    marker = f"h05-svc-insert-{uuid.uuid4().hex}"
    await AuditService.log(
        AuditEventType.AUTH_LOGOUT,
        target_id=marker,
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.target_id == marker)
        )
        row = result.scalar_one_or_none()

    assert row is not None, "AuditService.log() did not persist the row"
    assert row.event_type == AuditEventType.AUTH_LOGOUT.value


async def test_orm_direct_insert_still_works():
    """db.add(AuditLog(...)) + flush() (INSERT) must succeed with triggers active."""
    marker = f"h05-orm-insert-{uuid.uuid4().hex}"
    async with AsyncSessionLocal() as session:
        async with session.begin():
            entry = AuditLog(
                event_type=AuditEventType.AUTH_LOGOUT.value,
                target_id=marker,
            )
            session.add(entry)
            await session.flush()
            await session.refresh(entry)

    assert entry.id is not None
    assert entry.event_type == AuditEventType.AUTH_LOGOUT.value


# ── Raw SQL UPDATE blocked ────────────────────────────────────────────────────

async def test_raw_sql_update_raises():
    """Raw SQL UPDATE must be blocked by the BEFORE UPDATE trigger."""
    row = await _committed_row()

    exc_caught = None
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text(
                    "UPDATE public.audit_logs "
                    "SET event_type = 'TAMPERED' "
                    "WHERE id = :id"
                ),
                {"id": str(row["id"])},
            )
        except Exception as exc:
            exc_caught = exc
            await session.rollback()  # explicit rollback before any further use

    assert exc_caught is not None, "Expected trigger to raise on UPDATE but it succeeded"
    assert "append-only" in str(exc_caught).lower(), (
        f"Trigger fired but error message is unexpected: {exc_caught}"
    )


# ── Raw SQL DELETE blocked ────────────────────────────────────────────────────

async def test_raw_sql_delete_raises():
    """Raw SQL DELETE must be blocked by the BEFORE DELETE trigger."""
    row = await _committed_row()

    exc_caught = None
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text("DELETE FROM public.audit_logs WHERE id = :id"),
                {"id": str(row["id"])},
            )
        except Exception as exc:
            exc_caught = exc
            await session.rollback()  # explicit rollback before any further use

    assert exc_caught is not None, "Expected trigger to raise on DELETE but it succeeded"
    assert "append-only" in str(exc_caught).lower(), (
        f"Trigger fired but error message is unexpected: {exc_caught}"
    )


# ── Raw SQL TRUNCATE blocked ──────────────────────────────────────────────────

async def test_raw_sql_truncate_raises():
    """TRUNCATE must be blocked even on an empty-looking table.

    The BEFORE TRUNCATE FOR EACH STATEMENT trigger fires unconditionally —
    no matching rows are required. This is the easiest QA probe in production
    because it has zero data-loss risk and works regardless of row count.
    """
    exc_caught = None
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("TRUNCATE public.audit_logs"))
        except Exception as exc:
            exc_caught = exc
            await session.rollback()  # explicit rollback before any further use

    assert exc_caught is not None, "Expected trigger to raise on TRUNCATE but it succeeded"
    assert "append-only" in str(exc_caught).lower(), (
        f"Trigger fired but error message is unexpected: {exc_caught}"
    )


# ── SQLAlchemy ORM delete() blocked ───────────────────────────────────────────

async def test_orm_delete_statement_raises():
    """SQLAlchemy delete(AuditLog).where(...) must also be blocked by the trigger."""
    row = await _committed_row()

    exc_caught = None
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                delete(AuditLog).where(AuditLog.id == row["id"])
            )
        except Exception as exc:
            exc_caught = exc
            await session.rollback()  # explicit rollback before any further use

    assert exc_caught is not None, "Expected trigger to raise on ORM DELETE but it succeeded"
    assert "append-only" in str(exc_caught).lower(), (
        f"Trigger fired but error message is unexpected: {exc_caught}"
    )


# ── ORM dirty-object flush blocked (refinement #2) ───────────────────────────

async def test_orm_dirty_object_flush_raises():
    """Modifying a loaded AuditLog ORM object and calling flush() must be blocked.

    SQLAlchemy tracks the field mutation as "dirty" and translates flush()
    into UPDATE — the BEFORE UPDATE trigger then blocks it. This test confirms
    the trigger fires on the ORM code path, not only raw SQL.
    """
    row = await _committed_row()

    exc_caught = None
    async with AsyncSessionLocal() as session:
        # Load the row into SQLAlchemy's identity map
        result = await session.execute(
            select(AuditLog).where(AuditLog.id == row["id"])
        )
        entry = result.scalar_one()

        # Mutate the in-memory object — marks it "dirty" in SQLAlchemy
        entry.event_type = "MUTATED_VIA_ORM"

        try:
            # flush() translates the dirty object into UPDATE → trigger blocks it
            await session.flush()
        except Exception as exc:
            exc_caught = exc
            await session.rollback()  # explicit rollback before any further use

    assert exc_caught is not None, (
        "Expected trigger to raise on ORM dirty-object flush but it succeeded"
    )
    assert "append-only" in str(exc_caught).lower(), (
        f"Trigger fired but error message is unexpected: {exc_caught}"
    )


# ── Original row intact after failed UPDATE (refinement #3) ──────────────────

async def test_failed_update_leaves_row_unchanged():
    """After a blocked UPDATE, the row must retain its original field values.

    The trigger fires BEFORE the UPDATE takes effect, so the row is never
    mutated. The failed transaction is rolled back. This test reads the row
    in a fresh session to verify the committed state is unchanged.
    """
    row = await _committed_row()
    original_event_type = row["event_type"]

    # Attempt UPDATE — trigger must block it
    exc_caught = None
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text(
                    "UPDATE public.audit_logs "
                    "SET event_type = 'TAMPERED' "
                    "WHERE id = :id"
                ),
                {"id": str(row["id"])},
            )
        except Exception as exc:
            exc_caught = exc
            await session.rollback()  # explicit rollback (refinement #1)

    assert exc_caught is not None, "Expected trigger to raise on UPDATE but it succeeded"
    assert "append-only" in str(exc_caught).lower()

    # Fresh session — verify committed state is unchanged
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.id == row["id"])
        )
        row_after = result.scalar_one()

    assert row_after.event_type == original_event_type, (
        f"Row was mutated despite trigger: "
        f"expected {original_event_type!r}, got {row_after.event_type!r}"
    )
