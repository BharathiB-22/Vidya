"""
SIS Graduation Audit — H62 SQLAlchemy models.

Tables (tenant schema):
  sis_graduation_audits        — one per batch audit run
  sis_graduation_candidates    — one per student per audit; eligibility + board decision
  sis_graduation_overrides     — append-only Dean override log (no UPDATE/DELETE)
  sis_graduation_certificates  — issued graduation certificate record

Table (public schema):
  public.public_graduation_index — cross-tenant QR verification lookup

Graduation audit lifecycle:
  DRAFT → SUBMITTED → BOARD_APPROVED → CERTIFICATES_ISSUED

Candidate lifecycle:
  eligibility_status: ELIGIBLE | NOT_ELIGIBLE | PROVISIONAL
  board_status:       PENDING  | RATIFIED | DEFERRED
  certificate_status: NOT_ISSUED | ISSUED | REVOKED

Human gates:
  Gate 1: Dean → SUBMITTED
  Gate 2a: Board → RATIFIED / DEFERRED (per candidate)
  Gate 2b: Board → BOARD_APPROVED (batch resolution; board_resolution_ref mandatory)
  Gate 3:  Registrar → ISSUED (per candidate or batch)

No automatic graduation. AI advises, humans decide.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Numeric,
    SmallInteger, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class GraduationAuditStatus(str, enum.Enum):
    DRAFT                = "DRAFT"
    SUBMITTED            = "SUBMITTED"
    BOARD_APPROVED       = "BOARD_APPROVED"
    CERTIFICATES_ISSUED  = "CERTIFICATES_ISSUED"


class CandidateEligibilityStatus(str, enum.Enum):
    ELIGIBLE            = "ELIGIBLE"
    NOT_ELIGIBLE        = "NOT_ELIGIBLE"
    PROVISIONAL         = "PROVISIONAL"


class CandidateBoardStatus(str, enum.Enum):
    PENDING   = "PENDING"
    RATIFIED  = "RATIFIED"
    DEFERRED  = "DEFERRED"


class CandidateCertificateStatus(str, enum.Enum):
    NOT_ISSUED = "NOT_ISSUED"
    ISSUED     = "ISSUED"
    REVOKED    = "REVOKED"


class GraduationCertificateStatus(str, enum.Enum):
    ISSUED  = "ISSUED"
    REVOKED = "REVOKED"


# ─────────────────────────────────────────────────────────────────────────────
# Table 1: sis_graduation_audits
# ─────────────────────────────────────────────────────────────────────────────

class SisGraduationAudit(Base):
    __tablename__ = "sis_graduation_audits"
    __table_args__ = (
        Index("ix_graduation_audits_batch_id",  "batch_id"),
        Index("ix_graduation_audits_status",    "status"),
        Index("ix_graduation_audits_program_id", "program_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Batch / program context (snapshot — no FK; batch may change name over time)
    batch_id                  = Column(UUID(as_uuid=True), nullable=False)
    batch_name_snapshot       = Column(String(100), nullable=True)
    program_id                = Column(UUID(as_uuid=True), nullable=True)
    program_name_snapshot     = Column(String(200), nullable=True)
    academic_year_snapshot    = Column(String(20),  nullable=True)

    # Lifecycle
    status = Column(String(25), nullable=False, server_default=text("'DRAFT'"))

    # Human gate timestamps
    triggered_by               = Column(UUID(as_uuid=True), nullable=False)
    triggered_at               = Column(DateTime(timezone=True), nullable=False,
                                        server_default=text("now()"))
    submitted_by               = Column(UUID(as_uuid=True), nullable=True)
    submitted_at               = Column(DateTime(timezone=True), nullable=True)
    board_approved_by          = Column(UUID(as_uuid=True), nullable=True)
    board_approved_at          = Column(DateTime(timezone=True), nullable=True)
    board_resolution_ref       = Column(String(200), nullable=True)   # mandatory at BOARD_APPROVED
    certificates_issued_by     = Column(UUID(as_uuid=True), nullable=True)
    certificates_issued_at     = Column(DateTime(timezone=True), nullable=True)

    # Summary counters (updated at each gate)
    total_candidates     = Column(SmallInteger, nullable=True)
    eligible_count       = Column(SmallInteger, nullable=True)
    provisional_count    = Column(SmallInteger, nullable=True)
    not_eligible_count   = Column(SmallInteger, nullable=True)
    ratified_count       = Column(SmallInteger, nullable=True)
    deferred_count       = Column(SmallInteger, nullable=True)

    notes      = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)

    candidates = relationship(
        "SisGraduationCandidate",
        back_populates="audit",
        cascade="all, delete-orphan",
        order_by="SisGraduationCandidate.student_name_snapshot",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Table 2: sis_graduation_candidates
# ─────────────────────────────────────────────────────────────────────────────

class SisGraduationCandidate(Base):
    __tablename__ = "sis_graduation_candidates"
    __table_args__ = (
        UniqueConstraint("audit_id", "student_id", name="uq_graduation_candidates_audit_student"),
        Index("ix_graduation_candidates_audit_id",          "audit_id"),
        Index("ix_graduation_candidates_student_id",        "student_id"),
        Index("ix_graduation_candidates_eligibility_status", "eligibility_status"),
        Index("ix_graduation_candidates_board_status",      "board_status"),
    )

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_id   = Column(UUID(as_uuid=True), ForeignKey("sis_graduation_audits.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), nullable=False)

    # Student snapshot
    usn_snapshot           = Column(String(30),  nullable=True)
    student_name_snapshot  = Column(String(200), nullable=False)
    program_name_snapshot  = Column(String(200), nullable=True)

    # ── Eligibility flags (all advisory — computed by engine) ─────────────────
    missing_declarations          = Column(Boolean, nullable=False, server_default=text("false"))
    has_arrears                   = Column(Boolean, nullable=False, server_default=text("false"))
    credits_shortfall             = Column(Boolean, nullable=False, server_default=text("false"))
    has_withheld                  = Column(Boolean, nullable=False, server_default=text("false"))
    final_sem_not_locked          = Column(Boolean, nullable=False, server_default=text("false"))
    graduation_year_not_reached   = Column(Boolean, nullable=False, server_default=text("false"))
    attendance_below_threshold    = Column(Boolean, nullable=False, server_default=text("false"))
    disciplinary_hold             = Column(Boolean, nullable=False, server_default=text("false"))

    # ── Computed snapshot values ──────────────────────────────────────────────
    total_credits_earned   = Column(Numeric(6, 2), nullable=True)
    min_credits_required   = Column(Numeric(6, 2), nullable=True)
    current_cgpa           = Column(Numeric(4, 2), nullable=True)
    arrear_count           = Column(SmallInteger,  nullable=True)
    semesters_declared     = Column(SmallInteger,  nullable=True)

    # ── Eligibility outcome (advisory — Dean may override) ───────────────────
    eligibility_status = Column(String(20), nullable=False, server_default=text("'NOT_ELIGIBLE'"))
    override_reason    = Column(Text, nullable=True)
    overridden_by      = Column(UUID(as_uuid=True), nullable=True)
    overridden_at      = Column(DateTime(timezone=True), nullable=True)
    provisional_grace_deadline = Column(Date, nullable=True)

    # ── Board decision ────────────────────────────────────────────────────────
    board_status      = Column(String(20), nullable=False, server_default=text("'PENDING'"))
    board_decided_by  = Column(UUID(as_uuid=True), nullable=True)
    board_decided_at  = Column(DateTime(timezone=True), nullable=True)
    board_notes       = Column(Text, nullable=True)   # never exposed in public verify

    # ── Certificate ───────────────────────────────────────────────────────────
    certificate_status = Column(String(20), nullable=False, server_default=text("'NOT_ISSUED'"))
    certificate_id     = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)

    audit     = relationship("SisGraduationAudit", back_populates="candidates")
    overrides = relationship("SisGraduationOverride", back_populates="candidate")


# ─────────────────────────────────────────────────────────────────────────────
# Table 3: sis_graduation_overrides  (append-only — no UPDATE/DELETE)
# ─────────────────────────────────────────────────────────────────────────────

class SisGraduationOverride(Base):
    __tablename__ = "sis_graduation_overrides"
    __table_args__ = (
        Index("ix_graduation_overrides_candidate_id", "candidate_id"),
        Index("ix_graduation_overrides_actor_id",     "actor_user_id"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id  = Column(UUID(as_uuid=True), ForeignKey("sis_graduation_candidates.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), nullable=False)
    actor_role    = Column(String(30), nullable=False)
    previous_status = Column(String(20), nullable=False)
    new_status      = Column(String(20), nullable=False)
    reason          = Column(Text, nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # No updated_at — this table is append-only
    candidate = relationship("SisGraduationCandidate", back_populates="overrides")


# ─────────────────────────────────────────────────────────────────────────────
# Table 4: sis_graduation_certificates
# ─────────────────────────────────────────────────────────────────────────────

class SisGraduationCertificate(Base):
    __tablename__ = "sis_graduation_certificates"
    __table_args__ = (
        UniqueConstraint("certificate_number", name="uq_graduation_certificates_number"),
        Index("ix_graduation_certificates_student_id", "student_id"),
        Index("ix_graduation_certificates_audit_id",   "audit_id"),
        Index("ix_graduation_certificates_status",     "status"),
    )

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("sis_graduation_candidates.id", ondelete="RESTRICT"), nullable=False)
    audit_id     = Column(UUID(as_uuid=True), ForeignKey("sis_graduation_audits.id", ondelete="RESTRICT"), nullable=False)
    student_id   = Column(UUID(as_uuid=True), nullable=False)

    # Snapshot — frozen at issuance
    usn_snapshot           = Column(String(30),  nullable=True)
    student_name_snapshot  = Column(String(200), nullable=False)
    program_name_snapshot  = Column(String(200), nullable=True)
    degree_title_snapshot  = Column(String(200), nullable=True)
    school_name_snapshot   = Column(String(200), nullable=True)
    batch_name_snapshot    = Column(String(100), nullable=True)
    graduation_year        = Column(SmallInteger, nullable=False)
    overall_cgpa_snapshot  = Column(Numeric(4, 2), nullable=True)
    total_credits_earned   = Column(Numeric(6, 2), nullable=True)

    # Identity
    certificate_number     = Column(String(50), nullable=True)   # CERT/{TENANT}/{YEAR}/{SEQ}
    is_provisional         = Column(Boolean, nullable=False, server_default=text("false"))

    # Provisional → graduated confirmation
    provisional_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    provisional_confirmed_by = Column(UUID(as_uuid=True), nullable=True)

    # Lifecycle
    status     = Column(String(20), nullable=False, server_default=text("'ISSUED'"))
    issued_by  = Column(UUID(as_uuid=True), nullable=False)
    issued_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    revoked_by = Column(UUID(as_uuid=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(Text, nullable=True)

    # PDF
    pdf_s3_key       = Column(String(500), nullable=True)
    pdf_generated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)


# ─────────────────────────────────────────────────────────────────────────────
# Public-schema table: public.public_graduation_index
# ─────────────────────────────────────────────────────────────────────────────

class PublicGraduationIndex(Base):
    """Platform-level cross-tenant lookup for certificate QR verification.

    Lives in the public schema so the /verify/certificate/{number} endpoint
    can find the right tenant without requiring a tenant slug header.
    """
    __tablename__ = "public_graduation_index"
    __table_args__ = (
        Index("ix_public_graduation_index_tenant_id",     "tenant_id"),
        Index("ix_public_graduation_index_certificate_id", "certificate_id"),
        {"schema": "public"},
    )

    certificate_number = Column(String(50), primary_key=True)
    tenant_id          = Column(UUID(as_uuid=True), nullable=False)
    schema_name        = Column(String(100), nullable=False)
    certificate_id     = Column(UUID(as_uuid=True), nullable=False)
    student_id         = Column(UUID(as_uuid=True), nullable=False)
    is_provisional     = Column(Boolean, nullable=False, server_default=text("false"))
    status             = Column(String(20), nullable=False)   # ISSUED | REVOKED
    graduation_year    = Column(SmallInteger, nullable=True)
    issued_at          = Column(DateTime(timezone=True), nullable=True)
    updated_at         = Column(DateTime(timezone=True), nullable=True)
