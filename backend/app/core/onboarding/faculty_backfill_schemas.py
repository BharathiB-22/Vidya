"""Faculty identity backfill schemas — ERP Onboarding Phase 1.5.

Generate the missing faculty_code / institution_email for EXISTING faculty
without touching login, password, or admin accounts.  Preview-first, idempotent.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FacultyBackfillRow(BaseModel):
    user_id: UUID
    full_name: str
    login_email: str
    existing_faculty_code: Optional[str] = None
    existing_institution_email: Optional[str] = None
    projected_faculty_code: Optional[str] = None
    projected_institution_email: Optional[str] = None
    # SKIP_COMPLETE | ASSIGN_CODE | ASSIGN_EMAIL | ASSIGN_BOTH
    action: str
    note: Optional[str] = None


class FacultyBackfillPreviewResponse(BaseModel):
    domain: Optional[str] = None
    total_faculty: int
    codes_to_assign: int
    emails_to_assign: int
    already_complete: int
    # Faculty whose home department (primary_department_id) is still NULL but can
    # be derived from an active program assignment — NULL-only, never overwrites.
    departments_to_derive: int = 0
    rows: list[FacultyBackfillRow]


class FacultyBackfillCommitResult(BaseModel):
    domain: Optional[str] = None
    total_faculty: int
    codes_assigned: int
    emails_assigned: int
    personal_emails_backfilled: int
    profiles_created: int
    # Home departments derived from active program assignments (NULL-only).
    departments_derived: int = 0
    batch_ref: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
