"""
M06 Labs & Assignment Evaluator — router.

RBAC
----
  _WRITE    = ADMIN + FACULTY    (create/update/publish/close assignments, ratify)
  _READ     = ADMIN + DEAN + FACULTY
  _EVALUATE = ADMIN + FACULTY + EVALUATOR  (evaluator recommendation path)
  _STUDENT  = STUDENT            (submit, view own, view ratified result)
  _FULL     = ADMIN + DEAN + FACULTY + STUDENT + EVALUATOR
  _EVAL_ONLY = EVALUATOR only    (evaluator-scoped routes)

Router is pure HTTP glue. All business logic lives in service.py.

Endpoint summary (faculty)
--------------------------
  POST   /assignments                         create assignment
  GET    /assignments                         list assignments
  GET    /assignments/{id}                    get detail (test cases: full for faculty)
  PUT    /assignments/{id}                    update (DRAFT only)
  POST   /assignments/{id}/publish            publish
  POST   /assignments/{id}/close              close
  GET    /assignments/{id}/submissions        list submissions
  GET    /submissions/{id}/review             full review panel detail
  PATCH  /submissions/{id}/scores             update per-criterion human scores
  POST   /submissions/{id}/ratify             write to grade_ledger (human gate)
  GET    /assignments/{id}/report             trigger / download moderation report
  GET    /jobs/{job_id}                       poll evaluation job status

Endpoint summary (student)
--------------------------
  GET    /student/assignments                 list published assignments
  GET    /student/assignments/{id}            detail (hidden test cases stripped)
  POST   /student/assignments/{id}/submit     submit
  GET    /student/submissions/my              my submissions
  GET    /student/submissions/{id}/result     view ratified result only
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_responsibility, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m06_labs_evaluator.evaluator_schemas import (
    EvaluatorAnalytics,
    EvaluatorAssignmentList,
    EvaluatorAssignmentResponse,
    EvaluatorAssignRequest,
    EvaluatorRecommendRequest,
    TenantEvaluatorUser,
)
from app.modules.m06_labs_evaluator.evaluator_service import EvaluatorService
from app.modules.m06_labs_evaluator.repository import GradeLedgerRepository, TaskJobPublicRepository
from app.modules.m06_labs_evaluator.schemas import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentResponse,
    AssignmentUpdate,
    GradeLedgerResponse,
    JobStatusResponse,
    RatifyRequest,
    ReviewPanelResponse,
    ScoresUpdateRequest,
    SubmissionCreate,
    SubmissionDetailResponse,
    SubmissionListResponse,
    SubmissionResponse,
)
from app.modules.m06_labs_evaluator.service import (
    AssignmentService,
    LabServiceError,
    ReviewService,
    SubmissionService,
)

router = APIRouter(tags=["labs-evaluator"])

_WRITE    = require_roles(TenantRole.ADMIN, TenantRole.FACULTY)
_READ     = require_roles(TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_EVALUATE = require_roles(TenantRole.ADMIN, TenantRole.FACULTY, TenantRole.EVALUATOR)
_STUDENT  = require_roles(TenantRole.STUDENT)
# Evaluator-scoped routes: legacy standalone EVALUATOR users OR a FACULTY
# account granted the EVALUATOR responsibility (single login, multiple roles).
_EVAL_ONLY = require_responsibility(TenantRole.EVALUATOR)
_FULL     = require_roles(
    TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY,
    TenantRole.STUDENT, TenantRole.EVALUATOR,
)


def _svc_error(exc: LabServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    )


def _strip_hidden_tests(assignment_dict: dict) -> dict:
    """Remove hidden test cases before returning to students."""
    tcs = assignment_dict.get("test_cases") or []
    assignment_dict["test_cases"] = [t for t in tcs if not t.get("is_hidden", False)]
    return assignment_dict


async def _course_context(
    syllabus_id: UUID | None,
    db: AsyncSession,
) -> tuple[str | None, str | None]:
    """Resolve course title + code from syllabi → courses chain. Fails silently."""
    if not syllabus_id:
        return None, None
    try:
        row = (await db.execute(
            text(
                "SELECT c.title, c.code "
                "FROM syllabi s JOIN courses c ON c.id = s.course_id "
                "WHERE s.id = :sid"
            ),
            {"sid": str(syllabus_id)},
        )).fetchone()
        if row:
            return row[0], row[1]
    except Exception:
        pass
    return None, None


# ===========================================================================
# Faculty — Assignment CRUD
# ===========================================================================

@router.post("/assignments", response_model=AssignmentResponse, status_code=201)
async def create_assignment(
    payload: AssignmentCreate,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.create(
            payload,
            created_by_user_id=current_user.user_id,
            db=db,
        )
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_ASSIGNMENT_CREATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_assignment",
        target_id=str(assignment.id),
        metadata={"title": assignment.title, "type": assignment.submission_type},
    )
    return AssignmentResponse.model_validate(assignment)


@router.get("/assignments", response_model=AssignmentListResponse)
async def list_assignments(
    syllabus_id: UUID | None = Query(None),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await AssignmentService.list_assignments(
        db=db,
        syllabus_id=syllabus_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return AssignmentListResponse(
        items=[AssignmentResponse.model_validate(a) for a in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    return AssignmentResponse.model_validate(assignment).model_copy(
        update={"course_title": course_title, "course_code": course_code}
    )


@router.put("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: UUID,
    payload: AssignmentUpdate,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.update(assignment_id, payload, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_ASSIGNMENT_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_assignment",
        target_id=str(assignment_id),
    )
    return AssignmentResponse.model_validate(assignment)


@router.post("/assignments/{assignment_id}/publish", response_model=AssignmentResponse)
async def publish_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.publish(assignment_id, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_ASSIGNMENT_PUBLISHED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_assignment",
        target_id=str(assignment_id),
        metadata={"max_marks": assignment.max_marks},
    )
    return AssignmentResponse.model_validate(assignment)


@router.post("/assignments/{assignment_id}/close", response_model=AssignmentResponse)
async def close_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.close(assignment_id, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_ASSIGNMENT_CLOSED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_assignment",
        target_id=str(assignment_id),
    )
    return AssignmentResponse.model_validate(assignment)


# ===========================================================================
# Faculty — Submission list + review panel
# ===========================================================================

@router.get("/assignments/{assignment_id}/submissions", response_model=SubmissionListResponse)
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
    except LabServiceError as exc:
        raise _svc_error(exc)
    return SubmissionListResponse(
        items=[SubmissionResponse.model_validate(s) for s in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/submissions/{submission_id}/review", response_model=ReviewPanelResponse)
async def get_review_panel(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        sub, assignment, grade_entry = await ReviewService.get_review_panel(
            submission_id, db=db
        )
    except LabServiceError as exc:
        raise _svc_error(exc)

    from app.modules.m06_labs_evaluator.schemas import EvaluationResponse
    eval_resp = (
        EvaluationResponse.model_validate(sub.evaluation)
        if sub.evaluation
        else None
    )
    sub_detail = SubmissionDetailResponse(
        **SubmissionResponse.model_validate(sub).model_dump(),
        content_text=sub.content_text,
        ai_scan_result=sub.ai_scan_result,
        evaluation=eval_resp,
    )
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    return ReviewPanelResponse(
        submission=sub_detail,
        assignment=AssignmentResponse.model_validate(assignment).model_copy(
            update={"course_title": course_title, "course_code": course_code}
        ),
        grade_entry=GradeLedgerResponse.model_validate(grade_entry) if grade_entry else None,
    )


@router.patch("/submissions/{submission_id}/scores")
async def update_scores(
    submission_id: UUID,
    payload: ScoresUpdateRequest,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        evaluation = await ReviewService.update_scores(
            submission_id, payload.scores, db=db
        )
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_SCORES_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_submission",
        target_id=str(submission_id),
        metadata={"criteria_updated": len(payload.scores)},
    )
    from app.modules.m06_labs_evaluator.schemas import EvaluationResponse
    return EvaluationResponse.model_validate(evaluation)


@router.post("/submissions/{submission_id}/ratify", response_model=GradeLedgerResponse)
async def ratify_submission(
    submission_id: UUID,
    payload: RatifyRequest,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        grade = await ReviewService.ratify(
            submission_id,
            ratified_by_user_id=current_user.user_id,
            ratification_note=payload.ratification_note,
            db=db,
        )
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_SUBMISSION_RATIFIED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_submission",
        target_id=str(submission_id),
        metadata={
            "final_score":  float(grade.final_score),
            "max_marks":    grade.max_marks,
        },
    )
    return GradeLedgerResponse.model_validate(grade)


# ===========================================================================
# Moderation report
# ===========================================================================

@router.get("/assignments/{assignment_id}/report")
async def get_moderation_report(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Generate and return the moderation report CSV for an assignment."""
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)

    from app.modules.m06_labs_evaluator.report_export import generate_csv_report
    from fastapi.responses import Response

    csv_content = await generate_csv_report(
        assignment_id, assignment.rubric or [], db=db
    )

    await AuditService.log(
        AuditEventType.LAB_REPORT_REQUESTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_assignment",
        target_id=str(assignment_id),
    )

    filename = f"moderation_report_{assignment_id}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ===========================================================================
# Faculty — Evaluator assignment management
# ===========================================================================

@router.post(
    "/assignments/{assignment_id}/evaluators",
    response_model=EvaluatorAssignmentResponse,
    status_code=201,
)
async def assign_evaluator(
    assignment_id: UUID,
    payload: EvaluatorAssignRequest,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        mapping = await EvaluatorService.assign(
            assignment_id,
            evaluator_user_id=payload.evaluator_user_id,
            assigned_by_user_id=current_user.user_id,
            db=db,
        )
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_EVALUATOR_ASSIGNED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_assignment",
        target_id=str(assignment_id),
        metadata={"evaluator_user_id": str(payload.evaluator_user_id)},
    )
    return EvaluatorAssignmentResponse.model_validate(mapping)


@router.get(
    "/assignments/{assignment_id}/evaluators",
    response_model=EvaluatorAssignmentList,
)
async def list_assignment_evaluators(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items = await EvaluatorService.list_for_assignment(assignment_id, db=db)
    return EvaluatorAssignmentList(
        items=[EvaluatorAssignmentResponse.model_validate(m) for m in items],
        total=len(items),
    )


@router.delete(
    "/assignments/{assignment_id}/evaluators/{evaluator_user_id}",
    status_code=204,
)
async def remove_evaluator(
    assignment_id: UUID,
    evaluator_user_id: UUID,
    current_user: CurrentUser = Depends(_WRITE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        await EvaluatorService.remove(assignment_id, evaluator_user_id, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_EVALUATOR_REMOVED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_assignment",
        target_id=str(assignment_id),
        metadata={"evaluator_user_id": str(evaluator_user_id)},
    )


# ===========================================================================
# Faculty — Tenant evaluator user lookup (safe, role-filtered)
# ===========================================================================

@router.get("/evaluators", response_model=list[TenantEvaluatorUser])
async def list_tenant_evaluators(
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Return all active users who can evaluate in this tenant — for the picker.

    Includes legacy standalone EVALUATOR users AND FACULTY members granted the
    EVALUATOR responsibility (single account, multiple responsibilities).
    """
    from sqlalchemy import or_, select
    from app.core.auth.models import User
    from app.modules.m_academics.models import FacultyRoleGrant

    eval_grant_subq = (
        select(FacultyRoleGrant.faculty_user_id)
        .where(FacultyRoleGrant.role_code == "EVALUATOR", FacultyRoleGrant.is_active.is_(True))
        .scalar_subquery()
    )
    result = await db.execute(
        select(User)
        .where(
            User.is_active.is_(True),
            or_(
                User.role == TenantRole.EVALUATOR,
                User.id.in_(eval_grant_subq),
            ),
        )
        .order_by(User.full_name)
    )
    return [TenantEvaluatorUser.model_validate(u) for u in result.scalars().all()]


# ===========================================================================
# Evaluator — scoped read + recommendation routes
# ===========================================================================

@router.get("/evaluator/assignments", response_model=AssignmentListResponse)
async def evaluator_list_assignments(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_EVAL_ONLY),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await EvaluatorService.list_assignments(
        current_user.user_id, db=db, offset=offset, limit=limit
    )
    return AssignmentListResponse(
        items=[AssignmentResponse.model_validate(a) for a in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/evaluator/assignments/{assignment_id}", response_model=AssignmentResponse)
async def evaluator_get_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_EVAL_ONLY),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        await EvaluatorService.require_scope(current_user.user_id, assignment_id, db)
        assignment = await AssignmentService.get(assignment_id, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    return AssignmentResponse.model_validate(assignment).model_copy(
        update={"course_title": course_title, "course_code": course_code}
    )


@router.get(
    "/evaluator/assignments/{assignment_id}/submissions",
    response_model=SubmissionListResponse,
)
async def evaluator_list_submissions(
    assignment_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: CurrentUser = Depends(_EVAL_ONLY),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        await EvaluatorService.require_scope(current_user.user_id, assignment_id, db)
        items, total = await SubmissionService.list_for_assignment(
            assignment_id, db=db, offset=offset, limit=limit
        )
    except LabServiceError as exc:
        raise _svc_error(exc)
    return SubmissionListResponse(
        items=[SubmissionResponse.model_validate(s) for s in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/evaluator/submissions/{submission_id}/review", response_model=ReviewPanelResponse)
async def evaluator_get_review_panel(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_EVAL_ONLY),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        sub, assignment, grade_entry = await ReviewService.get_review_panel(
            submission_id, db=db
        )
        await EvaluatorService.require_scope(current_user.user_id, assignment.id, db)
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_EVALUATOR_OPENED_SUBMISSION,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_submission",
        target_id=str(submission_id),
        metadata={"assignment_id": str(assignment.id)},
    )

    from app.modules.m06_labs_evaluator.schemas import EvaluationResponse
    eval_resp = (
        EvaluationResponse.model_validate(sub.evaluation)
        if sub.evaluation
        else None
    )
    sub_detail = SubmissionDetailResponse(
        **SubmissionResponse.model_validate(sub).model_dump(),
        content_text=sub.content_text,
        ai_scan_result=sub.ai_scan_result,
        evaluation=eval_resp,
    )
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    return ReviewPanelResponse(
        submission=sub_detail,
        assignment=AssignmentResponse.model_validate(assignment).model_copy(
            update={"course_title": course_title, "course_code": course_code}
        ),
        grade_entry=GradeLedgerResponse.model_validate(grade_entry) if grade_entry else None,
    )


@router.patch("/evaluator/submissions/{submission_id}/recommend")
async def evaluator_submit_recommendation(
    submission_id: UUID,
    payload: EvaluatorRecommendRequest,
    current_user: CurrentUser = Depends(_EVAL_ONLY),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    from app.modules.m06_labs_evaluator.schemas import CriterionScoreUpdate, EvaluationResponse
    score_updates = [
        CriterionScoreUpdate(
            criterion_id=s.criterion_id,
            human_score=s.human_score,
            human_note=s.human_note,
        )
        for s in payload.scores
    ]
    try:
        evaluation = await EvaluatorService.submit_recommendation(
            submission_id,
            evaluator_user_id=current_user.user_id,
            scores=score_updates,
            db=db,
        )
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_EVALUATOR_SUBMITTED_RECOMMENDATION,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_submission",
        target_id=str(submission_id),
        metadata={
            "criteria_updated": len(payload.scores),
            "note": payload.recommendation_note,
        },
    )
    return EvaluationResponse.model_validate(evaluation)


@router.get("/evaluator/analytics", response_model=EvaluatorAnalytics)
async def evaluator_analytics(
    current_user: CurrentUser = Depends(_EVAL_ONLY),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    stats = await EvaluatorService.get_analytics(current_user.user_id, db=db)
    return EvaluatorAnalytics(**stats)


# ===========================================================================
# Submission file download — presigned GET URL
# ===========================================================================

@router.get("/submissions/{submission_id}/file-url")
async def get_submission_file_url(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_EVALUATE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """
    Return a short-lived presigned GET URL for the uploaded submission file.
    Accessible by faculty, admin, dean, and evaluators (scope-checked).
    """
    try:
        sub = await SubmissionService.get_submission(submission_id, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)

    # Evaluator scope check
    if current_user.role == TenantRole.EVALUATOR:
        try:
            await EvaluatorService.require_scope(current_user.user_id, sub.assignment_id, db)
        except LabServiceError as exc:
            raise _svc_error(exc)

    if not sub.content_url:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_FILE", "message": "No uploaded file for this submission."},
        )

    from app.config import settings
    from app.core.storage.repository import StorageRepository

    expires_in = getattr(settings, "PRESIGNED_URL_EXPIRY_MINUTES_GET", 5) * 60
    url = await StorageRepository.generate_presigned_get_url(
        object_key=sub.content_url,
        expires_in_seconds=expires_in,
    )
    return {"url": url, "expires_in_seconds": expires_in}


# ===========================================================================
# Job status poll
# ===========================================================================

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    current_user: CurrentUser = Depends(_FULL),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    from app.modules.m02_syllabus.repository import TaskJobPublicRepository
    from app.database import async_session_public

    async with async_session_public() as pub_db:
        job = await TaskJobPublicRepository.get_by_id(job_id, db=pub_db)

    if job is None:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Job not found."})

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


# ===========================================================================
# Student — assignments + submit + result
# ===========================================================================

@router.get("/student/assignments", response_model=AssignmentListResponse)
async def student_list_assignments(
    syllabus_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await AssignmentService.list_assignments(
        db=db,
        syllabus_id=syllabus_id,
        status="PUBLISHED",
        offset=offset,
        limit=limit,
    )
    # Strip hidden test cases from student view
    responses = []
    for a in items:
        d = AssignmentResponse.model_validate(a).model_dump()
        _strip_hidden_tests(d)
        responses.append(d)
    return AssignmentListResponse(items=responses, total=total, offset=offset, limit=limit)


@router.get("/student/assignments/{assignment_id}", response_model=AssignmentResponse)
async def student_get_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        assignment = await AssignmentService.get(assignment_id, db=db)
    except LabServiceError as exc:
        raise _svc_error(exc)
    if assignment.status not in ("PUBLISHED", "CLOSED"):
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Assignment not found."})
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    d = AssignmentResponse.model_validate(assignment).model_copy(
        update={"course_title": course_title, "course_code": course_code}
    ).model_dump()
    _strip_hidden_tests(d)
    return d


@router.post("/student/assignments/{assignment_id}/submit", response_model=SubmissionResponse, status_code=201)
async def student_submit(
    assignment_id: UUID,
    payload: SubmissionCreate,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        submission, job_id = await SubmissionService.submit(
            assignment_id=assignment_id,
            student_user_id=current_user.user_id,
            content_text=payload.content_text,
            content_url=payload.content_url,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except LabServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.LAB_SUBMISSION_RECEIVED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="lab_submission",
        target_id=str(submission.id),
        metadata={"assignment_id": str(assignment_id), "eval_job_id": str(job_id)},
    )
    return SubmissionResponse.model_validate(submission)


@router.get("/student/submissions/my", response_model=SubmissionListResponse)
async def student_my_submissions(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    from sqlalchemy import select
    from app.modules.m06_labs_evaluator.models import GradeLedger

    items, total = await SubmissionService.list_for_student(
        current_user.user_id, db=db, offset=offset, limit=limit
    )

    # Batch-fetch grade ledger for RATIFIED submissions so we can surface
    # final_score / graded_max_marks without N+1 queries.
    ratified_ids = [s.id for s in items if s.status == "RATIFIED"]
    grade_map: dict = {}
    if ratified_ids:
        rows = await db.execute(
            select(GradeLedger).where(GradeLedger.submission_id.in_(ratified_ids))
        )
        for g in rows.scalars().all():
            grade_map[g.submission_id] = g

    resp_items = []
    for s in items:
        sub_resp = SubmissionResponse.model_validate(s)
        if s.id in grade_map:
            g = grade_map[s.id]
            sub_resp = sub_resp.model_copy(update={
                "final_score": g.final_score,
                "graded_max_marks": g.max_marks,
            })
        resp_items.append(sub_resp)

    return SubmissionListResponse(
        items=resp_items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/student/submissions/{submission_id}/result", response_model=ReviewPanelResponse)
async def student_get_result(
    submission_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    sub = await SubmissionService.get_submission(
        submission_id, db=db, load_evaluation=True
    )
    if sub.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})
    if sub.status != "RATIFIED":
        raise HTTPException(
            status_code=403,
            detail={"error": "NOT_RATIFIED", "message": "Results are only visible after faculty ratification."},
        )

    # Load assignment and grade entry directly — do NOT call ReviewService.get_review_panel
    # which has the side effect of advancing EVALUATED→REVIEWED status.
    assignment = await AssignmentService.get(sub.assignment_id, db=db)
    grade_entry = await GradeLedgerRepository.get_by_submission(submission_id, db=db)

    from app.modules.m06_labs_evaluator.schemas import EvaluationResponse
    eval_resp = (
        EvaluationResponse.model_validate(sub.evaluation)
        if sub.evaluation
        else None
    )
    sub_detail = SubmissionDetailResponse(
        **SubmissionResponse.model_validate(sub).model_dump(),
        content_text=None,
        ai_scan_result=sub.ai_scan_result,
        evaluation=eval_resp,
    )
    course_title, course_code = await _course_context(assignment.syllabus_id, db)
    return ReviewPanelResponse(
        submission=sub_detail,
        assignment=AssignmentResponse.model_validate(assignment).model_copy(
            update={"course_title": course_title, "course_code": course_code}
        ),
        grade_entry=GradeLedgerResponse.model_validate(grade_entry) if grade_entry else None,
    )
