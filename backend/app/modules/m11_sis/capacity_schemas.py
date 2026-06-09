"""Capacity schemas — H64.6."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SectionCapacityOut(BaseModel):
    section_id:   UUID
    section_name: str
    semester_id:  UUID
    max_strength: Optional[int]
    enrolled:     int
    available:    Optional[int]   # None when max_strength is unset
    is_full:      bool
    fill_pct:     Optional[float] # 0–100, None when max_strength unset

    model_config = {"from_attributes": True}


class SetCapacityIn(BaseModel):
    max_strength: Optional[int] = Field(None, ge=1, le=10000, description="Set null to remove the cap")
