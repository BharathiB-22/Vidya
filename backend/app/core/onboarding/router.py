from typing import AsyncGenerator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.onboarding.repository import OnboardingRepository
from app.core.onboarding.schemas import (
    CSVCommitResult,
    CSVPreviewResponse,
    DepartmentCreate,
    DepartmentResponse,
    GenerateStudentsRequest,
    GenerateStudentsResult,
    ProgramCreate,
    ProgramResponse,
)
from app.core.onboarding.service import OnboardingService
from app.database import AsyncSessionLocal

router = APIRouter(tags=["onboarding"])

_MAX_CSV_BYTES = 5 * 1024 * 1024  # 5 MB


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


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

@router.get("/departments", response_model=list[DepartmentResponse])
async def list_departments(
    db: AsyncSession = Depends(_admin_db),
) -> list[DepartmentResponse]:
    depts = await OnboardingRepository.list_departments(db)
    return [DepartmentResponse.model_validate(d) for d in depts]


@router.post("/departments", response_model=DepartmentResponse, status_code=201)
async def create_department(
    body: DepartmentCreate,
    db: AsyncSession = Depends(_admin_db),
) -> DepartmentResponse:
    existing = await OnboardingRepository.get_department_by_code(body.code, db)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "CONFLICT",
                "message": f"Department code '{body.code.upper()}' already exists",
            },
        )
    dept = await OnboardingRepository.create_department(body.name, body.code, db)
    return DepartmentResponse.model_validate(dept)


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------

@router.get("/programs", response_model=list[ProgramResponse])
async def list_programs(
    db: AsyncSession = Depends(_admin_db),
) -> list[ProgramResponse]:
    progs = await OnboardingRepository.list_programs(db)
    return [ProgramResponse.model_validate(p) for p in progs]


@router.post("/programs", response_model=ProgramResponse, status_code=201)
async def create_program(
    body: ProgramCreate,
    db: AsyncSession = Depends(_admin_db),
) -> ProgramResponse:
    existing = await OnboardingRepository.get_program_by_code(body.code, db)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "CONFLICT",
                "message": f"Program code '{body.code.upper()}' already exists",
            },
        )
    prog = await OnboardingRepository.create_program(
        body.name, body.code, body.dept_id, body.duration_years, db
    )
    return ProgramResponse.model_validate(prog)


# ---------------------------------------------------------------------------
# Bulk student generation
# ---------------------------------------------------------------------------

@router.post("/generate-students", response_model=GenerateStudentsResult)
async def generate_students(
    body: GenerateStudentsRequest,
    db: AsyncSession = Depends(_admin_db),
) -> GenerateStudentsResult:
    return await OnboardingService.generate_students(body, db)


# ---------------------------------------------------------------------------
# CSV import — students
# ---------------------------------------------------------------------------

def _read_csv_upload(file: UploadFile) -> None:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail={"error": "BAD_REQUEST", "message": "Please upload a .csv file"},
        )


@router.post("/import/students/preview", response_model=CSVPreviewResponse)
async def preview_students_csv(
    file: UploadFile = File(..., description="CSV file with columns: full_name, email, identifier (optional), section (optional)"),
    db: AsyncSession = Depends(_admin_db),
) -> CSVPreviewResponse:
    _read_csv_upload(file)
    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "FILE_TOO_LARGE", "message": "CSV must be under 5 MB"},
        )
    return await OnboardingService.preview_students_csv(content, db)


@router.post("/import/students/commit", response_model=CSVCommitResult)
async def commit_students_csv(
    file: UploadFile = File(...),
    default_password: str = Form(default="Student@123"),
    db: AsyncSession = Depends(_admin_db),
) -> CSVCommitResult:
    _read_csv_upload(file)
    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "FILE_TOO_LARGE", "message": "CSV must be under 5 MB"},
        )
    if len(default_password) < 8:
        raise HTTPException(
            status_code=422,
            detail={"error": "VALIDATION_ERROR", "message": "default_password must be ≥ 8 characters"},
        )
    return await OnboardingService.commit_students_csv(content, default_password, db)


# ---------------------------------------------------------------------------
# CSV import — faculty
# ---------------------------------------------------------------------------

@router.post("/import/faculty/preview", response_model=CSVPreviewResponse)
async def preview_faculty_csv(
    file: UploadFile = File(..., description="CSV file with columns: full_name, email, employee_id (optional)"),
    db: AsyncSession = Depends(_admin_db),
) -> CSVPreviewResponse:
    _read_csv_upload(file)
    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "FILE_TOO_LARGE", "message": "CSV must be under 5 MB"},
        )
    return await OnboardingService.preview_faculty_csv(content, db)


@router.post("/import/faculty/commit", response_model=CSVCommitResult)
async def commit_faculty_csv(
    file: UploadFile = File(...),
    default_password: str = Form(default="Faculty@123"),
    db: AsyncSession = Depends(_admin_db),
) -> CSVCommitResult:
    _read_csv_upload(file)
    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "FILE_TOO_LARGE", "message": "CSV must be under 5 MB"},
        )
    if len(default_password) < 8:
        raise HTTPException(
            status_code=422,
            detail={"error": "VALIDATION_ERROR", "message": "default_password must be ≥ 8 characters"},
        )
    return await OnboardingService.commit_faculty_csv(content, default_password, db)


# ---------------------------------------------------------------------------
# Sample CSV downloads
# ---------------------------------------------------------------------------

_STUDENTS_CSV_SAMPLE = (
    "full_name,email,identifier,section\n"
    "John Doe,john.doe@university.edu,ABC26MCA001,A\n"
    "Jane Smith,jane.smith@university.edu,ABC26MCA002,B\n"
    "Alex Johnson,alex.j@university.edu,,A\n"
)

_FACULTY_CSV_SAMPLE = (
    "full_name,email,employee_id,department,designation\n"
    "Dr. John Smith,john.smith@university.edu,EMP001,Computer Science,Professor\n"
    "Dr. Jane Doe,jane.doe@university.edu,EMP002,Mathematics,Associate Professor\n"
    "Prof. Alex Kumar,alex.kumar@university.edu,EMP003,Physics,Assistant Professor\n"
)


@router.get("/sample-csv/students")
async def sample_students_csv() -> Response:
    return Response(
        content=_STUDENTS_CSV_SAMPLE,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=students_sample.csv"},
    )


@router.get("/sample-csv/faculty")
async def sample_faculty_csv() -> Response:
    return Response(
        content=_FACULTY_CSV_SAMPLE,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=faculty_sample.csv"},
    )
