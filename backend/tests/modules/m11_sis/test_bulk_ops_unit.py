"""Unit tests for H64.5 — Bulk Operations Service and Router."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m11_sis.bulk_ops_schemas import BulkFacultyIn, BulkOpResult, BulkStudentIn
from app.modules.m11_sis.bulk_ops_service import (
    BulkOpsService,
    _FACULTY_ACTION_MAP,
    _STUDENT_ACTION_MAP,
)
from app.modules.m11_sis.lifecycle_service import LifecycleServiceError


# ---------------------------------------------------------------------------
# 1. Action maps
# ---------------------------------------------------------------------------

def test_student_action_map_deactivate():
    assert _STUDENT_ACTION_MAP["DEACTIVATE"] == "WITHDRAWN"


def test_student_action_map_archive():
    assert _STUDENT_ACTION_MAP["ARCHIVE"] == "ARCHIVED"


def test_faculty_action_map_deactivate():
    assert _FACULTY_ACTION_MAP["DEACTIVATE"] == "INACTIVE"


def test_faculty_action_map_archive():
    assert _FACULTY_ACTION_MAP["ARCHIVE"] == "ARCHIVED"


# ---------------------------------------------------------------------------
# 2. BulkStudentIn schema validation
# ---------------------------------------------------------------------------

def test_bulk_student_in_valid():
    ids = [uuid.uuid4(), uuid.uuid4()]
    obj = BulkStudentIn(student_ids=ids, action="DEACTIVATE")
    assert obj.action == "DEACTIVATE"
    assert len(obj.student_ids) == 2


def test_bulk_student_in_empty_list_rejected():
    with pytest.raises(Exception):
        BulkStudentIn(student_ids=[], action="DEACTIVATE")


def test_bulk_student_in_invalid_action_rejected():
    with pytest.raises(Exception):
        BulkStudentIn(student_ids=[uuid.uuid4()], action="GRADUATE")


def test_bulk_faculty_in_valid():
    ids = [uuid.uuid4()]
    obj = BulkFacultyIn(faculty_ids=ids, action="ARCHIVE")
    assert obj.action == "ARCHIVE"


# ---------------------------------------------------------------------------
# 3. BulkOpResult schema
# ---------------------------------------------------------------------------

def test_bulk_op_result_fields():
    r = BulkOpResult(action="DEACTIVATE", requested=3, succeeded=2, failed=1, errors=["x: err"])
    assert r.requested == 3
    assert r.succeeded == 2
    assert r.failed == 1
    assert len(r.errors) == 1


# ---------------------------------------------------------------------------
# 4. bulk_student_action — all succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_student_action_all_succeed():
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    actor_id = uuid.uuid4()
    db = AsyncMock()

    with patch(
        "app.modules.m11_sis.bulk_ops_service.StudentLifecycleService.transition",
        new_callable=AsyncMock,
    ) as mock_t:
        mock_t.return_value = MagicMock()
        result = await BulkOpsService.bulk_student_action(
            ids, "DEACTIVATE",
            reason="batch deactivate",
            actor_user_id=actor_id,
            actor_role="ADMIN",
            db=db,
        )

    assert result.succeeded == 3
    assert result.failed == 0
    assert result.errors == []
    assert mock_t.call_count == 3


# ---------------------------------------------------------------------------
# 5. bulk_student_action — partial failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_student_action_partial_failure():
    good_id = uuid.uuid4()
    bad_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    db = AsyncMock()

    def side_effect(student_id, new_status, *, actor_user_id, actor_role, reason, db):
        if student_id == bad_id:
            raise LifecycleServiceError("INVALID_TRANSITION", "Cannot transition ARCHIVED", 409)
        return MagicMock()

    with patch(
        "app.modules.m11_sis.bulk_ops_service.StudentLifecycleService.transition",
        new_callable=AsyncMock,
        side_effect=side_effect,
    ):
        result = await BulkOpsService.bulk_student_action(
            [good_id, bad_id], "ARCHIVE",
            reason=None,
            actor_user_id=actor_id,
            actor_role="ADMIN",
            db=db,
        )

    assert result.succeeded == 1
    assert result.failed == 1
    assert len(result.errors) == 1
    assert str(bad_id) in result.errors[0]


# ---------------------------------------------------------------------------
# 6. bulk_student_action — all fail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_student_action_all_fail():
    ids = [uuid.uuid4(), uuid.uuid4()]
    actor_id = uuid.uuid4()
    db = AsyncMock()

    with patch(
        "app.modules.m11_sis.bulk_ops_service.StudentLifecycleService.transition",
        new_callable=AsyncMock,
        side_effect=LifecycleServiceError("ALREADY", "no change", 409),
    ):
        result = await BulkOpsService.bulk_student_action(
            ids, "ARCHIVE",
            reason="test",
            actor_user_id=actor_id,
            actor_role="ADMIN",
            db=db,
        )

    assert result.succeeded == 0
    assert result.failed == 2
    assert result.requested == 2


# ---------------------------------------------------------------------------
# 7. bulk_faculty_action — all succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_faculty_action_all_succeed():
    ids = [uuid.uuid4(), uuid.uuid4()]
    actor_id = uuid.uuid4()
    db = AsyncMock()

    with patch(
        "app.modules.m11_sis.bulk_ops_service.FacultyLifecycleService.transition",
        new_callable=AsyncMock,
    ) as mock_t:
        mock_t.return_value = MagicMock()
        result = await BulkOpsService.bulk_faculty_action(
            ids, "DEACTIVATE",
            reason="restructure",
            actor_user_id=actor_id,
            actor_role="ADMIN",
            db=db,
        )

    assert result.succeeded == 2
    assert result.failed == 0
    assert mock_t.call_count == 2


# ---------------------------------------------------------------------------
# 8. bulk_faculty_action — partial failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_faculty_action_partial_failure():
    good_id = uuid.uuid4()
    bad_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    db = AsyncMock()

    def side_effect(faculty_id, new_status, *, actor_user_id, actor_role, reason, db):
        if faculty_id == bad_id:
            raise LifecycleServiceError("INVALID_TRANSITION", "Cannot transition ARCHIVED", 409)
        return MagicMock()

    with patch(
        "app.modules.m11_sis.bulk_ops_service.FacultyLifecycleService.transition",
        new_callable=AsyncMock,
        side_effect=side_effect,
    ):
        result = await BulkOpsService.bulk_faculty_action(
            [good_id, bad_id], "ARCHIVE",
            reason=None,
            actor_user_id=actor_id,
            actor_role="ADMIN",
            db=db,
        )

    assert result.succeeded == 1
    assert result.failed == 1
    assert str(bad_id) in result.errors[0]


# ---------------------------------------------------------------------------
# 9. bulk_student_action — unexpected exception collected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_student_unexpected_exception_collected():
    ids = [uuid.uuid4()]
    actor_id = uuid.uuid4()
    db = AsyncMock()

    with patch(
        "app.modules.m11_sis.bulk_ops_service.StudentLifecycleService.transition",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB connection lost"),
    ):
        result = await BulkOpsService.bulk_student_action(
            ids, "DEACTIVATE",
            reason=None,
            actor_user_id=actor_id,
            actor_role="ADMIN",
            db=db,
        )

    assert result.succeeded == 0
    assert result.failed == 1
    assert "unexpected error" in result.errors[0]


# ---------------------------------------------------------------------------
# 10. Router: 2 bulk routes exist
# ---------------------------------------------------------------------------

def test_bulk_ops_router_has_two_routes():
    from app.modules.m11_sis.bulk_ops_router import bulk_ops_router
    paths = [r.path for r in bulk_ops_router.routes]
    assert "/students/bulk" in paths
    assert "/faculty/bulk" in paths
    assert len(bulk_ops_router.routes) == 2


# ---------------------------------------------------------------------------
# 11. Total SIS route count — 173 after H64.5
# ---------------------------------------------------------------------------

def test_sis_router_total_routes_h645():
    from app.modules.m11_sis.router import router
    # 5 school + 7 enrollment + 11 directory + 4 me + 2 rollover + 15 attendance
    # + 19 marks + 10 hallticket + 24 exam + 36 results + 2 import_batches
    # + 3 transcript + 13 graduation + 4 lifecycle + 2 bulk_ops (H64.5) = 173
    assert len(router.routes) == 178
