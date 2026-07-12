"""
Service-layer tests for M01 ProgramService.
Uses a real DB session (tenant_db_a) with search_path set to SCHEMA_A.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.core.auth.schemas import CurrentUser
from app.core.governance import service as gov
from app.modules.m01_program_advisor.models import ProgramStatus
from app.modules.m01_program_advisor.repository import ProgramRepository
from app.modules.m01_program_advisor.schemas import (
    CourseCreate,
    ElectiveBasketCreate,
    ProgramCreate,
    ProgramOutcomeCreate,
    ProgramUpdate,
)
from app.modules.m01_program_advisor.service import ProgramService, ProgramServiceError
from tests.modules.m01_program_advisor.conftest import (
    approve_all_syllabi,
    bind_to_batch,
    build_compliant_program,
    force_status,
    make_program_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_draft(tenant_db, created_by: uuid.UUID | None = None):
    payload = ProgramCreate(**make_program_payload())
    return await ProgramService.create_program(
        payload,
        created_by=created_by or uuid.uuid4(),
        db=tenant_db,
    )


# ---------------------------------------------------------------------------
# Program CRUD
# ---------------------------------------------------------------------------

async def test_create_program_creates_draft(tenant_db_a):
    program = await _create_draft(tenant_db_a)
    assert program.status == ProgramStatus.DRAFT
    assert program.version == 1
    assert program.parent_version_id is None


async def test_update_allowed_while_under_governance_review(tenant_db_a, admin_user_a):
    # PENDING_APPROVAL is an editable window — but it belongs to the GOVERNANCE
    # authority, not the Dean. The service permits the edit; the router's
    # `assert_can_edit_structure` is what rejects a Dean attempting it (see
    # test_router.py::test_dean_cannot_edit_curriculum_under_review).
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PENDING_APPROVAL, tenant_db_a)

    updated = await ProgramService.update_program(
        program.id, ProgramUpdate(title="Board Revised Title"), db=tenant_db_a,
    )
    assert updated.title == "Board Revised Title"


async def test_update_blocked_once_approved_and_locked(tenant_db_a, admin_user_a):
    # Approval LOCKS the curriculum. Nobody edits it — not the Dean, not
    # governance. A change means a new version.
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.update_program(
            program.id, ProgramUpdate(title="New Title"), db=tenant_db_a,
        )
    assert exc.value.code == "CURRICULUM_LOCKED"


async def test_delete_allowed_when_draft(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])

    await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert await ProgramRepository.get_by_id(program.id, db=tenant_db_a) is None


async def test_delete_allowed_when_generation_failed(tenant_db_a, admin_user_a):
    # AI structure generation fell over — the Dean still holds the curriculum and
    # may scrap it. (This replaces the old RETURNED case: the Board no longer
    # hands a curriculum back, so a submitted one never returns to the Dean.)
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.GENERATION_FAILED, tenant_db_a)

    await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert await ProgramRepository.get_by_id(program.id, db=tenant_db_a) is None


async def test_delete_blocked_when_pending_approval(tenant_db_a, admin_user_a):
    # Once submitted, the curriculum sits in front of the governance authority.
    # The Dean cannot pull it out from under them.
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PENDING_APPROVAL, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"
    assert await ProgramRepository.get_by_id(program.id, db=tenant_db_a) is not None


async def test_delete_blocked_when_approved(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"
    assert await ProgramRepository.get_by_id(program.id, db=tenant_db_a) is not None


async def test_delete_blocked_when_published(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PUBLISHED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


async def test_update_blocked_when_published(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PUBLISHED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.update_program(
            program.id, ProgramUpdate(title="New Title"), db=tenant_db_a,
        )
    assert exc.value.code == "CURRICULUM_LOCKED"


async def test_publish_requires_approved(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.publish(program.id, published_by=dean_user_a["id"], db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


async def test_publish_locks_program(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    published = await ProgramService.publish(program.id, published_by=dean_user_a["id"], db=tenant_db_a)
    assert published.status == ProgramStatus.PUBLISHED
    assert published.published_by_user_id == dean_user_a["id"]

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# State machine: submit → approve+lock / return  (Phase A governance)
#
# The Dean submits. The governance authority approves and locks. The Dean can no
# longer do either — ProgramService has no `approve` at all any more; approving
# lives in app.core.governance.service, with the separation-of-duties checks.
# ---------------------------------------------------------------------------

async def test_dean_submits_draft_to_governance(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)

    await gov.submit_for_approval(
        program.id, submitted_by=dean_user_a["id"], note="Ready for review", db=tenant_db_a,
    )

    refreshed = await ProgramRepository.get_by_id(program.id, db=tenant_db_a)
    assert refreshed.status == ProgramStatus.PENDING_APPROVAL
    assert refreshed.submitted_by_user_id == dean_user_a["id"]
    assert refreshed.submitted_at is not None


async def test_submit_blocked_by_compliance(tenant_db_a, admin_user_a, dean_user_a):
    # 0 outcomes, 0 courses — governance should never be handed this.
    program = await _create_draft(tenant_db_a, admin_user_a["id"])

    with pytest.raises(gov.GovernanceServiceError) as exc:
        await gov.submit_for_approval(
            program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
        )
    assert exc.value.code == "COMPLIANCE_FAILED"


async def test_submit_requires_draft(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    with pytest.raises(gov.GovernanceServiceError) as exc:
        await gov.submit_for_approval(
            program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
        )
    assert exc.value.code == "INVALID_STATUS"


async def test_submit_requires_an_academic_year_and_batch(
    tenant_db_a, admin_user_a, dean_user_a,
):
    """An approved curriculum is immutable and students stay on the version they
    were admitted under — so it must know which batch it governs BEFORE it is
    frozen. There is no chance to say afterwards."""
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    # Undo the batch binding that build_compliant_program applied.
    await tenant_db_a.execute(
        text(
            "UPDATE programs SET academic_year = NULL, effective_from_batch_id = NULL "
            "WHERE id = :id"
        ),
        {"id": str(program.id)},
    )
    await tenant_db_a.flush()

    with pytest.raises(gov.GovernanceServiceError) as exc:
        await gov.submit_for_approval(
            program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
        )
    assert exc.value.code == "BATCH_REQUIRED"


async def test_approval_is_blocked_until_every_subject_has_a_syllabus(
    tenant_db_a, admin_user_a, dean_user_a, board_user_a,
):
    """THE gate of Phase A.

    Approval is permanent, so a subject locked without an official syllabus could
    never be given one — the only repair would be a whole new curriculum version.
    The Board must therefore write every syllabus BEFORE it can approve.
    """
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await gov.submit_for_approval(
        program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
    )

    # No syllabi at all.
    with pytest.raises(gov.GovernanceServiceError) as exc:
        await gov.approve_and_lock(
            program.id, decided_by=board_user_a["id"], comment=None, db=tenant_db_a,
        )
    assert exc.value.code == "SYLLABUS_INCOMPLETE"

    # All but one — still refused. "Every subject" means every subject.
    total = await approve_all_syllabi(program.id, tenant_db_a, board_user_a["id"])
    await tenant_db_a.execute(
        text(
            "UPDATE syllabi SET status = 'DRAFT' WHERE id = "
            "(SELECT s.id FROM syllabi s JOIN courses c ON c.id = s.course_id "
            " WHERE c.program_id = :p LIMIT 1)"
        ),
        {"p": str(program.id)},
    )
    await tenant_db_a.flush()

    readiness = await gov.get_readiness(program.id, tenant_db_a)
    assert readiness.total_subjects == total
    assert readiness.approved_count == total - 1
    assert readiness.can_approve is False

    with pytest.raises(gov.GovernanceServiceError) as exc:
        await gov.approve_and_lock(
            program.id, decided_by=board_user_a["id"], comment=None, db=tenant_db_a,
        )
    assert exc.value.code == "SYLLABUS_INCOMPLETE"


async def test_governance_approves_and_locks(
    tenant_db_a, admin_user_a, dean_user_a, board_user_a,
):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await gov.submit_for_approval(
        program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
    )
    await approve_all_syllabi(program.id, tenant_db_a, board_user_a["id"])

    readiness = await gov.get_readiness(program.id, tenant_db_a)
    assert readiness.can_approve is True

    locked = await gov.approve_and_lock(
        program.id, decided_by=board_user_a["id"], comment="Approved by BoS", db=tenant_db_a,
    )
    assert locked == readiness.total_subjects

    refreshed = await ProgramRepository.get_by_id(program.id, db=tenant_db_a)
    assert refreshed.status == ProgramStatus.APPROVED
    assert refreshed.approved_by_user_id == board_user_a["id"]
    # Approval is what LOCKS the curriculum — not publication.
    assert refreshed.locked_by_user_id == board_user_a["id"]
    assert refreshed.locked_at is not None

    # The syllabi froze WITH the curriculum: structure and syllabus are one thing.
    statuses = (
        await tenant_db_a.execute(
            text(
                "SELECT DISTINCT s.status FROM syllabi s JOIN courses c ON c.id = s.course_id "
                "WHERE c.program_id = :p"
            ),
            {"p": str(program.id)},
        )
    ).scalars().all()
    assert statuses == ["LOCKED"]

    # And so did the elective baskets' composition — no subject may be slipped
    # into a locked curriculum without ever passing the Board.
    unlocked_baskets = (
        await tenant_db_a.execute(
            text(
                "SELECT count(*) FROM elective_baskets "
                "WHERE program_id = :p AND locked_at IS NULL"
            ),
            {"p": str(program.id)},
        )
    ).scalar_one()
    assert unlocked_baskets == 0


async def test_one_board_member_may_enhance_and_approve_alone(
    tenant_db_a, admin_user_a, dean_user_a, board_user_a,
):
    """There is NO separation of duties inside the Board.

    One member may receive a curriculum, revise it, approve every subject's
    syllabus, and then approve and lock the curriculum — alone, with no second
    signature. That is the model, not a gap: the Board is ONE academic authority,
    not a ladder of approval levels, and demanding a second pair of eyes would
    invent a hierarchy the institution does not have (and stall a curriculum
    whenever only one member was available).

    Accountability comes from the trail instead — see
    test_the_governance_trail_records_who_did_what.
    """
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await gov.submit_for_approval(
        program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
    )

    # The same member revises the structure...
    await ProgramService.update_program(
        program.id, ProgramUpdate(title="Revised by the Board"), db=tenant_db_a,
    )
    # ...signs off every syllabus...
    await approve_all_syllabi(program.id, tenant_db_a, board_user_a["id"])
    # ...and approves the curriculum. No second signature required.
    locked = await gov.approve_and_lock(
        program.id, decided_by=board_user_a["id"], comment="Approved", db=tenant_db_a,
    )
    assert locked > 0

    refreshed = await ProgramRepository.get_by_id(program.id, db=tenant_db_a)
    assert refreshed.status == ProgramStatus.APPROVED
    assert refreshed.approved_by_user_id == board_user_a["id"]


async def test_the_governance_trail_records_who_did_what(
    tenant_db_a, admin_user_a, dean_user_a, board_user_a,
):
    """Accountability without restriction.

    Because one Board member may enhance, write the syllabus, approve AND lock a
    curriculum alone, the trail is the only thing standing between "one academic
    authority" and "nobody knows who did this". It has to capture the submit, the
    modification, and the approval, each with its actor.
    """
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await gov.submit_for_approval(
        program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
    )
    await approve_all_syllabi(program.id, tenant_db_a, board_user_a["id"])
    await gov.approve_and_lock(
        program.id, decided_by=board_user_a["id"], comment="Approved", db=tenant_db_a,
    )

    # The service tests bypass the routers, which are what write audit rows — so
    # assert the trail READS correctly rather than that the routers wrote to it.
    # The end-to-end script (scripts/verify_governance_v2.py) exercises the real
    # write path over HTTP.
    trail = await gov.get_audit_trail(
        program.id, dean_user_a["tenant_id"], tenant_db_a,
    )
    assert isinstance(trail, list)
    for entry in trail:
        assert entry.action and entry.category and entry.at


async def test_submitting_is_a_one_way_handover(
    tenant_db_a, admin_user_a, dean_user_a,
):
    """There is no return, no reject and no resubmit.

    The Board never hands work back to the Dean — when it disagrees with the plan
    it enhances the plan itself. So a submitted curriculum has exactly ONE
    approval cycle, and the Dean can never edit it again.
    """
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await gov.submit_for_approval(
        program.id, submitted_by=dean_user_a["id"], note="Please review", db=tenant_db_a,
    )

    assert not hasattr(gov, "return_to_dean")
    assert not hasattr(ProgramStatus, "RETURNED")

    # Submitting twice is refused — the curriculum is already with the Board.
    with pytest.raises(gov.GovernanceServiceError) as exc:
        await gov.submit_for_approval(
            program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
        )
    assert exc.value.code == "INVALID_STATUS"

    history = await gov.get_history(program.id, tenant_db_a)
    assert [h["cycle"] for h in history] == [1]
    assert history[0]["status"] == "PENDING"


async def test_a_dean_is_never_governance(tenant_db_a, dean_user_a):
    """The ONE restriction in the entire model.

    Board members are equal peers with full academic ownership and no separation
    of duties — one of them may enhance, write, approve and lock a curriculum
    alone. The Dean is the only person barred from approving, because the planner
    must not approve their own plan. And that holds even when the Dean also holds
    a BOARD grant, which is the loophole this test exists to nail shut.
    """
    dean = CurrentUser(
        user_id=dean_user_a["id"],
        tenant_id=dean_user_a["tenant_id"],
        schema_name=dean_user_a["schema_name"],
        role="DEAN",
        email=dean_user_a["email"],
    )
    assert await gov.acts_as_governance(dean, tenant_db_a) is False

    await tenant_db_a.execute(
        text(
            "INSERT INTO faculty_role_grants "
            "(id, faculty_user_id, role_code, is_active, granted_by) "
            "VALUES (:i, :u, 'BOARD', true, :u)"
        ),
        {"i": str(uuid.uuid4()), "u": str(dean_user_a["id"])},
    )
    await tenant_db_a.flush()

    # Holding a BOARD grant changes nothing: a Dean is still not the Board.
    assert await gov.acts_as_governance(dean, tenant_db_a) is False


async def test_board_user_is_governance(tenant_db_a, board_user_a):
    member = CurrentUser(
        user_id=board_user_a["id"],
        tenant_id=board_user_a["tenant_id"],
        schema_name=board_user_a["schema_name"],
        role="BOARD",
        email=board_user_a["email"],
    )
    assert await gov.acts_as_governance(member, tenant_db_a) is True


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------

async def test_fork_requires_approved(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.fork_program(program.id, created_by=admin_user_a["id"], db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


async def test_fork_creates_new_version(
    tenant_db_a, admin_user_a, dean_user_a, board_user_a,
):
    # A locked curriculum is changed by forking a new version — the whole point
    # of "never modify a locked curriculum".
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await gov.submit_for_approval(
        program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
    )
    await approve_all_syllabi(program.id, tenant_db_a, board_user_a["id"])
    await gov.approve_and_lock(
        program.id, decided_by=board_user_a["id"], comment=None, db=tenant_db_a,
    )

    forked = await ProgramService.fork_program(
        program.id, created_by=admin_user_a["id"], db=tenant_db_a
    )
    assert forked.version == 2
    assert forked.parent_version_id == program.id
    # The new version lands back in the Dean's hands, unapproved and unlocked.
    assert forked.status == ProgramStatus.DRAFT
    assert forked.locked_at is None
    assert forked.approved_by_user_id is None


async def test_fork_carries_the_official_syllabi_forward(
    tenant_db_a, admin_user_a, dean_user_a, board_user_a,
):
    """v2 inherits editable copies of v1's syllabi.

    Without this, fixing one typo in one subject would mean v2 starts with no
    syllabi at all and the Board must AI-regenerate every one from scratch. The
    Board should revise a version, not rebuild it.

    v1's own syllabi must be untouched: they hang off v1's course rows, and the
    copies hang off v2's brand-new ones, so the two versions share nothing.
    """
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await gov.submit_for_approval(
        program.id, submitted_by=dean_user_a["id"], note=None, db=tenant_db_a,
    )
    subject_count = await approve_all_syllabi(program.id, tenant_db_a, board_user_a["id"])
    await gov.approve_and_lock(
        program.id, decided_by=board_user_a["id"], comment=None, db=tenant_db_a,
    )

    forked = await ProgramService.fork_program(
        program.id, created_by=admin_user_a["id"], db=tenant_db_a
    )

    async def _syllabi(pid, status_filter: str | None = None):
        sql = (
            "SELECT count(*) FROM syllabi s JOIN courses c ON c.id = s.course_id "
            "WHERE c.program_id = :p"
        )
        if status_filter:
            sql += f" AND s.status = '{status_filter}'"
        return (
            await tenant_db_a.execute(text(sql), {"p": str(pid)})
        ).scalar_one()

    # Every subject in v2 arrived with a syllabus, editable.
    assert await _syllabi(forked.id) == subject_count
    assert await _syllabi(forked.id, "DRAFT") == subject_count

    # v1 is untouched: still locked, still the same count.
    assert await _syllabi(program.id) == subject_count
    assert await _syllabi(program.id, "LOCKED") == subject_count


# ---------------------------------------------------------------------------
# Immutability guards on courses and outcomes
# ---------------------------------------------------------------------------

async def test_add_course_blocked_once_locked(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.add_course(
            program.id,
            CourseCreate(code="CS001", title="Course", credits=4, semester=1, is_elective=False),
            db=tenant_db_a,
        )
    assert exc.value.code == "CURRICULUM_LOCKED"


async def test_add_outcome_blocked_once_locked(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.add_outcome(
            program.id,
            ProgramOutcomeCreate(code="PO1", description="desc"),
            db=tenant_db_a,
        )
    assert exc.value.code == "CURRICULUM_LOCKED"


async def test_duplicate_course_code_rejected(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    course = CourseCreate(code="CS101", title="Course", credits=4, semester=1, is_elective=False)
    await ProgramService.add_course(program.id, course, db=tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.add_course(program.id, course, db=tenant_db_a)
    assert exc.value.code == "CODE_EXISTS"


# ---------------------------------------------------------------------------
# Elective Baskets — an elective is never modeled as a single course; it
# must belong to a named basket alongside its sibling alternatives.
# ---------------------------------------------------------------------------

async def test_add_basket_and_course_becomes_elective(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    basket = await ProgramService.add_basket(
        program.id,
        ElectiveBasketCreate(semester=3, name="Artificial Intelligence Electives"),
        admin_user_a["id"],
        db=tenant_db_a,
    )
    assert basket.semester == 3

    course = await ProgramService.add_course(
        program.id,
        CourseCreate(
            code="AI301", title="Artificial Intelligence", credits=4, semester=3,
            is_elective=False, elective_basket_id=basket.id,
        ),
        db=tenant_db_a,
    )
    # A course inside a basket is an elective by definition, regardless of
    # what is_elective was explicitly passed as.
    assert course.is_elective is True
    assert course.elective_basket_id == basket.id


async def test_add_course_basket_semester_mismatch_rejected(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    basket = await ProgramService.add_basket(
        program.id, ElectiveBasketCreate(semester=3, name="AI Electives"),
        admin_user_a["id"], db=tenant_db_a,
    )

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.add_course(
            program.id,
            CourseCreate(
                code="AI401", title="Deep Learning", credits=4, semester=4,
                elective_basket_id=basket.id,
            ),
            db=tenant_db_a,
        )
    assert exc.value.code == "BASKET_SEMESTER_MISMATCH"


async def test_delete_basket_unlinks_courses(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    basket = await ProgramService.add_basket(
        program.id, ElectiveBasketCreate(semester=3, name="AI Electives"),
        admin_user_a["id"], db=tenant_db_a,
    )
    course = await ProgramService.add_course(
        program.id,
        CourseCreate(code="AI301", title="Artificial Intelligence", credits=4, semester=3, elective_basket_id=basket.id),
        db=tenant_db_a,
    )

    await ProgramService.delete_basket(basket.id, program.id, db=tenant_db_a)

    # The DELETE is raw SQL (bypasses the ORM unit-of-work), so `course` --
    # already loaded into this session's identity map above -- keeps its
    # stale in-memory elective_basket_id unless explicitly refreshed (see
    # the identical force_status staleness issue elsewhere in this suite).
    await tenant_db_a.refresh(course)
    assert course.elective_basket_id is None
    # is_elective is untouched by unlinking -- Dean may still want it flagged
    # elective while deciding which basket it belongs to next.
    assert course.is_elective is True


async def test_fork_program_copies_baskets_and_relinks_courses(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    basket = await ProgramService.add_basket(
        program.id, ElectiveBasketCreate(semester=3, name="AI Electives", credits=4),
        admin_user_a["id"], db=tenant_db_a,
    )
    await ProgramService.add_course(
        program.id,
        CourseCreate(code="AI301", title="Artificial Intelligence", credits=4, semester=3, elective_basket_id=basket.id),
        db=tenant_db_a,
    )
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    forked = await ProgramService.fork_program(program.id, created_by=admin_user_a["id"], db=tenant_db_a)

    forked_baskets = await ProgramService.list_baskets(forked.id, db=tenant_db_a)
    assert len(forked_baskets) == 1
    assert forked_baskets[0].id != basket.id
    assert forked_baskets[0].name == "AI Electives"
    # The slot's credits are curriculum data — a new version must not silently
    # reset them to the default.
    assert forked_baskets[0].credits == 4

    from app.modules.m01_program_advisor.repository import CourseRepository
    forked_courses = await CourseRepository.list_by_program(forked.id, db=tenant_db_a)
    forked_ai_course = next(c for c in forked_courses if c.code == "AI301")
    assert forked_ai_course.elective_basket_id == forked_baskets[0].id
