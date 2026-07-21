"""
M04 Assignments — Pydantic schemas.

Request / response models for the HTTP layer only.
Business logic lives in service.py; DB logic in repository.py.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_ASSIGNMENT_TYPES = ("ESSAY", "CASE_STUDY", "REPORT", "HOMEWORK", "OTHER")


# ---------------------------------------------------------------------------
# Assignment questions
# ---------------------------------------------------------------------------

class AssignmentQuestion(BaseModel):
    """One question in the assignment's question builder.

    `marks` is per-question; across the whole assignment they sum to max_marks
    (checked in the service, where the max is known). Kept as a plain value
    object — the questions live inline on the assignment (JSONB), not as rows.
    """
    question_number: int = Field(ge=1)
    question_text:   str = Field(min_length=1)
    marks:           float = Field(gt=0)
    notes:           str | None = None


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    instructions: str | None = None
    assignment_type: str = "HOMEWORK"
    syllabus_id: UUID | None = None
    max_marks: float = Field(gt=0)
    weightage_percent: float | None = Field(default=None, ge=0, le=100)
    due_date: datetime | None = None
    allow_late: bool = True
    late_penalty_percent: float | None = Field(default=None, ge=0, le=100)
    max_attempts: int = Field(default=1, ge=1, le=10)
    allowed_file_types: list[str] = Field(default_factory=list)
    # The evaluator(s) this coursework should route to. Each student submission
    # becomes one work item against these, round-robin, through the existing M09.6
    # engine. Empty = nobody nominated; the department allocates by hand as before.
    evaluator_user_ids: list[UUID] = Field(default_factory=list)
    # The question builder. Empty = no structured questions (a question paper may
    # be uploaded instead, or none at all). When non-empty, marks must sum to
    # max_marks — enforced in the service.
    questions: list[AssignmentQuestion] = Field(default_factory=list)
    # S3 object key of an uploaded question paper (.pdf/.docx), the fallback when
    # no structured questions are entered.
    question_paper_url: str | None = None

    @field_validator("assignment_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in _ASSIGNMENT_TYPES:
            raise ValueError(f"assignment_type must be one of {_ASSIGNMENT_TYPES}")
        return v


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    instructions: str | None = None
    assignment_type: str | None = None
    max_marks: float | None = Field(default=None, gt=0)
    weightage_percent: float | None = Field(default=None, ge=0, le=100)
    due_date: datetime | None = None
    allow_late: bool | None = None
    late_penalty_percent: float | None = Field(default=None, ge=0, le=100)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    allowed_file_types: list[str] | None = None
    evaluator_user_ids: list[UUID] | None = None
    questions: list[AssignmentQuestion] | None = None
    question_paper_url: str | None = None


class AssignmentProgress(BaseModel):
    """How far one assignment has travelled, derived on read.

    The owning faculty hands a closed assignment to the department and, until
    now, lost sight of it. This is that visibility: every number is computed
    from assignment_submissions, assignment_evaluations and the M09.6 ledger at
    request time, so there is nothing to keep in sync and no second source of
    truth. AI counts are advisory state only — they never imply a mark.
    """
    total_students:           int = 0
    submitted_count:          int = 0
    graded_count:             int = 0
    late_count:               int = 0
    # Advisory AI pipeline (PENDING/EXTRACTING/EVALUATING collapse into pending).
    ai_completed_count:       int = 0
    ai_failed_count:          int = 0
    ai_pending_count:         int = 0
    # Submissions an evaluator currently owns, per the M09.6 assignment engine.
    evaluator_assigned_count: int = 0


class AssignmentResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    instructions: str | None
    assignment_type: str
    syllabus_id: UUID | None
    max_marks: float
    weightage_percent: float | None
    due_date: datetime | None
    allow_late: bool
    late_penalty_percent: float | None
    max_attempts: int
    allowed_file_types: list[str]
    evaluator_user_ids: list[UUID] = Field(default_factory=list)
    questions: list[AssignmentQuestion] = Field(default_factory=list)
    question_paper_url: str | None = None
    status: str
    created_by_user_id: UUID
    published_at: datetime | None
    closed_at: datetime | None
    submitted_at: datetime | None = None
    submitted_by_user_id: UUID | None = None
    finalized_at: datetime | None = None
    finalized_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None
    # Enriched from syllabi -> courses join (populated on detail endpoints only)
    course_title: str | None = None
    course_code: str | None = None
    # Display names resolved on the detail endpoint (ids are otherwise opaque to
    # an evaluator opening the assignment).
    created_by_name: str | None = None
    evaluator_names: list[str] = Field(default_factory=list)
    # Live evaluation progress, populated on the list + detail endpoints so the
    # owning faculty sees the state of their coursework without opening it.
    # None = not computed for this response (e.g. the student-facing list).
    progress: AssignmentProgress | None = None

    @field_validator("evaluator_user_ids", "questions", mode="before")
    @classmethod
    def _null_is_empty(cls, v: object) -> object:
        # These columns are nullable — "none set" reads as [] to every caller
        # rather than making each one handle null.
        return [] if v is None else v

    model_config = {"from_attributes": True}


class MyTeachingCourse(BaseModel):
    """One course the calling faculty teaches (from subject_assignments), with the
    latest LOCKED/APPROVED syllabus resolved. Drives the create form's course
    picker — scoped to the faculty's own load — so syllabus_id binds automatically
    and a course without an approved syllabus is blocked with a clear message."""
    course_id:             UUID
    course_code:           str
    course_title:          str
    semester:              int | None = None
    section_id:            UUID | None = None
    section_name:          str | None = None
    syllabus_id:           UUID | None = None
    has_approved_syllabus: bool = False


class EligibleEvaluator(BaseModel):
    """A user who may be allocated coursework to evaluate."""
    id:        UUID
    full_name: str | None = None
    email:     str | None = None
    role:      str


class MyCourseworkEvaluation(BaseModel):
    """One ASSIGNMENT the calling evaluator is assigned to.

    Assignment-centric (not submission-centric): it appears the moment the
    faculty publishes, before any student has submitted, so the evaluator can
    open it, read the questions/rubric, and prepare. Per-evaluator counts show
    how much of their allocated work is done."""
    assignment_id:     UUID
    assignment_title:  str
    assignment_status: str
    course_title:      str | None = None
    course_code:       str | None = None
    semester:          int | None = None
    sections:          str | None = None
    faculty_name:      str | None = None
    evaluator_names:   str | None = None
    due_date:          datetime | None = None
    max_marks:         float
    question_count:    int = 0
    total_submissions: int = 0
    # Assignment-level progress (the whole class) for the home card.
    total_students:     int = 0
    submitted_students: int = 0
    reviewed_students:  int = 0
    pending_submission: int = 0
    pending_review:     int = 0
    # Evaluator's own slice.
    allocated_to_me:   int = 0
    graded_by_me:      int = 0
    pending_for_me:    int = 0


# ---------------------------------------------------------------------------
# Evaluation Center — the coursework-specific evaluator workspace. One
# assignment's full class roster (every enrolled student, submitted or not),
# plus live progress. Backed by Assignment (visibility from publish) + the
# enrollment roster + submissions — never by the allocation ledger alone, so a
# student who has not submitted still appears.
# ---------------------------------------------------------------------------

class EvaluationCenterStudent(BaseModel):
    student_user_id:   UUID
    student_name:      str | None = None
    student_usn:       str | None = None
    # Display status, derived: NOT_SUBMITTED | SUBMITTED | UNDER_REVIEW | REVIEWED.
    # UNDER_REVIEW = submitted AND allocated to an evaluator but not yet graded.
    submission_status: str
    submission_id:     UUID | None = None
    is_late:           bool = False
    submitted_at:      datetime | None = None
    marks_obtained:    float | None = None
    graded_at:         datetime | None = None
    evaluator_user_id: UUID | None = None
    evaluator_name:    str | None = None
    # Advisory AI state for this student's latest attempt; None = no row yet.
    ai_status:         str | None = None


class EvaluationCenterProgress(BaseModel):
    total_students:     int = 0
    submitted:          int = 0
    pending_submission: int = 0
    reviewed:           int = 0
    pending_review:     int = 0
    # Advisory AI pipeline across the roster (counted from the same rows).
    ai_completed:       int = 0
    ai_failed:          int = 0


class AiEvaluationResponse(BaseModel):
    """The ADVISORY AI evaluation of one submission. Read-only; never a mark of
    record. `status` drives the evaluator UI (PENDING/EXTRACTING/EVALUATING/
    COMPLETED/FAILED)."""
    submission_id:           UUID
    status:                  str
    # Submission summary
    extracted_text:          str | None = None
    word_count:              int | None = None
    file_type:               str | None = None
    # Suggested marks (advisory)
    suggested_marks:         list[dict] | None = None
    overall_suggested_marks: float | None = None
    percentage:              float | None = None
    confidence_level:        str | None = None
    # Feedback / rubric / bloom / CO
    feedback:                dict | None = None
    rubric_scores:           list[dict] | None = None
    bloom_analysis:          dict | None = None
    co_analysis:             dict | None = None
    # Similarity (internal only)
    similarity_score:        float | None = None
    similarity_matches:      list[dict] | None = None
    plagiarism_status:       str = "PLACEHOLDER"
    # Reliability / reproducibility
    ai_model:                str | None = None
    provider_used:           str | None = None
    fallback_chain:          str | None = None
    processing_ms:           int | None = None
    error_log:               str | None = None
    retry_count:             int = 0

    model_config = {"from_attributes": True}


class EvaluationCenterResponse(BaseModel):
    assignment: AssignmentResponse
    # Course semester, resolved from the syllabus -> course chain (the assignment
    # itself does not carry it). Shown in the header so the evaluator has full
    # context before any submission arrives.
    semester:   int | None = None
    progress:   EvaluationCenterProgress
    students:   list[EvaluationCenterStudent] = Field(default_factory=list)


class AssignEvaluatorRequest(BaseModel):
    """Allocate one student submission to one evaluator.

    The allocation itself is recorded by the M09.6 assignment engine, which is the
    single ledger for evaluation work; this is just the coursework-facing way in.
    """
    evaluator_user_id: UUID
    due_at:            datetime | None = None
    notes:             str | None = None


class AssignmentListResponse(BaseModel):
    items: list[AssignmentResponse]
    total: int
    offset: int
    limit: int


class AssignmentStatistics(BaseModel):
    total_students: int
    submitted_count: int
    graded_count: int
    late_count: int
    average_marks: float | None
    # Advisory AI pipeline + evaluator allocation, so the faculty header can show
    # the whole evaluation state in one place. Defaulted: older clients ignore them.
    ai_completed_count:       int = 0
    ai_failed_count:          int = 0
    ai_pending_count:         int = 0
    evaluator_assigned_count: int = 0


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

class SubmissionCreate(BaseModel):
    content_text: str | None = None
    # For file uploads: client uses the generic storage presigned-upload flow,
    # then passes the returned object_key here.
    content_url: str | None = None


class SubmissionResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    student_user_id: UUID
    attempt_number: int
    content_url: str | None
    # content_text omitted from list view — too large; included in detail below
    submitted_at: datetime
    is_late: bool
    status: str
    marks_obtained: float | None
    feedback: str | None
    graded_by_user_id: UUID | None
    graded_at: datetime | None
    returned_at: datetime | None
    # Enriched (faculty submissions list only)
    student_name: str | None = None
    # Who the M09.6 engine currently has evaluating this submission; None until
    # the department allocates one. Read from that ledger, never stored here.
    evaluator_user_id: UUID | None = None
    evaluator_name: str | None = None
    # Advisory AI evaluation state for this submission (PENDING/EXTRACTING/
    # EVALUATING/COMPLETED/FAILED). None = the worker has not produced a row.
    # Status only — the suggestions themselves stay on the detail endpoint.
    ai_status: str | None = None
    # What the EVALUATOR recommended, preserved permanently and shown only to the
    # assignment's owner so they can compare it against their own decision.
    # NULL when the owner graded it themselves, or on pre-0103ten rows.
    evaluator_marks_obtained: float | None = None
    evaluator_feedback: str | None = None

    model_config = {"from_attributes": True}

    def for_student(self) -> "SubmissionResponse":
        """This submission as a STUDENT may see it before release.

        Everything the faculty has not yet released is stripped: marks, feedback,
        who graded it and when, the evaluator's recommendation, and the AI
        pipeline state. What remains is the student's own submission and whether
        it is still being evaluated — which is all they are entitled to until the
        owning faculty releases the results.
        """
        return self.model_copy(update={
            "marks_obtained":           None,
            "feedback":                 None,
            "graded_by_user_id":        None,
            "graded_at":                None,
            "evaluator_user_id":        None,
            "evaluator_name":           None,
            "evaluator_marks_obtained": None,
            "evaluator_feedback":       None,
            "ai_status":                None,
        })


class SubmissionDetailResponse(SubmissionResponse):
    content_text: str | None

    model_config = {"from_attributes": True}


class SubmissionListResponse(BaseModel):
    items: list[SubmissionResponse]
    total: int
    offset: int
    limit: int


class GradeSubmissionRequest(BaseModel):
    marks_obtained: float = Field(ge=0)
    feedback: str | None = None
