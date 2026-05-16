"""
M06 Labs & Assignment Evaluator — router.

RBAC
----
  _WRITE   = ADMIN + FACULTY     (create/update/publish/close assignments, ratify)
  _READ    = ADMIN + DEAN + FACULTY
  _STUDENT = STUDENT             (submit, view own, view ratified result)
  _FULL    = ADMIN + DEAN + FACULTY + STUDENT

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m06_labs_evaluator.repository import TaskJobPublicRepository
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

_WRITE   = require_roles(TenantRole.ADMIN, TenantRole.FACULTY)
_READ    = require_roles(TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_STUDENT = require_roles(TenantRole.STUDENT)
_FULL    = require_roles(
    TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.STUDENT
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
    return AssignmentResponse.model_validate(assignment)


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
    return ReviewPanelResponse(
        submission=sub_detail,
        assignment=AssignmentResponse.model_validate(assignment),
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
    d = AssignmentResponse.model_validate(assignment).model_dump()
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
    items, total = await SubmissionService.list_for_student(
        current_user.user_id, db=db, offset=offset, limit=limit
    )
    return SubmissionListResponse(
        items=[SubmissionResponse.model_validate(s) for s in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/student/submissions/{submission_id}/result", response_model=SubmissionDetailResponse)
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
    from app.modules.m06_labs_evaluator.schemas import EvaluationResponse
    eval_resp = (
        EvaluationResponse.model_validate(sub.evaluation)
        if sub.evaluation
        else None
    )
    return SubmissionDetailResponse(
        **SubmissionResponse.model_validate(sub).model_dump(),
        content_text=None,          # content not returned in result view
        ai_scan_result=sub.ai_scan_result,
        evaluation=eval_resp,
    )
