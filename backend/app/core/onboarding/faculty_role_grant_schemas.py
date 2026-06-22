"""Faculty responsibility-grant schemas — ERP Onboarding Phase 1.5.

A single FACULTY account may hold multiple active grants simultaneously
(GUIDE / EVALUATOR / BOARD / DEAN).  Responsibilities are grants, never
separate user accounts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# The only responsibilities that may be granted to FACULTY accounts.
# BOARD and DEAN are PRIMARY roles (set on users.role, like ADMIN/FACULTY/STUDENT)
# and are never grantable here.  Pre-Phase 1.7 databases may still have legacy
# BOARD grants — run scripts/repair_board_dean_roles.py to clean those up.
GRANTABLE_ROLES: frozenset[str] = frozenset({"GUIDE", "EVALUATOR"})


def normalize_role_code(value: str) -> str:
    return (value or "").strip().upper()


class FacultyRoleGrantRequest(BaseModel):
    faculty_user_id: UUID = Field(..., description="Target FACULTY user")
    role_code: str = Field(..., description="One of GUIDE / EVALUATOR / BOARD")

    @field_validator("role_code", mode="before")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_role_code(v) if isinstance(v, str) else v


class FacultyRoleRevokeRequest(BaseModel):
    faculty_user_id: UUID
    role_code: str

    @field_validator("role_code", mode="before")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_role_code(v) if isinstance(v, str) else v


class FacultyInfo(BaseModel):
    id: UUID
    full_name: str
    email: str


class FacultyRoleGrantOut(BaseModel):
    id: UUID
    faculty_user_id: UUID
    role_code: str
    is_active: bool
    granted_by: UUID
    granted_at: datetime
    revoked_by: Optional[UUID] = None
    revoked_at: Optional[datetime] = None
    faculty: Optional[FacultyInfo] = None
    # True when a grant call reactivated a previously revoked row.
    reactivated: bool = False


class FacultyRoleGrantListResponse(BaseModel):
    total: int
    items: list[FacultyRoleGrantOut]
