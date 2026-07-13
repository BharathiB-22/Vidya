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

class ChecklistItem(BaseModel):
    """One stage of a document's academic lifecycle, as the Board reads it.

    A STAGE, never a rule. "Unit IV — AI generation incomplete" is a stage; "Unit IV has
    2 topics and a unit runs to 10-15" is our validator talking out loud, and a Board
    member who reads it learns only that we do not trust our own generator. The
    thresholds, the duplicate detection, the retry counts and the topic floors stay in
    the backend, where they belong, and nothing here carries them.

    DONE        finished, and good enough to publish
    INCOMPLETE  it exists but the AI did not finish it — one click repairs it
    PENDING     not there yet
    """
    key: str            # "unit_3", "objectives", "approved"
    label: str          # "Unit III", "Objectives", "Board Approval"
    state: str          # DONE | INCOMPLETE | PENDING
    unit_number: Optional[int] = None   # set on unit rows, so the UI can regenerate one

    # Shown, but NOT enforced by the approval gate.
    #
    # Exactly one stage is optional today: the References. They are fetched from CrossRef
    # and OpenLibrary, and a third-party outage must never be able to block a
    # university's curriculum. Everything else on every checklist is tested by the gate
    # — that is the rule, and this flag exists so that the one exception has to be
    # declared out loud rather than quietly tolerated. The UI marks it "(optional)" and
    # it is excluded from the completion percentage, so 100% means "approvable", not
    # "approvable, probably".
    optional: bool = False


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

    # WHO owns this document — "BOARD" or "DEAN".
    #
    # The Board teaches, examines and owns the syllabus of theory subjects,
    # laboratories and elective options. An internship, a project and a seminar are the
    # Dean's: what they contain depends on the host company, the supervisor and the
    # review calendar, and no Board of Studies can know those at approval time.
    #
    # A DEAN item appears in the Board's worksheet so the curriculum can be SEEN whole,
    # and does nothing else: no gaps, no actions, and no weight in `can_approve`.
    owner: str = "BOARD"

    # Where this document stands, stage by stage, and how far along it is (0-100).
    # Measured against ITS OWN checklist — a theory syllabus against its units and
    # outcomes, an internship against the Dean's four steps.
    checklist: list[ChecklistItem] = []
    progress_percent: int = 0

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

    TWO progress figures, because there are two bodies at work and they are not waiting
    on each other. The Board's is the taught curriculum — the only thing its approval
    gate tests. The Dean's is the execution documents, which he prepares and approves in
    his own time and which gate his PUBLISH, not the Board's approval. One combined
    percentage would tell each of them how much work the other still had to do.
    """
    program_id: UUID
    total_subjects: int
    approved_count: int
    draft_count: int
    missing_count: int
    can_approve: bool

    # How far the BOARD is, across the subjects it teaches (0-100).
    board_progress_percent: int = 0
    # How far the DEAN is, across his execution documents (0-100). 100 when the
    # curriculum contains none — nothing outstanding is nothing outstanding.
    dean_progress_percent: int = 100
    dean_document_count: int = 0

    # THE SECOND GATE. The Dean may publish when the Board has approved the taught
    # curriculum AND every one of his own documents is approved.
    #
    # Computed from the same rows the publish endpoint tests, so the button and the API
    # can never disagree — the same discipline as `can_approve`.
    can_publish: bool = False
    dean_approved_count: int = 0

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
# Publishing — the Dean's gate
#
# (There is no bulk-generation schema here any more. The Board no longer generates
# forty syllabi on one click; it decides subject by subject whether a syllabus wants an
# AI draft or a human author. See governance/router.py.)
# ---------------------------------------------------------------------------

class PublishReadiness(BaseModel):
    """The DEAN's gate, and only his.

    A projection of the same readiness computation the Board's worksheet uses — the same
    rows, the same rules, one source of truth — but showing only what is HIS: the
    execution documents, and whether the curriculum may now be released.

    It is a separate endpoint rather than the Board's, for two reasons. The Board's
    worksheet is gated to the governance authority, and opening it is itself recorded as
    an act of review — a Dean checking whether he can publish must not appear in the
    Board's accountability trail as having reviewed the curriculum. And he has no
    business seeing which teaching subjects are still in draft: that is the Board's work,
    and it is not waiting on him.
    """
    program_id: UUID
    program_status: str

    # True when the Board has approved the taught curriculum AND every execution document
    # is approved by the Dean. Computed from the rows m01.publish tests, so this and the
    # endpoint cannot disagree.
    can_publish: bool

    total_documents: int
    approved_documents: int
    documents: list[ReadinessItem] = []

