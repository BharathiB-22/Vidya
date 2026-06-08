"""
SIS Graduation Audit — H62 Repository layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m11_sis.graduation_models import (
    PublicGraduationIndex,
    SisGraduationAudit,
    SisGraduationCandidate,
    SisGraduationCertificate,
    SisGraduationOverride,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Graduation Audit
# ─────────────────────────────────────────────────────────────────────────────

class GraduationAuditRepo:

    @staticmethod
    async def create(audit: SisGraduationAudit, db: AsyncSession) -> SisGraduationAudit:
        db.add(audit)
        await db.flush()
        return audit

    @staticmethod
    async def get_by_id(
        audit_id: UUID,
        db: AsyncSession,
        *,
        with_candidates: bool = False,
    ) -> Optional[SisGraduationAudit]:
        stmt = select(SisGraduationAudit).where(SisGraduationAudit.id == audit_id)
        if with_candidates:
            stmt = stmt.options(selectinload(SisGraduationAudit.candidates))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_for_batch(
        batch_id: UUID,
        db: AsyncSession,
    ) -> Optional[SisGraduationAudit]:
        """Return any DRAFT or SUBMITTED audit for this batch (prevent duplicate triggers)."""
        result = await db.execute(
            select(SisGraduationAudit).where(
                SisGraduationAudit.batch_id == batch_id,
                SisGraduationAudit.status.in_(["DRAFT", "SUBMITTED"]),
            ).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        *,
        status_filter: Optional[str] = None,
        batch_id: Optional[UUID] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SisGraduationAudit]:
        stmt = (
            select(SisGraduationAudit)
            .order_by(SisGraduationAudit.triggered_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter:
            stmt = stmt.where(SisGraduationAudit.status == status_filter)
        if batch_id:
            stmt = stmt.where(SisGraduationAudit.batch_id == batch_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_all(
        db: AsyncSession,
        *,
        status_filter: Optional[str] = None,
        batch_id: Optional[UUID] = None,
    ) -> int:
        stmt = select(func.count()).select_from(SisGraduationAudit)
        if status_filter:
            stmt = stmt.where(SisGraduationAudit.status == status_filter)
        if batch_id:
            stmt = stmt.where(SisGraduationAudit.batch_id == batch_id)
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def refresh_counters(audit_id: UUID, db: AsyncSession) -> None:
        totals = (await db.execute(
            select(
                func.count().label("total"),
                func.sum(
                    func.cast(SisGraduationCandidate.eligibility_status == "ELIGIBLE", func.Integer)
                ).label("eligible"),
                func.sum(
                    func.cast(SisGraduationCandidate.eligibility_status == "PROVISIONAL", func.Integer)
                ).label("provisional"),
                func.sum(
                    func.cast(SisGraduationCandidate.eligibility_status == "NOT_ELIGIBLE", func.Integer)
                ).label("not_eligible"),
                func.sum(
                    func.cast(SisGraduationCandidate.board_status == "RATIFIED", func.Integer)
                ).label("ratified"),
                func.sum(
                    func.cast(SisGraduationCandidate.board_status == "DEFERRED", func.Integer)
                ).label("deferred"),
            ).where(SisGraduationCandidate.audit_id == audit_id)
        )).mappings().one()

        await db.execute(
            update(SisGraduationAudit)
            .where(SisGraduationAudit.id == audit_id)
            .values(
                total_candidates   = totals["total"]       or 0,
                eligible_count     = totals["eligible"]    or 0,
                provisional_count  = totals["provisional"] or 0,
                not_eligible_count = totals["not_eligible"] or 0,
                ratified_count     = totals["ratified"]    or 0,
                deferred_count     = totals["deferred"]    or 0,
                updated_at         = _now(),
            )
        )
        await db.flush()

    @staticmethod
    async def next_certificate_number(
        tenant_code: str,
        year: int,
        db: AsyncSession,
    ) -> str:
        from sqlalchemy import text
        result = await db.execute(text("SELECT nextval('sis_graduation_cert_seq')"))
        seq = result.scalar_one()
        return f"CERT/{tenant_code.upper()}/{year}/{seq:06d}"


# ─────────────────────────────────────────────────────────────────────────────
# Graduation Candidates
# ─────────────────────────────────────────────────────────────────────────────

class GraduationCandidateRepo:

    @staticmethod
    async def bulk_create(
        candidates: list[SisGraduationCandidate],
        db: AsyncSession,
    ) -> None:
        for c in candidates:
            db.add(c)
        await db.flush()

    @staticmethod
    async def get_by_id(
        candidate_id: UUID,
        db: AsyncSession,
    ) -> Optional[SisGraduationCandidate]:
        result = await db.execute(
            select(SisGraduationCandidate).where(SisGraduationCandidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_student_and_audit(
        student_id: UUID,
        audit_id: UUID,
        db: AsyncSession,
    ) -> Optional[SisGraduationCandidate]:
        result = await db.execute(
            select(SisGraduationCandidate).where(
                SisGraduationCandidate.student_id == student_id,
                SisGraduationCandidate.audit_id   == audit_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_audit(
        audit_id: UUID,
        db: AsyncSession,
        *,
        eligibility_filter: Optional[str] = None,
        board_filter: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[SisGraduationCandidate]:
        stmt = (
            select(SisGraduationCandidate)
            .where(SisGraduationCandidate.audit_id == audit_id)
            .order_by(SisGraduationCandidate.student_name_snapshot)
            .offset(offset)
            .limit(limit)
        )
        if eligibility_filter:
            stmt = stmt.where(SisGraduationCandidate.eligibility_status == eligibility_filter)
        if board_filter:
            stmt = stmt.where(SisGraduationCandidate.board_status == board_filter)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete_for_audit(audit_id: UUID, db: AsyncSession) -> None:
        """Delete all candidates for an audit — used during regenerate (DRAFT only)."""
        from sqlalchemy import delete
        await db.execute(
            delete(SisGraduationCandidate).where(
                SisGraduationCandidate.audit_id == audit_id
            )
        )
        await db.flush()

    @staticmethod
    async def list_ratified_for_audit(
        audit_id: UUID,
        db: AsyncSession,
    ) -> list[SisGraduationCandidate]:
        result = await db.execute(
            select(SisGraduationCandidate).where(
                SisGraduationCandidate.audit_id    == audit_id,
                SisGraduationCandidate.board_status == "RATIFIED",
                SisGraduationCandidate.certificate_status == "NOT_ISSUED",
            ).order_by(SisGraduationCandidate.student_name_snapshot)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_latest_for_student(
        student_id: UUID,
        db: AsyncSession,
    ) -> Optional[SisGraduationCandidate]:
        result = await db.execute(
            select(SisGraduationCandidate)
            .where(SisGraduationCandidate.student_id == student_id)
            .order_by(SisGraduationCandidate.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────────────
# Graduation Overrides  (append-only)
# ─────────────────────────────────────────────────────────────────────────────

class GraduationOverrideRepo:

    @staticmethod
    async def append(
        entry: SisGraduationOverride,
        db: AsyncSession,
    ) -> None:
        db.add(entry)
        await db.flush()

    @staticmethod
    async def list_for_candidate(
        candidate_id: UUID,
        db: AsyncSession,
    ) -> list[SisGraduationOverride]:
        result = await db.execute(
            select(SisGraduationOverride)
            .where(SisGraduationOverride.candidate_id == candidate_id)
            .order_by(SisGraduationOverride.created_at.asc())
        )
        return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Graduation Certificates
# ─────────────────────────────────────────────────────────────────────────────

class GraduationCertificateRepo:

    @staticmethod
    async def create(
        cert: SisGraduationCertificate,
        db: AsyncSession,
    ) -> SisGraduationCertificate:
        db.add(cert)
        await db.flush()
        return cert

    @staticmethod
    async def get_by_id(
        cert_id: UUID,
        db: AsyncSession,
    ) -> Optional[SisGraduationCertificate]:
        result = await db.execute(
            select(SisGraduationCertificate).where(SisGraduationCertificate.id == cert_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_number(
        certificate_number: str,
        db: AsyncSession,
    ) -> Optional[SisGraduationCertificate]:
        result = await db.execute(
            select(SisGraduationCertificate).where(
                SisGraduationCertificate.certificate_number == certificate_number
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        *,
        status_filter: Optional[str] = None,
        student_id: Optional[UUID] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SisGraduationCertificate]:
        stmt = (
            select(SisGraduationCertificate)
            .order_by(SisGraduationCertificate.issued_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if status_filter:
            stmt = stmt.where(SisGraduationCertificate.status == status_filter)
        if student_id:
            stmt = stmt.where(SisGraduationCertificate.student_id == student_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Public Graduation Index (public schema — cross-tenant)
# ─────────────────────────────────────────────────────────────────────────────

class PublicGraduationIndexRepo:

    @staticmethod
    async def upsert(
        certificate_number: str,
        tenant_id: UUID,
        schema_name: str,
        certificate_id: UUID,
        student_id: UUID,
        is_provisional: bool,
        status: str,
        graduation_year: Optional[int],
        issued_at: Optional[datetime],
        db: AsyncSession,
    ) -> None:
        existing = await db.execute(
            select(PublicGraduationIndex).where(
                PublicGraduationIndex.certificate_number == certificate_number
            )
        )
        row = existing.scalar_one_or_none()
        now = _now()
        if row:
            row.status         = status
            row.is_provisional = is_provisional
            row.updated_at     = now
            await db.flush()
        else:
            entry = PublicGraduationIndex(
                certificate_number = certificate_number,
                tenant_id          = tenant_id,
                schema_name        = schema_name,
                certificate_id     = certificate_id,
                student_id         = student_id,
                is_provisional     = is_provisional,
                status             = status,
                graduation_year    = graduation_year,
                issued_at          = issued_at,
                updated_at         = now,
            )
            db.add(entry)
            await db.flush()

    @staticmethod
    async def get_by_number(
        certificate_number: str,
        db: AsyncSession,
    ) -> Optional[PublicGraduationIndex]:
        result = await db.execute(
            select(PublicGraduationIndex).where(
                PublicGraduationIndex.certificate_number == certificate_number
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_status(
        certificate_number: str,
        status: str,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(PublicGraduationIndex)
            .where(PublicGraduationIndex.certificate_number == certificate_number)
            .values(status=status, updated_at=_now())
        )
        await db.flush()
