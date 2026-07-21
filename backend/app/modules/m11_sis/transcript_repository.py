"""
SIS Transcript Generation — H61 Repository layer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m11_sis.transcript_models import (
    PublicTranscriptIndex,
    SisTranscript,
    SisTranscriptSemesterLine,
    SisTranscriptSubjectLine,
    SisTranscriptVerificationLog,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Transcript CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptRepo:

    @staticmethod
    async def create(transcript: SisTranscript, db: AsyncSession) -> SisTranscript:
        db.add(transcript)
        await db.flush()
        return transcript

    @staticmethod
    async def get_by_id(
        transcript_id: UUID,
        db: AsyncSession,
        *,
        with_lines: bool = False,
    ) -> Optional[SisTranscript]:
        stmt = select(SisTranscript).where(SisTranscript.id == transcript_id)
        if with_lines:
            stmt = stmt.options(
                selectinload(SisTranscript.semester_lines).selectinload(
                    SisTranscriptSemesterLine.subject_lines
                )
            )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_verification_code(
        code: UUID,
        db: AsyncSession,
    ) -> Optional[SisTranscript]:
        result = await db.execute(
            select(SisTranscript).where(SisTranscript.verification_code == code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_student(
        student_id: UUID,
        db: AsyncSession,
        *,
        status_filter: Optional[str] = None,
    ) -> list[SisTranscript]:
        stmt = (
            select(SisTranscript)
            .where(SisTranscript.student_id == student_id)
            .order_by(SisTranscript.version.desc(), SisTranscript.created_at.desc())
        )
        if status_filter:
            stmt = stmt.where(SisTranscript.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_all(
        db: AsyncSession,
        *,
        status_filter: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SisTranscript]:
        stmt = (
            select(SisTranscript)
            .order_by(SisTranscript.requested_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter:
            stmt = stmt.where(SisTranscript.status == status_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_all(
        db: AsyncSession,
        *,
        status_filter: Optional[str] = None,
    ) -> int:
        from sqlalchemy import func
        stmt = select(func.count()).select_from(SisTranscript)
        if status_filter:
            stmt = stmt.where(SisTranscript.status == status_filter)
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def has_active_request(student_id: UUID, db: AsyncSession) -> bool:
        """Return True if student already has a REQUESTED or GENERATED transcript."""
        result = await db.execute(
            select(SisTranscript).where(
                SisTranscript.student_id == student_id,
                SisTranscript.status.in_(["REQUESTED", "GENERATED"]),
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def next_transcript_number(
        tenant_code: str,
        year: int,
        db: AsyncSession,
    ) -> str:
        result = await db.execute(text("SELECT nextval('sis_transcript_seq')"))
        seq = result.scalar_one()
        return f"TRX/{tenant_code.upper()}/{year}/{seq:06d}"


# ─────────────────────────────────────────────────────────────────────────────
# Semester / Subject Lines
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptLinesRepo:

    @staticmethod
    async def bulk_insert_semester_lines(
        lines: list[SisTranscriptSemesterLine],
        db: AsyncSession,
    ) -> None:
        for line in lines:
            db.add(line)
        await db.flush()

    @staticmethod
    async def bulk_insert_subject_lines(
        lines: list[SisTranscriptSubjectLine],
        db: AsyncSession,
    ) -> None:
        for line in lines:
            db.add(line)
        await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Verification Log
# ─────────────────────────────────────────────────────────────────────────────

class VerificationLogRepo:

    @staticmethod
    async def append(
        entry: SisTranscriptVerificationLog,
        db: AsyncSession,
    ) -> None:
        db.add(entry)
        await db.flush()

    @staticmethod
    async def list_for_transcript(
        transcript_id: UUID,
        db: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SisTranscriptVerificationLog]:
        result = await db.execute(
            select(SisTranscriptVerificationLog)
            .where(SisTranscriptVerificationLog.transcript_id == transcript_id)
            .order_by(SisTranscriptVerificationLog.verified_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Public Transcript Index (public schema — cross-tenant)
# ─────────────────────────────────────────────────────────────────────────────

class PublicTranscriptIndexRepo:

    @staticmethod
    async def upsert(
        verification_code: UUID,
        tenant_id: UUID,
        schema_name: str,
        transcript_id: UUID,
        transcript_number: Optional[str],
        status: str,
        issued_at: Optional[datetime],
        db: AsyncSession,
    ) -> None:
        existing = await db.execute(
            select(PublicTranscriptIndex).where(
                PublicTranscriptIndex.verification_code == verification_code
            )
        )
        row = existing.scalar_one_or_none()
        now = _now()
        if row:
            row.status      = status
            row.issued_at   = issued_at
            row.updated_at  = now
            await db.flush()
        else:
            entry = PublicTranscriptIndex(
                verification_code = verification_code,
                tenant_id         = tenant_id,
                schema_name       = schema_name,
                transcript_id     = transcript_id,
                transcript_number = transcript_number,
                status            = status,
                issued_at         = issued_at,
                updated_at        = now,
            )
            db.add(entry)
            await db.flush()

    @staticmethod
    async def get_by_code(
        verification_code: UUID,
        db: AsyncSession,
    ) -> Optional[PublicTranscriptIndex]:
        result = await db.execute(
            select(PublicTranscriptIndex).where(
                PublicTranscriptIndex.verification_code == verification_code
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_status(
        verification_code: UUID,
        status: str,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(PublicTranscriptIndex)
            .where(PublicTranscriptIndex.verification_code == verification_code)
            .values(status=status, updated_at=_now())
        )
        await db.flush()
