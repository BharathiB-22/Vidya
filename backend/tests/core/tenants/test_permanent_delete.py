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


_FIXED_SUFFIX = "__deleted_20260608_120000"


def _purged_tenant(base: SimpleNamespace, suffix: str = _FIXED_SUFFIX) -> SimpleNamespace:
    """Simulate the tenant row after permanently_delete_tenant mangles slug/schema."""
    import copy
    t = copy.copy(base)
    t.status = TenantStatus.PERMANENTLY_DELETED
    t.is_active = False
    t.slug = f"{base.slug}{suffix}"
    t.schema_name = f"{base.schema_name}{suffix}"
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


# ---------------------------------------------------------------------------
# Slug and schema_name mangling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permanent_delete_result_slug_is_mangled():
    """After permanent delete the result slug must contain the __deleted_ suffix."""
    tenant = _make_tenant(status=TenantStatus.DELETED, slug="abs-university")
    tenant.schema_name = "tenant_abs_university"
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
        ),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()),
    ):
        result = await TenantService.permanently_delete_tenant(
            tenant.id, tenant.slug, db
        )

    assert result.slug.startswith("abs-university")
    assert "__deleted_" in result.slug
    assert result.schema_name.startswith("tenant_abs_university")
    assert "__deleted_" in result.schema_name


@pytest.mark.asyncio
async def test_permanent_delete_audit_records_original_slug():
    """AuditService.log must receive the ORIGINAL slug and schema_name, not mangled."""
    original_slug = "abs-university"
    original_schema = "tenant_abs_university"
    tenant = _make_tenant(
        status=TenantStatus.DELETED,
        slug=original_slug,
    )
    tenant.schema_name = original_schema
    purged = _purged_tenant(tenant)   # has mangled slug/schema
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
        patch(
            "app.core.tenants.service.AuditService.log",
            new=AsyncMock(),
        ) as mock_log,
    ):
        await TenantService.permanently_delete_tenant(
            tenant.id, original_slug, db, actor_user_id=actor_id
        )

    call_kwargs = mock_log.call_args[1]
    # schema_name arg to AuditService.log must be the original
    assert call_kwargs["schema_name"] == original_schema
    # metadata must record original values — not the compliance suffix
    assert call_kwargs["metadata"]["slug"] == original_slug
    assert call_kwargs["metadata"]["schema_name"] == original_schema
    assert "__deleted_" not in call_kwargs["metadata"]["slug"]
    assert "__deleted_" not in call_kwargs["metadata"]["schema_name"]


# ---------------------------------------------------------------------------
# Recreation — slug released after permanent delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tenant_succeeds_when_slug_released_by_permanent_delete():
    """
    After permanent delete, get_tenant_by_slug returns None (slug is mangled).
    Creating a new tenant with the same institution name must succeed.
    """
    from app.core.tenants.schemas import CreateTenantRequest

    provisioned = _make_tenant(status=TenantStatus.ACTIVE, slug="abs-university")
    provisioned.status = TenantStatus.ACTIVE
    db = _make_db()

    with (
        patch(
            "app.core.tenants.service.TenantRepository.get_tenant_by_slug",
            new=AsyncMock(return_value=None),   # slug released — not found
        ),
        patch(
            "app.core.tenants.service.TenantRepository.create_tenant",
            new=AsyncMock(return_value=provisioned),
        ),
        patch(
            "app.core.tenants.service.run_tenant_migrations",
            new=AsyncMock(),
        ),
        patch(
            "app.core.tenants.service.seed_admin_user",
            new=AsyncMock(),
        ),
        patch(
            "app.core.tenants.service.TenantRepository.update_tenant",
            new=AsyncMock(return_value=provisioned),
        ),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()),
        patch("app.core.tenants.service._dispatch_welcome_email"),
    ):
        result = await TenantService.create_tenant(
            CreateTenantRequest(
                name="ABS University",
                admin_email="admin@abs.edu",
                admin_password="Admin1234!",
                admin_full_name="Admin",
            ),
            db,
        )

    assert result.status == TenantStatus.ACTIVE


@pytest.mark.asyncio
async def test_create_tenant_still_blocked_when_active_tenant_exists():
    """Recreation must still be rejected if a non-deleted tenant with the slug exists."""
    from app.core.tenants.schemas import CreateTenantRequest

    existing = _make_tenant(status=TenantStatus.ACTIVE, slug="abs-university")
    db = _make_db()

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_slug",
        new=AsyncMock(return_value=existing),  # slug still occupied
    ):
        with pytest.raises(TenantError) as exc:
            await TenantService.create_tenant(
                CreateTenantRequest(
                    name="ABS University",
                    admin_email="admin@abs.edu",
                    admin_password="Admin1234!",
                    admin_full_name="Admin",
                ),
                db,
            )

    assert exc.value.code == "SLUG_CONFLICT"
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Repository — schema rename SQL verification (integration-level unit test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repository_permanently_delete_renames_schema():
    """
    TenantRepository.permanently_delete_tenant must:
    - check whether the schema exists via information_schema
    - issue ALTER SCHEMA ... RENAME TO ... with the __deleted_ suffix
    - mangle slug and schema_name on the tenant row
    """
    from app.core.tenants.repository import TenantRepository
    import copy

    original_slug = "abs-university"
    original_schema = "tenant_abs_university"
    tenant = _make_tenant(status=TenantStatus.DELETED, slug=original_slug)
    tenant.schema_name = original_schema

    # Track every db.execute call
    execute_calls: list[str] = []

    async def _fake_execute(stmt, params=None):
        sql = str(stmt) if hasattr(stmt, "__clause_element__") else str(stmt)
        execute_calls.append(sql)
        # First call: information_schema check → schema exists
        if "information_schema" in sql:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = 1
            return mock_result
        # Second call: ALTER SCHEMA → no return value needed
        if "ALTER SCHEMA" in sql:
            return MagicMock()
        # SELECT Tenant query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = copy.copy(tenant)
        return mock_result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_fake_execute)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    result = await TenantRepository.permanently_delete_tenant(tenant.id, db)

    # Schema rename SQL must have been issued
    rename_calls = [c for c in execute_calls if "ALTER SCHEMA" in c]
    assert len(rename_calls) == 1, "Expected exactly one ALTER SCHEMA statement"
    rename_sql = rename_calls[0]
    assert f'"{original_schema}"' in rename_sql
    assert "__deleted_" in rename_sql

    # Tenant row must have mangled values
    assert result.status == TenantStatus.PERMANENTLY_DELETED
    assert result.slug.startswith(original_slug)
    assert "__deleted_" in result.slug
    assert result.schema_name.startswith(original_schema)
    assert "__deleted_" in result.schema_name


@pytest.mark.asyncio
async def test_repository_permanently_delete_skips_rename_when_schema_absent():
    """
    If the schema never existed (FAILED provisioning), permanent delete must
    succeed without issuing ALTER SCHEMA.
    """
    from app.core.tenants.repository import TenantRepository
    import copy

    tenant = _make_tenant(status=TenantStatus.DELETED, slug="ghost-university")
    tenant.schema_name = "tenant_ghost_university"
    execute_calls: list[str] = []

    async def _fake_execute(stmt, params=None):
        sql = str(stmt) if hasattr(stmt, "__clause_element__") else str(stmt)
        execute_calls.append(sql)
        if "information_schema" in sql:
            # Schema does not exist
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = copy.copy(tenant)
        return mock_result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_fake_execute)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    result = await TenantRepository.permanently_delete_tenant(tenant.id, db)

    rename_calls = [c for c in execute_calls if "ALTER SCHEMA" in c]
    assert len(rename_calls) == 0, "ALTER SCHEMA must not be issued when schema is absent"
    assert result.status == TenantStatus.PERMANENTLY_DELETED
