"""
Unit tests for the compliance-safe permanent delete flow.

Key invariants:
- permanent delete sets status=PERMANENTLY_DELETED (no SQL DELETE)
- PERMANENTLY_DELETED tenants are excluded from list_tenants
- restore fails for PERMANENTLY_DELETED tenants
- TENANT_PERMANENTLY_DELETED audit event is written
- TENANT_RESTORED audit event is NOT written on permanent delete
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.core.audit_log.models import AuditEventType
from app.core.auth.models import TenantStatus
from app.core.tenants.service import TenantError, TenantService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant(
    status: TenantStatus = TenantStatus.DELETED,
    slug: str = "test-university",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Test University",
        slug=slug,
        schema_name="tenant_test_university",
        status=status,
        is_active=False,
        contact_email="admin@test.edu",
        deleted_at=datetime.now(timezone.utc) if status == TenantStatus.DELETED else None,
        deleted_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        logo_url=None,
        primary_color=None,
        secondary_color=None,
    )


def _purged_tenant(base: SimpleNamespace) -> SimpleNamespace:
    """Simulate the tenant row after permanently_delete_tenant sets status."""
    import copy
    t = copy.copy(base)
    t.status = TenantStatus.PERMANENTLY_DELETED
    t.is_active = False
    return t


def _make_db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# permanently_delete_tenant — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permanent_delete_sets_status_not_sql_delete():
    """permanently_delete_tenant must update status, never issue SQL DELETE."""
    tenant = _make_tenant(status=TenantStatus.DELETED)
    purged = _purged_tenant(tenant)
    db = _make_db()

    with (
        patch(
            "app.core.tenants.service.TenantRepository.get_tenant_by_id",
            new=AsyncMock(return_value=tenant),
        ),
        patch(
            "app.core.tenants.service.TenantRepository.permanently_delete_tenant",
            new=AsyncMock(return_value=purged),
        ) as mock_perm_del,
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()),
    ):
        result = await TenantService.permanently_delete_tenant(
            tenant.id, tenant.slug, db
        )

    # Must call permanently_delete_tenant (status update), not a raw SQL delete
    mock_perm_del.assert_awaited_once_with(tenant.id, db)
    assert result.status == TenantStatus.PERMANENTLY_DELETED
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_permanent_delete_writes_audit_event():
    """TENANT_PERMANENTLY_DELETED audit event must be written."""
    tenant = _make_tenant(status=TenantStatus.DELETED)
    purged = _purged_tenant(tenant)
    db = _make_db()
    actor_id = uuid.uuid4()

    with (
        patch(
            "app.core.tenants.service.TenantRepository.get_tenant_by_id",
            new=AsyncMock(return_value=tenant),
        ),
        patch(
            "app.core.tenants.service.TenantRepository.permanently_delete_tenant",
            new=AsyncMock(return_value=purged),
        ),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()) as mock_log,
    ):
        await TenantService.permanently_delete_tenant(
            tenant.id, tenant.slug, db, actor_user_id=actor_id
        )

    mock_log.assert_awaited_once()
    logged_event = mock_log.call_args[0][0]
    assert logged_event == AuditEventType.TENANT_PERMANENTLY_DELETED


@pytest.mark.asyncio
async def test_permanent_delete_slug_mismatch_raises():
    """Wrong slug confirmation must raise SLUG_MISMATCH."""
    tenant = _make_tenant(status=TenantStatus.DELETED, slug="real-slug")
    db = _make_db()

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_id",
        new=AsyncMock(return_value=tenant),
    ):
        with pytest.raises(TenantError) as exc:
            await TenantService.permanently_delete_tenant(tenant.id, "wrong-slug", db)

    assert exc.value.code == "SLUG_MISMATCH"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_permanent_delete_requires_deleted_status():
    """Only DELETED tenants may be permanently deleted."""
    for bad_status in (
        TenantStatus.ACTIVE,
        TenantStatus.INACTIVE,
        TenantStatus.ARCHIVED,
        TenantStatus.PROVISIONING,
        TenantStatus.FAILED,
    ):
        tenant = _make_tenant(status=bad_status)
        db = _make_db()

        with patch(
            "app.core.tenants.service.TenantRepository.get_tenant_by_id",
            new=AsyncMock(return_value=tenant),
        ):
            with pytest.raises(TenantError) as exc:
                await TenantService.permanently_delete_tenant(tenant.id, tenant.slug, db)

        assert exc.value.code == "INVALID_STATE", f"Expected INVALID_STATE for {bad_status}"


@pytest.mark.asyncio
async def test_permanent_delete_already_purged_raises():
    """Calling permanent delete on an already PERMANENTLY_DELETED tenant raises."""
    tenant = _make_tenant(status=TenantStatus.PERMANENTLY_DELETED)
    db = _make_db()

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_id",
        new=AsyncMock(return_value=tenant),
    ):
        with pytest.raises(TenantError) as exc:
            await TenantService.permanently_delete_tenant(tenant.id, tenant.slug, db)

    assert exc.value.code == "INVALID_STATE"


# ---------------------------------------------------------------------------
# restore_tenant — blocks PERMANENTLY_DELETED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_fails_for_permanently_deleted():
    """Restore must reject PERMANENTLY_DELETED tenants with a clear error."""
    tenant = _make_tenant(status=TenantStatus.PERMANENTLY_DELETED)
    db = _make_db()

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_id",
        new=AsyncMock(return_value=tenant),
    ):
        with pytest.raises(TenantError) as exc:
            await TenantService.restore_tenant(tenant.id, db)

    assert exc.value.code == "INVALID_STATE"
    assert exc.value.status_code == 409
    # Must not have committed — no changes made
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_restore_succeeds_for_soft_deleted():
    """Restore must still work for DELETED (soft-deleted) tenants."""
    tenant = _make_tenant(status=TenantStatus.DELETED)
    restored = _make_tenant(status=TenantStatus.INACTIVE)
    db = _make_db()

    with (
        patch(
            "app.core.tenants.service.TenantRepository.get_tenant_by_id",
            new=AsyncMock(return_value=tenant),
        ),
        patch(
            "app.core.tenants.service.TenantRepository.restore_tenant",
            new=AsyncMock(return_value=restored),
        ),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()),
    ):
        result = await TenantService.restore_tenant(tenant.id, db)

    assert result.status == TenantStatus.INACTIVE
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# list_tenants — PERMANENTLY_DELETED excluded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tenants_excludes_permanently_deleted():
    """PERMANENTLY_DELETED tenants must never appear in list results."""
    from app.core.tenants.repository import TenantRepository
    from sqlalchemy import select

    normal = _make_tenant(status=TenantStatus.ACTIVE)
    purged = _make_tenant(status=TenantStatus.PERMANENTLY_DELETED)

    # Simulate the repository filtering: the query excludes PERMANENTLY_DELETED.
    # We test the filter clause is applied on the stmt, not the full DB roundtrip.
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [normal]
    db.execute = AsyncMock(return_value=execute_result)

    result = await TenantRepository.list_tenants(db, include_inactive=True)

    # Verify the SQL was constructed with the exclusion filter.
    stmt_used = db.execute.call_args[0][0]
    stmt_str = str(stmt_used.compile(compile_kwargs={"literal_binds": True}))
    assert "PERMANENTLY_DELETED" in stmt_str, (
        "list_tenants query must filter out PERMANENTLY_DELETED"
    )
    assert normal in result
