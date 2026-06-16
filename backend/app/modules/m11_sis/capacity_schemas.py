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
    available:    Optional[int]   # None when max_strength is unset; may be negative when over capacity
    is_full:      bool
    fill_pct:     Optional[float] # 0–100+, None when max_strength unset

    # P1.2 Task A — academic-hierarchy context (derived via section→…→school chain)
    school_id:        Optional[UUID] = None
    school_name:      Optional[str]  = None
    department_id:    Optional[UUID] = None
    department_name:  Optional[str]  = None
    program_id:       Optional[UUID] = None
    program_name:     Optional[str]  = None
    program_code:     Optional[str]  = None
    batch_id:         Optional[UUID] = None
    batch_name:       Optional[str]  = None
    semester_number:  Optional[int]  = None
    semester_label:   Optional[str]  = None

    # HEALTHY | NEAR_FULL | FULL | OVER | NO_CAP
    status:           str = "NO_CAP"

    model_config = {"from_attributes": True}


class SetCapacityIn(BaseModel):
    max_strength: Optional[int] = Field(None, ge=1, le=10000, description="Set null to remove the cap")
