"""
SIS Hall Ticket Eligibility — H58 Pydantic schemas.

Eligibility workflow:
  1. POST /hall-tickets/eligibility/compute   → creates DRAFT rows
  2. POST /hall-tickets/eligibility/{id}/override  → Dean overrides (still DRAFT or PUBLISHED)
  3. POST /hall-tickets/eligibility/publish        → DRAFT → PUBLISHED
  4. GET  /hall-tickets/my-eligibility             → students see PUBLISHED only
  5. POST /hall-tickets/batches                    → requires PUBLISHED; assigns hall_ticket_number
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Compute request
# ---------------------------------------------------------------------------

class EligibilityComputeIn(BaseModel):
    semester_id:     UUID
    section_id:      Optional[UUID] = None     # None = all sections in semester
    threshold_pct:   float          = Field(75.0, ge=0.0, le=100.0)


class EligibilityPublishIn(BaseModel):
    semester_id:  UUID
    section_id:   Optional[UUID] = None    # None = publish all DRAFT in semester


# ---------------------------------------------------------------------------
# Override request (Dean / Admin human gate)
# ---------------------------------------------------------------------------

class EligibilityOverrideIn(BaseModel):
    status: str = Field(..., pattern="^(ELIGIBLE|CONDITIONAL)$")
    reason: str = Field(..., min_length=20, max_length=1000)


# ---------------------------------------------------------------------------
# Batch generation request
# ---------------------------------------------------------------------------

class HallTicketBatchCreateIn(BaseModel):
    semester_id:  UUID
    section_id:   Optional[UUID] = None    # None = all sections
    notes:        Optional[str]  = None


# ---------------------------------------------------------------------------
# Eligibility row output
# ---------------------------------------------------------------------------

class EligibilityCheckItem(BaseModel):
    check_name: str
    passed:     bool
    detail:     str


class EligibilityOut(BaseModel):
    id:             UUID
    student_id:     UUID
    student_name:   str
    usn:            Optional[str]
    email:          str
    semester_id:    UUID
    publish_status: str                    # DRAFT | PUBLISHED
    status:         str                    # ELIGIBLE | NOT_ELIGIBLE | CONDITIONAL
    computed_at:    Optional[datetime]

    # Snapshot
    attendance_threshold_used: Decimal
    computed_academic_year:    str
    computed_semester_name:    str

    # Check results
    attendance_pct:   Optional[Decimal]
    has_shortage:     bool
    marks_all_locked: bool
    marks_all_filled: bool
    failure_reasons:  list[str]

    # Override
    is_overridden:   bool
    override_by:     Optional[UUID]
    override_at:     Optional[datetime]
    override_reason: Optional[str]
    override_status: Optional[str]

    # Hall ticket
    hall_ticket_number: Optional[str]
    batch_id:           Optional[UUID]

    # Future exam fields
    exam_session_id:  Optional[UUID]
    exam_schedule_id: Optional[UUID]
    exam_center_id:   Optional[UUID]
    room_number:      Optional[str]
    seat_number:      Optional[str]

    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Dashboard (Dean / Admin)
# ---------------------------------------------------------------------------

class EligibilityDashboardOut(BaseModel):
    semester_id:         UUID
    semester_name:       str
    total_students:      int
    eligible_count:      int
    not_eligible_count:  int
    conditional_count:   int
    draft_count:         int
    published_count:     int
    rows:                list[EligibilityOut]


# ---------------------------------------------------------------------------
# Compute result summary
# ---------------------------------------------------------------------------

class EligibilityComputeResult(BaseModel):
    semester_id:     UUID
    section_id:      Optional[UUID]
    threshold_pct:   float
    processed:       int
    eligible_count:  int
    not_eligible_count: int
    skipped_overridden: int


# ---------------------------------------------------------------------------
# Publish result summary
# ---------------------------------------------------------------------------

class EligibilityPublishResult(BaseModel):
    semester_id:   UUID
    published:     int
    already_published: int


# ---------------------------------------------------------------------------
# Student self-view (PUBLISHED only)
# ---------------------------------------------------------------------------

class EligibilityCheckItemOut(BaseModel):
    check_name: str
    passed:     bool
    detail:     str


class MyEligibilityOut(BaseModel):
    student_id:         UUID
    student_name:       str
    usn:                Optional[str]
    semester_id:        UUID
    semester_name:      str
    status:             str               # ELIGIBLE | NOT_ELIGIBLE | CONDITIONAL
    checklist:          list[EligibilityCheckItemOut]
    failure_reasons:    list[str]
    hall_ticket_number: Optional[str]
    is_ticket_available: bool             # True if status in (ELIGIBLE, CONDITIONAL) and number assigned

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Faculty advisory view (read-only, own sections only)
# ---------------------------------------------------------------------------

class AdvisoryStudentRow(BaseModel):
    student_id:      UUID
    student_name:    str
    usn:             Optional[str]
    attendance_pct:  Optional[Decimal]
    has_shortage:    bool
    marks_all_locked: bool
    marks_all_filled: bool
    status:          Optional[str]        # None if not yet computed
    publish_status:  Optional[str]        # None if not yet computed


class FacultyAdvisoryOut(BaseModel):
    section_id:    UUID
    section_name:  str
    course_code:   Optional[str]
    semester_id:   UUID
    semester_name: str
    students:      list[AdvisoryStudentRow]


# ---------------------------------------------------------------------------
# Hall ticket batch output
# ---------------------------------------------------------------------------

class HallTicketBatchOut(BaseModel):
    id:            UUID
    semester_id:   UUID
    semester_name: Optional[str]
    scope:         str
    scope_ref_id:  Optional[UUID]
    generated_by:  UUID
    generated_at:  datetime
    ticket_count:  int
    ticket_prefix: str
    notes:         Optional[str]
    created_at:    datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Individual hall ticket view
# ---------------------------------------------------------------------------

class HallTicketOut(BaseModel):
    hall_ticket_number:   str
    student_id:           UUID
    student_name:         str
    usn:                  Optional[str]
    semester_id:          UUID
    semester_name:        str
    academic_year:        str
    status:               str             # ELIGIBLE | CONDITIONAL
    batch_id:             UUID
    issued_at:            datetime

    # Future exam fields (null until scheduled)
    exam_session_id:  Optional[UUID]
    exam_schedule_id: Optional[UUID]
    exam_center_id:   Optional[UUID]
    room_number:      Optional[str]
    seat_number:      Optional[str]
