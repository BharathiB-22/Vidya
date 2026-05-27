"""
Academic Structure — router.

RBAC
----
  _WRITE = ADMIN only     (create, update, deactivate, generate-semesters)
  _READ  = all authenticated roles (department/program/batch/semester/section lists)

Router is pure HTTP glue. All validation lives in service.py.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m_academics.schemas import (
    BatchCreate, BatchOut, BatchUpdate,
    DepartmentCreate, DepartmentOut, DepartmentUpdate,
    GenerateSemestersOut,
    ProgramCreate, ProgramOut, ProgramUpdate,
    SectionCreate, SectionOut, SectionUpdate,
    SemesterCreate, SemesterOut, SemesterUpdate,
)
from app.modules.m_academics.service import (
    AcadServiceError,
    BatchService, DepartmentService, ProgramService,
    SectionService, SemesterService,
)

router = APIRouter(tags=["academics"])

_ADMIN = (TenantRole.ADMIN,)


def _err(e: AcadServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ===========================================================================
# Departments
# ===========================================================================

@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[DepartmentOut]:
    rows = await DepartmentService.list_all(db, include_inactive=include_inactive)
    return [DepartmentOut.model_validate(r) for r in rows]


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(
    body: DepartmentCreate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> DepartmentOut:
    try:
        dept = await DepartmentService.create(body, db)
        return DepartmentOut.model_validate(dept)
    except AcadServiceError as e:
        raise _err(e)


@router.get("/departments/{dept_id}", response_model=DepartmentOut)
async def get_department(
    dept_id: UUID,
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> DepartmentOut:
    try:
        dept = await DepartmentService.get(dept_id, db)
        return DepartmentOut.model_validate(dept)
    except AcadServiceError as e:
        raise _err(e)


@router.put("/departments/{dept_id}", response_model=DepartmentOut)
async def update_department(
    dept_id: UUID,
    body: DepartmentUpdate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> DepartmentOut:
    try:
        dept = await DepartmentService.update(dept_id, body, db)
        return DepartmentOut.model_validate(dept)
    except AcadServiceError as e:
        raise _err(e)


# ===========================================================================
# Programs
# ===========================================================================

@router.get("/programs", response_model=list[ProgramOut])
async def list_programs(
    department_id: UUID | None = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ProgramOut]:
    rows = await ProgramService.list_all(db, department_id=department_id, include_inactive=include_inactive)
    return [ProgramOut.model_validate(r) for r in rows]


@router.post("/programs", response_model=ProgramOut, status_code=201)
async def create_program(
    body: ProgramCreate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramOut:
    try:
        prog = await ProgramService.create(body, db)
        return ProgramOut.model_validate(prog)
    except AcadServiceError as e:
        raise _err(e)


@router.get("/programs/{prog_id}", response_model=ProgramOut)
async def get_program(
    prog_id: UUID,
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramOut:
    try:
        prog = await ProgramService.get(prog_id, db)
        return ProgramOut.model_validate(prog)
    except AcadServiceError as e:
        raise _err(e)


@router.put("/programs/{prog_id}", response_model=ProgramOut)
async def update_program(
    prog_id: UUID,
    body: ProgramUpdate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramOut:
    try:
        prog = await ProgramService.update(prog_id, body, db)
        return ProgramOut.model_validate(prog)
    except AcadServiceError as e:
        raise _err(e)


# ===========================================================================
# Batches
# ===========================================================================

@router.get("/batches", response_model=list[BatchOut])
async def list_batches(
    program_id: UUID | None = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[BatchOut]:
    rows = await BatchService.list_all(db, program_id=program_id, include_inactive=include_inactive)
    return [BatchOut.model_validate(r) for r in rows]


@router.post("/batches", response_model=BatchOut, status_code=201)
async def create_batch(
    body: BatchCreate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> BatchOut:
    try:
        batch = await BatchService.create(body, db)
        return BatchOut.model_validate(batch)
    except AcadServiceError as e:
        raise _err(e)


@router.get("/batches/{batch_id}", response_model=BatchOut)
async def get_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> BatchOut:
    try:
        batch = await BatchService.get(batch_id, db)
        return BatchOut.model_validate(batch)
    except AcadServiceError as e:
        raise _err(e)


@router.put("/batches/{batch_id}", response_model=BatchOut)
async def update_batch(
    batch_id: UUID,
    body: BatchUpdate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> BatchOut:
    try:
        batch = await BatchService.update(batch_id, body, db)
        return BatchOut.model_validate(batch)
    except AcadServiceError as e:
        raise _err(e)


@router.post("/batches/{batch_id}/generate-semesters", response_model=GenerateSemestersOut)
async def generate_semesters(
    batch_id: UUID,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GenerateSemestersOut:
    try:
        return await BatchService.generate_semesters(batch_id, db)
    except AcadServiceError as e:
        raise _err(e)


# ===========================================================================
# Semesters
# ===========================================================================

@router.get("/semesters", response_model=list[SemesterOut])
async def list_semesters(
    batch_id: UUID | None = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SemesterOut]:
    rows = await SemesterService.list_all(db, batch_id=batch_id, include_inactive=include_inactive)
    return [SemesterOut.model_validate(r) for r in rows]


@router.post("/semesters", response_model=SemesterOut, status_code=201)
async def create_semester(
    body: SemesterCreate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SemesterOut:
    try:
        sem = await SemesterService.create(body, db)
        return SemesterOut.model_validate(sem)
    except AcadServiceError as e:
        raise _err(e)


@router.get("/semesters/{sem_id}", response_model=SemesterOut)
async def get_semester(
    sem_id: UUID,
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SemesterOut:
    try:
        sem = await SemesterService.get(sem_id, db)
        return SemesterOut.model_validate(sem)
    except AcadServiceError as e:
        raise _err(e)


@router.put("/semesters/{sem_id}", response_model=SemesterOut)
async def update_semester(
    sem_id: UUID,
    body: SemesterUpdate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SemesterOut:
    try:
        sem = await SemesterService.update(sem_id, body, db)
        return SemesterOut.model_validate(sem)
    except AcadServiceError as e:
        raise _err(e)


# ===========================================================================
# Sections
# ===========================================================================

@router.get("/sections", response_model=list[SectionOut])
async def list_sections(
    semester_id: UUID | None = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SectionOut]:
    rows = await SectionService.list_all(db, semester_id=semester_id, include_inactive=include_inactive)
    return [SectionOut.model_validate(r) for r in rows]


@router.post("/sections", response_model=SectionOut, status_code=201)
async def create_section(
    body: SectionCreate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SectionOut:
    try:
        section = await SectionService.create(body, db)
        return SectionOut.model_validate(section)
    except AcadServiceError as e:
        raise _err(e)


@router.get("/sections/{section_id}", response_model=SectionOut)
async def get_section(
    section_id: UUID,
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SectionOut:
    try:
        section = await SectionService.get(section_id, db)
        return SectionOut.model_validate(section)
    except AcadServiceError as e:
        raise _err(e)


@router.put("/sections/{section_id}", response_model=SectionOut)
async def update_section(
    section_id: UUID,
    body: SectionUpdate,
    _: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SectionOut:
    try:
        section = await SectionService.update(section_id, body, db)
        return SectionOut.model_validate(section)
    except AcadServiceError as e:
        raise _err(e)
