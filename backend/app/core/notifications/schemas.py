from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.core.notifications.models import NotificationType


class NotificationCreate(BaseModel):
    recipient_user_id: UUID
    notification_type: NotificationType
    title:       str
    body:        str
    entity_type: Optional[str] = None
    entity_id:   Optional[str] = None


class NotificationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                UUID
    recipient_user_id: UUID
    notification_type: NotificationType
    title:             str
    body:              str
    entity_type:       Optional[str]
    entity_id:         Optional[str]
    is_read:           bool
    created_at:        datetime
    read_at:           Optional[datetime]


class NotificationListResponse(BaseModel):
    total:        int
    unread_count: int
    page:         int
    page_size:    int
    items:        list[NotificationResponse]


class MarkReadResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:      UUID
    is_read: bool
    read_at: Optional[datetime]
