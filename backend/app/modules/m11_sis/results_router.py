"""
SIS Results Management — H60 FastAPI router.

Prefix: /results   (mounted under /api/sis/ by m11_sis/router.py)

Routes (~30):
  Grading Policy  : POST/GET /grading-policies, GET/PUT/{id},
                    POST/PUT/DELETE /{id}/bands, /{id}/bands/{band_id}
  Declarations    : POST/GET /declarations, GET/PUT/DELETE /{id},
                    POST /{id}/compute, /{id}/computation-status,
                    /{id}/verify, /{id}/publish, /{id}/lock, /{id}/revert-to-draft
  External Marks  : GET/POST /{id}/marks-sheet, /{id}/external-marks, PUT /{id}/external-marks/{eid}
  Grace Marks     : POST/GET /{id}/grace-marks, DELETE /{id}/grace-marks/{log_id}
  Results         : GET /{id}/results, /{id}/results/{student_id}
  Grade Cards     : GET /{id}/grade-cards, /{id}/grade-cards/{student_id}
  Rank / Toppers  : GET /{id}/rank-list, /{id}/toppers
  SGPA/CGPA       : POST /{id}/compute-sgpa-cgpa, POST /{id}/compute-ranks
  Student self    : GET /my-results, /my-grade-card/{decl_id}, /my-transcript
  History         : GET /students/{student_id}/transcript

RBAC:
  _MANAGERS = ADMIN, DEAN   (all write operations; verify/publish/lock)
  _DEAN     = DEAN only     (grace marks; verify)
  _ADMIN    = ADMIN only    (lock; grading policy CRUD)
  _READERS  = ADMIN, DEAN, FACULTY (read results; grade cards; rank list)
  _STUDENT  = STUDENT only  (self-service; PUBLISHED/LOCKED only)
  _ALL      = all 4 roles   (read published declarations)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.results_schemas import (
    ComputationStatusOut,
    ComputeResultIn,
    ComputeResultOut,
    ExternalMarkOut,
    ExternalMarksBulkIn,
    GraceMarkApplyIn,
    GraceMarkLogOut,
    GraceMarkRevokeIn,
    GradeCardOut,
    GradingBandIn,
    GradingPolicyCreateIn,
    GradingPolicyListOut,
    GradingPolicyOut,
    GradingPolicyUpdateIn,
    MarksSheetOut,
    RankListOut,
    ResultDeclarationCreateIn,
    ResultDeclarationListOut,
    ResultDeclarationOut,
    ResultDeclarationUpdateIn,
    RevertToDraftIn,
    SemesterResultOut,
    SubjectResultOut,
    TopperListOut,
    TranscriptOut,
)
from app.modules.m11_sis.results_service import (
    ExternalMarksService,
    GraceMarksService,
    GradeCardService,
    GradingPolicyService,
    RankListService,
    ResultComputationService,
    ResultDeclarationService,
    ResultsServiceError,
    SGPACGPAService,
    TranscriptService,
)
from app.modules.m11_sis.results_repository import (
    ExternalMarksRepo,
    GraceMarksLogRepo,
    GradingPolicyRepo,
    ResultDeclarationRepo,
    SemesterResultRepo,
    SubjectResultRepo,
)

results_router = APIRouter(prefix="/results", tags=["M11 SIS - Results Management"])

_ADMIN    = (TenantRole.ADMIN,)
_DEAN     = (TenantRole.DEAN,)
_MANAGERS = (TenantRole.ADMIN, TenantRole.DEAN)
_READERS  = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_STUDENT  = (TenantRole.STUDENT,)
_ALL      = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.STUDENT)


def _err(e: ResultsServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Grading Policy
# ─────────────────────────────────────────────────────────────────────────────

@results_router.post("/grading-policies", response_model=GradingPolicyOut, status_code=201)
async def create_grading_policy(
    body: GradingPolicyCreateIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GradingPolicyOut:
    try:
        policy = await GradingPolicyService.create(body, current_user.user_id, db)
        await db.commit()
        return GradingPolicyOut.model_validate(policy)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.get("/grading-policies", response_model=list[GradingPolicyListOut])
async def list_grading_policies(
    active_only: bool = Query(True),
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[GradingPolicyListOut]:
    policies = await GradingPolicyRepo.list_all(db, active_only=active_only)
    return [
        GradingPolicyListOut(
            id              = p.id,
            name            = p.name,
            program_id      = p.program_id,
            pass_percentage = p.pass_percentage,
            is_default      = p.is_default,
            is_active       = p.is_active,
            band_count      = len(p.bands),
        )
        for p in policies
    ]


@results_router.get("/grading-policies/{policy_id}", response_model=GradingPolicyOut)
async def get_grading_policy(
    policy_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GradingPolicyOut:
    policy = await GradingPolicyRepo.get_by_id(policy_id, db)
    if not policy:
        raise HTTPException(404, detail="Grading policy not found")
    return GradingPolicyOut.model_validate(policy)


@results_router.put("/grading-policies/{policy_id}", response_model=GradingPolicyOut)
async def update_grading_policy(
    policy_id: UUID,
    body: GradingPolicyUpdateIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GradingPolicyOut:
    try:
        policy = await GradingPolicyService.update(policy_id, body, db)
        await db.commit()
        return GradingPolicyOut.model_validate(policy)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.post("/grading-policies/{policy_id}/bands",
                     response_model=GradingPolicyOut, status_code=201)
async def add_grading_band(
    policy_id: UUID,
    body: GradingBandIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GradingPolicyOut:
    try:
        await GradingPolicyService.add_band(policy_id, body, db)
        await db.commit()
        policy = await GradingPolicyRepo.get_by_id(policy_id, db)
        return GradingPolicyOut.model_validate(policy)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.put("/grading-policies/{policy_id}/bands/{band_id}",
                    response_model=GradingPolicyOut)
async def update_grading_band(
    policy_id: UUID,
    band_id: UUID,
    body: GradingBandIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GradingPolicyOut:
    try:
        await GradingPolicyService.update_band(band_id, body, db)
        await db.commit()
        policy = await GradingPolicyRepo.get_by_id(policy_id, db)
        return GradingPolicyOut.model_validate(policy)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.delete("/grading-policies/{policy_id}/bands/{band_id}", status_code=204)
async def delete_grading_band(
    policy_id: UUID,
    band_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await GradingPolicyService.delete_band(band_id, db)
        await db.commit()
    except ResultsServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Result Declarations
# ─────────────────────────────────────────────────────────────────────────────

@results_router.post("/declarations", response_model=ResultDeclarationOut, status_code=201)
async def create_declaration(
    body: ResultDeclarationCreateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ResultDeclarationOut:
    try:
        decl = await ResultDeclarationService.create(body, current_user.user_id, db)
        await db.commit()
        return ResultDeclarationOut.model_validate(decl)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.get("/declarations", response_model=list[ResultDeclarationListOut])
async def list_declarations(
    semester_id:      Optional[UUID] = Query(None),
    status:           Optional[str]  = Query(None),
    declaration_type: Optional[str]  = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ResultDeclarationListOut]:
    if semester_id:
        decls = await ResultDeclarationRepo.list_by_semester(
            semester_id, db, status=status, declaration_type=declaration_type
        )
    else:
        decls = await ResultDeclarationRepo.list_published(db)
    return [ResultDeclarationListOut.model_validate(d) for d in decls]


@results_router.get("/declarations/{declaration_id}", response_model=ResultDeclarationOut)
async def get_declaration(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ResultDeclarationOut:
    decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
    if not decl:
        raise HTTPException(404, detail="Result declaration not found")
    return ResultDeclarationOut.model_validate(decl)


@results_router.put("/declarations/{declaration_id}", response_model=ResultDeclarationOut)
async def update_declaration(
    declaration_id: UUID,
    body: ResultDeclarationUpdateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ResultDeclarationOut:
    try:
        decl = await ResultDeclarationService.update(declaration_id, body, db)
        await db.commit()
        return ResultDeclarationOut.model_validate(decl)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.delete("/declarations/{declaration_id}", status_code=204)
async def delete_declaration(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await ResultDeclarationService.delete(declaration_id, db)
        await db.commit()
    except ResultsServiceError as e:
        raise _err(e)


@results_router.get("/declarations/{declaration_id}/computation-status",
                    response_model=ComputationStatusOut)
async def get_computation_status(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ComputationStatusOut:
    try:
        return await ExternalMarksService.get_computation_status(declaration_id, db)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.post("/declarations/{declaration_id}/compute",
                     response_model=ComputeResultOut)
async def compute_results(
    declaration_id: UUID,
    body: ComputeResultIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ComputeResultOut:
    try:
        result = await ResultComputationService.compute(
            declaration_id, current_user.user_id, body.force, db
        )
        await db.commit()
        return result
    except ResultsServiceError as e:
        raise _err(e)


@results_router.post("/declarations/{declaration_id}/compute-sgpa-cgpa",
                     response_model=list[SemesterResultOut])
async def compute_sgpa_cgpa(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SemesterResultOut]:
    try:
        rows = await SGPACGPAService.compute_sgpa_cgpa(declaration_id, db)
        await db.commit()
        return [SemesterResultOut.model_validate(r) for r in rows]
    except ResultsServiceError as e:
        raise _err(e)


@results_router.post("/declarations/{declaration_id}/compute-ranks",
                     response_model=list[SemesterResultOut])
async def compute_ranks(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SemesterResultOut]:
    try:
        rows = await RankListService.compute_ranks(declaration_id, db)
        await db.commit()
        return [SemesterResultOut.model_validate(r) for r in rows]
    except ResultsServiceError as e:
        raise _err(e)


# ── Human Gates ───────────────────────────────────────────────────────────────

@results_router.post("/declarations/{declaration_id}/verify",
                     response_model=ResultDeclarationOut)
async def verify_declaration(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ResultDeclarationOut:
    try:
        decl = await ResultDeclarationService.verify(
            declaration_id, current_user.user_id, db
        )
        await db.commit()
        return ResultDeclarationOut.model_validate(decl)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.post("/declarations/{declaration_id}/publish",
                     response_model=ResultDeclarationOut)
async def publish_declaration(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ResultDeclarationOut:
    try:
        decl = await ResultDeclarationService.publish(
            declaration_id, current_user.user_id, db
        )
        await db.commit()
        return ResultDeclarationOut.model_validate(decl)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.post("/declarations/{declaration_id}/lock",
                     response_model=ResultDeclarationOut)
async def lock_declaration(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ResultDeclarationOut:
    try:
        decl = await ResultDeclarationService.lock(
            declaration_id, current_user.user_id, db
        )
        await db.commit()
        return ResultDeclarationOut.model_validate(decl)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.post("/declarations/{declaration_id}/revert-to-draft",
                     response_model=ResultDeclarationOut)
async def revert_to_draft(
    declaration_id: UUID,
    body: RevertToDraftIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ResultDeclarationOut:
    try:
        decl = await ResultDeclarationService.revert_to_draft(
            declaration_id, body, current_user.user_id, db
        )
        await db.commit()
        return ResultDeclarationOut.model_validate(decl)
    except ResultsServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# External Marks
# ─────────────────────────────────────────────────────────────────────────────

@results_router.get("/declarations/{declaration_id}/marks-sheet",
                    response_model=MarksSheetOut)
async def get_marks_sheet(
    declaration_id: UUID,
    section_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> MarksSheetOut:
    try:
        status = await ExternalMarksService.get_computation_status(declaration_id, db)
        rows   = await ExternalMarksRepo.list_by_declaration(declaration_id, db, section_id)
        from app.modules.m11_sis.results_schemas import MarksSheetRowOut
        sheet_rows = [
            MarksSheetRowOut(
                student_id              = r.student_id,
                course_id               = r.course_id,
                section_id              = r.section_id,
                external_marks_obtained = r.external_marks_obtained,
                external_marks_max      = r.external_marks_max,
                is_absent               = r.is_absent,
                entered_by              = r.entered_by,
                entered_at              = r.entered_at,
            )
            for r in rows
        ]
        return MarksSheetOut(
            declaration_id = declaration_id,
            total_students = len({r.student_id for r in rows}),
            total_courses  = len({r.course_id for r in rows}),
            entered_count  = status.external_marks_entered,
            pending_count  = status.external_marks_pending,
            rows           = sheet_rows,
        )
    except ResultsServiceError as e:
        raise _err(e)


@results_router.post("/declarations/{declaration_id}/external-marks",
                     response_model=list[ExternalMarkOut])
async def bulk_enter_external_marks(
    declaration_id: UUID,
    body: ExternalMarksBulkIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ExternalMarkOut]:
    try:
        rows = await ExternalMarksService.bulk_upsert(
            declaration_id, body, current_user.user_id, db
        )
        await db.commit()
        return [ExternalMarkOut.model_validate(r) for r in rows]
    except ResultsServiceError as e:
        raise _err(e)


@results_router.get("/declarations/{declaration_id}/external-marks",
                    response_model=list[ExternalMarkOut])
async def list_external_marks(
    declaration_id: UUID,
    section_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ExternalMarkOut]:
    rows = await ExternalMarksRepo.list_by_declaration(declaration_id, db, section_id)
    return [ExternalMarkOut.model_validate(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Grace Marks (DEAN only)
# ─────────────────────────────────────────────────────────────────────────────

@results_router.post("/declarations/{declaration_id}/grace-marks",
                     response_model=GraceMarkLogOut, status_code=201)
async def apply_grace_marks(
    declaration_id: UUID,
    body: GraceMarkApplyIn,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GraceMarkLogOut:
    try:
        log = await GraceMarksService.apply(
            declaration_id, body, current_user.user_id, db
        )
        await db.commit()
        return GraceMarkLogOut.model_validate(log)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.get("/declarations/{declaration_id}/grace-marks",
                    response_model=list[GraceMarkLogOut])
async def list_grace_marks(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[GraceMarkLogOut]:
    logs = await GraceMarksLogRepo.list_by_declaration(declaration_id, db)
    return [GraceMarkLogOut.model_validate(l) for l in logs]


@results_router.delete("/declarations/{declaration_id}/grace-marks/{log_id}",
                       status_code=204)
async def revoke_grace_marks(
    declaration_id: UUID,
    log_id: UUID,
    body: GraceMarkRevokeIn,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await GraceMarksService.revoke(
            log_id, body.revoke_reason, current_user.user_id, db
        )
        await db.commit()
    except ResultsServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Subject Results
# ─────────────────────────────────────────────────────────────────────────────

@results_router.get("/declarations/{declaration_id}/results",
                    response_model=list[SubjectResultOut])
async def list_results(
    declaration_id: UUID,
    section_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SubjectResultOut]:
    rows = await SubjectResultRepo.list_by_declaration(
        declaration_id, db, section_id=section_id
    )
    return [SubjectResultOut.model_validate(r) for r in rows]


@results_router.get("/declarations/{declaration_id}/results/{student_id}",
                    response_model=list[SubjectResultOut])
async def get_student_results(
    declaration_id: UUID,
    student_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SubjectResultOut]:
    rows = await SubjectResultRepo.list_by_declaration(
        declaration_id, db, student_id=student_id
    )
    return [SubjectResultOut.model_validate(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Grade Cards
# ─────────────────────────────────────────────────────────────────────────────

@results_router.get("/declarations/{declaration_id}/grade-cards/{student_id}",
                    response_model=GradeCardOut)
async def get_grade_card(
    declaration_id: UUID,
    student_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GradeCardOut:
    try:
        return await GradeCardService.get_grade_card(declaration_id, student_id, db)
    except ResultsServiceError as e:
        raise _err(e)


@results_router.get("/declarations/{declaration_id}/grade-cards",
                    response_model=list[GradeCardOut])
async def list_grade_cards(
    declaration_id: UUID,
    section_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[GradeCardOut]:
    try:
        sem_results = await SemesterResultRepo.list_by_declaration(declaration_id, db)
        cards = []
        for sr in sem_results:
            card = await GradeCardService.get_grade_card(declaration_id, sr.student_id, db)
            cards.append(card)
        return cards
    except ResultsServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Rank List + Toppers
# ─────────────────────────────────────────────────────────────────────────────

@results_router.get("/declarations/{declaration_id}/rank-list",
                    response_model=RankListOut)
async def get_rank_list(
    declaration_id: UUID,
    scope:         str            = Query("program"),
    scope_ref_id:  Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> RankListOut:
    try:
        return await RankListService.get_rank_list(
            declaration_id, scope, scope_ref_id, db
        )
    except ResultsServiceError as e:
        raise _err(e)


@results_router.get("/declarations/{declaration_id}/toppers",
                    response_model=TopperListOut)
async def get_toppers(
    declaration_id: UUID,
    scope:         str            = Query("program"),
    scope_ref_id:  Optional[UUID] = Query(None),
    top_n:         int            = Query(10),
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TopperListOut:
    try:
        return await RankListService.get_toppers(
            declaration_id, scope, scope_ref_id, top_n, db
        )
    except ResultsServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Academic History
# ─────────────────────────────────────────────────────────────────────────────

@results_router.get("/students/{student_id}/transcript", response_model=TranscriptOut)
async def get_student_transcript(
    student_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TranscriptOut:
    try:
        return await TranscriptService.get_transcript(student_id, db)
    except ResultsServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Student self-service (PUBLISHED/LOCKED only)
# ─────────────────────────────────────────────────────────────────────────────

@results_router.get("/my-results", response_model=list[SemesterResultOut])
async def my_results(
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SemesterResultOut]:
    rows = await SemesterResultRepo.list_by_student(
        current_user.user_id, db, published_only=True
    )
    return [SemesterResultOut.model_validate(r) for r in rows]


@results_router.get("/my-grade-card/{declaration_id}", response_model=GradeCardOut)
async def my_grade_card(
    declaration_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GradeCardOut:
    # Guard: declaration must be PUBLISHED or LOCKED
    decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
    if not decl:
        raise HTTPException(404, detail="Result declaration not found")
    if decl.status not in ("PUBLISHED", "LOCKED"):
        raise HTTPException(403, detail="Results are not yet published")
    try:
        return await GradeCardService.get_grade_card(
            declaration_id, current_user.user_id, db
        )
    except ResultsServiceError as e:
        raise _err(e)


@results_router.get("/my-transcript", response_model=TranscriptOut)
async def my_transcript(
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TranscriptOut:
    try:
        return await TranscriptService.get_transcript(current_user.user_id, db)
    except ResultsServiceError as e:
        raise _err(e)
