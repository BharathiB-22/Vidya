from __future__ import annotations

import json
import uuid as _uuid
from uuid import UUID

from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m01_program_advisor.models import (
    Course,
    CoursePrerequisite,
    ElectiveBasket,
    Program,
    ProgramOutcome,
    ProgramStatus,
)
from app.modules.m01_program_advisor.schemas import CourseCreate, ProgramOutcomeCreate


# ---------------------------------------------------------------------------
# ProgramRepository
# ---------------------------------------------------------------------------

class ProgramRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        title: str,
        degree_type: str,
        department: str,
        duration_years: int,
        total_credits: int,
        created_by_user_id: UUID,
        *,
        db: AsyncSession,
        acad_program_id: UUID | None = None,
        ai_instructions: str | None = None,
    ) -> Program:
        program = Program(
            title=title,
            degree_type=degree_type,
            department=department,
            duration_years=duration_years,
            total_credits=total_credits,
            created_by_user_id=created_by_user_id,
            acad_program_id=acad_program_id,
            ai_instructions=ai_instructions,
        )
        db.add(program)
        await db.flush()
        await db.refresh(program)
        return program

    @staticmethod
    async def update(
        program_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> Program | None:
        stmt = select(Program).where(Program.id == program_id)
        result = await db.execute(stmt)
        program = result.scalar_one_or_none()
        if program is None:
            return None
        for key, value in updates.items():
            setattr(program, key, value)
        await db.flush()
        await db.refresh(program)
        return program

    @staticmethod
    async def update_status(
        program_id: UUID,
        status: ProgramStatus,
        *,
        db: AsyncSession,
    ) -> Program | None:
        stmt = (
            update(Program)
            .where(Program.id == program_id)
            .values(status=status, updated_at=func.now())
            .returning(Program)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_approved(
        program_id: UUID,
        approved_by_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> Program | None:
        stmt = (
            update(Program)
            .where(Program.id == program_id)
            .values(
                status=ProgramStatus.APPROVED,
                approved_by_user_id=approved_by_user_id,
                approved_at=func.now(),
                updated_at=func.now(),
            )
            .returning(Program)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_published(
        program_id: UUID,
        published_by_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> Program | None:
        stmt = (
            update(Program)
            .where(Program.id == program_id)
            .values(
                status=ProgramStatus.PUBLISHED,
                published_by_user_id=published_by_user_id,
                published_at=func.now(),
                updated_at=func.now(),
            )
            .returning(Program)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> Program | None:
        stmt = select(Program).where(Program.id == program_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_detail(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> Program | None:
        stmt = (
            select(Program)
            .where(Program.id == program_id)
            .options(
                selectinload(Program.outcomes),
                selectinload(Program.courses),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        *,
        status_filter: ProgramStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        acad_program_ids: list[UUID] | None = None,
        db: AsyncSession,
    ) -> list[Program]:
        stmt = select(Program).order_by(Program.created_at.desc()).offset(offset).limit(limit)
        if status_filter is not None:
            stmt = stmt.where(Program.status == status_filter)
        if acad_program_ids is not None:
            stmt = stmt.where(Program.acad_program_id.in_(acad_program_ids))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count(
        *,
        status_filter: ProgramStatus | None = None,
        acad_program_ids: list[UUID] | None = None,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(Program.id))
        if status_filter is not None:
            stmt = stmt.where(Program.status == status_filter)
        if acad_program_ids is not None:
            stmt = stmt.where(Program.acad_program_id.in_(acad_program_ids))
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def list_versions(
        parent_version_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[Program]:
        stmt = (
            select(Program)
            .where(Program.parent_version_id == parent_version_id)
            .order_by(Program.version.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# ProgramOutcomeRepository
# ---------------------------------------------------------------------------

class ProgramOutcomeRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        program_id: UUID,
        code: str,
        description: str,
        bloom_level: str | None,
        display_order: int,
        *,
        db: AsyncSession,
    ) -> ProgramOutcome:
        outcome = ProgramOutcome(
            program_id=program_id,
            code=code,
            description=description,
            bloom_level=bloom_level,
            display_order=display_order,
        )
        db.add(outcome)
        await db.flush()
        await db.refresh(outcome)
        return outcome

    @staticmethod
    async def bulk_create(
        program_id: UUID,
        items: list[ProgramOutcomeCreate],
        *,
        db: AsyncSession,
    ) -> list[ProgramOutcome]:
        outcomes = [
            ProgramOutcome(
                program_id=program_id,
                code=item.code,
                description=item.description,
                bloom_level=item.bloom_level,
                display_order=item.display_order,
            )
            for item in items
        ]
        db.add_all(outcomes)
        await db.flush()
        for outcome in outcomes:
            await db.refresh(outcome)
        return outcomes

    @staticmethod
    async def update(
        outcome_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> ProgramOutcome | None:
        stmt = select(ProgramOutcome).where(ProgramOutcome.id == outcome_id)
        result = await db.execute(stmt)
        outcome = result.scalar_one_or_none()
        if outcome is None:
            return None
        for key, value in updates.items():
            setattr(outcome, key, value)
        await db.flush()
        await db.refresh(outcome)
        return outcome

    @staticmethod
    async def delete(
        outcome_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(ProgramOutcome).where(ProgramOutcome.id == outcome_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        outcome_id: UUID,
        *,
        db: AsyncSession,
    ) -> ProgramOutcome | None:
        stmt = select(ProgramOutcome).where(ProgramOutcome.id == outcome_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(
        program_id: UUID,
        code: str,
        *,
        db: AsyncSession,
    ) -> ProgramOutcome | None:
        stmt = select(ProgramOutcome).where(
            and_(ProgramOutcome.program_id == program_id, ProgramOutcome.code == code)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_program(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[ProgramOutcome]:
        stmt = (
            select(ProgramOutcome)
            .where(ProgramOutcome.program_id == program_id)
            .order_by(ProgramOutcome.display_order.asc(), ProgramOutcome.code.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# CourseRepository
# ---------------------------------------------------------------------------

class CourseRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        program_id: UUID,
        code: str,
        title: str,
        credits: int,
        semester: int,
        is_elective: bool = False,
        course_type: str | None = None,
        elective_basket_id: UUID | None = None,
        hours_lecture: int | None = None,
        hours_tutorial: int | None = None,
        hours_practical: int | None = None,
        description: str | None = None,
        *,
        db: AsyncSession,
    ) -> Course:
        course = Course(
            program_id=program_id,
            code=code,
            title=title,
            credits=credits,
            semester=semester,
            course_type=course_type,
            is_elective=is_elective,
            elective_basket_id=elective_basket_id,
            hours_lecture=hours_lecture,
            hours_tutorial=hours_tutorial,
            hours_practical=hours_practical,
            description=description,
        )
        db.add(course)
        await db.flush()
        await db.refresh(course)
        return course

    @staticmethod
    async def bulk_create(
        program_id: UUID,
        items: list[CourseCreate],
        *,
        db: AsyncSession,
    ) -> list[Course]:
        courses = [
            Course(
                program_id=program_id,
                code=item.code,
                title=item.title,
                credits=item.credits,
                semester=item.semester,
                course_type=item.course_type.value if item.course_type else None,
                is_elective=item.is_elective,
                elective_basket_id=item.elective_basket_id,
                hours_lecture=item.hours_lecture,
                hours_tutorial=item.hours_tutorial,
                hours_practical=item.hours_practical,
                description=item.description,
            )
            for item in items
        ]
        db.add_all(courses)
        await db.flush()
        for course in courses:
            await db.refresh(course)
        return courses

    @staticmethod
    async def update(
        course_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> Course | None:
        stmt = select(Course).where(Course.id == course_id)
        result = await db.execute(stmt)
        course = result.scalar_one_or_none()
        if course is None:
            return None
        for key, value in updates.items():
            setattr(course, key, value)
        await db.flush()
        await db.refresh(course)
        return course

    @staticmethod
    async def delete(
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(Course).where(Course.id == course_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_ai_generated(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = delete(Course).where(
            and_(Course.program_id == program_id, Course.is_ai_generated.is_(True))
        )
        result = await db.execute(stmt)
        return result.rowcount

    @staticmethod
    async def mark_all_ai_generated(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = (
            update(Course)
            .where(Course.program_id == program_id)
            .values(is_ai_generated=True)
        )
        result = await db.execute(stmt)
        return result.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> Course | None:
        stmt = select(Course).where(Course.id == course_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(
        program_id: UUID,
        code: str,
        *,
        db: AsyncSession,
    ) -> Course | None:
        stmt = select(Course).where(
            and_(Course.program_id == program_id, Course.code == code)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_program(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[Course]:
        stmt = (
            select(Course)
            .where(Course.program_id == program_id)
            .order_by(Course.semester.asc(), Course.code.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_semester(
        program_id: UUID,
        semester: int,
        *,
        db: AsyncSession,
    ) -> list[Course]:
        stmt = (
            select(Course)
            .where(and_(Course.program_id == program_id, Course.semester == semester))
            .order_by(Course.code.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_program(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(Course.id)).where(Course.program_id == program_id)
        result = await db.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# ElectiveBasketRepository
# ---------------------------------------------------------------------------

class ElectiveBasketRepository:

    @staticmethod
    async def create(
        program_id: UUID,
        semester: int,
        name: str,
        description: str | None,
        created_by_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> ElectiveBasket:
        basket = ElectiveBasket(
            program_id=program_id, semester=semester, name=name,
            description=description, created_by_user_id=created_by_user_id,
        )
        db.add(basket)
        await db.flush()
        await db.refresh(basket)
        return basket

    @staticmethod
    async def update(
        basket_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> ElectiveBasket | None:
        stmt = select(ElectiveBasket).where(ElectiveBasket.id == basket_id)
        result = await db.execute(stmt)
        basket = result.scalar_one_or_none()
        if basket is None:
            return None
        for key, value in updates.items():
            setattr(basket, key, value)
        await db.flush()
        await db.refresh(basket)
        return basket

    @staticmethod
    async def delete(basket_id: UUID, *, db: AsyncSession) -> bool:
        stmt = delete(ElectiveBasket).where(ElectiveBasket.id == basket_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def get_by_id(basket_id: UUID, *, db: AsyncSession) -> ElectiveBasket | None:
        stmt = (
            select(ElectiveBasket)
            .where(ElectiveBasket.id == basket_id)
            .options(selectinload(ElectiveBasket.courses))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_program(program_id: UUID, *, db: AsyncSession) -> list[ElectiveBasket]:
        stmt = (
            select(ElectiveBasket)
            .where(ElectiveBasket.program_id == program_id)
            .options(selectinload(ElectiveBasket.courses))
            .order_by(ElectiveBasket.semester.asc(), ElectiveBasket.name.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# CoursePrerequisiteRepository
# ---------------------------------------------------------------------------

class CoursePrerequisiteRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        course_id: UUID,
        prerequisite_course_id: UUID,
        *,
        db: AsyncSession,
    ) -> CoursePrerequisite:
        prereq = CoursePrerequisite(
            course_id=course_id,
            prerequisite_course_id=prerequisite_course_id,
        )
        db.add(prereq)
        await db.flush()
        await db.refresh(prereq)
        return prereq

    @staticmethod
    async def bulk_create(
        course_id: UUID,
        prerequisite_course_ids: list[UUID],
        *,
        db: AsyncSession,
    ) -> list[CoursePrerequisite]:
        prereqs = [
            CoursePrerequisite(
                course_id=course_id,
                prerequisite_course_id=pid,
            )
            for pid in prerequisite_course_ids
        ]
        db.add_all(prereqs)
        await db.flush()
        for prereq in prereqs:
            await db.refresh(prereq)
        return prereqs

    @staticmethod
    async def delete(
        prerequisite_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(CoursePrerequisite).where(CoursePrerequisite.id == prerequisite_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_by_course(
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = delete(CoursePrerequisite).where(CoursePrerequisite.course_id == course_id)
        result = await db.execute(stmt)
        return result.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def list_by_course(
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[CoursePrerequisite]:
        stmt = (
            select(CoursePrerequisite)
            .where(CoursePrerequisite.course_id == course_id)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def exists(
        course_id: UUID,
        prerequisite_course_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = select(func.count(CoursePrerequisite.id)).where(
            and_(
                CoursePrerequisite.course_id == course_id,
                CoursePrerequisite.prerequisite_course_id == prerequisite_course_id,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one() > 0


# ---------------------------------------------------------------------------
# TaskJobPublicRepository
# ---------------------------------------------------------------------------

class TaskJobPublicRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        tenant_id: UUID,
        task_type: str,
        queue_name: str,
        payload: dict,
        *,
        db: AsyncSession,
    ) -> UUID:
        job_id = _uuid.uuid4()
        stmt = text(
            "INSERT INTO public.task_jobs "
            "(id, tenant_id, task_type, queue_name, status, payload) "
            "VALUES (CAST(:id AS uuid), CAST(:tenant_id AS uuid), :task_type, :queue_name, 'PENDING', CAST(:payload AS jsonb))"
        )
        await db.execute(stmt, {
            "id":          str(job_id),
            "tenant_id":   str(tenant_id),
            "task_type":   task_type,
            "queue_name":  queue_name,
            "payload":     json.dumps(payload),
        })
        await db.flush()
        return job_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        job_id: UUID,
        tenant_id: UUID,
        *,
        db: AsyncSession,
    ) -> dict | None:
        stmt = text(
            "SELECT id, tenant_id, task_type, queue_name, status, payload, result, "
            "error, created_at, started_at, completed_at "
            "FROM public.task_jobs "
            "WHERE id = CAST(:job_id AS uuid) AND tenant_id = CAST(:tenant_id AS uuid)"
        )
        result = await db.execute(stmt, {
            "job_id":    str(job_id),
            "tenant_id": str(tenant_id),
        })
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None
