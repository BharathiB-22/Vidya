import io
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.onboarding.schemas import (
    CSVCommitResult,
    CSVPreviewResponse,
    GenerateStudentsRequest,
    GenerateStudentsResult,
    UsnBackfillCommitResult,
    UsnBackfillPreviewResponse,
)
from app.core.onboarding.faculty_program_schemas import (
    FacultyProgramAssignRequest,
    FacultyProgramListResponse,
    FacultyProgramOut,
    FacultyProgramRevokeRequest,
)
from app.core.onboarding.faculty_program_service import (
    FacultyProgramService,
    FacultyProgramServiceError,
)
from app.core.onboarding.service import OnboardingError, OnboardingService
from app.core.onboarding.usn_backfill_service import UsnBackfillService
from app.database import AsyncSessionLocal

router = APIRouter(tags=["onboarding"])

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


async def _admin_db(
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
) -> AsyncGenerator[AsyncSession, None]:
    if current_user.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "message": "SUPER_ADMIN cannot use tenant /admin/ endpoints",
            },
        )
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {current_user.schema_name}, public")
            )
            yield session


def _onboarding_err(e: OnboardingError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


def _read_file_upload(file: UploadFile) -> None:
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"error": "BAD_REQUEST", "message": "No file provided"},
        )
    name = file.filename.lower()
    if not (name.endswith(".csv") or name.endswith(".xlsx")):
        raise HTTPException(
            status_code=400,
            detail={"error": "BAD_REQUEST", "message": "Please upload a .csv or .xlsx file"},
        )


def _parse_uuid_form(value: str | None, field: str) -> "UUID | None":
    from uuid import UUID
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"error": "VALIDATION_ERROR", "message": f"{field} must be a valid UUID"},
        )


# ---------------------------------------------------------------------------
# Bulk student generation
# ---------------------------------------------------------------------------

@router.post("/generate-students", response_model=GenerateStudentsResult)
async def generate_students(
    body: GenerateStudentsRequest,
    db: AsyncSession = Depends(_admin_db),
) -> GenerateStudentsResult:
    try:
        return await OnboardingService.generate_students(body, db)
    except OnboardingError as e:
        raise _onboarding_err(e)


# ---------------------------------------------------------------------------
# CSV / XLSX import — students
# ---------------------------------------------------------------------------

@router.post("/import/students/preview", response_model=CSVPreviewResponse)
async def preview_students_csv(
    file: UploadFile = File(
        ...,
        description=(
            "CSV or XLSX with columns: full_name, email, identifier (opt). "
            "program_code required if no program_id context is supplied."
        ),
    ),
    program_id: str | None = Form(None),
    section_id: str | None = Form(None),
    db: AsyncSession = Depends(_admin_db),
) -> CSVPreviewResponse:
    _read_file_upload(file)
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "FILE_TOO_LARGE", "message": "File must be under 5 MB"},
        )
    ctx_program = _parse_uuid_form(program_id, "program_id")
    ctx_section = _parse_uuid_form(section_id, "section_id")
    return await OnboardingService.preview_students_csv(
        content, db,
        filename=file.filename or "students.csv",
        context_program_id=ctx_program,
        context_section_id=ctx_section,
    )


@router.post("/import/students/commit", response_model=CSVCommitResult)
async def commit_students_csv(
    file: UploadFile = File(...),
    default_password: str = Form(default="Student@123"),
    program_id: str | None = Form(None),
    section_id: str | None = Form(None),
    db: AsyncSession = Depends(_admin_db),
) -> CSVCommitResult:
    _read_file_upload(file)
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "FILE_TOO_LARGE", "message": "File must be under 5 MB"},
        )
    if len(default_password) < 8:
        raise HTTPException(
            status_code=422,
            detail={"error": "VALIDATION_ERROR", "message": "default_password must be ≥ 8 characters"},
        )
    ctx_program = _parse_uuid_form(program_id, "program_id")
    ctx_section = _parse_uuid_form(section_id, "section_id")
    return await OnboardingService.commit_students_csv(
        content, default_password, db,
        filename=file.filename or "students.csv",
        context_program_id=ctx_program,
        context_section_id=ctx_section,
    )


# ---------------------------------------------------------------------------
# CSV / XLSX import — faculty
# ---------------------------------------------------------------------------

@router.post("/import/faculty/preview", response_model=CSVPreviewResponse)
async def preview_faculty_csv(
    file: UploadFile = File(
        ...,
        description="CSV or XLSX with columns: full_name, email, employee_id (opt)",
    ),
    db: AsyncSession = Depends(_admin_db),
) -> CSVPreviewResponse:
    _read_file_upload(file)
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "FILE_TOO_LARGE", "message": "File must be under 5 MB"},
        )
    return await OnboardingService.preview_faculty_csv(
        content, db,
        filename=file.filename or "faculty.csv",
    )


@router.post("/import/faculty/commit", response_model=CSVCommitResult)
async def commit_faculty_csv(
    file: UploadFile = File(...),
    default_password: str = Form(default="Faculty@123"),
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(_admin_db),
) -> CSVCommitResult:
    _read_file_upload(file)
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "FILE_TOO_LARGE", "message": "File must be under 5 MB"},
        )
    if len(default_password) < 8:
        raise HTTPException(
            status_code=422,
            detail={"error": "VALIDATION_ERROR", "message": "default_password must be ≥ 8 characters"},
        )
    return await OnboardingService.commit_faculty_csv(
        content, default_password, db,
        filename=file.filename or "faculty.csv",
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
    )


# ---------------------------------------------------------------------------
# USN backfill — assign USNs to existing students (preview-first)
# ---------------------------------------------------------------------------

@router.post("/usn-backfill/preview", response_model=UsnBackfillPreviewResponse)
async def usn_backfill_preview(
    db: AsyncSession = Depends(_admin_db),
) -> UsnBackfillPreviewResponse:
    """Read-only: derive academic identity and project USNs.  No writes."""
    return await UsnBackfillService.preview(db)


@router.post("/usn-backfill/commit", response_model=UsnBackfillCommitResult)
async def usn_backfill_commit(
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(_admin_db),
) -> UsnBackfillCommitResult:
    """Seed counters, allocate USNs, and assign them to students lacking one.

    Idempotent and atomic.  Existing USNs are never modified.
    """
    return await UsnBackfillService.commit(db, actor_user_id=current_user.user_id)


# ---------------------------------------------------------------------------
# Faculty ↔ Program assignments (Phase 1 / Step 3)
# ---------------------------------------------------------------------------

def _faculty_program_err(e: FacultyProgramServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.post("/faculty-programs/assign", response_model=FacultyProgramOut)
async def assign_faculty_program(
    body: FacultyProgramAssignRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(_admin_db),
) -> FacultyProgramOut:
    """Grant a faculty teaching scope on a program (reactivates if revoked)."""
    try:
        return await FacultyProgramService.assign_program(
            db,
            faculty_user_id=body.faculty_user_id,
            program_id=body.program_id,
            assigned_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
        )
    except FacultyProgramServiceError as e:
        raise _faculty_program_err(e)


@router.post("/faculty-programs/revoke", response_model=FacultyProgramOut)
async def revoke_faculty_program(
    body: FacultyProgramRevokeRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(_admin_db),
) -> FacultyProgramOut:
    """Soft-revoke the active assignment for (faculty, program)."""
    try:
        return await FacultyProgramService.revoke_program(
            db,
            faculty_user_id=body.faculty_user_id,
            program_id=body.program_id,
            revoked_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
        )
    except FacultyProgramServiceError as e:
        raise _faculty_program_err(e)


@router.get("/faculty-programs/by-faculty/{faculty_user_id}", response_model=FacultyProgramListResponse)
async def list_programs_for_faculty(
    faculty_user_id: str,
    include_inactive: bool = False,
    db: AsyncSession = Depends(_admin_db),
) -> FacultyProgramListResponse:
    fid = _parse_uuid_form(faculty_user_id, "faculty_user_id")
    return await FacultyProgramService.list_programs(
        db, faculty_user_id=fid, include_inactive=include_inactive
    )


@router.get("/faculty-programs/by-program/{program_id}", response_model=FacultyProgramListResponse)
async def list_faculty_for_program(
    program_id: str,
    include_inactive: bool = False,
    db: AsyncSession = Depends(_admin_db),
) -> FacultyProgramListResponse:
    pid = _parse_uuid_form(program_id, "program_id")
    return await FacultyProgramService.list_faculty_for_program(
        db, program_id=pid, include_inactive=include_inactive
    )


# ---------------------------------------------------------------------------
# Sample template downloads
# ---------------------------------------------------------------------------

def _make_xlsx(headers: list[str], rows: list[list]) -> bytes:
    import openpyxl  # noqa: PLC0415
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_STUDENTS_CSV_SAMPLE = (
    "full_name,email,identifier\n"
    "John Doe,john.doe@university.edu,ABC26MCA001\n"
    "Jane Smith,jane.smith@university.edu,ABC26MCA002\n"
)

_FACULTY_CSV_SAMPLE = (
    "full_name,email,employee_id,program_codes\n"
    "Dr. John Smith,john.smith@university.edu,EMP001,MCA|BCA\n"
    "Dr. Jane Doe,jane.doe@university.edu,EMP002,MCA\n"
)


@router.get("/sample-csv/students")
async def sample_students_csv() -> Response:
    return Response(
        content=_STUDENTS_CSV_SAMPLE,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=students_template.csv"},
    )


@router.get("/sample-csv/faculty")
async def sample_faculty_csv() -> Response:
    return Response(
        content=_FACULTY_CSV_SAMPLE,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=faculty_template.csv"},
    )


@router.get("/sample-xlsx/students")
async def sample_students_xlsx() -> Response:
    content = _make_xlsx(
        headers=["full_name", "email", "identifier"],
        rows=[
            ["John Doe", "john.doe@university.edu", "ABC26MCA001"],
            ["Jane Smith", "jane.smith@university.edu", "ABC26MCA002"],
        ],
    )
    return Response(
        content=content,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=students_template.xlsx"},
    )


@router.get("/sample-xlsx/faculty")
async def sample_faculty_xlsx() -> Response:
    content = _make_xlsx(
        headers=["full_name", "email", "employee_id", "program_codes"],
        rows=[
            ["Dr. John Smith", "john.smith@university.edu", "EMP001", "MCA|BCA"],
            ["Dr. Jane Doe", "jane.doe@university.edu", "EMP002", "MCA"],
        ],
    )
    return Response(
        content=content,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=faculty_template.xlsx"},
    )
