import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class TaskJobStatus(str, enum.Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    SUCCESS   = "SUCCESS"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"


class TaskJob(Base):
    __tablename__ = "task_jobs"
    __table_args__ = (
        Index("ix_task_jobs_tenant_created",  "tenant_id", "created_at"),
        Index("ix_task_jobs_status_created",  "status",    "created_at"),
        Index("ix_task_jobs_tenant_status",   "tenant_id", "status"),
        Index("ix_task_jobs_created",         "created_at"),
        {"schema": "public"},
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # nullable: platform-level tasks (e.g. provisioning) have no tenant
    tenant_id   = Column(UUID(as_uuid=True), nullable=True)

    task_type   = Column(String,  nullable=False)
    queue_name  = Column(String,  nullable=False)
    status      = Column(
        Enum(TaskJobStatus, native_enum=False),
        nullable=False,
        default=TaskJobStatus.PENDING,
        server_default=TaskJobStatus.PENDING.value,
    )

    # Input payload stored for auditability; may be omitted for large blobs
    payload     = Column(JSONB,   nullable=True)

    # Written by VidyaTask.on_success
    result      = Column(JSONB,   nullable=True)

    # Written by VidyaTask.on_failure (last exception message)
    error       = Column(Text,    nullable=True)

    created_at  = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    # Written by VidyaTask.before_start when worker picks up the task
    started_at  = Column(DateTime(timezone=True), nullable=True)
    # Written by VidyaTask.on_success / on_failure
    completed_at = Column(DateTime(timezone=True), nullable=True)
