"""Faculty responsibility-grant tests — ERP Onboarding Phase 1.5.

A single FACULTY account may hold multiple active grants simultaneously
(GUIDE / EVALUATOR / BOARD).  DEAN is a primary role, not a grant.
Integration tests against a real
PostgreSQL tenant schema; exercise grant / revoke / reactivate / list and the
soft-delete + multi-grant invariants.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.onboarding.faculty_role_grant_service import (
    FacultyRoleGrantService,
    FacultyRoleGrantServiceError,
)

_engine = create_async_engine(
    settings.DATABASE_URL, echo=False, connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _make_user(schema: str, name: str, role: str = "FACULTY") -> uuid.UUID:
    uid = uuid.uuid4()
    email = f"{name.lower().replace(' ', '.')}.{uid.hex[:6]}@test.edu"
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, :email, 'x', :role, :name, true)"
            ), {"id": str(uid), "email": email, "role": role, "name": name})
    return uid


async def _grant(schema, faculty, role_code, actor, actor_role="ADMIN"):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await FacultyRoleGrantService.grant(
                s, faculty_user_id=faculty, role_code=role_code, granted_by=actor,
                actor_role=actor_role,
            )


async def _revoke(schema, faculty, role_code, actor, actor_role="ADMIN"):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await FacultyRoleGrantService.revoke(
                s, faculty_user_id=faculty, role_code=role_code, revoked_by=actor,
                actor_role=actor_role,
            )


async def _list(schema, faculty, include_inactive=False):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await FacultyRoleGrantService.list_grants(
                s, faculty_user_id=faculty, include_inactive=include_inactive,
            )


async def _row_count(schema, faculty, role_code) -> tuple[int, int]:
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(text(
                "SELECT count(*) AS total, count(*) FILTER (WHERE is_active) AS active "
                "FROM faculty_role_grants WHERE faculty_user_id = :f AND role_code = :r"
            ), {"f": str(faculty), "r": role_code})
            m = r.mappings().one()
            return int(m["total"]), int(m["active"])


# ===========================================================================

@pytest.mark.asyncio
async def test_grant_responsibility(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Kavya")
    admin = await _make_user(schema, "Admin K", role="ADMIN")

    out = await _grant(schema, fac, "GUIDE", admin)
    assert out.is_active is True
    assert out.role_code == "GUIDE"
    assert out.reactivated is False
    assert out.faculty.full_name == "Dr Kavya"
    assert await _row_count(schema, fac, "GUIDE") == (1, 1)


@pytest.mark.asyncio
async def test_multiple_active_grants_simultaneously(test_tenant_a):
    """Kavya holds GUIDE and EVALUATOR at the same time — single account."""
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Kavya")
    admin = await _make_user(schema, "Admin K", role="ADMIN")

    await _grant(schema, fac, "GUIDE", admin)
    await _grant(schema, fac, "EVALUATOR", admin)

    listing = await _list(schema, fac)
    assert listing.total == 2
    assert {i.role_code for i in listing.items} == {"GUIDE", "EVALUATOR"}


@pytest.mark.asyncio
async def test_duplicate_grant_prevented(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Arun")
    admin = await _make_user(schema, "Admin A", role="ADMIN")

    await _grant(schema, fac, "EVALUATOR", admin)
    with pytest.raises(FacultyRoleGrantServiceError) as exc:
        await _grant(schema, fac, "EVALUATOR", admin)
    assert exc.value.code == "DUPLICATE_GRANT"
    assert await _row_count(schema, fac, "EVALUATOR") == (1, 1)


@pytest.mark.asyncio
async def test_revoke_and_reactivate_reuses_row(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Meena")
    admin = await _make_user(schema, "Admin M", role="ADMIN")

    first = await _grant(schema, fac, "BOARD", admin)
    rev = await _revoke(schema, fac, "BOARD", admin)
    assert rev.is_active is False and rev.revoked_by == admin and rev.revoked_at is not None

    again = await _grant(schema, fac, "BOARD", admin)
    assert again.reactivated is True
    assert again.is_active is True
    assert again.id == first.id            # same row reused — no duplicate history
    assert again.revoked_at is None
    assert await _row_count(schema, fac, "BOARD") == (1, 1)


@pytest.mark.asyncio
async def test_revoke_without_active_raises(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr None")
    admin = await _make_user(schema, "Admin N", role="ADMIN")
    with pytest.raises(FacultyRoleGrantServiceError) as exc:
        await _revoke(schema, fac, "GUIDE", admin)
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_role_code_rejected(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr X")
    admin = await _make_user(schema, "Admin X", role="ADMIN")
    # DEAN is a primary role, not a grantable responsibility.
    for bad in ("HOD", "PLACEMENT", "STUDENT", "ADMIN", "DEAN"):
        with pytest.raises(FacultyRoleGrantServiceError) as exc:
            await _grant(schema, fac, bad, admin)
        assert exc.value.code == "INVALID_ROLE_CODE"


@pytest.mark.asyncio
async def test_grant_rejects_non_faculty(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    student = await _make_user(schema, "Stud One", role="STUDENT")
    admin = await _make_user(schema, "Admin S", role="ADMIN")
    with pytest.raises(FacultyRoleGrantServiceError) as exc:
        await _grant(schema, student, "GUIDE", admin)
    assert exc.value.code == "INVALID_ROLE"


@pytest.mark.asyncio
async def test_soft_delete_persists_row(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Soft")
    admin = await _make_user(schema, "Admin Soft", role="ADMIN")
    await _grant(schema, fac, "GUIDE", admin)
    await _revoke(schema, fac, "GUIDE", admin)
    total, active = await _row_count(schema, fac, "GUIDE")
    assert (total, active) == (1, 0)        # row kept, inactive

    active_list = await _list(schema, fac)
    assert active_list.total == 0
    all_list = await _list(schema, fac, include_inactive=True)
    assert all_list.total == 1


# ===========================================================================
# Governance: who may grant/revoke which responsibility
# ===========================================================================

@pytest.mark.asyncio
async def test_dean_can_grant_guide_and_evaluator(test_tenant_a):
    """A Dean may assign GUIDE and EVALUATOR inside their department."""
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Aishu")
    dean = await _make_user(schema, "Dean D", role="DEAN")

    g = await _grant(schema, fac, "GUIDE", dean, actor_role="DEAN")
    e = await _grant(schema, fac, "EVALUATOR", dean, actor_role="DEAN")
    assert g.is_active and e.is_active
    assert {i.role_code for i in (await _list(schema, fac)).items} == {"GUIDE", "EVALUATOR"}

    # Dean may also revoke what it can grant.
    rev = await _revoke(schema, fac, "GUIDE", dean, actor_role="DEAN")
    assert rev.is_active is False


@pytest.mark.asyncio
async def test_dean_cannot_grant_board(test_tenant_a):
    """BOARD is ADMIN-only — a Dean is forbidden (403)."""
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Aishu")
    dean = await _make_user(schema, "Dean D", role="DEAN")

    with pytest.raises(FacultyRoleGrantServiceError) as exc:
        await _grant(schema, fac, "BOARD", dean, actor_role="DEAN")
    assert exc.value.code == "FORBIDDEN"
    assert exc.value.status_code == 403
    assert (await _list(schema, fac)).total == 0


@pytest.mark.asyncio
async def test_dean_is_not_a_grantable_responsibility(test_tenant_a):
    """DEAN is a primary role — granting it is rejected as an invalid code,
    for ADMIN and DEAN alike."""
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Aishu")
    admin = await _make_user(schema, "Admin A", role="ADMIN")
    dean = await _make_user(schema, "Dean D", role="DEAN")
    for actor, actor_role in ((admin, "ADMIN"), (dean, "DEAN")):
        with pytest.raises(FacultyRoleGrantServiceError) as exc:
            await _grant(schema, fac, "DEAN", actor, actor_role=actor_role)
        assert exc.value.code == "INVALID_ROLE_CODE"
    assert (await _list(schema, fac)).total == 0


@pytest.mark.asyncio
async def test_dean_cannot_revoke_board(test_tenant_a):
    """A Dean cannot revoke a BOARD grant an Admin created."""
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Aishu")
    admin = await _make_user(schema, "Admin A", role="ADMIN")
    dean = await _make_user(schema, "Dean D", role="DEAN")

    await _grant(schema, fac, "BOARD", admin)  # admin grants BOARD
    with pytest.raises(FacultyRoleGrantServiceError) as exc:
        await _revoke(schema, fac, "BOARD", dean, actor_role="DEAN")
    assert exc.value.code == "FORBIDDEN"
    assert await _row_count(schema, fac, "BOARD") == (1, 1)  # still active


@pytest.mark.asyncio
async def test_admin_can_grant_all_responsibilities(test_tenant_a):
    """ADMIN may grant every grantable responsibility, including BOARD."""
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Full")
    admin = await _make_user(schema, "Admin F", role="ADMIN")

    for rc in ("GUIDE", "EVALUATOR", "BOARD"):
        out = await _grant(schema, fac, rc, admin, actor_role="ADMIN")
        assert out.is_active and out.role_code == rc
    assert {i.role_code for i in (await _list(schema, fac)).items} == {
        "GUIDE", "EVALUATOR", "BOARD",
    }


@pytest.mark.asyncio
async def test_unauthorized_actor_role_forbidden(test_tenant_a):
    """A non-admin / non-dean actor cannot manage responsibilities at all."""
    schema = test_tenant_a["schema_name"]
    fac = await _make_user(schema, "Dr Z")
    actor = await _make_user(schema, "Faculty Z", role="FACULTY")
    with pytest.raises(FacultyRoleGrantServiceError) as exc:
        await _grant(schema, fac, "GUIDE", actor, actor_role="FACULTY")
    assert exc.value.code == "FORBIDDEN"
