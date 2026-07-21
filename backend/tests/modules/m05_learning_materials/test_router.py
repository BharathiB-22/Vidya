"""
Router RBAC and HTTP smoke tests for M05 /learning-packages endpoints (STEP-12).

Strategy
--------
  - Real JWT auth + tenant DB (auth is stateless; tenant session is created by fixture).
  - LearningPackageService methods are mocked so tests need no seeded packages.
  - Tests verify: RBAC gates, HTTP verbs/status codes, response shape, audit path.

RBAC matrix under test
-----------------------
  Endpoint group          ADMIN  FACULTY  DEAN  STUDENT  Unauth
  Write (curate/index/items) ✓      ✓      403    403     401
  Read  (list/get/jobs)     ✓      ✓       ✓     403     401
  Full  (get/items read/ask) ✓      ✓       ✓      ✓      401
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio

from tests.conftest import SCHEMA_A, SLUG_A, _insert_tenant_user, make_tenant_headers

# Sends a syntactically-present but invalid Bearer token — triggers 401 from
# get_current_user (JWTError path) rather than 422 (missing-header validation).
_BAD_AUTH_HEADERS = {
    "X-Tenant-Slug": SLUG_A,
    "Authorization": "Bearer this.is.not.a.valid.jwt",
}

BASE = "/learning-packages"


# ---------------------------------------------------------------------------
# Extra fixtures (DEAN + STUDENT for this module)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def dean_user_a(test_tenant_a):
    user = await _insert_tenant_user(
        SCHEMA_A, "dean_m05@test.com", "Dean1234!", "DEAN", "Dean M05"
    )
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def student_user_a(test_tenant_a):
    user = await _insert_tenant_user(
        SCHEMA_A, "student_m05@test.com", "Student1234!", "STUDENT", "Student M05"
    )
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _pkg_dict(pkg_id: uuid.UUID | None = None) -> dict:
    """Minimal dict that can be used as a mock LearningPackage."""
    pkg_id = pkg_id or uuid.uuid4()
    return {
        "id":                 pkg_id,
        "syllabus_id":        uuid.uuid4(),
        "unit_number":        1,
        "version":            1,
        "status":             "READY",
        "top_n":              10,
        "item_count":         3,
        "qdrant_indexed":     True,
        "ai_model":           "gemini-flash",
        "created_by_user_id": uuid.uuid4(),
        "curated_at":         None,
        "created_at":         datetime.utcnow(),
        "updated_at":         None,
    }


def _orm_pkg(pkg_id: uuid.UUID | None = None):
    from app.modules.m05_learning_materials.models import PackageStatus
    m = MagicMock()
    m.id                  = pkg_id or uuid.uuid4()
    m.syllabus_id         = uuid.uuid4()
    m.unit_number         = 1
    m.version             = 1
    m.status              = PackageStatus.READY
    m.top_n               = 10
    m.item_count          = 3
    m.qdrant_indexed      = True
    m.ai_model            = "gemini-flash"
    m.prompt_hash         = None
    m.created_by_user_id  = uuid.uuid4()
    m.curated_at          = None
    m.created_at          = datetime.utcnow()
    m.updated_at          = None
    return m


def _orm_item(package_id: uuid.UUID | None = None):
    from app.modules.m05_learning_materials.models import MaterialSourceType
    m = MagicMock()
    m.id                  = uuid.uuid4()
    m.package_id          = package_id or uuid.uuid4()
    m.source_type         = MaterialSourceType.FACULTY_NOTE
    m.title               = "Test Resource"
    m.url                 = "https://example.com"
    m.content_hash        = "abc123"
    m.metadata_           = {}
    m.relevance_score     = None
    m.faculty_recommended = True
    m.added_by_user_id    = uuid.uuid4()
    m.display_order       = 0
    m.qdrant_indexed      = False
    m.created_at          = datetime.utcnow()
    m.updated_at          = None
    return m


def _orm_session(package_id: uuid.UUID | None = None):
    m = MagicMock()
    m.id               = uuid.uuid4()
    m.package_id       = package_id or uuid.uuid4()
    m.student_user_id  = uuid.uuid4()
    m.created_at       = datetime.utcnow()
    m.updated_at       = None
    m.messages         = []
    return m


# ===========================================================================
# Unauthenticated — 401 on every write endpoint
# ===========================================================================

async def test_unauth_cannot_trigger_curation(async_client, test_tenant_a):
    resp = await async_client.post(
        f"{BASE}/curate",
        json={"syllabus_id": str(uuid.uuid4()), "unit_number": 1},
        headers=_BAD_AUTH_HEADERS,
    )
    assert resp.status_code == 401


async def test_unauth_cannot_list_packages(async_client, test_tenant_a):
    resp = await async_client.get(
        f"{BASE}",
        params={"syllabus_id": str(uuid.uuid4())},
        headers=_BAD_AUTH_HEADERS,
    )
    assert resp.status_code == 401


# ===========================================================================
# RBAC — STUDENT blocked from write endpoints
# ===========================================================================

async def test_student_cannot_trigger_curation(
    async_client, test_tenant_a, student_user_a
):
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.post(
        f"{BASE}/curate",
        json={"syllabus_id": str(uuid.uuid4()), "unit_number": 1},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_student_cannot_trigger_rag_indexing(
    async_client, test_tenant_a, student_user_a
):
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.post(
        f"{BASE}/{uuid.uuid4()}/index",
        headers=headers,
    )
    assert resp.status_code == 403


async def test_student_cannot_add_item(
    async_client, test_tenant_a, student_user_a
):
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.post(
        f"{BASE}/{uuid.uuid4()}/items",
        json={"title": "Some Resource", "url": "https://example.com"},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_student_cannot_remove_item(
    async_client, test_tenant_a, student_user_a
):
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.delete(
        f"{BASE}/{uuid.uuid4()}/items/{uuid.uuid4()}",
        headers=headers,
    )
    assert resp.status_code == 403


async def test_student_cannot_toggle_recommendation(
    async_client, test_tenant_a, student_user_a
):
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.patch(
        f"{BASE}/{uuid.uuid4()}/items/{uuid.uuid4()}/recommend",
        json={"faculty_recommended": True},
        headers=headers,
    )
    assert resp.status_code == 403


# ===========================================================================
# RBAC — DEAN blocked from write endpoints
# ===========================================================================

async def test_dean_cannot_trigger_curation(
    async_client, test_tenant_a, dean_user_a
):
    headers = make_tenant_headers(dean_user_a)
    resp = await async_client.post(
        f"{BASE}/curate",
        json={"syllabus_id": str(uuid.uuid4()), "unit_number": 1},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_dean_cannot_add_item(
    async_client, test_tenant_a, dean_user_a
):
    headers = make_tenant_headers(dean_user_a)
    resp = await async_client.post(
        f"{BASE}/{uuid.uuid4()}/items",
        json={"title": "Some Resource", "url": "https://example.com"},
        headers=headers,
    )
    assert resp.status_code == 403


# ===========================================================================
# RBAC — STUDENT can read packages and ask questions
# ===========================================================================

async def test_student_can_get_package(
    async_client, test_tenant_a, student_user_a
):
    pkg = _orm_pkg()
    headers = make_tenant_headers(student_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.get_package",
        new=AsyncMock(return_value=pkg),
    ):
        resp = await async_client.get(
            f"{BASE}/{pkg.id}",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == str(pkg.id)


async def test_student_can_list_items(
    async_client, test_tenant_a, student_user_a
):
    item = _orm_item()
    headers = make_tenant_headers(student_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.list_items",
        new=AsyncMock(return_value=[item]),
    ):
        resp = await async_client.get(
            f"{BASE}/{uuid.uuid4()}/items",
            headers=headers,
        )

    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_student_can_ask_question(
    async_client, test_tenant_a, student_user_a
):
    session_id = uuid.uuid4()
    msg_id     = uuid.uuid4()
    headers    = make_tenant_headers(student_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.ask_question",
        new=AsyncMock(return_value={
            "session_id": session_id,
            "message_id": msg_id,
            "answer":     "42",
            "sources":    [],
            "model_used": "gemini-flash",
        }),
    ):
        resp = await async_client.post(
            f"{BASE}/{uuid.uuid4()}/ask",
            json={"question": "What is this module about?"},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "42"
    assert data["session_id"] == str(session_id)


# ===========================================================================
# RBAC — DEAN can read packages
# ===========================================================================

async def test_dean_can_read_packages(
    async_client, test_tenant_a, dean_user_a
):
    headers = make_tenant_headers(dean_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.list_packages",
        new=AsyncMock(return_value=(0, [])),
    ):
        resp = await async_client.get(
            f"{BASE}",
            params={"syllabus_id": str(uuid.uuid4())},
            headers=headers,
        )

    assert resp.status_code == 200


# ===========================================================================
# Happy-path HTTP wiring — ADMIN
# ===========================================================================

async def test_trigger_curation_returns_202(
    async_client, test_tenant_a, admin_user_a
):
    from app.modules.m05_learning_materials.schemas import CurationJobResponse

    job_id = uuid.uuid4()
    pkg_id = uuid.uuid4()
    headers = make_tenant_headers(admin_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.dispatch_curation",
        new=AsyncMock(return_value=CurationJobResponse(
            job_id=job_id, package_id=pkg_id, status="queued"
        )),
    ):
        resp = await async_client.post(
            f"{BASE}/curate",
            json={"syllabus_id": str(uuid.uuid4()), "unit_number": 1},
            headers=headers,
        )

    assert resp.status_code == 202
    data = resp.json()
    assert data["job_id"] == str(job_id)
    assert data["status"] == "queued"


async def test_trigger_rag_indexing_returns_202(
    async_client, test_tenant_a, admin_user_a
):
    job_id  = uuid.uuid4()
    pkg_id  = uuid.uuid4()
    headers = make_tenant_headers(admin_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.dispatch_rag_indexing",
        new=AsyncMock(return_value=str(job_id)),
    ):
        resp = await async_client.post(
            f"{BASE}/{pkg_id}/index",
            headers=headers,
        )

    assert resp.status_code == 202
    assert resp.json()["job_id"] == str(job_id)


async def test_list_packages_pagination(
    async_client, test_tenant_a, faculty_user_a
):
    pkgs    = [_orm_pkg(), _orm_pkg()]
    headers = make_tenant_headers(faculty_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.list_packages",
        new=AsyncMock(return_value=(2, pkgs)),
    ):
        resp = await async_client.get(
            f"{BASE}",
            params={"syllabus_id": str(uuid.uuid4()), "page": 1, "page_size": 20},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


async def test_get_package_404(
    async_client, test_tenant_a, faculty_user_a
):
    headers = make_tenant_headers(faculty_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.get_package",
        new=AsyncMock(return_value=None),
    ):
        resp = await async_client.get(
            f"{BASE}/{uuid.uuid4()}",
            headers=headers,
        )

    assert resp.status_code == 404
    assert resp.json()["error"] == "NOT_FOUND"


async def test_add_faculty_item_returns_201(
    async_client, test_tenant_a, faculty_user_a
):
    item    = _orm_item()
    headers = make_tenant_headers(faculty_user_a)

    with (
        patch(
            "app.modules.m05_learning_materials.service"
            ".LearningPackageService.add_faculty_item",
            new=AsyncMock(return_value=item),
        ),
        patch(
            "app.core.audit_log.service.AuditService.log",
            new=AsyncMock(),
        ),
    ):
        resp = await async_client.post(
            f"{BASE}/{uuid.uuid4()}/items",
            json={"title": "Great Video", "url": "https://youtube.com/watch?v=abc"},
            headers=headers,
        )

    assert resp.status_code == 201
    assert resp.json()["id"] == str(item.id)


async def test_remove_item_returns_200(
    async_client, test_tenant_a, faculty_user_a
):
    headers = make_tenant_headers(faculty_user_a)

    with (
        patch(
            "app.modules.m05_learning_materials.service"
            ".LearningPackageService.remove_item",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.core.audit_log.service.AuditService.log",
            new=AsyncMock(),
        ),
    ):
        resp = await async_client.delete(
            f"{BASE}/{uuid.uuid4()}/items/{uuid.uuid4()}",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"


async def test_toggle_recommendation(
    async_client, test_tenant_a, faculty_user_a
):
    item    = _orm_item()
    headers = make_tenant_headers(faculty_user_a)

    with (
        patch(
            "app.modules.m05_learning_materials.service"
            ".LearningPackageService.toggle_faculty_recommendation",
            new=AsyncMock(return_value=item),
        ),
        patch(
            "app.core.audit_log.service.AuditService.log",
            new=AsyncMock(),
        ),
    ):
        resp = await async_client.patch(
            f"{BASE}/{uuid.uuid4()}/items/{item.id}/recommend",
            json={"faculty_recommended": True},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == str(item.id)


async def test_get_job_status_404(
    async_client, test_tenant_a, admin_user_a
):
    headers = make_tenant_headers(admin_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.get_job_status",
        new=AsyncMock(return_value=None),
    ):
        resp = await async_client.get(
            f"{BASE}/jobs/{uuid.uuid4()}",
            headers=headers,
        )

    assert resp.status_code == 404


async def test_get_qa_session_404(
    async_client, test_tenant_a, student_user_a
):
    headers = make_tenant_headers(student_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.get_qa_session",
        new=AsyncMock(return_value=None),
    ):
        resp = await async_client.get(
            f"{BASE}/{uuid.uuid4()}/qa/sessions/{uuid.uuid4()}",
            headers=headers,
        )

    assert resp.status_code == 404


# ===========================================================================
# Service error → correct HTTP status code propagation
# ===========================================================================

async def test_duplicate_curation_returns_409(
    async_client, test_tenant_a, faculty_user_a
):
    from app.modules.m05_learning_materials.service import PackageServiceError

    headers = make_tenant_headers(faculty_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.dispatch_curation",
        new=AsyncMock(
            side_effect=PackageServiceError("ALREADY_CURATING", "Busy.", 409)
        ),
    ):
        resp = await async_client.post(
            f"{BASE}/curate",
            json={"syllabus_id": str(uuid.uuid4()), "unit_number": 1},
            headers=headers,
        )

    assert resp.status_code == 409
    assert resp.json()["error"] == "ALREADY_CURATING"


async def test_not_indexed_ask_returns_409(
    async_client, test_tenant_a, student_user_a
):
    from app.modules.m05_learning_materials.service import PackageServiceError

    headers = make_tenant_headers(student_user_a)

    with patch(
        "app.modules.m05_learning_materials.service"
        ".LearningPackageService.ask_question",
        new=AsyncMock(
            side_effect=PackageServiceError("NOT_INDEXED", "Not indexed.", 409)
        ),
    ):
        resp = await async_client.post(
            f"{BASE}/{uuid.uuid4()}/ask",
            json={"question": "What is this module about?"},
            headers=headers,
        )

    assert resp.status_code == 409
    assert resp.json()["error"] == "NOT_INDEXED"
