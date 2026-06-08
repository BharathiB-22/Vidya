"""
SIS Transcript Generation — H61 SQLAlchemy models.

Tables (tenant schema):
  sis_transcripts                  — one record per transcript issuance / request
  sis_transcript_semester_lines    — frozen semester snapshot
  sis_transcript_subject_lines     — frozen subject snapshot
  sis_transcript_verification_log  — append-only QR scan audit (no UPDATE/DELETE)

Table (public schema):
  public_transcript_index          — cross-tenant verification lookup

Transcript lifecycle:
  REQUESTED → GENERATED → ISSUED
                        → STALE (if underlying LOCKED result is amended)
                        → SUPERSEDED (when regenerated)
                        → REVOKED

Degree status: ELIGIBLE / NOT_ELIGIBLE / PROVISIONAL / GRADUATED
Transcript type: OFFICIAL / PROVISIONAL / DUPLICATE
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Index, Numeric, SmallInteger, String,
    Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class TranscriptStatus(str, enum.Enum):
    REQUESTED  = "REQUESTED"
    GENERATED  = "GENERATED"
    ISSUED     = "ISSUED"
    STALE      = "STALE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED    = "REVOKED"


class TranscriptType(str, enum.Enum):
    OFFICIAL    = "OFFICIAL"
    PROVISIONAL = "PROVISIONAL"
    DUPLICATE   = "DUPLICATE"


class DegreeStatus(str, enum.Enum):
    ELIGIBLE     = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    PROVISIONAL  = "PROVISIONAL"
    GRADUATED    = "GRADUATED"


class VerificationResult(str, enum.Enum):
    VALID      = "VALID"
    REVOKED    = "REVOKED"
    SUPERSEDED = "SUPERSEDED"
    NOT_FOUND  = "NOT_FOUND"


# ─────────────────────────────────────────────────────────────────────────────
# Table 1: sis_transcripts
# ─────────────────────────────────────────────────────────────────────────────

class SisTranscript(Base):
    __tablename__ = "sis_transcripts"
    __table_args__ = (
        UniqueConstraint("transcript_number", name="uq_transcripts_transcript_number"),
        UniqueConstraint("verification_code",  name="uq_transcripts_verification_code"),
        Index("ix_transcripts_student_status", "student_id", "status"),
        Index("ix_transcripts_verification_code", "verification_code"),
        Index("ix_transcripts_status",  "status"),
        Index("ix_transcripts_student_id", "student_id"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Student context (plain UUID — cross-module reference)
    student_id                = Column(UUID(as_uuid=True), nullable=False)
    usn_snapshot              = Column(String(30),  nullable=True)
    student_name_snapshot     = Column(String(200), nullable=False)

    # Academic context — frozen at generation
    program_id                = Column(UUID(as_uuid=True), nullable=True)
    program_name_snapshot     = Column(String(200), nullable=True)
    department_name_snapshot  = Column(String(200), nullable=True)
    school_name_snapshot      = Column(String(200), nullable=True)
    batch_name_snapshot       = Column(String(100), nullable=True)
    degree_title_snapshot     = Column(String(200), nullable=True)

    # Identity
    transcript_number         = Column(String(50),  nullable=True)   # set at GENERATED
    verification_code         = Column(UUID(as_uuid=True), nullable=True)  # set at GENERATED
    transcript_type           = Column(String(20),  nullable=False, server_default=text("'OFFICIAL'"))
    purpose                   = Column(Text, nullable=True)

    # Computed snapshot fields (written by Celery task)
    overall_cgpa_snapshot             = Column(Numeric(4, 2), nullable=True)
    total_credits_attempted_snapshot  = Column(Numeric(6, 2), nullable=True)
    total_credits_earned_snapshot     = Column(Numeric(6, 2), nullable=True)
    arrear_count_snapshot             = Column(SmallInteger,  nullable=True)
    degree_status_snapshot            = Column(String(20),    nullable=True)
    semesters_included                = Column(SmallInteger,  nullable=True)

    # Lifecycle
    status  = Column(String(15), nullable=False, server_default=text("'REQUESTED'"))
    version = Column(SmallInteger, nullable=False, server_default=text("1"))
    parent_transcript_id = Column(UUID(as_uuid=True), nullable=True)

    # PDF
    pdf_s3_key        = Column(String(500), nullable=True)
    pdf_generated_at  = Column(DateTime(timezone=True), nullable=True)

    # Human gate timestamps
    requested_by = Column(UUID(as_uuid=True), nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    generated_by = Column(UUID(as_uuid=True), nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    issued_by    = Column(UUID(as_uuid=True), nullable=True)
    issued_at    = Column(DateTime(timezone=True), nullable=True)
    revoked_by   = Column(UUID(as_uuid=True), nullable=True)
    revoked_at   = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)

    semester_lines     = relationship("SisTranscriptSemesterLine",
                                      back_populates="transcript",
                                      cascade="all, delete-orphan",
                                      order_by="SisTranscriptSemesterLine.display_order")
    verification_logs  = relationship("SisTranscriptVerificationLog",
                                      back_populates="transcript")


# ─────────────────────────────────────────────────────────────────────────────
# Table 2: sis_transcript_semester_lines
# ─────────────────────────────────────────────────────────────────────────────

class SisTranscriptSemesterLine(Base):
    __tablename__ = "sis_transcript_semester_lines"
    __table_args__ = (
        Index("ix_transcript_semester_lines_transcript_id", "transcript_id"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcript_id  = Column(UUID(as_uuid=True), nullable=False)

    # Non-FK references (snapshot is independent)
    semester_id    = Column(UUID(as_uuid=True), nullable=True)
    declaration_id = Column(UUID(as_uuid=True), nullable=True)

    # Frozen snapshot
    semester_number_snapshot       = Column(SmallInteger,   nullable=True)
    semester_name_snapshot         = Column(String(100),    nullable=True)
    academic_year_snapshot         = Column(String(20),     nullable=True)
    sgpa_snapshot                  = Column(Numeric(4, 2),  nullable=True)
    cgpa_snapshot                  = Column(Numeric(4, 2),  nullable=True)
    credits_attempted_snapshot     = Column(Numeric(6, 2),  nullable=True)
    credits_earned_snapshot        = Column(Numeric(6, 2),  nullable=True)
    overall_result_status_snapshot = Column(String(15),     nullable=True)
    display_order                  = Column(SmallInteger,   nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    transcript   = relationship("SisTranscript", back_populates="semester_lines")
    subject_lines = relationship("SisTranscriptSubjectLine",
                                  back_populates="semester_line",
                                  cascade="all, delete-orphan",
                                  order_by="SisTranscriptSubjectLine.display_order")


# ─────────────────────────────────────────────────────────────────────────────
# Table 3: sis_transcript_subject_lines
# ─────────────────────────────────────────────────────────────────────────────

class SisTranscriptSubjectLine(Base):
    __tablename__ = "sis_transcript_subject_lines"
    __table_args__ = (
        Index("ix_transcript_subject_lines_transcript_id", "transcript_id"),
        Index("ix_transcript_subject_lines_semester_line", "semester_line_id"),
        Index("ix_transcript_subject_lines_best", "transcript_id", "is_best_attempt"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcript_id   = Column(UUID(as_uuid=True), nullable=False)
    semester_line_id = Column(UUID(as_uuid=True), nullable=False)

    # Reference
    course_id = Column(UUID(as_uuid=True), nullable=True)

    # Frozen snapshot
    course_code_snapshot    = Column(String(20),    nullable=True)
    course_name_snapshot    = Column(String(200),   nullable=True)
    course_credits_snapshot = Column(Numeric(4, 2), nullable=True)
    internal_marks_snapshot = Column(Numeric(6, 2), nullable=True)
    external_marks_snapshot = Column(Numeric(6, 2), nullable=True)
    grace_marks_snapshot    = Column(Numeric(6, 2), nullable=True)
    total_marks_snapshot    = Column(Numeric(6, 2), nullable=True)
    max_marks_snapshot      = Column(Numeric(6, 2), nullable=True)
    percentage_snapshot     = Column(Numeric(5, 2), nullable=True)
    grade_letter_snapshot   = Column(String(5),     nullable=True)
    grade_point_snapshot    = Column(Numeric(4, 2), nullable=True)
    is_pass_snapshot        = Column(Boolean,       nullable=True)
    result_status_snapshot  = Column(String(10),    nullable=True)
    attempt_number          = Column(SmallInteger,  nullable=False, server_default=text("1"))
    declaration_type_snapshot = Column(String(20),  nullable=True)
    is_best_attempt         = Column(Boolean, nullable=False, server_default=text("true"))
    display_order           = Column(SmallInteger, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    semester_line = relationship("SisTranscriptSemesterLine", back_populates="subject_lines")


# ─────────────────────────────────────────────────────────────────────────────
# Table 4: sis_transcript_verification_log  (append-only)
# ─────────────────────────────────────────────────────────────────────────────

class SisTranscriptVerificationLog(Base):
    __tablename__ = "sis_transcript_verification_log"
    __table_args__ = (
        Index("ix_verification_log_transcript_id",  "transcript_id"),
        Index("ix_verification_log_code",            "verification_code"),
        Index("ix_verification_log_verified_at",     "verified_at"),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcript_id        = Column(UUID(as_uuid=True), nullable=True)
    verification_code    = Column(String(50),  nullable=False)
    verified_at          = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    requester_ip_hash    = Column(String(64),  nullable=True)
    requester_context    = Column(String(100), nullable=True)
    verification_result  = Column(String(15),  nullable=False)
    created_at           = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    transcript = relationship("SisTranscript", back_populates="verification_logs")


# ─────────────────────────────────────────────────────────────────────────────
# Public-schema table: public.public_transcript_index
# ─────────────────────────────────────────────────────────────────────────────

class PublicTranscriptIndex(Base):
    """Platform-level cross-tenant lookup for QR verification.

    Lives in the public schema so the verify endpoint can find the right
    tenant without requiring a tenant slug header.
    """
    __tablename__ = "public_transcript_index"
    __table_args__ = (
        Index("ix_public_transcript_index_tenant_id",      "tenant_id"),
        Index("ix_public_transcript_index_transcript_id",  "transcript_id"),
        {"schema": "public"},
    )

    verification_code  = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id          = Column(UUID(as_uuid=True), nullable=False)
    schema_name        = Column(String(100), nullable=False)
    transcript_id      = Column(UUID(as_uuid=True), nullable=False)
    transcript_number  = Column(String(50),  nullable=True)
    status             = Column(String(15),  nullable=False)
    issued_at          = Column(DateTime(timezone=True), nullable=True)
    updated_at         = Column(DateTime(timezone=True), nullable=True)
