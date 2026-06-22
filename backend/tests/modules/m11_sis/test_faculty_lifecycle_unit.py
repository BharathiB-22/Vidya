"""Unit tests for H64.4 — Faculty Lifecycle Service and Router."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.m11_sis.lifecycle_service import (
    FACULTY_ALL_STATUSES,
    FACULTY_TRANSITIONS,
    FacultyLifecycleService,
    LifecycleServiceError,
)


# ---------------------------------------------------------------------------
# 1. FACULTY_ALL_STATUSES is exactly 3 values
# ---------------------------------------------------------------------------

def test_faculty_all_statuses():
    assert FACULTY_ALL_STATUSES == {"ACTIVE", "INACTIVE", "ARCHIVED"}


# ---------------------------------------------------------------------------
# 2. FACULTY_TRANSITIONS keys match all statuses
# ---------------------------------------------------------------------------

def test_faculty_transition_keys():
    assert set(FACULTY_TRANSITIONS.keys()) == FACULTY_ALL_STATUSES


# ---------------------------------------------------------------------------
# 3. ARCHIVED is terminal
# ---------------------------------------------------------------------------

def test_faculty_archived_terminal():
    assert FACULTY_TRANSITIONS["ARCHIVED"] == []


# ---------------------------------------------------------------------------
# 4. All transition targets are valid
# ---------------------------------------------------------------------------

def test_faculty_transition_targets_valid():
    for src, targets in FACULTY_TRANSITIONS.items():
        for t in targets:
            assert t in FACULTY_ALL_STATUSES


# ---------------------------------------------------------------------------
# 5. ACTIVE can go to INACTIVE and ARCHIVED
# ---------------------------------------------------------------------------

def test_active_transitions():
    assert set(FACULTY_TRANSITIONS["ACTIVE"]) == {"INACTIVE", "ARCHIVED"}


# ---------------------------------------------------------------------------
# 6. INACTIVE can go to ACTIVE and ARCHIVED (reversible)
# ---------------------------------------------------------------------------

def test_inactive_transitions():
    assert set(FACULTY_TRANSITIONS["INACTIVE"]) == {"ACTIVE", "ARCHIVED"}


# ---------------------------------------------------------------------------
# 7. Non-ADMIN/DEAN actor is rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_rejects_student_role():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(lifecycle_status="ACTIVE"))

    with pytest.raises(LifecycleServiceError) as exc_info:
        await FacultyLifecycleService.transition(
            uuid.uuid4(), "INACTIVE",
            actor_user_id=uuid.uuid4(),
            actor_role="STUDENT",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "FORBIDDEN"
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 8. Unknown status is rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_rejects_unknown_status():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(lifecycle_status="ACTIVE"))

    with pytest.raises(LifecycleServiceError) as exc_info:
        await FacultyLifecycleService.transition(
            uuid.uuid4(), "SUSPENDED",
            actor_user_id=uuid.uuid4(),
            actor_role="ADMIN",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 9. Same-status transition is rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_rejects_same_status():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(lifecycle_status="INACTIVE"))

    with pytest.raises(LifecycleServiceError) as exc_info:
        await FacultyLifecycleService.transition(
            uuid.uuid4(), "INACTIVE",
            actor_user_id=uuid.uuid4(),
            actor_role="DEAN",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "NO_CHANGE"


# ---------------------------------------------------------------------------
# 10. Terminal state (ARCHIVED) rejects outbound transition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_rejects_from_archived():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(lifecycle_status="ARCHIVED"))

    with pytest.raises(LifecycleServiceError) as exc_info:
        await FacultyLifecycleService.transition(
            uuid.uuid4(), "ACTIVE",
            actor_user_id=uuid.uuid4(),
            actor_role="ADMIN",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "INVALID_TRANSITION"
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 11. NOT_FOUND for missing profile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_raises_not_found():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(LifecycleServiceError) as exc_info:
        await FacultyLifecycleService.transition(
            uuid.uuid4(), "INACTIVE",
            actor_user_id=uuid.uuid4(),
            actor_role="ADMIN",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 12. Successful ACTIVE → INACTIVE transition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_deactivation():
    profile = MagicMock()
    profile.lifecycle_status = "ACTIVE"
    profile.is_active        = True

    db = AsyncMock()
    db.get   = AsyncMock(return_value=profile)
    db.add   = MagicMock()
    db.flush = AsyncMock()

    result = await FacultyLifecycleService.transition(
        uuid.uuid4(), "INACTIVE",
        actor_user_id=uuid.uuid4(),
        actor_role="ADMIN",
        reason="On leave",
        db=db,
    )
    assert result.lifecycle_status == "INACTIVE"
    assert result.is_active is False
    db.add.assert_called_once()


# ---------------------------------------------------------------------------
# 13. INACTIVE → ACTIVE reactivation sets is_active=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reactivation():
    profile = MagicMock()
    profile.lifecycle_status = "INACTIVE"
    profile.is_active        = False

    db = AsyncMock()
    db.get   = AsyncMock(return_value=profile)
    db.add   = MagicMock()
    db.flush = AsyncMock()

    result = await FacultyLifecycleService.transition(
        uuid.uuid4(), "ACTIVE",
        actor_user_id=uuid.uuid4(),
        actor_role="DEAN",
        reason="Returned from leave",
        db=db,
    )
    assert result.lifecycle_status == "ACTIVE"
    assert result.is_active is True


# ---------------------------------------------------------------------------
# 14. ACTIVE → ARCHIVED sets is_active=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_archive_sets_inactive():
    profile = MagicMock()
    profile.lifecycle_status = "ACTIVE"
    profile.is_active        = True

    db = AsyncMock()
    db.get   = AsyncMock(return_value=profile)
    db.add   = MagicMock()
    db.flush = AsyncMock()

    result = await FacultyLifecycleService.transition(
        uuid.uuid4(), "ARCHIVED",
        actor_user_id=uuid.uuid4(),
        actor_role="ADMIN",
        reason=None,
        db=db,
    )
    assert result.is_active is False


# ---------------------------------------------------------------------------
# 15. lifecycle_router now has 4 routes (2 student + 2 faculty)
# ---------------------------------------------------------------------------

def test_lifecycle_router_has_four_routes():
    from app.modules.m11_sis.lifecycle_router import lifecycle_router
    assert len(lifecycle_router.routes) == 4


# ---------------------------------------------------------------------------
# 16. Faculty lifecycle routes are present in main SIS router
# ---------------------------------------------------------------------------

def test_sis_router_has_faculty_lifecycle_routes():
    from app.modules.m11_sis.router import router
    paths = [r.path for r in router.routes]
    assert "/faculty/{faculty_id}/lifecycle" in paths


# ---------------------------------------------------------------------------
# 17. Total SIS route count updated (+2 faculty lifecycle = 171)
# ---------------------------------------------------------------------------

def test_sis_router_total_routes_h644():
    from app.modules.m11_sis.router import router
    assert len(router.routes) == 179


# ---------------------------------------------------------------------------
# 18. Migration 0041ten exists and chains correctly
# ---------------------------------------------------------------------------

def test_faculty_lifecycle_migration_revision():
    import importlib.util, pathlib
    p = pathlib.Path("backend/alembic/tenant_versions/0041ten_faculty_lifecycle.py")
    assert p.exists(), "Migration 0041ten not found"
    spec = importlib.util.spec_from_file_location("mig_0041", p)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision      == "0041ten"
    assert mod.down_revision == "0040ten"
