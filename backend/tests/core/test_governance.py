"""Academic Governance — Phase A.

Covers the parts of the governance surface that the m01 tests do not: the
vocabulary endpoint (Board vs University Members) and the review queue.

The state machine itself (submit → approve+lock / return, separation of duties)
is covered in tests/modules/m01_program_advisor/, next to the curriculum it acts
on.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.core.governance import service as gov
from tests.conftest import SCHEMA_A, SLUG_A, _insert_tenant_user, make_tenant_headers

BASE = "/governance"


# Emails are unique per test: the tenant schema is shared across the tests in
# this module, so a fixed address would collide on the users.email unique index
# the second time a fixture runs.
@pytest_asyncio.fixture
async def board_user_a(test_tenant_a):
    email = f"gov_board_{uuid.uuid4().hex[:8]}@test.com"
    user = await _insert_tenant_user(SCHEMA_A, email, "Board1234!", "BOARD", "Gov Board")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def dean_user_a(test_tenant_a):
    email = f"gov_dean_{uuid.uuid4().hex[:8]}@test.com"
    user = await _insert_tenant_user(SCHEMA_A, email, "Dean1234!", "DEAN", "Gov Dean")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


async def _set_governance_type(tenant_id, value: str) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                text("UPDATE public.tenants SET governance_type = :v WHERE id = :t"),
                {"v": value, "t": str(tenant_id)},
            )


# ---------------------------------------------------------------------------
# Vocabulary — the same behaviour under two different names
# ---------------------------------------------------------------------------

async def test_default_governance_vocabulary_is_board(
    async_client, test_tenant_a, board_user_a,
):
    resp = await async_client.get(f"{BASE}/info", headers=make_tenant_headers(board_user_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["governance_type"] == "BOARD"
    assert body["body_label"]      == "Board"
    assert body["member_label"]    == "Board Member"


async def test_university_members_vocabulary(
    async_client, test_tenant_a, board_user_a,
):
    """The whole point of governance_type: a tenant that calls its authority
    'University Members' gets that wording everywhere, with identical behaviour."""
    await _set_governance_type(test_tenant_a["id"], "UNIVERSITY_MEMBERS")
    try:
        resp = await async_client.get(f"{BASE}/info", headers=make_tenant_headers(board_user_a))
        assert resp.status_code == 200
        body = resp.json()
        assert body["governance_type"] == "UNIVERSITY_MEMBERS"
        assert body["body_label"]      == "University Members"
        assert body["member_label"]    == "University Member"
    finally:
        await _set_governance_type(test_tenant_a["id"], "BOARD")


async def test_every_role_can_read_the_vocabulary(
    async_client, test_tenant_a, dean_user_a,
):
    # The Dean's UI has to say "Submit to the Board" too, so this is not gated.
    resp = await async_client.get(f"{BASE}/info", headers=make_tenant_headers(dean_user_a))
    assert resp.status_code == 200
    assert resp.json()["body_label"] == "Board"


# ---------------------------------------------------------------------------
# Review queue — governance only
# ---------------------------------------------------------------------------

async def test_queue_requires_governance_membership(
    async_client, test_tenant_a, dean_user_a, faculty_user_a,
):
    for user in (dean_user_a, faculty_user_a):
        resp = await async_client.get(f"{BASE}/queue", headers=make_tenant_headers(user))
        assert resp.status_code == 403, f"{user['role']} must not see the review queue"


async def test_board_sees_the_queue(async_client, test_tenant_a, board_user_a):
    resp = await async_client.get(f"{BASE}/queue", headers=make_tenant_headers(board_user_a))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"pending", "approved", "published"}


# ---------------------------------------------------------------------------
# Membership rules
# ---------------------------------------------------------------------------

async def test_faculty_with_board_grant_is_governance(test_tenant_a, faculty_user_a):
    """A real Board of Studies is staffed by senior professors. A FACULTY account
    holding an active BOARD grant exercises governance from that one account."""
    from app.core.auth.schemas import CurrentUser

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await db.execute(
                text(
                    "INSERT INTO faculty_role_grants "
                    "(id, faculty_user_id, role_code, is_active, granted_by) "
                    "VALUES (:id, :u, 'BOARD', true, :u)"
                ),
                {"id": str(uuid.uuid4()), "u": str(faculty_user_a["id"])},
            )

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            user = CurrentUser(
                user_id=faculty_user_a["id"],
                tenant_id=test_tenant_a["id"],
                schema_name=SCHEMA_A,
                role="FACULTY",
                email=faculty_user_a["email"],
            )
            assert await gov.acts_as_governance(user, db) is True
