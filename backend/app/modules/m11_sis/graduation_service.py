"""
SIS Graduation Audit — H62 Service layer.

Human gates:
  Gate 1: Dean submits (DRAFT → SUBMITTED)
  Gate 2a: Board ratifies / defers per candidate
  Gate 2b: Board approves batch (SUBMITTED → BOARD_APPROVED; board_resolution_ref mandatory)
  Gate 3: Registrar issues certificate(s) (per-candidate or batch)

No automatic graduation. AI advises, humans decide.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.graduation_models import (
    CandidateBoardStatus,
    CandidateCertificateStatus,
    CandidateEligibilityStatus,
    GraduationAuditStatus,
    GraduationCertificateStatus,
    SisGraduationAudit,
    SisGraduationCandidate,
    SisGraduationCertificate,
    SisGraduationOverride,
)
from app.modules.m11_sis.graduation_repository import (
    GraduationAuditRepo,
    GraduationCandidateRepo,
    GraduationCertificateRepo,
    GraduationOverrideRepo,
    PublicGraduationIndexRepo,
)
from app.modules.m11_sis.graduation_schemas import (
    AuditApproveIn,
    BoardDeferIn,
    BoardRatifyIn,
    CandidateOverrideIn,
    CertificateRevokeIn,
    CertificateVerifyResponse,
    ProvisionalConfirmIn,
    StudentGraduationStatusRead,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _partial_name(full_name: str) -> str:
    """Return 'Firstname L.' for public display — never expose full name."""
    parts = full_name.strip().split()
    if not parts:
        return "Unknown"
    first = parts[0]
    if len(parts) > 1:
        return f"{first} {parts[-1][0]}."
    return first


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility Engine
# ─────────────────────────────────────────────────────────────────────────────

class EligibilityEngine:
    """
    Computes advisory eligibility for a single student within a batch.

    All outputs are advisory only — a human (Dean/Board) must ratify.
    """

    @staticmethod
    async def compute(
        student_id: UUID,
        batch_id: UUID,
        db: AsyncSession,
    ) -> dict:
        """
        Returns a dict with:
          flags: {missing_declarations, has_arrears, credits_shortfall, has_withheld,
                  final_sem_not_locked, graduation_year_not_reached,
                  attendance_below_threshold, disciplinary_hold}
          values: {total_credits_earned, min_credits_required, current_cgpa,
                   arrear_count, semesters_declared, program_id, program_name,
                   usn, student_name, graduation_year}
          eligibility_status: ELIGIBLE | NOT_ELIGIBLE | PROVISIONAL
        """
        flags: dict[str, bool] = {
            "missing_declarations":        False,
            "has_arrears":                 False,
            "credits_shortfall":           False,
            "has_withheld":                False,
            "final_sem_not_locked":        False,
            "graduation_year_not_reached": False,
            "attendance_below_threshold":  False,
            "disciplinary_hold":           False,
        }
        values: dict = {
            "total_credits_earned": None,
            "min_credits_required": None,
            "current_cgpa":         None,
            "arrear_count":         0,
            "semesters_declared":   0,
            "program_id":           None,
            "program_name":         None,
            "usn":                  None,
            "student_name":         "Unknown",
            "graduation_year":      None,
        }

        # ── Student profile ───────────────────────────────────────────────────
        from app.modules.m11_sis.models import SisStudentProfile
        profile_row = (await db.execute(
            select(SisStudentProfile).where(SisStudentProfile.user_id == student_id)
        )).scalar_one_or_none()

        if profile_row:
            values["usn"] = getattr(profile_row, "usn", None)

        from app.core.auth.models import User
        user_row = (await db.execute(
            select(User).where(User.id == student_id)
        )).scalar_one_or_none()
        if user_row:
            values["student_name"] = getattr(user_row, "full_name", None) or "Unknown"

        # ── Batch → program → min_credits ────────────────────────────────────
        from app.modules.m_academics.models import AcadBatch, AcadProgram, AcadSemester
        batch_row = (await db.execute(
            select(AcadBatch).where(AcadBatch.id == batch_id)
        )).scalar_one_or_none()

        program_row = None
        if batch_row and getattr(batch_row, "program_id", None):
            program_row = (await db.execute(
                select(AcadProgram).where(AcadProgram.id == batch_row.program_id)
            )).scalar_one_or_none()

        if program_row:
            values["program_id"]   = program_row.id
            values["program_name"] = getattr(program_row, "name", None)
            min_credits = getattr(program_row, "min_credits_for_degree", None)
            if min_credits is not None:
                values["min_credits_required"] = Decimal(str(min_credits))

        # ── Compute expected graduation year ──────────────────────────────────
        if batch_row:
            duration = getattr(program_row, "duration_years", None) if program_row else None
            batch_name = getattr(batch_row, "name", "") or ""
            admission_year: Optional[int] = None
            for token in batch_name.split():
                if token.isdigit() and len(token) == 4:
                    admission_year = int(token)
                    break
            if admission_year and duration:
                values["graduation_year"] = admission_year + int(duration)

        # ── Semester / result data ─────────────────────────────────────────────
        sems = (await db.execute(
            select(AcadSemester).where(AcadSemester.batch_id == batch_id)
            .order_by(AcadSemester.number)
        )).scalars().all()

        if sems:
            values["semesters_declared"] = len(sems)
            final_sem = sems[-1]
            if not getattr(final_sem, "is_locked", False):
                flags["final_sem_not_locked"] = True

        # ── Result / arrear analysis ───────────────────────────────────────────
        from app.modules.m11_sis.transcript_models import SisTranscript, TranscriptStatus
        transcript_row = (await db.execute(
            select(SisTranscript).where(
                SisTranscript.student_id == student_id,
                SisTranscript.status == TranscriptStatus.ISSUED,
            ).order_by(SisTranscript.created_at.desc()).limit(1)
        )).scalar_one_or_none()

        if transcript_row:
            cgpa = getattr(transcript_row, "cgpa_snapshot", None)
            if cgpa is not None:
                values["current_cgpa"] = Decimal(str(cgpa))

            total_credits = getattr(transcript_row, "total_credits_earned", None)
            if total_credits is not None:
                values["total_credits_earned"] = Decimal(str(total_credits))
                if values["min_credits_required"] is not None:
                    if values["total_credits_earned"] < values["min_credits_required"]:
                        flags["credits_shortfall"] = True

            arrear_count = getattr(transcript_row, "arrear_count", None)
            if arrear_count:
                values["arrear_count"] = int(arrear_count)
                if int(arrear_count) > 0:
                    flags["has_arrears"] = True
        else:
            if values["min_credits_required"] is not None:
                flags["credits_shortfall"] = True
            flags["missing_declarations"] = True

        # ── Graduation year check ─────────────────────────────────────────────
        if values["graduation_year"] is not None:
            current_year = datetime.now().year
            if current_year < values["graduation_year"]:
                flags["graduation_year_not_reached"] = True

        # ── Advisory eligibility status ───────────────────────────────────────
        blocking_flags = [
            flags["has_arrears"],
            flags["credits_shortfall"],
            flags["has_withheld"],
            flags["disciplinary_hold"],
        ]
        advisory_flags = [
            flags["missing_declarations"],
            flags["final_sem_not_locked"],
            flags["graduation_year_not_reached"],
            flags["attendance_below_threshold"],
        ]

        if any(blocking_flags):
            eligibility_status = CandidateEligibilityStatus.NOT_ELIGIBLE
        elif any(advisory_flags):
            eligibility_status = CandidateEligibilityStatus.PROVISIONAL
        else:
            eligibility_status = CandidateEligibilityStatus.ELIGIBLE

        return {
            "flags": flags,
            "values": values,
            "eligibility_status": eligibility_status.value,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Graduation Lifecycle Service
# ─────────────────────────────────────────────────────────────────────────────

class GraduationLifecycleService:

    # ── Gate 0: Trigger audit (DRAFT) ─────────────────────────────────────────

    @staticmethod
    async def trigger(
        batch_id: UUID,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationAudit:
        existing = await GraduationAuditRepo.get_active_for_batch(batch_id, db)
        if existing:
            raise ValueError(
                f"An active graduation audit already exists for this batch "
                f"(id={existing.id}, status={existing.status}). "
                "Close or complete it before triggering a new one."
            )

        from app.modules.m_academics.models import AcadBatch, AcadProgram
        batch_row = (await db.execute(
            select(AcadBatch).where(AcadBatch.id == batch_id)
        )).scalar_one_or_none()
        if not batch_row:
            raise ValueError(f"Batch {batch_id} not found")

        program_row = None
        if getattr(batch_row, "program_id", None):
            program_row = (await db.execute(
                select(AcadProgram).where(AcadProgram.id == batch_row.program_id)
            )).scalar_one_or_none()

        audit = SisGraduationAudit(
            batch_id               = batch_id,
            batch_name_snapshot    = getattr(batch_row, "name", None),
            program_id             = getattr(batch_row, "program_id", None),
            program_name_snapshot  = getattr(program_row, "name", None) if program_row else None,
            academic_year_snapshot = getattr(batch_row, "academic_year", None),
            status                 = GraduationAuditStatus.DRAFT.value,
            triggered_by           = actor.user_id,
            triggered_at           = _now(),
        )
        await GraduationAuditRepo.create(audit, db)
        await GraduationLifecycleService._populate_candidates(audit.id, batch_id, db)
        await GraduationAuditRepo.refresh_counters(audit.id, db)

        await AuditService.log(
            AuditEventType.GRADUATION_AUDIT_TRIGGERED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationAudit",
            target_id=str(audit.id),
            metadata={"batch_id": str(batch_id), "status": "DRAFT"},
        )
        return audit

    @staticmethod
    async def _populate_candidates(
        audit_id: UUID,
        batch_id: UUID,
        db: AsyncSession,
    ) -> None:
        from app.modules.m_academics.models import AcadEnrollment, AcadSection, AcadSemester

        student_ids_result = await db.execute(
            select(AcadEnrollment.student_id).distinct().where(
                AcadEnrollment.is_active == True,  # noqa: E712
            ).join(AcadSection, AcadSection.id == AcadEnrollment.section_id)
            .join(AcadSemester, AcadSemester.id == AcadSection.semester_id)
            .where(AcadSemester.batch_id == batch_id)
        )
        student_ids = [row[0] for row in student_ids_result.all()]

        candidates = []
        for sid in student_ids:
            result = await EligibilityEngine.compute(sid, batch_id, db)
            flags  = result["flags"]
            values = result["values"]
            c = SisGraduationCandidate(
                audit_id               = audit_id,
                student_id             = sid,
                usn_snapshot           = values.get("usn"),
                student_name_snapshot  = values.get("student_name", "Unknown"),
                program_name_snapshot  = values.get("program_name"),
                missing_declarations        = flags["missing_declarations"],
                has_arrears                 = flags["has_arrears"],
                credits_shortfall           = flags["credits_shortfall"],
                has_withheld                = flags["has_withheld"],
                final_sem_not_locked        = flags["final_sem_not_locked"],
                graduation_year_not_reached = flags["graduation_year_not_reached"],
                attendance_below_threshold  = flags["attendance_below_threshold"],
                disciplinary_hold           = flags["disciplinary_hold"],
                total_credits_earned  = values.get("total_credits_earned"),
                min_credits_required  = values.get("min_credits_required"),
                current_cgpa          = values.get("current_cgpa"),
                arrear_count          = values.get("arrear_count"),
                semesters_declared    = values.get("semesters_declared"),
                eligibility_status    = result["eligibility_status"],
                board_status          = CandidateBoardStatus.PENDING.value,
                certificate_status    = CandidateCertificateStatus.NOT_ISSUED.value,
            )
            candidates.append(c)

        if candidates:
            await GraduationCandidateRepo.bulk_create(candidates, db)

    # ── Regenerate (DRAFT only) ───────────────────────────────────────────────

    @staticmethod
    async def regenerate(
        audit_id: UUID,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationAudit:
        audit = await GraduationAuditRepo.get_by_id(audit_id, db)
        if not audit:
            raise ValueError("Graduation audit not found")
        if audit.status != GraduationAuditStatus.DRAFT.value:
            raise ValueError("Only DRAFT audits can be regenerated")

        await GraduationCandidateRepo.delete_for_audit(audit_id, db)
        await GraduationLifecycleService._populate_candidates(audit_id, audit.batch_id, db)
        await GraduationAuditRepo.refresh_counters(audit_id, db)

        audit.updated_at = _now()
        await db.flush()

        await AuditService.log(
            AuditEventType.GRADUATION_AUDIT_REGENERATED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationAudit",
            target_id=str(audit_id),
            metadata={"batch_id": str(audit.batch_id)},
        )
        return audit

    # ── Gate 1: Dean submits (DRAFT → SUBMITTED) ──────────────────────────────

    @staticmethod
    async def submit(
        audit_id: UUID,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationAudit:
        audit = await GraduationAuditRepo.get_by_id(audit_id, db)
        if not audit:
            raise ValueError("Graduation audit not found")
        if audit.status != GraduationAuditStatus.DRAFT.value:
            raise ValueError("Only DRAFT audits can be submitted")

        audit.status       = GraduationAuditStatus.SUBMITTED.value
        audit.submitted_by = actor.user_id
        audit.submitted_at = _now()
        audit.updated_at   = _now()
        await db.flush()

        await AuditService.log(
            AuditEventType.GRADUATION_AUDIT_SUBMITTED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationAudit",
            target_id=str(audit_id),
            metadata={"status": "SUBMITTED"},
        )
        return audit

    # ── Gate 2a: Board ratifies a candidate ───────────────────────────────────

    @staticmethod
    async def ratify_candidate(
        candidate_id: UUID,
        data: BoardRatifyIn,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationCandidate:
        candidate = await GraduationCandidateRepo.get_by_id(candidate_id, db)
        if not candidate:
            raise ValueError("Candidate not found")

        audit = await GraduationAuditRepo.get_by_id(candidate.audit_id, db)
        if not audit or audit.status != GraduationAuditStatus.SUBMITTED.value:
            raise ValueError("Candidate ratification is only allowed for SUBMITTED audits")

        candidate.board_status     = CandidateBoardStatus.RATIFIED.value
        candidate.board_decided_by = actor.user_id
        candidate.board_decided_at = _now()
        if data.board_notes:
            candidate.board_notes = data.board_notes
        candidate.updated_at = _now()
        await db.flush()

        await AuditService.log(
            AuditEventType.GRADUATION_CANDIDATE_RATIFIED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationCandidate",
            target_id=str(candidate_id),
            metadata={
                "audit_id":   str(candidate.audit_id),
                "student_id": str(candidate.student_id),
            },
        )
        return candidate

    # ── Gate 2a: Board defers a candidate ─────────────────────────────────────

    @staticmethod
    async def defer_candidate(
        candidate_id: UUID,
        data: BoardDeferIn,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationCandidate:
        candidate = await GraduationCandidateRepo.get_by_id(candidate_id, db)
        if not candidate:
            raise ValueError("Candidate not found")

        audit = await GraduationAuditRepo.get_by_id(candidate.audit_id, db)
        if not audit or audit.status != GraduationAuditStatus.SUBMITTED.value:
            raise ValueError("Candidate deferral is only allowed for SUBMITTED audits")

        candidate.board_status     = CandidateBoardStatus.DEFERRED.value
        candidate.board_decided_by = actor.user_id
        candidate.board_decided_at = _now()
        candidate.board_notes      = data.board_notes
        candidate.updated_at       = _now()
        await db.flush()

        await AuditService.log(
            AuditEventType.GRADUATION_CANDIDATE_DEFERRED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationCandidate",
            target_id=str(candidate_id),
            metadata={
                "audit_id":   str(candidate.audit_id),
                "student_id": str(candidate.student_id),
                "reason":     data.board_notes[:100],
            },
        )
        return candidate

    # ── Dean override of eligibility ──────────────────────────────────────────

    @staticmethod
    async def override_candidate(
        candidate_id: UUID,
        data: CandidateOverrideIn,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationCandidate:
        candidate = await GraduationCandidateRepo.get_by_id(candidate_id, db)
        if not candidate:
            raise ValueError("Candidate not found")

        audit = await GraduationAuditRepo.get_by_id(candidate.audit_id, db)
        if not audit:
            raise ValueError("Graduation audit not found")
        if audit.status not in (
            GraduationAuditStatus.DRAFT.value,
            GraduationAuditStatus.SUBMITTED.value,
        ):
            raise ValueError("Overrides only allowed on DRAFT or SUBMITTED audits")

        override_entry = SisGraduationOverride(
            candidate_id    = candidate_id,
            actor_user_id   = actor.user_id,
            actor_role      = actor.role,
            previous_status = candidate.eligibility_status,
            new_status      = data.new_status,
            reason          = data.reason,
            created_at      = _now(),
        )
        await GraduationOverrideRepo.append(override_entry, db)

        candidate.eligibility_status = data.new_status
        candidate.override_reason    = data.reason
        candidate.overridden_by      = actor.user_id
        candidate.overridden_at      = _now()
        if data.provisional_grace_deadline is not None:
            candidate.provisional_grace_deadline = data.provisional_grace_deadline
        candidate.updated_at = _now()
        await db.flush()

        await AuditService.log(
            AuditEventType.GRADUATION_CANDIDATE_OVERRIDDEN,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationCandidate",
            target_id=str(candidate_id),
            metadata={
                "previous_status": override_entry.previous_status,
                "new_status":      data.new_status,
                "reason_hash":     hashlib.sha256(data.reason.encode()).hexdigest()[:16],
            },
        )
        return candidate

    # ── Gate 2b: Board approves batch (SUBMITTED → BOARD_APPROVED) ───────────

    @staticmethod
    async def approve(
        audit_id: UUID,
        data: AuditApproveIn,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationAudit:
        audit = await GraduationAuditRepo.get_by_id(audit_id, db)
        if not audit:
            raise ValueError("Graduation audit not found")
        if audit.status != GraduationAuditStatus.SUBMITTED.value:
            raise ValueError("Only SUBMITTED audits can be Board-approved")

        if not data.board_resolution_ref or not data.board_resolution_ref.strip():
            raise ValueError("board_resolution_ref is required before BOARD_APPROVED")

        audit.status               = GraduationAuditStatus.BOARD_APPROVED.value
        audit.board_approved_by    = actor.user_id
        audit.board_approved_at    = _now()
        audit.board_resolution_ref = data.board_resolution_ref.strip()
        audit.updated_at           = _now()
        await db.flush()

        await AuditService.log(
            AuditEventType.GRADUATION_AUDIT_BOARD_APPROVED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationAudit",
            target_id=str(audit_id),
            metadata={
                "board_resolution_ref": data.board_resolution_ref,
                "status": "BOARD_APPROVED",
            },
        )
        return audit

    # ── Gate 3: Issue certificate for a single ratified candidate ─────────────

    @staticmethod
    async def issue_certificate(
        candidate_id: UUID,
        actor: CurrentUser,
        tenant_code: str,
        db: AsyncSession,
    ) -> SisGraduationCertificate:
        candidate = await GraduationCandidateRepo.get_by_id(candidate_id, db)
        if not candidate:
            raise ValueError("Candidate not found")
        if candidate.board_status != CandidateBoardStatus.RATIFIED.value:
            raise ValueError("Only RATIFIED candidates can have a certificate issued")
        if candidate.certificate_status == CandidateCertificateStatus.ISSUED.value:
            raise ValueError("Certificate already issued for this candidate")

        audit = await GraduationAuditRepo.get_by_id(candidate.audit_id, db)
        if not audit or audit.status != GraduationAuditStatus.BOARD_APPROVED.value:
            raise ValueError("Certificate issuance requires BOARD_APPROVED audit status")

        graduation_year = datetime.now().year
        cert_number = await GraduationAuditRepo.next_certificate_number(
            tenant_code, graduation_year, db
        )

        is_provisional = (
            candidate.eligibility_status == CandidateEligibilityStatus.PROVISIONAL.value
        )

        cert = SisGraduationCertificate(
            candidate_id           = candidate_id,
            audit_id               = audit.id,
            student_id             = candidate.student_id,
            usn_snapshot           = candidate.usn_snapshot,
            student_name_snapshot  = candidate.student_name_snapshot,
            program_name_snapshot  = candidate.program_name_snapshot,
            batch_name_snapshot    = audit.batch_name_snapshot,
            graduation_year        = graduation_year,
            overall_cgpa_snapshot  = candidate.current_cgpa,
            total_credits_earned   = candidate.total_credits_earned,
            certificate_number     = cert_number,
            is_provisional         = is_provisional,
            status                 = GraduationCertificateStatus.ISSUED.value,
            issued_by              = actor.user_id,
            issued_at              = _now(),
        )
        await GraduationCertificateRepo.create(cert, db)

        candidate.certificate_status = CandidateCertificateStatus.ISSUED.value
        candidate.certificate_id     = cert.id
        candidate.updated_at         = _now()
        await db.flush()

        await PublicGraduationIndexRepo.upsert(
            certificate_number = cert_number,
            tenant_id          = actor.tenant_id,
            schema_name        = actor.schema_name or "",
            certificate_id     = cert.id,
            student_id         = candidate.student_id,
            is_provisional     = is_provisional,
            status             = GraduationCertificateStatus.ISSUED.value,
            graduation_year    = graduation_year,
            issued_at          = cert.issued_at,
            db                 = db,
        )

        await AuditService.log(
            AuditEventType.GRADUATION_CERTIFICATE_ISSUED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationCertificate",
            target_id=str(cert.id),
            metadata={
                "certificate_number": cert_number,
                "student_id":         str(candidate.student_id),
                "is_provisional":     is_provisional,
            },
        )
        return cert

    # ── Issue all ratified + un-issued certificates in a BOARD_APPROVED audit ─

    @staticmethod
    async def issue_all_certificates(
        audit_id: UUID,
        actor: CurrentUser,
        tenant_code: str,
        db: AsyncSession,
    ) -> list[SisGraduationCertificate]:
        audit = await GraduationAuditRepo.get_by_id(audit_id, db)
        if not audit or audit.status != GraduationAuditStatus.BOARD_APPROVED.value:
            raise ValueError("Batch issuance requires BOARD_APPROVED audit status")

        pending = await GraduationCandidateRepo.list_ratified_for_audit(audit_id, db)
        certs = []
        for candidate in pending:
            cert = await GraduationLifecycleService.issue_certificate(
                candidate.id, actor, tenant_code, db
            )
            certs.append(cert)

        if certs:
            audit.status                 = GraduationAuditStatus.CERTIFICATES_ISSUED.value
            audit.certificates_issued_by = actor.user_id
            audit.certificates_issued_at = _now()
            audit.updated_at             = _now()
            await db.flush()

        return certs

    # ── Confirm provisional → graduated ───────────────────────────────────────

    @staticmethod
    async def confirm_provisional(
        cert_id: UUID,
        data: ProvisionalConfirmIn,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationCertificate:
        cert = await GraduationCertificateRepo.get_by_id(cert_id, db)
        if not cert:
            raise ValueError("Certificate not found")
        if cert.status != GraduationCertificateStatus.ISSUED.value:
            raise ValueError("Only ISSUED certificates can be confirmed")
        if not cert.is_provisional:
            raise ValueError("This certificate is not provisional")
        if cert.provisional_confirmed_at:
            raise ValueError("Provisional status already confirmed for this certificate")

        cert.is_provisional              = False
        cert.provisional_confirmed_at    = _now()
        cert.provisional_confirmed_by    = actor.user_id
        cert.updated_at                  = _now()
        await db.flush()

        if cert.certificate_number:
            await PublicGraduationIndexRepo.update_status(
                cert.certificate_number, GraduationCertificateStatus.ISSUED.value, db
            )

        await AuditService.log(
            AuditEventType.GRADUATION_PROVISIONAL_CONFIRMED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationCertificate",
            target_id=str(cert_id),
            metadata={
                "certificate_number": cert.certificate_number,
                "notes_hash": hashlib.sha256(data.confirmation_notes.encode()).hexdigest()[:16],
            },
        )
        return cert

    # ── Revoke certificate ─────────────────────────────────────────────────────

    @staticmethod
    async def revoke_certificate(
        cert_id: UUID,
        data: CertificateRevokeIn,
        actor: CurrentUser,
        db: AsyncSession,
    ) -> SisGraduationCertificate:
        cert = await GraduationCertificateRepo.get_by_id(cert_id, db)
        if not cert:
            raise ValueError("Certificate not found")
        if cert.status == GraduationCertificateStatus.REVOKED.value:
            raise ValueError("Certificate is already revoked")

        cert.status        = GraduationCertificateStatus.REVOKED.value
        cert.revoked_by    = actor.user_id
        cert.revoked_at    = _now()
        cert.revoke_reason = data.revoke_reason
        cert.updated_at    = _now()
        await db.flush()

        candidate = await GraduationCandidateRepo.get_by_id(cert.candidate_id, db)
        if candidate:
            candidate.certificate_status = CandidateCertificateStatus.REVOKED.value
            candidate.updated_at         = _now()
            await db.flush()

        if cert.certificate_number:
            await PublicGraduationIndexRepo.update_status(
                cert.certificate_number, GraduationCertificateStatus.REVOKED.value, db
            )

        await AuditService.log(
            AuditEventType.GRADUATION_CERTIFICATE_REVOKED,
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            tenant_id=actor.tenant_id,
            schema_name=actor.schema_name,
            target_entity="SisGraduationCertificate",
            target_id=str(cert_id),
            metadata={
                "certificate_number": cert.certificate_number,
                "reason_hash": hashlib.sha256(data.revoke_reason.encode()).hexdigest()[:16],
            },
        )
        return cert


# ─────────────────────────────────────────────────────────────────────────────
# Student-facing graduation status
# ─────────────────────────────────────────────────────────────────────────────

class StudentGraduationService:

    @staticmethod
    async def my_status(
        student_id: UUID,
        db: AsyncSession,
    ) -> StudentGraduationStatusRead:
        candidate = await GraduationCandidateRepo.get_latest_for_student(student_id, db)

        from app.modules.m11_sis.models import SisStudentProfile
        profile = (await db.execute(
            select(SisStudentProfile).where(SisStudentProfile.user_id == student_id)
        )).scalar_one_or_none()
        usn = getattr(profile, "usn", None) if profile else None

        from app.core.auth.models import User
        user_row = (await db.execute(
            select(User).where(User.id == student_id)
        )).scalar_one_or_none()
        student_name = getattr(user_row, "full_name", None) or "Unknown" if user_row else "Unknown"

        if not candidate:
            return StudentGraduationStatusRead(
                student_id         = student_id,
                usn                = usn,
                student_name       = student_name,
                program_name       = None,
                eligibility_status = None,
                board_status       = None,
                certificate_status = None,
                certificate_number = None,
                graduation_year    = None,
                is_provisional     = None,
                message            = "No graduation audit has been initiated for your batch yet.",
            )

        cert = None
        if candidate.certificate_id:
            cert = await GraduationCertificateRepo.get_by_id(candidate.certificate_id, db)

        return StudentGraduationStatusRead(
            student_id         = student_id,
            usn                = usn,
            student_name       = student_name,
            program_name       = candidate.program_name_snapshot,
            eligibility_status = candidate.eligibility_status,
            board_status       = candidate.board_status,
            certificate_status = candidate.certificate_status,
            certificate_number = cert.certificate_number if cert else None,
            graduation_year    = cert.graduation_year if cert else None,
            is_provisional     = cert.is_provisional if cert else None,
            message            = _graduation_message(candidate, cert),
        )


def _graduation_message(
    candidate: SisGraduationCandidate,
    cert: Optional[SisGraduationCertificate],
) -> str:
    if candidate.certificate_status == CandidateCertificateStatus.REVOKED.value:
        return "Your graduation certificate has been revoked. Please contact the Registrar."
    if candidate.certificate_status == CandidateCertificateStatus.ISSUED.value:
        if cert and cert.is_provisional:
            return "Your provisional graduation certificate has been issued. Final confirmation is pending."
        return "Your graduation certificate has been issued."
    if candidate.board_status == CandidateBoardStatus.RATIFIED.value:
        return "Your graduation has been ratified by the Board. Certificate issuance is pending."
    if candidate.board_status == CandidateBoardStatus.DEFERRED.value:
        return "Your graduation decision has been deferred by the Board. Please contact the Registrar."
    if candidate.eligibility_status == CandidateEligibilityStatus.NOT_ELIGIBLE.value:
        return "You are currently not eligible for graduation. Please contact your department."
    if candidate.eligibility_status == CandidateEligibilityStatus.PROVISIONAL.value:
        return "Your eligibility is provisional. Please clear all pending requirements."
    return "Your graduation eligibility is under review."


# ─────────────────────────────────────────────────────────────────────────────
# Public Certificate Verification (no auth required)
# ─────────────────────────────────────────────────────────────────────────────

class GraduationVerifyService:
    """
    Verify a graduation certificate by number.
    Response MUST NEVER expose: CGPA, credits, eligibility flags, board notes.
    """

    @staticmethod
    async def verify(
        certificate_number: str,
        db: AsyncSession,
    ) -> CertificateVerifyResponse:
        await AuditService.log(
            AuditEventType.GRADUATION_CERTIFICATE_VERIFIED,
            actor_user_id=None,
            target_entity="graduation_certificate",
            target_id=certificate_number,
            metadata={"certificate_number": certificate_number},
        )

        index_row = await PublicGraduationIndexRepo.get_by_number(certificate_number, db)
        if not index_row:
            return CertificateVerifyResponse(
                certificate_number   = certificate_number,
                student_name_partial = "Unknown",
                programme_name       = None,
                institution_name     = None,
                graduation_year      = None,
                is_provisional       = False,
                status               = "NOT_FOUND",
                message              = "Certificate not found. Please verify the certificate number.",
            )

        schema_name = index_row.schema_name

        cert_result = await db.execute(
            text(
                f"SELECT student_name_snapshot, program_name_snapshot, "
                f"       graduation_year, is_provisional, status "
                f"FROM {schema_name}.sis_graduation_certificates "
                f"WHERE certificate_number = :cert_number"
            ).bindparams(cert_number=certificate_number)
        )
        row = cert_result.mappings().one_or_none()

        if not row:
            status_val = index_row.status or "ISSUED"
            msg = "Certificate status: REVOKED." if status_val == "REVOKED" else "Certificate verified."
            return CertificateVerifyResponse(
                certificate_number   = certificate_number,
                student_name_partial = "Unknown",
                programme_name       = None,
                institution_name     = None,
                graduation_year      = index_row.graduation_year,
                is_provisional       = index_row.is_provisional,
                status               = status_val,
                message              = msg,
            )

        status_val     = row["status"]
        is_provisional = row["is_provisional"]
        full_name      = row["student_name_snapshot"] or ""
        prog_name      = row["program_name_snapshot"]
        grad_year      = row["graduation_year"]

        if status_val == GraduationCertificateStatus.REVOKED.value:
            message = "This certificate has been revoked. Please contact the institution."
        elif is_provisional:
            message = "Provisional graduation certificate verified. Final confirmation pending."
        else:
            message = "Graduation certificate verified successfully."

        return CertificateVerifyResponse(
            certificate_number   = certificate_number,
            student_name_partial = _partial_name(full_name),
            programme_name       = prog_name,
            institution_name     = None,
            graduation_year      = grad_year,
            is_provisional       = is_provisional,
            status               = status_val,
            message              = message,
        )
