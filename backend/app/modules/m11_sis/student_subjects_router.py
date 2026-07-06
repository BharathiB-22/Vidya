"""
My Subjects / Subject Details — student self-service router.

Mounted at /sis/me/subjects* by the main SIS router (see m11_sis/router.py).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.student_subjects_schemas import MySubjectsOut, SubjectDetailOut
from app.modules.m11_sis.student_subjects_service import StudentSubjectsService

student_subjects_router = APIRouter(tags=["M11 SIS Self-Service"])


@student_subjects_router.get("/me/subjects", response_model=MySubjectsOut)
async def get_my_subjects(
    semester_id: UUID | None = Query(None, description="Filter to a specific semester (defaults to current)"),
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> MySubjectsOut:
    return await StudentSubjectsService.get_my_subjects(current_user.user_id, db, semester_id=semester_id)


@student_subjects_router.get("/me/subjects/{course_id}", response_model=SubjectDetailOut)
async def get_my_subject_detail(
    course_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SubjectDetailOut:
    detail = await StudentSubjectsService.get_subject_detail(current_user.user_id, course_id, db)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Subject not found or you are not enrolled in it."},
        )
    return detail
