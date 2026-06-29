"""
M02 SyllabusService — state machine, versioning, rollback/fork, compliance.

Architecture contract
---------------------
  - All business logic lives here; routers are pure HTTP glue.
  - SyllabusServiceError carries a machine-readable `code`, human `message`,
    and HTTP `status_code` so routers can raise HTTPException without logic.
  - Immutability is enforced at the service layer for FACULTY_APPROVED and
    ADMIN_LOCKED; the DB-level ENUM does not enforce ordering.
  - Downstream modules (M03/M05/M08) call get_latest_approved_for_downstream()
    which returns only FACULTY_APPROVED or ADMIN_LOCKED syllabi.
  - Fork creates a full deep copy: COs, CO-PO mappings, units, confirmed
    references.  Unconfirmed (AI-sourced) references are not copied — they are
    re-fetched by reference_enrichment if the faculty triggers AI again.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m02_syllabus.models import (
    COPOMapping,
    CourseOutcome,
    MappingStrength,
    SyllabusReference,
    SyllabusStatus,
    SyllabusUnit,
)
from app.modules.m02_syllabus.repository import (
    COPOMappingRepository,
    CourseOutcomeRepository,
    SyllabusReferenceRepository,
    SyllabusRepository,
    SyllabusUnitRepository,
    TaskJobPublicRepository,
)
from app.modules.m02_syllabus.schemas import (
    COPOMappingBulkUpdate,
    COPOMappingCreate,
    COPOMappingResponse,
    COPOMatrixCell,
    COPOMatrixPOHeader,
    COPOMatrixResponse,
    COPOMatrixRow,
    ComplianceCheckResponse,
    ComplianceViolation,
    CourseOutcomeCreate,
    CourseOutcomeUpdate,
    ReferenceCandidate,
    SyllabusCreate,
    SyllabusReferenceCreate,
    SyllabusReferenceUpdate,
    SyllabusUnitCreate,
    SyllabusUnitUpdate,
    SyllabusUpdate,
)

logger = logging.getLogger("vidya.service.m02")

# ---------------------------------------------------------------------------
# Exported error class
# ---------------------------------------------------------------------------

class SyllabusServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Compliance: pure functions — no DB access
# ---------------------------------------------------------------------------

_CO_MIN     = 4
_UNIT_MIN   = 4
_COPO_WARN_THRESHOLD = 0.5   # warn if < 50 % of COs have any PO mapping


def _run_compliance_check(
    cos:      list[CourseOutcome],
    units:    list[SyllabusUnit],
    mappings: list[COPOMapping],
) -> ComplianceCheckResponse:
    violations: list[ComplianceViolation] = []

    # 1. Minimum COs
    if len(cos) < _CO_MIN:
        violations.append(ComplianceViolation(
            code="CO_MIN_NOT_MET",
            message=f"At least {_CO_MIN} course outcomes required; found {len(cos)}.",
            severity="ERROR",
        ))

    # 2. Minimum units
    if len(units) < _UNIT_MIN:
        violations.append(ComplianceViolation(
            code="UNIT_MIN_NOT_MET",
            message=f"At least {_UNIT_MIN} units required; found {len(units)}.",
            severity="ERROR",
        ))

    # 3. CO-PO mapping coverage (WARNING — approval not blocked)
    if cos:
        co_ids_mapped = {m.co_id for m in mappings}
        coverage = len(co_ids_mapped) / len(cos)
        if coverage < _COPO_WARN_THRESHOLD:
            violations.append(ComplianceViolation(
                code="COPO_COVERAGE_LOW",
                message=(
                    f"Only {len(co_ids_mapped)}/{len(cos)} COs have PO mappings "
                    f"({coverage:.0%}); recommended ≥ {_COPO_WARN_THRESHOLD:.0%}."
                ),
                severity="WARNING",
            ))

    # 4. Bloom taxonomy diversity (WARNING — approval not blocked)
    if cos:
        bloom_levels = {co.bloom_level for co in cos}
        if len(bloom_levels) < 2:
            level = next(iter(bloom_levels)).value if bloom_levels else "UNKNOWN"
            violations.append(ComplianceViolation(
                code="BLOOM_DIVERSITY_LOW",
                message=(
                    f"All {len(cos)} COs are at the same Bloom level ({level}); "
                    "consider covering a broader taxonomy range."
                ),
                severity="WARNING",
            ))

    passed = not any(v.severity == "ERROR" for v in violations)
    return ComplianceCheckResponse(passed=passed, violations=violations)


# ---------------------------------------------------------------------------
# Internal transition helpers
# ---------------------------------------------------------------------------

# REJECTED is editable — faculty can revise and resubmit.
_MUTABLE_STATUSES   = {SyllabusStatus.DRAFT, SyllabusStatus.AI_GENERATING, SyllabusStatus.REJECTED}
_IMMUTABLE_STATUSES = {
    SyllabusStatus.PENDING_REVIEW,
    SyllabusStatus.DEAN_APPROVED,
    SyllabusStatus.DEAN_LOCKED,
}

# Faculty may delete a syllabus in any of these statuses.
_FACULTY_DELETABLE = {
    SyllabusStatus.DRAFT,
    SyllabusStatus.AI_GENERATING,
    SyllabusStatus.PENDING_REVIEW,
    SyllabusStatus.REJECTED,
}


async def _require_status(
    syllabus_id: UUID,
    required: SyllabusStatus,
    *,
    db: AsyncSession,
):
    """Load syllabus and assert exact status, else raise SyllabusServiceError."""
    syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
    if syllabus is None:
        raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
    if syllabus.status != required:
        raise SyllabusServiceError(
            "INVALID_STATUS",
            f"Expected status {required.value}, got {syllabus.status.value}.",
            409,
        )
    return syllabus


async def _require_mutable(
    syllabus_id: UUID,
    *,
    db: AsyncSession,
):
    """Raise IMMUTABLE if status is PENDING_REVIEW, DEAN_APPROVED, or DEAN_LOCKED."""
    syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
    if syllabus is None:
        raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
    if syllabus.status in _IMMUTABLE_STATUSES:
        raise SyllabusServiceError(
            "IMMUTABLE",
            f"Syllabus is {syllabus.status.value} and cannot be edited. "
            "Fork to a new DRAFT version to make changes.",
            409,
        )
    if syllabus.status == SyllabusStatus.AI_GENERATING:
        raise SyllabusServiceError(
            "GENERATING",
            "Syllabus AI generation is in progress. Wait for completion before editing.",
            409,
        )
    return syllabus


async def _require_not_generating(
    syllabus_id: UUID,
    *,
    db: AsyncSession,
):
    """Raise GENERATING if AI task is still running."""
    syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
    if syllabus is None:
        raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
    if syllabus.status == SyllabusStatus.AI_GENERATING:
        raise SyllabusServiceError(
            "GENERATING",
            "Syllabus AI generation is in progress.",
            409,
        )
    return syllabus


# ---------------------------------------------------------------------------
# Deep fork helper — creates a full copy of a syllabus as a new DRAFT
# ---------------------------------------------------------------------------

async def _deep_fork(
    original_id: UUID,
    new_version: int,
    created_by: UUID,
    change_note: str | None,
    *,
    db: AsyncSession,
):
    """
    Create a new DRAFT syllabus that is a full structural copy of `original_id`.

    Copied:   COs, CO-PO mappings (per CO), units, is_confirmed=True references.
    Skipped:  Unconfirmed (AI-sourced) references — re-run enrichment if needed.
    """
    original = await SyllabusRepository.get_detail(original_id, db=db)
    if original is None:
        raise SyllabusServiceError("NOT_FOUND", "Source syllabus not found.", 404)

    from app.modules.m02_syllabus.models import Syllabus  # avoid top-level circular

    new_syllabus = Syllabus(
        course_id=original.course_id,
        version=new_version,
        parent_version_id=original.id,
        status=SyllabusStatus.DRAFT,
        custom_instructions=original.custom_instructions,
        change_note=change_note,
        ai_model=original.ai_model,
        prompt_hash=original.prompt_hash,
        created_by_user_id=created_by,
    )
    db.add(new_syllabus)
    await db.flush()
    await db.refresh(new_syllabus)

    # -- Copy COs + their mappings ------------------------------------------
    for orig_co in original.outcomes:
        new_co = CourseOutcome(
            syllabus_id=new_syllabus.id,
            code=orig_co.code,
            description=orig_co.description,
            bloom_level=orig_co.bloom_level,
            display_order=orig_co.display_order,
        )
        db.add(new_co)
        await db.flush()
        await db.refresh(new_co)

        for m in orig_co.mappings:
            db.add(COPOMapping(
                co_id=new_co.id,
                po_id=m.po_id,
                mapping_strength=m.mapping_strength,
                justification=m.justification,
            ))

    # -- Copy units -----------------------------------------------------------
    for orig_unit in original.units:
        db.add(SyllabusUnit(
            syllabus_id=new_syllabus.id,
            unit_number=orig_unit.unit_number,
            title=orig_unit.title,
            topics=orig_unit.topics,
            total_hours=orig_unit.total_hours,
            pedagogy=orig_unit.pedagogy,
            bloom_summary=orig_unit.bloom_summary,
        ))

    # -- Copy confirmed references only --------------------------------------
    for orig_ref in original.references:
        if orig_ref.is_confirmed:
            db.add(SyllabusReference(
                syllabus_id=new_syllabus.id,
                title=orig_ref.title,
                authors=orig_ref.authors,
                year=orig_ref.year,
                ref_type=orig_ref.ref_type,
                source=orig_ref.source,
                doi=orig_ref.doi,
                isbn=orig_ref.isbn,
                url=orig_ref.url,
                publisher=orig_ref.publisher,
                is_confirmed=True,
            ))

    await db.flush()
    return new_syllabus


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class SyllabusService:

    # =========================================================================
    # Syllabus CRUD
    # =========================================================================

    @staticmethod
    async def create_syllabus(
        payload: SyllabusCreate,
        created_by: UUID,
        creator_role: str = "",
        *,
        db: AsyncSession,
    ):
        # Faculty must have an active assignment for this course before creating a syllabus.
        if creator_role == "FACULTY":
            from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository
            assignment = await SubjectAssignmentRepository.get_active_for_faculty_course(
                payload.course_id, created_by, db=db
            )
            if assignment is None:
                raise SyllabusServiceError(
                    "NOT_ASSIGNED",
                    "You must be assigned to this course before creating a syllabus. "
                    "Contact your Dean to request an assignment.",
                    403,
                )

        version = await SyllabusRepository.get_next_version(payload.course_id, db=db)
        syllabus = await SyllabusRepository.create(
            course_id=payload.course_id,
            created_by_user_id=created_by,
            custom_instructions=payload.custom_instructions,
            db=db,
        )
        if version > 1:
            await SyllabusRepository.update(
                syllabus.id, {"version": version}, db=db
            )
        await db.commit()
        return syllabus

    @staticmethod
    async def get_syllabus(syllabus_id: UUID, *, db: AsyncSession):
        return await SyllabusRepository.get_by_id(syllabus_id, db=db)

    @staticmethod
    async def get_syllabus_detail(syllabus_id: UUID, *, db: AsyncSession):
        return await SyllabusRepository.get_detail(syllabus_id, db=db)

    @staticmethod
    async def list_syllabi(
        course_id: UUID | None,
        status_filter: SyllabusStatus | None = None,
        page: int = 1,
        page_size: int = 50,
        *,
        caller_role: str = "",
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ):
        offset = (page - 1) * page_size

        if caller_role == "FACULTY" and faculty_user_id is not None:
            from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository
            if course_id is not None:
                # Specific course: verify the faculty is assigned to it
                assignment = await SubjectAssignmentRepository.get_active_for_faculty_course(
                    course_id, faculty_user_id, db=db
                )
                if assignment is None:
                    raise SyllabusServiceError(
                        "NOT_ASSIGNED",
                        "You are not assigned to this course.",
                        403,
                    )
            else:
                # No course filter: scope to assigned courses only
                assignments = await SubjectAssignmentRepository.list_by_faculty(
                    faculty_user_id, db=db
                )
                course_ids = list({a.course_id for a in assignments})
                total = await SyllabusRepository.count_by_courses(
                    course_ids, status_filter=status_filter, db=db
                )
                items = await SyllabusRepository.list_by_courses(
                    course_ids, status_filter=status_filter, offset=offset, limit=page_size, db=db
                )
                return total, items

        if course_id is not None:
            total = await SyllabusRepository.count_by_course(
                course_id, status_filter=status_filter, db=db
            )
            items = await SyllabusRepository.list_by_course(
                course_id, status_filter=status_filter, offset=offset, limit=page_size, db=db
            )
        else:
            total = await SyllabusRepository.count_all(status_filter=status_filter, db=db)
            items = await SyllabusRepository.list_all(
                status_filter=status_filter, offset=offset, limit=page_size, db=db
            )
        return total, items

    @staticmethod
    async def list_versions(course_id: UUID, *, db: AsyncSession):
        return await SyllabusRepository.list_versions(course_id, db=db)

    @staticmethod
    async def update_syllabus(
        syllabus_id: UUID,
        payload: SyllabusUpdate,
        *,
        db: AsyncSession,
    ):
        await _require_mutable(syllabus_id, db=db)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise SyllabusServiceError("NO_FIELDS", "No fields to update.", 422)
        updates["updated_at"] = datetime.now(timezone.utc)
        syllabus = await SyllabusRepository.update(syllabus_id, updates, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def delete_syllabus(
        syllabus_id: UUID,
        *,
        caller_role: str = "",
        db: AsyncSession,
    ) -> None:
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)

        if caller_role == "FACULTY":
            if syllabus.status not in _FACULTY_DELETABLE:
                raise SyllabusServiceError(
                    "DELETE_FORBIDDEN",
                    f"Faculty cannot delete a {syllabus.status.value} syllabus. "
                    "Only Draft, Generating, Pending Review, and Rejected syllabi can be deleted.",
                    409,
                )
        elif caller_role != "ADMIN":
            # DEAN and other roles cannot delete
            raise SyllabusServiceError(
                "DELETE_FORBIDDEN",
                "Only Faculty (owner) or Admin may delete a syllabus.",
                403,
            )

        deleted = await SyllabusRepository.delete(syllabus_id, db=db)
        if not deleted:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()

    # =========================================================================
    # State machine — AI generation
    # =========================================================================

    @staticmethod
    async def dispatch_ai_generation(
        syllabus_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        *,
        db: AsyncSession,
    ) -> str:
        """
        Queue the AI generation task.  Returns the job_id (str).
        Only valid from DRAFT status.  Sets status to AI_GENERATING atomically
        before dispatching so re-dispatch is blocked until the task finishes.
        """
        await _require_status(syllabus_id, SyllabusStatus.DRAFT, db=db)
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)

        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="generate_syllabus",
            queue_name="heavy",
            payload={"syllabus_id": str(syllabus_id), "schema_name": schema_name},
            db=db,
        )
        await SyllabusRepository.update_status(
            syllabus_id, SyllabusStatus.AI_GENERATING, db=db
        )
        await db.commit()

        from app.workers.heavy.syllabus_generation import generate_syllabus  # noqa: PLC0415

        generate_syllabus.delay(
            job_id=str(job_id),
            syllabus_id=str(syllabus_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
        )
        logger.info(
            "m02.service: AI generation queued (syllabus=%s job=%s)", syllabus_id, job_id
        )
        return str(job_id)

    # =========================================================================
    # State machine — submit / dean-approve / reject / lock / unlock
    # =========================================================================

    @staticmethod
    async def submit_for_review(
        syllabus_id: UUID,
        submitted_by: UUID,
        *,
        db: AsyncSession,
    ):
        """
        DRAFT → PENDING_REVIEW.
        Faculty submits syllabus for Dean review. Runs compliance checks;
        raises COMPLIANCE_FAILED on ERROR violations.
        """
        await _require_status(syllabus_id, SyllabusStatus.DRAFT, db=db)
        return await SyllabusService._do_submit_for_review(syllabus_id, submitted_by, db=db)

    @staticmethod
    async def resubmit(
        syllabus_id: UUID,
        submitted_by: UUID,
        *,
        db: AsyncSession,
    ):
        """
        REJECTED → PENDING_REVIEW.
        Faculty resubmits a previously rejected syllabus after addressing Dean's feedback.
        Runs the same compliance checks as initial submission.
        """
        await _require_status(syllabus_id, SyllabusStatus.REJECTED, db=db)
        return await SyllabusService._do_submit_for_review(syllabus_id, submitted_by, db=db)

    @staticmethod
    async def _do_submit_for_review(
        syllabus_id: UUID,
        submitted_by: UUID,
        *,
        db: AsyncSession,
    ):
        cos      = await CourseOutcomeRepository.list_by_syllabus(syllabus_id, db=db)
        units    = await SyllabusUnitRepository.list_by_syllabus(syllabus_id, db=db)
        mappings = await COPOMappingRepository.list_by_syllabus(syllabus_id, db=db)

        result = _run_compliance_check(cos, units, mappings)
        if not result.passed:
            error_msgs = "; ".join(
                v.message for v in result.violations if v.severity == "ERROR"
            )
            raise SyllabusServiceError("COMPLIANCE_FAILED", error_msgs, 422)

        syllabus = await SyllabusRepository.set_pending_review(
            syllabus_id, submitted_by, db=db
        )
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def approve(
        syllabus_id: UUID,
        approved_by: UUID,
        *,
        db: AsyncSession,
    ):
        """
        PENDING_REVIEW → DEAN_APPROVED.
        Dean approves the submitted syllabus. Only DEAN role may call this.
        """
        await _require_status(syllabus_id, SyllabusStatus.PENDING_REVIEW, db=db)

        syllabus = await SyllabusRepository.set_dean_approved(
            syllabus_id, approved_by, db=db
        )
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def reject(
        syllabus_id: UUID,
        reason: str,
        *,
        db: AsyncSession,
    ):
        """
        PENDING_REVIEW → REJECTED.
        Dean rejects the syllabus with a reason. Faculty can edit it and resubmit.
        """
        await _require_status(syllabus_id, SyllabusStatus.PENDING_REVIEW, db=db)
        syllabus = await SyllabusRepository.update(
            syllabus_id,
            {
                "status":       SyllabusStatus.REJECTED,
                "dean_comment": reason,
                "updated_at":   datetime.now(timezone.utc),
            },
            db=db,
        )
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def request_revision(
        syllabus_id: UUID,
        comments: str,
        *,
        db: AsyncSession,
    ):
        """
        PENDING_REVIEW → REJECTED (revision-type).
        Dean requests specific changes with comments. Faculty edits and resubmits.
        The dean_comment is prefixed to distinguish revision requests from hard rejections.
        """
        await _require_status(syllabus_id, SyllabusStatus.PENDING_REVIEW, db=db)
        syllabus = await SyllabusRepository.update(
            syllabus_id,
            {
                "status":       SyllabusStatus.REJECTED,
                "dean_comment": f"[REVISION REQUESTED] {comments}",
                "updated_at":   datetime.now(timezone.utc),
            },
            db=db,
        )
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def lock(
        syllabus_id: UUID,
        locked_by: UUID,
        *,
        db: AsyncSession,
    ):
        """DEAN_APPROVED → DEAN_LOCKED."""
        await _require_status(syllabus_id, SyllabusStatus.DEAN_APPROVED, db=db)
        syllabus = await SyllabusRepository.set_dean_locked(syllabus_id, locked_by, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def unlock(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ):
        """DEAN_LOCKED → DEAN_APPROVED."""
        await _require_status(syllabus_id, SyllabusStatus.DEAN_LOCKED, db=db)
        syllabus = await SyllabusRepository.update_status(
            syllabus_id, SyllabusStatus.DEAN_APPROVED, db=db
        )
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def fork(
        syllabus_id: UUID,
        created_by: UUID,
        change_note: str | None,
        *,
        db: AsyncSession,
    ):
        """
        Fork any non-generating syllabus version into a new DRAFT.
        The source version is not modified.  Use this to create an edit branch
        from an approved or locked syllabus.
        """
        source = await _require_not_generating(syllabus_id, db=db)
        new_version = await SyllabusRepository.get_next_version(source.course_id, db=db)
        new_syllabus = await _deep_fork(
            syllabus_id,
            new_version=new_version,
            created_by=created_by,
            change_note=change_note,
            db=db,
        )
        await db.commit()
        return new_syllabus

    # =========================================================================
    # Compliance check (on-demand, read-only)
    # =========================================================================

    @staticmethod
    async def run_compliance_check(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> ComplianceCheckResponse:
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        cos      = await CourseOutcomeRepository.list_by_syllabus(syllabus_id, db=db)
        units    = await SyllabusUnitRepository.list_by_syllabus(syllabus_id, db=db)
        mappings = await COPOMappingRepository.list_by_syllabus(syllabus_id, db=db)
        return _run_compliance_check(cos, units, mappings)

    # =========================================================================
    # Downstream access — M03/M05/M08
    # =========================================================================

    @staticmethod
    async def get_latest_approved_for_downstream(
        course_id: UUID,
        *,
        db: AsyncSession,
    ):
        """
        Return the highest-versioned DEAN_APPROVED or DEAN_LOCKED syllabus.
        Downstream modules must call this and reject None (no approved version).
        """
        return await SyllabusRepository.get_latest_approved(course_id, db=db)

    # =========================================================================
    # Export eligibility
    # =========================================================================

    @staticmethod
    async def dispatch_export(
        syllabus_id: UUID,
        export_format: str,
        *,
        tenant_id: UUID,
        schema_name: str,
        requested_by_user_id: UUID,
        db: AsyncSession,
    ) -> UUID:
        """
        Queue the export Celery task.  Export is only permitted for
        DEAN_APPROVED or DEAN_LOCKED syllabi.
        """
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        export_eligible = {SyllabusStatus.DEAN_APPROVED, SyllabusStatus.DEAN_LOCKED}
        if syllabus.status not in export_eligible:
            raise SyllabusServiceError(
                "EXPORT_NOT_ELIGIBLE",
                f"Syllabus must be DEAN_APPROVED or DEAN_LOCKED for export; "
                f"current status is {syllabus.status.value}.",
                422,
            )

        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="export_syllabus",
            queue_name="heavy",
            payload={
                "syllabus_id": str(syllabus_id),
                "format":      export_format,
                "schema_name": schema_name,
            },
            db=db,
        )
        await db.commit()

        # Export task is implemented in STEP-12; deferred import avoids early crash.
        try:
            from app.workers.heavy.syllabus_export import export_syllabus  # noqa: PLC0415
            export_syllabus.delay(
                job_id=str(job_id),
                syllabus_id=str(syllabus_id),
                tenant_id=str(tenant_id),
                schema_name=schema_name,
                export_format=export_format,
                requested_by_user_id=str(requested_by_user_id),
            )
        except ImportError:
            logger.warning(
                "m02.service: syllabus_export task not yet registered (STEP-12 pending)"
            )

        return job_id

    # =========================================================================
    # Job status
    # =========================================================================

    @staticmethod
    async def get_job_status(
        job_id: UUID,
        tenant_id: UUID,
        *,
        db: AsyncSession,
    ) -> dict | None:
        return await TaskJobPublicRepository.get_by_id(job_id, tenant_id, db=db)

    # =========================================================================
    # Course Outcomes (DRAFT-only mutations)
    # =========================================================================

    @staticmethod
    async def add_co(
        syllabus_id: UUID,
        payload: CourseOutcomeCreate,
        *,
        db: AsyncSession,
    ):
        await _require_mutable(syllabus_id, db=db)
        existing = await CourseOutcomeRepository.get_by_code(syllabus_id, payload.code, db=db)
        if existing:
            raise SyllabusServiceError(
                "CODE_EXISTS",
                f"CO code {payload.code!r} already exists in this syllabus.",
                409,
            )
        co = await CourseOutcomeRepository.create(
            syllabus_id=syllabus_id,
            code=payload.code,
            description=payload.description,
            bloom_level=payload.bloom_level,
            display_order=payload.display_order,
            db=db,
        )
        await db.commit()
        return co

    @staticmethod
    async def update_co(
        co_id: UUID,
        syllabus_id: UUID,
        payload: CourseOutcomeUpdate,
        *,
        db: AsyncSession,
    ):
        await _require_mutable(syllabus_id, db=db)
        co = await CourseOutcomeRepository.get_by_id(co_id, db=db)
        if co is None or co.syllabus_id != syllabus_id:
            raise SyllabusServiceError("NOT_FOUND", "Course outcome not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise SyllabusServiceError("NO_FIELDS", "No fields to update.", 422)
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await CourseOutcomeRepository.update(co_id, updates, db=db)
        await db.commit()
        return updated

    @staticmethod
    async def delete_co(
        co_id: UUID,
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_mutable(syllabus_id, db=db)
        co = await CourseOutcomeRepository.get_by_id(co_id, db=db)
        if co is None or co.syllabus_id != syllabus_id:
            raise SyllabusServiceError("NOT_FOUND", "Course outcome not found.", 404)
        await CourseOutcomeRepository.delete(co_id, db=db)
        await db.commit()

    @staticmethod
    async def list_cos(syllabus_id: UUID, *, db: AsyncSession):
        return await CourseOutcomeRepository.list_by_syllabus(syllabus_id, db=db)

    # =========================================================================
    # CO-PO mappings (DRAFT-only mutations; FACULTY_APPROVED read-only view allowed)
    # =========================================================================

    @staticmethod
    async def update_copo_mappings(
        co_id: UUID,
        syllabus_id: UUID,
        payload: COPOMappingBulkUpdate,
        *,
        db: AsyncSession,
    ):
        """Replace all PO mappings for a single CO atomically."""
        await _require_mutable(syllabus_id, db=db)
        co = await CourseOutcomeRepository.get_by_id(co_id, db=db)
        if co is None or co.syllabus_id != syllabus_id:
            raise SyllabusServiceError("NOT_FOUND", "Course outcome not found.", 404)

        items = [
            {"po_id": m.po_id, "mapping_strength": m.mapping_strength, "justification": m.justification}
            for m in payload.mappings
        ]
        mappings = await COPOMappingRepository.replace_for_co(co_id, items, db=db)
        await db.commit()
        return mappings

    @staticmethod
    async def build_copo_matrix(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> COPOMatrixResponse | None:
        """
        Build the full CO × PO matrix for display and export.
        All POs in the programme appear as columns; empty cells where no mapping.
        """
        from app.modules.m01_program_advisor.repository import (
            CourseRepository,
            ProgramOutcomeRepository,
        )

        syllabus = await SyllabusRepository.get_detail(syllabus_id, db=db)
        if syllabus is None:
            return None

        course = await CourseRepository.get_by_id(syllabus.course_id, db=db)
        if course is None:
            return None

        pos = await ProgramOutcomeRepository.list_by_program(course.program_id, db=db)
        po_map = {po.id: po for po in pos}

        # Index mappings by (co_id, po_id)
        all_mappings = await COPOMappingRepository.list_by_syllabus(syllabus_id, db=db)
        mapping_index: dict[tuple, COPOMapping] = {
            (m.co_id, m.po_id): m for m in all_mappings
        }

        po_headers = [
            COPOMatrixPOHeader(
                po_id=po.id,
                po_code=po.code,
                po_description=po.description,
            )
            for po in pos
        ]

        rows: list[COPOMatrixRow] = []
        for co in syllabus.outcomes:
            cells = []
            for po in pos:
                m = mapping_index.get((co.id, po.id))
                cells.append(COPOMatrixCell(
                    po_id=po.id,
                    po_code=po.code,
                    mapping_strength=m.mapping_strength if m else None,
                    justification=m.justification if m else None,
                ))
            rows.append(COPOMatrixRow(
                co_id=co.id,
                co_code=co.code,
                description=co.description,
                bloom_level=co.bloom_level,
                cells=cells,
            ))

        return COPOMatrixResponse(
            syllabus_id=syllabus_id,
            course_id=syllabus.course_id,
            po_headers=po_headers,
            rows=rows,
        )

    # =========================================================================
    # Units (DRAFT-only mutations)
    # =========================================================================

    @staticmethod
    async def add_unit(
        syllabus_id: UUID,
        payload: SyllabusUnitCreate,
        *,
        db: AsyncSession,
    ):
        await _require_mutable(syllabus_id, db=db)
        unit = await SyllabusUnitRepository.create(
            syllabus_id=syllabus_id,
            unit_number=payload.unit_number,
            title=payload.title,
            total_hours=payload.total_hours,
            topics=[t.model_dump(exclude_none=True) for t in payload.topics],
            pedagogy=payload.pedagogy,
            db=db,
        )
        await db.commit()
        return unit

    @staticmethod
    async def update_unit(
        unit_id: UUID,
        syllabus_id: UUID,
        payload: SyllabusUnitUpdate,
        *,
        db: AsyncSession,
    ):
        await _require_mutable(syllabus_id, db=db)
        unit = await SyllabusUnitRepository.get_by_id(unit_id, db=db)
        if unit is None or unit.syllabus_id != syllabus_id:
            raise SyllabusServiceError("NOT_FOUND", "Unit not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise SyllabusServiceError("NO_FIELDS", "No fields to update.", 422)
        if "topics" in updates:
            updates["topics"] = [
                t if isinstance(t, dict) else t.model_dump(exclude_none=True)
                for t in updates["topics"]
            ]
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await SyllabusUnitRepository.update(unit_id, updates, db=db)
        await db.commit()
        return updated

    @staticmethod
    async def delete_unit(
        unit_id: UUID,
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_mutable(syllabus_id, db=db)
        unit = await SyllabusUnitRepository.get_by_id(unit_id, db=db)
        if unit is None or unit.syllabus_id != syllabus_id:
            raise SyllabusServiceError("NOT_FOUND", "Unit not found.", 404)
        await SyllabusUnitRepository.delete(unit_id, db=db)
        await db.commit()

    @staticmethod
    async def reorder_units(
        syllabus_id: UUID,
        order_map: dict[UUID, int],
        *,
        db: AsyncSession,
    ) -> int:
        await _require_mutable(syllabus_id, db=db)
        count = await SyllabusUnitRepository.reorder(order_map, db=db)
        await db.commit()
        return count

    @staticmethod
    async def list_units(syllabus_id: UUID, *, db: AsyncSession):
        return await SyllabusUnitRepository.list_by_syllabus(syllabus_id, db=db)

    # =========================================================================
    # References (DRAFT-only mutations for add/update/delete/confirm)
    # =========================================================================

    @staticmethod
    async def add_reference(
        syllabus_id: UUID,
        payload: SyllabusReferenceCreate,
        *,
        db: AsyncSession,
    ):
        await _require_mutable(syllabus_id, db=db)
        ref = await SyllabusReferenceRepository.create(
            syllabus_id=syllabus_id,
            title=payload.title,
            ref_type=payload.ref_type,
            source=payload.source,
            authors=payload.authors,
            year=payload.year,
            doi=payload.doi,
            isbn=payload.isbn,
            url=payload.url,
            publisher=payload.publisher,
            is_confirmed=payload.is_confirmed,
            db=db,
        )
        await db.commit()
        return ref

    @staticmethod
    async def update_reference(
        ref_id: UUID,
        syllabus_id: UUID,
        payload: SyllabusReferenceUpdate,
        *,
        db: AsyncSession,
    ):
        await _require_mutable(syllabus_id, db=db)
        ref = await SyllabusReferenceRepository.get_by_id(ref_id, db=db)
        if ref is None or ref.syllabus_id != syllabus_id:
            raise SyllabusServiceError("NOT_FOUND", "Reference not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise SyllabusServiceError("NO_FIELDS", "No fields to update.", 422)
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await SyllabusReferenceRepository.update(ref_id, updates, db=db)
        await db.commit()
        return updated

    @staticmethod
    async def delete_reference(
        ref_id: UUID,
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_mutable(syllabus_id, db=db)
        ref = await SyllabusReferenceRepository.get_by_id(ref_id, db=db)
        if ref is None or ref.syllabus_id != syllabus_id:
            raise SyllabusServiceError("NOT_FOUND", "Reference not found.", 404)
        await SyllabusReferenceRepository.delete(ref_id, db=db)
        await db.commit()

    @staticmethod
    async def confirm_reference(
        ref_id: UUID,
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ):
        """
        Faculty confirms an AI-sourced reference candidate.
        Sets is_confirmed=True so the reference survives future forks.
        Allowed in DRAFT only; confirmed references in approved syllabi are immutable.
        """
        await _require_mutable(syllabus_id, db=db)
        ref = await SyllabusReferenceRepository.get_by_id(ref_id, db=db)
        if ref is None or ref.syllabus_id != syllabus_id:
            raise SyllabusServiceError("NOT_FOUND", "Reference not found.", 404)
        if ref.is_confirmed:
            raise SyllabusServiceError(
                "ALREADY_CONFIRMED", "Reference is already confirmed.", 409
            )
        updated = await SyllabusReferenceRepository.update(
            ref_id, {"is_confirmed": True, "updated_at": datetime.now(timezone.utc)}, db=db
        )
        await db.commit()
        return updated

    @staticmethod
    async def list_references(syllabus_id: UUID, *, db: AsyncSession):
        return await SyllabusReferenceRepository.list_by_syllabus(syllabus_id, db=db)

    @staticmethod
    async def search_references(
        query: str,
        ref_type,
        limit: int = 5,
    ) -> list[ReferenceCandidate]:
        """
        On-demand faculty search against CrossRef + OpenLibrary.
        Results are not saved — faculty adds chosen candidates via add_reference().
        """
        from app.modules.m02_syllabus.models import RefType
        from app.modules.m02_syllabus.reference_clients import (
            CrossRefClient,
            OpenLibraryClient,
        )

        crossref = CrossRefClient(max_results=limit)
        results: list[ReferenceCandidate] = []
        seen: set[str] = set()

        try:
            for c in await crossref.search(query, ref_type=ref_type, rows=limit):
                key = c.doi or c.title.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(ReferenceCandidate(
                        title=c.title,
                        authors=c.authors,
                        year=c.year,
                        ref_type=c.ref_type,
                        source=c.source,
                        doi=c.doi,
                        isbn=c.isbn,
                        url=c.url,
                        publisher=c.publisher,
                    ))
        except Exception:
            logger.warning("m02.service: CrossRef search failed", exc_info=True)

        if ref_type in (RefType.TEXTBOOK, RefType.REFERENCE):
            ol = OpenLibraryClient(max_results=limit)
            try:
                for c in await ol.search(query, limit=limit):
                    key = c.doi or c.title.lower()
                    if key not in seen and len(results) < limit:
                        seen.add(key)
                        results.append(ReferenceCandidate(
                            title=c.title,
                            authors=c.authors,
                            year=c.year,
                            ref_type=c.ref_type,
                            source=c.source,
                            doi=c.doi,
                            isbn=c.isbn,
                            url=c.url,
                            publisher=c.publisher,
                        ))
            except Exception:
                logger.warning("m02.service: OpenLibrary search failed", exc_info=True)

        return results[:limit]
