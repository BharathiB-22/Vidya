"""
SIS Results Management — H60 Pydantic schemas.

Covers:
  Grading Policy + Bands
  Result Declarations (CRUD + lifecycle)
  External Marks (bulk sheet + entry)
  Result Computation
  Grace Marks
  Subject Results + Grade Card
  Semester Results (SGPA/CGPA)
  Rank List
  Student self-service (my-results, my-grade-card, my-transcript)
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Grading Policy
# ─────────────────────────────────────────────────────────────────────────────

class GradingBandIn(BaseModel):
    grade_letter:   str            = Field(..., max_length=5)
    min_percentage: Decimal        = Field(..., ge=0, le=100)
    max_percentage: Decimal        = Field(..., ge=0, le=100)
    grade_point:    Decimal        = Field(..., ge=0, le=10)
    is_pass:        bool           = True
    display_order:  Optional[int]  = None

    @model_validator(mode="after")
    def _min_le_max(self) -> "GradingBandIn":
        if self.min_percentage > self.max_percentage:
            raise ValueError("min_percentage must be <= max_percentage")
        return self


class GradingBandOut(BaseModel):
    id:             UUID
    policy_id:      UUID
    grade_letter:   str
    min_percentage: Decimal
    max_percentage: Decimal
    grade_point:    Decimal
    is_pass:        bool
    display_order:  Optional[int]
    created_at:     datetime

    model_config = {"from_attributes": True}


class GradingPolicyCreateIn(BaseModel):
    name:            str              = Field(..., max_length=100)
    program_id:      Optional[UUID]   = None   # None = global policy
    pass_percentage: Decimal          = Field(Decimal("40.0"), ge=0, le=100)
    is_default:      bool             = False
    bands:           list[GradingBandIn] = Field(default_factory=list)


class GradingPolicyUpdateIn(BaseModel):
    name:            Optional[str]     = Field(None, max_length=100)
    pass_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    is_default:      Optional[bool]    = None
    is_active:       Optional[bool]    = None


class GradingPolicyOut(BaseModel):
    id:              UUID
    name:            str
    program_id:      Optional[UUID]
    pass_percentage: Decimal
    is_default:      bool
    is_active:       bool
    created_by:      UUID
    created_at:      datetime
    updated_at:      Optional[datetime]
    bands:           list[GradingBandOut] = []

    model_config = {"from_attributes": True}


class GradingPolicyListOut(BaseModel):
    id:              UUID
    name:            str
    program_id:      Optional[UUID]
    pass_percentage: Decimal
    is_default:      bool
    is_active:       bool
    band_count:      int = 0

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Result Declarations
# ─────────────────────────────────────────────────────────────────────────────

class ResultDeclarationCreateIn(BaseModel):
    exam_session_id:         UUID
    semester_id:             UUID
    grading_policy_id:       UUID
    declaration_type:        str  = "REGULAR"
    source_declaration_id:   Optional[UUID] = None
    title:                   Optional[str]  = Field(None, max_length=200)
    notes:                   Optional[str]  = None
    internal_marks_required: bool           = True


class ResultDeclarationUpdateIn(BaseModel):
    grading_policy_id:       Optional[UUID] = None
    title:                   Optional[str]  = Field(None, max_length=200)
    notes:                   Optional[str]  = None
    internal_marks_required: Optional[bool] = None


class ResultDeclarationOut(BaseModel):
    id:                           UUID
    exam_session_id:              UUID
    semester_id:                  UUID
    snapshot_academic_year:       str
    snapshot_semester_name:       str
    snapshot_grading_policy_name: str
    declaration_type:             str
    source_declaration_id:        Optional[UUID]
    grading_policy_id:            UUID
    title:                        Optional[str]
    notes:                        Optional[str]
    internal_marks_required:      bool
    status:                       str
    verified_by:                  Optional[UUID]
    verified_at:                  Optional[datetime]
    published_by:                 Optional[UUID]
    published_at:                 Optional[datetime]
    locked_by:                    Optional[UUID]
    locked_at:                    Optional[datetime]
    created_by:                   UUID
    created_at:                   datetime
    updated_at:                   Optional[datetime]

    model_config = {"from_attributes": True}


class ResultDeclarationListOut(BaseModel):
    id:                           UUID
    semester_id:                  UUID
    snapshot_academic_year:       str
    snapshot_semester_name:       str
    snapshot_grading_policy_name: str
    declaration_type:             str
    title:                        Optional[str]
    status:                       str
    published_at:                 Optional[datetime]
    created_at:                   datetime

    model_config = {"from_attributes": True}


class RevertToDraftIn(BaseModel):
    reason: str = Field(..., min_length=5)


# ─────────────────────────────────────────────────────────────────────────────
# External Marks
# ─────────────────────────────────────────────────────────────────────────────

class ExternalMarkEntryIn(BaseModel):
    student_id:             UUID
    course_id:              UUID
    section_id:             UUID
    external_marks_obtained: Optional[Decimal] = Field(None, ge=0)
    external_marks_max:     Decimal            = Field(..., gt=0)
    is_absent:              bool               = False
    attempt_number:         int                = 1
    edit_reason:            Optional[str]      = None   # required if post-DRAFT


class ExternalMarksBulkIn(BaseModel):
    entries: list[ExternalMarkEntryIn] = Field(..., min_length=1)


class ExternalMarkOut(BaseModel):
    id:                      UUID
    declaration_id:          UUID
    student_id:              UUID
    course_id:               UUID
    section_id:              UUID
    external_marks_obtained: Optional[Decimal]
    external_marks_max:      Decimal
    is_absent:               bool
    attempt_number:          int
    entered_by:              Optional[UUID]
    entered_at:              Optional[datetime]
    edited_by:               Optional[UUID]
    edited_at:               Optional[datetime]
    edit_reason:             Optional[str]
    created_at:              datetime
    updated_at:              Optional[datetime]

    model_config = {"from_attributes": True}


class MarksSheetRowOut(BaseModel):
    student_id:              UUID
    course_id:               UUID
    course_name:             str = ""
    section_id:              UUID
    external_marks_obtained: Optional[Decimal]
    external_marks_max:      Decimal
    is_absent:               bool
    entered_by:              Optional[UUID]
    entered_at:              Optional[datetime]

    model_config = {"from_attributes": True}


class MarksSheetOut(BaseModel):
    declaration_id:   UUID
    total_students:   int
    total_courses:    int
    entered_count:    int
    pending_count:    int
    rows:             list[MarksSheetRowOut]


# ─────────────────────────────────────────────────────────────────────────────
# Computation
# ─────────────────────────────────────────────────────────────────────────────

class ComputationStatusOut(BaseModel):
    declaration_id:          UUID
    total_expected:          int
    external_marks_entered:  int
    external_marks_pending:  int
    internal_marks_locked:   bool
    ready_to_compute:        bool
    blocking_reasons:        list[str]


class ComputeResultIn(BaseModel):
    force: bool = False   # recompute even if already computed


class ComputeResultOut(BaseModel):
    declaration_id:  UUID
    computed_count:  int
    pass_count:      int
    fail_count:      int
    absent_count:    int
    pending_count:   int
    message:         str


# ─────────────────────────────────────────────────────────────────────────────
# Grace Marks
# ─────────────────────────────────────────────────────────────────────────────

class GraceMarkApplyIn(BaseModel):
    student_id:          UUID
    course_id:           UUID
    grace_marks_applied: Decimal = Field(..., gt=0, le=10)
    reason:              str     = Field(..., min_length=10)


class GraceMarkRevokeIn(BaseModel):
    revoke_reason: str = Field(..., min_length=5)


class GraceMarkLogOut(BaseModel):
    id:                  UUID
    declaration_id:      UUID
    subject_result_id:   UUID
    student_id:          UUID
    course_id:           UUID
    grace_marks_applied: Decimal
    reason:              str
    authorized_by:       UUID
    authorized_at:       datetime
    revoked_by:          Optional[UUID]
    revoked_at:          Optional[datetime]
    revoke_reason:       Optional[str]
    created_at:          datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Subject Results
# ─────────────────────────────────────────────────────────────────────────────

class SubjectResultOut(BaseModel):
    id:               UUID
    declaration_id:   UUID
    student_id:       UUID
    course_id:        UUID
    section_id:       UUID
    semester_id:      UUID
    internal_marks:   Optional[Decimal]
    external_marks:   Optional[Decimal]
    grace_marks:      Optional[Decimal]
    total_marks:      Optional[Decimal]
    max_marks:        Decimal
    percentage:       Optional[Decimal]
    grade_letter:     Optional[str]
    grade_point:      Optional[Decimal]
    is_pass:          Optional[bool]
    result_status:    str
    credits_attempted: Optional[Decimal]
    credits_earned:   Optional[Decimal]
    attempt_number:   int
    computed_at:      Optional[datetime]

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Grade Card
# ─────────────────────────────────────────────────────────────────────────────

class GradeCardSubjectRow(BaseModel):
    course_id:        UUID
    course_name:      str = ""
    course_code:      str = ""
    credits:          Optional[Decimal]
    internal_marks:   Optional[Decimal]
    external_marks:   Optional[Decimal]
    grace_marks:      Optional[Decimal]
    total_marks:      Optional[Decimal]
    max_marks:        Decimal
    percentage:       Optional[Decimal]
    grade_letter:     Optional[str]
    grade_point:      Optional[Decimal]
    result_status:    str


class GradeCardOut(BaseModel):
    student_id:                   UUID
    declaration_id:               UUID
    snapshot_academic_year:       str
    snapshot_semester_name:       str
    snapshot_grading_policy_name: str
    declaration_type:             str
    published_at:                 Optional[datetime]
    sgpa:                         Optional[Decimal]
    cgpa:                         Optional[Decimal]
    total_credits_attempted:      Optional[Decimal]
    total_credits_earned:         Optional[Decimal]
    overall_result_status:        Optional[str]
    section_rank:                 Optional[int]
    program_rank:                 Optional[int]
    subjects:                     list[GradeCardSubjectRow]


# ─────────────────────────────────────────────────────────────────────────────
# Semester Results (SGPA/CGPA)
# ─────────────────────────────────────────────────────────────────────────────

class SemesterResultOut(BaseModel):
    id:                      UUID
    declaration_id:          UUID
    student_id:              UUID
    semester_id:             UUID
    sgpa:                    Optional[Decimal]
    cgpa:                    Optional[Decimal]
    total_credits_attempted: Optional[Decimal]
    total_credits_earned:    Optional[Decimal]
    overall_result_status:   Optional[str]
    section_rank:            Optional[int]
    program_rank:            Optional[int]
    computed_at:             Optional[datetime]

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Rank List
# ─────────────────────────────────────────────────────────────────────────────

class RankEntryOut(BaseModel):
    rank:                    int
    student_id:              UUID
    sgpa:                    Optional[Decimal]
    cgpa:                    Optional[Decimal]
    total_credits_earned:    Optional[Decimal]
    overall_result_status:   Optional[str]
    section_rank:            Optional[int]
    program_rank:            Optional[int]


class RankListOut(BaseModel):
    declaration_id:  UUID
    scope:           str   # "section" or "program"
    scope_ref_id:    Optional[UUID]
    total_students:  int
    entries:         list[RankEntryOut]


class TopperOut(BaseModel):
    rank:       int
    student_id: UUID
    sgpa:       Optional[Decimal]
    cgpa:       Optional[Decimal]


class TopperListOut(BaseModel):
    declaration_id: UUID
    scope:          str
    entries:        list[TopperOut]


# ─────────────────────────────────────────────────────────────────────────────
# Student self-service
# ─────────────────────────────────────────────────────────────────────────────

class MyResultSummaryOut(BaseModel):
    declaration_id:               UUID
    snapshot_academic_year:       str
    snapshot_semester_name:       str
    declaration_type:             str
    published_at:                 Optional[datetime]
    sgpa:                         Optional[Decimal]
    cgpa:                         Optional[Decimal]
    overall_result_status:        Optional[str]
    total_credits_earned:         Optional[Decimal]


class TranscriptSemesterOut(BaseModel):
    declaration_id:               UUID
    snapshot_academic_year:       str
    snapshot_semester_name:       str
    declaration_type:             str
    published_at:                 Optional[datetime]
    sgpa:                         Optional[Decimal]
    cgpa:                         Optional[Decimal]
    overall_result_status:        Optional[str]
    total_credits_attempted:      Optional[Decimal]
    total_credits_earned:         Optional[Decimal]
    subjects:                     list[GradeCardSubjectRow]


class TranscriptOut(BaseModel):
    student_id:      UUID
    cgpa:            Optional[Decimal]
    total_credits:   Optional[Decimal]
    semesters:       list[TranscriptSemesterOut]
