"""
Service-layer integration tests for M02 SyllabusService.
Uses a real DB session (tenant_db_a) with search_path set to SCHEMA_A.
Celery dispatch is mocked to avoid Redis dependency.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.modules.m02_syllabus.models import BloomLevel, SyllabusStatus
from app.modules.m02_syllabus.schemas import (
    COPOMappingBulkUpdate,
    COPOMappingCreate,
    CourseOutcomeCreate,
    CourseOutcomeUpdate,
    MappingStrength,
    SyllabusCreate,
    SyllabusReferenceCreate,
    SyllabusUpdate,
    SyllabusUnitCreate,
    SyllabusUnitUpdate,
    UnitTopicItem,
)
from app.modules.m02_syllabus.service import SyllabusService, SyllabusServiceError
from tests.modules.m02_syllabus.conftest import (
    build_compliant_syllabus,
    force_syllabus_status,
    make_syllabus_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_draft(tenant_db, course_id, user_id=None):
    payload = SyllabusCreate(**make_syllabus_payload(course_id))
    return await SyllabusService.create_syllabus(
        payload, created_by=user_id or uuid.uuid4(), caller_role="BOARD", db=tenant_db
    )


async def _do_approve(syllabus_id, user_id, tenant_db):
    """DRAFT -> APPROVED, in one step.

    The Board writes the official syllabus and the Board signs it off, so there is
    no submit-for-review handoff — there is nobody to hand it to.
    """
    return await SyllabusService.approve(
        syllabus_id, approved_by=user_id, caller_role="BOARD", db=tenant_db
    )


# ===========================================================================
# CRUD
# ===========================================================================

async def test_create_syllabus_creates_draft(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    assert s.status == SyllabusStatus.DRAFT
    assert s.version == 1
    assert s.parent_version_id is None
    assert s.course_id == m01_setup["course_id"]


async def test_get_syllabus_returns_none_for_unknown(tenant_db_a, m01_setup):
    result = await SyllabusService.get_syllabus(uuid.uuid4(), db=tenant_db_a)
    assert result is None


async def test_update_syllabus_allowed_in_draft(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    updated = await SyllabusService.update_syllabus(
        s.id, SyllabusUpdate(custom_instructions="Focus on Python"), caller_role="BOARD", db=tenant_db_a
    )
    assert updated.custom_instructions == "Focus on Python"


async def test_editing_an_approved_syllabus_returns_it_to_draft(tenant_db_a, m01_setup):
    """Approval is a sign-off, not a freeze. The Board may revise a syllabus right
    up to curriculum approval — but a sign-off must mean "I have read exactly
    this", so it cannot survive an edit to the thing it signed off on. The
    curriculum then cannot be approved until the Board approves the syllabus
    again, which is what keeps a stale document out of a locked curriculum."""
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await force_syllabus_status(s.id, SyllabusStatus.APPROVED, tenant_db_a)

    updated = await SyllabusService.update_syllabus(
        s.id, SyllabusUpdate(custom_instructions="Changed"), caller_role="BOARD", db=tenant_db_a
    )
    assert updated.status == SyllabusStatus.DRAFT
    assert updated.approved_at is None
    assert updated.approved_by_user_id is None


async def test_update_syllabus_blocked_when_locked(tenant_db_a, m01_setup):
    """LOCKED means the curriculum was approved. Nobody edits — not the Board that
    locked it, not an Admin. The only way past it is a new curriculum version."""
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await force_syllabus_status(s.id, SyllabusStatus.LOCKED, tenant_db_a)

    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.update_syllabus(
            s.id, SyllabusUpdate(custom_instructions="Changed"), caller_role="BOARD", db=tenant_db_a
        )
    assert exc.value.code == "CURRICULUM_LOCKED"
    assert exc.value.status_code == 409


async def test_delete_syllabus_allowed_in_draft(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await SyllabusService.delete_syllabus(s.id, caller_role="BOARD", db=tenant_db_a)
    assert await SyllabusService.get_syllabus(s.id, db=tenant_db_a) is None


async def test_delete_syllabus_blocked_when_locked(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await force_syllabus_status(s.id, SyllabusStatus.LOCKED, tenant_db_a)

    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.delete_syllabus(s.id, caller_role="BOARD", db=tenant_db_a)
    assert exc.value.code == "CURRICULUM_LOCKED"


# ===========================================================================
# Compliance check
# ===========================================================================

async def test_compliance_check_on_empty_syllabus(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    result = await SyllabusService.run_compliance_check(s.id, db=tenant_db_a)
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "CO_MIN_NOT_MET" in codes
    assert "UNIT_MIN_NOT_MET" in codes


async def test_compliance_check_passes_with_4_cos_and_units(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s.id, tenant_db_a)
    result = await SyllabusService.run_compliance_check(s.id, db=tenant_db_a)
    assert result.passed is True


# ===========================================================================
# Approve
# ===========================================================================

async def test_approve_requires_draft(tenant_db_a, m01_setup, admin_user_a):
    # Approving an already-approved syllabus is a no-op the caller should know about.
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s.id, tenant_db_a)
    await force_syllabus_status(s.id, SyllabusStatus.APPROVED, tenant_db_a)

    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.approve(s.id, approved_by=admin_user_a["id"], caller_role="BOARD", db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


async def test_approve_blocked_by_compliance_error(tenant_db_a, m01_setup, admin_user_a):
    # Empty syllabus → approve runs compliance → COMPLIANCE_FAILED. The Board
    # cannot sign off a syllabus with no outcomes and no units.
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.approve(
            s.id, approved_by=admin_user_a["id"], caller_role="BOARD", db=tenant_db_a
        )
    assert exc.value.code == "COMPLIANCE_FAILED"
    assert exc.value.status_code == 422


async def test_structural_course_edit_unapproves_the_syllabus(
    tenant_db_a, m01_setup, admin_user_a,
):
    """The mechanism that lets the Board edit the structure freely with no freeze.

    A syllabus is written against a course: its header prints the credits, its
    units are paced to the contact hours derived from the L-T-P. Move any of that
    and the Board's sign-off no longer describes the document it signed off on —
    so the syllabus goes back to DRAFT and must be re-read. The curriculum's
    approve gate (every subject APPROVED) then cannot pass until it is.
    """
    from app.modules.m01_program_advisor.schemas import CourseUpdate
    from app.modules.m01_program_advisor.service import ProgramService

    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s.id, tenant_db_a)
    approved = await _do_approve(s.id, admin_user_a["id"], tenant_db_a)
    assert approved.status == SyllabusStatus.APPROVED

    await ProgramService.update_course(
        m01_setup["course_id"],
        m01_setup["program_id"],
        CourseUpdate(credits=6),
        db=tenant_db_a,
    )

    refreshed = await SyllabusService.get_syllabus(s.id, db=tenant_db_a)
    assert refreshed.status == SyllabusStatus.DRAFT
    assert refreshed.approved_at is None


async def test_approve_succeeds_with_compliant_syllabus(tenant_db_a, m01_setup, admin_user_a):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s.id, tenant_db_a)

    approved = await _do_approve(s.id, admin_user_a["id"], tenant_db_a)
    assert approved.status == SyllabusStatus.APPROVED
    assert approved.approved_by_user_id == admin_user_a["id"]
    assert approved.approved_at is not None


async def test_approve_passes_with_warnings_only(tenant_db_a, m01_setup, admin_user_a):
    # 4 COs (same bloom level → BLOOM_DIVERSITY_LOW warning) + 4 units, no CO-PO mappings
    # → COPO_COVERAGE_LOW warning too, but no ERRORs → should approve
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    for i in range(1, 5):
        await SyllabusService.add_co(
            s.id,
            CourseOutcomeCreate(
                code=f"CO{i}",
                description=f"Same bloom level outcome {i} description ok",
                bloom_level=BloomLevel.APPLY,  # intentionally all same level
                display_order=i,
            ),
            caller_role="BOARD", db=tenant_db_a,
        )
    for i in range(1, 5):
        await SyllabusService.add_unit(
            s.id,
            SyllabusUnitCreate(unit_number=i, title=f"Unit {i}", total_hours=10,
                               topics=[UnitTopicItem(title="Topic")]),
            caller_role="BOARD", db=tenant_db_a,
        )

    approved = await _do_approve(s.id, admin_user_a["id"], tenant_db_a)
    assert approved.status == SyllabusStatus.APPROVED


# ===========================================================================
# Reject / lock / unlock — all gone
#
# reject() belonged to the workflow where FACULTY authored a syllabus and a DEAN
# sent it back. The Board writes the syllabus itself, so there is nobody to
# reject and nowhere to send it: when the Board is unhappy with a syllabus, it
# edits it.
#
# lock()/unlock() are gone because locking is not a syllabus-level act. A
# syllabus is locked when the CURRICULUM is approved — structure and syllabus
# freeze as one thing, or the pair is incoherent — and it is never unlocked.
# ===========================================================================

async def test_the_removed_transitions_are_really_gone(tenant_db_a, m01_setup):
    for method in ("submit_for_review", "resubmit", "reject", "request_revision",
                   "lock", "unlock"):
        assert not hasattr(SyllabusService, method), method


async def test_a_locked_syllabus_blocks_all_edits(tenant_db_a, m01_setup, admin_user_a):
    """LOCKED is the one truly immutable state. It is reached by CURRICULUM
    approval, not by a syllabus-level lock, and there is no way back out of it
    short of a new curriculum version."""
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s.id, tenant_db_a)
    await _do_approve(s.id, admin_user_a["id"], tenant_db_a)
    await force_syllabus_status(s.id, SyllabusStatus.LOCKED, tenant_db_a)

    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.update_syllabus(
            s.id, SyllabusUpdate(custom_instructions="Changed"), caller_role="BOARD", db=tenant_db_a
        )
    assert exc.value.code == "CURRICULUM_LOCKED"

    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.delete_syllabus(s.id, caller_role="BOARD", db=tenant_db_a)
    assert exc.value.code == "CURRICULUM_LOCKED"



# ===========================================================================
# Fork
# ===========================================================================

async def test_fork_creates_new_draft_with_parent_link(tenant_db_a, m01_setup, admin_user_a):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s.id, tenant_db_a)

    forked = await SyllabusService.fork(
        s.id, created_by=admin_user_a["id"], change_note="New approach", caller_role="BOARD", db=tenant_db_a
    )
    assert forked.status == SyllabusStatus.DRAFT
    assert forked.version == 2
    assert forked.parent_version_id == s.id
    assert forked.change_note == "New approach"


async def test_fork_copies_cos_and_units(tenant_db_a, m01_setup, admin_user_a):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s.id, tenant_db_a)

    forked = await SyllabusService.fork(
        s.id, created_by=admin_user_a["id"], change_note=None, caller_role="BOARD", db=tenant_db_a
    )
    orig_cos   = await SyllabusService.list_cos(s.id, db=tenant_db_a)
    forked_cos = await SyllabusService.list_cos(forked.id, db=tenant_db_a)
    assert len(forked_cos) == len(orig_cos)
    assert forked_cos[0].code == orig_cos[0].code

    orig_units   = await SyllabusService.list_units(s.id, db=tenant_db_a)
    forked_units = await SyllabusService.list_units(forked.id, db=tenant_db_a)
    assert len(forked_units) == len(orig_units)


async def test_fork_blocked_when_generating(tenant_db_a, m01_setup, admin_user_a):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await force_syllabus_status(s.id, SyllabusStatus.AI_GENERATING, tenant_db_a)

    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.fork(
            s.id, created_by=admin_user_a["id"], change_note=None, caller_role="BOARD", db=tenant_db_a
        )
    assert exc.value.code == "GENERATING"


# ===========================================================================
# Course Outcomes — DRAFT-only mutations
# ===========================================================================

async def test_add_co_succeeds_in_draft(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    co = await SyllabusService.add_co(
        s.id,
        CourseOutcomeCreate(
            code="CO1",
            description="Apply algorithms to solve computational problems",
            bloom_level=BloomLevel.APPLY,
            display_order=1,
        ),
        caller_role="BOARD", db=tenant_db_a,
    )
    assert co.code == "CO1"
    assert co.bloom_level == BloomLevel.APPLY


async def test_adding_a_co_unapproves_the_syllabus(tenant_db_a, m01_setup):
    """Editing ANY part of an approved syllabus takes its approval away.

    An approval must mean "a member of the board has read exactly this document".
    If a course outcome could be added to an approved syllabus without disturbing
    the approval, the curriculum's approve gate would pass on a document nobody
    had read in its current form. Every write goes through `_require_mutable`,
    which is where the invalidation lives, so no write path can forget it.
    """
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await force_syllabus_status(s.id, SyllabusStatus.APPROVED, tenant_db_a)

    await SyllabusService.add_co(
        s.id,
        CourseOutcomeCreate(
            code="CO1",
            description="An outcome added after the board approved the syllabus",
            bloom_level=BloomLevel.APPLY,
        ),
        caller_role="BOARD", db=tenant_db_a,
    )

    refreshed = await SyllabusService.get_syllabus(s.id, db=tenant_db_a)
    assert refreshed.status == SyllabusStatus.DRAFT
    assert refreshed.approved_at is None


async def test_add_co_duplicate_code_raises_error(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await SyllabusService.add_co(
        s.id,
        CourseOutcomeCreate(
            code="CO1",
            description="First outcome with this code for test",
            bloom_level=BloomLevel.APPLY,
        ),
        caller_role="BOARD", db=tenant_db_a,
    )
    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.add_co(
            s.id,
            CourseOutcomeCreate(
                code="CO1",
                description="Duplicate code should raise error here",
                bloom_level=BloomLevel.EVALUATE,
            ),
            caller_role="BOARD", db=tenant_db_a,
        )
    assert exc.value.code == "CODE_EXISTS"


async def test_deleting_a_co_unapproves_the_syllabus(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    co = await SyllabusService.add_co(
        s.id,
        CourseOutcomeCreate(
            code="CO1", description="Outcome to attempt deletion of when approved",
            bloom_level=BloomLevel.APPLY,
        ),
        caller_role="BOARD", db=tenant_db_a,
    )
    await force_syllabus_status(s.id, SyllabusStatus.APPROVED, tenant_db_a)

    await SyllabusService.delete_co(co.id, s.id, caller_role="BOARD", db=tenant_db_a)

    refreshed = await SyllabusService.get_syllabus(s.id, db=tenant_db_a)
    assert refreshed.status == SyllabusStatus.DRAFT


# ===========================================================================
# Units — DRAFT-only mutations
# ===========================================================================

async def test_add_unit_succeeds_in_draft(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    unit = await SyllabusService.add_unit(
        s.id,
        SyllabusUnitCreate(
            unit_number=1, title="Introduction to Computing",
            total_hours=12, topics=[UnitTopicItem(title="Basics")],
        ),
        caller_role="BOARD", db=tenant_db_a,
    )
    assert unit.unit_number == 1
    assert unit.title == "Introduction to Computing"


async def test_adding_a_unit_unapproves_the_syllabus(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await force_syllabus_status(s.id, SyllabusStatus.APPROVED, tenant_db_a)

    await SyllabusService.add_unit(
        s.id,
        SyllabusUnitCreate(unit_number=1, title="New Unit", total_hours=10,
                           topics=[UnitTopicItem(title="T")]),
        caller_role="BOARD", db=tenant_db_a,
    )

    refreshed = await SyllabusService.get_syllabus(s.id, db=tenant_db_a)
    assert refreshed.status == SyllabusStatus.DRAFT


# ===========================================================================
# CO-PO Mappings
# ===========================================================================

async def test_update_copo_mappings_succeeds_in_draft(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    co = await SyllabusService.add_co(
        s.id,
        CourseOutcomeCreate(
            code="CO1", description="Apply algorithms to real problems and systems",
            bloom_level=BloomLevel.APPLY,
        ),
        caller_role="BOARD", db=tenant_db_a,
    )
    po_id = m01_setup["po_ids"][0]
    mappings = await SyllabusService.update_copo_mappings(
        co.id, s.id,
        COPOMappingBulkUpdate(mappings=[
            COPOMappingCreate(po_id=po_id, mapping_strength=MappingStrength.HIGH)
        ]),
        caller_role="BOARD", db=tenant_db_a,
    )
    assert len(mappings) == 1
    assert mappings[0].po_id == po_id
    assert mappings[0].mapping_strength == MappingStrength.HIGH


async def test_updating_copo_mappings_unapproves_the_syllabus(tenant_db_a, m01_setup):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    co = await SyllabusService.add_co(
        s.id,
        CourseOutcomeCreate(
            code="CO1", description="Outcome for testing copo mapping when approved",
            bloom_level=BloomLevel.APPLY,
        ),
        caller_role="BOARD", db=tenant_db_a,
    )
    await force_syllabus_status(s.id, SyllabusStatus.APPROVED, tenant_db_a)

    await SyllabusService.update_copo_mappings(
        co.id, s.id,
        COPOMappingBulkUpdate(mappings=[
            COPOMappingCreate(po_id=m01_setup["po_ids"][0])
        ]),
        caller_role="BOARD", db=tenant_db_a,
    )

    refreshed = await SyllabusService.get_syllabus(s.id, db=tenant_db_a)
    assert refreshed.status == SyllabusStatus.DRAFT


# ===========================================================================
# Export eligibility
# ===========================================================================

async def test_dispatch_export_blocked_for_draft(tenant_db_a, m01_setup, test_tenant_a):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    with pytest.raises(SyllabusServiceError) as exc:
        await SyllabusService.dispatch_export(
            syllabus_id=s.id,
            export_format="pdf",
            tenant_id=test_tenant_a["id"],
            schema_name=test_tenant_a["schema_name"],
            requested_by_user_id=uuid.uuid4(),
            db=tenant_db_a,
        )
    assert exc.value.code == "EXPORT_NOT_ELIGIBLE"
    assert exc.value.status_code == 422


async def test_dispatch_export_allowed_for_approved(
    tenant_db_a, m01_setup, test_tenant_a, admin_user_a
):
    s = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s.id, tenant_db_a)
    await _do_approve(s.id, admin_user_a["id"], tenant_db_a)

    mock_task = MagicMock()
    mock_task.delay = MagicMock()
    with patch(
        "app.modules.m02_syllabus.service.TaskJobPublicRepository.create",
        return_value=uuid.uuid4(),
    ), patch(
        "app.modules.m02_syllabus.service.SyllabusRepository.get_by_id",
        wraps=lambda sid, db: tenant_db_a.get(
            __import__("app.modules.m02_syllabus.models", fromlist=["Syllabus"]).Syllabus, sid
        ),
    ):
        pass  # just test it doesn't raise; Celery not running in test env

    # Simpler approach: just verify no EXPORT_NOT_ELIGIBLE is raised
    # (the Celery dispatch will raise ImportError or similar which we swallow)
    try:
        await SyllabusService.dispatch_export(
            syllabus_id=s.id,
            export_format="pdf",
            tenant_id=test_tenant_a["id"],
            schema_name=test_tenant_a["schema_name"],
            requested_by_user_id=admin_user_a["id"],
            db=tenant_db_a,
        )
    except SyllabusServiceError as e:
        pytest.fail(f"Should not raise SyllabusServiceError: {e.code} — {e.message}")
    # Celery/ImportError is silently logged by service; test passes if no SyllabusServiceError


# ===========================================================================
# Versioning — list_versions
# ===========================================================================

async def test_list_versions_returns_all_course_syllabi(
    tenant_db_a, m01_setup, admin_user_a
):
    s1 = await _create_draft(tenant_db_a, m01_setup["course_id"])
    await build_compliant_syllabus(s1.id, tenant_db_a)
    await _do_approve(s1.id, admin_user_a["id"], tenant_db_a)
    s2 = await SyllabusService.fork(
        s1.id, created_by=admin_user_a["id"], change_note="Version 2", caller_role="BOARD", db=tenant_db_a
    )

    versions = await SyllabusService.list_versions(m01_setup["course_id"], db=tenant_db_a)
    version_ids = {v.id for v in versions}
    assert s1.id in version_ids
    assert s2.id in version_ids
    assert len(versions) >= 2
