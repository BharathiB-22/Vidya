"""
SIS Hall Ticket Eligibility — H58 SQLAlchemy models.

Tables:
  sis_hall_ticket_batches      — one row per batch generation event
  sis_hall_ticket_eligibility  — one row per student per semester

Eligibility workflow:
  compute → DRAFT rows created/updated (students cannot see)
  Dean reviews, overrides individual rows with mandatory reason
  publish → DRAFT → PUBLISHED (students can now see their status)
  generate batch → assigns hall_ticket_number to ELIGIBLE/CONDITIONAL rows

Status values: ELIGIBLE | NOT_ELIGIBLE | CONDITIONAL
Publish status: DRAFT | PUBLISHED

Invariant: compute does NOT overwrite rows that have override_by set
           and are already PUBLISHED.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class EligibilityStatus(str, enum.Enum):
    ELIGIBLE     = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    CONDITIONAL  = "CONDITIONAL"


class PublishStatus(str, enum.Enum):
    DRAFT     = "DRAFT"
    PUBLISHED = "PUBLISHED"


class BatchScope(str, enum.Enum):
    ALL     = "ALL"
    SECTION = "SECTION"


class SisHallTicketBatch(Base):
    __tablename__ = "sis_hall_ticket_batches"
    __table_args__ = (
        Index("ix_ht_batches_semester",     "semester_id"),
        Index("ix_ht_batches_generated_by", "generated_by"),
        Index("ix_ht_batches_generated_at", "generated_at"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semester_id    = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="RESTRICT"), nullable=False)
    scope          = Column(String(10), nullable=False, server_default=text("'ALL'"))
    scope_ref_id   = Column(UUID(as_uuid=True), nullable=True)   # section_id when scope=SECTION
    generated_by   = Column(UUID(as_uuid=True), nullable=False)  # plain UUID — codebase pattern
    generated_at   = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    ticket_count   = Column(Integer,     nullable=False, server_default=text("0"))
    ticket_prefix  = Column(String(40),  nullable=False)          # e.g. TOCS-2026S2
    notes          = Column(Text,        nullable=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    eligibility_rows = relationship("SisHallTicketEligibility", back_populates="batch")


class SisHallTicketEligibility(Base):
    __tablename__ = "sis_hall_ticket_eligibility"
    __table_args__ = (
        UniqueConstraint("student_id", "semester_id", name="uq_ht_eligibility_student_semester"),
        Index("ix_ht_eligibility_student",        "student_id"),
        Index("ix_ht_eligibility_semester",       "semester_id"),
        Index("ix_ht_eligibility_status",         "status"),
        Index("ix_ht_eligibility_publish_status", "publish_status"),
        Index("ix_ht_eligibility_batch_id",       "batch_id"),
        Index("ix_ht_eligibility_has_shortage",   "has_shortage"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Who + which semester
    student_id     = Column(UUID(as_uuid=True), nullable=False)  # plain UUID
    semester_id    = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="RESTRICT"), nullable=False)

    # Publish workflow
    publish_status = Column(String(12), nullable=False, server_default=text("'DRAFT'"))

    # Eligibility result
    status         = Column(String(15), nullable=False, server_default=text("'NOT_ELIGIBLE'"))

    # When computed
    computed_at    = Column(DateTime(timezone=True), nullable=True)

    # Snapshot metadata
    attendance_threshold_used = Column(Numeric(5, 2), nullable=False, server_default=text("75.0"))
    computed_academic_year    = Column(String(20),    nullable=False, server_default=text("''"))
    computed_semester_name    = Column(String(100),   nullable=False, server_default=text("''"))

    # Check results
    attendance_pct   = Column(Numeric(5, 2), nullable=True)
    has_shortage     = Column(Boolean,       nullable=False, server_default=text("false"))
    marks_all_locked = Column(Boolean,       nullable=False, server_default=text("false"))
    marks_all_filled = Column(Boolean,       nullable=False, server_default=text("false"))
    failure_reasons  = Column(ARRAY(Text),   nullable=True)

    # Override (Dean / Admin human gate)
    override_by     = Column(UUID(as_uuid=True),         nullable=True)
    override_at     = Column(DateTime(timezone=True),    nullable=True)
    override_reason = Column(Text,                       nullable=True)
    override_status = Column(String(15),                 nullable=True)

    # Hall ticket assignment
    batch_id            = Column(UUID(as_uuid=True), ForeignKey("sis_hall_ticket_batches.id", ondelete="SET NULL"), nullable=True)
    hall_ticket_number  = Column(String(80), nullable=True)

    # Future exam scheduling fields
    exam_session_id  = Column(UUID(as_uuid=True), nullable=True)
    exam_schedule_id = Column(UUID(as_uuid=True), nullable=True)
    exam_center_id   = Column(UUID(as_uuid=True), nullable=True)
    room_number      = Column(String(30), nullable=True)
    seat_number      = Column(String(30), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)

    batch = relationship("SisHallTicketBatch", back_populates="eligibility_rows")
