import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class NotificationType(str, enum.Enum):
    TASK_COMPLETE       = "TASK_COMPLETE"
    TASK_FAILED         = "TASK_FAILED"
    SUBMISSION_FLAGGED  = "SUBMISSION_FLAGGED"
    REVIEW_REQUESTED    = "REVIEW_REQUESTED"
    OUTCOME_PUBLISHED   = "OUTCOME_PUBLISHED"
    GENERAL             = "GENERAL"

    # SIS — H52
    ENROLLMENT_CREATED          = "ENROLLMENT_CREATED"
    ENROLLMENT_MOVED            = "ENROLLMENT_MOVED"
    ENROLLMENT_UNENROLLED       = "ENROLLMENT_UNENROLLED"
    USN_ASSIGNED                = "USN_ASSIGNED"
    ADMISSION_YEAR_ASSIGNED     = "ADMISSION_YEAR_ASSIGNED"
    COURSE_ASSIGNED             = "COURSE_ASSIGNED"
    COURSE_ASSIGNMENT_REVOKED   = "COURSE_ASSIGNMENT_REVOKED"

    # SIS Attendance — H55
    ATTENDANCE_SHORTAGE_WARNING = "ATTENDANCE_SHORTAGE_WARNING"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index("ix_notifications_recipient_is_read", "recipient_user_id", "is_read"),
    )

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_user_id = Column(UUID(as_uuid=True), nullable=False)
    notification_type = Column(
        String,
        nullable=False,
    )
    title             = Column(String,  nullable=False)
    body              = Column(Text,    nullable=False)
    entity_type       = Column(String,  nullable=True)   # e.g. "TaskJob", "Submission"
    entity_id         = Column(String,  nullable=True)   # str of entity PK
    is_read           = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at        = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    read_at           = Column(DateTime(timezone=True), nullable=True)
