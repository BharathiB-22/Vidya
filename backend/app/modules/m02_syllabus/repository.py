from __future__ import annotations

import json
import uuid as _uuid
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m02_syllabus.models import (
    BloomLevel,
    COPOMapping,
    CourseOutcome,
    MappingStrength,
    RefSource,
    RefType,
    Syllabus,
    SyllabusReference,
    SyllabusStatus,
    SyllabusUnit,
)


# ---------------------------------------------------------------------------
# SyllabusRepository
# ---------------------------------------------------------------------------

class SyllabusRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        course_id: UUID,
        created_by_user_id: UUID,
        custom_instructions: str | None = None,
        doc_type: str = "THEORY",
        *,
        db: AsyncSession,
    ) -> Syllabus:
        syllabus = Syllabus(
            course_id=course_id,
            created_by_user_id=created_by_user_id,
            custom_instructions=custom_instructions,
            # Stamped from the course's type at creation. Everything downstream —
            # which AI prompt runs, which sections can be regenerated, whether the
            # Dean may edit it after approval — keys off this.
            doc_type=doc_type,
            document={},
        )
        db.add(syllabus)
        await db.flush()
        await db.refresh(syllabus)
        return syllabus

    @staticmethod
    async def update(
        syllabus_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> Syllabus | None:
        stmt = select(Syllabus).where(Syllabus.id == syllabus_id)
        result = await db.execute(stmt)
        syllabus = result.scalar_one_or_none()
        if syllabus is None:
            return None
        for key, value in updates.items():
            setattr(syllabus, key, value)
        await db.flush()
        await db.refresh(syllabus)
        return syllabus

    @staticmethod
    async def update_status(
        syllabus_id: UUID,
        status: SyllabusStatus,
        *,
        db: AsyncSession,
    ) -> Syllabus | None:
        stmt = (
            update(Syllabus)
            .where(Syllabus.id == syllabus_id)
            .values(status=status, updated_at=func.now())
            .returning(Syllabus)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_board_approved(
        syllabus_id: UUID,
        approved_by_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> Syllabus | None:
        """DRAFT -> APPROVED. The Board signs off one official syllabus.

        Locking is NOT done here — a syllabus is locked only when the whole
        curriculum is approved (governance.service.approve_and_lock), because
        the syllabus and the structure must freeze as one thing.
        """
        stmt = (
            update(Syllabus)
            .where(Syllabus.id == syllabus_id)
            .values(
                status=SyllabusStatus.APPROVED,
                approved_by_user_id=approved_by_user_id,
                approved_at=func.now(),
                updated_at=func.now(),
            )
            .returning(Syllabus)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def revert_to_draft(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> Syllabus | None:
        """APPROVED -> DRAFT, clearing the approval.

        Called when the Board edits the underlying course after approving its
        syllabus: the syllabus was written against a structure that has since
        moved, so the sign-off no longer means anything and the Board must look
        at it again. This is what stops a stale syllabus reaching a locked
        curriculum. LOCKED syllabi are never touched — locked is forever.
        """
        stmt = (
            update(Syllabus)
            .where(
                Syllabus.id == syllabus_id,
                Syllabus.status == SyllabusStatus.APPROVED,
            )
            .values(
                status=SyllabusStatus.DRAFT,
                approved_by_user_id=None,
                approved_at=None,
                updated_at=func.now(),
            )
            .returning(Syllabus)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(Syllabus).where(Syllabus.id == syllabus_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> Syllabus | None:
        stmt = select(Syllabus).where(Syllabus.id == syllabus_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_detail(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> Syllabus | None:
        """Load syllabus with all child collections eagerly."""
        stmt = (
            select(Syllabus)
            .where(Syllabus.id == syllabus_id)
            .options(
                selectinload(Syllabus.outcomes).selectinload(CourseOutcome.mappings),
                selectinload(Syllabus.units),
                selectinload(Syllabus.references),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_course(
        course_id: UUID,
        *,
        status_filter: SyllabusStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[Syllabus]:
        stmt = (
            select(Syllabus)
            .where(Syllabus.course_id == course_id)
            .order_by(Syllabus.version.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter is not None:
            stmt = stmt.where(Syllabus.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_course(
        course_id: UUID,
        *,
        status_filter: SyllabusStatus | None = None,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(Syllabus.id)).where(Syllabus.course_id == course_id)
        if status_filter is not None:
            stmt = stmt.where(Syllabus.status == status_filter)
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def list_all(
        *,
        status_filter: SyllabusStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[Syllabus]:
        stmt = (
            select(Syllabus)
            .order_by(Syllabus.course_id.asc(), Syllabus.version.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter is not None:
            stmt = stmt.where(Syllabus.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_all(
        *,
        status_filter: SyllabusStatus | None = None,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(Syllabus.id))
        if status_filter is not None:
            stmt = stmt.where(Syllabus.status == status_filter)
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def list_by_courses(
        course_ids: list[UUID],
        *,
        status_filter: SyllabusStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[Syllabus]:
        if not course_ids:
            return []
        conditions: list = [Syllabus.course_id.in_(course_ids)]
        if status_filter is not None:
            conditions.append(Syllabus.status == status_filter)
        stmt = (
            select(Syllabus)
            .where(and_(*conditions))
            .order_by(Syllabus.course_id.asc(), Syllabus.version.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_courses(
        course_ids: list[UUID],
        *,
        status_filter: SyllabusStatus | None = None,
        db: AsyncSession,
    ) -> int:
        if not course_ids:
            return 0
        conditions: list = [Syllabus.course_id.in_(course_ids)]
        if status_filter is not None:
            conditions.append(Syllabus.status == status_filter)
        stmt = select(func.count(Syllabus.id)).where(and_(*conditions))
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def list_versions(
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[Syllabus]:
        """Return all versions for a course ordered oldest → newest."""
        stmt = (
            select(Syllabus)
            .where(Syllabus.course_id == course_id)
            .order_by(Syllabus.version.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_latest_approved(
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> Syllabus | None:
        """Return the highest-versioned APPROVED or LOCKED syllabus.

        This is what every downstream module (course kits, learning materials,
        exam papers) teaches from — the official, Board-signed-off syllabus and
        nothing else.
        """
        stmt = (
            select(Syllabus)
            .where(
                and_(
                    Syllabus.course_id == course_id,
                    or_(
                        Syllabus.status == SyllabusStatus.APPROVED,
                        Syllabus.status == SyllabusStatus.LOCKED,
                    ),
                )
            )
            .order_by(Syllabus.version.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_next_version(
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        """Return the next available version number for a course's syllabi."""
        stmt = select(func.coalesce(func.max(Syllabus.version), 0)).where(
            Syllabus.course_id == course_id
        )
        result = await db.execute(stmt)
        return result.scalar_one() + 1


# ---------------------------------------------------------------------------
# CourseOutcomeRepository
# ---------------------------------------------------------------------------

class CourseOutcomeRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        syllabus_id: UUID,
        code: str,
        description: str,
        bloom_level: BloomLevel,
        display_order: int = 0,
        *,
        db: AsyncSession,
    ) -> CourseOutcome:
        outcome = CourseOutcome(
            syllabus_id=syllabus_id,
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
        syllabus_id: UUID,
        items: list[dict],
        *,
        db: AsyncSession,
    ) -> list[CourseOutcome]:
        outcomes = [
            CourseOutcome(
                syllabus_id=syllabus_id,
                code=item["code"],
                description=item["description"],
                bloom_level=item["bloom_level"],
                display_order=item.get("display_order", idx),
            )
            for idx, item in enumerate(items)
        ]
        db.add_all(outcomes)
        await db.flush()
        for o in outcomes:
            await db.refresh(o)
        return outcomes

    @staticmethod
    async def update(
        co_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> CourseOutcome | None:
        stmt = select(CourseOutcome).where(CourseOutcome.id == co_id)
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
        co_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(CourseOutcome).where(CourseOutcome.id == co_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_all(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = delete(CourseOutcome).where(CourseOutcome.syllabus_id == syllabus_id)
        result = await db.execute(stmt)
        return result.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        co_id: UUID,
        *,
        db: AsyncSession,
    ) -> CourseOutcome | None:
        stmt = select(CourseOutcome).where(CourseOutcome.id == co_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(
        syllabus_id: UUID,
        code: str,
        *,
        db: AsyncSession,
    ) -> CourseOutcome | None:
        stmt = select(CourseOutcome).where(
            and_(CourseOutcome.syllabus_id == syllabus_id, CourseOutcome.code == code)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_syllabus(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[CourseOutcome]:
        stmt = (
            select(CourseOutcome)
            .where(CourseOutcome.syllabus_id == syllabus_id)
            .order_by(CourseOutcome.display_order.asc(), CourseOutcome.code.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_syllabus(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(CourseOutcome.id)).where(
            CourseOutcome.syllabus_id == syllabus_id
        )
        result = await db.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# COPOMappingRepository
# ---------------------------------------------------------------------------

class COPOMappingRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        co_id: UUID,
        po_id: UUID,
        mapping_strength: MappingStrength = MappingStrength.MEDIUM,
        justification: str | None = None,
        *,
        db: AsyncSession,
    ) -> COPOMapping:
        mapping = COPOMapping(
            co_id=co_id,
            po_id=po_id,
            mapping_strength=mapping_strength,
            justification=justification,
        )
        db.add(mapping)
        await db.flush()
        await db.refresh(mapping)
        return mapping

    @staticmethod
    async def bulk_create(
        items: list[dict],
        *,
        db: AsyncSession,
    ) -> list[COPOMapping]:
        mappings = [
            COPOMapping(
                co_id=item["co_id"],
                po_id=item["po_id"],
                mapping_strength=item.get("mapping_strength", MappingStrength.MEDIUM),
                justification=item.get("justification"),
            )
            for item in items
        ]
        db.add_all(mappings)
        await db.flush()
        for m in mappings:
            await db.refresh(m)
        return mappings

    @staticmethod
    async def update(
        mapping_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> COPOMapping | None:
        stmt = select(COPOMapping).where(COPOMapping.id == mapping_id)
        result = await db.execute(stmt)
        mapping = result.scalar_one_or_none()
        if mapping is None:
            return None
        for key, value in updates.items():
            setattr(mapping, key, value)
        await db.flush()
        await db.refresh(mapping)
        return mapping

    @staticmethod
    async def delete(
        mapping_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(COPOMapping).where(COPOMapping.id == mapping_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_by_co(
        co_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = delete(COPOMapping).where(COPOMapping.co_id == co_id)
        result = await db.execute(stmt)
        return result.rowcount

    @staticmethod
    async def replace_for_co(
        co_id: UUID,
        items: list[dict],
        *,
        db: AsyncSession,
    ) -> list[COPOMapping]:
        """Atomically replace all PO mappings for a CO (delete then bulk insert)."""
        await COPOMappingRepository.delete_by_co(co_id, db=db)
        if not items:
            return []
        return await COPOMappingRepository.bulk_create(
            [{"co_id": co_id, **item} for item in items],
            db=db,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        mapping_id: UUID,
        *,
        db: AsyncSession,
    ) -> COPOMapping | None:
        stmt = select(COPOMapping).where(COPOMapping.id == mapping_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_co_and_po(
        co_id: UUID,
        po_id: UUID,
        *,
        db: AsyncSession,
    ) -> COPOMapping | None:
        stmt = select(COPOMapping).where(
            and_(COPOMapping.co_id == co_id, COPOMapping.po_id == po_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_co(
        co_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[COPOMapping]:
        stmt = select(COPOMapping).where(COPOMapping.co_id == co_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_syllabus(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[COPOMapping]:
        """Return all CO-PO mappings for every CO belonging to this syllabus."""
        stmt = (
            select(COPOMapping)
            .join(CourseOutcome, COPOMapping.co_id == CourseOutcome.id)
            .where(CourseOutcome.syllabus_id == syllabus_id)
            .order_by(CourseOutcome.display_order.asc(), COPOMapping.co_id)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# SyllabusUnitRepository
# ---------------------------------------------------------------------------

class SyllabusUnitRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        syllabus_id: UUID,
        unit_number: int,
        title: str,
        total_hours: int,
        topics: list | None = None,
        pedagogy: str | None = None,
        bloom_summary: list | None = None,
        *,
        db: AsyncSession,
    ) -> SyllabusUnit:
        unit = SyllabusUnit(
            syllabus_id=syllabus_id,
            unit_number=unit_number,
            title=title,
            total_hours=total_hours,
            topics=topics or [],
            pedagogy=pedagogy,
            bloom_summary=bloom_summary,
        )
        db.add(unit)
        await db.flush()
        await db.refresh(unit)
        return unit

    @staticmethod
    async def bulk_create(
        syllabus_id: UUID,
        items: list[dict],
        *,
        db: AsyncSession,
    ) -> list[SyllabusUnit]:
        units = [
            SyllabusUnit(
                syllabus_id=syllabus_id,
                unit_number=item["unit_number"],
                title=item["title"],
                # The official prose block that prints in the regulation.
                content=item.get("content"),
                total_hours=item["total_hours"],
                topics=item.get("topics", []),
                pedagogy=item.get("pedagogy"),
                bloom_summary=item.get("bloom_summary"),
            )
            for item in items
        ]
        db.add_all(units)
        await db.flush()
        for u in units:
            await db.refresh(u)
        return units

    @staticmethod
    async def update(
        unit_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> SyllabusUnit | None:
        stmt = select(SyllabusUnit).where(SyllabusUnit.id == unit_id)
        result = await db.execute(stmt)
        unit = result.scalar_one_or_none()
        if unit is None:
            return None
        for key, value in updates.items():
            setattr(unit, key, value)
        await db.flush()
        await db.refresh(unit)
        return unit

    @staticmethod
    async def delete(
        unit_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(SyllabusUnit).where(SyllabusUnit.id == unit_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_all(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = delete(SyllabusUnit).where(SyllabusUnit.syllabus_id == syllabus_id)
        result = await db.execute(stmt)
        return result.rowcount

    @staticmethod
    async def reorder(
        order_map: dict[UUID, int],
        *,
        db: AsyncSession,
    ) -> int:
        """Bulk-update unit_number for each unit_id in the map."""
        updated = 0
        for unit_id, new_number in order_map.items():
            stmt = (
                update(SyllabusUnit)
                .where(SyllabusUnit.id == unit_id)
                .values(unit_number=new_number, updated_at=func.now())
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
        unit_id: UUID,
        *,
        db: AsyncSession,
    ) -> SyllabusUnit | None:
        stmt = select(SyllabusUnit).where(SyllabusUnit.id == unit_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_number(
        syllabus_id: UUID,
        unit_number: int,
        *,
        db: AsyncSession,
    ) -> SyllabusUnit | None:
        stmt = select(SyllabusUnit).where(
            and_(
                SyllabusUnit.syllabus_id == syllabus_id,
                SyllabusUnit.unit_number == unit_number,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_syllabus(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[SyllabusUnit]:
        stmt = (
            select(SyllabusUnit)
            .where(SyllabusUnit.syllabus_id == syllabus_id)
            .order_by(SyllabusUnit.unit_number.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_syllabus(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(SyllabusUnit.id)).where(
            SyllabusUnit.syllabus_id == syllabus_id
        )
        result = await db.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# SyllabusReferenceRepository
# ---------------------------------------------------------------------------

class SyllabusReferenceRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        syllabus_id: UUID,
        title: str,
        ref_type: RefType,
        source: RefSource,
        authors: list | None = None,
        year: int | None = None,
        doi: str | None = None,
        isbn: str | None = None,
        url: str | None = None,
        publisher: str | None = None,
        is_confirmed: bool = True,
        *,
        db: AsyncSession,
    ) -> SyllabusReference:
        ref = SyllabusReference(
            syllabus_id=syllabus_id,
            title=title,
            ref_type=ref_type,
            source=source,
            authors=authors or [],
            year=year,
            doi=doi,
            isbn=isbn,
            url=url,
            publisher=publisher,
            is_confirmed=is_confirmed,
        )
        db.add(ref)
        await db.flush()
        await db.refresh(ref)
        return ref

    @staticmethod
    async def bulk_create(
        syllabus_id: UUID,
        items: list[dict],
        *,
        db: AsyncSession,
    ) -> list[SyllabusReference]:
        refs = [
            SyllabusReference(
                syllabus_id=syllabus_id,
                title=item["title"],
                ref_type=item["ref_type"],
                source=item["source"],
                authors=item.get("authors", []),
                year=item.get("year"),
                doi=item.get("doi"),
                isbn=item.get("isbn"),
                url=item.get("url"),
                publisher=item.get("publisher"),
                is_confirmed=item.get("is_confirmed", True),
            )
            for item in items
        ]
        db.add_all(refs)
        await db.flush()
        for r in refs:
            await db.refresh(r)
        return refs

    @staticmethod
    async def update(
        ref_id: UUID,
        updates: dict,
        *,
        db: AsyncSession,
    ) -> SyllabusReference | None:
        stmt = select(SyllabusReference).where(SyllabusReference.id == ref_id)
        result = await db.execute(stmt)
        ref = result.scalar_one_or_none()
        if ref is None:
            return None
        for key, value in updates.items():
            setattr(ref, key, value)
        await db.flush()
        await db.refresh(ref)
        return ref

    @staticmethod
    async def delete(
        ref_id: UUID,
        *,
        db: AsyncSession,
    ) -> bool:
        stmt = delete(SyllabusReference).where(SyllabusReference.id == ref_id)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def delete_all_unconfirmed(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
        ref_types: list[RefType] | None = None,
    ) -> int:
        """Clear AI-fetched references so enrichment can re-run idempotently.

        Confirmed references are never touched — those are the Board's own, curated
        by hand, and an AI re-run must not throw them away.

        `ref_types` SCOPES the delete to one part of the bibliography. It exists
        because Text Books and Reference Books are regenerated independently (see
        RegenerateSection.BOOKS vs REFERENCES): a Board unhappy with the Text Books
        asks for those to be rewritten, and clearing the Web Resources along with
        them would silently destroy work nobody asked to lose.

        None clears the whole unconfirmed bibliography, which is what a full
        generation wants.
        """
        conditions = [
            SyllabusReference.syllabus_id == syllabus_id,
            SyllabusReference.is_confirmed.is_(False),
        ]
        if ref_types:
            conditions.append(SyllabusReference.ref_type.in_(ref_types))

        stmt = delete(SyllabusReference).where(and_(*conditions))
        result = await db.execute(stmt)
        return result.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        ref_id: UUID,
        *,
        db: AsyncSession,
    ) -> SyllabusReference | None:
        stmt = select(SyllabusReference).where(SyllabusReference.id == ref_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_syllabus(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[SyllabusReference]:
        stmt = (
            select(SyllabusReference)
            .where(SyllabusReference.syllabus_id == syllabus_id)
            .order_by(SyllabusReference.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_syllabus(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(SyllabusReference.id)).where(
            SyllabusReference.syllabus_id == syllabus_id
        )
        result = await db.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# TaskJobPublicRepository  (raw SQL on public.task_jobs — same as M01)
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
            "id":         str(job_id),
            "tenant_id":  str(tenant_id),
            "task_type":  task_type,
            "queue_name": queue_name,
            "payload":    json.dumps(payload),
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
