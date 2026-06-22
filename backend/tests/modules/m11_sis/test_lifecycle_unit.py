"""Unit tests for H64.3 — Student Lifecycle Service and Router."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m11_sis.lifecycle_service import (
    TRANSITIONS,
    ALL_STATUSES,
    LifecycleServiceError,
    StudentLifecycleService,
)


# ---------------------------------------------------------------------------
# 1. ALL_STATUSES contains all 8 expected values
# ---------------------------------------------------------------------------

def test_all_statuses_complete():
    expected = {"APPLICANT", "ENROLLED", "ACTIVE", "DETAINED", "GRADUATED", "ALUMNI", "WITHDRAWN", "ARCHIVED"}
    assert ALL_STATUSES == expected


# ---------------------------------------------------------------------------
# 2. TRANSITIONS keys match ALL_STATUSES
# ---------------------------------------------------------------------------

def test_transition_keys_match_all_statuses():
    assert set(TRANSITIONS.keys()) == ALL_STATUSES


# ---------------------------------------------------------------------------
# 3. ARCHIVED is terminal
# ---------------------------------------------------------------------------

def test_archived_is_terminal():
    assert TRANSITIONS["ARCHIVED"] == []


# ---------------------------------------------------------------------------
# 4. All transition targets are valid statuses
# ---------------------------------------------------------------------------

def test_all_transition_targets_valid():
    for src, targets in TRANSITIONS.items():
        for t in targets:
            assert t in ALL_STATUSES, f"{src} → {t} references unknown status"


# ---------------------------------------------------------------------------
# 5. No self-transitions in map
# ---------------------------------------------------------------------------

def test_no_self_transitions():
    for src, targets in TRANSITIONS.items():
        assert src not in targets, f"{src} has self-transition"


# ---------------------------------------------------------------------------
# 6. Known specific transitions are correct
# ---------------------------------------------------------------------------

def test_applicant_transitions():
    assert set(TRANSITIONS["APPLICANT"]) == {"ENROLLED", "WITHDRAWN"}

def test_active_transitions():
    assert set(TRANSITIONS["ACTIVE"]) == {"DETAINED", "GRADUATED", "WITHDRAWN", "ALUMNI"}


# ---------------------------------------------------------------------------
# 7. transition() rejects non-ADMIN/DEAN actors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_rejects_non_admin():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(lifecycle_status="ACTIVE"))

    with pytest.raises(LifecycleServiceError) as exc_info:
        await StudentLifecycleService.transition(
            uuid.uuid4(), "GRADUATED",
            actor_user_id=uuid.uuid4(),
            actor_role="FACULTY",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "FORBIDDEN"
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 8. transition() rejects unknown status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_rejects_unknown_status():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(lifecycle_status="ACTIVE"))

    with pytest.raises(LifecycleServiceError) as exc_info:
        await StudentLifecycleService.transition(
            uuid.uuid4(), "ZOMBIE",
            actor_user_id=uuid.uuid4(),
            actor_role="ADMIN",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 9. transition() rejects same-status change
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_rejects_same_status():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(lifecycle_status="ACTIVE"))

    with pytest.raises(LifecycleServiceError) as exc_info:
        await StudentLifecycleService.transition(
            uuid.uuid4(), "ACTIVE",
            actor_user_id=uuid.uuid4(),
            actor_role="ADMIN",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "NO_CHANGE"


# ---------------------------------------------------------------------------
# 10. transition() rejects invalid path (e.g. ACTIVE → ENROLLED)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_rejects_invalid_path():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(lifecycle_status="ACTIVE"))

    with pytest.raises(LifecycleServiceError) as exc_info:
        await StudentLifecycleService.transition(
            uuid.uuid4(), "ENROLLED",
            actor_user_id=uuid.uuid4(),
            actor_role="ADMIN",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "INVALID_TRANSITION"
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 11. transition() raises NOT_FOUND for missing profile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_raises_not_found():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(LifecycleServiceError) as exc_info:
        await StudentLifecycleService.transition(
            uuid.uuid4(), "GRADUATED",
            actor_user_id=uuid.uuid4(),
            actor_role="ADMIN",
            reason=None,
            db=db,
        )
    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 12. Successful transition updates profile and creates history entry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_transition():
    profile = MagicMock()
    profile.lifecycle_status = "ACTIVE"
    profile.is_active        = True
    profile.updated_at       = None

    db = AsyncMock()
    db.get   = AsyncMock(return_value=profile)
    db.add   = MagicMock()
    db.flush = AsyncMock()

    result = await StudentLifecycleService.transition(
        uuid.uuid4(), "GRADUATED",
        actor_user_id=uuid.uuid4(),
        actor_role="DEAN",
        reason="Completed all credits",
        db=db,
    )

    assert result.lifecycle_status == "GRADUATED"
    assert result.is_active is True
    db.add.assert_called_once()
    db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# 13. Transition to WITHDRAWN sets is_active=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_withdrawn_sets_inactive():
    profile = MagicMock()
    profile.lifecycle_status = "ACTIVE"
    profile.is_active        = True

    db = AsyncMock()
    db.get   = AsyncMock(return_value=profile)
    db.add   = MagicMock()
    db.flush = AsyncMock()

    await StudentLifecycleService.transition(
        uuid.uuid4(), "WITHDRAWN",
        actor_user_id=uuid.uuid4(),
        actor_role="ADMIN",
        reason=None,
        db=db,
    )
    assert profile.is_active is False


# ---------------------------------------------------------------------------
# 14. Transition to ARCHIVED sets is_active=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_archived_sets_inactive():
    profile = MagicMock()
    profile.lifecycle_status = "WITHDRAWN"
    profile.is_active        = False

    db = AsyncMock()
    db.get   = AsyncMock(return_value=profile)
    db.add   = MagicMock()
    db.flush = AsyncMock()

    await StudentLifecycleService.transition(
        uuid.uuid4(), "ARCHIVED",
        actor_user_id=uuid.uuid4(),
        actor_role="ADMIN",
        reason=None,
        db=db,
    )
    assert profile.is_active is False


# ---------------------------------------------------------------------------
# 15. lifecycle_router imports and registers 2 routes
# ---------------------------------------------------------------------------

def test_lifecycle_router_routes():
    from app.modules.m11_sis.lifecycle_router import lifecycle_router
    paths = [r.path for r in lifecycle_router.routes]
    assert "/students/{student_id}/lifecycle" in paths
    # H64.4 adds 2 faculty routes → 4 total
    assert len(lifecycle_router.routes) == 4


# ---------------------------------------------------------------------------
# 16. Main SIS router includes lifecycle routes
# ---------------------------------------------------------------------------

def test_sis_router_includes_lifecycle():
    from app.modules.m11_sis.router import router
    paths = [r.path for r in router.routes]
    assert "/students/{student_id}/lifecycle" in paths


# ---------------------------------------------------------------------------
# 17. SIS router total route count updated for H64.3 (+2 lifecycle routes)
# ---------------------------------------------------------------------------

def test_sis_router_total_routes_h643():
    from app.modules.m11_sis.router import router
    # 167 (H64.1/H64.2) + 2 student lifecycle + 2 faculty lifecycle = 171
    assert len(router.routes) == 179


# ---------------------------------------------------------------------------
# 18. Migration file exists and has correct revision chain
# ---------------------------------------------------------------------------

def test_lifecycle_migration_exists():
    import importlib.util, pathlib
    p = pathlib.Path("backend/alembic/tenant_versions/0040ten_student_lifecycle.py")
    assert p.exists(), "Migration 0040ten not found"


def test_lifecycle_migration_revision():
    import importlib.util, pathlib
    p = pathlib.Path("backend/alembic/tenant_versions/0040ten_student_lifecycle.py")
    spec = importlib.util.spec_from_file_location("mig_0040", p)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision      == "0040ten"
    assert mod.down_revision == "0039ten"
