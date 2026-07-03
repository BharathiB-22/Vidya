"""
M05 Learning Material Packager — Repository layer (STEP-07).

Classes:
  LearningPackageRepository  — CRUD + status lifecycle for learning_packages
  PackageItemRepository      — bulk insert, dedup check, relevance-score update
  PackageQARepository        — Q&A session + message persistence

Conventions (mirrors M03):
  - All methods are @staticmethod with keyword-only `db: AsyncSession`.
  - Write methods use db.flush() so callers control commit boundaries.
  - Status-transition methods use UPDATE ... RETURNING for single round-trips.
  - Bulk inserts use db.add_all() + single flush.
  - No cross-tenant queries; schema isolation is enforced by set_search_path
    at connection time (same as M02/M03).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m05_learning_materials.models import (
    LearningPackage,
    MaterialSourceType,
    PackageItem,
    PackageQAMessage,
    PackageQASession,
    PackageStatus,
    QARole,
)

logger = logging.getLogger("vidya.m05.repository")


# ---------------------------------------------------------------------------
# LearningPackageRepository
# ---------------------------------------------------------------------------

class LearningPackageRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        syllabus_id: UUID,
        unit_number: int,
        created_by_user_id: UUID,
        version: int = 1,
        top_n: int = 10,
        *,
        db: AsyncSession,
    ) -> LearningPackage:
        """Create a new package in PENDING status."""
        pkg = LearningPackage(
            syllabus_id=syllabus_id,
            unit_number=unit_number,
            created_by_user_id=created_by_user_id,
            version=version,
            top_n=top_n,
            status=PackageStatus.PENDING,
        )
        db.add(pkg)
        await db.flush()
        await db.refresh(pkg)
        return pkg

    @staticmethod
    async def update_status(
        package_id: UUID,
        status: PackageStatus,
        *,
        db: AsyncSession,
    ) -> LearningPackage | None:
        """Generic status transition; sets updated_at."""
        stmt = (
            update(LearningPackage)
            .where(LearningPackage.id == package_id)
            .values(status=status, updated_at=func.now())
            .returning(LearningPackage)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def reset_for_recuration(
        package_id: UUID,
        top_n: int,
        *,
        db: AsyncSession,
    ) -> LearningPackage | None:
        """Reset an existing package to PENDING for an in-place re-curation
        (upsert path — avoids creating a duplicate row for the same
        syllabus_id + unit_number + version)."""
        stmt = (
            update(LearningPackage)
            .where(LearningPackage.id == package_id)
            .values(
                status=PackageStatus.PENDING,
                top_n=top_n,
                updated_at=func.now(),
            )
            .returning(LearningPackage)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_curating(
        package_id: UUID,
        ai_model: str,
        prompt_hash: str,
        *,
        db: AsyncSession,
    ) -> LearningPackage | None:
        """Transition to CURATING; record which AI model and prompt were used."""
        stmt = (
            update(LearningPackage)
            .where(LearningPackage.id == package_id)
            .values(
                status=PackageStatus.CURATING,
                ai_model=ai_model,
                prompt_hash=prompt_hash,
                updated_at=func.now(),
            )
            .returning(LearningPackage)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_ready(
        package_id: UUID,
        item_count: int,
        *,
        db: AsyncSession,
    ) -> LearningPackage | None:
        """Transition to READY; stamp curated_at and update the denormalized item_count."""
        stmt = (
            update(LearningPackage)
            .where(LearningPackage.id == package_id)
            .values(
                status=PackageStatus.READY,
                item_count=item_count,
                curated_at=func.now(),
                updated_at=func.now(),
            )
            .returning(LearningPackage)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_qdrant_indexed(
        package_id: UUID,
        *,
        db: AsyncSession,
    ) -> LearningPackage | None:
        """Mark the package as fully indexed in Qdrant (called by STEP-09 task)."""
        stmt = (
            update(LearningPackage)
            .where(LearningPackage.id == package_id)
            .values(qdrant_indexed=True, updated_at=func.now())
            .returning(LearningPackage)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_outdated_by_syllabus(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        """Bulk-transition all READY packages for a syllabus to OUTDATED.

        Called by the syllabus-bump hook (M02 → M05, R7) before creating the
        new package generation.  Returns the number of rows updated.
        """
        stmt = (
            update(LearningPackage)
            .where(
                and_(
                    LearningPackage.syllabus_id == syllabus_id,
                    LearningPackage.status == PackageStatus.READY,
                )
            )
            .values(status=PackageStatus.OUTDATED, updated_at=func.now())
        )
        result = await db.execute(stmt)
        return result.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        package_id: UUID,
        *,
        db: AsyncSession,
    ) -> LearningPackage | None:
        stmt = select(LearningPackage).where(LearningPackage.id == package_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_syllabus_unit(
        syllabus_id: UUID,
        unit_number: int,
        *,
        db: AsyncSession,
    ) -> LearningPackage | None:
        """Return the current (non-OUTDATED) package for a syllabus unit.

        When multiple versions exist (re-curations), the highest version wins.
        """
        stmt = (
            select(LearningPackage)
            .where(
                and_(
                    LearningPackage.syllabus_id == syllabus_id,
                    LearningPackage.unit_number == unit_number,
                    LearningPackage.status != PackageStatus.OUTDATED,
                )
            )
            .order_by(LearningPackage.version.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def count_by_syllabus(
        syllabus_id: UUID,
        *,
        status_filter: PackageStatus | None = None,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(LearningPackage.id)).where(
            LearningPackage.syllabus_id == syllabus_id
        )
        if status_filter is not None:
            stmt = stmt.where(LearningPackage.status == status_filter)
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def update_item_count(
        package_id: UUID,
        item_count: int,
        *,
        db: AsyncSession,
    ) -> None:
        """Update the denormalized item_count (called by service after add/remove)."""
        stmt = (
            update(LearningPackage)
            .where(LearningPackage.id == package_id)
            .values(item_count=item_count, updated_at=func.now())
        )
        await db.execute(stmt)

    @staticmethod
    async def list_by_syllabus(
        syllabus_id: UUID,
        *,
        status_filter: PackageStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[LearningPackage]:
        stmt = (
            select(LearningPackage)
            .where(LearningPackage.syllabus_id == syllabus_id)
            .order_by(LearningPackage.unit_number.asc(), LearningPackage.version.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter is not None:
            stmt = stmt.where(LearningPackage.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_all(
        *,
        status_filter: PackageStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[LearningPackage]:
        stmt = (
            select(LearningPackage)
            .order_by(LearningPackage.unit_number.asc(), LearningPackage.version.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter is not None:
            stmt = stmt.where(LearningPackage.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_all(
        *,
        status_filter: PackageStatus | None = None,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(LearningPackage.id))
        if status_filter is not None:
            stmt = stmt.where(LearningPackage.status == status_filter)
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def list_by_syllabus_ids(
        syllabus_ids: list[UUID],
        *,
        status_filter: PackageStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[LearningPackage]:
        if not syllabus_ids:
            return []
        stmt = (
            select(LearningPackage)
            .where(LearningPackage.syllabus_id.in_(syllabus_ids))
            .order_by(LearningPackage.unit_number.asc(), LearningPackage.version.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter is not None:
            stmt = stmt.where(LearningPackage.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_syllabus_ids(
        syllabus_ids: list[UUID],
        *,
        status_filter: PackageStatus | None = None,
        db: AsyncSession,
    ) -> int:
        if not syllabus_ids:
            return 0
        stmt = select(func.count(LearningPackage.id)).where(
            LearningPackage.syllabus_id.in_(syllabus_ids)
        )
        if status_filter is not None:
            stmt = stmt.where(LearningPackage.status == status_filter)
        result = await db.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# PackageItemRepository
# ---------------------------------------------------------------------------

class PackageItemRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def bulk_create(
        package_id: UUID,
        items: list[dict[str, Any]],
        *,
        db: AsyncSession,
    ) -> list[PackageItem]:
        """Insert all package items in a single flush.

        Expected keys per dict:
          source_type (str | MaterialSourceType), title (str), url (str | None),
          content_hash (str | None), metadata (dict), relevance_score (float | None),
          display_order (int), faculty_recommended (bool), added_by_user_id (UUID | None).
        """
        rows = [
            PackageItem(
                package_id=package_id,
                source_type=MaterialSourceType(item["source_type"])
                    if isinstance(item["source_type"], str)
                    else item["source_type"],
                title=item["title"],
                url=item.get("url"),
                content_hash=item.get("content_hash"),
                metadata_=item.get("metadata", {}),
                relevance_score=item.get("relevance_score"),
                faculty_recommended=item.get("faculty_recommended", False),
                added_by_user_id=item.get("added_by_user_id"),
                display_order=item.get("display_order", 0),
            )
            for item in items
        ]
        db.add_all(rows)
        await db.flush()
        for row in rows:
            await db.refresh(row)
        return rows

    @staticmethod
    async def update_relevance_score(
        item_id: UUID,
        relevance_score: float,
        display_order: int,
        *,
        db: AsyncSession,
    ) -> PackageItem | None:
        """Update relevance_score and display_order after re-ranking."""
        stmt = (
            update(PackageItem)
            .where(PackageItem.id == item_id)
            .values(
                relevance_score=relevance_score,
                display_order=display_order,
                updated_at=func.now(),
            )
            .returning(PackageItem)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_qdrant_indexed(
        item_id: UUID,
        *,
        db: AsyncSession,
    ) -> PackageItem | None:
        """Mark a single item as indexed in Qdrant (called per-item in STEP-09)."""
        stmt = (
            update(PackageItem)
            .where(PackageItem.id == item_id)
            .values(qdrant_indexed=True, updated_at=func.now())
            .returning(PackageItem)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_faculty_recommended(
        item_id: UUID,
        value: bool,
        *,
        db: AsyncSession,
    ) -> PackageItem | None:
        """Set or clear the faculty_recommended flag on a single item."""
        stmt = (
            update(PackageItem)
            .where(PackageItem.id == item_id)
            .values(faculty_recommended=value, updated_at=func.now())
            .returning(PackageItem)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_all_for_package(
        package_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        """Delete all items for a package; used when re-curating after a syllabus bump."""
        stmt = delete(PackageItem).where(PackageItem.package_id == package_id)
        result = await db.execute(stmt)
        return result.rowcount

    @staticmethod
    async def delete_ai_items(
        package_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        """Delete only AI-curated items (added_by_user_id IS NULL); preserves faculty items."""
        stmt = delete(PackageItem).where(
            and_(
                PackageItem.package_id == package_id,
                PackageItem.added_by_user_id.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.rowcount

    @staticmethod
    async def update_display_order(
        item_id: UUID,
        display_order: int,
        *,
        db: AsyncSession,
    ) -> None:
        """Update the display_order for a single item (used to resequence faculty items)."""
        stmt = (
            update(PackageItem)
            .where(PackageItem.id == item_id)
            .values(display_order=display_order, updated_at=func.now())
        )
        await db.execute(stmt)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        item_id: UUID,
        *,
        db: AsyncSession,
    ) -> PackageItem | None:
        stmt = select(PackageItem).where(PackageItem.id == item_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_package(
        package_id: UUID,
        *,
        faculty_only: bool = False,
        db: AsyncSession,
    ) -> list[PackageItem]:
        """Return items ordered by display_order (relevance rank).

        `faculty_only=True` filters to faculty-recommended items only.
        """
        stmt = (
            select(PackageItem)
            .where(PackageItem.package_id == package_id)
            .order_by(PackageItem.display_order.asc())
        )
        if faculty_only:
            stmt = stmt.where(PackageItem.faculty_recommended.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_faculty_added(
        package_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[PackageItem]:
        """Return items manually added by faculty (added_by_user_id IS NOT NULL), ordered by display_order."""
        stmt = (
            select(PackageItem)
            .where(
                and_(
                    PackageItem.package_id == package_id,
                    PackageItem.added_by_user_id.isnot(None),
                )
            )
            .order_by(PackageItem.display_order.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def dedup_hash_exists(
        package_id: UUID,
        content_hash: str,
        *,
        db: AsyncSession,
    ) -> bool:
        """Return True if content_hash already exists for this package (R2 dedup check)."""
        stmt = select(func.count(PackageItem.id)).where(
            and_(
                PackageItem.package_id == package_id,
                PackageItem.content_hash == content_hash,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one() > 0


# ---------------------------------------------------------------------------
# PackageQARepository
# ---------------------------------------------------------------------------

class PackageQARepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create_session(
        package_id: UUID,
        student_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> PackageQASession:
        """Open a new Q&A session for a student on a package."""
        session = PackageQASession(
            package_id=package_id,
            student_user_id=student_user_id,
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    @staticmethod
    async def append_message(
        session_id: UUID,
        role: QARole,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        *,
        db: AsyncSession,
    ) -> PackageQAMessage:
        """Append one turn (USER or ASSISTANT) to an existing Q&A session."""
        msg = PackageQAMessage(
            session_id=session_id,
            role=role,
            content=content,
            sources=sources or [],
        )
        db.add(msg)
        # Touch updated_at on the parent session for easy "last activity" queries.
        await db.execute(
            update(PackageQASession)
            .where(PackageQASession.id == session_id)
            .values(updated_at=func.now())
        )
        await db.flush()
        await db.refresh(msg)
        return msg

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_session(
        session_id: UUID,
        *,
        db: AsyncSession,
    ) -> PackageQASession | None:
        stmt = select(PackageQASession).where(PackageQASession.id == session_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_session_with_messages(
        session_id: UUID,
        *,
        db: AsyncSession,
    ) -> PackageQASession | None:
        """Eager-load messages for replay / context window reconstruction."""
        stmt = (
            select(PackageQASession)
            .where(PackageQASession.id == session_id)
            .options(selectinload(PackageQASession.messages))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_messages(
        session_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[PackageQAMessage]:
        """Return all messages in chronological order (oldest first)."""
        stmt = (
            select(PackageQAMessage)
            .where(PackageQAMessage.session_id == session_id)
            .order_by(PackageQAMessage.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_sessions_for_student(
        package_id: UUID,
        student_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[PackageQASession]:
        """All sessions a student has opened for a given package, newest first."""
        stmt = (
            select(PackageQASession)
            .where(
                and_(
                    PackageQASession.package_id == package_id,
                    PackageQASession.student_user_id == student_user_id,
                )
            )
            .order_by(PackageQASession.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
