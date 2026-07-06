"""
M04 Assignments — router.

RBAC
----
  _WRITE   = ADMIN + FACULTY   (create/update/publish/close, grade, return)
  _READ    = ADMIN + DEAN + FACULTY
  _STUDENT = STUDENT           (list, view, submit, view own result)

Router is pure HTTP glue. All business logic lives in service.py.

Endpoint summary (faculty)
--------------------------
  POST   /assignments                         create assignment
  GET    /assignments                         list assignments
  GET    /assignments/{id}                    get detail
  PUT    /assignments/{id}                    update (DRAFT only)
  POST   /assignments/{id}/publish            publish (notifies enrolled students)
  POST   /assignments/{id}/close              close
  GET    /assignments/{id}/submissions        list submissions
  GET    /assignments/{id}/statistics         submission/grading stats
  PATCH  /submissions/{id}/grade              record marks + feedback
  POST   /submissions/{id}/return             return to student (notifies student)
  GET    /submissions/{id}/file-url           presigned download (faculty)

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
from app.modules.m04_assignments.repository import AssignmentRepository, SubmissionRepository
from app.modules.m04_assignments.schemas import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentResponse,
    AssignmentStatistics,
    AssignmentUpdate,
    GradeSubmissionRequest,
    SubmissionCreate,
    SubmissionDetailResponse,
    SubmissionListResponse,
    SubmissionResponse,
)
from app.modules.m04_assignments.service import (
    AssignmentService,
    AssignmentServiceError,
    SubmissionService,
)

router = APIRouter(tags=["assignments"])

_WRITE   = require_roles(TenantRole.ADMIN, TenantRole.FACULTY)
_READ    = require_roles(TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_STUDENT = require_roles(TenantRole.STUDENT)


def _svc_error(exc: AssignmentServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"error": exc.code, "message": exc.message})


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
        metadata={"title": assignment.title, "type": assignment.assignment_type},
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
    items, total = await AssignmentService.list_assignments(
        db=db, syllabus_id=syllabus_id, status=status, offset=offset, limit=limit
    )
    return AssignmentListResponse(
        items=[AssignmentResponse.model_validate(a) for a in items],
        total=total, offset=offset, limit=limit,
    )


@router.get("/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
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
    try:
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
# Faculty — Submissions, grading, statistics
# ===========================================================================

@router.get("/{assignment_id}/submissions", response_model=SubmissionListResponse)
async def list_submissions(
    assignment_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        items, total = await SubmissionService.list_for_assignment(
            assignment_id, db=db, offset=offset, limit=limit
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    resp_items = []
    for s in items:
        name = await _student_name(s.student_user_id, db)
        resp_items.append(
            SubmissionResponse.model_validate(s).model_copy(update={"student_name": name})
        )
    return SubmissionListResponse(items=resp_items, total=total, offset=offset, limit=limit)


@router.get("/{assignment_id}/statistics", response_model=AssignmentStatistics)
async def get_statistics(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        stats = await AssignmentService.statistics(assignment_id, db=db)
    except AssignmentServiceError as exc:
        raise _svc_error(exc)
    return AssignmentStatistics(**stats)


@router.patch("/submissions/{submission_id}/grade", response_model=SubmissionResponse)
async def grade_submission(
    submission_id: UUID,
    payload: GradeSubmissionRequest,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        submission = await SubmissionService.grade(
            submission_id,
            marks_obtained=payload.marks_obtained,
            feedback=payload.feedback,
            graded_by_user_id=current_user.user_id,
            db=db,
        )
    except AssignmentServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.COURSEWORK_SUBMISSION_GRADED,
        actor_user_id=current_user.user_id, actor_role=current_user.role,
        tenant_id=current_user.tenant_id, schema_name=current_user.schema_name,
        target_entity="assignment_submission", target_id=str(submission_id),
        metadata={"marks_obtained": payload.marks_obtained},
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
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        sub = await SubmissionService.get_submission(submission_id, db=db)
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
