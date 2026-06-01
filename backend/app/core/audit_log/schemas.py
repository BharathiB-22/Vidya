from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.audit_log.models import AuditEventType


class AuditLogEntry(BaseModel):
    """Read-only response schema for a single audit log row.

    The ORM column is named ``metadata`` in the database but the SQLAlchemy
    attribute is ``metadata_`` (to avoid colliding with SQLAlchemy's reserved
    class attribute).  ``validation_alias`` maps the ORM attribute name to this
    field so that ``model_validate(orm_obj)`` resolves correctly, while the
    serialised JSON key remains ``metadata``.
    """

    model_config = {"from_attributes": True, "populate_by_name": True}

    id:            UUID
    event_type:    AuditEventType
    actor_user_id: Optional[UUID]
    actor_role:    Optional[str]
    tenant_id:     Optional[UUID]
    schema_name:   Optional[str]
    target_entity: Optional[str]
    target_id:     Optional[str]
    metadata:      Optional[dict[str, Any]] = Field(None, validation_alias="metadata_")
    ip_address:    Optional[str]
    user_agent:    Optional[str]
    created_at:    datetime


class AuditLogListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     list[AuditLogEntry]


class PlatformAuditStats(BaseModel):
    total_events:   int
    tenant_events:  int
    login_events:   int
    ai_events:      int
    security_events: int
    recent:         list[AuditLogEntry]
