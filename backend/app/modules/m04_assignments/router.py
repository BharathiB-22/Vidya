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
from app.modules.m04_assignments.models import AssignmentStatus
from app.modules.m04_assignments.repository import (
    COURSEWORK_TARGET_ENTITY,
    AssignmentRepository,
    SubmissionRepository,
)
from app.modules.m09_paper_admin.assignment_models import ACTIVE_STATUSES
from app.modules.m04_assignments.schemas import (
    AssignEvaluatorRequest,
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentResponse,
    AssignmentStatistics,
    AssignmentUpdate,
    EligibleEvaluator,
    GradeSubmissionRequest,
    MyCourseworkEvaluation,
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
        actor_role=current_user.role,
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
    # institution, so both keep the full list.
    items, total = await AssignmentService.list_assignments(
        db=db, syllabus_id=syllabus_id, status=status, offset=offset, limit=limit,
        created_by_user_id=(
            None if _is_privileged(current_user.role) else current_user.user_id
        ),
    )
    return AssignmentListResponse(
        items=[AssignmentResponse.model_validate(a) for a in items],
        total=total, offset=offset, limit=limit,
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
            actor_role=current_user.role,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    return AssignmentResponse.model_validate(assignment).model_copy(
        update={"course_title": course_title, "course_code": course_code}
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
    rows = (
        await db.execute(
            text(
                """
                SELECT s.id            AS submission_id,
                       a.id            AS assignment_id,
                       a.title         AS assignment_title,
                       c.title         AS course_title,
                       c.code          AS course_code,
                       u.full_name     AS student_name,
                       s.attempt_number,
                       s.submitted_at,
                       s.is_late,
                       s.status        AS submission_status,
                       a.status        AS assignment_status,
                       a.max_marks,
                       s.marks_obtained,
                       ea.due_at,
                       ea.status       AS allocation_status
                FROM evaluation_assignments ea
                JOIN assignment_submissions s ON s.id = ea.target_id
                JOIN assignments a           ON a.id = s.assignment_id
                LEFT JOIN syllabi syl        ON syl.id = a.syllabus_id
                LEFT JOIN courses c          ON c.id = syl.course_id
                LEFT JOIN users u            ON u.id = s.student_user_id
                WHERE ea.target_entity = :target_entity
                  AND ea.evaluator_id  = :evaluator_id
                  AND ea.status = ANY(:active_statuses)
                ORDER BY ea.due_at NULLS LAST, s.submitted_at
                """
            ),
            {
                "target_entity":   COURSEWORK_TARGET_ENTITY,
                "evaluator_id":    str(current_user.user_id),
                "active_statuses": list(ACTIVE_STATUSES),
            },
        )
    ).mappings().all()

    return [MyCourseworkEvaluation(**dict(r)) for r in rows]


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
    from app.modules.m09_paper_admin.assignment_repository import AssignmentRepository as _EvalRepo
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

    if assignment.status != AssignmentStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "NOT_SUBMITTED_FOR_EVALUATION",
                "message": "The faculty must submit this assignment for evaluation "
                           "before evaluators can be allocated.",
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
            actor_role=current_user.role,
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


@router.post("/{assignment_id}/finalize", response_model=AssignmentResponse)
async def finalize_marks(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_ALLOCATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Ratify the evaluated marks. A human decision, recorded at the database
    level — nothing computes or infers it, and grading stops once it is set."""
    try:
        assignment = await AssignmentService.finalize_marks(
            assignment_id, actor_user_id=current_user.user_id, db=db
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_MARKS_FINALIZED,
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
            actor_role=current_user.role,
            db=db, offset=offset, limit=limit,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

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
            })
        )
    return SubmissionListResponse(items=resp_items, total=total, offset=offset, limit=limit)


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
            actor_role=current_user.role,
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

    assignment = await AssignmentService.get(submission.assignment_id, db=db)
    await notify_user(
        db,
        notification_type=NotificationType.ASSIGNMENT_GRADED,
        recipient_user_id=submission.student_user_id,
        title=f"Assignment graded: {assignment.title}",
        body=f"You scored {payload.marks_obtained}/{assignment.max_marks}.",
        entity_type="AssignmentSubmission",
        entity_id=str(submission.id),
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
            actor_role=current_user.role,
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
            actor_role=current_user.role,
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

@router.get("/student", response_model=AssignmentListResponse)
async def student_list_assignments(
    syllabus_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await AssignmentService.list_assignments(
        db=db, syllabus_id=syllabus_id, statuses=["PUBLISHED", "CLOSED"],
        offset=offset, limit=limit,
    )
    return AssignmentListResponse(
        items=[AssignmentResponse.model_validate(a) for a in items],
        total=total, offset=offset, limit=limit,
    )


@router.get("/student/{assignment_id}", response_model=AssignmentResponse)
async def student_get_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    if assignment.status not in ("PUBLISHED", "CLOSED"):
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Assignment not found."})
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
    return SubmissionListResponse(
        items=[SubmissionResponse.model_validate(s) for s in items],
        total=total, offset=offset, limit=limit,
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
    if sub.status not in ("GRADED", "RETURNED"):
        raise HTTPException(
            status_code=403,
            detail={"error": "NOT_GRADED", "message": "Results are only visible after grading."},
        )
    return SubmissionDetailResponse.model_validate(sub)


@router.get("/student/{assignment_id}/question-paper-url")
async def get_question_paper_url_student(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    if assignment.status not in ("PUBLISHED", "CLOSED"):
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Assignment not found."})
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
