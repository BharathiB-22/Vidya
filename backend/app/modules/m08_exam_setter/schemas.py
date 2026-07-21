"""
M08 Exam Setter — Pydantic schemas.

Naming convention:
  *Create  — request body for resource creation
  *Update  — request body for partial update
  *Request — request body for workflow actions
  *Response — response model
  *ListResponse — paginated list wrapper
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.m08_exam_setter.models import ExamWorkflow


# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------

class QuestionFormatConfig(BaseModel):
    """How many questions of each type to generate."""
    mcq_count:     int = Field(default=0, ge=0)
    short_count:   int = Field(default=0, ge=0)
    long_count:    int = Field(default=0, ge=0)
    problem_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def at_least_one(self) -> "QuestionFormatConfig":
        total = self.mcq_count + self.short_count + self.long_count + self.problem_count
        if total == 0:
            raise ValueError("At least one question format must have count > 0.")
        return self


class BloomsDistribution(BaseModel):
    """Requested or actual Bloom's level distribution (percentages, must sum to 100)."""
    remember:   float = Field(default=0.0, ge=0.0, le=100.0)
    understand: float = Field(default=0.0, ge=0.0, le=100.0)
    apply:      float = Field(default=0.0, ge=0.0, le=100.0)
    analyse:    float = Field(default=0.0, ge=0.0, le=100.0)
    evaluate:   float = Field(default=0.0, ge=0.0, le=100.0)
    create:     float = Field(default=0.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def must_sum_to_100(self) -> "BloomsDistribution":
        total = (
            self.remember + self.understand + self.apply
            + self.analyse + self.evaluate + self.create
        )
        if abs(total - 100.0) > 1.0:
            raise ValueError(f"Bloom's distribution must sum to 100 (got {total:.1f}).")
        return self


# ---------------------------------------------------------------------------
# Per-unit paper blueprint  (P1.16)
# ---------------------------------------------------------------------------

class BlueprintRow(BaseModel):
    """One question group within a unit's blueprint — a university exam pattern
    row: generate ``count`` questions of ``marks`` each, of which the student
    answers ``answer_count`` per the ``choice_pattern``.

    choice_pattern:
      COMPULSORY  — answer all (answer_count == count).
      ANSWER_ANY  — "Answer any N of M" (answer_count < count).
      OR_CHOICE   — either/or alternatives ("Q OR Q"); answer_count == 1.

    Backward compatible: legacy rows carry only {count, marks}. When answer_count
    is absent it defaults to count (compulsory), so old blueprints keep their exact
    printed and evaluation totals.
    """
    category:       str | None = Field(default=None, description="Optional group label")
    count:          int   = Field(..., gt=0, le=50, description="Questions to GENERATE")
    marks:          float = Field(..., gt=0, le=100, description="Marks per question")
    answer_count:   int | None = Field(default=None, ge=1, le=50,
                                       description="Questions the student must answer")
    choice_pattern: str   = Field(default="COMPULSORY")

    # Identity of the template block this row was compiled from. Generation stamps
    # it onto every question the row produces, so the editor and the PDF rebuild
    # the faculty's template exactly rather than inferring it from (unit, marks).
    # Absent on legacy blueprints, which keep the old inference path.
    template_block_id: str | None = Field(default=None, description="Owning template block id")
    subpart_index:     int | None = Field(default=None, ge=0,
                                          description="Sub-part index within a FULL_QUESTION block")
    # Position of the owning block in the printed paper. Rows are grouped by unit,
    # so this is what restores the faculty's block order for numbering.
    block_order:       int | None = Field(default=None, ge=0,
                                          description="Owning block's position in the paper")

    @field_validator("choice_pattern", mode="before")
    @classmethod
    def _norm_pattern(cls, v: str | None) -> str:
        v = (v or "COMPULSORY").upper().strip()
        return v if v in ("COMPULSORY", "ANSWER_ANY", "OR_CHOICE") else "COMPULSORY"

    @model_validator(mode="after")
    def _defaults(self) -> "BlueprintRow":
        # Default answer_count to count, then coerce it to the pattern so the two
        # totals and the printed instructions are always self-consistent.
        if self.answer_count is None:
            self.answer_count = self.count
        if self.choice_pattern == "COMPULSORY":
            self.answer_count = self.count
        elif self.choice_pattern == "OR_CHOICE":
            self.answer_count = 1
        if self.answer_count > self.count:
            self.answer_count = self.count
        return self


class UnitBlueprint(BaseModel):
    """Blueprint for a single unit: an ordered list of question groups."""
    unit_number: int              = Field(..., ge=0)
    rows:        list[BlueprintRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Section configuration  (H-35)
# ---------------------------------------------------------------------------

class SectionConfig(BaseModel):
    """
    One Part (A / B / C) in a section-based exam.

    mcq_only=True constrains all questions in this section to MCQ type.
    The service layer enforces this during generation.
    answer_q must not exceed total_q (e.g. "answer any 8 of 10").
    """
    label:       str   = Field(..., min_length=1, max_length=4,
                               description='Section label, e.g. "A", "B", "C"')
    instruction: str | None = None
    total_q:     int   = Field(..., gt=0, description="Total questions in this section")
    answer_q:    int   = Field(..., gt=0, description="Questions the student must answer")
    marks_each:  float = Field(..., gt=0)
    order:       int   = Field(..., ge=0)
    mcq_only:    bool  = False

    @model_validator(mode="after")
    def _answer_le_total(self) -> "SectionConfig":
        if self.answer_q > self.total_q:
            raise ValueError(
                f"answer_q ({self.answer_q}) cannot exceed total_q ({self.total_q})."
            )
        return self


# ---------------------------------------------------------------------------
# ExamPaper schemas
# ---------------------------------------------------------------------------

class ExamPaperCreate(BaseModel):
    course_id:            UUID
    title:                str = Field(..., min_length=3, max_length=300)
    # "AI" dispatches the existing Celery/LLM generation; "MANUAL" creates an
    # empty, immediately-editable paper (no Celery, no LLM).
    creation_mode:        str = Field(default="AI", pattern="^(AI|MANUAL)$")
    exam_type:            str = Field(default="END_SEM")
    exam_workflow:        ExamWorkflow = Field(
        default=ExamWorkflow.BOARD_EXAM,
        description="INTERNAL = faculty-only gate; BOARD_EXAM = full 3-gate Board flow",
    )
    total_marks:          int = Field(..., gt=0, le=500)
    duration_mins:        int = Field(..., gt=0, le=600)
    units_included:       list[int] = Field(..., min_length=1)
    # A paper's question plan may come from a per-unit blueprint (preferred), a
    # flat question_format, or a section layout. At least one must be provided.
    question_format:      QuestionFormatConfig | None = None
    blueprint:            list[UnitBlueprint] | None = None
    # Paper Template (source of truth). blueprint is compiled from this; the
    # definition is stored verbatim so the editor and PDF can reconstruct the
    # exact structure. Optional → legacy/unit papers still work.
    template_definition:  dict[str, Any] | None = None
    # LEGACY. v3 templates have no "type" — a paper is sections of question
    # definitions, and the builder stopped sending this. Still accepted (and still
    # stored) so an older client's papers record what they always did.
    template_type:        str | None = None
    requested_dist:       BloomsDistribution
    section_config:       list[SectionConfig] | None = None
    special_instructions: str | None = None

    @model_validator(mode="after")
    def _has_question_plan(self) -> "ExamPaperCreate":
        # A template fully describes the paper on its own — it is the source of
        # truth and does not need a blueprint alongside it. The older plans stay
        # valid so legacy and section papers keep working unchanged.
        td = self.template_definition or {}
        has_template = bool(td.get("sections") or td.get("blocks") or td.get("units"))
        has_blueprint = bool(self.blueprint) and any(b.rows for b in self.blueprint)
        if not (has_template or has_blueprint
                or self.question_format is not None or self.section_config):
            raise ValueError(
                "Provide a paper template, a blueprint, a question format, or a "
                "section layout."
            )
        return self

    @model_validator(mode="after")
    def _template_marks_match(self) -> "ExamPaperCreate":
        """total_marks must be the template's own evaluation total.

        The template is the source of truth, so a paper whose stored total says
        something different from what its structure evaluates to is already wrong
        before a single question exists.
        """
        td = self.template_definition or {}
        if not (td.get("sections") or td.get("blocks") or td.get("units")):
            return self
        from app.modules.m08_exam_setter.paper_template import template_totals

        _printed, evaluation = template_totals(self.template_definition)
        if evaluation > 0 and abs(evaluation - float(self.total_marks)) > 0.01:
            raise ValueError(
                f"total_marks ({self.total_marks}) does not match the template's "
                f"evaluation total ({evaluation:g}). The template decides the marks."
            )
        return self

    @model_validator(mode="after")
    def _mcq_only_guard(self) -> "ExamPaperCreate":
        if self.section_config and self.question_format is not None:
            has_mcq_only = any(s.mcq_only for s in self.section_config)
            if has_mcq_only and self.question_format.mcq_count == 0:
                raise ValueError(
                    "section_config contains an mcq_only section "
                    "but question_format.mcq_count is 0."
                )
        return self


class ExamPaperResponse(BaseModel):
    id:                   UUID
    course_id:            UUID
    created_by:           UUID
    title:                str
    exam_type:            str
    exam_workflow:        str
    total_marks:          int
    duration_mins:        int
    units_included:       list[Any]
    question_format:      dict[str, Any] | None
    blueprint:            list[Any] | None
    template_type:        str | None
    template_definition:  dict[str, Any] | None
    requested_dist:       dict[str, Any]
    actual_dist:          dict[str, Any] | None
    section_config:       list[Any] | None
    co_coverage_report:   list[Any] | None
    unit_coverage_report: list[Any] | None
    special_instructions: str | None
    ai_model:             str | None
    generation_job_id:    UUID | None
    status:               str
    failure_reason:       str | None
    submitted_at:         datetime | None
    approved_by:          UUID | None
    approved_at:          datetime | None
    board_comment:        str | None
    scrutinizer_id:       UUID | None
    scrutinized_at:       datetime | None
    scrutinizer_comment:  str | None
    sealed_at:            datetime | None
    release_at:           datetime | None
    released_at:          datetime | None
    created_at:           datetime
    updated_at:           datetime | None

    model_config = {"from_attributes": True}


class ExamPaperListResponse(BaseModel):
    items:  list[ExamPaperResponse]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# ExamQuestion schemas
# ---------------------------------------------------------------------------

class MCQOption(BaseModel):
    label: str  # "A", "B", "C", "D"
    text:  str


class MarkingCriterion(BaseModel):
    criterion:   str
    marks:       float
    description: str


class ExamQuestionResponse(BaseModel):
    id:             UUID
    exam_paper_id:  UUID
    unit_number:    int
    # Every unit the question draws on (P1.19). unit_number stays the PRIMARY
    # unit; a definition that INTEGRATES a pool lists the whole pool here. NULL
    # on legacy rows, which cover unit_number alone.
    unit_numbers:   list[Any] | None = None
    difficulty:     str | None = None
    co_code:        str | None
    bloom_level:    str
    question_type:  str
    question_text:  str
    options:        list[Any] | None      # MCQ options (no correct_option exposed here)
    marks:          float
    set_membership: list[str]
    section_label:  str | None
    choice_group:   int | None
    co_ids:         list[Any] | None
    ai_generated:   bool
    is_edited:      bool
    display_order:  int
    template_block_id:      str | None
    template_subpart_index: int | None
    created_at:     datetime
    updated_at:     datetime | None
    # model_answer and correct_option exposed only in answers export (role-gated)

    model_config = {"from_attributes": True}


class ExamQuestionWithAnswerResponse(ExamQuestionResponse):
    """Includes model answer — only for faculty/board/admin post-release export."""
    model_answer:   str | None
    correct_option: str | None
    marking_scheme: list[Any] | None


class ExamQuestionUpdate(BaseModel):
    question_text:   str | None = None
    options:         list[MCQOption] | None = None
    correct_option:  str | None = None
    marks:           float | None = Field(default=None, gt=0)
    model_answer:    str | None = None
    marking_scheme:  list[MarkingCriterion] | None = None
    set_membership:  list[str] | None = None
    bloom_level:     str | None = None
    unit_number:     int | None = None       # editable unit mapping
    co_code:         str | None = None
    section_label:   str | None = None
    choice_group:    int | None = None
    co_ids:          list[UUID] | None = None

    @field_validator("bloom_level", mode="before")
    @classmethod
    def _norm_bloom(cls, v: str | None) -> str | None:
        return v.upper().strip() if v else v

    @field_validator("set_membership", mode="before")
    @classmethod
    def _norm_sets(cls, v: list | None) -> list | None:
        if v is None:
            return v
        return [str(s).upper().strip() for s in v]


class ManualQuestionCreate(BaseModel):
    """Add a hand-written question to a paper (manual builder). Coexists with
    AI-generated questions; stored with ai_generated=False."""
    question_text:   str = Field(..., min_length=1)
    question_type:   str = Field(default="SHORT_ANSWER")
    marks:           float = Field(..., gt=0, le=999.99)
    bloom_level:     str = Field(default="REMEMBER")
    unit_number:     int = Field(default=1, ge=0)
    co_code:         str | None = None
    co_ids:          list[UUID] | None = None
    options:         list[MCQOption] | None = None
    correct_option:  str | None = None
    model_answer:    str | None = None
    marking_scheme:  list[MarkingCriterion] | None = None
    section_label:   str | None = None
    set_membership:  list[str] = Field(default_factory=lambda: ["A", "B"])
    # Which template block this question belongs to. Required in practice on a
    # paper that has a template: a question with no block has nowhere to print,
    # and inventing an "other" bucket for it would misrepresent the paper.
    template_block_id:      str | None = None
    template_subpart_index: int | None = Field(default=None, ge=0)

    @field_validator("bloom_level", mode="before")
    @classmethod
    def _norm_bloom(cls, v: str | None) -> str | None:
        return v.upper().strip() if v else "REMEMBER"

    @field_validator("question_type", mode="before")
    @classmethod
    def _norm_type(cls, v: str | None) -> str | None:
        return v.upper().replace(" ", "_").strip() if v else "SHORT_ANSWER"


class QuestionReorderRequest(BaseModel):
    """Full ordered list of question ids for the paper; index becomes display_order."""
    ordered_ids: list[UUID] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Bloom's compliance report schema
# ---------------------------------------------------------------------------

class BloomsViolation(BaseModel):
    level:         str
    requested_pct: float
    actual_pct:    float
    delta_pct:     float


class BloomsComplianceResponse(BaseModel):
    id:               UUID
    exam_paper_id:    UUID
    requested_dist:   dict[str, Any]
    actual_dist:      dict[str, Any]
    compliance_ok:    bool
    violations:       list[Any]
    co_coverage_ok:   bool | None
    unit_coverage_ok: bool | None
    generated_at:     datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Workflow action schemas
# ---------------------------------------------------------------------------

class BoardDecisionRequest(BaseModel):
    approved:      bool
    board_comment: str | None = None

    @model_validator(mode="after")
    def comment_required_on_return(self) -> "BoardDecisionRequest":
        if not self.approved and not self.board_comment:
            raise ValueError("board_comment is required when returning a paper.")
        return self


class SealRequest(BaseModel):
    release_at: datetime = Field(
        ...,
        description="UTC datetime when the paper should be auto-released. Must be in the future.",
    )

    @model_validator(mode="after")
    def must_be_future(self) -> "SealRequest":
        from datetime import timezone
        now = datetime.now(timezone.utc)
        # Ensure timezone-aware comparison
        ra = self.release_at
        if ra.tzinfo is None:
            from datetime import timezone
            ra = ra.replace(tzinfo=timezone.utc)
        if ra <= now:
            raise ValueError("release_at must be in the future.")
        return self


# ---------------------------------------------------------------------------
# Job status polling
# ---------------------------------------------------------------------------

class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# H-35 workflow action schemas
# ---------------------------------------------------------------------------

class FacultyApproveRequest(BaseModel):
    """INTERNAL workflow: faculty self-approves the paper (Gate 1 only)."""
    faculty_comment: str | None = None


class ScrutinizerAssignRequest(BaseModel):
    """Assign a second-faculty scrutinizer — BOARD_EXAM workflow only."""
    scrutinizer_id: UUID


class ScrutinizerDecisionRequest(BaseModel):
    approved:           bool
    scrutinizer_comment: str | None = None

    @model_validator(mode="after")
    def _comment_required_on_return(self) -> "ScrutinizerDecisionRequest":
        if not self.approved and not self.scrutinizer_comment:
            raise ValueError("scrutinizer_comment is required when returning a paper.")
        return self


class RegenerateQuestionRequest(BaseModel):
    """Optional guidance for single-question regeneration."""
    instruction: str | None = None


# ---------------------------------------------------------------------------
# H-35 InternalMarks schemas  (Addition 2)
# ---------------------------------------------------------------------------

class InternalMarksCreate(BaseModel):
    student_id:      UUID
    course_id:       UUID
    semester:        int   = Field(..., gt=0, le=12)
    academic_year:   str   = Field(..., min_length=4, max_length=10,
                                   description='e.g. "2025-26"')
    internal1_marks: float | None = Field(default=None, ge=0)
    internal2_marks: float | None = Field(default=None, ge=0)
    assignment_marks: float | None = Field(default=None, ge=0)
    attendance_marks: float | None = Field(default=None, ge=0)
    max_internal:    int   = Field(default=40, gt=0)


class InternalMarksUpdate(BaseModel):
    internal1_marks:  float | None = Field(default=None, ge=0)
    internal2_marks:  float | None = Field(default=None, ge=0)
    assignment_marks: float | None = Field(default=None, ge=0)
    attendance_marks: float | None = Field(default=None, ge=0)


class InternalMarksResponse(BaseModel):
    id:               UUID
    student_id:       UUID
    course_id:        UUID
    semester:         int
    academic_year:    str
    internal1_marks:  float | None
    internal2_marks:  float | None
    assignment_marks: float | None
    attendance_marks: float | None
    total_internal:   float | None
    max_internal:     int
    status:           str
    submitted_by:     UUID | None
    submitted_at:     datetime | None
    locked_by:        UUID | None
    locked_at:        datetime | None
    created_at:       datetime
    updated_at:       datetime | None

    model_config = {"from_attributes": True}


class InternalMarksListResponse(BaseModel):
    items:  list[InternalMarksResponse]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# H-35 QuestionBank schemas  (Addition 1)
# ---------------------------------------------------------------------------

class QuestionBankEntryResponse(BaseModel):
    id:              UUID
    course_id:       UUID
    source_paper_id: UUID | None
    unit_number:     int
    co_ids:          list[Any] | None
    bloom_level:     str
    question_type:   str
    question_text:   str
    options:         list[Any] | None
    marks:           float
    model_answer:    str | None
    marking_scheme:  list[Any] | None
    section_label:   str | None
    is_approved:     bool
    usage_count:     int
    ai_generated:    bool
    created_at:      datetime
    updated_at:      datetime | None

    model_config = {"from_attributes": True}


class QuestionBankListResponse(BaseModel):
    items:  list[QuestionBankEntryResponse]
    total:  int
    offset: int
    limit:  int
