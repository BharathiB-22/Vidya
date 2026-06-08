"""
SIS Transcript Generation — H61 Pydantic schemas.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Input schemas
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptRequestCreate(BaseModel):
    transcript_type: Literal["OFFICIAL", "PROVISIONAL", "DUPLICATE"] = "OFFICIAL"
    purpose:         Optional[str] = None
    student_id:      Optional[UUID] = None   # Admin requests on behalf of student


class TranscriptRevokeIn(BaseModel):
    revoke_reason: str

    @field_validator("revoke_reason")
    @classmethod
    def _reason_min_length(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("revoke_reason must be at least 10 characters")
        return v.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Output schemas
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptSubjectLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                       UUID
    semester_line_id:         UUID
    course_id:                Optional[UUID]
    course_code_snapshot:     Optional[str]
    course_name_snapshot:     Optional[str]
    course_credits_snapshot:  Optional[Decimal]
    internal_marks_snapshot:  Optional[Decimal]
    external_marks_snapshot:  Optional[Decimal]
    grace_marks_snapshot:     Optional[Decimal]
    total_marks_snapshot:     Optional[Decimal]
    max_marks_snapshot:       Optional[Decimal]
    percentage_snapshot:      Optional[Decimal]
    grade_letter_snapshot:    Optional[str]
    grade_point_snapshot:     Optional[Decimal]
    is_pass_snapshot:         Optional[bool]
    result_status_snapshot:   Optional[str]
    attempt_number:           int
    declaration_type_snapshot: Optional[str]
    is_best_attempt:          bool
    display_order:            int


class TranscriptSemesterLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                             UUID
    transcript_id:                  UUID
    semester_id:                    Optional[UUID]
    declaration_id:                 Optional[UUID]
    semester_number_snapshot:       Optional[int]
    semester_name_snapshot:         Optional[str]
    academic_year_snapshot:         Optional[str]
    sgpa_snapshot:                  Optional[Decimal]
    cgpa_snapshot:                  Optional[Decimal]
    credits_attempted_snapshot:     Optional[Decimal]
    credits_earned_snapshot:        Optional[Decimal]
    overall_result_status_snapshot: Optional[str]
    display_order:                  int
    subject_lines:                  list[TranscriptSubjectLineRead] = []


class TranscriptSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                      UUID
    student_id:              UUID
    usn_snapshot:            Optional[str]
    student_name_snapshot:   str
    program_name_snapshot:   Optional[str]
    transcript_number:       Optional[str]
    transcript_type:         str
    status:                  str
    version:                 int
    overall_cgpa_snapshot:   Optional[Decimal]
    arrear_count_snapshot:   Optional[int]
    degree_status_snapshot:  Optional[str]
    semesters_included:      Optional[int]
    issued_at:               Optional[datetime]
    requested_at:            datetime
    created_at:              datetime


class TranscriptDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                               UUID
    student_id:                       UUID
    usn_snapshot:                     Optional[str]
    student_name_snapshot:            str
    program_id:                       Optional[UUID]
    program_name_snapshot:            Optional[str]
    department_name_snapshot:         Optional[str]
    school_name_snapshot:             Optional[str]
    batch_name_snapshot:              Optional[str]
    degree_title_snapshot:            Optional[str]
    transcript_number:                Optional[str]
    verification_code:                Optional[UUID]  # admin/dean only
    transcript_type:                  str
    purpose:                          Optional[str]
    overall_cgpa_snapshot:            Optional[Decimal]
    total_credits_attempted_snapshot: Optional[Decimal]
    total_credits_earned_snapshot:    Optional[Decimal]
    arrear_count_snapshot:            Optional[int]
    degree_status_snapshot:           Optional[str]
    semesters_included:               Optional[int]
    status:                           str
    version:                          int
    parent_transcript_id:             Optional[UUID]
    pdf_s3_key:                       Optional[str]
    pdf_generated_at:                 Optional[datetime]
    requested_by:                     UUID
    requested_at:                     datetime
    generated_by:                     Optional[UUID]
    generated_at:                     Optional[datetime]
    issued_by:                        Optional[UUID]
    issued_at:                        Optional[datetime]
    revoked_by:                       Optional[UUID]
    revoked_at:                       Optional[datetime]
    revoke_reason:                    Optional[str]
    created_at:                       datetime
    semester_lines:                   list[TranscriptSemesterLineRead] = []


class PDFDownloadResponse(BaseModel):
    presigned_url: str
    expires_at:    datetime


class GenerateDispatchResponse(BaseModel):
    transcript_id: UUID
    celery_task_id: str
    message: str


class VerificationLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                  UUID
    verified_at:         datetime
    requester_context:   Optional[str]
    verification_result: str


# ─────────────────────────────────────────────────────────────────────────────
# Degree Progress
# ─────────────────────────────────────────────────────────────────────────────

class BacklogSubject(BaseModel):
    course_id:   Optional[str]
    course_code: Optional[str]
    course_name: Optional[str]
    semester:    Optional[str]
    grade:       Optional[str]
    attempts:    int


class SemesterProgressRow(BaseModel):
    semester_number:      Optional[int]
    semester_name:        Optional[str]
    academic_year:        Optional[str]
    sgpa:                 Optional[Decimal]
    cgpa:                 Optional[Decimal]
    credits_attempted:    Optional[Decimal]
    credits_earned:       Optional[Decimal]
    overall_result_status: Optional[str]


class DegreeProgressRead(BaseModel):
    student_id:                  UUID
    usn:                         Optional[str]
    student_name:                str
    program_name:                Optional[str]
    expected_graduation_year:    Optional[int]
    total_semesters_declared:    int
    total_credits_attempted:     Decimal
    total_credits_earned:        Decimal
    min_credits_for_degree:      Optional[Decimal]
    current_cgpa:                Optional[Decimal]
    arrear_count:                int
    active_backlogs:             list[BacklogSubject]
    degree_status:               str
    is_final_semester_declared:  bool
    semesters:                   list[SemesterProgressRow]


# ─────────────────────────────────────────────────────────────────────────────
# Public verify response (limited — never includes marks or CGPA)
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptVerifyResponse(BaseModel):
    verification_code:    str
    transcript_number:    Optional[str]
    student_name_partial: str     # "Firstname L." — never full name
    program_name:         Optional[str]
    institution_name:     Optional[str]
    degree_status:        Optional[str]
    issued_at:            Optional[datetime]
    status:               str     # VALID / REVOKED / SUPERSEDED / NOT_FOUND
    is_provisional:       bool
    message:              str
