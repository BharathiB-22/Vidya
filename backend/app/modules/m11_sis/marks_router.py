"""
SIS Internal Marks — H57 Router.

RBAC:
  _faculty_write = FACULTY role OR DEAN with active FACULTY grant (create/edit components, enter marks)
  _MANAGERS      = ADMIN, DEAN         (lock, reopen, analytics, readiness)
  _READERS       = FACULTY, ADMIN, DEAN (view components and entries)
  _STUDENT       = STUDENT only        (self-view published/locked marks)

Service-level guards enforce that FACULTY can only operate on their assigned courses.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles, require_responsibility
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.marks_schemas import (
    BUILT_IN_TEMPLATES,
    BulkMarkEntryIn, BulkMarkEntryResult, ComponentCreateIn, ComponentOut,
    ComponentTemplate, ComponentUpdateIn, MarkEntryOut, MarksImportCommitResult,
    MarksImportPreviewOut, MyMarksOut, ReopenComponentIn, SectionMarksReportOut,
    SectionReadinessOut, SingleMarkEditIn, FacultyCourseComponentSummary,
)
from app.modules.m11_sis.marks_service import MarksService, MarksServiceError

marks_router = APIRouter(tags=["M11 SIS Internal Marks"])

_MANAGERS = (TenantRole.ADMIN, TenantRole.DEAN)
_READERS  = (TenantRole.FACULTY, TenantRole.ADMIN, TenantRole.DEAN)
_STUDENT  = (TenantRole.STUDENT,)

# DEAN users who hold an active FACULTY responsibility grant may also write.
_faculty_write = require_responsibility(TenantRole.FACULTY)

DEFAULT_ATT_THRESHOLD = 75.0


def _err(e: MarksServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Component templates
# ---------------------------------------------------------------------------

@marks_router.get("/marks/component-templates", response_model=list[ComponentTemplate])
async def list_component_templates(
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
) -> list[ComponentTemplate]:
    return BUILT_IN_TEMPLATES


# ---------------------------------------------------------------------------
# Components — CRUD
# ---------------------------------------------------------------------------

@marks_router.post("/marks/components", response_model=ComponentOut, status_code=201)
async def create_component(
    body: ComponentCreateIn,
    current_user: CurrentUser = Depends(_faculty_write),
    db: AsyncSession           = Depends(get_tenant_db_dep),
) -> ComponentOut:
    try:
        return await MarksService.create_component(
            body,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.get("/marks/components", response_model=list[ComponentOut])
async def list_components(
    course_id:   Optional[UUID] = Query(None),
    section_id:  Optional[UUID] = Query(None),
    semester_id: Optional[UUID] = Query(None),
    status:      Optional[str]  = Query(None, description="DRAFT, PUBLISHED, or LOCKED"),
    current_user: CurrentUser   = Depends(require_roles(*_READERS)),
    db: AsyncSession            = Depends(get_tenant_db_dep),
) -> list[ComponentOut]:
    try:
        return await MarksService.list_components(
            course_id=course_id,
            section_id=section_id,
            semester_id=semester_id,
            status=status,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.get("/marks/components/{component_id}", response_model=ComponentOut)
async def get_component(
    component_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> ComponentOut:
    try:
        return await MarksService.get_component(
            component_id,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.put("/marks/components/{component_id}", response_model=ComponentOut)
async def update_component(
    component_id: UUID,
    body: ComponentUpdateIn,
    current_user: CurrentUser = Depends(_faculty_write),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> ComponentOut:
    try:
        return await MarksService.update_component(
            component_id, body,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.delete("/marks/components/{component_id}", status_code=204)
async def delete_component(
    component_id: UUID,
    current_user: CurrentUser = Depends(_faculty_write),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> None:
    try:
        await MarksService.delete_component(
            component_id,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

@marks_router.post("/marks/components/{component_id}/publish", response_model=ComponentOut)
async def publish_component(
    component_id: UUID,
    current_user: CurrentUser = Depends(_faculty_write),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> ComponentOut:
    try:
        return await MarksService.publish_component(
            component_id,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.post("/marks/components/{component_id}/lock", response_model=ComponentOut)
async def lock_component(
    component_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> ComponentOut:
    try:
        return await MarksService.lock_component(
            component_id,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.post("/marks/components/{component_id}/reopen", response_model=ComponentOut)
async def reopen_component(
    component_id: UUID,
    body: ReopenComponentIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> ComponentOut:
    try:
        return await MarksService.reopen_component(
            component_id, body,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Mark entries
# ---------------------------------------------------------------------------

@marks_router.get("/marks/components/{component_id}/entries", response_model=list[MarkEntryOut])
async def get_entries(
    component_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> list[MarkEntryOut]:
    try:
        return await MarksService.get_entries(
            component_id,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.post(
    "/marks/components/{component_id}/entries/bulk",
    response_model=BulkMarkEntryResult,
)
async def bulk_enter_marks(
    component_id: UUID,
    body: BulkMarkEntryIn,
    current_user: CurrentUser = Depends(_faculty_write),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> BulkMarkEntryResult:
    try:
        return await MarksService.bulk_enter_marks(
            component_id, body,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.patch(
    "/marks/components/{component_id}/entries/{entry_id}",
    response_model=MarkEntryOut,
)
async def edit_entry(
    component_id: UUID,
    entry_id:     UUID,
    body: SingleMarkEditIn,
    current_user: CurrentUser = Depends(_faculty_write),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> MarkEntryOut:
    try:
        return await MarksService.edit_single_entry(
            component_id, entry_id, body,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Excel import / export
# ---------------------------------------------------------------------------

@marks_router.get("/marks/components/{component_id}/entries/template.xlsx")
async def download_marks_template(
    component_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> Response:
    try:
        content, filename = await MarksService.get_excel_template(component_id, db)
    except MarksServiceError as e:
        raise _err(e)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@marks_router.post(
    "/marks/components/{component_id}/entries/import/preview",
    response_model=MarksImportPreviewOut,
)
async def import_preview(
    component_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(_faculty_write),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> MarksImportPreviewOut:
    content = await file.read()
    try:
        return await MarksService.import_preview(
            component_id,
            content=content,
            filename=file.filename or "marks.xlsx",
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


@marks_router.post(
    "/marks/components/{component_id}/entries/import/commit",
    response_model=MarksImportCommitResult,
)
async def import_commit(
    component_id: UUID,
    file: UploadFile = File(...),
    edit_reason: Optional[str] = Query(None),
    current_user: CurrentUser  = Depends(_faculty_write),
    db: AsyncSession           = Depends(get_tenant_db_dep),
) -> MarksImportCommitResult:
    content = await file.read()
    try:
        return await MarksService.import_commit(
            component_id,
            content=content,
            filename=file.filename or "marks.xlsx",
            edit_reason=edit_reason,
            actor_id=current_user.user_id,
            actor_role=current_user.viewing_role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except MarksServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Analytics — ADMIN / DEAN
# ---------------------------------------------------------------------------

@marks_router.get("/marks/analytics/section/{section_id}", response_model=SectionMarksReportOut)
async def section_marks_report(
    section_id:   UUID,
    course_id:    Optional[UUID] = Query(None),
    current_user: CurrentUser    = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession             = Depends(get_tenant_db_dep),
) -> SectionMarksReportOut:
    try:
        return await MarksService.get_section_marks_report(section_id, course_id, db)
    except MarksServiceError as e:
        raise _err(e)


@marks_router.get("/marks/readiness/section/{section_id}", response_model=SectionReadinessOut)
async def section_readiness(
    section_id:  UUID,
    threshold:   float = Query(DEFAULT_ATT_THRESHOLD, description="Attendance threshold %"),
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> SectionReadinessOut:
    try:
        return await MarksService.get_section_readiness(section_id, threshold, db)
    except MarksServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Faculty overview
# ---------------------------------------------------------------------------

@marks_router.get("/marks/my-courses", response_model=list[FacultyCourseComponentSummary])
async def my_courses_overview(
    current_user: CurrentUser = Depends(_faculty_write),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> list[FacultyCourseComponentSummary]:
    try:
        return await MarksService.get_my_courses_overview(current_user.user_id, db)
    except MarksServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Student self-view
# ---------------------------------------------------------------------------

@marks_router.get("/marks/me", response_model=MyMarksOut)
async def get_my_marks(
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> MyMarksOut:
    try:
        return await MarksService.get_my_marks(current_user.user_id, db)
    except MarksServiceError as e:
        raise _err(e)
