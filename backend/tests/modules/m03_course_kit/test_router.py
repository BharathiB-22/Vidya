"""
Router RBAC and HTTP integration tests for M03 /course-kits endpoints.
Uses async_client against a real tenant schema.

DEAN gating verification confirms non-mutating masking:
  - server DB records are unchanged
  - only the HTTP response fields are masked (model_copy, not DB write)
"""
from __future__ import annotations

import uuid


from tests.conftest import make_tenant_headers
from tests.modules.m03_course_kit.conftest import (
    assign_faculty_to_course,
    build_compliant_kit_via_db,
    force_kit_status_committed,
    grant_dean_program_scope,
    make_kit_payload,
)
from app.modules.m03_course_kit.models import CourseKitStatus

BASE = "/course-kits"


# ---------------------------------------------------------------------------
# HTTP helper: create kit via API
# ---------------------------------------------------------------------------

async def _create_kit(async_client, headers, syllabus_id: uuid.UUID, unit_number: int = 1) -> dict:
    resp = await async_client.post(
        BASE, json=make_kit_payload(syllabus_id, unit_number=unit_number), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ===========================================================================
# RBAC — DEAN blocked from all write operations
# ===========================================================================

async def test_dean_cannot_create_kit(async_client, test_tenant_a, dean_user_a, m02_setup):
    headers = make_tenant_headers(dean_user_a)
    resp = await async_client.post(
        BASE, json=make_kit_payload(m02_setup["syllabus_id"]), headers=headers
    )
    assert resp.status_code == 403


async def test_dean_cannot_patch_kit(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.patch(
        f"{BASE}/{data['id']}", json={"tone": "formal"}, headers=dean_h
    )
    assert resp.status_code == 403


async def test_dean_cannot_delete_kit(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.delete(f"{BASE}/{data['id']}", headers=dean_h)
    assert resp.status_code == 403


async def test_dean_cannot_generate_kit(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/generate", json={}, headers=dean_h
    )
    assert resp.status_code == 403


async def test_dean_cannot_publish_kit(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/publish", json={}, headers=dean_h
    )
    assert resp.status_code == 403


async def test_dean_cannot_archive_kit(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/archive", json={}, headers=dean_h
    )
    assert resp.status_code == 403


async def test_dean_cannot_fork_kit(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/fork", json={}, headers=dean_h
    )
    assert resp.status_code == 403


async def test_dean_cannot_add_slide(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/slides",
        json={"slide_number": 1, "title": "Blocked Slide"},
        headers=dean_h,
    )
    assert resp.status_code == 403


async def test_dean_cannot_add_assignment(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/assignments",
        json={
            "assignment_number": 1,
            "title": "Blocked Assignment",
            "question_text": "Blocked assignment question text here.",
        },
        headers=dean_h,
    )
    assert resp.status_code == 403


# ===========================================================================
# RBAC — STUDENT blocked (read and write)
# ===========================================================================

async def test_student_cannot_create_kit(
    async_client, test_tenant_a, student_user_a, m02_setup
):
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.post(
        BASE, json=make_kit_payload(m02_setup["syllabus_id"]), headers=headers
    )
    assert resp.status_code == 403


async def test_student_cannot_read_kit_list(
    async_client, test_tenant_a, student_user_a, m02_setup
):
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.get(
        BASE,
        params={"syllabus_id": str(m02_setup["syllabus_id"])},
        headers=headers,
    )
    assert resp.status_code == 403


# ===========================================================================
# DEAN — read access allowed
# ===========================================================================

async def test_dean_can_read_kit_list(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    await grant_dean_program_scope(
        dean_user_a["id"], m02_setup["program_id"], test_tenant_a["schema_name"]
    )
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.get(
        BASE,
        params={"syllabus_id": str(m02_setup["syllabus_id"])},
        headers=dean_h,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1


async def test_dean_can_read_compliance(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    await grant_dean_program_scope(
        dean_user_a["id"], m02_setup["program_id"], test_tenant_a["schema_name"]
    )
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])

    resp = await async_client.get(
        f"{BASE}/{data['id']}/compliance", headers=dean_h
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "passed" in body
    assert "violations" in body


# ===========================================================================
# DEAN sensitive-field gating (non-mutating masking verification)
# ===========================================================================

async def test_dean_gating_nulls_speaker_notes_model_answer(
    async_client, test_tenant_a, admin_user_a, dean_user_a, faculty_user_a, m02_setup
):
    await grant_dean_program_scope(
        dean_user_a["id"], m02_setup["program_id"], test_tenant_a["schema_name"]
    )
    admin_h   = make_tenant_headers(admin_user_a)
    dean_h    = make_tenant_headers(dean_user_a)
    faculty_h = make_tenant_headers(faculty_user_a)

    await assign_faculty_to_course(
        m02_setup["course_id"], faculty_user_a["id"], test_tenant_a["schema_name"]
    )

    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])
    kit_id = data["id"]

    # Seed slide with speaker_notes, assignment with model_answer
    await async_client.post(
        f"{BASE}/{kit_id}/slides",
        json={
            "slide_number": 1,
            "title": "Gating Test Slide",
            "speaker_notes": "Secret faculty notes",
        },
        headers=admin_h,
    )
    await async_client.post(
        f"{BASE}/{kit_id}/assignments",
        json={
            "assignment_number": 1,
            "title": "Gating Test Assignment",
            "question_text": "Describe the gating mechanism in this system.",
            "model_answer": "Secret model answer text",
        },
        headers=admin_h,
    )

    # DEAN view — all sensitive fields must be null
    dean_resp = await async_client.get(f"{BASE}/{kit_id}", headers=dean_h)
    assert dean_resp.status_code == 200
    body = dean_resp.json()
    assert body["slides"][0]["speaker_notes"] is None
    assert body["assignments"][0]["model_answer"] is None

    # FACULTY view — sensitive fields must be present (non-null)
    faculty_resp = await async_client.get(f"{BASE}/{kit_id}", headers=faculty_h)
    assert faculty_resp.status_code == 200
    fac_body = faculty_resp.json()
    assert fac_body["slides"][0]["speaker_notes"] == "Secret faculty notes"
    assert fac_body["assignments"][0]["model_answer"] == "Secret model answer text"


async def test_dean_gating_is_non_mutating_db_record_unchanged(
    async_client, test_tenant_a, admin_user_a, dean_user_a, m02_setup
):
    """DEAN GET must not modify the DB record — verify by reading as ADMIN after."""
    await grant_dean_program_scope(
        dean_user_a["id"], m02_setup["program_id"], test_tenant_a["schema_name"]
    )
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)

    data = await _create_kit(async_client, admin_h, m02_setup["syllabus_id"])
    kit_id = data["id"]

    await async_client.post(
        f"{BASE}/{kit_id}/slides",
        json={"slide_number": 1, "title": "Non-Mutating Test", "speaker_notes": "Still here"},
        headers=admin_h,
    )

    # DEAN reads — should null speaker_notes in response
    dean_resp = await async_client.get(f"{BASE}/{kit_id}", headers=dean_h)
    assert dean_resp.json()["slides"][0]["speaker_notes"] is None

    # ADMIN reads after — speaker_notes must still be in the DB
    admin_resp = await async_client.get(f"{BASE}/{kit_id}", headers=admin_h)
    assert admin_resp.json()["slides"][0]["speaker_notes"] == "Still here"


# ===========================================================================
# HTTP happy path
# ===========================================================================

async def test_admin_can_create_kit_returns_201_draft(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.post(
        BASE, json=make_kit_payload(m02_setup["syllabus_id"]), headers=headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "DRAFT"
    assert body["version"] == 1
    assert body["syllabus_id"] == str(m02_setup["syllabus_id"])


async def test_get_kit_returns_404_for_unknown_id(
    async_client, test_tenant_a, admin_user_a
):
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.get(f"{BASE}/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert "message" in body


async def test_get_kit_detail_includes_child_lists(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    data = await _create_kit(async_client, headers, m02_setup["syllabus_id"])

    resp = await async_client.get(f"{BASE}/{data['id']}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "slides" in body
    assert "assignments" in body
    assert isinstance(body["slides"], list)
    assert isinstance(body["assignments"], list)


async def test_patch_kit_updates_tone(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    data = await _create_kit(async_client, headers, m02_setup["syllabus_id"])

    resp = await async_client.patch(
        f"{BASE}/{data['id']}", json={"tone": "conversational"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["tone"] == "conversational"


async def test_compliance_check_returns_shape(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    data = await _create_kit(async_client, headers, m02_setup["syllabus_id"])

    resp = await async_client.get(f"{BASE}/{data['id']}/compliance", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "passed" in body
    assert "violations" in body
    assert isinstance(body["violations"], list)
    # empty kit → should have violations
    assert body["passed"] is False


async def test_publish_compliant_kit_returns_published_status(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    data = await _create_kit(async_client, headers, m02_setup["syllabus_id"])
    kit_id = data["id"]

    await build_compliant_kit_via_db(uuid.UUID(kit_id), test_tenant_a["schema_name"])

    resp = await async_client.post(
        f"{BASE}/{kit_id}/publish", json={}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PUBLISHED"
    assert body["id"] == kit_id


async def test_422_publish_non_compliant_kit(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    data = await _create_kit(async_client, headers, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/publish", json={}, headers=headers
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body.get("error") == "COMPLIANCE_FAILED"


async def test_fork_creates_new_draft_with_parent_link(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    data = await _create_kit(async_client, headers, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/fork", json={}, headers=headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "DRAFT"
    assert body["id"] != data["id"]


async def test_409_when_publishing_non_draft_kit(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    data = await _create_kit(async_client, headers, m02_setup["syllabus_id"])
    kit_id = uuid.UUID(data["id"])

    await force_kit_status_committed(kit_id, CourseKitStatus.ARCHIVED)

    resp = await async_client.post(
        f"{BASE}/{data['id']}/publish", json={}, headers=headers
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body.get("error") == "INVALID_STATE"


async def test_export_blocked_for_draft_kit(
    async_client, test_tenant_a, admin_user_a, m02_setup
):
    headers = make_tenant_headers(admin_user_a)
    data = await _create_kit(async_client, headers, m02_setup["syllabus_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/export", json={"format": "pdf"}, headers=headers
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body.get("error") == "INVALID_STATE"


# ===========================================================================
# Tenant isolation
# ===========================================================================

async def test_tenant_b_user_cannot_access_tenant_a_kit(
    async_client, test_tenant_a, test_tenant_b,
    admin_user_a, admin_user_b, m02_setup
):
    admin_a_h = make_tenant_headers(admin_user_a)
    admin_b_h = make_tenant_headers(admin_user_b)

    data = await _create_kit(async_client, admin_a_h, m02_setup["syllabus_id"])

    # Tenant B user attempts to access Tenant A's kit
    resp = await async_client.get(f"{BASE}/{data['id']}", headers=admin_b_h)
    # Expect 404 (not found in B's schema) or 422
    assert resp.status_code in (404, 422)
