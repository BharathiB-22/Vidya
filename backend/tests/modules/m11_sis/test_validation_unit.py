"""Unit tests for H64.8 — SIS Validation Report."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.m11_sis.validation_schemas import (
    CheckResult,
    ValidationItem,
    ValidationReportOut,
)
from app.modules.m11_sis.validation_service import MAX_ITEMS, ValidationService


# ---------------------------------------------------------------------------
# 1. Schema validation
# ---------------------------------------------------------------------------

def test_validation_item_fields():
    item = ValidationItem(id=uuid.uuid4(), detail="Alice (a@b.com)")
    assert "Alice" in item.detail


def test_check_result_severity_values():
    for sev in ("ERROR", "WARNING", "INFO"):
        cr = CheckResult(
            check_id="x", label="X", description="d", severity=sev,
            count=0, items=[],
        )
        assert cr.severity == sev


def test_validation_report_out_empty():
    out = ValidationReportOut(
        generated_at=datetime.now(timezone.utc),
        total_issues=0,
        checks=[],
    )
    assert out.total_issues == 0
    assert out.checks == []


def test_check_result_items_list():
    items = [ValidationItem(id=uuid.uuid4(), detail=f"User {i}") for i in range(3)]
    cr = CheckResult(check_id="c", label="C", description="d", severity="INFO", count=3, items=items)
    assert cr.count == 3
    assert len(cr.items) == 3


# ---------------------------------------------------------------------------
# 2. MAX_ITEMS constant
# ---------------------------------------------------------------------------

def test_max_items_is_positive():
    assert MAX_ITEMS > 0
    assert MAX_ITEMS <= 100


# ---------------------------------------------------------------------------
# 3. generate_report returns 7 checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_report_returns_seven_checks():
    db = AsyncMock()
    empty = MagicMock()
    empty.all.return_value = []
    db.execute = AsyncMock(return_value=empty)

    report = await ValidationService.generate_report(db=db)
    assert len(report.checks) == 7


# ---------------------------------------------------------------------------
# 4. check IDs are unique and all expected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_ids_are_correct():
    db = AsyncMock()
    empty = MagicMock()
    empty.all.return_value = []
    db.execute = AsyncMock(return_value=empty)

    report = await ValidationService.generate_report(db=db)
    ids = {c.check_id for c in report.checks}
    expected = {
        "students_without_profile",
        "faculty_without_profile",
        "students_without_usn",
        "students_not_enrolled",
        "enrolled_inactive_section",
        "sections_over_capacity",
        "lifecycle_is_active_mismatch",
    }
    assert ids == expected


# ---------------------------------------------------------------------------
# 5. total_issues = sum of all check counts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_total_issues_is_sum_of_check_counts():
    db = AsyncMock()
    empty = MagicMock()
    empty.all.return_value = []
    db.execute = AsyncMock(return_value=empty)

    report = await ValidationService.generate_report(db=db)
    assert report.total_issues == sum(c.count for c in report.checks)


# ---------------------------------------------------------------------------
# 6. Zero issues when DB returns empty rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_issues_on_clean_data():
    db = AsyncMock()
    empty = MagicMock()
    empty.all.return_value = []
    db.execute = AsyncMock(return_value=empty)

    report = await ValidationService.generate_report(db=db)
    assert report.total_issues == 0
    for check in report.checks:
        assert check.count == 0
        assert check.items == []


# ---------------------------------------------------------------------------
# 7. generated_at is timezone-aware
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generated_at_is_utc():
    db = AsyncMock()
    empty = MagicMock()
    empty.all.return_value = []
    db.execute = AsyncMock(return_value=empty)

    report = await ValidationService.generate_report(db=db)
    assert report.generated_at.tzinfo is not None


# ---------------------------------------------------------------------------
# 8. items populated from DB rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_items_populated():
    db = AsyncMock()
    uid = uuid.uuid4()

    class _Row:
        id = uid
        full_name = "Alice Smith"
        email = "alice@example.com"
        user_id = uid
        lifecycle_status = "ACTIVE"

    populated = MagicMock()
    populated.all.return_value = [_Row()]
    empty = MagicMock()
    empty.all.return_value = []

    call_count = 0

    async def side_effect(_stmt):
        nonlocal call_count
        call_count += 1
        # First call = students_without_profile → return 1 row
        if call_count == 1:
            return populated
        return empty

    db.execute = AsyncMock(side_effect=side_effect)

    report = await ValidationService.generate_report(db=db)
    without_profile = next(c for c in report.checks if c.check_id == "students_without_profile")
    assert without_profile.count == 1
    assert str(uid) in str(without_profile.items[0].id)


# ---------------------------------------------------------------------------
# 9. Severity levels present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_severity_levels_include_all_three():
    db = AsyncMock()
    empty = MagicMock()
    empty.all.return_value = []
    db.execute = AsyncMock(return_value=empty)

    report = await ValidationService.generate_report(db=db)
    severities = {c.severity for c in report.checks}
    # We expect at least ERROR and WARNING and INFO
    assert "ERROR" in severities
    assert "WARNING" in severities
    assert "INFO" in severities


# ---------------------------------------------------------------------------
# 10. Validation router has 1 route
# ---------------------------------------------------------------------------

def test_validation_router_has_one_route():
    from app.modules.m11_sis.validation_router import validation_router
    paths = [r.path for r in validation_router.routes]
    assert "/validation/report" in paths
    assert len(validation_router.routes) == 1


# ---------------------------------------------------------------------------
# 11. Total SIS route count — 178 after H64.8
# ---------------------------------------------------------------------------

def test_sis_router_total_routes_h648():
    from app.modules.m11_sis.router import router
    # 177 (H64.7) + 1 validation = 178
    assert len(router.routes) == 178
