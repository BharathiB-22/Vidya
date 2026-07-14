"""
Academic Structure — service layer.

Owns all validation logic. Repository is pure DB access; this layer enforces:
  - uniqueness checks (check-before-insert; admin-only, low-traffic path)
  - referential integrity guards (cannot deactivate parent with active children)
  - batch year vs program duration consistency
  - semester number range vs program duration
  - idempotent generate_semesters
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.onboarding.usn_governance import ProgramCodeUsageService
from app.modules.m_academics.models import (
    AcadBatch, AcadDepartment, AcadProgram,
    AcadSection, AcadSemester,
)
from app.modules.m_academics.repository import (
    BatchRepo, DepartmentRepo, ProgramRepo,
    SectionRepo, SemesterRepo,
)
from app.modules.m_academics.schemas import (
    BatchCreate, BatchUpdate,
    DepartmentCreate, DepartmentUpdate,
    GenerateSemestersOut,
    ProgramCreate, ProgramUpdate,
    SectionCreate, SectionUpdate,
    SemesterCreate, SemesterOut, SemesterUpdate,
)


class AcadServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------

class DepartmentService:

    @staticmethod
    async def create(body: DepartmentCreate, db: AsyncSession) -> AcadDepartment:
        if await DepartmentRepo.get_by_name(body.name, db):
            raise AcadServiceError("DUPLICATE_NAME", f"Department '{body.name}' already exists.")
        if await DepartmentRepo.get_by_code(body.code, db):
            raise AcadServiceError("DUPLICATE_CODE", f"Department code '{body.code}' already exists.")
        dept = await DepartmentRepo.create(body.name, body.code, body.description, db, school_id=body.school_id)
        await db.commit()
        return dept

    @staticmethod
    async def get(dept_id: UUID, db: AsyncSession) -> AcadDepartment:
        dept = await DepartmentRepo.get_by_id(dept_id, db)
        if dept is None:
            raise AcadServiceError("NOT_FOUND", "Department not found.", 404)
        return dept

    @staticmethod
    async def list_all(db: AsyncSession, include_inactive: bool = False) -> list[AcadDepartment]:
        return await DepartmentRepo.list_all(db, include_inactive=include_inactive)

    @staticmethod
    async def update(dept_id: UUID, body: DepartmentUpdate, db: AsyncSession) -> AcadDepartment:
        dept = await DepartmentRepo.get_by_id(dept_id, db)
        if dept is None:
            raise AcadServiceError("NOT_FOUND", "Department not found.", 404)

        updates: dict = body.model_dump(exclude_none=True)

        if "name" in updates and updates["name"] != dept.name:
            if await DepartmentRepo.get_by_name(updates["name"], db):
                raise AcadServiceError("DUPLICATE_NAME", f"Department '{updates['name']}' already exists.")

        if "code" in updates and updates["code"] != dept.code:
            if await DepartmentRepo.get_by_code(updates["code"], db):
                raise AcadServiceError("DUPLICATE_CODE", f"Department code '{updates['code']}' already exists.")

        if updates.get("is_active") is False:
            if await DepartmentRepo.has_active_programs(dept_id, db):
                raise AcadServiceError(
                    "HAS_ACTIVE_CHILDREN",
                    "Cannot deactivate department with active programs. Deactivate all programs first.",
                )

        dept = await DepartmentRepo.update(dept, updates, db)
        await db.commit()
        return dept


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------

class ProgramService:

    @staticmethod
    async def create(body: ProgramCreate, db: AsyncSession) -> AcadProgram:
        dept = await DepartmentRepo.get_by_id(body.department_id, db)
        if dept is None:
            raise AcadServiceError("NOT_FOUND", "Department not found.", 404)
        if not dept.is_active:
            raise AcadServiceError("INACTIVE_PARENT", "Cannot add program to an inactive department.")

        if await ProgramRepo.get_by_code(body.code, db):
            raise AcadServiceError("DUPLICATE_CODE", f"Program code '{body.code}' already exists.")

        prog = await ProgramRepo.create(
            body.department_id, body.name, body.code,
            body.degree_type.value, body.duration_years, db,
            min_credits_for_degree=body.min_credits_for_degree,
        )
        await db.commit()
        return prog

    @staticmethod
    async def get(prog_id: UUID, db: AsyncSession) -> AcadProgram:
        prog = await ProgramRepo.get_by_id(prog_id, db)
        if prog is None:
            raise AcadServiceError("NOT_FOUND", "Program not found.", 404)
        return prog

    @staticmethod
    async def list_all(
        db: AsyncSession,
        department_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[AcadProgram]:
        return await ProgramRepo.list_all(db, department_id=department_id, include_inactive=include_inactive)

    @staticmethod
    async def update(prog_id: UUID, body: ProgramUpdate, db: AsyncSession) -> AcadProgram:
        prog = await ProgramRepo.get_by_id(prog_id, db)
        if prog is None:
            raise AcadServiceError("NOT_FOUND", "Program not found.", 404)

        updates: dict = body.model_dump(exclude_none=True)

        if "code" in updates and updates["code"] != prog.code:
            # USN immutability: the old code may be cemented into issued USNs.
            if await ProgramCodeUsageService.is_program_code_used(prog.code, db):
                raise AcadServiceError(
                    "USN_CODE_LOCKED",
                    "Program code cannot be changed because issued USNs depend on it.",
                    409,
                )
            if await ProgramRepo.get_by_code(updates["code"], db):
                raise AcadServiceError("DUPLICATE_CODE", f"Program code '{updates['code']}' already exists.")

        if "degree_type" in updates:
            updates["degree_type"] = updates["degree_type"].value

        if updates.get("is_active") is False:
            if await ProgramRepo.has_active_batches(prog_id, db):
                raise AcadServiceError(
                    "HAS_ACTIVE_CHILDREN",
                    "Cannot deactivate program with active batches. Deactivate all batches first.",
                )

        prog = await ProgramRepo.update(prog, updates, db)
        await db.commit()
        return prog


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

class BatchService:

    @staticmethod
    async def create(body: BatchCreate, db: AsyncSession) -> AcadBatch:
        prog = await ProgramRepo.get_by_id(body.program_id, db)
        if prog is None:
            raise AcadServiceError("NOT_FOUND", "Program not found.", 404)
        if not prog.is_active:
            raise AcadServiceError("INACTIVE_PARENT", "Cannot add batch to an inactive program.")

        expected_span = prog.duration_years
        actual_span   = body.end_year - body.start_year
        if actual_span != expected_span:
            raise AcadServiceError(
                "YEAR_SPAN_MISMATCH",
                f"Batch span ({actual_span} yr) must match program duration ({expected_span} yr).",
            )

        if await BatchRepo.get_by_program_and_year(body.program_id, body.start_year, db):
            raise AcadServiceError(
                "DUPLICATE_BATCH",
                f"A batch starting in {body.start_year} already exists for this program.",
            )

        batch = await BatchRepo.create(body.program_id, body.name, body.start_year, body.end_year, db)
        await db.commit()
        return batch

    @staticmethod
    async def get(batch_id: UUID, db: AsyncSession) -> AcadBatch:
        batch = await BatchRepo.get_by_id(batch_id, db)
        if batch is None:
            raise AcadServiceError("NOT_FOUND", "Batch not found.", 404)
        return batch

    @staticmethod
    async def list_all(
        db: AsyncSession,
        program_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[AcadBatch]:
        return await BatchRepo.list_all(db, program_id=program_id, include_inactive=include_inactive)

    @staticmethod
    async def update(batch_id: UUID, body: BatchUpdate, db: AsyncSession) -> AcadBatch:
        batch = await BatchRepo.get_by_id(batch_id, db)
        if batch is None:
            raise AcadServiceError("NOT_FOUND", "Batch not found.", 404)

        updates: dict = body.model_dump(exclude_none=True)

        if updates.get("is_active") is False:
            if await BatchRepo.has_active_semesters(batch_id, db):
                raise AcadServiceError(
                    "HAS_ACTIVE_CHILDREN",
                    "Cannot deactivate batch with active semesters. Deactivate all semesters first.",
                )

        batch = await BatchRepo.update(batch, updates, db)
        await db.commit()
        return batch

    @staticmethod
    async def generate_semesters(batch_id: UUID, db: AsyncSession) -> GenerateSemestersOut:
        batch = await BatchRepo.get_by_id(batch_id, db)
        if batch is None:
            raise AcadServiceError("NOT_FOUND", "Batch not found.", 404)

        prog = await ProgramRepo.get_by_id(batch.program_id, db)
        if prog is None:
            raise AcadServiceError("NOT_FOUND", "Associated program not found.", 404)

        total = prog.duration_years * 2
        created_list: list[AcadSemester] = []
        skipped = 0

        for num in range(1, total + 1):
            existing = await SemesterRepo.get_by_batch_and_number(batch_id, num, db)
            if existing:
                skipped += 1
                continue
            sem = await SemesterRepo.create(batch_id, num, None, db)
            created_list.append(sem)

        await db.commit()

        return GenerateSemestersOut(
            created=len(created_list),
            skipped=skipped,
            semesters=[SemesterOut.model_validate(s) for s in created_list],
        )


# ---------------------------------------------------------------------------
# Semester
# ---------------------------------------------------------------------------

class SemesterService:

    @staticmethod
    async def create(body: SemesterCreate, db: AsyncSession) -> AcadSemester:
        batch = await BatchRepo.get_by_id(body.batch_id, db)
        if batch is None:
            raise AcadServiceError("NOT_FOUND", "Batch not found.", 404)
        if not batch.is_active:
            raise AcadServiceError("INACTIVE_PARENT", "Cannot add semester to an inactive batch.")

        prog = await ProgramRepo.get_by_id(batch.program_id, db)
        max_sem = (prog.duration_years * 2) if prog else 12
        if body.number > max_sem:
            raise AcadServiceError(
                "NUMBER_OUT_OF_RANGE",
                f"Semester number {body.number} exceeds max ({max_sem}) for this program.",
            )

        if await SemesterRepo.get_by_batch_and_number(body.batch_id, body.number, db):
            raise AcadServiceError(
                "DUPLICATE_SEMESTER",
                f"Semester {body.number} already exists in this batch.",
            )

        sem = await SemesterRepo.create(body.batch_id, body.number, body.label, db)
        await db.commit()
        return sem

    @staticmethod
    async def get(sem_id: UUID, db: AsyncSession) -> AcadSemester:
        sem = await SemesterRepo.get_by_id(sem_id, db)
        if sem is None:
            raise AcadServiceError("NOT_FOUND", "Semester not found.", 404)
        return sem

    @staticmethod
    async def list_all(
        db: AsyncSession,
        batch_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[AcadSemester]:
        return await SemesterRepo.list_all(db, batch_id=batch_id, include_inactive=include_inactive)

    @staticmethod
    async def update(sem_id: UUID, body: SemesterUpdate, db: AsyncSession) -> AcadSemester:
        sem = await SemesterRepo.get_by_id(sem_id, db)
        if sem is None:
            raise AcadServiceError("NOT_FOUND", "Semester not found.", 404)

        updates: dict = body.model_dump(exclude_none=True)

        if updates.get("is_active") is False:
            if await SemesterRepo.has_active_sections(sem_id, db):
                raise AcadServiceError(
                    "HAS_ACTIVE_CHILDREN",
                    "Cannot deactivate semester with active sections. Deactivate all sections first.",
                )

        sem = await SemesterRepo.update(sem, updates, db)
        await db.commit()
        return sem


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

class SectionService:

    @staticmethod
    async def create(body: SectionCreate, db: AsyncSession) -> AcadSection:
        sem = await SemesterRepo.get_by_id(body.semester_id, db)
        if sem is None:
            raise AcadServiceError("NOT_FOUND", "Semester not found.", 404)
        if not sem.is_active:
            raise AcadServiceError("INACTIVE_PARENT", "Cannot add section to an inactive semester.")

        if await SectionRepo.get_by_semester_and_name(body.semester_id, body.name, db):
            raise AcadServiceError(
                "DUPLICATE_SECTION",
                f"Section '{body.name}' already exists in this semester.",
            )

        section = await SectionRepo.create(body.semester_id, body.name, body.max_strength, db)
        await db.commit()
        return section

    @staticmethod
    async def get(section_id: UUID, db: AsyncSession) -> AcadSection:
        section = await SectionRepo.get_by_id(section_id, db)
        if section is None:
            raise AcadServiceError("NOT_FOUND", "Section not found.", 404)
        return section

    @staticmethod
    async def list_all(
        db: AsyncSession,
        semester_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[AcadSection]:
        return await SectionRepo.list_all(db, semester_id=semester_id, include_inactive=include_inactive)

    @staticmethod
    async def update(section_id: UUID, body: SectionUpdate, db: AsyncSession) -> AcadSection:
        section = await SectionRepo.get_by_id(section_id, db)
        if section is None:
            raise AcadServiceError("NOT_FOUND", "Section not found.", 404)

        updates: dict = body.model_dump(exclude_none=True)

        if "name" in updates and updates["name"] != section.name:
            if await SectionRepo.get_by_semester_and_name(section.semester_id, updates["name"], db):
                raise AcadServiceError(
                    "DUPLICATE_SECTION",
                    f"Section '{updates['name']}' already exists in this semester.",
                )

        section = await SectionRepo.update(section, updates, db)
        await db.commit()
        return section
