"""H05-07: RBAC hardening matrix — integration tests.

Covers:
  - BUG-H04-03 fix: missing Authorization → 401 (not 422)
  - Malformed Authorization header variants
  - Missing / unknown / inactive X-Tenant-Slug
  - Schema injection and path traversal via X-Tenant-Slug
  - Schema injection via JWT claims (regex guard)
  - Cross-tenant JWT mismatch → 403 TENANT_MISMATCH
  - Role deny matrix (representative sample across all modules)
  - SUPER_ADMIN boundary rules (platform-only, explicit tenant context)
  - Inactive user rejection
  - Forged JWT rejection
"""
import uuid
from datetime import timedelta

import pytest
from jose import jwt as jose_jwt
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.auth.security import create_access_token, hash_password
from tests.conftest import (
    SCHEMA_A,
    SCHEMA_B,
    SLUG_A,
    SLUG_B,
    make_platform_headers,
    make_tenant_headers,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Local DB session (mirrors conftest pattern)
# ---------------------------------------------------------------------------

_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

_INACTIVE_SCHEMA = "tenant_test_inactive"
_INACTIVE_SLUG   = "test-tenant-inactive"


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

async def _insert_user(schema_name: str, email: str, role: str, is_active: bool = True) -> dict:
    user_id = uuid.uuid4()
    pw_hash = hash_password("Test1234!")
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
            await session.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                    "VALUES (:id, :email, :hash, :role, :name, :active)"
                ),
                {
                    "id": str(user_id),
                    "email": email,
                    "hash": pw_hash,
                    "role": role,
                    "name": f"{role.title()} User",
                    "active": is_active,
                },
            )
    return {"id": user_id, "email": email, "role": role}


# ---------------------------------------------------------------------------
# Extra role fixtures (board, dean, guide) for tenant_a
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def board_user_a(test_tenant_a):
    u = await _insert_user(SCHEMA_A, f"board_a_{uuid.uuid4().hex[:6]}@test.com", "BOARD")
    yield {**u, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def dean_user_a(test_tenant_a):
    u = await _insert_user(SCHEMA_A, f"dean_a_{uuid.uuid4().hex[:6]}@test.com", "DEAN")
    yield {**u, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def guide_user_a(test_tenant_a):
    u = await _insert_user(SCHEMA_A, f"guide_a_{uuid.uuid4().hex[:6]}@test.com", "GUIDE")
    yield {**u, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def inactive_user_a(test_tenant_a):
    u = await _insert_user(
        SCHEMA_A,
        f"inactive_a_{uuid.uuid4().hex[:6]}@test.com",
        "FACULTY",
        is_active=False,
    )
    yield {**u, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def inactive_tenant(setup_public_schema):
    """A tenant that exists in the DB but has is_active=False."""
    import subprocess, sys, os
    from pathlib import Path
    _BACKEND_DIR = str(Path(__file__).parent.parent.parent.parent)
    env = {**os.environ, "ALEMBIC_TARGET": "tenant", "TENANT_SCHEMA": _INACTIVE_SCHEMA}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR, env=env, check=True, capture_output=True,
    )
    t_id = uuid.uuid4()
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO public.tenants (id, slug, name, schema_name, is_active) "
                    "VALUES (:id, :slug, :name, :schema, false) "
                    "ON CONFLICT (slug) DO UPDATE SET is_active = false"
                ),
                {"id": str(t_id), "slug": _INACTIVE_SLUG, "name": "Inactive Tenant",
                 "schema": _INACTIVE_SCHEMA},
            )
    yield {"id": t_id, "slug": _INACTIVE_SLUG, "schema_name": _INACTIVE_SCHEMA}
    async with _Session() as session:
        async with session.begin():
            # Do not DELETE from public.tenants — audit_logs FK cascade would
            # attempt UPDATE on audit_logs which the H05-06 trigger blocks.
            # Leaving the record as is_active=false is equivalent for test isolation.
            await session.execute(
                text("UPDATE public.tenants SET is_active = false WHERE slug = :slug"),
                {"slug": _INACTIVE_SLUG},
            )
            await session.execute(
                text(f"DROP SCHEMA IF EXISTS {_INACTIVE_SCHEMA} CASCADE")
            )


# ===========================================================================
# Category 1 — Unauthenticated behavior (BUG-H04-03 fix)
# ===========================================================================

async def test_missing_auth_on_me_returns_401(async_client, test_tenant_a):
    """GET /auth/me with no Authorization header must return 401, not 422."""
    resp = await async_client.get("/auth/me", headers={"X-Tenant-Slug": SLUG_A})
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


async def test_missing_auth_on_programs_returns_401(async_client, test_tenant_a):
    """GET /programs with no Authorization must return 401, not 422."""
    resp = await async_client.get("/programs", headers={"X-Tenant-Slug": SLUG_A})
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


async def test_missing_auth_on_audit_log_returns_401(async_client):
    """GET /audit-logs with no Authorization must return 401, not 422."""
    resp = await async_client.get("/audit-logs")
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


async def test_missing_auth_on_admin_users_returns_401(async_client, test_tenant_a):
    """GET /admin/users with no Authorization must return 401, not 422."""
    resp = await async_client.get("/admin/users", headers={"X-Tenant-Slug": SLUG_A})
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


# ===========================================================================
# Category 2 — Malformed Authorization header
# ===========================================================================

async def test_bearer_prefix_missing_returns_401(async_client, test_tenant_a):
    """Authorization without 'Bearer ' prefix → 401."""
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": "Token sometoken", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


async def test_basic_auth_returns_401(async_client, test_tenant_a):
    """HTTP Basic auth is not accepted — must return 401."""
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": "Basic dXNlcjpwYXNz", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


async def test_bearer_with_empty_token_returns_401(async_client, test_tenant_a):
    """'Bearer ' with nothing after the space — empty token string → 401."""
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer ", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401


async def test_malformed_jwt_segments_returns_401(async_client, test_tenant_a):
    """JWT with wrong number of segments is rejected → 401."""
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not.a.valid.jwt.payload", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


async def test_jwt_missing_sub_claim_rejected(async_client, test_tenant_a):
    """JWT without 'sub' claim cannot be decoded into a user → 401."""
    bad_token = jose_jwt.encode(
        {"role": "ADMIN", "schema_name": SCHEMA_A},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {bad_token}", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401


async def test_expired_jwt_returns_401(async_client, test_tenant_a, faculty_user_a):
    """An expired JWT must be rejected → 401."""
    expired = create_access_token(
        {
            "sub": str(faculty_user_a["id"]),
            "tenant_id": str(faculty_user_a["tenant_id"]),
            "schema_name": SCHEMA_A,
            "role": "FACULTY",
            "email": faculty_user_a["email"],
        },
        expires_delta=timedelta(seconds=-1),
    )
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired}", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401


# ===========================================================================
# Category 3 — Missing / unknown / inactive X-Tenant-Slug
# ===========================================================================

async def test_missing_tenant_slug_on_login_returns_422(async_client):
    """POST /auth/login without X-Tenant-Slug must return 422 (required header)."""
    resp = await async_client.post(
        "/auth/login",
        json={"email": "anyone@test.com", "password": "password123"},
    )
    assert resp.status_code == 422


async def test_unknown_tenant_slug_returns_404(async_client, faculty_user_a):
    """Valid JWT but unknown X-Tenant-Slug → 404 TENANT_NOT_FOUND."""
    headers = make_tenant_headers(faculty_user_a)
    headers["X-Tenant-Slug"] = f"slug-does-not-exist-{uuid.uuid4().hex[:8]}"
    resp = await async_client.get("/programs", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"] == "TENANT_NOT_FOUND"


async def test_inactive_tenant_slug_returns_403(async_client, inactive_tenant, faculty_user_a):
    """Valid JWT but inactive tenant → 403 TENANT_INACTIVE."""
    headers = make_tenant_headers(faculty_user_a)
    headers["X-Tenant-Slug"] = _INACTIVE_SLUG
    resp = await async_client.get("/programs", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"] == "TENANT_INACTIVE"


# ===========================================================================
# Category 4 — Schema injection / traversal via X-Tenant-Slug
# ===========================================================================

@pytest.mark.parametrize("slug", [
    "'; DROP TABLE tenants; --",
    "../public",
    "tenant; DROP TABLE users; --",
    "test tenant",         # whitespace
    "tenant\x00null",     # null byte
    "TENANT_A",            # uppercase — no tenant with this slug
    "",                    # empty string
])
async def test_injection_in_tenant_slug_returns_404(async_client, test_tenant_a, faculty_user_a, slug):
    """Injection/traversal attempts in X-Tenant-Slug are rejected via 404.

    The slug is looked up in the DB with a parameterised query; no matching
    tenant is found, so resolve_tenant raises 404 before any schema is touched.
    """
    headers = make_tenant_headers(faculty_user_a)
    headers["X-Tenant-Slug"] = slug
    resp = await async_client.get("/programs", headers=headers)
    # Empty string causes 422 (FastAPI validates non-empty str header);
    # all others cause 404 (tenant not found).
    assert resp.status_code in (404, 422), (
        f"Expected 404 or 422 for slug={slug!r}, got {resp.status_code}"
    )


# ===========================================================================
# Category 5 — Schema injection via JWT claims (regex guard in get_current_user)
# ===========================================================================

@pytest.mark.parametrize("bad_schema", [
    "public; DROP TABLE users; --",
    "../public",
    "tenant a b",           # whitespace
    "TENANT_TEST_A",        # uppercase (must be lowercase)
    "tenant-with-hyphens",  # hyphens not in [a-z0-9_]
    "; DROP TABLE tenants",
])
async def test_schema_injection_in_jwt_claims_rejected(async_client, test_tenant_a, bad_schema):
    """JWT with a schema_name that fails the regex guard → 401 UNAUTHORIZED.

    The regex r'^tenant_[a-z0-9_]+$' is the only line of defence before the
    schema value is used in a SET search_path statement.
    """
    bad_token = create_access_token({
        "sub": str(uuid.uuid4()),
        "tenant_id": str(test_tenant_a["id"]),
        "schema_name": bad_schema,
        "role": "ADMIN",
        "email": "attacker@evil.com",
    })
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {bad_token}", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


@pytest.mark.parametrize("valid_schema", [
    "tenant_abc",
    "tenant_abc123",
    "tenant_test_a",
    "tenant_org_unit_01",
])
async def test_valid_schema_name_pattern_accepted(async_client, test_tenant_a, valid_schema):
    """Schema names matching the regex pass the guard (user lookup may then fail with 401,
    but the schema name itself is accepted — the regex is not the rejection cause)."""
    bad_token = create_access_token({
        "sub": str(uuid.uuid4()),
        "tenant_id": str(test_tenant_a["id"]),
        "schema_name": valid_schema,
        "role": "ADMIN",
        "email": "tester@test.com",
    })
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {bad_token}", "X-Tenant-Slug": SLUG_A},
    )
    # The schema name passes the regex guard, so the rejection reason will be
    # either 401 (user not found in that schema) or 403 (TENANT_MISMATCH — the
    # JWT schema differs from the slug's schema).  Either is fine; the important
    # thing is that it was NOT rejected by the regex itself (which returns 401
    # with message "Invalid token claims").
    assert resp.status_code in (401, 403)
    body = resp.json()
    assert not (resp.status_code == 401 and body.get("message") == "Invalid token claims"), (
        f"Schema {valid_schema!r} should pass the regex guard but was rejected by it"
    )


# ===========================================================================
# Category 6 — Cross-tenant JWT mismatch
# ===========================================================================

async def test_tenant_a_jwt_with_tenant_b_slug_returns_403(
    async_client, test_tenant_a, test_tenant_b, faculty_user_a
):
    """JWT scoped to tenant_a + X-Tenant-Slug for tenant_b → 403 TENANT_MISMATCH."""
    headers = make_tenant_headers(faculty_user_a)  # schema=tenant_a, slug=tenant_a
    headers["X-Tenant-Slug"] = SLUG_B             # override to tenant_b
    resp = await async_client.get("/programs", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"] == "TENANT_MISMATCH"


async def test_tenant_b_jwt_with_tenant_a_slug_returns_403(
    async_client, test_tenant_a, test_tenant_b, faculty_user_b
):
    """JWT scoped to tenant_b + X-Tenant-Slug for tenant_a → 403 TENANT_MISMATCH."""
    headers = make_tenant_headers(faculty_user_b)  # schema=tenant_b, slug=tenant_b
    headers["X-Tenant-Slug"] = SLUG_A              # override to tenant_a
    resp = await async_client.get("/programs", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"] == "TENANT_MISMATCH"


async def test_correct_tenant_match_succeeds(async_client, test_tenant_a, admin_user_a):
    """JWT and X-Tenant-Slug for the same tenant → 200 (no mismatch)."""
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.get("/programs", headers=headers)
    assert resp.status_code == 200


async def test_randomized_cross_tenant_mismatch(
    async_client, test_tenant_a, test_tenant_b, faculty_user_a, faculty_user_b
):
    """Repeated cross-tenant attempts all return 403 TENANT_MISMATCH."""
    combos = [
        (faculty_user_a, SLUG_B),
        (faculty_user_b, SLUG_A),
        (faculty_user_a, SLUG_B),
        (faculty_user_b, SLUG_A),
        (faculty_user_a, SLUG_B),
    ]
    for user, wrong_slug in combos:
        headers = make_tenant_headers(user)
        headers["X-Tenant-Slug"] = wrong_slug
        resp = await async_client.get("/programs", headers=headers)
        assert resp.status_code == 403, (
            f"Expected 403 for user={user['schema_name']!r} + slug={wrong_slug!r}, "
            f"got {resp.status_code}"
        )
        assert resp.json()["error"] == "TENANT_MISMATCH"


# ===========================================================================
# Category 7 — Role deny matrix
# ===========================================================================

async def test_student_cannot_list_programs(async_client, test_tenant_a, student_user_a):
    """STUDENT is not in M01 _READ (ADMIN+DEAN+FACULTY) → 403."""
    resp = await async_client.get("/programs", headers=make_tenant_headers(student_user_a))
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_faculty_cannot_create_program(async_client, test_tenant_a, faculty_user_a):
    """FACULTY is not in M01 _WRITE (ADMIN+DEAN) → 403 on POST /programs."""
    resp = await async_client.post(
        "/programs",
        json={
            "title": "Test Program",
            "degree_type": "B.Tech",
            "department": "CSE",
            "duration_years": 4,
            "total_credits": 160,
            "regulation_year": 2024,
        },
        headers=make_tenant_headers(faculty_user_a),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_faculty_cannot_approve_program(async_client, test_tenant_a, faculty_user_a):
    """FACULTY is not in M01 _DEAN → 403 on approve endpoint."""
    fake_id = uuid.uuid4()
    resp = await async_client.post(
        f"/programs/{fake_id}/approve",
        json={"comment": "Looks good"},
        headers=make_tenant_headers(faculty_user_a),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_board_cannot_list_programs(async_client, test_tenant_a, board_user_a):
    """BOARD is not in M01 _READ (ADMIN+DEAN+FACULTY) → 403."""
    resp = await async_client.get("/programs", headers=make_tenant_headers(board_user_a))
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_guide_cannot_list_programs(async_client, test_tenant_a, guide_user_a):
    """GUIDE is not in M01 _READ → 403."""
    resp = await async_client.get("/programs", headers=make_tenant_headers(guide_user_a))
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_student_cannot_list_syllabi(async_client, test_tenant_a, student_user_a):
    """STUDENT is not in M02 _READ (ADMIN+DEAN+FACULTY) → 403."""
    resp = await async_client.get(
        "/syllabi",
        params={"course_id": str(uuid.uuid4())},
        headers=make_tenant_headers(student_user_a),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_student_cannot_list_admin_users(async_client, test_tenant_a, student_user_a):
    """STUDENT is not ADMIN → 403 on /admin/users."""
    resp = await async_client.get("/admin/users", headers=make_tenant_headers(student_user_a))
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_faculty_cannot_list_admin_users(async_client, test_tenant_a, faculty_user_a):
    """FACULTY is not ADMIN → 403 on /admin/users."""
    resp = await async_client.get("/admin/users", headers=make_tenant_headers(faculty_user_a))
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_dean_cannot_access_tenants_endpoint(async_client, test_tenant_a, dean_user_a):
    """DEAN is a tenant user (not SUPER_ADMIN) → 403 on /tenants."""
    resp = await async_client.get("/tenants", headers=make_tenant_headers(dean_user_a))
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_faculty_cannot_lock_syllabus(async_client, test_tenant_a, faculty_user_a):
    """FACULTY is not in M02 _LOCK (ADMIN+DEAN) → 403."""
    fake_id = uuid.uuid4()
    resp = await async_client.post(
        f"/syllabi/{fake_id}/lock",
        json={"comment": "Locking semester"},
        headers=make_tenant_headers(faculty_user_a),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_student_cannot_trigger_curation(async_client, test_tenant_a, student_user_a):
    """STUDENT is not in M05 _WRITE (ADMIN+FACULTY) → 403 on /learning-packages/curate."""
    resp = await async_client.post(
        "/learning-packages/curate",
        json={
            "syllabus_id": str(uuid.uuid4()),
            "unit_number": 1,
            "top_n": 5,
        },
        headers=make_tenant_headers(student_user_a),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_faculty_cannot_run_bell_curve(async_client, test_tenant_a, faculty_user_a):
    """FACULTY is not in M10 _BOARD_ADMIN (BOARD+ADMIN) → 403 on bell-curve trigger."""
    resp = await async_client.post(
        "/bell-curve/analyses",
        json={"paper_id": str(uuid.uuid4()), "method": "z_score", "cap_percentile": 95.0},
        headers=make_tenant_headers(faculty_user_a),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_student_cannot_view_bell_curve(async_client, test_tenant_a, student_user_a):
    """STUDENT is not in M10 _READ (BOARD+ADMIN+DEAN) → 403."""
    resp = await async_client.get(
        "/bell-curve/analyses",
        headers=make_tenant_headers(student_user_a),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


# ===========================================================================
# Category 8 — SUPER_ADMIN boundary rules
# ===========================================================================

async def test_super_admin_on_tenant_me_returns_403(async_client, test_platform_user):
    """SUPER_ADMIN calling GET /auth/me → 403 (must use /platform/auth/me).

    SUPER_ADMIN is platform-scoped by default; /auth/me is for tenant users only.
    """
    resp = await async_client.get("/auth/me", headers=make_platform_headers(test_platform_user))
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_super_admin_can_access_platform_me(async_client, test_platform_user):
    """SUPER_ADMIN on /platform/auth/me → 200."""
    resp = await async_client.get(
        "/platform/auth/me", headers=make_platform_headers(test_platform_user)
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "SUPER_ADMIN"


async def test_super_admin_can_list_tenants(async_client, test_platform_user, test_tenant_a):
    """SUPER_ADMIN on /tenants → 200 (platform management endpoint)."""
    resp = await async_client.get("/tenants", headers=make_platform_headers(test_platform_user))
    assert resp.status_code == 200


async def test_super_admin_on_admin_users_without_tenant_slug_returns_403(
    async_client, test_platform_user
):
    """SUPER_ADMIN on /admin/users without X-Tenant-Slug → 403.

    _get_admin_db detects is_super_admin=True and raises 403 explicitly before
    any tenant resolution occurs. SUPER_ADMIN must use tenant ADMIN credentials
    for /admin/ routes; there is no SUPER_ADMIN path through these endpoints.
    """
    resp = await async_client.get("/admin/users", headers=make_platform_headers(test_platform_user))
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_super_admin_on_admin_users_with_tenant_slug_returns_403(
    async_client, test_platform_user, test_tenant_a
):
    """SUPER_ADMIN on /admin/users with X-Tenant-Slug → 403.

    SUPER_ADMIN passes verify_tenant_match (no schema to check) and resolves
    the tenant. Then _get_admin_db detects is_super_admin=True and raises 403
    explicitly. SUPER_ADMIN must use tenant ADMIN credentials for /admin/ routes.
    """
    headers = {**make_platform_headers(test_platform_user), "X-Tenant-Slug": SLUG_A}
    resp = await async_client.get("/admin/users", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_super_admin_can_read_programs_with_explicit_tenant_slug(
    async_client, test_platform_user, test_tenant_a
):
    """SUPER_ADMIN + explicit X-Tenant-Slug → can access tenant data (intended).

    SUPER_ADMIN providing an explicit tenant context is permitted. The tenant
    mismatch check is skipped (SUPER_ADMIN has no schema_name in JWT).
    """
    headers = {**make_platform_headers(test_platform_user), "X-Tenant-Slug": SLUG_A}
    resp = await async_client.get("/programs", headers=headers)
    assert resp.status_code == 200


async def test_super_admin_with_mismatched_tenant_context_still_resolves(
    async_client, test_platform_user, test_tenant_a, test_tenant_b
):
    """SUPER_ADMIN has no schema_name claim so 'mismatch' does not apply.

    Providing any valid slug is treated as explicit tenant access. SUPER_ADMIN
    may read tenant_b's data even if they previously accessed tenant_a — there
    is no JWT-level scoping for SUPER_ADMIN (only slug validity is checked).
    """
    for slug in (SLUG_A, SLUG_B):
        headers = {**make_platform_headers(test_platform_user), "X-Tenant-Slug": slug}
        resp = await async_client.get("/programs", headers=headers)
        assert resp.status_code == 200, (
            f"SUPER_ADMIN should access any valid tenant, failed for slug={slug!r}"
        )


# ===========================================================================
# Category 9 — Inactive user
# ===========================================================================

async def test_inactive_user_token_rejected(async_client, test_tenant_a, inactive_user_a):
    """JWT for a user with is_active=False → 401 (user not found or inactive)."""
    token = create_access_token({
        "sub": str(inactive_user_a["id"]),
        "tenant_id": str(inactive_user_a["tenant_id"]),
        "schema_name": SCHEMA_A,
        "role": "FACULTY",
        "email": inactive_user_a["email"],
    })
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


# ===========================================================================
# Category 10 — Forged / tampered JWT
# ===========================================================================

async def test_forged_jwt_wrong_secret_rejected(async_client, test_tenant_a, faculty_user_a):
    """JWT signed with the wrong secret → 401."""
    forged = jose_jwt.encode(
        {
            "sub": str(faculty_user_a["id"]),
            "schema_name": SCHEMA_A,
            "role": "ADMIN",
            "email": faculty_user_a["email"],
        },
        "wrong-secret-entirely",
        algorithm="HS256",
    )
    resp = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {forged}", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"


async def test_role_escalation_via_forged_jwt_rejected(async_client, test_tenant_a, student_user_a):
    """A student cannot forge an ADMIN JWT — wrong secret → 401."""
    forged = jose_jwt.encode(
        {
            "sub": str(student_user_a["id"]),
            "tenant_id": str(student_user_a["tenant_id"]),
            "schema_name": SCHEMA_A,
            "role": "ADMIN",
            "email": student_user_a["email"],
        },
        "attacker-controlled-secret",
        algorithm="HS256",
    )
    resp = await async_client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {forged}", "X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "UNAUTHORIZED"
