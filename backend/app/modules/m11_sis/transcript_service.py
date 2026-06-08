"""
SIS Transcript Generation — H61 Service layer.

Non-negotiable invariants:
  - Only LOCKED result declarations are included in a transcript snapshot.
  - Transcripts cannot be auto-issued; every issuance requires a human gate.
  - Issued transcripts are immutable; regeneration creates a new version.
  - Verification logs are append-only (no delete/update).
  - Public verify response never exposes marks or CGPA.
  - AI advises, humans decide — no autonomous degree conferral.
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
from app.modules.m11_sis.transcript_models import (
    DegreeStatus,
    SisTranscript,
    SisTranscriptSemesterLine,
    SisTranscriptSubjectLine,
    SisTranscriptVerificationLog,
    TranscriptStatus,
    TranscriptType,
    VerificationResult,
)
from app.modules.m11_sis.transcript_repository import (
    PublicTranscriptIndexRepo,
    TranscriptLinesRepo,
    TranscriptRepo,
    VerificationLogRepo,
)
from app.modules.m11_sis.transcript_schemas import (
    BacklogSubject,
    DegreeProgressRead,
    SemesterProgressRow,
    TranscriptVerifyResponse,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TranscriptServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Transcript lifecycle service
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptLifecycleService:

    @staticmethod
    async def request(
        student_id: UUID,
        transcript_type: str,
        purpose: Optional[str],
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> SisTranscript:
        # Guard: one active request per student
        if await TranscriptRepo.has_active_request(student_id, db):
            raise TranscriptServiceError(
                "ACTIVE_REQUEST_EXISTS",
                "Student already has a pending transcript request. "
                "Issue or revoke it before requesting a new one.",
                409,
            )

        # Load student name from users table
        u_row = (await db.execute(
            text("SELECT full_name FROM users WHERE id = :uid"),
            {"uid": str(student_id)},
        )).mappings().one_or_none()
        if not u_row:
            raise TranscriptServiceError("STUDENT_NOT_FOUND", "Student not found", 404)

        transcript = SisTranscript(
            id                    = uuid.uuid4(),
            student_id            = student_id,
            student_name_snapshot = u_row["full_name"],
            transcript_type       = transcript_type,
            purpose               = purpose,
            status                = TranscriptStatus.REQUESTED,
            version               = 1,
            requested_by          = actor_user_id,
            requested_at          = _now(),
            created_at            = _now(),
        )
        await TranscriptRepo.create(transcript, db)

        await AuditService.log(
            AuditEventType.TRANSCRIPT_REQUESTED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisTranscript",
            target_id=str(transcript.id),
            metadata={"student_id": str(student_id), "type": transcript_type},
        )
        return transcript

    @staticmethod
    async def dispatch_generate(
        transcript_id: UUID,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        tenant_code: str,
        db: AsyncSession,
    ) -> str:
        """Validate and dispatch the Celery PDF generation task. Returns celery task_id."""
        transcript = await TranscriptRepo.get_by_id(transcript_id, db)
        if not transcript:
            raise TranscriptServiceError("NOT_FOUND", "Transcript not found", 404)
        if transcript.status not in (TranscriptStatus.REQUESTED, TranscriptStatus.STALE):
            raise TranscriptServiceError(
                "INVALID_STATUS",
                f"Cannot generate a transcript with status '{transcript.status}'. "
                "Expected REQUESTED or STALE.",
                409,
            )

        # Check at least one LOCKED declaration exists for this student
        from app.modules.m11_sis.results_models import DeclarationStatus, SisResultDeclaration
        decl_result = await db.execute(
            select(SisResultDeclaration).where(
                SisResultDeclaration.status == DeclarationStatus.LOCKED.value,
            ).limit(1)
        )
        # Filter by student: check via semester_results
        from app.modules.m11_sis.results_models import SisSemesterResult
        sr_result = await db.execute(
            select(SisSemesterResult.declaration_id)
            .where(SisSemesterResult.student_id == transcript.student_id)
            .limit(1)
        )
        if not sr_result.scalar_one_or_none():
            raise TranscriptServiceError(
                "NO_RESULTS",
                "No semester results found for this student. "
                "Compute and lock result declarations first.",
                409,
            )

        from app.workers.heavy.generate_transcript_pdf import generate_transcript_pdf
        task = generate_transcript_pdf.delay(
            transcript_id=str(transcript_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
            actor_user_id=str(actor_user_id),
            actor_role=actor_role,
            tenant_code=tenant_code,
        )

        await AuditService.log(
            AuditEventType.TRANSCRIPT_GENERATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisTranscript",
            target_id=str(transcript_id),
            metadata={"celery_task_id": task.id, "status_before": transcript.status},
        )
        return task.id

    @staticmethod
    async def issue(
        transcript_id: UUID,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> SisTranscript:
        transcript = await TranscriptRepo.get_by_id(transcript_id, db)
        if not transcript:
            raise TranscriptServiceError("NOT_FOUND", "Transcript not found", 404)
        if transcript.status != TranscriptStatus.GENERATED:
            raise TranscriptServiceError(
                "INVALID_STATUS",
                f"Cannot issue a transcript with status '{transcript.status}'. "
                "Generate it first.",
                409,
            )

        now = _now()
        transcript.status    = TranscriptStatus.ISSUED
        transcript.issued_by = actor_user_id
        transcript.issued_at = now
        transcript.updated_at = now
        await db.flush()

        # Write to public index (enables QR verification)
        await PublicTranscriptIndexRepo.upsert(
            verification_code = transcript.verification_code,
            tenant_id         = tenant_id,
            schema_name       = schema_name,
            transcript_id     = transcript.id,
            transcript_number = transcript.transcript_number,
            status            = TranscriptStatus.ISSUED,
            issued_at         = now,
            db                = db,
        )

        await AuditService.log(
            AuditEventType.TRANSCRIPT_ISSUED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisTranscript",
            target_id=str(transcript_id),
            metadata={
                "transcript_number": transcript.transcript_number,
                "student_id":        str(transcript.student_id),
                "version":           transcript.version,
            },
        )
        return transcript

    @staticmethod
    async def revoke(
        transcript_id: UUID,
        revoke_reason: str,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> SisTranscript:
        transcript = await TranscriptRepo.get_by_id(transcript_id, db)
        if not transcript:
            raise TranscriptServiceError("NOT_FOUND", "Transcript not found", 404)
        if transcript.status != TranscriptStatus.ISSUED:
            raise TranscriptServiceError(
                "INVALID_STATUS",
                f"Only ISSUED transcripts can be revoked. Current status: '{transcript.status}'.",
                409,
            )

        now = _now()
        transcript.status       = TranscriptStatus.REVOKED
        transcript.revoked_by   = actor_user_id
        transcript.revoked_at   = now
        transcript.revoke_reason = revoke_reason
        transcript.updated_at   = now
        await db.flush()

        if transcript.verification_code:
            await PublicTranscriptIndexRepo.update_status(
                transcript.verification_code, TranscriptStatus.REVOKED, db
            )

        await AuditService.log(
            AuditEventType.TRANSCRIPT_REVOKED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisTranscript",
            target_id=str(transcript_id),
            metadata={
                "transcript_number": transcript.transcript_number,
                "revoke_reason_summary": revoke_reason[:100],
            },
        )
        return transcript

    @staticmethod
    async def regenerate(
        transcript_id: UUID,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> SisTranscript:
        """Supersede the current ISSUED transcript and create a new REQUESTED one."""
        old = await TranscriptRepo.get_by_id(transcript_id, db)
        if not old:
            raise TranscriptServiceError("NOT_FOUND", "Transcript not found", 404)
        if old.status != TranscriptStatus.ISSUED:
            raise TranscriptServiceError(
                "INVALID_STATUS",
                f"Only ISSUED transcripts can be regenerated. Current: '{old.status}'.",
                409,
            )

        now = _now()
        old.status     = TranscriptStatus.SUPERSEDED
        old.updated_at = now
        await db.flush()

        if old.verification_code:
            await PublicTranscriptIndexRepo.update_status(
                old.verification_code, TranscriptStatus.SUPERSEDED, db
            )

        new_transcript = SisTranscript(
            id                    = uuid.uuid4(),
            student_id            = old.student_id,
            student_name_snapshot = old.student_name_snapshot,
            transcript_type       = old.transcript_type,
            purpose               = old.purpose,
            status                = TranscriptStatus.REQUESTED,
            version               = old.version + 1,
            parent_transcript_id  = old.id,
            requested_by          = actor_user_id,
            requested_at          = now,
            created_at            = now,
        )
        await TranscriptRepo.create(new_transcript, db)

        await AuditService.log(
            AuditEventType.TRANSCRIPT_REGENERATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisTranscript",
            target_id=str(transcript_id),
            metadata={
                "old_transcript_id": str(transcript_id),
                "new_transcript_id": str(new_transcript.id),
                "new_version":       new_transcript.version,
            },
        )
        return new_transcript


# ─────────────────────────────────────────────────────────────────────────────
# Degree Progress Service
# ─────────────────────────────────────────────────────────────────────────────

class DegreeProgressService:

    @staticmethod
    async def get_progress(
        student_id: UUID,
        db: AsyncSession,
    ) -> DegreeProgressRead:
        from app.modules.m11_sis.results_models import (
            DeclarationStatus, SisResultDeclaration,
            SisSemesterResult, SisSubjectResult,
        )
        from app.modules.m_academics.models import AcadBatch, AcadProgram, AcadSemester

        # Load student profile
        u_row = (await db.execute(
            text("SELECT full_name FROM users WHERE id = :uid"),
            {"uid": str(student_id)},
        )).mappings().one_or_none()
        student_name = u_row["full_name"] if u_row else "Unknown"

        # Load student profile for USN
        from app.modules.m11_sis.models import SisStudentProfile
        profile_result = await db.execute(
            select(SisStudentProfile).where(SisStudentProfile.user_id == student_id)
        )
        profile = profile_result.scalar_one_or_none()
        usn = profile.usn if profile else None
        admission_year = profile.admission_year if profile else None

        # Load enrollment → program_id
        from app.modules.m_academics.models import AcadEnrollment
        enroll_result = await db.execute(
            select(AcadEnrollment).where(
                AcadEnrollment.student_id == student_id,
                AcadEnrollment.is_active.is_(True),
            ).limit(1)
        )
        enrollment = enroll_result.scalar_one_or_none()

        program_name     = None
        program_obj      = None
        batch_obj        = None
        min_credits      = None
        expected_grad_yr = None

        if enrollment:
            from app.modules.m_academics.models import AcadSection
            section = await db.get(AcadSection, enrollment.section_id)
            if section:
                semester = await db.get(AcadSemester, section.semester_id)
                if semester:
                    batch_obj = await db.get(AcadBatch, semester.batch_id)
                    if batch_obj:
                        program_obj = await db.get(AcadProgram, batch_obj.program_id)
                        if program_obj:
                            program_name = program_obj.name
                            min_credits  = getattr(program_obj, "min_credits_for_degree", None)
                        if admission_year and batch_obj:
                            # Approximate expected graduation from batch end year
                            batch_name = batch_obj.name or ""
                            parts = batch_name.replace("–", "-").split("-")
                            if len(parts) == 2 and parts[1].strip().isdigit():
                                expected_grad_yr = int(parts[1].strip())
                            elif admission_year:
                                duration = int(getattr(program_obj, "duration_years", 4) or 4) if program_obj else 4
                                expected_grad_yr = admission_year + duration

        # Load all LOCKED semester results for student
        sr_result = await db.execute(
            select(SisSemesterResult)
            .where(SisSemesterResult.student_id == student_id)
            .order_by(SisSemesterResult.computed_at)
        )
        semester_results = list(sr_result.scalars().all())

        # Correlate with declarations to confirm LOCKED status
        locked_declaration_ids: set[UUID] = set()
        for sr in semester_results:
            decl = await db.get(SisResultDeclaration, sr.declaration_id)
            if decl and decl.status == DeclarationStatus.LOCKED.value:
                locked_declaration_ids.add(sr.declaration_id)

        valid_semester_results = [
            sr for sr in semester_results if sr.declaration_id in locked_declaration_ids
        ]

        # Build semester summaries
        semester_rows: list[SemesterProgressRow] = []
        total_credits_attempted = Decimal("0")
        total_credits_earned    = Decimal("0")
        latest_cgpa             = None

        for sr in valid_semester_results:
            sem = await db.get(AcadSemester, sr.semester_id) if sr.semester_id else None
            decl = await db.get(SisResultDeclaration, sr.declaration_id)
            row = SemesterProgressRow(
                semester_number       = sem.semester_number if sem else None,
                semester_name         = decl.snapshot_semester_name if decl else None,
                academic_year         = decl.snapshot_academic_year if decl else None,
                sgpa                  = sr.sgpa,
                cgpa                  = sr.cgpa,
                credits_attempted     = sr.total_credits_attempted,
                credits_earned        = sr.total_credits_earned,
                overall_result_status = sr.overall_result_status,
            )
            semester_rows.append(row)
            total_credits_attempted += Decimal(str(sr.total_credits_attempted or 0))
            total_credits_earned    += Decimal(str(sr.total_credits_earned    or 0))
            if sr.cgpa is not None:
                latest_cgpa = sr.cgpa

        # Sort by semester number
        semester_rows.sort(key=lambda r: (r.semester_number or 0))

        # Compute arrears (active backlogs)
        # For each (student_id, course_id) pair: arrear if best result_status != PASS
        sub_result = await db.execute(
            select(SisSubjectResult)
            .where(
                SisSubjectResult.student_id == student_id,
                SisSubjectResult.declaration_id.in_(locked_declaration_ids),
            )
            .order_by(SisSubjectResult.course_id, SisSubjectResult.attempt_number)
        )
        all_subject_results = list(sub_result.scalars().all())

        # Group by course_id — find best (latest PASS or latest attempt)
        from collections import defaultdict
        by_course: dict[UUID, list[SisSubjectResult]] = defaultdict(list)
        for subr in all_subject_results:
            by_course[subr.course_id].append(subr)

        active_backlogs: list[BacklogSubject] = []
        for course_id, results in by_course.items():
            results_sorted = sorted(results, key=lambda r: r.attempt_number)
            has_pass = any(r.result_status == "PASS" for r in results_sorted)
            if not has_pass:
                latest = results_sorted[-1]
                from app.modules.m01_program_advisor.models import Course
                course_obj = await db.get(Course, course_id)
                # Get semester snapshot from first result's declaration
                first_decl = await db.get(SisResultDeclaration, results_sorted[0].declaration_id)
                active_backlogs.append(BacklogSubject(
                    course_id   = str(course_id),
                    course_code = course_obj.code if course_obj else None,
                    course_name = course_obj.title if course_obj else None,
                    semester    = first_decl.snapshot_semester_name if first_decl else None,
                    grade       = latest.grade_letter,
                    attempts    = len(results_sorted),
                ))

        arrear_count = len(active_backlogs)

        # Compute degree status
        any_withheld = any(
            sr.overall_result_status in ("WITHHELD", "FAIL")
            for sr in valid_semester_results
        )
        credits_ok = (
            min_credits is not None and total_credits_earned >= Decimal(str(min_credits))
        ) if min_credits else True  # If not configured, don't block

        if not valid_semester_results:
            degree_status = DegreeStatus.PROVISIONAL
        elif any_withheld or arrear_count > 0:
            degree_status = DegreeStatus.NOT_ELIGIBLE
        elif not credits_ok:
            degree_status = DegreeStatus.NOT_ELIGIBLE
        else:
            # Check if all required semesters are declared (need program config)
            degree_status = DegreeStatus.ELIGIBLE

        # Is final semester declared?
        is_final = len(valid_semester_results) > 0 and (
            semester_rows[-1].overall_result_status in ("PASS", "FAIL", "WITHHELD")
            if semester_rows else False
        )

        return DegreeProgressRead(
            student_id                 = student_id,
            usn                        = usn,
            student_name               = student_name,
            program_name               = program_name,
            expected_graduation_year   = expected_grad_yr,
            total_semesters_declared   = len(valid_semester_results),
            total_credits_attempted    = total_credits_attempted,
            total_credits_earned       = total_credits_earned,
            min_credits_for_degree     = Decimal(str(min_credits)) if min_credits else None,
            current_cgpa               = Decimal(str(latest_cgpa)) if latest_cgpa else None,
            arrear_count               = arrear_count,
            active_backlogs            = active_backlogs,
            degree_status              = degree_status.value,
            is_final_semester_declared = is_final,
            semesters                  = semester_rows,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Public Verification Service
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptVerifyService:

    @staticmethod
    async def verify(
        code_str: str,
        requester_ip: Optional[str],
        requester_context: Optional[str],
        db: AsyncSession,   # platform DB (public schema)
    ) -> TranscriptVerifyResponse:
        """
        1. Lookup public.public_transcript_index.
        2. Open tenant session to get full transcript details.
        3. Log verification attempt (fire-and-forget).
        4. Return limited public response.
        """
        # Parse code
        try:
            code_uuid = uuid.UUID(code_str)
        except ValueError:
            return TranscriptVerifyResponse(
                verification_code    = code_str,
                transcript_number    = None,
                student_name_partial = "Unknown",
                program_name         = None,
                institution_name     = None,
                degree_status        = None,
                issued_at            = None,
                status               = VerificationResult.NOT_FOUND,
                is_provisional       = False,
                message              = "Verification code not found.",
            )

        ip_hash = (
            hashlib.sha256(requester_ip.encode()).hexdigest()[:16]
            if requester_ip else None
        )

        # Look up in public index
        index_entry = await PublicTranscriptIndexRepo.get_by_code(code_uuid, db)
        if not index_entry:
            return TranscriptVerifyResponse(
                verification_code    = code_str,
                transcript_number    = None,
                student_name_partial = "Unknown",
                program_name         = None,
                institution_name     = None,
                degree_status        = None,
                issued_at            = None,
                status               = VerificationResult.NOT_FOUND,
                is_provisional       = False,
                message              = "Transcript not found. "
                                       "Verify the code is correct and the transcript has been issued.",
            )

        # Map status to verification result
        vr_map = {
            "ISSUED":     VerificationResult.VALID,
            "REVOKED":    VerificationResult.REVOKED,
            "SUPERSEDED": VerificationResult.SUPERSEDED,
        }
        verify_result = vr_map.get(index_entry.status, VerificationResult.NOT_FOUND)

        # Open tenant session to get transcript details
        transcript_data = await TranscriptVerifyService._load_tenant_transcript(
            schema_name=index_entry.schema_name,
            verification_code=code_uuid,
        )

        # Log verification (fire-and-forget — never blocks response)
        try:
            await TranscriptVerifyService._log_verification(
                schema_name=index_entry.schema_name,
                transcript_id=index_entry.transcript_id,
                code_str=code_str,
                ip_hash=ip_hash,
                context=requester_context or "API",
                result=verify_result.value,
            )
        except Exception:
            pass

        # Build limited public response
        if not transcript_data:
            return TranscriptVerifyResponse(
                verification_code    = code_str,
                transcript_number    = index_entry.transcript_number,
                student_name_partial = "—",
                program_name         = None,
                institution_name     = None,
                degree_status        = None,
                issued_at            = index_entry.issued_at,
                status               = verify_result.value,
                is_provisional       = False,
                message              = _verify_message(verify_result),
            )

        name_partial = _partial_name(transcript_data.get("student_name_snapshot", ""))
        is_provisional = (
            transcript_data.get("transcript_type") == TranscriptType.PROVISIONAL
        )

        return TranscriptVerifyResponse(
            verification_code    = code_str,
            transcript_number    = transcript_data.get("transcript_number"),
            student_name_partial = name_partial,
            program_name         = transcript_data.get("program_name_snapshot"),
            institution_name     = transcript_data.get("institution_name"),
            degree_status        = transcript_data.get("degree_status_snapshot"),
            issued_at            = transcript_data.get("issued_at"),
            status               = verify_result.value,
            is_provisional       = is_provisional,
            message              = _verify_message(verify_result),
        )

    @staticmethod
    async def _load_tenant_transcript(
        schema_name: str,
        verification_code: UUID,
    ) -> Optional[dict]:
        from app.database import get_tenant_db
        try:
            async for tenant_db in get_tenant_db(schema_name):
                row = (await tenant_db.execute(
                    text("""
                        SELECT t.student_name_snapshot, t.program_name_snapshot,
                               t.transcript_number, t.transcript_type,
                               t.degree_status_snapshot, t.issued_at,
                               ten.name AS institution_name
                        FROM sis_transcripts t
                        LEFT JOIN public.tenants ten ON ten.schema_name = :schema
                        WHERE t.verification_code = :code
                        LIMIT 1
                    """),
                    {"code": str(verification_code), "schema": schema_name},
                )).mappings().one_or_none()
                if row:
                    return dict(row)
        except Exception:
            pass
        return None

    @staticmethod
    async def _log_verification(
        schema_name: str,
        transcript_id: UUID,
        code_str: str,
        ip_hash: Optional[str],
        context: str,
        result: str,
    ) -> None:
        from app.database import get_tenant_db
        try:
            async for tenant_db in get_tenant_db(schema_name):
                entry = SisTranscriptVerificationLog(
                    id                  = uuid.uuid4(),
                    transcript_id       = transcript_id,
                    verification_code   = code_str,
                    verified_at         = _now(),
                    requester_ip_hash   = ip_hash,
                    requester_context   = context,
                    verification_result = result,
                    created_at          = _now(),
                )
                await VerificationLogRepo.append(entry, tenant_db)
                await tenant_db.commit()
                break
        except Exception:
            pass


def _partial_name(full_name: str) -> str:
    """Return 'Firstname L.' for privacy."""
    parts = full_name.strip().split()
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


def _verify_message(result: VerificationResult) -> str:
    messages = {
        VerificationResult.VALID:      "This transcript is valid and was officially issued.",
        VerificationResult.REVOKED:    "This transcript has been revoked by the issuing institution.",
        VerificationResult.SUPERSEDED: "A newer version of this transcript has been issued. "
                                        "Please request the latest copy from the institution.",
        VerificationResult.NOT_FOUND:  "Transcript not found. Verify the QR code is correct.",
    }
    return messages.get(result, "Verification status unknown.")
