"""Academic Governance — curriculum approval records (Phase A).

The governance authority (Board / University Members — the name is a per-tenant
display choice, see auth.models.GovernanceType) owns the final curriculum. The
Dean prepares and submits it; governance reviews, modifies, approves and locks.

`CurriculumApprovalRequest` is the append-only record of that handover. One row
per submit → decide cycle:

    cycle 1  submitted → RETURNED  (governance sent it back with comments)
    cycle 2  submitted → APPROVED  (Dean fixed it, governance locked it)

Rows are never deleted and never re-opened. A partial unique index guarantees a
program can have at most ONE PENDING request at a time.
"""
import enum
import uuid

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ApprovalRequestStatus(str, enum.Enum):
    PENDING  = "PENDING"    # with the governance authority, awaiting a decision
    APPROVED = "APPROVED"   # governance approved; the curriculum is locked
    RETURNED = "RETURNED"   # governance sent it back to the Dean with comments


class CurriculumApprovalRequest(Base):
    __tablename__ = "curriculum_approval_requests"
    __table_args__ = (
        UniqueConstraint("program_id", "cycle", name="uq_car_program_cycle"),
        Index("ix_car_program", "program_id"),
        Index("ix_car_status", "status"),
        Index(
            "uq_car_one_open_per_program",
            "program_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id           = Column(
        UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False,
    )
    cycle                = Column(Integer, nullable=False, default=1, server_default=text("1"))
    status               = Column(
        String(20),
        nullable=False,
        default=ApprovalRequestStatus.PENDING.value,
        server_default=text("'PENDING'"),
    )
    submitted_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    submitted_at         = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    submission_note      = Column(Text, nullable=True)
    decided_by_user_id   = Column(UUID(as_uuid=True), nullable=True)
    decided_at           = Column(DateTime(timezone=True), nullable=True)
    decision_comment     = Column(Text, nullable=True)
    created_at           = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
