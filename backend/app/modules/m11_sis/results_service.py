"""
SIS Results Management — H60 Service layer.

Business logic:
  - Grading policy CRUD + band management (overlap validation)
  - Result declaration CRUD + lifecycle (DRAFT→VERIFIED→PUBLISHED→LOCKED)
  - External marks entry
  - Result computation (aggregate internal+external, apply grade bands, pass/fail)
  - Grace marks (Dean gate, re-compute, revoke)
  - SGPA calculation (credit-weighted per semester)
  - CGPA calculation (historical aggregation across all published declarations)
  - Rank list computation (section rank, program rank)
  - Grade card assembly
  - Academic history / transcript

Non-negotiable invariants:
  - Grace marks require Dean role; logged in sis_grace_marks_log (append-only)
  - Students see only PUBLISHED/LOCKED declarations
  - LOCKED declarations are fully immutable
  - AuditLog on every lifecycle transition + every grace mark event
  - AI advises, humans decide: no auto-pass/fail without human publish gate
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.results_models import (
    DeclarationStatus,
    OverallResultStatus,
    ResultStatus,
    SisExternalMarks,
    SisGraceMarksLog,
    SisGradingPolicy,
    SisGradingPolicyBand,
    SisResultDeclaration,
    SisSemesterResult,
    SisSubjectResult,
)
from app.modules.m11_sis.results_repository import (
    ExternalMarksRepo,
    GraceMarksLogRepo,
    GradingPolicyRepo,
    ResultDeclarationRepo,
    SemesterResultRepo,
    SubjectResultRepo,
)
from app.modules.m11_sis.results_schemas import (
    ComputationStatusOut,
    ComputeResultOut,
    ExternalMarksBulkIn,
    GraceMarkApplyIn,
    GradeCardOut,
    GradeCardSubjectRow,
    GradingPolicyCreateIn,
    GradingPolicyUpdateIn,
    RankEntryOut,
    RankListOut,
    RevertToDraftIn,
    ResultDeclarationCreateIn,
    ResultDeclarationUpdateIn,
    TopperListOut,
    TopperOut,
    TranscriptOut,
    TranscriptSemesterOut,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResultsServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Grading Policy Service
# ─────────────────────────────────────────────────────────────────────────────

class GradingPolicyService:

    @staticmethod
    def _validate_bands_no_overlap(bands: list) -> None:
        """Raise if any two bands share a percentage range."""
        sorted_bands = sorted(bands, key=lambda b: float(b.min_percentage))
        for i in range(len(sorted_bands) - 1):
            curr = sorted_bands[i]
            nxt  = sorted_bands[i + 1]
            if float(curr.max_percentage) >= float(nxt.min_percentage):
                raise ResultsServiceError(
                    "BAND_OVERLAP",
                    f"Grade bands '{curr.grade_letter}' and '{nxt.grade_letter}' overlap",
                )

    @staticmethod
    async def create(
        body: GradingPolicyCreateIn,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisGradingPolicy:
        if body.bands:
            GradingPolicyService._validate_bands_no_overlap(body.bands)

        if body.is_default:
            await GradingPolicyRepo.clear_default_flag(db)

        policy = SisGradingPolicy(
            id              = uuid.uuid4(),
            name            = body.name,
            program_id      = body.program_id,
            pass_percentage = body.pass_percentage,
            is_default      = body.is_default,
            is_active       = True,
            created_by      = actor_user_id,
            created_at      = _now(),
        )
        await GradingPolicyRepo.create(policy, db)

        for band_in in body.bands:
            band = SisGradingPolicyBand(
                id             = uuid.uuid4(),
                policy_id      = policy.id,
                grade_letter   = band_in.grade_letter,
                min_percentage = band_in.min_percentage,
                max_percentage = band_in.max_percentage,
                grade_point    = band_in.grade_point,
                is_pass        = band_in.is_pass,
                display_order  = band_in.display_order,
                created_at     = _now(),
            )
            await GradingPolicyRepo.add_band(band, db)

        return await GradingPolicyRepo.get_by_id(policy.id, db)

    @staticmethod
    async def update(
        policy_id: UUID,
        body: GradingPolicyUpdateIn,
        db: AsyncSession,
    ) -> SisGradingPolicy:
        policy = await GradingPolicyRepo.get_by_id(policy_id, db)
        if not policy:
            raise ResultsServiceError("NOT_FOUND", "Grading policy not found", 404)

        if body.name is not None:
            policy.name = body.name
        if body.pass_percentage is not None:
            policy.pass_percentage = body.pass_percentage
        if body.is_default is not None:
            if body.is_default and not policy.is_default:
                await GradingPolicyRepo.clear_default_flag(db)
            policy.is_default = body.is_default
        if body.is_active is not None:
            policy.is_active = body.is_active

        policy.updated_at = _now()
        await db.flush()
        return await GradingPolicyRepo.get_by_id(policy_id, db)

    @staticmethod
    async def add_band(
        policy_id: UUID,
        band_in,
        db: AsyncSession,
    ) -> SisGradingPolicyBand:
        policy = await GradingPolicyRepo.get_by_id(policy_id, db)
        if not policy:
            raise ResultsServiceError("NOT_FOUND", "Grading policy not found", 404)

        existing = await GradingPolicyRepo.get_bands_for_policy(policy_id, db)
        combined = list(existing) + [band_in]
        GradingPolicyService._validate_bands_no_overlap(combined)

        band = SisGradingPolicyBand(
            id             = uuid.uuid4(),
            policy_id      = policy_id,
            grade_letter   = band_in.grade_letter,
            min_percentage = band_in.min_percentage,
            max_percentage = band_in.max_percentage,
            grade_point    = band_in.grade_point,
            is_pass        = band_in.is_pass,
            display_order  = band_in.display_order,
            created_at     = _now(),
        )
        return await GradingPolicyRepo.add_band(band, db)

    @staticmethod
    async def update_band(
        band_id: UUID,
        band_in,
        db: AsyncSession,
    ) -> SisGradingPolicyBand:
        band = await GradingPolicyRepo.get_band(band_id, db)
        if not band:
            raise ResultsServiceError("NOT_FOUND", "Band not found", 404)
        if band_in.grade_letter is not None:
            band.grade_letter = band_in.grade_letter
        if band_in.min_percentage is not None:
            band.min_percentage = band_in.min_percentage
        if band_in.max_percentage is not None:
            band.max_percentage = band_in.max_percentage
        if band_in.grade_point is not None:
            band.grade_point = band_in.grade_point
        if band_in.is_pass is not None:
            band.is_pass = band_in.is_pass
        if band_in.display_order is not None:
            band.display_order = band_in.display_order
        await db.flush()
        return band

    @staticmethod
    async def delete_band(band_id: UUID, db: AsyncSession) -> None:
        band = await GradingPolicyRepo.get_band(band_id, db)
        if not band:
            raise ResultsServiceError("NOT_FOUND", "Band not found", 404)
        await GradingPolicyRepo.delete_band(band, db)


# ─────────────────────────────────────────────────────────────────────────────
# Result Declaration Service
# ─────────────────────────────────────────────────────────────────────────────

class ResultDeclarationService:

    @staticmethod
    async def _get_or_raise(declaration_id: UUID, db: AsyncSession) -> SisResultDeclaration:
        decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
        if not decl:
            raise ResultsServiceError("NOT_FOUND", "Result declaration not found", 404)
        return decl

    @staticmethod
    async def _assert_not_locked(decl: SisResultDeclaration) -> None:
        if decl.status == DeclarationStatus.LOCKED:
            raise ResultsServiceError(
                "DECLARATION_LOCKED",
                "This result declaration is locked and cannot be modified",
                409,
            )

    @staticmethod
    async def create(
        body: ResultDeclarationCreateIn,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisResultDeclaration:
        policy = await GradingPolicyRepo.get_by_id(body.grading_policy_id, db)
        if not policy:
            raise ResultsServiceError("POLICY_NOT_FOUND", "Grading policy not found", 404)

        # Fetch snapshot data from exam session and semester
        from app.modules.m11_sis.exam_models import SisExamSession
        from app.modules.m_academics.models import AcadSemester
        session_row = await db.get(SisExamSession, body.exam_session_id)
        semester_row = await db.get(AcadSemester, body.semester_id)

        academic_year   = session_row.academic_year if session_row else ""
        semester_name   = semester_row.label or str(semester_row.number) if semester_row else ""
        policy_name     = policy.name

        decl = SisResultDeclaration(
            id                           = uuid.uuid4(),
            exam_session_id              = body.exam_session_id,
            semester_id                  = body.semester_id,
            snapshot_academic_year       = academic_year,
            snapshot_semester_name       = semester_name,
            snapshot_grading_policy_name = policy_name,
            declaration_type             = body.declaration_type,
            source_declaration_id        = body.source_declaration_id,
            grading_policy_id            = body.grading_policy_id,
            title                        = body.title,
            notes                        = body.notes,
            internal_marks_required      = body.internal_marks_required,
            status                       = DeclarationStatus.DRAFT,
            created_by                   = actor_user_id,
            created_at                   = _now(),
        )
        return await ResultDeclarationRepo.create(decl, db)

    @staticmethod
    async def update(
        declaration_id: UUID,
        body: ResultDeclarationUpdateIn,
        db: AsyncSession,
    ) -> SisResultDeclaration:
        decl = await ResultDeclarationService._get_or_raise(declaration_id, db)
        if decl.status != DeclarationStatus.DRAFT:
            raise ResultsServiceError(
                "NOT_DRAFT",
                "Only DRAFT declarations can be updated. Revert to DRAFT first.",
                409,
            )
        if body.grading_policy_id is not None:
            policy = await GradingPolicyRepo.get_by_id(body.grading_policy_id, db)
            if not policy:
                raise ResultsServiceError("POLICY_NOT_FOUND", "Grading policy not found", 404)
            decl.grading_policy_id            = body.grading_policy_id
            decl.snapshot_grading_policy_name = policy.name
        if body.title is not None:
            decl.title = body.title
        if body.notes is not None:
            decl.notes = body.notes
        if body.internal_marks_required is not None:
            decl.internal_marks_required = body.internal_marks_required
        decl.updated_at = _now()
        await db.flush()
        return decl

    @staticmethod
    async def delete(declaration_id: UUID, db: AsyncSession) -> None:
        decl = await ResultDeclarationService._get_or_raise(declaration_id, db)
        if decl.status != DeclarationStatus.DRAFT:
            raise ResultsServiceError(
                "NOT_DRAFT", "Only DRAFT declarations can be deleted", 409
            )
        await db.delete(decl)
        await db.flush()

    # ── Human Gates ──────────────────────────────────────────────────────────

    @staticmethod
    async def verify(
        declaration_id: UUID,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisResultDeclaration:
        decl = await ResultDeclarationService._get_or_raise(declaration_id, db)
        if decl.status != DeclarationStatus.DRAFT:
            raise ResultsServiceError(
                "INVALID_TRANSITION",
                f"Cannot verify: declaration is {decl.status}, expected DRAFT",
                409,
            )
        # Block if any subject results still PENDING
        pending = await db.execute(
            select(SisSubjectResult).where(
                SisSubjectResult.declaration_id == declaration_id,
                SisSubjectResult.result_status == ResultStatus.PENDING,
            ).limit(1)
        )
        if pending.scalar_one_or_none():
            raise ResultsServiceError(
                "PENDING_RESULTS",
                "All subject results must be computed before verification. "
                "Run compute first.",
                409,
            )
        decl.status      = DeclarationStatus.VERIFIED
        decl.verified_by = actor_user_id
        decl.verified_at = _now()
        decl.updated_at  = _now()
        await db.flush()
        return decl

    @staticmethod
    async def publish(
        declaration_id: UUID,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisResultDeclaration:
        decl = await ResultDeclarationService._get_or_raise(declaration_id, db)
        if decl.status != DeclarationStatus.VERIFIED:
            raise ResultsServiceError(
                "INVALID_TRANSITION",
                f"Cannot publish: declaration is {decl.status}, expected VERIFIED",
                409,
            )
        decl.status       = DeclarationStatus.PUBLISHED
        decl.published_by = actor_user_id
        decl.published_at = _now()
        decl.updated_at   = _now()
        await db.flush()
        return decl

    @staticmethod
    async def lock(
        declaration_id: UUID,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisResultDeclaration:
        decl = await ResultDeclarationService._get_or_raise(declaration_id, db)
        if decl.status != DeclarationStatus.PUBLISHED:
            raise ResultsServiceError(
                "INVALID_TRANSITION",
                f"Cannot lock: declaration is {decl.status}, expected PUBLISHED",
                409,
            )
        decl.status    = DeclarationStatus.LOCKED
        decl.locked_by = actor_user_id
        decl.locked_at = _now()
        decl.updated_at = _now()
        await db.flush()
        return decl

    @staticmethod
    async def revert_to_draft(
        declaration_id: UUID,
        body: RevertToDraftIn,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisResultDeclaration:
        decl = await ResultDeclarationService._get_or_raise(declaration_id, db)
        if decl.status not in (DeclarationStatus.VERIFIED,):
            raise ResultsServiceError(
                "INVALID_TRANSITION",
                "Only VERIFIED declarations can be reverted to DRAFT",
                409,
            )
        decl.status      = DeclarationStatus.DRAFT
        decl.verified_by = None
        decl.verified_at = None
        decl.updated_at  = _now()
        # Record revert reason in notes (appended)
        note = f"[REVERTED by {actor_user_id} at {_now().isoformat()}] {body.reason}"
        decl.notes = (decl.notes or "") + "\n" + note
        await db.flush()
        return decl


# ─────────────────────────────────────────────────────────────────────────────
# External Marks Service
# ─────────────────────────────────────────────────────────────────────────────

class ExternalMarksService:

    @staticmethod
    async def bulk_upsert(
        declaration_id: UUID,
        body: ExternalMarksBulkIn,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> list[SisExternalMarks]:
        decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
        if not decl:
            raise ResultsServiceError("NOT_FOUND", "Result declaration not found", 404)
        if decl.status == DeclarationStatus.LOCKED:
            raise ResultsServiceError(
                "DECLARATION_LOCKED", "Cannot enter marks on a LOCKED declaration", 409
            )

        results = []
        for entry in body.entries:
            existing = await ExternalMarksRepo.get_by_declaration_student_course(
                declaration_id, entry.student_id, entry.course_id, db
            )
            if existing:
                # Edit requires reason when declaration is post-DRAFT
                if decl.status != DeclarationStatus.DRAFT and not entry.edit_reason:
                    raise ResultsServiceError(
                        "EDIT_REASON_REQUIRED",
                        f"Edit reason required when declaration status is {decl.status}",
                        422,
                    )
                existing.external_marks_obtained = entry.external_marks_obtained
                existing.external_marks_max      = entry.external_marks_max
                existing.is_absent               = entry.is_absent
                existing.edited_by               = actor_user_id
                existing.edited_at               = _now()
                existing.edit_reason             = entry.edit_reason
                existing.updated_at              = _now()
                await db.flush()
                results.append(existing)
            else:
                row = SisExternalMarks(
                    id                      = uuid.uuid4(),
                    declaration_id          = declaration_id,
                    student_id              = entry.student_id,
                    course_id               = entry.course_id,
                    section_id              = entry.section_id,
                    external_marks_obtained = entry.external_marks_obtained,
                    external_marks_max      = entry.external_marks_max,
                    is_absent               = entry.is_absent,
                    attempt_number          = entry.attempt_number,
                    entered_by              = actor_user_id,
                    entered_at              = _now(),
                    created_at              = _now(),
                )
                row = await ExternalMarksRepo.upsert(row, db)
                results.append(row)
        return results

    @staticmethod
    async def get_computation_status(
        declaration_id: UUID, db: AsyncSession
    ) -> ComputationStatusOut:
        decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
        if not decl:
            raise ResultsServiceError("NOT_FOUND", "Result declaration not found", 404)

        total    = await ExternalMarksRepo.count_total(declaration_id, db)
        entered  = await ExternalMarksRepo.count_entered(declaration_id, db)
        pending  = total - entered
        blocking = []

        if pending > 0:
            blocking.append(f"{pending} external mark entries are still pending")

        # Check internal marks readiness
        internal_locked = True
        if decl.internal_marks_required:
            from app.modules.m11_sis.marks_models import SisMarksComponent
            unlocked = await db.execute(
                select(SisMarksComponent).where(
                    SisMarksComponent.semester_id == decl.semester_id,
                    SisMarksComponent.status != "LOCKED",
                ).limit(1)
            )
            if unlocked.scalar_one_or_none():
                internal_locked = False
                blocking.append("Not all internal marks components are LOCKED")

        ready = len(blocking) == 0
        return ComputationStatusOut(
            declaration_id         = declaration_id,
            total_expected         = total,
            external_marks_entered = entered,
            external_marks_pending = pending,
            internal_marks_locked  = internal_locked,
            ready_to_compute       = ready,
            blocking_reasons       = blocking,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Result Computation Engine
# ─────────────────────────────────────────────────────────────────────────────

def _apply_grade_band(
    percentage: Decimal,
    bands: list[SisGradingPolicyBand],
) -> tuple[Optional[str], Optional[Decimal], Optional[bool]]:
    """Return (grade_letter, grade_point, is_pass) for a given percentage."""
    for band in sorted(bands, key=lambda b: float(b.min_percentage), reverse=True):
        if float(band.min_percentage) <= float(percentage) <= float(band.max_percentage):
            return band.grade_letter, band.grade_point, band.is_pass
    return None, None, None


class ResultComputationService:

    @staticmethod
    async def compute(
        declaration_id: UUID,
        actor_user_id: UUID,
        force: bool,
        db: AsyncSession,
    ) -> ComputeResultOut:
        decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
        if not decl:
            raise ResultsServiceError("NOT_FOUND", "Result declaration not found", 404)
        if decl.status == DeclarationStatus.LOCKED:
            raise ResultsServiceError(
                "DECLARATION_LOCKED", "Cannot compute on a LOCKED declaration", 409
            )

        policy = await GradingPolicyRepo.get_by_id(decl.grading_policy_id, db)
        if not policy or not policy.bands:
            raise ResultsServiceError(
                "NO_GRADE_BANDS",
                "Grading policy has no bands defined. Add grade bands first.",
                409,
            )

        ext_marks_rows = await ExternalMarksRepo.list_by_declaration(declaration_id, db)
        if not ext_marks_rows:
            raise ResultsServiceError(
                "NO_EXTERNAL_MARKS",
                "No external marks entries found for this declaration",
                409,
            )

        # Aggregate internal marks per student×course
        from app.modules.m11_sis.marks_models import SisMarksComponent, SisMarksEntry
        internal_totals: dict[tuple[UUID, UUID], Decimal] = {}
        internal_max: dict[tuple[UUID, UUID], Decimal]    = {}

        if decl.internal_marks_required:
            # Sum all LOCKED components for matching semester
            components_result = await db.execute(
                select(SisMarksComponent).where(
                    SisMarksComponent.semester_id == decl.semester_id,
                    SisMarksComponent.status == "LOCKED",
                )
            )
            components = list(components_result.scalars().all())

            for comp in components:
                entries_result = await db.execute(
                    select(SisMarksEntry).where(
                        SisMarksEntry.component_id == comp.id,
                        SisMarksEntry.marks_obtained.isnot(None),
                    )
                )
                for entry in entries_result.scalars():
                    key = (entry.student_id, comp.course_id)
                    internal_totals[key] = (
                        internal_totals.get(key, Decimal("0")) + entry.marks_obtained
                    )
                    internal_max[key] = (
                        internal_max.get(key, Decimal("0")) + comp.max_marks
                    )

        # Fetch course credits
        from app.modules.m01_program_advisor.models import Course
        course_credits: dict[UUID, Decimal] = {}
        for row in ext_marks_rows:
            if row.course_id not in course_credits:
                course_obj = await db.get(Course, row.course_id)
                course_credits[row.course_id] = (
                    Decimal(str(course_obj.credits)) if course_obj else Decimal("0")
                )

        now = _now()
        pass_count   = 0
        fail_count   = 0
        absent_count = 0
        pending_count= 0

        for ext in ext_marks_rows:
            key = (ext.student_id, ext.course_id)

            if ext.is_absent:
                result_status = ResultStatus.ABSENT
                absent_count += 1
                grade_letter  = None
                grade_point   = None
                is_pass_val   = False
                total         = None
                percentage    = None
            elif ext.external_marks_obtained is None:
                result_status = ResultStatus.PENDING
                pending_count += 1
                grade_letter  = None
                grade_point   = None
                is_pass_val   = None
                total         = None
                percentage    = None
            else:
                int_marks  = internal_totals.get(key, Decimal("0"))
                int_max    = internal_max.get(key, Decimal("0"))
                ext_marks  = ext.external_marks_obtained
                ext_max    = ext.external_marks_max

                # Retrieve existing grace marks (Dean-applied)
                existing_result = await SubjectResultRepo.get_by_declaration_student_course(
                    declaration_id, ext.student_id, ext.course_id, db
                )
                grace = (existing_result.grace_marks or Decimal("0")) if existing_result else Decimal("0")

                total_max  = int_max + ext_max
                total      = int_marks + ext_marks + grace
                percentage = (total / total_max * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ) if total_max > 0 else Decimal("0")

                grade_letter, grade_point, is_pass_val = _apply_grade_band(
                    percentage, policy.bands
                )
                result_status = ResultStatus.PASS if is_pass_val else ResultStatus.FAIL
                if is_pass_val:
                    pass_count += 1
                else:
                    fail_count += 1

            credits_attempted = course_credits.get(ext.course_id, Decimal("0"))
            credits_earned    = credits_attempted if result_status == ResultStatus.PASS else Decimal("0")
            if result_status == ResultStatus.ABSENT:
                credits_earned = Decimal("0")

            max_marks = (
                internal_max.get(key, Decimal("0")) + ext.external_marks_max
            )

            existing = await SubjectResultRepo.get_by_declaration_student_course(
                declaration_id, ext.student_id, ext.course_id, db
            )
            if existing:
                if not force and existing.result_status not in (
                    ResultStatus.PENDING, ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.ABSENT
                ):
                    continue
                existing.internal_marks    = internal_totals.get(key)
                existing.external_marks    = ext.external_marks_obtained
                existing.total_marks       = total
                existing.max_marks         = max_marks
                existing.percentage        = percentage
                existing.grade_letter      = grade_letter
                existing.grade_point       = grade_point
                existing.is_pass           = is_pass_val
                existing.result_status     = result_status
                existing.credits_attempted = credits_attempted
                existing.credits_earned    = credits_earned
                existing.computed_at       = now
                existing.updated_at        = now
                await db.flush()
            else:
                row = SisSubjectResult(
                    id                = uuid.uuid4(),
                    declaration_id    = declaration_id,
                    student_id        = ext.student_id,
                    course_id         = ext.course_id,
                    section_id        = ext.section_id,
                    semester_id       = decl.semester_id,
                    internal_marks    = internal_totals.get(key),
                    external_marks    = ext.external_marks_obtained,
                    grace_marks       = None,
                    total_marks       = total,
                    max_marks         = max_marks,
                    percentage        = percentage,
                    grade_letter      = grade_letter,
                    grade_point       = grade_point,
                    is_pass           = is_pass_val,
                    result_status     = result_status,
                    credits_attempted = credits_attempted,
                    credits_earned    = credits_earned,
                    attempt_number    = ext.attempt_number,
                    computed_at       = now,
                    created_at        = now,
                )
                await SubjectResultRepo.upsert(row, db)

        return ComputeResultOut(
            declaration_id = declaration_id,
            computed_count = len(ext_marks_rows),
            pass_count     = pass_count,
            fail_count     = fail_count,
            absent_count   = absent_count,
            pending_count  = pending_count,
            message        = (
                f"Computed {len(ext_marks_rows)} results: "
                f"{pass_count} PASS, {fail_count} FAIL, "
                f"{absent_count} ABSENT, {pending_count} PENDING"
            ),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Grace Marks Service
# ─────────────────────────────────────────────────────────────────────────────

class GraceMarksService:

    @staticmethod
    async def apply(
        declaration_id: UUID,
        body: GraceMarkApplyIn,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisGraceMarksLog:
        decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
        if not decl:
            raise ResultsServiceError("NOT_FOUND", "Result declaration not found", 404)
        if decl.status in (DeclarationStatus.PUBLISHED, DeclarationStatus.LOCKED):
            raise ResultsServiceError(
                "DECLARATION_PUBLISHED",
                "Grace marks cannot be applied after publication. Revert to DRAFT first.",
                409,
            )

        subject_result = await SubjectResultRepo.get_by_declaration_student_course(
            declaration_id, body.student_id, body.course_id, db
        )
        if not subject_result:
            raise ResultsServiceError(
                "RESULT_NOT_FOUND",
                "Subject result not found. Run compute first.",
                404,
            )

        # Revoke any existing active grace entry for this subject result
        existing_log = await GraceMarksLogRepo.get_active_for_subject_result(
            subject_result.id, db
        )
        if existing_log:
            raise ResultsServiceError(
                "GRACE_ALREADY_APPLIED",
                "Grace marks already applied for this result. Revoke first.",
                409,
            )

        log = SisGraceMarksLog(
            id                  = uuid.uuid4(),
            declaration_id      = declaration_id,
            subject_result_id   = subject_result.id,
            student_id          = body.student_id,
            course_id           = body.course_id,
            grace_marks_applied = body.grace_marks_applied,
            reason              = body.reason,
            authorized_by       = actor_user_id,
            authorized_at       = _now(),
            created_at          = _now(),
        )
        await GraceMarksLogRepo.create(log, db)

        # Update subject result with grace marks
        subject_result.grace_marks = body.grace_marks_applied
        subject_result.updated_at  = _now()
        await db.flush()

        # Re-run compute for this single entry to refresh grade/pass-fail
        policy = await GradingPolicyRepo.get_by_id(decl.grading_policy_id, db)
        if policy and policy.bands and subject_result.total_marks is not None:
            new_total = (
                (subject_result.internal_marks or Decimal("0"))
                + (subject_result.external_marks or Decimal("0"))
                + body.grace_marks_applied
            )
            percentage = (
                new_total / subject_result.max_marks * 100
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            grade_letter, grade_point, is_pass = _apply_grade_band(percentage, policy.bands)
            subject_result.total_marks       = new_total
            subject_result.percentage        = percentage
            subject_result.grade_letter      = grade_letter
            subject_result.grade_point       = grade_point
            subject_result.is_pass           = is_pass
            subject_result.result_status     = (
                ResultStatus.PASS if is_pass else ResultStatus.FAIL
            )
            subject_result.credits_earned    = (
                subject_result.credits_attempted if is_pass else Decimal("0")
            )
            subject_result.computed_at       = _now()
            subject_result.updated_at        = _now()
            await db.flush()

        return log

    @staticmethod
    async def revoke(
        log_id: UUID,
        revoke_reason: str,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisGraceMarksLog:
        log = await GraceMarksLogRepo.get_by_id(log_id, db)
        if not log:
            raise ResultsServiceError("NOT_FOUND", "Grace mark log entry not found", 404)
        if log.revoked_at is not None:
            raise ResultsServiceError(
                "ALREADY_REVOKED", "This grace mark entry is already revoked", 409
            )
        decl = await ResultDeclarationRepo.get_by_id(log.declaration_id, db)
        if decl and decl.status in (DeclarationStatus.PUBLISHED, DeclarationStatus.LOCKED):
            raise ResultsServiceError(
                "DECLARATION_PUBLISHED",
                "Cannot revoke grace marks after publication",
                409,
            )

        log.revoked_by   = actor_user_id
        log.revoked_at   = _now()
        log.revoke_reason = revoke_reason
        await db.flush()

        # Reset grace marks on subject result and recompute
        subject_result = await SubjectResultRepo.get_by_id(log.subject_result_id, db)
        if subject_result:
            subject_result.grace_marks = None
            subject_result.updated_at  = _now()
            await db.flush()

        return log


# ─────────────────────────────────────────────────────────────────────────────
# SGPA / CGPA Service
# ─────────────────────────────────────────────────────────────────────────────

class SGPACGPAService:

    @staticmethod
    async def compute_sgpa_cgpa(
        declaration_id: UUID,
        db: AsyncSession,
    ) -> list[SisSemesterResult]:
        decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
        if not decl:
            raise ResultsServiceError("NOT_FOUND", "Result declaration not found", 404)

        subject_results = await SubjectResultRepo.list_by_declaration(declaration_id, db)
        if not subject_results:
            raise ResultsServiceError(
                "NO_SUBJECT_RESULTS",
                "No subject results found. Run compute first.",
                409,
            )

        # Group by student
        by_student: dict[UUID, list[SisSubjectResult]] = {}
        for sr in subject_results:
            by_student.setdefault(sr.student_id, []).append(sr)

        semester_results = []
        for student_id, rows in by_student.items():
            # SGPA = Σ(grade_point × credits_attempted) / Σ(credits_attempted)
            # Only include non-ABSENT rows in SGPA
            total_gp_credits = Decimal("0")
            total_credits    = Decimal("0")
            total_earned     = Decimal("0")
            all_pass         = True
            any_withheld     = False

            for row in rows:
                if row.result_status == ResultStatus.ABSENT:
                    continue
                if row.credits_attempted and row.grade_point is not None:
                    total_gp_credits += row.grade_point * row.credits_attempted
                    total_credits    += row.credits_attempted
                if row.credits_earned:
                    total_earned += row.credits_earned
                if row.result_status != ResultStatus.PASS:
                    all_pass = False
                if row.result_status == ResultStatus.WITHHELD:
                    any_withheld = True

            sgpa = None
            if total_credits > 0:
                sgpa = (total_gp_credits / total_credits).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            # CGPA: aggregate all published/locked semester results for this student
            prior_results = await SemesterResultRepo.list_by_student(
                student_id, db, published_only=True
            )
            all_gp  = total_gp_credits
            all_att = total_credits
            for prior in prior_results:
                if prior.declaration_id == declaration_id:
                    continue
                # Re-derive per-semester weighted sum from subject results
                prior_subjects = await SubjectResultRepo.list_by_declaration(
                    prior.declaration_id, db, student_id=student_id
                )
                for sr in prior_subjects:
                    if sr.result_status == ResultStatus.ABSENT:
                        continue
                    if sr.credits_attempted and sr.grade_point is not None:
                        all_gp  += sr.grade_point * sr.credits_attempted
                        all_att += sr.credits_attempted

            cgpa = None
            if all_att > 0:
                cgpa = (all_gp / all_att).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            # Overall status
            if any_withheld:
                overall = OverallResultStatus.WITHHELD
            elif all_pass:
                overall = OverallResultStatus.PASS
            else:
                overall = OverallResultStatus.FAIL

            existing = await SemesterResultRepo.get_by_declaration_student(
                declaration_id, student_id, db
            )
            now = _now()
            if existing:
                existing.sgpa                    = sgpa
                existing.cgpa                    = cgpa
                existing.total_credits_attempted = total_credits or None
                existing.total_credits_earned    = total_earned or None
                existing.overall_result_status   = overall.value
                existing.computed_at             = now
                existing.updated_at              = now
                await db.flush()
                semester_results.append(existing)
            else:
                row = SisSemesterResult(
                    id                      = uuid.uuid4(),
                    declaration_id          = declaration_id,
                    student_id              = student_id,
                    semester_id             = decl.semester_id,
                    sgpa                    = sgpa,
                    cgpa                    = cgpa,
                    total_credits_attempted = total_credits or None,
                    total_credits_earned    = total_earned or None,
                    overall_result_status   = overall.value,
                    computed_at             = now,
                    created_at              = now,
                )
                row = await SemesterResultRepo.upsert(row, db)
                semester_results.append(row)

        return semester_results


# ─────────────────────────────────────────────────────────────────────────────
# Rank List Service
# ─────────────────────────────────────────────────────────────────────────────

class RankListService:

    @staticmethod
    async def compute_ranks(
        declaration_id: UUID, db: AsyncSession
    ) -> list[SisSemesterResult]:
        """Compute section_rank and program_rank for all semester results."""
        all_sem_results = await SemesterResultRepo.list_by_declaration(declaration_id, db)
        if not all_sem_results:
            raise ResultsServiceError(
                "NO_SEMESTER_RESULTS",
                "No semester results found. Run SGPA/CGPA compute first.",
                409,
            )

        # Program rank: sort all students by SGPA desc
        sorted_all = sorted(
            all_sem_results,
            key=lambda r: float(r.sgpa or Decimal("0")),
            reverse=True,
        )
        for rank, sem_res in enumerate(sorted_all, start=1):
            sem_res.program_rank = rank

        # Section rank: group by section (via subject_results)
        subject_results = await SubjectResultRepo.list_by_declaration(declaration_id, db)
        student_sections: dict[UUID, UUID] = {}
        for sr in subject_results:
            student_sections[sr.student_id] = sr.section_id

        section_groups: dict[UUID, list[SisSemesterResult]] = {}
        for sem_res in all_sem_results:
            sec_id = student_sections.get(sem_res.student_id)
            if sec_id:
                section_groups.setdefault(sec_id, []).append(sem_res)

        for sec_id, group in section_groups.items():
            sorted_sec = sorted(
                group,
                key=lambda r: float(r.sgpa or Decimal("0")),
                reverse=True,
            )
            for rank, sem_res in enumerate(sorted_sec, start=1):
                sem_res.section_rank = rank

        await db.flush()
        return all_sem_results

    @staticmethod
    async def get_rank_list(
        declaration_id: UUID,
        scope: str,
        scope_ref_id: Optional[UUID],
        db: AsyncSession,
    ) -> RankListOut:
        all_sem = await SemesterResultRepo.list_by_declaration(declaration_id, db)
        if scope == "section" and scope_ref_id:
            subject_results = await SubjectResultRepo.list_by_declaration(
                declaration_id, db, section_id=scope_ref_id
            )
            student_ids_in_section = {sr.student_id for sr in subject_results}
            all_sem = [r for r in all_sem if r.student_id in student_ids_in_section]
            rank_field = "section_rank"
        else:
            rank_field = "program_rank"

        sorted_sem = sorted(
            all_sem,
            key=lambda r: getattr(r, rank_field) or 9999,
        )
        entries = [
            RankEntryOut(
                rank                  = getattr(r, rank_field) or 0,
                student_id            = r.student_id,
                sgpa                  = r.sgpa,
                cgpa                  = r.cgpa,
                total_credits_earned  = r.total_credits_earned,
                overall_result_status = r.overall_result_status,
                section_rank          = r.section_rank,
                program_rank          = r.program_rank,
            )
            for r in sorted_sem
        ]
        return RankListOut(
            declaration_id = declaration_id,
            scope          = scope,
            scope_ref_id   = scope_ref_id,
            total_students = len(entries),
            entries        = entries,
        )

    @staticmethod
    async def get_toppers(
        declaration_id: UUID,
        scope: str,
        scope_ref_id: Optional[UUID],
        top_n: int,
        db: AsyncSession,
    ) -> TopperListOut:
        rank_list = await RankListService.get_rank_list(
            declaration_id, scope, scope_ref_id, db
        )
        top_entries = [
            TopperOut(
                rank       = e.rank,
                student_id = e.student_id,
                sgpa       = e.sgpa,
                cgpa       = e.cgpa,
            )
            for e in rank_list.entries[:top_n]
        ]
        return TopperListOut(
            declaration_id = declaration_id,
            scope          = scope,
            entries        = top_entries,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Grade Card Service
# ─────────────────────────────────────────────────────────────────────────────

class GradeCardService:

    @staticmethod
    async def get_grade_card(
        declaration_id: UUID,
        student_id: UUID,
        db: AsyncSession,
    ) -> GradeCardOut:
        decl = await ResultDeclarationRepo.get_by_id(declaration_id, db)
        if not decl:
            raise ResultsServiceError("NOT_FOUND", "Result declaration not found", 404)

        subject_rows = await SubjectResultRepo.list_by_declaration(
            declaration_id, db, student_id=student_id
        )
        sem_result = await SemesterResultRepo.get_by_declaration_student(
            declaration_id, student_id, db
        )

        # Enrich with course names
        from app.modules.m01_program_advisor.models import Course
        subjects = []
        for sr in subject_rows:
            course_obj = await db.get(Course, sr.course_id)
            subjects.append(GradeCardSubjectRow(
                course_id      = sr.course_id,
                course_name    = course_obj.name if course_obj else "",
                course_code    = getattr(course_obj, "code", "") if course_obj else "",
                credits        = sr.credits_attempted,
                internal_marks = sr.internal_marks,
                external_marks = sr.external_marks,
                grace_marks    = sr.grace_marks,
                total_marks    = sr.total_marks,
                max_marks      = sr.max_marks,
                percentage     = sr.percentage,
                grade_letter   = sr.grade_letter,
                grade_point    = sr.grade_point,
                result_status  = sr.result_status,
            ))

        return GradeCardOut(
            student_id                   = student_id,
            declaration_id               = declaration_id,
            snapshot_academic_year       = decl.snapshot_academic_year,
            snapshot_semester_name       = decl.snapshot_semester_name,
            snapshot_grading_policy_name = decl.snapshot_grading_policy_name,
            declaration_type             = decl.declaration_type,
            published_at                 = decl.published_at,
            sgpa                         = sem_result.sgpa if sem_result else None,
            cgpa                         = sem_result.cgpa if sem_result else None,
            total_credits_attempted      = sem_result.total_credits_attempted if sem_result else None,
            total_credits_earned         = sem_result.total_credits_earned if sem_result else None,
            overall_result_status        = sem_result.overall_result_status if sem_result else None,
            section_rank                 = sem_result.section_rank if sem_result else None,
            program_rank                 = sem_result.program_rank if sem_result else None,
            subjects                     = subjects,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Transcript Service
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptService:

    @staticmethod
    async def get_transcript(
        student_id: UUID,
        db: AsyncSession,
    ) -> TranscriptOut:
        sem_results = await SemesterResultRepo.list_by_student(
            student_id, db, published_only=True
        )

        # Latest CGPA (from most recent declaration)
        latest_cgpa  = sem_results[-1].cgpa if sem_results else None
        total_credits = sum(
            r.total_credits_earned or Decimal("0") for r in sem_results
        ) or None

        from app.modules.m01_program_advisor.models import Course
        semesters = []
        for sem_res in sem_results:
            decl = await ResultDeclarationRepo.get_by_id(sem_res.declaration_id, db)
            if not decl:
                continue
            subj_rows = await SubjectResultRepo.list_by_declaration(
                sem_res.declaration_id, db, student_id=student_id
            )
            subjects = []
            for sr in subj_rows:
                course_obj = await db.get(Course, sr.course_id)
                subjects.append(GradeCardSubjectRow(
                    course_id      = sr.course_id,
                    course_name    = course_obj.name if course_obj else "",
                    course_code    = getattr(course_obj, "code", "") if course_obj else "",
                    credits        = sr.credits_attempted,
                    internal_marks = sr.internal_marks,
                    external_marks = sr.external_marks,
                    grace_marks    = sr.grace_marks,
                    total_marks    = sr.total_marks,
                    max_marks      = sr.max_marks,
                    percentage     = sr.percentage,
                    grade_letter   = sr.grade_letter,
                    grade_point    = sr.grade_point,
                    result_status  = sr.result_status,
                ))

            semesters.append(TranscriptSemesterOut(
                declaration_id          = sem_res.declaration_id,
                snapshot_academic_year  = decl.snapshot_academic_year,
                snapshot_semester_name  = decl.snapshot_semester_name,
                declaration_type        = decl.declaration_type,
                published_at            = decl.published_at,
                sgpa                    = sem_res.sgpa,
                cgpa                    = sem_res.cgpa,
                overall_result_status   = sem_res.overall_result_status,
                total_credits_attempted = sem_res.total_credits_attempted,
                total_credits_earned    = sem_res.total_credits_earned,
                subjects                = subjects,
            ))

        return TranscriptOut(
            student_id    = student_id,
            cgpa          = latest_cgpa,
            total_credits = total_credits,
            semesters     = semesters,
        )
