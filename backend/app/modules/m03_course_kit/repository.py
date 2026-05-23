from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m03_course_kit.models import (
    AssignmentType,
    BloomLevel,
    ComplexityLevel,
    CourseKit,
    CourseKitStatus,
    KitAssignment,
    KitQuizlet,
    KitSlide,
    QuizletType,
)

# Re-export so callers only need one import path for job tracking.
from app.modules.m02_syllabus.repository import TaskJobPublicRepository  # noqa: F401


# ---------------------------------------------------------------------------
# CourseKitRepository
# ---------------------------------------------------------------------------

class CourseKitRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        syllabus_id: UUID,
        unit_number: int,
        created_by_user_id: UUID,
        complexity_level: ComplexityLevel = ComplexityLevel.UG,
        tone: str | None = None,
        custom_instructions: str | None = None,
        *,
        db: AsyncSession,
    ) -> CourseKit:
        kit = CourseKit(
            syllabus_id=syllabus_id,
            unit_number=unit_number,
            created_by_user_id=created_by_user_id,
            complexity_level=complexity_level,
            tone=tone,
            custom_instructions=custom_instructions,
        )
        db.add(kit)
        await db.flush()
        await db.refresh(kit)
        return kit

    @staticmethod
    async def update(
        kit_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> CourseKit | None:
        stmt = select(CourseKit).where(CourseKit.id == kit_id)
        result = await db.execute(stmt)
        kit = result.scalar_one_or_none()
        if kit is None:
            return None
        for key, value in updates.items():
            setattr(kit, key, value)
        await db.flush()
        await db.refresh(kit)
        return kit

    @staticmethod
    async def update_status(
        kit_id: UUID,
        status: CourseKitStatus,
        *,
        db: AsyncSession,
    ) -> CourseKit | None:
        stmt = (
            update(CourseKit)
            .where(CourseKit.id == kit_id)
            .values(status=status, updated_at=func.now())
            .returning(CourseKit)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_published(
        kit_id: UUID,
        published_by_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> CourseKit | None:
        stmt = (
            update(CourseKit)
            .where(CourseKit.id == kit_id)
            .values(
                status=CourseKitStatus.PUBLISHED,
                published_by_user_id=published_by_user_id,
                published_at=func.now(),
                updated_at=func.now(),
            )
            .returning(CourseKit)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_ai_generating(
        kit_id: UUID,
        ai_model: str,
        prompt_hash: str,
        *,
        db: AsyncSession,
    ) -> CourseKit | None:
        stmt = (
            update(CourseKit)
            .where(CourseKit.id == kit_id)
            .values(
                status=CourseKitStatus.AI_GENERATING,
                ai_model=ai_model,
                prompt_hash=prompt_hash,
                updated_at=func.now(),
            )
            .returning(CourseKit)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def reset_to_draft(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> CourseKit | None:
        """Best-effort reset after a failed AI generation task."""
        stmt = (
            update(CourseKit)
            .where(CourseKit.id == kit_id)
            .values(status=CourseKitStatus.DRAFT, updated_at=func.now())
            .returning(CourseKit)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(CourseKit).where(CourseKit.id == kit_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> CourseKit | None:
        stmt = select(CourseKit).where(CourseKit.id == kit_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_detail(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> CourseKit | None:
        """Eager-load all child collections for the detail view and deep-fork."""
        stmt = (
            select(CourseKit)
            .where(CourseKit.id == kit_id)
            .options(
                selectinload(CourseKit.slides),
                selectinload(CourseKit.quizlets),
                selectinload(CourseKit.assignments),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_syllabus(
        syllabus_id: UUID,
        *,
        status_filter: CourseKitStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[CourseKit]:
        stmt = (
            select(CourseKit)
            .where(CourseKit.syllabus_id == syllabus_id)
            .order_by(CourseKit.unit_number.asc(), CourseKit.version.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter is not None:
            stmt = stmt.where(CourseKit.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_syllabus(
        syllabus_id: UUID,
        *,
        status_filter: CourseKitStatus | None = None,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(CourseKit.id)).where(
            CourseKit.syllabus_id == syllabus_id
        )
        if status_filter is not None:
            stmt = stmt.where(CourseKit.status == status_filter)
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def list_all(
        *,
        status_filter: CourseKitStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[CourseKit]:
        stmt = (
            select(CourseKit)
            .order_by(CourseKit.unit_number.asc(), CourseKit.version.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter is not None:
            stmt = stmt.where(CourseKit.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_all(
        *,
        status_filter: CourseKitStatus | None = None,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(CourseKit.id))
        if status_filter is not None:
            stmt = stmt.where(CourseKit.status == status_filter)
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def list_versions(
        syllabus_id: UUID,
        unit_number: int,
        *,
        db: AsyncSession,
    ) -> list[CourseKit]:
        """All kits for one unit, oldest → newest. Used for version history."""
        stmt = (
            select(CourseKit)
            .where(
                and_(
                    CourseKit.syllabus_id == syllabus_id,
                    CourseKit.unit_number == unit_number,
                )
            )
            .order_by(CourseKit.version.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_published_for_unit(
        syllabus_id: UUID,
        unit_number: int,
        *,
        db: AsyncSession,
    ) -> CourseKit | None:
        """Return the single PUBLISHED kit for a unit (at most one at any time)."""
        stmt = (
            select(CourseKit)
            .where(
                and_(
                    CourseKit.syllabus_id == syllabus_id,
                    CourseKit.unit_number == unit_number,
                    CourseKit.status == CourseKitStatus.PUBLISHED,
                )
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def has_published_for_unit(
        syllabus_id: UUID,
        unit_number: int,
        *,
        db: AsyncSession,
    ) -> bool:
        """Used by service to enforce one-PUBLISHED-per-unit invariant."""
        kit = await CourseKitRepository.get_published_for_unit(
            syllabus_id, unit_number, db=db
        )
        return kit is not None

    @staticmethod
    async def get_next_version(
        syllabus_id: UUID,
        unit_number: int,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.coalesce(func.max(CourseKit.version), 0)).where(
            and_(
                CourseKit.syllabus_id == syllabus_id,
                CourseKit.unit_number == unit_number,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one() + 1


# ---------------------------------------------------------------------------
# SlideRepository
# ---------------------------------------------------------------------------

class SlideRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        kit_id: UUID,
        slide_number: int,
        title: str,
        content: dict | None = None,
        speaker_notes: str | None = None,
        bloom_level: BloomLevel | None = None,
        co_reference: str | None = None,
        *,
        db: AsyncSession,
    ) -> KitSlide:
        slide = KitSlide(
            kit_id=kit_id,
            slide_number=slide_number,
            title=title,
            content=content or {},
            speaker_notes=speaker_notes,
            bloom_level=bloom_level,
            co_reference=co_reference,
        )
        db.add(slide)
        await db.flush()
        await db.refresh(slide)
        return slide

    @staticmethod
    async def bulk_create(
        kit_id: UUID,
        items: list[dict],
        *,
        db: AsyncSession,
    ) -> list[KitSlide]:
        slides = [
            KitSlide(
                kit_id=kit_id,
                slide_number=item["slide_number"],
                title=item["title"],
                content=item.get("content", {}),
                speaker_notes=item.get("speaker_notes"),
                bloom_level=item.get("bloom_level"),
                co_reference=item.get("co_reference"),
            )
            for item in items
        ]
        db.add_all(slides)
        await db.flush()
        for s in slides:
            await db.refresh(s)
        return slides

    @staticmethod
    async def update(
        slide_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> KitSlide | None:
        stmt = select(KitSlide).where(KitSlide.id == slide_id)
        result = await db.execute(stmt)
        slide = result.scalar_one_or_none()
        if slide is None:
            return None
        for key, value in updates.items():
            setattr(slide, key, value)
        await db.flush()
        await db.refresh(slide)
        return slide

    @staticmethod
    async def delete(
        slide_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(KitSlide).where(KitSlide.id == slide_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_all(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = delete(KitSlide).where(KitSlide.kit_id == kit_id)
        result = await db.execute(stmt)
        return result.rowcount

    @staticmethod
    async def reorder(
        order_map: dict[UUID, int],
        *,
        db: AsyncSession,
    ) -> int:
        """Bulk-update slide_number for each slide_id in the map."""
        updated = 0
        for slide_id, new_number in order_map.items():
            stmt = (
                update(KitSlide)
                .where(KitSlide.id == slide_id)
                .values(slide_number=new_number, updated_at=func.now())
            )
            result = await db.execute(stmt)
            updated += result.rowcount
        await db.flush()
        return updated

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        slide_id: UUID,
        *,
        db: AsyncSession,
    ) -> KitSlide | None:
        stmt = select(KitSlide).where(KitSlide.id == slide_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_number(
        kit_id: UUID,
        slide_number: int,
        *,
        db: AsyncSession,
    ) -> KitSlide | None:
        stmt = select(KitSlide).where(
            and_(KitSlide.kit_id == kit_id, KitSlide.slide_number == slide_number)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_kit(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[KitSlide]:
        stmt = (
            select(KitSlide)
            .where(KitSlide.kit_id == kit_id)
            .order_by(KitSlide.slide_number.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_kit(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(KitSlide.id)).where(KitSlide.kit_id == kit_id)
        result = await db.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# QuizletRepository
# ---------------------------------------------------------------------------

class QuizletRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        kit_id: UUID,
        question_number: int,
        question_text: str,
        question_type: QuizletType = QuizletType.MCQ,
        options: list | None = None,
        answer_key: dict | None = None,
        answer_explanation: str | None = None,
        bloom_level: BloomLevel | None = None,
        co_reference: str | None = None,
        *,
        db: AsyncSession,
    ) -> KitQuizlet:
        quizlet = KitQuizlet(
            kit_id=kit_id,
            question_number=question_number,
            question_text=question_text,
            question_type=question_type,
            options=options or [],
            answer_key=answer_key or {},
            answer_explanation=answer_explanation,
            bloom_level=bloom_level,
            co_reference=co_reference,
        )
        db.add(quizlet)
        await db.flush()
        await db.refresh(quizlet)
        return quizlet

    @staticmethod
    async def bulk_create(
        kit_id: UUID,
        items: list[dict],
        *,
        db: AsyncSession,
    ) -> list[KitQuizlet]:
        quizlets = [
            KitQuizlet(
                kit_id=kit_id,
                question_number=item["question_number"],
                question_text=item["question_text"],
                question_type=item.get("question_type", QuizletType.MCQ),
                options=item.get("options", []),
                answer_key=item.get("answer_key", {}),
                answer_explanation=item.get("answer_explanation"),
                bloom_level=item.get("bloom_level"),
                co_reference=item.get("co_reference"),
            )
            for item in items
        ]
        db.add_all(quizlets)
        await db.flush()
        for q in quizlets:
            await db.refresh(q)
        return quizlets

    @staticmethod
    async def update(
        quizlet_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> KitQuizlet | None:
        stmt = select(KitQuizlet).where(KitQuizlet.id == quizlet_id)
        result = await db.execute(stmt)
        quizlet = result.scalar_one_or_none()
        if quizlet is None:
            return None
        for key, value in updates.items():
            setattr(quizlet, key, value)
        await db.flush()
        await db.refresh(quizlet)
        return quizlet

    @staticmethod
    async def delete(
        quizlet_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(KitQuizlet).where(KitQuizlet.id == quizlet_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_all(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = delete(KitQuizlet).where(KitQuizlet.kit_id == kit_id)
        result = await db.execute(stmt)
        return result.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        quizlet_id: UUID,
        *,
        db: AsyncSession,
    ) -> KitQuizlet | None:
        stmt = select(KitQuizlet).where(KitQuizlet.id == quizlet_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_kit(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[KitQuizlet]:
        stmt = (
            select(KitQuizlet)
            .where(KitQuizlet.kit_id == kit_id)
            .order_by(KitQuizlet.question_number.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_kit(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(KitQuizlet.id)).where(KitQuizlet.kit_id == kit_id)
        result = await db.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# AssignmentRepository
# ---------------------------------------------------------------------------

class AssignmentRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        kit_id: UUID,
        assignment_number: int,
        title: str,
        assignment_type: AssignmentType,
        question_text: str,
        complexity_level: ComplexityLevel = ComplexityLevel.UG,
        current_events_toggle: bool = False,
        model_answer: str | None = None,
        rubric: list | None = None,
        bloom_level: BloomLevel | None = None,
        co_reference: str | None = None,
        *,
        db: AsyncSession,
    ) -> KitAssignment:
        assignment = KitAssignment(
            kit_id=kit_id,
            assignment_number=assignment_number,
            title=title,
            assignment_type=assignment_type,
            question_text=question_text,
            complexity_level=complexity_level,
            current_events_toggle=current_events_toggle,
            model_answer=model_answer,
            rubric=rubric or [],
            bloom_level=bloom_level,
            co_reference=co_reference,
        )
        db.add(assignment)
        await db.flush()
        await db.refresh(assignment)
        return assignment

    @staticmethod
    async def bulk_create(
        kit_id: UUID,
        items: list[dict],
        *,
        db: AsyncSession,
    ) -> list[KitAssignment]:
        assignments = [
            KitAssignment(
                kit_id=kit_id,
                assignment_number=item["assignment_number"],
                title=item["title"],
                assignment_type=item["assignment_type"],
                question_text=item["question_text"],
                complexity_level=item.get("complexity_level", ComplexityLevel.UG),
                current_events_toggle=item.get("current_events_toggle", False),
                model_answer=item.get("model_answer"),
                rubric=item.get("rubric", []),
                bloom_level=item.get("bloom_level"),
                co_reference=item.get("co_reference"),
            )
            for item in items
        ]
        db.add_all(assignments)
        await db.flush()
        for a in assignments:
            await db.refresh(a)
        return assignments

    @staticmethod
    async def update(
        assignment_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> KitAssignment | None:
        stmt = select(KitAssignment).where(KitAssignment.id == assignment_id)
        result = await db.execute(stmt)
        assignment = result.scalar_one_or_none()
        if assignment is None:
            return None
        for key, value in updates.items():
            setattr(assignment, key, value)
        await db.flush()
        await db.refresh(assignment)
        return assignment

    @staticmethod
    async def delete(
        assignment_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(KitAssignment).where(KitAssignment.id == assignment_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_all(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = delete(KitAssignment).where(KitAssignment.kit_id == kit_id)
        result = await db.execute(stmt)
        return result.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        assignment_id: UUID,
        *,
        db: AsyncSession,
    ) -> KitAssignment | None:
        stmt = select(KitAssignment).where(KitAssignment.id == assignment_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_kit(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[KitAssignment]:
        stmt = (
            select(KitAssignment)
            .where(KitAssignment.kit_id == kit_id)
            .order_by(KitAssignment.assignment_number.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_kit_and_type(
        kit_id: UUID,
        assignment_type: AssignmentType,
        *,
        db: AsyncSession,
    ) -> list[KitAssignment]:
        stmt = (
            select(KitAssignment)
            .where(
                and_(
                    KitAssignment.kit_id == kit_id,
                    KitAssignment.assignment_type == assignment_type,
                )
            )
            .order_by(KitAssignment.assignment_number.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_kit(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(KitAssignment.id)).where(
            KitAssignment.kit_id == kit_id
        )
        result = await db.execute(stmt)
        return result.scalar_one()
