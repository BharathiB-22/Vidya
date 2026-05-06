import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.auth.models import TenantStatus
from app.core.tenants.schemas import CreateTenantRequest, TenantUpdateRequest
from app.core.tenants.service import TenantError, TenantService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant(
    status: TenantStatus = TenantStatus.ACTIVE,
    is_active: bool = True,
    slug: str = "test-university",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Test University",
        slug=slug,
        schema_name="tenant_test_university",
        status=status,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
    )


def _make_db() -> MagicMock:
    """Return a mock AsyncSession whose begin() is an async context manager."""
    db = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin = MagicMock(return_value=ctx)
    return db


def _create_request(**kwargs) -> CreateTenantRequest:
    defaults = dict(
        name="Test University",
        admin_email="admin@test.edu",
        admin_password="Admin1234!",
        admin_full_name="Admin User",
    )
    return CreateTenantRequest(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# create_tenant — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tenant_success():
    db = _make_db()
    provisioning_tenant = _make_tenant(status=TenantStatus.PROVISIONING, is_active=False)
    active_tenant = _make_tenant(status=TenantStatus.ACTIVE, is_active=True)

    with (
        patch("app.core.tenants.service.TenantRepository.get_tenant_by_slug", new=AsyncMock(return_value=None)),
        patch("app.core.tenants.service.TenantRepository.create_tenant", new=AsyncMock(return_value=provisioning_tenant)),
        patch("app.core.tenants.service.run_tenant_migrations", new=AsyncMock(return_value=None)),
        patch("app.core.tenants.service.seed_admin_user", new=AsyncMock(return_value=None)),
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=AsyncMock(return_value=active_tenant)),
        patch("app.core.tenants.service.hash_password", return_value="hashed"),
    ):
        result = await TenantService.create_tenant(_create_request(), db)

    assert result.status == TenantStatus.ACTIVE
    assert result.is_active is True
    assert result.slug == "test-university"


# ---------------------------------------------------------------------------
# create_tenant — slug conflict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tenant_slug_conflict():
    db = _make_db()
    existing = _make_tenant()

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_slug",
        new=AsyncMock(return_value=existing),
    ):
        with pytest.raises(TenantError) as exc_info:
            await TenantService.create_tenant(_create_request(), db)

    assert exc_info.value.code == "SLUG_CONFLICT"
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# create_tenant — migration failure → status set to FAILED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tenant_migration_failure():
    db = _make_db()
    provisioning_tenant = _make_tenant(status=TenantStatus.PROVISIONING, is_active=False)
    failed_tenant = _make_tenant(status=TenantStatus.FAILED, is_active=False)

    update_mock = AsyncMock(return_value=failed_tenant)

    with (
        patch("app.core.tenants.service.TenantRepository.get_tenant_by_slug", new=AsyncMock(return_value=None)),
        patch("app.core.tenants.service.TenantRepository.create_tenant", new=AsyncMock(return_value=provisioning_tenant)),
        patch("app.core.tenants.service.run_tenant_migrations", new=AsyncMock(side_effect=RuntimeError("pg error"))),
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=update_mock),
        patch("app.core.tenants.service.hash_password", return_value="hashed"),
    ):
        with pytest.raises(TenantError) as exc_info:
            await TenantService.create_tenant(_create_request(), db)

    assert exc_info.value.code == "PROVISIONING_FAILED"
    assert exc_info.value.status_code == 500
    # update_tenant must have been called to mark the tenant FAILED
    update_mock.assert_awaited_once()
    call_kwargs = update_mock.call_args[0][1]  # second positional arg is the updates dict
    assert call_kwargs.get("status") == TenantStatus.FAILED


# ---------------------------------------------------------------------------
# get_tenant — not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tenant_not_found():
    db = _make_db()

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_id",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(TenantError) as exc_info:
            await TenantService.get_tenant(uuid.uuid4(), db)

    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# update_tenant — no fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tenant_no_fields():
    db = _make_db()
    body = TenantUpdateRequest()  # all None

    with pytest.raises(TenantError) as exc_info:
        await TenantService.update_tenant(uuid.uuid4(), body, db)

    assert exc_info.value.code == "NO_FIELDS"
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# update_tenant — not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tenant_not_found():
    db = _make_db()
    body = TenantUpdateRequest(is_active=False)

    with patch(
        "app.core.tenants.service.TenantRepository.update_tenant",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(TenantError) as exc_info:
            await TenantService.update_tenant(uuid.uuid4(), body, db)

    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# list_tenants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tenants_returns_all():
    db = _make_db()
    tenants = [_make_tenant(slug="uni-a"), _make_tenant(slug="uni-b")]

    with patch(
        "app.core.tenants.service.TenantRepository.list_tenants",
        new=AsyncMock(return_value=tenants),
    ):
        result = await TenantService.list_tenants(db, include_inactive=True)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_tenants_empty():
    db = _make_db()

    with patch(
        "app.core.tenants.service.TenantRepository.list_tenants",
        new=AsyncMock(return_value=[]),
    ):
        result = await TenantService.list_tenants(db)

    assert result == []
