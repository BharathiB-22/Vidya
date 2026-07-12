from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.auth.models import GovernanceType
from app.core.governance.models import ApprovalRequestStatus
from app.modules.m01_program_advisor.models import CourseType


# ---------------------------------------------------------------------------
# Governance identity — what this tenant calls its authority
# ---------------------------------------------------------------------------

class GovernanceInfo(BaseModel):
    """The tenant's governance display vocabulary.

    Behaviour is identical for every governance_type; only the words change.
    The frontend renders `body_label` / `member_label` everywhere it would
    otherwise hardcode "Board".
    """
    governance_type: GovernanceType
    body_label: str        # "Board"        | "University Members"
    member_label: str      # "Board Member" | "University Member"


# ---------------------------------------------------------------------------
# Approval requests
# ---------------------------------------------------------------------------

class ApprovalRequestOut(BaseModel):
    id: UUID
    program_id: UUID
    cycle: int
    status: ApprovalRequestStatus
    submitted_by_user_id: UUID
    submitted_by_name: Optional[str] = None
    submitted_at: datetime
    submission_note: Optional[str] = None
    decided_by_user_id: Optional[UUID] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_comment: Optional[str] = None

    model_config = {"from_attributes": True}


class SubmitForApprovalRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


class ApproveCurriculumRequest(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Submission checklist — what the Dean must finish before handing over
# ---------------------------------------------------------------------------

class SubmissionCheckItem(BaseModel):
    """One line of the Dean's pre-submission checklist.

    `section` is where the fix lives, so the UI can take the Dean straight there
    instead of leaving them to hunt for it:

        settings    the Academic Year / Batch fields on the programme
        structure   semesters, subjects, credits, course codes
        electives   elective baskets and their options
        outcomes    programme outcomes
        compliance  the compliance report
    """
    key: str
    label: str                     # "Academic Year selected"
    passed: bool
    blocking: bool                 # False = a warning; it will not stop the submission
    detail: Optional[str] = None   # "Semester 4 has no subjects"
    section: str


class SubmissionChecklist(BaseModel):
    """Everything standing between a Dean and the handover.

    Submitting is irreversible — the Dean never gets the curriculum back — so this
    is deliberately shown as a checklist BEFORE the act rather than as an error
    afterwards. `can_submit` is true when no blocking item has failed; warnings do
    not stop a submission, they just say what the Board will find.
    """
    program_id: UUID
    can_submit: bool
    items: list[SubmissionCheckItem]
    first_failing_section: Optional[str] = None


# ---------------------------------------------------------------------------
# Readiness — what is left before the curriculum can be approved
# ---------------------------------------------------------------------------

class ReadinessItem(BaseModel):
    """One subject and the state of its official document.

    `syllabus_status is None` means the subject has no document at all — the
    commonest reason a curriculum cannot yet be approved.
    """
    course_id: UUID
    course_code: str
    course_title: str
    semester: int
    is_elective: bool
    basket_name: Optional[str] = None      # which elective slot, if any
    syllabus_id: Optional[UUID] = None
    syllabus_status: Optional[str] = None  # DRAFT | AI_GENERATING | APPROVED | LOCKED

    # WHICH document this subject carries — THEORY | LAB | INTERNSHIP |
    # MINI_PROJECT | MAJOR_PROJECT | SEMINAR. The dashboard says "Lab Manual" or
    # "Internship Guidelines" rather than "Syllabus" for the ones that are not one.
    course_type: str = CourseType.THEORY.value

    # What is still WRONG with the document — "Missing: Reference Books",
    # "Unit IV weak". Empty when there is nothing to flag.
    #
    # Advisory: gaps do NOT block approval. A Board may knowingly approve a syllabus
    # with no suggested reading, and a gate that let a missing web-resource list
    # stop an entire curriculum would be intolerable. What gaps do is tell the Board
    # WHERE to look — the dangerous document is not the one that is obviously
    # missing, it is the one that looks finished and has three topics in Unit IV.
    gaps: list[str] = []


class ReadinessSummary(BaseModel):
    """The Board's worksheet, and the approve gate's evidence.

    `can_approve` is computed from the same rows the gate in
    `approve_and_lock` tests, so the button in the UI and the API can never
    disagree about whether a curriculum is ready.
    """
    program_id: UUID
    total_subjects: int
    approved_count: int
    draft_count: int
    missing_count: int
    can_approve: bool
    items: list[ReadinessItem]


# ---------------------------------------------------------------------------
# Change summary — what the Board did, shown to the Dean before publishing
# ---------------------------------------------------------------------------

class ChangeSummaryLine(BaseModel):
    label: str      # "Added subject"
    count: int      # 2


class ChangeSummary(BaseModel):
    """Derived from the audit log, not a bespoke table. Covers only the Board's
    tenure — events raised after the Dean submitted."""
    program_id: UUID
    total_changes: int
    lines: list[ChangeSummaryLine]


# ---------------------------------------------------------------------------
# The governance trail — the Board's accountability record
# ---------------------------------------------------------------------------

class TrailEntry(BaseModel):
    """One governance action: who did what, in what capacity, and when.

    The Board has no separation of duties — a single member may enhance a
    curriculum, write its syllabus and approve it alone — so accountability rests
    entirely on this record. It is assembled from the append-only audit log, which
    means no entry here can be altered or removed after the fact.
    """
    event_type: str
    action: str                    # "Approved the curriculum"
    category: str                  # SUBMIT | REVIEW | MODIFY | SYLLABUS | APPROVE | PUBLISH
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    at: datetime
    detail: Optional[str] = None   # "12 subjects", a course code, an approval note


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

class QueueItem(BaseModel):
    """One curriculum in front of, or already decided by, the Board."""
    program_id: UUID
    title: str
    department: str
    degree_type: str
    version: int
    status: str
    total_credits: int
    duration_years: int
    regulation_year: Optional[int] = None
    academic_year: Optional[str] = None
    batch_name: Optional[str] = None
    course_count: int
    elective_slot_count: int
    syllabus_count: int
    approved_syllabus_count: int = 0
    submitted_at: Optional[datetime] = None
    submitted_by_name: Optional[str] = None
    submission_note: Optional[str] = None
    locked_at: Optional[datetime] = None
    published_at: Optional[datetime] = None


class GovernanceQueueResponse(BaseModel):
    pending: list[QueueItem]
    approved: list[QueueItem]
    published: list[QueueItem]


# ---------------------------------------------------------------------------
# Bulk syllabus generation
# ---------------------------------------------------------------------------

class GenerateSyllabiRequest(BaseModel):
    regenerate_all: bool = Field(
        default=False,
        description=(
            "By default only subjects with NO syllabus are generated, so a "
            "re-run after a partial failure picks up exactly what failed and "
            "leaves the Board's edits alone. Set true to regenerate every "
            "subject from scratch, discarding Board edits to unapproved drafts."
        ),
    )
    custom_instructions: Optional[str] = Field(default=None, max_length=4000)


class GenerateSyllabiResponse(BaseModel):
    program_id: UUID
    batch_id: UUID
    dispatched: int          # how many subjects were queued for generation
    skipped: int             # already had a syllabus (and regenerate_all was false)
    job_ids: list[UUID]
