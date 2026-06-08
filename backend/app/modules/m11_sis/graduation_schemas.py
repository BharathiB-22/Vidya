"""
SIS Graduation Audit — H62 Pydantic schemas.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Input schemas
# ─────────────────────────────────────────────────────────────────────────────

class GraduationAuditCreate(BaseModel):
    batch_id:             UUID
    academic_year_snapshot: Optional[str] = None


class CandidateOverrideIn(BaseModel):
    new_status:              str    # ELIGIBLE | NOT_ELIGIBLE | PROVISIONAL
    reason:                  str
    provisional_grace_deadline: Optional[date] = None

    @field_validator("new_status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        allowed = {"ELIGIBLE", "NOT_ELIGIBLE", "PROVISIONAL"}
        if v not in allowed:
            raise ValueError(f"new_status must be one of {allowed}")
        return v

    @field_validator("reason")
    @classmethod
    def _reason_min_length(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError("reason must be at least 20 characters")
        return v.strip()


class BoardRatifyIn(BaseModel):
    board_notes: Optional[str] = None


class BoardDeferIn(BaseModel):
    board_notes: str

    @field_validator("board_notes")
    @classmethod
    def _notes_required(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("board_notes must be at least 10 characters when deferring")
        return v.strip()


class AuditApproveIn(BaseModel):
    board_resolution_ref: str   # mandatory per PDCA modification #5

    @field_validator("board_resolution_ref")
    @classmethod
    def _ref_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("board_resolution_ref is required before BOARD_APPROVED")
        return v.strip()


class CertificateRevokeIn(BaseModel):
    revoke_reason: str

    @field_validator("revoke_reason")
    @classmethod
    def _reason_min_length(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("revoke_reason must be at least 10 characters")
        return v.strip()


class ProvisionalConfirmIn(BaseModel):
    confirmation_notes: str

    @field_validator("confirmation_notes")
    @classmethod
    def _notes_required(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("confirmation_notes must be at least 10 characters")
        return v.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Output schemas — candidates
# ─────────────────────────────────────────────────────────────────────────────

class GraduationCandidateSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                    UUID
    audit_id:              UUID
    student_id:            UUID
    usn_snapshot:          Optional[str]
    student_name_snapshot: str
    program_name_snapshot: Optional[str]
    eligibility_status:    str
    board_status:          str
    certificate_status:    str
    certificate_id:        Optional[UUID]
    arrear_count:          Optional[int]
    current_cgpa:          Optional[Decimal]
    semesters_declared:    Optional[int]
    overridden_by:         Optional[UUID]
    overridden_at:         Optional[datetime]
    created_at:            datetime


class GraduationCandidateDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                    UUID
    audit_id:              UUID
    student_id:            UUID
    usn_snapshot:          Optional[str]
    student_name_snapshot: str
    program_name_snapshot: Optional[str]

    # Eligibility flags (visible to Dean/Admin/Board)
    missing_declarations:          bool
    has_arrears:                   bool
    credits_shortfall:             bool
    has_withheld:                  bool
    final_sem_not_locked:          bool
    graduation_year_not_reached:   bool
    attendance_below_threshold:    bool
    disciplinary_hold:             bool

    # Computed values
    total_credits_earned:  Optional[Decimal]
    min_credits_required:  Optional[Decimal]
    current_cgpa:          Optional[Decimal]
    arrear_count:          Optional[int]
    semesters_declared:    Optional[int]

    # Outcome
    eligibility_status:          str
    override_reason:             Optional[str]
    overridden_by:               Optional[UUID]
    overridden_at:               Optional[datetime]
    provisional_grace_deadline:  Optional[date]

    # Board decision
    board_status:     str
    board_decided_by: Optional[UUID]
    board_decided_at: Optional[datetime]
    board_notes:      Optional[str]   # visible to Board/Dean/Admin only; never public verify

    # Certificate
    certificate_status: str
    certificate_id:     Optional[UUID]

    created_at: datetime
    updated_at: Optional[datetime]


# ─────────────────────────────────────────────────────────────────────────────
# Output schemas — audits
# ─────────────────────────────────────────────────────────────────────────────

class GraduationAuditSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                       UUID
    batch_id:                 UUID
    batch_name_snapshot:      Optional[str]
    program_name_snapshot:    Optional[str]
    academic_year_snapshot:   Optional[str]
    status:                   str
    triggered_by:             UUID
    triggered_at:             datetime
    submitted_at:             Optional[datetime]
    board_approved_at:        Optional[datetime]
    board_resolution_ref:     Optional[str]
    certificates_issued_at:   Optional[datetime]
    total_candidates:         Optional[int]
    eligible_count:           Optional[int]
    provisional_count:        Optional[int]
    not_eligible_count:       Optional[int]
    ratified_count:           Optional[int]
    deferred_count:           Optional[int]
    created_at:               datetime


class GraduationAuditDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                       UUID
    batch_id:                 UUID
    batch_name_snapshot:      Optional[str]
    program_id:               Optional[UUID]
    program_name_snapshot:    Optional[str]
    academic_year_snapshot:   Optional[str]
    status:                   str
    triggered_by:             UUID
    triggered_at:             datetime
    submitted_by:             Optional[UUID]
    submitted_at:             Optional[datetime]
    board_approved_by:        Optional[UUID]
    board_approved_at:        Optional[datetime]
    board_resolution_ref:     Optional[str]
    certificates_issued_by:   Optional[UUID]
    certificates_issued_at:   Optional[datetime]
    total_candidates:         Optional[int]
    eligible_count:           Optional[int]
    provisional_count:        Optional[int]
    not_eligible_count:       Optional[int]
    ratified_count:           Optional[int]
    deferred_count:           Optional[int]
    notes:                    Optional[str]
    created_at:               datetime
    updated_at:               Optional[datetime]
    candidates:               list[GraduationCandidateSummaryRead] = []


# ─────────────────────────────────────────────────────────────────────────────
# Output schemas — certificates
# ─────────────────────────────────────────────────────────────────────────────

class GraduationCertificateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                    UUID
    candidate_id:          UUID
    audit_id:              UUID
    student_id:            UUID
    usn_snapshot:          Optional[str]
    student_name_snapshot: str
    program_name_snapshot: Optional[str]
    degree_title_snapshot: Optional[str]
    school_name_snapshot:  Optional[str]
    batch_name_snapshot:   Optional[str]
    graduation_year:       int
    overall_cgpa_snapshot: Optional[Decimal]
    total_credits_earned:  Optional[Decimal]
    certificate_number:    Optional[str]
    is_provisional:        bool
    provisional_confirmed_at: Optional[datetime]
    status:                str
    issued_by:             UUID
    issued_at:             datetime
    revoked_at:            Optional[datetime]
    revoke_reason:         Optional[str]
    pdf_s3_key:            Optional[str]
    pdf_generated_at:      Optional[datetime]
    created_at:            datetime


# ─────────────────────────────────────────────────────────────────────────────
# Student-facing read
# ─────────────────────────────────────────────────────────────────────────────

class StudentGraduationStatusRead(BaseModel):
    student_id:            UUID
    usn:                   Optional[str]
    student_name:          str
    program_name:          Optional[str]
    # Advisory eligibility (no CGPA or credits — student self-view)
    eligibility_status:    Optional[str]
    board_status:          Optional[str]
    certificate_status:    Optional[str]
    certificate_number:    Optional[str]
    graduation_year:       Optional[int]
    is_provisional:        Optional[bool]
    message:               str


# ─────────────────────────────────────────────────────────────────────────────
# Public certificate verify response
# MUST NEVER expose: CGPA, credits, eligibility flags, board notes
# ─────────────────────────────────────────────────────────────────────────────

class CertificateVerifyResponse(BaseModel):
    certificate_number:    str
    student_name_partial:  str    # "Firstname L." — never full name
    programme_name:        Optional[str]
    institution_name:      Optional[str]
    graduation_year:       Optional[int]
    is_provisional:        bool
    status:                str    # ISSUED | REVOKED | NOT_FOUND
    message:               str


class PDFDownloadResponse(BaseModel):
    presigned_url: str
    expires_at:    datetime


class AuditReportDispatchResponse(BaseModel):
    audit_id:       UUID
    celery_task_id: str
    message:        str
