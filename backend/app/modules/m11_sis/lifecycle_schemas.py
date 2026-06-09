"""Student Lifecycle — H64.3 Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LifecycleHistoryEntry(BaseModel):
    id:          UUID
    from_status: Optional[str]
    to_status:   str
    reason:      Optional[str]
    changed_by:  UUID
    changed_at:  datetime

    model_config = {"from_attributes": True}


class LifecycleStatusOut(BaseModel):
    student_id:     UUID
    current_status: str
    allowed_next:   list[str]
    history:        list[LifecycleHistoryEntry]


class LifecycleTransitionIn(BaseModel):
    new_status: str
    reason:     Optional[str] = None


class LifecycleTransitionOut(BaseModel):
    student_id:      UUID
    previous_status: str
    new_status:      str
    is_active:       bool
    message:         str
