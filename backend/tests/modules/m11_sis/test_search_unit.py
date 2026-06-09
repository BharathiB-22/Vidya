"""Unit tests for H64.7 — Global Search."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m11_sis.search_schemas import (
    CourseHit,
    FacultyHit,
    SearchResultsOut,
    SectionHit,
    StudentHit,
)
from app.modules.m11_sis.search_service import MIN_LEN, PER_KIND, global_search


# ---------------------------------------------------------------------------
# 1. Schema defaults
# ---------------------------------------------------------------------------

def test_search_results_out_empty():
    out = SearchResultsOut(query="x", students=[], faculty=[], sections=[], courses=[])
    assert out.students == []
    assert out.query == "x"


def test_student_hit_fields():
    h = StudentHit(id=uuid.uuid4(), full_name="Alice", email="a@b.com", usn="USN001", is_active=True)
    assert h.full_name == "Alice"


def test_faculty_hit_fields():
    h = FacultyHit(id=uuid.uuid4(), full_name="Bob", email="b@c.com", employee_id="EMP01", is_active=True)
    assert h.employee_id == "EMP01"


def test_section_hit_fields():
    h = SectionHit(id=uuid.uuid4(), name="CS-A", is_active=True)
    assert h.name == "CS-A"


def test_course_hit_fields():
    h = CourseHit(id=uuid.uuid4(), code="CS101", title="Intro to CS")
    assert h.code == "CS101"


# ---------------------------------------------------------------------------
# 2. Constants
# ---------------------------------------------------------------------------

def test_per_kind_is_positive():
    assert PER_KIND > 0


def test_min_len_is_two():
    assert MIN_LEN == 2


# ---------------------------------------------------------------------------
# 3. Short query returns empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_short_query_returns_empty():
    db = AsyncMock()
    result = await global_search("a", actor_role="ADMIN", db=db)
    assert result.students == []
    assert result.faculty == []
    assert result.sections == []
    assert result.courses == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_empty_query_returns_empty():
    db = AsyncMock()
    result = await global_search("", actor_role="ADMIN", db=db)
    assert result.query == ""
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# 4. STUDENT role sees only sections + courses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_student_role_skips_students_and_faculty():
    db = AsyncMock()
    # Return empty scalars for sections and courses
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await global_search("math", actor_role="STUDENT", db=db)
    assert result.students == []
    assert result.faculty == []
    # execute called twice: sections + courses
    assert db.execute.call_count == 2


# ---------------------------------------------------------------------------
# 5. FACULTY role sees students + sections + courses (not faculty)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_faculty_role_skips_faculty_search():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await global_search("john", actor_role="FACULTY", db=db)
    assert result.faculty == []
    # execute called 3 times: students + sections + courses
    assert db.execute.call_count == 3


# ---------------------------------------------------------------------------
# 6. ADMIN / DEAN sees all four categories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_searches_all_four_categories():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await global_search("test", actor_role="ADMIN", db=db)
    assert db.execute.call_count == 4


@pytest.mark.asyncio
async def test_dean_searches_all_four_categories():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await global_search("test", actor_role="DEAN", db=db)
    assert db.execute.call_count == 4


# ---------------------------------------------------------------------------
# 7. Search router has exactly 1 route
# ---------------------------------------------------------------------------

def test_search_router_has_one_route():
    from app.modules.m11_sis.search_router import search_router
    paths = [r.path for r in search_router.routes]
    assert "/search" in paths
    assert len(search_router.routes) == 1


# ---------------------------------------------------------------------------
# 8. Total SIS route count — 177 after H64.7
# ---------------------------------------------------------------------------

def test_sis_router_total_routes_h647():
    from app.modules.m11_sis.router import router
    # 176 (H64.6) + 1 search = 177
    assert len(router.routes) == 177
