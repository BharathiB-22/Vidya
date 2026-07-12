"""
M02 SyllabusService — the OFFICIAL university syllabus.

Who owns a syllabus
-------------------
The Board (governance authority). Nobody else, at any point.

The Board generates it, edits it, and approves it; it is then locked with the
curriculum and becomes read-only forever. Faculty NEVER author or edit a
syllabus — they teach to the approved one and build their lesson plans, PPTs,
course kits, assignments and question papers underneath it. The Dean reads it.

This replaces the workflow where Faculty wrote syllabi and a Dean reviewed them,
which is why there is no submit, resubmit, reject or request-revision here: those
transitions only make sense when the author and the approver are two different
people.

Lifecycle
---------
    DRAFT -> AI_GENERATING -> DRAFT -> APPROVED -> LOCKED

  APPROVED  the Board has signed this syllabus off. Still editable — but an edit
            sends it back to DRAFT, because a sign-off must mean "I read exactly
            this". Same for a structural edit to the underlying course
            (`invalidate_for_course`): a syllabus paced to the old contact hours
            is no longer the thing that was approved.
  LOCKED    the curriculum was approved. Permanent. The only way past it is a new
            curriculum version.

Architecture contract
---------------------
  - All business logic lives here; routers are pure HTTP glue.
  - SyllabusServiceError carries a machine-readable `code`, human `message`,
    and HTTP `status_code` so routers can raise HTTPException without logic.
  - Downstream modules (M03/M05/M08) call get_latest_approved_for_downstream(),
    which returns only APPROVED or LOCKED syllabi — Faculty teach from the
    official document and from nothing else.
  - Fork creates a full deep copy: objectives, practical components, COs, CO-PO
    mappings, units, confirmed references. Unconfirmed (AI-sourced) references
    are not copied — they are re-fetched by reference_enrichment.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m01_program_advisor.models import (
    DEAN_EDITABLE_TYPES,
    CourseType,
    ProgramStatus,
)
from app.modules.m01_program_advisor.repository import CourseRepository
from app.modules.m02_syllabus.ai_provider import normalize_course_type
from app.modules.m02_syllabus.formatting import format_ltp, has_practical
from app.modules.m02_syllabus.models import (
    COPOMapping,
    CourseOutcome,
    MappingStrength,
    Syllabus,
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
    DeanDocumentEditRequest,
    ReferenceCandidate,
    SyllabusCreate,
    SyllabusReferenceCreate,
    SyllabusReferenceUpdate,
    SyllabusUnitCreate,
    SyllabusUnitUpdate,
    SyllabusUpdate,
    parse_document,
)

logger = logging.getLogger("vidya.service.m02")

# ---------------------------------------------------------------------------
# Course type -> what its document HAS
# ---------------------------------------------------------------------------

_DOC_TYPE_LABELS: dict[str, str] = {
    CourseType.THEORY.value:        "theory syllabus",
    CourseType.LAB.value:           "lab manual",
    CourseType.INTERNSHIP.value:    "set of internship guidelines",
    CourseType.MINI_PROJECT.value:  "set of mini project guidelines",
    CourseType.MAJOR_PROJECT.value: "major project handbook",
    CourseType.SEMINAR.value:       "set of seminar guidelines",
}

# Which sections each type can be asked to regenerate.
#
# Only a theory syllabus has units and practical components. Every other type's
# body is regenerated as a whole, through DOCUMENT — asking a lab manual for its
# Unit III would require the AI to invent the section before it could rewrite it,
# which is the precise failure course types exist to prevent.
#
# Objectives, outcomes and the bibliography are common to all six, because all six
# have them.
_COMMON_SECTIONS = frozenset({"OBJECTIVES", "OUTCOMES", "REFERENCES", "BOOKS", "DOCUMENT"})

_REGENERABLE_SECTIONS: dict[str, frozenset[str]] = {
    CourseType.THEORY.value:        _COMMON_SECTIONS | {"UNIT", "PRACTICALS"},
    CourseType.LAB.value:           _COMMON_SECTIONS,
    CourseType.INTERNSHIP.value:    _COMMON_SECTIONS,
    CourseType.MINI_PROJECT.value:  _COMMON_SECTIONS,
    CourseType.MAJOR_PROJECT.value: _COMMON_SECTIONS,
    CourseType.SEMINAR.value:       _COMMON_SECTIONS,
}

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

# The Board edits a DRAFT syllabus freely. An APPROVED one it may still revise —
# approval is a sign-off, not a freeze, and the Board can change its mind right
# up to the moment the curriculum is locked. Editing an APPROVED syllabus sends
# it back to DRAFT (see update_syllabus), so it must be re-approved before the
# curriculum can be.
#
# LOCKED is the one true immutable state: it means the curriculum was approved,
# and nothing inside a locked curriculum ever changes again. Not for the Dean,
# not for the Board, not for Admin. The only way past it is a new version.
_IMMUTABLE_STATUSES = {SyllabusStatus.LOCKED}


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
    """The single gate every syllabus write passes through. It does two things.

    1. REFUSES the write if the syllabus is frozen (CURRICULUM_LOCKED) or has a
       generation job in flight (GENERATING).

    2. UN-APPROVES the syllabus if it was APPROVED.

    The second is the important one, and it is here rather than in each caller on
    purpose. An approval has to mean "a member of the board has read exactly this
    document" — otherwise the curriculum's approve gate is worthless, because it
    would pass on a syllabus whose units, outcomes or references had been rewritten
    since anyone last looked at it.

    Every mutation — the syllabus row, its units, its course outcomes, its CO-PO
    mappings, its references — comes through this function. Putting the
    invalidation here means no write path can forget it: you cannot edit any part
    of a syllabus without its approval falling away. The board simply approves it
    again once it has re-read it.
    """
    syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
    if syllabus is None:
        raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
    if syllabus.status in _IMMUTABLE_STATUSES:
        raise SyllabusServiceError(
            "CURRICULUM_LOCKED",
            "This syllabus belongs to an approved curriculum and is locked "
            "permanently. Nobody may edit it — not the Dean, not the Board. "
            "Create a new curriculum version to make academic changes.",
            409,
        )
    if syllabus.status == SyllabusStatus.AI_GENERATING:
        raise SyllabusServiceError(
            "GENERATING",
            "Syllabus AI generation is in progress. Wait for completion before editing.",
            409,
        )
    if syllabus.status == SyllabusStatus.APPROVED:
        await SyllabusRepository.revert_to_draft(syllabus_id, db=db)
        logger.info(
            "m02: syllabus=%s edited after approval — returned to DRAFT for re-review",
            syllabus_id,
        )
    return syllabus


def _validated_document(syllabus, raw: dict | None) -> dict:
    """Validate an incoming document body against the syllabus's OWN doc_type.

    Never against a type the caller names. The row's type is the Board's decision,
    and if a client could choose the shape it validates against, it could post an
    internship's fields at a lab manual and quietly turn one document into the
    other.

    A THEORY syllabus has no document body (its document is its units), so posting
    one at a theory syllabus is refused rather than silently dropped — a Board
    member who thinks they have written internship guidelines onto a theory course
    needs to be told they have not.
    """
    doc_type = normalize_course_type(syllabus.doc_type)

    if doc_type == CourseType.THEORY.value:
        if raw:
            raise SyllabusServiceError(
                "NO_DOCUMENT_BODY",
                "A theory syllabus has no document body — its content is its units, "
                "objectives, outcomes and references. Edit those instead.",
                422,
            )
        return {}

    try:
        return parse_document(doc_type, raw)
    except ValidationError as exc:
        raise SyllabusServiceError(
            "INVALID_DOCUMENT",
            f"That is not a valid {_DOC_TYPE_LABELS[doc_type]}: {exc.error_count()} "
            f"field(s) did not validate. {exc.errors()[0].get('msg', '')}",
            422,
        ) from exc


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
    target_course_id: UUID | None = None,
    db: AsyncSession,
):
    """
    Create a new DRAFT syllabus that is a full structural copy of `original_id`.

    Copied:   objectives, practical components, COs, CO-PO mappings (per CO),
              units, is_confirmed=True references.
    Skipped:  Unconfirmed (AI-sourced) references — re-run enrichment if needed.

    `target_course_id` re-points the copy at a DIFFERENT course, which is what
    program versioning needs: forking a curriculum to v2 creates brand-new
    `courses` rows, and each one inherits an editable copy of v1's syllabus so
    the Board revises rather than regenerating forty subjects from scratch.
    Because the copy hangs off v2's own course row, v1's syllabus is untouched —
    immutability holds by construction rather than by a guard.

    Defaults to the original's own course (a plain version bump of one syllabus).
    """
    original = await SyllabusRepository.get_detail(original_id, db=db)
    if original is None:
        raise SyllabusServiceError("NOT_FOUND", "Source syllabus not found.", 404)

    new_syllabus = Syllabus(
        course_id=target_course_id or original.course_id,
        version=new_version,
        # A copy onto a different course starts a fresh lineage: v2's syllabus is
        # not a later version OF v1's, it is v2's own first syllabus.
        parent_version_id=None if target_course_id else original.id,
        status=SyllabusStatus.DRAFT,
        custom_instructions=original.custom_instructions,
        change_note=change_note,
        ai_model=original.ai_model,
        prompt_hash=original.prompt_hash,
        # The type-specific document travels with the fork. For a lab manual or a
        # project handbook this IS the document — forking without it would produce
        # an empty copy of a document that looked complete, which is the worst
        # possible failure of a version history.
        doc_type=original.doc_type,
        document=dict(original.document or {}),
        objectives=list(original.objectives or []),
        practical_components=list(original.practical_components or []),
        internal_assessment=list(original.internal_assessment or []),
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
            # `content` is the unit's PRINTED prose block. Forking without it left
            # the copy rendering from its topic list alone, silently discarding any
            # prose the Board had written by hand into the version they forked from.
            content=orig_unit.content,
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
    async def _require_curriculum_unlocked(course_id: UUID, *, db: AsyncSession) -> None:
        """Refuse if this course's curriculum is approved (and therefore locked).

        `_require_mutable` guards edits to an EXISTING syllabus. This guards the
        other way in: creating a new one, or forking one, against a course whose
        curriculum has already been frozen.
        """
        from sqlalchemy import text as _text

        status = (
            await db.execute(
                _text(
                    "SELECT p.status FROM courses c "
                    "JOIN programs p ON p.id = c.program_id WHERE c.id = :cid"
                ),
                {"cid": str(course_id)},
            )
        ).scalar_one_or_none()

        if status in (ProgramStatus.APPROVED.value, ProgramStatus.PUBLISHED.value):
            raise SyllabusServiceError(
                "CURRICULUM_LOCKED",
                "This subject belongs to an approved curriculum, which is locked "
                "permanently. No syllabus may be added to it. Create a new "
                "curriculum version to make academic changes.",
                409,
            )

    @staticmethod
    async def create_syllabus(
        payload: SyllabusCreate,
        created_by: UUID,
        creator_role: str = "",
        *,
        db: AsyncSession,
    ):
        """Board (and Admin) only — the role gate is on the router.

        Refuses if the course belongs to a curriculum that is already approved.
        Without this the lock is worthless: a board member could add a BRAND NEW
        syllabus to a course inside a locked curriculum, approve it, and it would
        become the latest official syllabus that Faculty teach from and Students
        read — an unreviewed document slipped into a frozen curriculum through the
        one door that was not bolted.

        Editing is blocked by `_require_mutable`; this is the same rule for
        creation.
        """
        await SyllabusService._require_curriculum_unlocked(payload.course_id, db=db)

        # The course's TYPE decides which document this row will hold — a theory
        # syllabus, a lab manual, internship guidelines. Stamped at creation and not
        # read back through afterwards (see m02.models.Syllabus.doc_type).
        course = await CourseRepository.get_by_id(payload.course_id, db=db)
        if course is None:
            raise SyllabusServiceError("NOT_FOUND", "Course not found.", 404)

        version = await SyllabusRepository.get_next_version(payload.course_id, db=db)
        syllabus = await SyllabusRepository.create(
            course_id=payload.course_id,
            created_by_user_id=created_by,
            custom_instructions=payload.custom_instructions,
            doc_type=normalize_course_type(course.course_type),
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

        if caller_role == "DEAN" and faculty_user_id is not None:
            from sqlalchemy import select
            from app.modules.m01_program_advisor.models import Course, Program
            from app.modules.m_academics.dean_scope import get_dean_program_ids

            governed = await get_dean_program_ids(faculty_user_id, "DEAN", db)
            if governed is not None:
                course_subq = (
                    select(Course.id)
                    .join(Program, Program.id == Course.program_id)
                    .where(Program.acad_program_id.in_(governed))
                )
                governed_course_ids = set(
                    (await db.execute(course_subq)).scalars().all()
                )
                if course_id is not None:
                    if course_id not in governed_course_ids:
                        raise SyllabusServiceError(
                            "NOT_IN_SCOPE",
                            "You may only view syllabuses for programs you govern.",
                            403,
                        )
                else:
                    course_ids = list(governed_course_ids)
                    total = await SyllabusRepository.count_by_courses(
                        course_ids, status_filter=status_filter, db=db
                    )
                    items = await SyllabusRepository.list_by_courses(
                        course_ids, status_filter=status_filter, offset=offset, limit=page_size, db=db
                    )
                    return total, items

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
        caller_role: str = "",
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ):
        """Edit an official syllabus. Board (and Admin) only — the role gate is on
        the router; Faculty never reach here.

        `_require_mutable` refuses the edit if the syllabus is locked, and returns
        it to DRAFT if it was approved — an approval cannot survive an edit to the
        thing it signed off on.
        """
        existing = await _require_mutable(syllabus_id, db=db)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise SyllabusServiceError("NO_FIELDS", "No fields to update.", 422)

        # A document is validated against the row's OWN doc_type, never against a
        # type the caller supplies. Otherwise a client could post an internship
        # shape at a lab manual and turn one document into the other — the row's
        # type is the Board's, not the caller's.
        if "document" in updates:
            updates["document"] = _validated_document(existing, updates["document"])

        updates["updated_at"] = datetime.now(timezone.utc)
        syllabus = await SyllabusRepository.update(syllabus_id, updates, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def dean_edit_document(
        syllabus_id: UUID,
        payload: DeanDocumentEditRequest,
        editor_id: UUID,
        *,
        db: AsyncSession,
    ):
        """The Dean adapting an APPROVED guideline document.

        This is the ONE write in M02 that lands on an approved, otherwise-immutable
        syllabus row, and the only one that does not withdraw the approval. It
        exists because four of the six course types produce documents whose content
        genuinely depends on things the Board cannot know when it approves them:

            INTERNSHIP     which company hosts the student, and what that company
                           requires
            MINI_PROJECT   which supervisors are available, and their load
            MAJOR_PROJECT  the same, plus the review calendar for this cohort
            SEMINAR        the presentation schedule

        A THEORY syllabus is different in kind. It is the taught curriculum, the
        Board owns it, and a Dean quietly rewriting an approved one is precisely the
        failure the approve gate exists to prevent. So it is refused here — not
        merely hidden in the UI, which is a suggestion rather than a rule.

        The approval SURVIVES this edit (unlike every other write, which goes
        through `_require_mutable` and reverts to DRAFT). The Board approved the
        academic substance — the outcomes, the rubric's criteria, the structure —
        and the Dean is filling in the institutional detail underneath it, which is
        the arrangement the Board signed off on. But the row is STAMPED, so the
        governance trail can always say which parts of the approved document the
        Board wrote and which the Dean did.
        """
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)

        doc_type = normalize_course_type(syllabus.doc_type)

        if doc_type not in DEAN_EDITABLE_TYPES:
            raise SyllabusServiceError(
                "DEAN_MAY_NOT_EDIT",
                "The Dean cannot modify a theory syllabus. The Board owns the taught "
                "curriculum: it writes the syllabus and it approves it. You may "
                "publish this curriculum, but not rewrite it. Only Internship, Mini "
                "Project, Major Project and Seminar guidelines may be adapted after "
                "approval, because those depend on the company, the supervisor and "
                "institutional policy.",
                403,
            )

        # Before approval the document is the Board's working draft and the Board
        # edits it through the normal path. The Dean's adaptation is specifically a
        # POST-approval act — it is what happens once the academic substance is
        # settled and the institutional detail has to be filled in.
        if syllabus.status not in (SyllabusStatus.APPROVED, SyllabusStatus.LOCKED):
            raise SyllabusServiceError(
                "NOT_APPROVED",
                "These guidelines have not been approved by the Board yet. Until "
                "they are, they are the Board's working draft and the Board edits "
                "them.",
                409,
            )

        document = _validated_document(syllabus, payload.document)

        now = datetime.now(timezone.utc)
        updated = await SyllabusRepository.update(
            syllabus_id,
            {
                "document":               document,
                "dean_edited_at":         now,
                "dean_edited_by_user_id": editor_id,
                "updated_at":             now,
                # status is deliberately NOT touched. See the docstring: the Board's
                # approval covers the academic substance and survives this.
            },
            db=db,
        )
        await db.commit()

        logger.info(
            "m02.dean_edit: syllabus=%s type=%s edited by dean=%s (approval retained)",
            syllabus_id, doc_type, editor_id,
        )
        return updated

    @staticmethod
    async def delete_syllabus(
        syllabus_id: UUID,
        *,
        caller_role: str = "",
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> None:
        """Delete a syllabus. Board and Admin only, and never a locked one."""
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)

        if syllabus.status == SyllabusStatus.LOCKED:
            raise SyllabusServiceError(
                "CURRICULUM_LOCKED",
                "This syllabus belongs to an approved curriculum and cannot be "
                "deleted. Create a new curriculum version instead.",
                409,
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
        caller_role: str = "",
        faculty_user_id: UUID | None = None,
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

    @staticmethod
    async def dispatch_section_regeneration(
        syllabus_id: UUID,
        section: str,
        tenant_id: UUID,
        schema_name: str,
        *,
        unit_id: UUID | None = None,
        guidance: str | None = None,
        db: AsyncSession,
    ) -> str:
        """Rewrite ONE section of an existing syllabus. Returns the job id.

        The Board should never have to regenerate a whole syllabus because one unit
        came out weak — five units, five COs and a bibliography is a lot of work to
        throw away, and much of it will have been hand-edited by the time anyone
        notices the flaw.

        Unlike a full generation this does NOT move the syllabus to AI_GENERATING:
        the rest of the document stays readable and editable while one part of it is
        being rewritten in the background. The syllabus is only reverted to DRAFT
        (by the worker) if it had already been approved — a sign-off cannot survive
        a rewrite of the thing it signed off on.
        """
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)

        if syllabus.status == SyllabusStatus.LOCKED:
            raise SyllabusServiceError(
                "CURRICULUM_LOCKED",
                "This syllabus belongs to an approved curriculum and is locked "
                "permanently. Nothing inside it can be regenerated. Create a new "
                "curriculum version to make academic changes.",
                409,
            )
        if syllabus.status == SyllabusStatus.AI_GENERATING:
            raise SyllabusServiceError(
                "GENERATING",
                "This syllabus is already being generated. Wait for it to finish.",
                409,
            )

        # A section the document does not HAVE cannot be regenerated. Asking a lab
        # manual for its Unit III, or an internship for its practical components, is
        # not a request the AI could honour — it would have to invent the section
        # first, which is exactly the failure course types exist to prevent.
        doc_type = normalize_course_type(syllabus.doc_type)
        allowed  = _REGENERABLE_SECTIONS[doc_type]
        if section not in allowed:
            raise SyllabusServiceError(
                "SECTION_NOT_APPLICABLE",
                f"A {_DOC_TYPE_LABELS[doc_type]} has no {section.title()} section. "
                f"You can regenerate: {', '.join(sorted(allowed))}.",
                422,
            )

        if section == "UNIT":
            if unit_id is None:
                raise SyllabusServiceError(
                    "UNIT_REQUIRED", "Say which unit to regenerate.", 422,
                )
            units = await SyllabusUnitRepository.list_by_syllabus(syllabus_id, db=db)
            if not any(u.id == unit_id for u in units):
                raise SyllabusServiceError(
                    "NOT_FOUND", "That unit does not belong to this syllabus.", 404,
                )

        if section == "PRACTICALS":
            course = await CourseRepository.get_by_id(syllabus.course_id, db=db)
            if course is not None and not has_practical(course):
                raise SyllabusServiceError(
                    "NO_PRACTICAL_HOURS",
                    f"{course.code} carries no practical hours (L-T-P "
                    f"{format_ltp(course)}), so it has no Practical Components. "
                    "Generating laboratory work for a course with no laboratory "
                    "would commit the department to teaching it.",
                    422,
                )

        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="regenerate_syllabus_section",
            queue_name="heavy",
            payload={
                "syllabus_id": str(syllabus_id),
                "schema_name": schema_name,
                "section":     section,
                "unit_id":     str(unit_id) if unit_id else None,
            },
            db=db,
        )
        await db.commit()

        from app.workers.heavy.syllabus_generation import regenerate_syllabus_section

        regenerate_syllabus_section.delay(
            job_id=str(job_id),
            syllabus_id=str(syllabus_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
            section=section,
            unit_id=str(unit_id) if unit_id else None,
            guidance=guidance,
        )
        logger.info(
            "m02.regenerate: queued section=%s syllabus=%s job=%s",
            section, syllabus_id, job_id,
        )
        return str(job_id)

    @staticmethod
    async def generate_for_program(
        program_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        *,
        requested_by: UUID,
        regenerate_all: bool = False,
        custom_instructions: str | None = None,
        db: AsyncSession,
    ) -> tuple[UUID, list[UUID], int]:
        """Generate the official syllabus for EVERY subject in a program.

        Returns (batch_id, job_ids, skipped_count).

        A curriculum's syllabus is not one document — it is one per subject, so
        forty-odd AI calls for an MCA. That has to be a batch of independent
        background jobs, never a request: any single call can fail, and one
        failure must not cost the other thirty-nine.

        Partial failure is therefore expected and safe. Each subject generates on
        its own; a re-run picks up only what is still missing (unless
        `regenerate_all`), so the Board retries the five that failed rather than
        redoing all forty-two and losing its edits to the ones that worked. And
        because the curriculum cannot be approved until EVERY subject has an
        APPROVED syllabus, a half-generated program simply cannot be locked —
        the gate catches what the batch missed.

        "Every subject" includes every option inside every elective basket: an
        elective option is a real course a student sits and is examined in, so it
        needs its own official syllabus exactly as a core course does.

        Stamps `structure_finalized_at` on the first run — the record of which
        structure the syllabus was written against. It does NOT freeze the
        structure; the Board may keep editing, and any edit to a course sends its
        syllabus back to DRAFT (see `invalidate_for_course`).
        """
        from app.modules.m01_program_advisor.models import Course, Program
        from app.workers.heavy.syllabus_generation import generate_syllabus

        program = await db.get(Program, program_id)
        if program is None:
            raise SyllabusServiceError("NOT_FOUND", "Program not found.", 404)
        if program.status != ProgramStatus.PENDING_APPROVAL:
            raise SyllabusServiceError(
                "INVALID_STATUS",
                "The official syllabus is generated while the curriculum is with "
                f"the governance authority; this one is {program.status.value}.",
                409,
            )

        courses = (
            await db.execute(
                select(Course).where(Course.program_id == program_id).order_by(Course.semester, Course.code)
            )
        ).scalars().all()
        if not courses:
            raise SyllabusServiceError(
                "NO_SUBJECTS",
                "This curriculum has no subjects to generate a syllabus for.",
                422,
            )

        batch_id = uuid4()
        queued: list[tuple[UUID, UUID]] = []   # (syllabus_id, job_id)
        skipped = 0

        for course in courses:
            existing = await SyllabusRepository.list_by_course(course.id, db=db)
            live = [s for s in existing if s.status != SyllabusStatus.LOCKED]

            if live and not regenerate_all:
                skipped += 1
                continue

            # Regenerating: discard the unapproved drafts we are replacing, so a
            # course never ends up with two competing "latest" syllabi.
            if live and regenerate_all:
                for s in live:
                    await SyllabusRepository.delete(s.id, db=db)

            syllabus = Syllabus(
                course_id=course.id,
                version=await SyllabusRepository.get_next_version(course.id, db=db),
                status=SyllabusStatus.AI_GENERATING,
                custom_instructions=custom_instructions,
                created_by_user_id=requested_by,
            )
            db.add(syllabus)
            await db.flush()

            job_id = await TaskJobPublicRepository.create(
                tenant_id=tenant_id,
                task_type="generate_syllabus",
                queue_name="heavy",
                payload={
                    "syllabus_id": str(syllabus.id),
                    "schema_name": schema_name,
                    "batch_id":    str(batch_id),
                },
                db=db,
            )
            queued.append((syllabus.id, UUID(str(job_id))))

        if program.structure_finalized_at is None and queued:
            program.structure_finalized_at = datetime.now(timezone.utc)
            program.structure_finalized_by_user_id = requested_by

        await db.commit()

        # Dispatch only AFTER the commit. A Celery worker can pick a task up
        # within milliseconds, and if it did so before this transaction landed it
        # would go looking for a syllabus row that does not exist yet.
        for syllabus_id, job_id in queued:
            generate_syllabus.delay(
                job_id=str(job_id),
                syllabus_id=str(syllabus_id),
                tenant_id=str(tenant_id),
                schema_name=schema_name,
            )

        logger.info(
            "m02.generate_for_program: program=%s batch=%s dispatched=%d skipped=%d",
            program_id, batch_id, len(queued), skipped,
        )
        return batch_id, [job_id for _, job_id in queued], skipped

    # =========================================================================
    # State machine — the Board approves its own syllabus
    #
    # There is no submit, no resubmit, no reject and no request-revision. Those
    # existed when Faculty AUTHORED a syllabus and a Dean REVIEWED it — two
    # parties, so a handoff was needed. Now one body writes it and signs it off,
    # so there is nobody to hand it to.
    #
    # There is no lock/unlock either. A syllabus is locked when the CURRICULUM is
    # approved (governance.approve_and_lock) — the structure and the syllabus
    # freeze together or the pair is incoherent — and it is never unlocked.
    # =========================================================================

    @staticmethod
    async def approve(
        syllabus_id: UUID,
        approved_by: UUID,
        *,
        db: AsyncSession,
    ):
        """DRAFT -> APPROVED. The Board signs off one official syllabus.

        Compliance-gated: the Board should not be able to sign off a syllabus
        with no course outcomes or no units, however it came to be that way.
        """
        syllabus = await _require_status(syllabus_id, SyllabusStatus.DRAFT, db=db)

        cos      = await CourseOutcomeRepository.list_by_syllabus(syllabus_id, db=db)
        units    = await SyllabusUnitRepository.list_by_syllabus(syllabus_id, db=db)
        mappings = await COPOMappingRepository.list_by_syllabus(syllabus_id, db=db)

        result = _run_compliance_check(cos, units, mappings)
        if not result.passed:
            error_msgs = "; ".join(
                v.message for v in result.violations if v.severity == "ERROR"
            )
            raise SyllabusServiceError("COMPLIANCE_FAILED", error_msgs, 422)

        syllabus = await SyllabusRepository.set_board_approved(
            syllabus_id, approved_by, db=db
        )
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        await db.commit()
        return syllabus

    @staticmethod
    async def invalidate_for_course(
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        """Send this course's APPROVED syllabus back to DRAFT. Returns how many.

        Called whenever the Board makes a STRUCTURAL change to a course while the
        curriculum is still under review — credits, L-T-P, code, title, semester.
        The syllabus was written against the old structure (its units are paced
        to the old contact hours, its header prints the old credits), so the
        Board's earlier sign-off no longer describes what it signed off on.

        This is what lets the Board keep editing the structure right up to
        approval without any freeze: a stale syllabus is automatically pushed
        back into the Board's queue, and the approve gate — which demands that
        EVERY subject be APPROVED — cannot pass until someone has looked at it
        again. The invariant is maintained by the gate, not by a lock.

        LOCKED syllabi are never touched: their curriculum is approved, and its
        structure cannot change in the first place.

        Does not commit — the caller's structural edit and this invalidation must
        land in the same transaction, or a crash between them would leave an
        approved syllabus describing a course that had already moved.
        """
        syllabi = await SyllabusRepository.list_by_course(course_id, db=db)
        reverted = 0
        for syllabus in syllabi:
            if syllabus.status == SyllabusStatus.APPROVED:
                await SyllabusRepository.revert_to_draft(syllabus.id, db=db)
                reverted += 1
        if reverted:
            logger.info(
                "m02.invalidate: course=%s structural edit reverted %d approved "
                "syllabus/es to DRAFT for re-review",
                course_id, reverted,
            )
        return reverted

    @staticmethod
    async def fork(
        syllabus_id: UUID,
        created_by: UUID,
        change_note: str | None,
        *,
        db: AsyncSession,
    ):
        """
        Fork a syllabus version into a new DRAFT on the SAME course. The source
        version is not modified. Use this to branch a revision while the Board
        still holds the curriculum.

        Refused once the curriculum is locked. A fork creates a new syllabus
        version for the course, which would become the latest one downstream reads
        — so allowing it on a locked curriculum would let an unreviewed document
        displace the official one. Changing a locked curriculum means forking the
        CURRICULUM (which copies its syllabi onto the new version's own courses),
        not forking a syllabus underneath it.
        """
        source = await _require_not_generating(syllabus_id, db=db)
        await SyllabusService._require_curriculum_unlocked(source.course_id, db=db)
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
        Return the highest-versioned APPROVED or LOCKED syllabus — the official
        one. Downstream modules (course kits, learning materials, exam papers)
        must call this and reject None: Faculty teach from the Board-approved
        syllabus and from nothing else.
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
        Queue the export Celery task. Only an official syllabus — APPROVED or
        LOCKED — may be exported: a draft is not a university document.
        """
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            raise SyllabusServiceError("NOT_FOUND", "Syllabus not found.", 404)
        export_eligible = {SyllabusStatus.APPROVED, SyllabusStatus.LOCKED}
        if syllabus.status not in export_eligible:
            raise SyllabusServiceError(
                "EXPORT_NOT_ELIGIBLE",
                f"Only an approved official syllabus can be exported; "
                f"this one is {syllabus.status.value}.",
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
