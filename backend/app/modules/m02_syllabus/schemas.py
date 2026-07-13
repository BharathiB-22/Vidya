from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.modules.m01_program_advisor.models import CourseType
from app.modules.m02_syllabus.models import (
    BloomLevel,
    MappingStrength,
    RefSource,
    RefType,
    SyllabusStatus,
)


# ---------------------------------------------------------------------------
# The type-specific official document (Syllabus.document JSONB)
#
# A Board of Studies does not write a syllabus for an internship. It writes
# guidelines — duration, evaluation rubric, weekly activities, what the company
# must provide, how the viva runs. A laboratory gets a lab manual and an experiment
# list, not five units of lectures it never delivers. A major project gets a
# handbook with a proposal format and a demonstration.
#
# So THEORY is the only type whose document is units + outcomes + references. Every
# other type stores its body here, in `Syllabus.document`, shaped by the schema
# below that matches its `doc_type`.
#
# Every field is a plain list of lines, and that is deliberate: the Board must be
# able to edit, add, remove and reorder ANY of it (Phase A rule — nothing the AI
# produced is final). A richer nested shape would buy structure the Board could not
# then rewrite freely, which is the wrong trade for a document a university has to
# be able to amend in a meeting.
# ---------------------------------------------------------------------------

class Experiment(BaseModel):
    """One entry of a lab manual's experiment list — the thing that actually gets
    performed in the laboratory, in the week it is performed."""
    number:     int  = Field(..., ge=1)
    title:      str  = Field(..., min_length=5)
    aim:        Optional[str] = None
    procedure:  Optional[str] = None
    apparatus:  list[str] = Field(default_factory=list)
    hours:      Optional[int] = Field(default=None, ge=1)


class LabDocument(BaseModel):
    """LAB — a Lab Manual. Explicitly NO theory units.

    Course Outcomes are still Course Outcomes (they are the Lab Outcomes, and they
    map to POs like any other), so they live in the normal `outcomes` relationship
    rather than being duplicated here.
    """
    manual_intro:          Optional[str] = None
    experiments:           list[Experiment] = Field(default_factory=list)
    equipment:             list[str] = Field(default_factory=list)
    software:              list[str] = Field(default_factory=list)
    assessment_guidelines: list[str] = Field(default_factory=list)


class RubricRow(BaseModel):
    """One row of an evaluation rubric: what is judged and what it is worth."""
    criterion: str = Field(..., min_length=3)
    weightage: Optional[int] = Field(default=None, ge=0, le=100)   # percent
    descriptor: Optional[str] = None


class InternshipDocument(BaseModel):
    """INTERNSHIP — no syllabus exists, and the Board does not write one.

    Duration and credits are stated in the document because an internship's
    duration is a policy decision the Board makes (8 weeks, 6 months), not a
    property derivable from an L-T-P that internships do not have.
    """
    guidelines:           list[str] = Field(default_factory=list)
    duration:             Optional[str] = None    # "8 weeks (post Semester VI)"
    credits:              Optional[int] = Field(default=None, ge=0)
    evaluation_rubric:    list[RubricRow] = Field(default_factory=list)
    weekly_activities:    list[str] = Field(default_factory=list)
    company_requirements: list[str] = Field(default_factory=list)
    report_format:        list[str] = Field(default_factory=list)
    viva_guidelines:      list[str] = Field(default_factory=list)


class MiniProjectDocument(BaseModel):
    """MINI_PROJECT — milestones and reviews inside a single semester."""
    guidelines:   list[str] = Field(default_factory=list)
    milestones:   list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    reviews:      list[str] = Field(default_factory=list)
    rubrics:      list[RubricRow] = Field(default_factory=list)


class MajorProjectDocument(BaseModel):
    """MAJOR_PROJECT — a project handbook. The superset of the mini project: it
    carries a proposal, a demonstration and a viva, which a mini project does not."""
    handbook:           list[str] = Field(default_factory=list)
    proposal_format:    list[str] = Field(default_factory=list)
    timeline:           list[str] = Field(default_factory=list)
    reviews:            list[str] = Field(default_factory=list)
    rubrics:            list[RubricRow] = Field(default_factory=list)
    final_report_format: list[str] = Field(default_factory=list)
    demonstration:      list[str] = Field(default_factory=list)
    viva:               list[str] = Field(default_factory=list)


class SeminarDocument(BaseModel):
    """SEMINAR — guidelines in place of a syllabus."""
    guidelines:          list[str] = Field(default_factory=list)
    topic_selection:     list[str] = Field(default_factory=list)
    presentation_format: list[str] = Field(default_factory=list)
    evaluation_rubric:   list[RubricRow] = Field(default_factory=list)
    deliverables:        list[str] = Field(default_factory=list)


# doc_type -> the schema its `document` JSONB must satisfy. THEORY is absent on
# purpose: a theory syllabus IS its units, outcomes and references, and its
# `document` stays empty. A lookup miss therefore means "this type has no document
# body", which is exactly true of THEORY.
DOCUMENT_SCHEMAS: dict[str, type[BaseModel]] = {
    CourseType.LAB.value:           LabDocument,
    CourseType.INTERNSHIP.value:    InternshipDocument,
    CourseType.MINI_PROJECT.value:  MiniProjectDocument,
    CourseType.MAJOR_PROJECT.value: MajorProjectDocument,
    CourseType.SEMINAR.value:       SeminarDocument,
}


def document_schema_for(doc_type: str | None) -> type[BaseModel] | None:
    """The document schema for a course type, or None for THEORY / unknown."""
    return DOCUMENT_SCHEMAS.get((doc_type or "").upper())


def parse_document(doc_type: str | None, raw: dict | None) -> dict:
    """Validate a stored/incoming document body against its type's schema.

    Returns the normalised dict. THEORY (and anything unrecognised) normalises to
    {} — a theory syllabus has no document body, and silently keeping stray keys on
    one would be a second, unvalidated source of truth for content that belongs in
    its units.
    """
    schema = document_schema_for(doc_type)
    if schema is None:
        return {}
    return schema.model_validate(raw or {}).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Unit topic item (embedded in SyllabusUnit.topics JSONB)
# ---------------------------------------------------------------------------

class UnitTopicItem(BaseModel):
    title:          str
    description:    Optional[str] = None
    hours_estimate: Optional[int] = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# How many units a theory syllabus is taught in
#
# The Board's decision, taken before generation. Four and five are the formats real
# regulations print — three is not a syllabus, and nobody prints Unit VI. Mirrors
# ai_provider.VALID_UNIT_COUNTS, which is what the generator and its validator hold
# to; these are the bounds the API enforces on the way in.
# ---------------------------------------------------------------------------

MIN_UNITS = 4
MAX_UNITS = 5
DEFAULT_UNITS = 5


# ---------------------------------------------------------------------------
# Course outcome schemas
# ---------------------------------------------------------------------------

class CourseOutcomeCreate(BaseModel):
    code:          str = Field(..., min_length=1, max_length=20)
    description:   str = Field(..., min_length=10)
    bloom_level:   BloomLevel
    display_order: int = Field(default=0, ge=0)


class CourseOutcomeUpdate(BaseModel):
    description:   Optional[str]       = Field(default=None, min_length=10)
    bloom_level:   Optional[BloomLevel] = None
    display_order: Optional[int]        = Field(default=None, ge=0)


class CourseOutcomeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:            UUID
    syllabus_id:   UUID
    code:          str
    description:   str
    bloom_level:   BloomLevel
    display_order: int
    created_at:    datetime
    updated_at:    Optional[datetime]


# ---------------------------------------------------------------------------
# CO-PO mapping schemas
# ---------------------------------------------------------------------------

class COPOMappingCreate(BaseModel):
    po_id:            UUID
    mapping_strength: MappingStrength = MappingStrength.MEDIUM
    justification:    Optional[str]   = None


class COPOMappingUpdate(BaseModel):
    mapping_strength: Optional[MappingStrength] = None
    justification:    Optional[str]             = None


class COPOMappingResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:               UUID
    co_id:            UUID
    po_id:            UUID
    mapping_strength: MappingStrength
    justification:    Optional[str]
    created_at:       datetime


class COPOMappingBulkUpdate(BaseModel):
    """Replaces all PO mappings for a single CO in one PUT call."""
    mappings: list[COPOMappingCreate] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# CO-PO matrix response (for display and export)
# ---------------------------------------------------------------------------

class COPOMatrixPOHeader(BaseModel):
    po_id:        UUID
    po_code:      str
    po_description: str


class COPOMatrixCell(BaseModel):
    po_id:            UUID
    po_code:          str
    mapping_strength: Optional[MappingStrength] = None
    justification:    Optional[str]             = None


class COPOMatrixRow(BaseModel):
    co_id:       UUID
    co_code:     str
    description: str
    bloom_level: BloomLevel
    cells:       list[COPOMatrixCell]


class COPOMatrixResponse(BaseModel):
    syllabus_id:      UUID
    course_id:        UUID
    po_headers:       list[COPOMatrixPOHeader]
    rows:             list[COPOMatrixRow]


# ---------------------------------------------------------------------------
# Syllabus unit schemas
# ---------------------------------------------------------------------------

class SyllabusUnitCreate(BaseModel):
    unit_number: int          = Field(..., ge=1)
    title:       str          = Field(..., min_length=3)
    # The unit's official prose block — what prints in the regulation.
    content:     Optional[str] = None
    topics:      list[UnitTopicItem] = Field(default_factory=list)
    total_hours: int          = Field(..., ge=1)
    pedagogy:    Optional[str] = None


class SyllabusUnitUpdate(BaseModel):
    """The Board rewrites units freely: the title, the hours, and above all the
    prose content. Splitting a unit is add + edit; merging is edit + delete."""
    title:       Optional[str]              = Field(default=None, min_length=3)
    content:     Optional[str]              = None
    topics:      Optional[list[UnitTopicItem]] = None
    total_hours: Optional[int]              = Field(default=None, ge=1)
    pedagogy:    Optional[str]              = None


class SyllabusUnitReorder(BaseModel):
    """Maps unit_id → new unit_number for a batch reorder."""
    order: list[tuple[UUID, int]] = Field(..., min_length=1)


class SyllabusUnitResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:           UUID
    syllabus_id:  UUID
    unit_number:  int
    title:        str
    content:      Optional[str] = None
    topics:       list[UnitTopicItem]
    total_hours:  int
    pedagogy:     Optional[str]
    bloom_summary: Optional[list[dict]]
    created_at:   datetime
    updated_at:   Optional[datetime]


# ---------------------------------------------------------------------------
# Syllabus reference schemas
# ---------------------------------------------------------------------------

class SyllabusReferenceCreate(BaseModel):
    title:        str              = Field(..., min_length=3)
    authors:      list[str]        = Field(default_factory=list)
    year:         Optional[int]    = Field(default=None, ge=1000, le=2100)
    ref_type:     RefType          = RefType.TEXTBOOK
    source:       RefSource        = RefSource.MANUAL
    doi:          Optional[str]    = None
    isbn:         Optional[str]    = None
    url:          Optional[str]    = None
    publisher:    Optional[str]    = None
    is_confirmed: bool             = True


class SyllabusReferenceUpdate(BaseModel):
    title:        Optional[str]     = Field(default=None, min_length=3)
    authors:      Optional[list[str]] = None
    year:         Optional[int]     = Field(default=None, ge=1000, le=2100)
    ref_type:     Optional[RefType] = None
    doi:          Optional[str]     = None
    isbn:         Optional[str]     = None
    url:          Optional[str]     = None
    publisher:    Optional[str]     = None
    is_confirmed: Optional[bool]    = None


class SyllabusReferenceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:           UUID
    syllabus_id:  UUID
    title:        str
    authors:      list[str]
    year:         Optional[int]
    ref_type:     RefType
    source:       RefSource
    doi:          Optional[str]
    isbn:         Optional[str]
    url:          Optional[str]
    publisher:    Optional[str]
    is_confirmed: bool
    created_at:   datetime
    updated_at:   Optional[datetime]


# ---------------------------------------------------------------------------
# Reference search schemas (faculty-initiated CrossRef / OpenLibrary search)
# ---------------------------------------------------------------------------

class ReferenceSearchRequest(BaseModel):
    query:    str     = Field(..., min_length=3)
    ref_type: RefType = RefType.TEXTBOOK
    limit:    int     = Field(default=5, ge=1, le=20)


class ReferenceCandidate(BaseModel):
    """Candidate from CrossRef or OpenLibrary — not yet attached to a syllabus."""
    title:     str
    authors:   list[str]
    year:      Optional[int]
    ref_type:  RefType
    source:    RefSource
    doi:       Optional[str] = None
    isbn:      Optional[str] = None
    url:       Optional[str] = None
    publisher: Optional[str] = None


# ---------------------------------------------------------------------------
# Syllabus schemas
# ---------------------------------------------------------------------------

class SyllabusCreate(BaseModel):
    course_id:           UUID
    custom_instructions: Optional[str] = None


class SyllabusUpdate(BaseModel):
    """Every prose section of the official syllabus is editable by the Board.

    Nothing the AI produced is final. It writes the first draft; the Board rewrites
    whatever it likes and then approves — and only the approved version is ever
    published.
    """
    custom_instructions:  Optional[str] = None
    objectives:           Optional[list[str]] = None
    practical_components: Optional[list[str]] = None
    internal_assessment:  Optional[list[str]] = None
    board_comment:        Optional[str] = None
    # THE ACADEMIC STRUCTURE — the Board's, saved before any AI runs.
    #
    # How many units the subject is taught in, and for how many hours each. Changing
    # them does NOT restructure units that already exist: they record the Board's
    # decision, and the next generation writes to it. Adding or removing a unit by hand
    # is done on the units themselves.
    #
    # These are what a theory syllabus cannot be generated without. The system does not
    # derive them, and the model never chooses them.
    unit_count:           Optional[int] = Field(default=None, ge=MIN_UNITS, le=MAX_UNITS)
    unit_hours:           Optional[list[int]] = Field(default=None)

    @model_validator(mode="after")
    def _hours_are_real(self) -> SyllabusUpdate:
        """An hour plan that does not fit the units it is for is not a plan.

        Refused rather than trimmed or padded: silently dropping the Board's fifth
        figure, or inventing a fifth from nowhere, would be the system deciding the very
        thing it is being told.
        """
        if self.unit_hours is None:
            return self
        if any(h < 1 for h in self.unit_hours):
            raise ValueError("Every unit must be taught for at least one hour.")
        if self.unit_count is not None and len(self.unit_hours) != self.unit_count:
            raise ValueError(
                f"unit_hours has {len(self.unit_hours)} entries but the syllabus is to "
                f"be taught in {self.unit_count} units."
            )
        return self
    # The type-specific document body — the lab manual, the internship guidelines,
    # the project handbook. Validated against the row's own doc_type in the service,
    # never against a type the caller supplies: a client must not be able to turn a
    # lab manual into an internship by posting a different shape.
    document:             Optional[dict] = None


class SyllabusResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                  UUID
    course_id:           UUID
    version:             int
    parent_version_id:   Optional[UUID]
    status:              SyllabusStatus
    doc_type:            str = CourseType.THEORY.value
    document:            dict = {}
    # How many units the Board asked this theory syllabus to be taught in, and the
    # hours it allocated to each. Ignored by every other type — a lab manual has
    # experiments, an internship has none.
    #
    # `unit_hours` is the PLAN the units were written to. The authoritative hours are
    # the ones on the units themselves, which the Board edits freely afterwards.
    unit_count:          int = DEFAULT_UNITS
    unit_hours:          list[int] = []
    custom_instructions: Optional[str]
    change_note:         Optional[str]
    board_comment:       Optional[str]
    objectives:          list[str] = []
    practical_components: list[str] = []
    internal_assessment: list[str] = []
    ai_model:            Optional[str]
    prompt_hash:         Optional[str]
    created_by_user_id:  UUID
    approved_by_user_id: Optional[UUID]
    approved_at:         Optional[datetime]
    locked_by_user_id:   Optional[UUID]
    locked_at:           Optional[datetime]
    dean_edited_at:      Optional[datetime] = None
    dean_edited_by_user_id: Optional[UUID] = None
    created_at:          datetime
    updated_at:          Optional[datetime]


class CourseInformation(BaseModel):
    """The header block of an official university syllabus.

    Every field is DERIVED from the `courses` row at read time — none is stored
    on the syllabus and none is typed in by anyone. See m02/formatting.py: a
    stored copy of the credits or category would be a second source of truth, and
    would silently disagree with the curriculum the moment the Board adjusted the
    course during review.
    """
    course_code:     str
    course_name:     str
    credits:         int
    ltp:             str    # "3-1-2"
    contact_hours:   int    # (L + T + P) x 15 weeks
    category:        str    # Core | Elective | Lab | Project
    course_type:     str = CourseType.THEORY.value
    semester:        int = 1
    regulation_year: Optional[int] = None   # "Regulation 2026" — from the programme


class SyllabusDetail(SyllabusResponse):
    """Full syllabus with all child entities nested."""
    outcomes:    list[CourseOutcomeResponse]
    units:       list[SyllabusUnitResponse]
    references:  list[SyllabusReferenceResponse]
    # Enriched course + program context (populated by router)
    course_information: Optional[CourseInformation] = None
    course_title: Optional[str] = None
    course_code:  Optional[str] = None
    program_name: Optional[str] = None
    semester:     Optional[int] = None


class SyllabusListItem(SyllabusResponse):
    """Enriched row for the syllabus list — joins course + program info."""
    course_title: str
    course_code:  str
    program_name: str
    semester:     int


class SyllabusListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     list[SyllabusListItem]


class SyllabusVersionResponse(BaseModel):
    """Lightweight row for version history list."""
    model_config = {"from_attributes": True}

    id:                 UUID
    version:            int
    parent_version_id:  Optional[UUID]
    status:             SyllabusStatus
    change_note:        Optional[str]
    created_by_user_id: UUID
    created_at:         datetime


class SyllabusStatusResponse(BaseModel):
    """Returned by every state-transition endpoint."""
    model_config = {"from_attributes": True}

    id:         UUID
    version:    int
    status:     SyllabusStatus
    updated_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Action request schemas (state machine transitions)
# ---------------------------------------------------------------------------

class GenerateSyllabusRequest(BaseModel):
    custom_instructions: Optional[str] = Field(
        default=None,
        description="Optional guidance for the AI generator.",
    )
    unit_count: Optional[int] = Field(
        default=None,
        ge=MIN_UNITS,
        le=MAX_UNITS,
        description=(
            "How many units to write the syllabus in — 4 or 5. The Board's decision, "
            "made BEFORE generation: five is not a universal format, and a Board that "
            "wanted four used to generate five and delete one, which left the hours "
            "redistributed by hand and the AI's pacing wrong across the units that "
            "survived. Omitted leaves whatever the syllabus already carries. Ignored "
            "for course types that have no units."
        ),
    )
    unit_hours: Optional[list[int]] = Field(
        default=None,
        description=(
            "Teaching hours for each unit, in order — [10, 8, 12, 10]. The Board's "
            "decision too: hours come out of the timetable and the credit structure, "
            "and the AI cannot know that Unit III is the heavy one this year. Each "
            "unit is then WRITTEN TO its hours rather than given hours after the fact. "
            "Must have exactly `unit_count` entries. Omitted lets the AI pace the "
            "units against the course's contact hours, as before."
        ),
    )

    @model_validator(mode="after")
    def _hours_match_the_units(self) -> GenerateSyllabusRequest:
        """An hour plan for a different number of units is a plan for a different
        syllabus. Refused rather than padded: silently giving Unit V zero hours
        because the Board sent four figures is exactly the kind of quiet wrong answer
        this whole feature exists to stop."""
        if self.unit_hours is None:
            return self

        expected = self.unit_count or DEFAULT_UNITS
        if len(self.unit_hours) != expected:
            raise ValueError(
                f"unit_hours has {len(self.unit_hours)} entries but the syllabus is "
                f"to be written in {expected} units."
            )
        if any(h < 1 for h in self.unit_hours):
            raise ValueError("Every unit must be taught for at least one hour.")
        return self


class SyllabusAIJobResponse(BaseModel):
    job_id:      UUID
    syllabus_id: UUID
    status:      str = "queued"


class RegenerateSection(str, Enum):
    """Which slice of an existing document to rewrite.

    The Board should never have to regenerate a whole syllabus because ONE unit came
    out weak — by the time they notice, the other four and the outcomes will often
    have been hand-edited, and a full regeneration throws all of that away.

    BOOKS and REFERENCES are separate even though both end up in
    `syllabus_references`, because they are separate sections of the printed
    document and a Board unhappy with the Text Books has no reason to lose its Web
    Resources:

        BOOKS       Text Books                    (RefType.TEXTBOOK)
        REFERENCES  Reference Books, Suggested Reading, Web Resources

    DOCUMENT rewrites the type-specific body — the lab manual, the internship
    guidelines, the project handbook. It is the non-theory equivalent of
    regenerating the units, and it is the only section that applies to a course
    which has no units at all.
    """
    UNIT       = "UNIT"
    OBJECTIVES = "OBJECTIVES"
    OUTCOMES   = "OUTCOMES"
    REFERENCES = "REFERENCES"
    BOOKS      = "BOOKS"
    PRACTICALS = "PRACTICALS"
    DOCUMENT   = "DOCUMENT"


class RegenerateSectionRequest(BaseModel):
    section: RegenerateSection
    unit_id: Optional[UUID] = None       # required when section is UNIT
    guidance: Optional[str] = Field(
        default=None,
        max_length=2000,
        description=(
            "What the Board wants different this time — 'go deeper on cache "
            "coherence', 'this overlaps Unit III'. Passed straight to the model."
        ),
    )


# ---------------------------------------------------------------------------
# Dean's post-approval edit of a guideline document
# ---------------------------------------------------------------------------

class DeanDocumentEditRequest(BaseModel):
    """The Dean adapting an APPROVED Internship / Project / Seminar document.

    Permitted because those documents depend on the company, the supervisor and
    institutional policy — things the Board cannot know at approval time and the
    Dean must settle before students start. A THEORY syllabus is NOT editable this
    way and the service refuses it: the taught curriculum is the Board's, and a Dean
    quietly rewriting an approved syllabus is precisely the failure the approve gate
    exists to prevent.
    """
    document: dict = Field(
        ...,
        description=(
            "The full replacement document body, validated against the row's own "
            "doc_type. Partial edits are made by sending back the whole document "
            "with the changed section — the Board and Dean edit whole sections, not "
            "individual lines."
        ),
    )
    note: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Why the Dean changed it. Lands in the governance trail.",
    )


class SaveVersionRequest(BaseModel):
    change_note: Optional[str] = None


class ForkRequest(BaseModel):
    """Fork any historical syllabus version into a new DRAFT."""
    change_note: Optional[str] = None


class ApproveRequest(BaseModel):
    """DRAFT -> APPROVED. The Board signs off one official syllabus.

    There is no reject and no request-revision. The Board writes the syllabus and
    the Board approves it — there is no second party to send it back to. When the
    Board is unhappy with a syllabus it edits it.
    """
    comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Compliance schemas
# ---------------------------------------------------------------------------

class ComplianceViolation(BaseModel):
    code:     str
    message:  str
    severity: str   # "ERROR" | "WARNING"


class ComplianceCheckResponse(BaseModel):
    passed:     bool
    violations: list[ComplianceViolation]


# ---------------------------------------------------------------------------
# Export schemas
# ---------------------------------------------------------------------------

class SyllabusExportJobResponse(BaseModel):
    job_id:      UUID
    syllabus_id: UUID
    format:      str        # "pdf" | "docx" | "json"
    status:      str = "queued"
