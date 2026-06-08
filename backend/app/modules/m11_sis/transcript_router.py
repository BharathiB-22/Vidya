"""
SIS Transcript Generation — H61 FastAPI router.

Mounted under /api/sis/ by m11_sis/router.py.
Public verify route mounted at /api/verify/ by main.py (no auth).

Routes:
  POST   /transcripts/request              — student requests own transcript
  POST   /transcripts/{id}/generate        — admin/dean dispatches PDF generation
  POST   /transcripts/{id}/issue           — admin/dean issues transcript (Gate 2)
  POST   /transcripts/{id}/revoke          — admin/dean revokes issued transcript
  POST   /transcripts/{id}/regenerate      — admin/dean supersedes + creates new
  GET    /transcripts                       — admin/dean list all (paginated)
  GET    /transcripts/{id}                 — admin/dean detail with lines
  GET    /transcripts/{id}/pdf             — presigned S3 URL
  GET    /transcripts/{id}/verification-log — admin/dean audit trail
  GET    /my-transcripts                   — student own history
  GET    /my-degree-progress               — student own progress
  GET    /students/{student_id}/degree-progress — admin/dean view any student

Public (no auth, mounted separately):
  GET    /verify/{code}                    — QR verification (no marks/CGPA)
"""
from __future__ import annotations

import uuid as _uuid_module
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.transcript_schemas import (
    DegreeProgressRead,
    GenerateDispatchResponse,
    PDFDownloadResponse,
    TranscriptDetailRead,
    TranscriptRequestCreate,
    TranscriptRevokeIn,
    TranscriptSummaryRead,
    TranscriptVerifyResponse,
    VerificationLogRead,
)
from app.modules.m11_sis.transcript_service import (
    DegreeProgressService,
    TranscriptLifecycleService,
    TranscriptServiceError,
    TranscriptVerifyService,
)

_MANAGERS = [TenantRole.ADMIN, TenantRole.DEAN]
_STUDENT  = [TenantRole.STUDENT]
_ALL      = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.STUDENT]

transcript_router = APIRouter(prefix="/transcripts", tags=["H61 Transcripts"])
verify_router     = APIRouter(prefix="/verify",      tags=["H61 Public Verify"])


async def _get_platform_db():
    """Yield the platform (public schema) async session for the verify endpoint."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session


def _svc_error(exc: TranscriptServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


# ─────────────────────────────────────────────────────────────────────────────
# Student — request own transcript
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.post(
    "/request",
    response_model=TranscriptSummaryRead,
    status_code=201,
    summary="Student requests a transcript",
)
async def request_transcript(
    body: TranscriptRequestCreate,
    current_user: CurrentUser = Depends(require_roles(_ALL)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    # Determine student_id
    if current_user.role == TenantRole.STUDENT:
        student_id = current_user.id
        if body.student_id and body.student_id != current_user.id:
            raise HTTPException(403, "Students can only request their own transcript.")
    else:
        # ADMIN/DEAN can request on behalf of a student
        if not body.student_id:
            raise HTTPException(400, "student_id is required when requesting on behalf of a student.")
        student_id = body.student_id

    try:
        transcript = await TranscriptLifecycleService.request(
            student_id     = student_id,
            transcript_type = body.transcript_type,
            purpose        = body.purpose,
            actor_user_id  = current_user.id,
            actor_role     = current_user.role,
            tenant_id      = current_user.tenant_id,
            schema_name    = current_user.schema_name,
            db             = db,
        )
        await db.commit()
    except TranscriptServiceError as exc:
        raise _svc_error(exc)
    return transcript


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — dispatch PDF generation
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.post(
    "/{transcript_id}/generate",
    response_model=GenerateDispatchResponse,
    summary="Admin/Dean dispatches PDF generation",
)
async def dispatch_generate(
    transcript_id: UUID,
    current_user: CurrentUser = Depends(require_roles(_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    # Resolve tenant code for transcript numbering
    from sqlalchemy import text
    t_row = (await db.execute(
        text("SELECT slug FROM public.tenants WHERE id = :tid"),
        {"tid": str(current_user.tenant_id)},
    )).mappings().one_or_none()
    tenant_code = (t_row["slug"] if t_row else "UNK").upper().replace("-", "")[:8]

    try:
        celery_task_id = await TranscriptLifecycleService.dispatch_generate(
            transcript_id  = transcript_id,
            actor_user_id  = current_user.id,
            actor_role     = current_user.role,
            tenant_id      = current_user.tenant_id,
            schema_name    = current_user.schema_name,
            tenant_code    = tenant_code,
            db             = db,
        )
        await db.commit()
    except TranscriptServiceError as exc:
        raise _svc_error(exc)

    return GenerateDispatchResponse(
        transcript_id  = transcript_id,
        celery_task_id = celery_task_id,
        message        = "PDF generation queued. Refresh after a few seconds.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — issue  (Gate 2: human ratification)
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.post(
    "/{transcript_id}/issue",
    response_model=TranscriptSummaryRead,
    summary="Admin/Dean officially issues a generated transcript",
)
async def issue_transcript(
    transcript_id: UUID,
    current_user: CurrentUser = Depends(require_roles(_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    try:
        transcript = await TranscriptLifecycleService.issue(
            transcript_id  = transcript_id,
            actor_user_id  = current_user.id,
            actor_role     = current_user.role,
            tenant_id      = current_user.tenant_id,
            schema_name    = current_user.schema_name,
            db             = db,
        )
        await db.commit()
    except TranscriptServiceError as exc:
        raise _svc_error(exc)
    return transcript


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — revoke
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.post(
    "/{transcript_id}/revoke",
    response_model=TranscriptSummaryRead,
    summary="Admin/Dean revokes an issued transcript",
)
async def revoke_transcript(
    transcript_id: UUID,
    body: TranscriptRevokeIn,
    current_user: CurrentUser = Depends(require_roles(_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    try:
        transcript = await TranscriptLifecycleService.revoke(
            transcript_id  = transcript_id,
            revoke_reason  = body.revoke_reason,
            actor_user_id  = current_user.id,
            actor_role     = current_user.role,
            tenant_id      = current_user.tenant_id,
            schema_name    = current_user.schema_name,
            db             = db,
        )
        await db.commit()
    except TranscriptServiceError as exc:
        raise _svc_error(exc)
    return transcript


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — regenerate (supersede + new version)
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.post(
    "/{transcript_id}/regenerate",
    response_model=TranscriptSummaryRead,
    status_code=201,
    summary="Admin/Dean supersedes an issued transcript and creates a new version",
)
async def regenerate_transcript(
    transcript_id: UUID,
    current_user: CurrentUser = Depends(require_roles(_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    try:
        new_transcript = await TranscriptLifecycleService.regenerate(
            transcript_id  = transcript_id,
            actor_user_id  = current_user.id,
            actor_role     = current_user.role,
            tenant_id      = current_user.tenant_id,
            schema_name    = current_user.schema_name,
            db             = db,
        )
        await db.commit()
    except TranscriptServiceError as exc:
        raise _svc_error(exc)
    return new_transcript


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — list all
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.get(
    "",
    response_model=dict,
    summary="Admin/Dean list all transcripts (paginated)",
)
async def list_transcripts(
    status: Optional[str] = Query(None),
    offset: int           = Query(0, ge=0),
    limit: int            = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.transcript_repository import TranscriptRepo
    transcripts = await TranscriptRepo.list_all(
        db, status_filter=status, offset=offset, limit=limit
    )
    total = await TranscriptRepo.count_all(db, status_filter=status)
    return {
        "items":  [TranscriptSummaryRead.model_validate(t) for t in transcripts],
        "total":  total,
        "offset": offset,
        "limit":  limit,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Student — own transcript history
# NOTE: Must be defined before /{transcript_id} so FastAPI doesn't try to
#       convert "my-transcripts" as a UUID path parameter.
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.get(
    "/my-transcripts",
    response_model=list[TranscriptSummaryRead],
    summary="Student view own transcript history",
)
async def my_transcripts(
    current_user: CurrentUser = Depends(require_roles(_STUDENT)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.transcript_repository import TranscriptRepo
    transcripts = await TranscriptRepo.list_for_student(current_user.id, db)
    return transcripts


# ─────────────────────────────────────────────────────────────────────────────
# Student — own degree progress
# NOTE: Must be defined before /{transcript_id}.
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.get(
    "/my-degree-progress",
    response_model=DegreeProgressRead,
    summary="Student view own degree progress",
)
async def my_degree_progress(
    current_user: CurrentUser = Depends(require_roles(_STUDENT)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    return await DegreeProgressService.get_progress(current_user.id, db)


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — any student's degree progress
# NOTE: /students/{student_id}/... does not collide with /{transcript_id}
#       but kept before it for clarity and symmetry.
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.get(
    "/students/{student_id}/degree-progress",
    response_model=DegreeProgressRead,
    summary="Admin/Dean view any student's degree progress",
)
async def student_degree_progress(
    student_id: UUID,
    current_user: CurrentUser = Depends(require_roles(_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    return await DegreeProgressService.get_progress(student_id, db)


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — detail
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.get(
    "/{transcript_id}",
    response_model=TranscriptDetailRead,
    summary="Admin/Dean get transcript detail with snapshot lines",
)
async def get_transcript_detail(
    transcript_id: UUID,
    current_user: CurrentUser = Depends(require_roles(_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.transcript_repository import TranscriptRepo
    transcript = await TranscriptRepo.get_by_id(transcript_id, db, with_lines=True)
    if not transcript:
        raise HTTPException(404, "Transcript not found.")
    return transcript


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — presigned PDF URL
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.get(
    "/{transcript_id}/pdf",
    response_model=PDFDownloadResponse,
    summary="Get presigned URL to download transcript PDF",
)
async def get_pdf_url(
    transcript_id: UUID,
    current_user: CurrentUser = Depends(require_roles(_MANAGERS + _STUDENT)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.transcript_repository import TranscriptRepo
    transcript = await TranscriptRepo.get_by_id(transcript_id, db)
    if not transcript:
        raise HTTPException(404, "Transcript not found.")

    # Students may only access their own
    if current_user.role == TenantRole.STUDENT and transcript.student_id != current_user.id:
        raise HTTPException(403, "Access denied.")

    if not transcript.pdf_s3_key:
        raise HTTPException(404, "PDF not yet generated.")

    presigned_url = _generate_presigned_url(transcript.pdf_s3_key)
    expires_at    = datetime.now(timezone.utc) + timedelta(minutes=15)

    await AuditService.log(
        AuditEventType.TRANSCRIPT_PDF_DOWNLOADED,
        actor_user_id = current_user.id,
        actor_role    = current_user.role,
        tenant_id     = current_user.tenant_id,
        schema_name   = current_user.schema_name,
        target_entity = "SisTranscript",
        target_id     = str(transcript_id),
        metadata      = {"s3_key": transcript.pdf_s3_key},
    )
    return PDFDownloadResponse(presigned_url=presigned_url, expires_at=expires_at)


# ─────────────────────────────────────────────────────────────────────────────
# Admin/Dean — verification log
# ─────────────────────────────────────────────────────────────────────────────

@transcript_router.get(
    "/{transcript_id}/verification-log",
    response_model=list[VerificationLogRead],
    summary="Admin/Dean list QR scan verification log",
)
async def get_verification_log(
    transcript_id: UUID,
    offset: int = Query(0, ge=0),
    limit:  int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.transcript_repository import VerificationLogRepo
    logs = await VerificationLogRepo.list_for_transcript(
        transcript_id, db, offset=offset, limit=limit
    )
    return logs


# ─────────────────────────────────────────────────────────────────────────────
# Public — QR verify (no auth, no marks/CGPA)
# ─────────────────────────────────────────────────────────────────────────────

@verify_router.get(
    "/{code}",
    response_model=TranscriptVerifyResponse,
    summary="Public QR-code transcript verification (no auth required)",
)
async def verify_transcript(
    code: str,
    request: Request,
    db: AsyncSession = Depends(_get_platform_db),
):
    client_ip = request.client.host if request.client else None
    return await TranscriptVerifyService.verify(
        code_str          = code,
        requester_ip      = client_ip,
        requester_context = "QR_SCAN",
        db                = db,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _generate_presigned_url(s3_key: str, expiry_seconds: int = 900) -> str:
    import boto3
    from app.config import settings
    client = boto3.client(
        "s3",
        endpoint_url          = settings.S3_ENDPOINT,
        aws_access_key_id     = settings.S3_ACCESS_KEY,
        aws_secret_access_key = settings.S3_SECRET_KEY,
        region_name           = "us-east-1",
    )
    return client.generate_presigned_url(
        "get_object",
        Params  = {"Bucket": settings.S3_BUCKET, "Key": s3_key},
        ExpiresIn = expiry_seconds,
    )
