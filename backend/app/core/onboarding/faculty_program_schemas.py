"""Faculty ↔ Program assignment schemas — ERP Onboarding Phase 1 / Step 3."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FacultyProgramAssignRequest(BaseModel):
    faculty_user_id: UUID = Field(..., description="Target FACULTY user")
    program_id: UUID = Field(..., description="acad_programs.id to grant teaching scope on")


class FacultyProgramRevokeRequest(BaseModel):
    faculty_user_id: UUID
    program_id: UUID


class FacultyInfo(BaseModel):
    id: UUID
    full_name: str
    email: str


class ProgramInfo(BaseModel):
    id: UUID
    code: str
    name: str


class FacultyProgramOut(BaseModel):
    id: UUID
    faculty_user_id: UUID
    program_id: UUID
    is_active: bool
    assigned_by: UUID
    assigned_at: datetime
    revoked_by: Optional[UUID] = None
    revoked_at: Optional[datetime] = None
    # Enrichment (best-effort; null if the referenced row is missing)
    faculty: Optional[FacultyInfo] = None
    program: Optional[ProgramInfo] = None
    # True when an assign call reactivated a previously revoked row.
    reactivated: bool = False


class FacultyProgramListResponse(BaseModel):
    total: int
    items: list[FacultyProgramOut]
