"""
M04 Assignments — router.

RBAC
----
  _WRITE    = ADMIN + FACULTY   (create/update/publish/close, submit, return)
  _READ     = ADMIN + DEAN + FACULTY
  _EVALUATE = ADMIN + FACULTY + EVALUATOR  (grade — narrowed further per
              submission against the M09.6 allocation ledger)
  _ALLOCATE = ADMIN + DEAN      (assign evaluator, finalize marks)
  _STUDENT  = STUDENT           (list, view, submit, view own result)

Evaluation hand-off
-------------------
  Faculty creates (nominating evaluator(s)) -> students submit, and each
  submission raises its own evaluator work item -> Faculty submits -> Evaluator
  evaluates -> a human finalizes the marks.

  Allocation reuses the M09.6 assignment engine (evaluation_assignments,
  target_entity='assignment_submission') and the existing EVALUATOR role, so
  there is one ledger of evaluation work and no new role. Unlike exam scripts,
  coursework evaluation is NOT anonymous — the evaluator sees the student, as
  the owning faculty always has.

  The faculty's nomination (assignments.evaluator_user_ids) is a nomination, not
  an allocation: it says who this coursework routes to, and a student's
  submission turns it into a work item through the same engine. Where nobody is
  nominated, nothing changes — the department allocates by hand, and it may still
  override a nomination either way.

Router is pure HTTP glue. All business logic lives in service.py.

Endpoint summary (faculty)
--------------------------
  POST   /assignments                         create assignment
  GET    /assignments                         list assignments
  GET    /assignments/{id}                    get detail
  PUT    /assignments/{id}                    update (DRAFT only)
  POST   /assignments/{id}/publish            publish (notifies enrolled students)
  POST   /assignments/{id}/close              close
  POST   /assignments/{id}/submit             hand to department for evaluation
  GET    /assignments/{id}/submissions        list submissions
  GET    /assignments/{id}/statistics         submission/grading stats
  PATCH  /submissions/{id}/grade              record marks + feedback
  POST   /submissions/{id}/return             return to student (notifies student)
  GET    /submissions/{id}/file-url           presigned download (faculty)

Endpoint summary (department / admin)
-------------------------------------
  GET    /assignments/evaluators              users holding EVALUATOR
  POST   /submissions/{id}/evaluator          allocate one submission
  POST   /assignments/{id}/finalize           ratify the marks (human decision)

Endpoint summary (evaluator)
----------------------------
  GET    /assignments/evaluator/my-work       coursework allocated to me

Endpoint summary (student)
--------------------------
  GET    /student                             list published/closed assignments
  GET    /student/{id}                        detail
  POST   /student/{id}/submit                 submit (enforces max_attempts/deadline)
  GET    /student/submissions/my              my submissions (all attempts)
  GET    /student/submissions/{id}/result     view graded/returned result only
  GET    /student/submissions/{id}/file-url   presigned download (own submission)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.notifications.dispatch import notify_section_students, notify_user
from app.core.notifications.models import NotificationType
from app.modules.m04_assignments.models import AssignmentStatus, SubmissionStatus
from app.modules.m04_assignments.repository import (
    COURSEWORK_TARGET_ENTITY,
    AiEvaluationRepository,
    AssignmentRepository,
    SubmissionRepository,
)
from app.modules.m04_assignments.schemas import (
    AssignEvaluatorRequest,
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentProgress,
    AssignmentResponse,
    AssignmentStatistics,
    AssignmentUpdate,
    AiEvaluationResponse,
    EligibleEvaluator,
    EvaluationCenterProgress,
    EvaluationCenterResponse,
    EvaluationCenterStudent,
    GradeSubmissionRequest,
    MyCourseworkEvaluation,
    MyTeachingCourse,
    SubmissionCreate,
    SubmissionDetailResponse,
    SubmissionListResponse,
    SubmissionResponse,
)
from app.modules.m04_assignments.service import (
    AssignmentService,
    AssignmentServiceError,
    SubmissionService,
    _is_privileged,
)

router = APIRouter(tags=["assignments"])

_WRITE   = require_roles(TenantRole.ADMIN, TenantRole.FACULTY)
_READ    = require_roles(TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_STUDENT = require_roles(TenantRole.STUDENT)
# Evaluation of coursework is done by the allocated evaluator, so EVALUATOR joins
# the graders. Who may mark which submission is enforced in the service against
# the M09.6 allocation ledger — the role alone grants nothing.
_EVALUATE = require_roles(TenantRole.ADMIN, TenantRole.FACULTY, TenantRole.EVALUATOR)
# READ access to the ADVISORY AI evaluation — the Dean oversees the department and
# may view it exactly like an Admin, alongside the graders. This is view-only:
# grading and finalization stay on _EVALUATE / the dedicated endpoints, so a Dean
# still cannot grade or finalize. assert_may_view narrows to the relevant coursework.
_AI_READ = require_roles(
    TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.EVALUATOR
)
# Allocating evaluators is a department act: the Dean owns the department, Admin
# owns the institution. Faculty deliberately cannot allocate their own evaluator.
_ALLOCATE = require_roles(TenantRole.ADMIN, TenantRole.DEAN)


def _svc_error(exc: AssignmentServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"error": exc.code, "message": exc.message})


async def _assert_may_manage(
    assignment_id: UUID, current_user: CurrentUser, db: AsyncSession
) -> None:
    """Load the assignment and check the caller is allowed to change it.

    Publishing, closing, submitting and editing are the owning faculty's acts (or
    the department's). A peer faculty member is none of those things.
    """
    assignment = await AssignmentService.get(assignment_id, db=db)
    await AssignmentService.assert_may_manage(
        assignment,
        actor_user_id=current_user.user_id,
        # Authorization is decided on the ACTIVE workspace, never the base login
        # role — a DEAN acting in the Faculty workspace must behave as Faculty.
        actor_role=current_user.viewing_role,
    )


async def _course_context(syllabus_id: UUID | None, db: AsyncSession) -> tuple[str | None, str | None]:
    """Resolve course title + code from syllabi -> courses chain. Fails silently."""
    if not syllabus_id:
        return None, None
    try:
        row = (
            await db.execute(
                text(
                    "SELECT c.title, c.code FROM syllabi s "
                    "JOIN courses c ON c.id = s.course_id WHERE s.id = :sid"
                ),
                {"sid": str(syllabus_id)},
            )
        ).fetchone()
        if row:
            return row[0], row[1]
    except Exception:
        pass
    return None, None


async def _assert_is_evaluator(user_id: UUID, db: AsyncSession) -> None:
    """The allocated user must actually hold the EVALUATOR responsibility.

    Mirrors how M07 validates a Guide: either a standalone EVALUATOR account, or
    a FACULTY account carrying an active EVALUATOR grant. No new role is
    introduced — this is the existing one.
    """
    from sqlalchemy import select
    from app.core.auth.dependencies import user_has_grant
    from app.core.auth.models import User

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    ok = user is not None and user.is_active and (
        user.role == TenantRole.EVALUATOR
        or (user.role == TenantRole.FACULTY and await user_has_grant(db, user.id, "EVALUATOR"))
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_EVALUATOR",
                "message": "That user does not hold the EVALUATOR responsibility. "
                           "Grant it from Admin → Users (role EVALUATOR, or a "
                           "FACULTY member granted the EVALUATOR responsibility).",
            },
        )


async def _student_name(student_user_id: UUID, db: AsyncSession) -> str | None:
    row = (
        await db.execute(
            text("SELECT full_name FROM users WHERE id = :uid"), {"uid": str(student_user_id)}
        )
    ).one_or_none()
    return row[0] if row else None


# ===========================================================================
# Faculty — Assignment CRUD
# ===========================================================================

@router.post("", response_model=AssignmentResponse, status_code=201)
async def create_assignment(
    payload: AssignmentCreate,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    # A nominee who does not hold EVALUATOR would produce a work item nobody is
    # allowed to act on — reject it here rather than at submission time, when the
    # faculty is no longer around to fix it.
    for evaluator_id in payload.evaluator_user_ids:
        await _assert_is_evaluator(evaluator_id, db)

    try:
        assignment = await AssignmentService.create(
            payload, created_by_user_id=current_user.user_id, db=db
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_ASSIGNMENT_CREATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="assignment",
        target_id=str(assignment.id),
        metadata={
            "title": assignment.title,
            "type": assignment.assignment_type,
            "evaluator_user_ids": [str(e) for e in payload.evaluator_user_ids],
            "question_count": len(payload.questions),
            "has_question_paper": bool(assignment.question_paper_url),
        },
    )
    return AssignmentResponse.model_validate(assignment)


@router.get("", response_model=AssignmentListResponse)
async def list_assignments(
    syllabus_id: UUID | None = Query(None),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    # Coursework belongs to the faculty who set it: a faculty member sees their
    # own and nobody else's. The Dean owns the department and Admin the
    # institution, so both keep the full list — but ONLY while acting in that
    # workspace. Privilege is judged on the ACTIVE workspace (viewing_role), so a
    # DEAN switched into the Faculty workspace is scoped exactly like Faculty.
    items, total = await AssignmentService.list_assignments(
        db=db, syllabus_id=syllabus_id, status=status, offset=offset, limit=limit,
        created_by_user_id=(
            None if _is_privileged(current_user.viewing_role) else current_user.user_id
        ),
    )
    # Live progress for the whole page in three grouped queries — the faculty who
    # set this coursework must see how far it has got without opening each one.
    progress = await SubmissionRepository.progress_for_assignments(
        [a.id for a in items], db=db
    )
    # Cohort size is per COURSE, so resolve it once per distinct syllabus rather
    # than once per assignment — several assignments usually share one.
    cohort: dict[UUID, int] = {}
    for sid in {a.syllabus_id for a in items if a.syllabus_id}:
        cohort[sid] = await AssignmentRepository.enrolled_student_count_for_syllabus(
            sid, db=db
        )

    resp_items = [
        AssignmentResponse.model_validate(a).model_copy(update={
            "progress": AssignmentProgress(
                total_students=cohort.get(a.syllabus_id, 0) if a.syllabus_id else 0,
                **progress.get(a.id, {}),
            ),
        })
        for a in items
    ]
    return AssignmentListResponse(
        items=resp_items, total=total, offset=offset, limit=limit,
    )


@router.get("/evaluators", response_model=list[EligibleEvaluator])
async def list_eligible_evaluators(
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Users who may be allocated coursework to evaluate.

    The existing EVALUATOR responsibility, held either as a standalone EVALUATOR
    account or as a FACULTY account with an active EVALUATOR grant — the same
    two shapes M07 accepts for a Guide. No new role.

    Readable by faculty because they nominate the evaluator(s) for the coursework
    they set. Reading the directory is not allocating: the allocation ledger is
    still written only by the department (_ALLOCATE) or by a student's submission
    raising the faculty's own nomination.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT u.id, u.full_name, u.email, u.role
                FROM users u
                WHERE u.is_active = true
                  AND (
                        u.role = 'EVALUATOR'
                     OR (u.role = 'FACULTY' AND EXISTS (
                            SELECT 1 FROM faculty_role_grants g
                            WHERE g.faculty_user_id = u.id
                              AND g.role_code = 'EVALUATOR'
                              AND g.is_active = true
                        ))
                  )
                ORDER BY u.full_name
                """
            )
        )
    ).fetchall()
    return [
        EligibleEvaluator(id=r[0], full_name=r[1], email=r[2], role=r[3])
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Faculty — my teaching courses (for the create form's scoped course picker).
# Declared BEFORE GET /{assignment_id} so the literal path is not captured by the
# UUID path param.
# ---------------------------------------------------------------------------

@router.get("/my-teaching-courses", response_model=list[MyTeachingCourse])
async def my_teaching_courses(
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """The caller's OWN teaching courses (from subject_assignments), each with the
    latest LOCKED/APPROVED syllabus resolved — so the create form binds
    syllabus_id automatically and never lists institution-wide courses. Scoped to
    the active workspace user (a Dean acting as Faculty sees only their own load)."""
    rows = await AssignmentRepository.teaching_courses_for_faculty(
        current_user.user_id, db=db
    )
    return [
        MyTeachingCourse(
            course_id=r["course_id"],
            course_code=r["course_code"],
            course_title=r["course_title"],
            semester=r["semester"],
            section_id=r["section_id"],
            section_name=r["section_name"],
            syllabus_id=r["syllabus_id"],
            has_approved_syllabus=r["syllabus_id"] is not None,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Student — assignment list.
# MUST be declared BEFORE GET /{assignment_id}: FastAPI matches routes in
# definition order, so the literal "/student" path would otherwise be captured
# by the UUID path param and 422/403 (this was the "Failed to load assignments"
# bug). The other /student/* routes are 2+ segments and do not collide.
# ---------------------------------------------------------------------------

@router.get("/student", response_model=AssignmentListResponse)
async def student_list_assignments(
    syllabus_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Published/closed coursework for the courses this student is ENROLLED in —
    and nothing else. A student enrolled in nothing sees an empty list, never the
    whole institution."""
    enrolled = await AssignmentRepository.enrolled_syllabus_ids_for_student(
        current_user.user_id, db=db
    )
    items, total = await AssignmentService.list_assignments(
        db=db,
        syllabus_id=syllabus_id,
        syllabus_ids=enrolled,
        statuses=["PUBLISHED", "CLOSED"],
        offset=offset, limit=limit,
    )
    return AssignmentListResponse(
        items=[AssignmentResponse.model_validate(a) for a in items],
        total=total, offset=offset, limit=limit,
    )


@router.get("/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(
    assignment_id: UUID,
    # _EVALUATE, not _READ: an allocated evaluator must be able to see what the
    # work on their desk belongs to. assert_may_view narrows it from there.
    current_user: CurrentUser = Depends(_EVALUATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
        await AssignmentService.assert_may_view(
            assignment,
            actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    created_by_name = await _student_name(assignment.created_by_user_id, db)
    evaluator_names = [
        name
        for eid in (assignment.evaluator_user_ids or [])
        if (name := await _student_name(eid, db))
    ]
    # Same derived progress the dashboard shows, so Assignment Details always
    # reflects the latest evaluation state rather than only the assignment record.
    prog = await SubmissionRepository.progress_for_assignments([assignment.id], db=db)
    total_students = (
        await AssignmentRepository.enrolled_student_count_for_syllabus(
            assignment.syllabus_id, db=db
        )
        if assignment.syllabus_id else 0
    )
    return AssignmentResponse.model_validate(assignment).model_copy(
        update={
            "course_title": course_title,
            "course_code": course_code,
            "created_by_name": created_by_name,
            "evaluator_names": evaluator_names,
            "progress": AssignmentProgress(
                total_students=total_students, **prog.get(assignment.id, {})
            ),
        }
    )


@router.put("/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: UUID,
    payload: AssignmentUpdate,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    for evaluator_id in (payload.evaluator_user_ids or []):
        await _assert_is_evaluator(evaluator_id, db)

    try:
        await _assert_may_manage(assignment_id, current_user, db)
        assignment = await AssignmentService.update(assignment_id, payload, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_ASSIGNMENT_UPDATED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment", target_id=str(assignment_id),
    )
    return AssignmentResponse.model_validate(assignment)


@router.delete("/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Delete a DRAFT assignment.

    Only the owning faculty (judged on the active workspace) or a privileged
    actor may delete, and only while the assignment is a DRAFT — a published
    assignment cannot be deleted (the service returns 409).
    """
    try:
        await AssignmentService.delete(
            assignment_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_ASSIGNMENT_DELETED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment", target_id=str(assignment_id),
    )


@router.post("/{assignment_id}/publish", response_model=AssignmentResponse)
async def publish_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        await _assert_may_manage(assignment_id, current_user, db)
        assignment = await AssignmentService.publish(assignment_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_ASSIGNMENT_PUBLISHED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment", target_id=str(assignment_id),
        metadata={"max_marks": float(assignment.max_marks)},
    )

    if assignment.syllabus_id:
        section_ids = await AssignmentRepository.enrolled_section_ids_for_syllabus(
            assignment.syllabus_id, db=db
        )
        for section_id in section_ids:
            await notify_section_students(
                db,
                notification_type=NotificationType.ASSIGNMENT_PUBLISHED,
                section_id=section_id,
                title=f"New assignment: {assignment.title}",
                body=f"\"{assignment.title}\" has been published."
                     + (f" Due {assignment.due_date:%d %b %Y, %H:%M}." if assignment.due_date else ""),
                entity_type="Assignment",
                entity_id=str(assignment.id),
            )

    # Notify the nominated evaluators immediately, so they can open the assignment
    # directly (before any student submits). Submissions then arrive in their
    # queue as students hand them in.
    if assignment.evaluator_user_ids:
        course_title, course_code = await _course_context(assignment.syllabus_id, db)
        faculty_name = await _student_name(assignment.created_by_user_id, db)
        due = f" Due {assignment.due_date:%d %b %Y, %H:%M}." if assignment.due_date else ""
        course = f" ({course_code} — {course_title})" if course_title else ""
        by = f", set by {faculty_name}" if faculty_name else ""
        for ev in assignment.evaluator_user_ids:
            await notify_user(
                db,
                notification_type=NotificationType.ASSIGNMENT_EVALUATOR_ASSIGNED,
                recipient_user_id=ev if isinstance(ev, UUID) else UUID(str(ev)),
                title=f"You are an evaluator: {assignment.title}",
                body=(f"You have been assigned to evaluate \"{assignment.title}\"{course}{by}."
                      f"{due} You can open it now; submissions will appear in your queue."),
                entity_type="Assignment",
                entity_id=str(assignment.id),
            )
    return AssignmentResponse.model_validate(assignment)


@router.post("/{assignment_id}/close", response_model=AssignmentResponse)
async def close_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        await _assert_may_manage(assignment_id, current_user, db)
        assignment = await AssignmentService.close(assignment_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_ASSIGNMENT_CLOSED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment", target_id=str(assignment_id),
    )
    return AssignmentResponse.model_validate(assignment)


# ===========================================================================
# Evaluation hand-off
#
#   Faculty creates -> Faculty submits -> Dept/Admin assigns Evaluator
#   -> Evaluator evaluates -> Marks finalized
#
# Evaluator allocation reuses the M09.6 assignment engine and the existing
# EVALUATOR role; nothing new is introduced for either. Unlike exam scripts,
# coursework evaluation is NOT anonymous — the evaluator sees the student, the
# same as the faculty always has.
# ===========================================================================

@router.post("/{assignment_id}/submit", response_model=AssignmentResponse)
async def submit_for_evaluation(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Faculty hands a closed assignment to the department for evaluation."""
    try:
        await _assert_may_manage(assignment_id, current_user, db)
        assignment = await AssignmentService.submit_for_evaluation(
            assignment_id, actor_user_id=current_user.user_id, db=db
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_ASSIGNMENT_SUBMITTED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment", target_id=str(assignment_id),
    )
    return AssignmentResponse.model_validate(assignment)


@router.get("/evaluator/my-work", response_model=list[MyCourseworkEvaluation])
async def my_coursework_evaluations(
    current_user: CurrentUser = Depends(_EVALUATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """The coursework currently allocated to the calling evaluator.

    Coursework work items live in the M09.6 ledger like every other kind of
    evaluation work, but that ledger only knows a target_id. This resolves those
    ids back to the coursework they point at so "My Evaluations" can show
    coursework beside scripts and labs, from one list, without any caller having
    to know how coursework stores itself.

    Read-only, and self-scoped: an evaluator sees their own desk and nobody
    else's.
    """
    # Assignment-centric: return every assignment this evaluator is NOMINATED for
    # (assignments.evaluator_user_ids) that is open for evaluation — regardless of
    # whether any student has submitted yet. This is what lets the evaluator open
    # and prepare the moment the faculty publishes. Per-evaluator counts summarise
    # how much of their allocated work is done.
    eid = str(current_user.user_id)
    rows = (
        await db.execute(
            text(
                """
                SELECT a.id            AS assignment_id,
                       a.title         AS assignment_title,
                       a.status        AS assignment_status,
                       a.max_marks     AS max_marks,
                       a.due_date      AS due_date,
                       jsonb_array_length(COALESCE(a.questions, '[]'::jsonb)) AS question_count,
                       c.title         AS course_title,
                       c.code          AS course_code,
                       c.semester      AS semester,
                       u.full_name     AS faculty_name,
                       (SELECT string_agg(DISTINCT sec.name, ', ')
                          FROM subject_assignments sa
                          JOIN acad_sections sec ON sec.id = sa.section_id
                         WHERE sa.course_id = c.id AND sa.is_active = true) AS sections,
                       -- Comma-separated evaluator display names (nominees).
                       (SELECT string_agg(u2.full_name, ', ')
                          FROM jsonb_array_elements_text(
                                 COALESCE(a.evaluator_user_ids, '[]'::jsonb)) ev
                          JOIN users u2 ON u2.id = ev::uuid) AS evaluator_names,
                       -- Assignment-level progress (the whole class, not my slice).
                       (SELECT COUNT(DISTINCT ae.student_id) FROM acad_enrollments ae
                         WHERE ae.is_active = true
                           AND ae.section_id IN (
                               SELECT sa2.section_id FROM subject_assignments sa2
                                WHERE sa2.course_id = c.id AND sa2.is_active = true)
                       ) AS total_students,
                       (SELECT COUNT(DISTINCT s.student_user_id) FROM assignment_submissions s
                         WHERE s.assignment_id = a.id) AS submitted_students,
                       (SELECT COUNT(DISTINCT s.student_user_id) FROM assignment_submissions s
                         WHERE s.assignment_id = a.id
                           AND s.marks_obtained IS NOT NULL) AS reviewed_students,
                       (SELECT COUNT(*) FROM assignment_submissions s
                         WHERE s.assignment_id = a.id) AS total_submissions,
                       (SELECT COUNT(DISTINCT ea.target_id) FROM evaluation_assignments ea
                         WHERE ea.target_entity = :te AND ea.evaluator_id = :eid
                           AND ea.target_id IN (SELECT id FROM assignment_submissions
                                                 WHERE assignment_id = a.id)) AS allocated_to_me,
                       (SELECT COUNT(DISTINCT ea.target_id) FROM evaluation_assignments ea
                          JOIN assignment_submissions s2 ON s2.id = ea.target_id
                         WHERE ea.target_entity = :te AND ea.evaluator_id = :eid
                           AND s2.assignment_id = a.id
                           AND s2.marks_obtained IS NOT NULL) AS graded_by_me
                FROM assignments a
                LEFT JOIN syllabi syl ON syl.id = a.syllabus_id
                LEFT JOIN courses c   ON c.id = syl.course_id
                LEFT JOIN users u     ON u.id = a.created_by_user_id
                -- :eid_text is a DISTINCT bind from :eid on purpose. :eid is
                -- compared to the uuid column ea.evaluator_id, so asyncpg infers
                -- it as uuid; reusing it here would resolve to the non-existent
                -- jsonb_exists(jsonb, uuid). A separate text bind keeps this the
                -- jsonb_exists(jsonb, text) that actually exists.
                WHERE jsonb_exists(a.evaluator_user_ids, :eid_text)
                  AND a.status = ANY(:statuses)
                ORDER BY a.due_date NULLS LAST, a.title
                """
            ),
            {
                "te":       COURSEWORK_TARGET_ENTITY,
                "eid":      eid,
                "eid_text": eid,
                "statuses": ["PUBLISHED", "CLOSED", "SUBMITTED"],
            },
        )
    ).mappings().all()

    out = []
    for r in rows:
        d = dict(r)
        d["pending_for_me"] = max(0, int(d.get("allocated_to_me") or 0) - int(d.get("graded_by_me") or 0))
        # Assignment-level progress for the home card (whole class).
        total_students = int(d.get("total_students") or 0)
        submitted_students = int(d.get("submitted_students") or 0)
        reviewed_students = int(d.get("reviewed_students") or 0)
        d["pending_submission"] = max(0, total_students - submitted_students)
        d["pending_review"] = max(0, submitted_students - reviewed_students)
        out.append(MyCourseworkEvaluation(**d))
    return out


@router.get("/{assignment_id}/evaluation-center", response_model=EvaluationCenterResponse)
async def evaluation_center(
    assignment_id: UUID,
    # _EVALUATE: the assignment's creator, the department, or a nominated/allocated
    # evaluator. assert_may_view narrows from there — a nominee may open it from
    # publish, before any student submits.
    current_user: CurrentUser = Depends(_EVALUATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """One assignment's full class roster + live progress — the coursework
    Evaluation Center. Backed by the assignment (visible from publish) and the
    enrollment roster, so every student appears whether or not they submitted.
    """
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
        await AssignmentService.assert_may_view(
            assignment,
            actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    created_by_name = await _student_name(assignment.created_by_user_id, db)
    evaluator_names = [
        name
        for eid in (assignment.evaluator_user_ids or [])
        if (name := await _student_name(eid, db))
    ]
    assignment_resp = AssignmentResponse.model_validate(assignment).model_copy(
        update={
            "course_title": course_title,
            "course_code": course_code,
            "created_by_name": created_by_name,
            "evaluator_names": evaluator_names,
        }
    )

    # Course semester (assignments don't carry it — resolve via syllabus -> course).
    semester: int | None = None
    if assignment.syllabus_id is not None:
        srow = (
            await db.execute(
                text(
                    "SELECT c.semester FROM syllabi s "
                    "JOIN courses c ON c.id = s.course_id WHERE s.id = :sid"
                ),
                {"sid": str(assignment.syllabus_id)},
            )
        ).one_or_none()
        semester = srow[0] if srow else None

    roster = await AssignmentRepository.evaluation_roster(
        assignment_id, assignment.syllabus_id, db=db
    )
    students: list[EvaluationCenterStudent] = []
    submitted = reviewed = ai_completed = ai_failed = 0
    for r in roster:
        has_sub = r["submission_id"] is not None
        graded = r["marks_obtained"] is not None
        if has_sub:
            submitted += 1
        if graded:
            reviewed += 1
        ai_state = r.get("ai_status")
        if ai_state == "COMPLETED":
            ai_completed += 1
        elif ai_state == "FAILED":
            ai_failed += 1
        evaluator_id = (
            await AssignmentRepository.active_evaluator_for_submission(r["submission_id"], db=db)
            if has_sub else None
        )
        # Display status the evaluator queue understands. UNDER_REVIEW = submitted
        # and allocated to an evaluator, but not yet graded.
        if graded:
            disp_status = "REVIEWED"
        elif evaluator_id is not None:
            disp_status = "UNDER_REVIEW"
        elif has_sub:
            disp_status = "SUBMITTED"
        else:
            disp_status = "NOT_SUBMITTED"
        students.append(
            EvaluationCenterStudent(
                student_user_id=r["student_user_id"],
                student_name=r["student_name"],
                submission_status=disp_status,
                submission_id=r["submission_id"],
                is_late=bool(r["is_late"]) if r["is_late"] is not None else False,
                submitted_at=r["submitted_at"],
                marks_obtained=r["marks_obtained"],
                graded_at=r.get("graded_at"),
                ai_status=ai_state,
                evaluator_user_id=evaluator_id,
                evaluator_name=await _student_name(evaluator_id, db) if evaluator_id else None,
            )
        )

    total = len(students)
    progress = EvaluationCenterProgress(
        total_students=total,
        submitted=submitted,
        pending_submission=max(0, total - submitted),
        reviewed=reviewed,
        pending_review=max(0, submitted - reviewed),
        ai_completed=ai_completed,
        ai_failed=ai_failed,
    )
    return EvaluationCenterResponse(
        assignment=assignment_resp, semester=semester, progress=progress, students=students
    )


@router.post("/submissions/{submission_id}/evaluator", status_code=201)
async def assign_evaluator(
    submission_id: UUID,
    payload: AssignEvaluatorRequest,
    current_user: CurrentUser = Depends(_ALLOCATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Allocate one submission to one evaluator (Department/Admin).

    Delegates to the M09.6 assignment engine so coursework shares the one
    evaluation ledger — including its duplicate-allocation guard and its
    reassignment audit trail — instead of growing a second one.
    """
    from app.modules.m09_paper_admin.assignment_schemas import AssignmentCreateRequest
    from app.modules.m09_paper_admin.assignment_service import (
        AssignmentError,
        AssignmentService as EvaluationAssignmentService,
    )
    from app.modules.m04_assignments.repository import COURSEWORK_TARGET_ENTITY

    try:
        submission = await SubmissionService.get_submission(submission_id, db=db)
        assignment = await AssignmentService.get(submission.assignment_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    if assignment.status not in (
        AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED, AssignmentStatus.SUBMITTED,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "NOT_EVALUABLE",
                "message": "Evaluators can be allocated only while the assignment is "
                           "open for evaluation (published or closed).",
            },
        )

    await _assert_is_evaluator(payload.evaluator_user_id, db)

    try:
        row = await EvaluationAssignmentService.create_assignment(
            AssignmentCreateRequest(
                assignment_type="REGULAR",
                target_entity=COURSEWORK_TARGET_ENTITY,
                target_id=submission_id,
                evaluator_id=payload.evaluator_user_id,
                due_at=payload.due_at,
                notes=payload.notes,
            ),
            assigned_by=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            db=db,
        )
    except AssignmentError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400),
            detail={"error": getattr(exc, "code", "ASSIGNMENT_ERROR"), "message": str(exc)},
        )

    await AuditService.log(
        AuditEventType.COURSEWORK_EVALUATOR_ASSIGNED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment_submission", target_id=str(submission_id),
        metadata={
            "assignment_id":     str(submission.assignment_id),
            "evaluator_user_id": str(payload.evaluator_user_id),
            "allocation_id":     str(row.id),
        },
    )
    await notify_user(
        db,
        notification_type=NotificationType.REVIEW_REQUESTED,
        recipient_user_id=payload.evaluator_user_id,
        title=f"Evaluation assigned: {assignment.title}",
        body="A coursework submission has been allocated to you for evaluation.",
        entity_type="AssignmentSubmission",
        entity_id=str(submission_id),
    )
    return {"allocation_id": str(row.id), "evaluator_user_id": str(payload.evaluator_user_id)}


# The separate Dean "finalize" ratification has been removed: the assignment's
# owning faculty is the academic authority, and their review of the evaluator's
# recommendation IS the ratification. Releasing is that single human decision.
# AssignmentStatus.FINALIZED is retained only so historical rows stay readable.


@router.post("/{assignment_id}/release", response_model=AssignmentResponse)
async def release_marks(
    assignment_id: UUID,
    # The owning faculty's decision, not the department's. _assert_may_manage
    # narrows _WRITE to the creator (or Admin) exactly as publish/close do.
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Release the faculty-approved marks to students and notify them.

    Only after this can a student see any mark or feedback. Every submission must
    carry a mark first, so a release can never expose a half-evaluated class."""
    try:
        await _assert_may_manage(assignment_id, current_user, db)
        assignment = await AssignmentService.release(assignment_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_MARKS_RELEASED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment", target_id=str(assignment_id),
    )

    if assignment.syllabus_id:
        section_ids = await AssignmentRepository.enrolled_section_ids_for_syllabus(
            assignment.syllabus_id, db=db
        )
        for section_id in section_ids:
            await notify_section_students(
                db,
                notification_type=NotificationType.ASSIGNMENT_RESULTS_RELEASED,
                section_id=section_id,
                title=f"Results released: {assignment.title}",
                body=f"Your marks for \"{assignment.title}\" are now available.",
                entity_type="Assignment",
                entity_id=str(assignment.id),
            )
    return AssignmentResponse.model_validate(assignment)


@router.post("/{assignment_id}/archive", response_model=AssignmentResponse)
async def archive_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Archive a FINALIZED/RELEASED assignment (file it away). Ownership on the
    active workspace."""
    try:
        assignment = await AssignmentService.archive(
            assignment_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    await AuditService.log(
        AuditEventType.COURSEWORK_ASSIGNMENT_ARCHIVED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment", target_id=str(assignment_id),
    )
    return AssignmentResponse.model_validate(assignment)


@router.post("/{assignment_id}/restore", response_model=AssignmentResponse)
async def restore_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Restore an ARCHIVED assignment (back to FINALIZED)."""
    try:
        assignment = await AssignmentService.restore(
            assignment_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    await AuditService.log(
        AuditEventType.COURSEWORK_ASSIGNMENT_RESTORED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment", target_id=str(assignment_id),
    )
    return AssignmentResponse.model_validate(assignment)


# ===========================================================================
# Faculty — Submissions, grading, statistics
# ===========================================================================

@router.get("/{assignment_id}/submissions", response_model=SubmissionListResponse)
async def list_submissions(
    assignment_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    # _EVALUATE, not _READ: an allocated evaluator opens this page to reach their
    # work. The service returns only the submissions allocated to them, and 404s
    # for a faculty member who neither set this coursework nor was given any of
    # it — so the dependency is the outer bound, not the actual rule.
    current_user: CurrentUser = Depends(_EVALUATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        items, total = await SubmissionService.list_for_assignment(
            assignment_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db, offset=offset, limit=limit,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    # Advisory AI state for the whole page in one query — the assignment's owner
    # sees which submissions the AI has finished without expanding each row.
    ai_status = await AiEvaluationRepository.status_by_submissions(
        [s.id for s in items], db=db
    )

    resp_items = []
    for s in items:
        name = await _student_name(s.student_user_id, db)
        # Read from the M09.6 allocation ledger — m04 keeps no copy of it.
        evaluator_id = await AssignmentRepository.active_evaluator_for_submission(s.id, db=db)
        resp_items.append(
            SubmissionResponse.model_validate(s).model_copy(update={
                "student_name":      name,
                "evaluator_user_id": evaluator_id,
                "evaluator_name":    await _student_name(evaluator_id, db) if evaluator_id else None,
                "ai_status":         ai_status.get(s.id),
            })
        )
    return SubmissionListResponse(items=resp_items, total=total, offset=offset, limit=limit)


@router.get("/submissions/{submission_id}/ai-evaluation", response_model=AiEvaluationResponse | None)
async def get_ai_evaluation(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_AI_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """The ADVISORY AI evaluation for one submission (or null if none yet).

    Read-only. Never affects marks. Viewable by Admin/Dean (oversight) and the
    coursework's creator / department / nominated / allocated evaluator —
    assert_may_view narrows from the role bound.
    """
    try:
        submission = await SubmissionService.get_submission(submission_id, db=db)
        assignment = await AssignmentService.get(submission.assignment_id, db=db)
        await AssignmentService.assert_may_view(
            assignment, actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role, db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    row = await AiEvaluationRepository.get_by_submission(submission_id, db=db)
    if row is None:
        return None
    return AiEvaluationResponse.model_validate(row)


@router.post("/submissions/{submission_id}/re-evaluate", status_code=202)
async def reevaluate_submission(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_AI_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Re-run the background AI evaluation (advisory). Returns 202 and processes
    asynchronously; the evaluator's marks are never touched. Available to the same
    viewers as the read endpoint — it triggers AI only, never human grading."""
    try:
        submission = await SubmissionService.get_submission(submission_id, db=db)
        assignment = await AssignmentService.get(submission.assignment_id, db=db)
        await AssignmentService.assert_may_view(
            assignment, actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role, db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await SubmissionService.request_reevaluation(
        submission_id, assignment_id=submission.assignment_id,
        schema_name=current_user.schema_name, db=db,
    )
    return {"status": "PENDING", "submission_id": str(submission_id)}


@router.get("/{assignment_id}/statistics", response_model=AssignmentStatistics)
async def get_statistics(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        # Statistics are an aggregate over the WHOLE class, so they belong to
        # whoever set the coursework — not to an evaluator holding one submission
        # of it.
        await _assert_may_manage(assignment_id, current_user, db)
        stats = await AssignmentService.statistics(assignment_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    return AssignmentStatistics(**stats)


@router.patch("/submissions/{submission_id}/grade", response_model=SubmissionResponse)
async def grade_submission(
    submission_id: UUID,
    payload: GradeSubmissionRequest,
    current_user: CurrentUser = Depends(_EVALUATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        submission, previous_marks_obtained = await SubmissionService.grade(
            submission_id,
            marks_obtained=payload.marks_obtained,
            feedback=payload.feedback,
            graded_by_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_SUBMISSION_GRADED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment_submission", target_id=str(submission_id),
        metadata={
            "assignment_id": str(submission.assignment_id),
            "student_id": str(submission.student_user_id),
            "previous_marks_obtained": previous_marks_obtained,
            "marks_obtained": payload.marks_obtained,
        },
    )

    # Marks are NOT revealed to the student here — they become visible only when
    # the owning faculty RELEASES the assignment.
    #
    # An evaluator's save is a RECOMMENDATION, so the owner is told immediately
    # rather than only once the whole class is done: they are the academic
    # authority and cannot review what they were never told about. One
    # notification per save; the last one says the set is complete.
    assignment = await AssignmentService.get(submission.assignment_id, db=db)
    if current_user.user_id != assignment.created_by_user_id:
        ungraded = await SubmissionRepository.count_ungraded(
            submission.assignment_id, db=db
        )
        student_name = await _student_name(submission.student_user_id, db)
        who = student_name or "A student"
        if ungraded == 0:
            body = (
                f"{who}'s submission has been evaluated — that was the last one for "
                f"\"{assignment.title}\". Review the recommended marks and release "
                "the results when you are satisfied."
            )
        else:
            body = (
                f"{who}'s submission for \"{assignment.title}\" has been evaluated. "
                f"{ungraded} still awaiting evaluation. The marks are a "
                "recommendation until you review them."
            )
        await notify_user(
            db,
            notification_type=NotificationType.ASSIGNMENT_EVALUATION_COMPLETED,
            recipient_user_id=assignment.created_by_user_id,
            title=f"Evaluation received: {assignment.title}",
            body=body,
            entity_type="Assignment",
            entity_id=str(assignment.id),
        )
    return SubmissionResponse.model_validate(submission)


@router.post("/submissions/{submission_id}/return", response_model=SubmissionResponse)
async def return_submission(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        # Returning work to a student is the owning faculty's act.
        sub = await SubmissionService.get_submission(submission_id, db=db)
        await _assert_may_manage(sub.assignment_id, current_user, db)
        submission = await SubmissionService.mark_returned(submission_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_SUBMISSION_RETURNED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment_submission", target_id=str(submission_id),
    )

    assignment = await AssignmentService.get(submission.assignment_id, db=db)
    await notify_user(
        db,
        notification_type=NotificationType.ASSIGNMENT_RETURNED,
        recipient_user_id=submission.student_user_id,
        title=f"Assignment returned: {assignment.title}",
        body="Your submission has been returned with feedback.",
        entity_type="AssignmentSubmission",
        entity_id=str(submission.id),
    )
    return SubmissionResponse.model_validate(submission)


@router.get("/submissions/{submission_id}/file-url")
async def get_submission_file_url_faculty(
    submission_id: UUID,
    # _EVALUATE: the allocated evaluator must be able to open the work they were
    # given. assert_may_view keeps everyone else out — a student's uploaded file
    # is not readable by any faculty member who happens to be logged in.
    current_user: CurrentUser = Depends(_EVALUATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        sub = await SubmissionService.get_submission(submission_id, db=db)
        assignment = await AssignmentService.get(sub.assignment_id, db=db)
        await AssignmentService.assert_may_view(
            assignment,
            actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    if not sub.content_url:
        raise HTTPException(status_code=404, detail={"error": "NO_FILE", "message": "No uploaded file for this submission."})

    from app.config import settings
    from app.core.storage.repository import StorageRepository

    expires_in = getattr(settings, "PRESIGNED_URL_EXPIRY_MINUTES_GET", 5) * 60
    url = await StorageRepository.generate_presigned_get_url(
        object_key=sub.content_url, expires_in_seconds=expires_in
    )
    return {"url": url, "expires_in_seconds": expires_in}


@router.get("/{assignment_id}/question-paper-url")
async def get_question_paper_url_faculty(
    assignment_id: UUID,
    # _EVALUATE: an allocated evaluator must be able to read the question paper the
    # work they were given is answering. assert_may_view narrows from there.
    current_user: CurrentUser = Depends(_EVALUATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
        await AssignmentService.assert_may_view(
            assignment,
            actor_user_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    if not assignment.question_paper_url:
        raise HTTPException(status_code=404, detail={"error": "NO_FILE", "message": "No question paper for this assignment."})

    from app.config import settings
    from app.core.storage.repository import StorageRepository

    expires_in = getattr(settings, "PRESIGNED_URL_EXPIRY_MINUTES_GET", 5) * 60
    url = await StorageRepository.generate_presigned_get_url(
        object_key=assignment.question_paper_url, expires_in_seconds=expires_in
    )
    return {"url": url, "expires_in_seconds": expires_in}


# ===========================================================================
# Student — assignments + submit + result
# ===========================================================================

# NOTE: GET /student (list) is declared earlier, before GET /{assignment_id},
# so the literal "/student" path is not swallowed by the UUID path param.


@router.get("/student/{assignment_id}", response_model=AssignmentResponse)
async def student_get_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
        await AssignmentService.assert_student_may_view(
            assignment, student_user_id=current_user.user_id, db=db
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    return AssignmentResponse.model_validate(assignment).model_copy(
        update={"course_title": course_title, "course_code": course_code}
    )


@router.post("/student/{assignment_id}/submit", response_model=SubmissionResponse, status_code=201)
async def student_submit(
    assignment_id: UUID,
    payload: SubmissionCreate,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        submission = await SubmissionService.submit(
            assignment_id=assignment_id,
            student_user_id=current_user.user_id,
            content_text=payload.content_text,
            content_url=payload.content_url,
            # Lets the submission raise its own evaluator work item against the
            # evaluators the faculty nominated, through the M09.6 engine.
            tenant_id=current_user.tenant_id,
            # Enables the fire-and-forget background AI evaluation (advisory).
            schema_name=current_user.schema_name,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_SUBMISSION_RECEIVED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment_submission", target_id=str(submission.id),
        metadata={"assignment_id": str(assignment_id), "attempt_number": submission.attempt_number},
    )

    # Tell the owning faculty a submission has arrived.
    assignment = await AssignmentService.get(assignment_id, db=db)
    student_name = await _student_name(current_user.user_id, db)
    await notify_user(
        db,
        notification_type=NotificationType.ASSIGNMENT_SUBMISSION_RECEIVED,
        recipient_user_id=assignment.created_by_user_id,
        title=f"New submission: {assignment.title}",
        body=(f"{student_name or 'A student'} submitted \"{assignment.title}\" "
              f"(attempt {submission.attempt_number})."),
        entity_type="AssignmentSubmission",
        entity_id=str(submission.id),
    )
    return SubmissionResponse.model_validate(submission)


@router.get("/student/submissions/my", response_model=SubmissionListResponse)
async def student_my_submissions(
    syllabus_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await SubmissionService.list_for_student(
        current_user.user_id, db=db, syllabus_id=syllabus_id, offset=offset, limit=limit
    )

    # Nothing evaluative reaches a student before their faculty releases it. This
    # list used to return marks, feedback and the evaluator the moment a grade was
    # saved, which let a student read an unreleased mark here even though the
    # result page correctly refused to show it. Marks survive only for an assignment
    # the faculty has RELEASED, or a submission explicitly RETURNED for revision.
    released: dict[UUID, bool] = {}
    resp_items = []
    for s in items:
        if s.assignment_id not in released:
            a = await AssignmentService.get(s.assignment_id, db=db)
            released[s.assignment_id] = a.status == AssignmentStatus.RELEASED
        visible = released[s.assignment_id] or s.status == SubmissionStatus.RETURNED
        model = SubmissionResponse.model_validate(s)
        resp_items.append(model if visible else model.for_student())

    return SubmissionListResponse(
        items=resp_items, total=total, offset=offset, limit=limit,
    )


@router.get("/student/submissions/{submission_id}/result", response_model=SubmissionDetailResponse)
async def student_get_result(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        sub = await SubmissionService.get_submission(submission_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    if sub.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})
    # Marks are visible ONLY once the assignment is RELEASED (finalizing alone is
    # not enough) — or when this specific submission was explicitly RETURNED to
    # the student with feedback for revision.
    assignment = await AssignmentService.get(sub.assignment_id, db=db)
    released = assignment.status == AssignmentStatus.RELEASED
    returned = sub.status == "RETURNED"
    if not (released or returned):
        raise HTTPException(
            status_code=403,
            detail={"error": "NOT_RELEASED",
                    "message": "Results are visible once your marks have been released."},
        )
    # Released means the FACULTY-APPROVED mark and feedback — never the working
    # notes behind them. The evaluator's recommendation and the AI's analysis stay
    # internal to the staff who produced them, released or not.
    return SubmissionDetailResponse.model_validate(sub).model_copy(update={
        "evaluator_marks_obtained": None,
        "evaluator_feedback":       None,
        "evaluator_user_id":        None,
        "evaluator_name":           None,
        "ai_status":                None,
    })


@router.get("/student/{assignment_id}/question-paper-url")
async def get_question_paper_url_student(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
        await AssignmentService.assert_student_may_view(
            assignment, student_user_id=current_user.user_id, db=db
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    if not assignment.question_paper_url:
        raise HTTPException(status_code=404, detail={"error": "NO_FILE", "message": "No question paper for this assignment."})

    from app.config import settings
    from app.core.storage.repository import StorageRepository

    expires_in = getattr(settings, "PRESIGNED_URL_EXPIRY_MINUTES_GET", 5) * 60
    url = await StorageRepository.generate_presigned_get_url(
        object_key=assignment.question_paper_url, expires_in_seconds=expires_in
    )
    return {"url": url, "expires_in_seconds": expires_in}


@router.get("/student/submissions/{submission_id}/file-url")
async def get_submission_file_url_student(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        sub = await SubmissionService.get_submission(submission_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    if sub.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})
    if not sub.content_url:
        raise HTTPException(status_code=404, detail={"error": "NO_FILE", "message": "No uploaded file for this submission."})

    from app.config import settings
    from app.core.storage.repository import StorageRepository

    expires_in = getattr(settings, "PRESIGNED_URL_EXPIRY_MINUTES_GET", 5) * 60
    url = await StorageRepository.generate_presigned_get_url(
        object_key=sub.content_url, expires_in_seconds=expires_in
    )
    return {"url": url, "expires_in_seconds": expires_in}
