"""Unit tests for H64.6 — Enrollment Capacity Engine."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m11_sis.capacity_schemas import SectionCapacityOut, SetCapacityIn
from app.modules.m11_sis.capacity_service import CapacityError, CapacityService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_section(*, max_strength=None):
    s = MagicMock()
    s.id          = uuid.uuid4()
    s.name        = "Section A"
    s.semester_id = uuid.uuid4()
    s.max_strength = max_strength
    return s


# ---------------------------------------------------------------------------
# 1. SetCapacityIn schema
# ---------------------------------------------------------------------------

def test_set_capacity_in_valid():
    obj = SetCapacityIn(max_strength=60)
    assert obj.max_strength == 60


def test_set_capacity_in_null_removes_cap():
    obj = SetCapacityIn(max_strength=None)
    assert obj.max_strength is None


def test_set_capacity_in_zero_rejected():
    with pytest.raises(Exception):
        SetCapacityIn(max_strength=0)


def test_set_capacity_in_negative_rejected():
    with pytest.raises(Exception):
        SetCapacityIn(max_strength=-5)


# ---------------------------------------------------------------------------
# 2. SectionCapacityOut — no cap
# ---------------------------------------------------------------------------

def test_section_capacity_out_no_cap():
    out = SectionCapacityOut(
        section_id=uuid.uuid4(),
        section_name="A",
        semester_id=uuid.uuid4(),
        max_strength=None,
        enrolled=12,
        available=None,
        is_full=False,
        fill_pct=None,
    )
    assert out.is_full is False
    assert out.available is None
    assert out.fill_pct is None


def test_section_capacity_out_at_cap():
    out = SectionCapacityOut(
        section_id=uuid.uuid4(),
        section_name="B",
        semester_id=uuid.uuid4(),
        max_strength=30,
        enrolled=30,
        available=0,
        is_full=True,
        fill_pct=100.0,
    )
    assert out.is_full is True
    assert out.available == 0


def test_section_capacity_out_partial():
    out = SectionCapacityOut(
        section_id=uuid.uuid4(),
        section_name="C",
        semester_id=uuid.uuid4(),
        max_strength=40,
        enrolled=20,
        available=20,
        is_full=False,
        fill_pct=50.0,
    )
    assert out.fill_pct == 50.0
    assert out.available == 20


# ---------------------------------------------------------------------------
# 3. CapacityService.check_capacity — no cap set (passes silently)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_capacity_no_max_strength():
    db = AsyncMock()
    section = _make_section(max_strength=None)
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=section)))
    # Should not raise
    await CapacityService.check_capacity(section.id, db=db)


# ---------------------------------------------------------------------------
# 4. check_capacity — section not found (passes, no raise)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_capacity_section_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    # Missing section → no cap → no raise
    await CapacityService.check_capacity(uuid.uuid4(), db=db)


# ---------------------------------------------------------------------------
# 5. check_capacity — under cap (passes)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_capacity_under_cap():
    section = _make_section(max_strength=30)
    db = AsyncMock()
    results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=section)),
        MagicMock(scalar_one=MagicMock(return_value=25)),
    ]
    db.execute = AsyncMock(side_effect=results)
    await CapacityService.check_capacity(section.id, db=db)  # no raise


# ---------------------------------------------------------------------------
# 6. check_capacity — exactly at cap (raises 409)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_capacity_at_cap_raises():
    section = _make_section(max_strength=30)
    db = AsyncMock()
    results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=section)),
        MagicMock(scalar_one=MagicMock(return_value=30)),
    ]
    db.execute = AsyncMock(side_effect=results)
    with pytest.raises(CapacityError) as exc_info:
        await CapacityService.check_capacity(section.id, db=db)
    assert exc_info.value.code == "SECTION_AT_CAPACITY"
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# 7. check_capacity — over cap (raises 409)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_capacity_over_cap_raises():
    section = _make_section(max_strength=20)
    db = AsyncMock()
    results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=section)),
        MagicMock(scalar_one=MagicMock(return_value=21)),
    ]
    db.execute = AsyncMock(side_effect=results)
    with pytest.raises(CapacityError) as exc_info:
        await CapacityService.check_capacity(section.id, db=db)
    assert exc_info.value.code == "SECTION_AT_CAPACITY"


# ---------------------------------------------------------------------------
# 8. set_capacity — rejects cap below current enrollment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_capacity_below_enrollment_rejected():
    section = _make_section(max_strength=None)
    db = AsyncMock()
    results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=section)),
        MagicMock(scalar_one=MagicMock(return_value=35)),
    ]
    db.execute = AsyncMock(side_effect=results)
    with pytest.raises(CapacityError) as exc_info:
        await CapacityService.set_capacity(section.id, 30, db=db)
    assert exc_info.value.code == "BELOW_CURRENT_ENROLLMENT"
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# 9. set_capacity — section not found raises 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_capacity_section_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    with pytest.raises(CapacityError) as exc_info:
        await CapacityService.set_capacity(uuid.uuid4(), 40, db=db)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 10. get_section_capacity — section not found raises 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_section_capacity_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    with pytest.raises(CapacityError) as exc_info:
        await CapacityService.get_section_capacity(uuid.uuid4(), db=db)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 11. Capacity router has 3 routes
# ---------------------------------------------------------------------------

def test_capacity_router_has_three_routes():
    from app.modules.m11_sis.capacity_router import capacity_router
    paths = [r.path for r in capacity_router.routes]
    assert "/capacity/sections" in paths
    assert "/sections/{section_id}/capacity" in paths
    assert len(capacity_router.routes) == 3


# ---------------------------------------------------------------------------
# 12. Total SIS route count — 176 after H64.6
# ---------------------------------------------------------------------------

def test_sis_router_total_routes_h646():
    from app.modules.m11_sis.router import router
    # 5 school + 7 enrollment + 11 directory + 4 me + 2 rollover + 15 attendance
    # + 19 marks + 10 hallticket + 24 exam + 36 results + 2 import_batches
    # + 3 transcript + 13 graduation + 4 lifecycle + 2 bulk_ops + 3 capacity (H64.6) = 176
    assert len(router.routes) == 176
