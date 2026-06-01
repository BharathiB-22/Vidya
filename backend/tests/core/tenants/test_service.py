import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.core.audit_log.models import AuditEventType
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
    contact_email: str | None = "admin@test.edu",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Test University",
        slug=slug,
        schema_name="tenant_test_university",
        status=status,
        is_active=is_active,
        contact_email=contact_email,
        created_at=datetime.now(timezone.utc),
    )


def _make_db() -> MagicMock:
    """Return a mock AsyncSession with awaitable commit/rollback."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
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
# create_tenant — success + welcome email fired
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
        patch("app.core.tenants.service._dispatch_welcome_email") as mock_email,
    ):
        result = await TenantService.create_tenant(_create_request(), db)

    assert result.status == TenantStatus.ACTIVE
    assert result.is_active is True
    assert result.slug == "test-university"
    mock_email.assert_called_once()


@pytest.mark.asyncio
async def test_create_tenant_welcome_email_uses_contact_email():
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
        patch("app.core.tenants.service._dispatch_welcome_email") as mock_email,
    ):
        await TenantService.create_tenant(
            _create_request(contact_email="contact@other.edu"),
            db,
        )

    # contact_email overrides admin_email for welcome dispatch
    mock_email.assert_called_once_with("contact@other.edu")


@pytest.mark.asyncio
async def test_create_tenant_welcome_email_falls_back_to_admin_email():
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
        patch("app.core.tenants.service._dispatch_welcome_email") as mock_email,
    ):
        await TenantService.create_tenant(
            _create_request(),  # no contact_email → defaults to admin_email
            db,
        )

    mock_email.assert_called_once_with("admin@test.edu")


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
# retry_provisioning — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_provisioning_success():
    db = _make_db()
    failed_tenant = _make_tenant(status=TenantStatus.FAILED, is_active=False)
    active_tenant = _make_tenant(status=TenantStatus.ACTIVE, is_active=True)
    update_mock = AsyncMock(side_effect=[
        _make_tenant(status=TenantStatus.PROVISIONING, is_active=False),  # first call: set PROVISIONING
        active_tenant,  # second call: set ACTIVE
    ])

    with (
        patch("app.core.tenants.service.TenantRepository.get_tenant_by_id", new=AsyncMock(return_value=failed_tenant)),
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=update_mock),
        patch("app.core.tenants.service.run_tenant_migrations", new=AsyncMock(return_value=None)),
        patch("app.core.tenants.service._dispatch_welcome_email") as mock_email,
    ):
        result = await TenantService.retry_provisioning(failed_tenant.id, db)

    assert result.status == TenantStatus.ACTIVE
    mock_email.assert_called_once()


@pytest.mark.asyncio
async def test_retry_provisioning_sends_welcome_email():
    db = _make_db()
    failed_tenant = _make_tenant(
        status=TenantStatus.FAILED,
        is_active=False,
        contact_email="contact@uni.edu",
    )
    active_tenant = _make_tenant(status=TenantStatus.ACTIVE, is_active=True, contact_email="contact@uni.edu")
    update_mock = AsyncMock(side_effect=[
        _make_tenant(status=TenantStatus.PROVISIONING, is_active=False, contact_email="contact@uni.edu"),
        active_tenant,
    ])

    with (
        patch("app.core.tenants.service.TenantRepository.get_tenant_by_id", new=AsyncMock(return_value=failed_tenant)),
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=update_mock),
        patch("app.core.tenants.service.run_tenant_migrations", new=AsyncMock(return_value=None)),
        patch("app.core.tenants.service._dispatch_welcome_email") as mock_email,
    ):
        await TenantService.retry_provisioning(failed_tenant.id, db)

    mock_email.assert_called_once_with("contact@uni.edu")


# ---------------------------------------------------------------------------
# retry_provisioning — invalid state (not FAILED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_provisioning_rejected_when_active():
    db = _make_db()
    active_tenant = _make_tenant(status=TenantStatus.ACTIVE, is_active=True)

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_id",
        new=AsyncMock(return_value=active_tenant),
    ):
        with pytest.raises(TenantError) as exc_info:
            await TenantService.retry_provisioning(active_tenant.id, db)

    assert exc_info.value.code == "INVALID_STATE"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_retry_provisioning_rejected_when_provisioning():
    db = _make_db()
    provisioning_tenant = _make_tenant(status=TenantStatus.PROVISIONING, is_active=False)

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_id",
        new=AsyncMock(return_value=provisioning_tenant),
    ):
        with pytest.raises(TenantError) as exc_info:
            await TenantService.retry_provisioning(provisioning_tenant.id, db)

    assert exc_info.value.code == "INVALID_STATE"
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# retry_provisioning — migration failure marks FAILED again
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_provisioning_migration_failure():
    db = _make_db()
    failed_tenant = _make_tenant(status=TenantStatus.FAILED, is_active=False)
    update_mock = AsyncMock(return_value=_make_tenant(status=TenantStatus.FAILED, is_active=False))

    with (
        patch("app.core.tenants.service.TenantRepository.get_tenant_by_id", new=AsyncMock(return_value=failed_tenant)),
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=update_mock),
        patch("app.core.tenants.service.run_tenant_migrations", new=AsyncMock(side_effect=RuntimeError("schema error"))),
    ):
        with pytest.raises(TenantError) as exc_info:
            await TenantService.retry_provisioning(failed_tenant.id, db)

    assert exc_info.value.code == "PROVISIONING_FAILED"
    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# retry_provisioning — not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_provisioning_not_found():
    db = _make_db()

    with patch(
        "app.core.tenants.service.TenantRepository.get_tenant_by_id",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(TenantError) as exc_info:
            await TenantService.retry_provisioning(uuid.uuid4(), db)

    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.status_code == 404


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


# ---------------------------------------------------------------------------
# update_tenant — schema validation
# ---------------------------------------------------------------------------


def test_update_request_rejects_provisioning_status():
    with pytest.raises(ValidationError):
        TenantUpdateRequest(status=TenantStatus.PROVISIONING)


def test_update_request_rejects_failed_status():
    with pytest.raises(ValidationError):
        TenantUpdateRequest(status=TenantStatus.FAILED)


def test_update_request_accepts_active_inactive_archived():
    for s in (TenantStatus.ACTIVE, TenantStatus.INACTIVE, TenantStatus.ARCHIVED):
        req = TenantUpdateRequest(status=s)
        assert req.status == s


# ---------------------------------------------------------------------------
# update_tenant — contact_email update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tenant_contact_email():
    db = _make_db()
    updated = _make_tenant(contact_email="new@uni.edu")

    with (
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=AsyncMock(return_value=updated)),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()) as mock_audit,
    ):
        body = TenantUpdateRequest(contact_email="new@uni.edu")
        result = await TenantService.update_tenant(updated.id, body, db)

    assert result.contact_email == "new@uni.edu"
    event_arg = mock_audit.call_args[0][0]
    assert event_arg == AuditEventType.TENANT_UPDATED


# ---------------------------------------------------------------------------
# update_tenant — archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tenant_archive():
    db = _make_db()
    archived = _make_tenant(status=TenantStatus.ARCHIVED, is_active=False)

    with (
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=AsyncMock(return_value=archived)),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()) as mock_audit,
    ):
        body = TenantUpdateRequest(status=TenantStatus.ARCHIVED)
        result = await TenantService.update_tenant(archived.id, body, db)

    assert result.status == TenantStatus.ARCHIVED
    assert result.is_active is False
    event_arg = mock_audit.call_args[0][0]
    assert event_arg == AuditEventType.TENANT_ARCHIVED


# ---------------------------------------------------------------------------
# update_tenant — deactivate via status=INACTIVE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tenant_deactivate_via_status():
    db = _make_db()
    inactive = _make_tenant(status=TenantStatus.INACTIVE, is_active=False)

    with (
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=AsyncMock(return_value=inactive)),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()) as mock_audit,
    ):
        body = TenantUpdateRequest(status=TenantStatus.INACTIVE)
        result = await TenantService.update_tenant(inactive.id, body, db)

    assert result.status == TenantStatus.INACTIVE
    assert result.is_active is False
    event_arg = mock_audit.call_args[0][0]
    assert event_arg == AuditEventType.TENANT_DEACTIVATED


# ---------------------------------------------------------------------------
# update_tenant — reactivate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tenant_reactivate():
    db = _make_db()
    active = _make_tenant(status=TenantStatus.ACTIVE, is_active=True)

    with (
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=AsyncMock(return_value=active)),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()) as mock_audit,
    ):
        body = TenantUpdateRequest(status=TenantStatus.ACTIVE)
        result = await TenantService.update_tenant(active.id, body, db)

    assert result.status == TenantStatus.ACTIVE
    assert result.is_active is True
    event_arg = mock_audit.call_args[0][0]
    assert event_arg == AuditEventType.TENANT_REACTIVATED


# ---------------------------------------------------------------------------
# update_tenant — legacy is_active=False sets INACTIVE status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tenant_legacy_deactivate_sets_inactive_status():
    db = _make_db()
    inactive = _make_tenant(status=TenantStatus.INACTIVE, is_active=False)
    update_mock = AsyncMock(return_value=inactive)

    with (
        patch("app.core.tenants.service.TenantRepository.update_tenant", new=update_mock),
        patch("app.core.tenants.service.AuditService.log", new=AsyncMock()) as mock_audit,
    ):
        body = TenantUpdateRequest(is_active=False)
        await TenantService.update_tenant(inactive.id, body, db)

    call_updates = update_mock.call_args[0][1]
    assert call_updates.get("status") == TenantStatus.INACTIVE
    assert call_updates.get("is_active") is False
    event_arg = mock_audit.call_args[0][0]
    assert event_arg == AuditEventType.TENANT_DEACTIVATED
