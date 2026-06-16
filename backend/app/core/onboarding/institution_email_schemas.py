"""Institution email foundation — Phase 1.2 / Task C schemas.

Generation only: project and assign {usn|employee_id}@{institution_domain}
institution emails to existing students and faculty.  Login is unaffected.
"""
from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

# Minimal hostname check: labels of alnum/hyphen separated by dots, with a TLD.
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}$")


def normalize_domain(value: str) -> str:
    return (value or "").strip().lower().lstrip("@")


class InstitutionDomainOut(BaseModel):
    institution_domain: Optional[str]


class SetInstitutionDomainIn(BaseModel):
    domain: str

    @field_validator("domain", mode="before")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_domain(v) if isinstance(v, str) else v

    @field_validator("domain", mode="after")
    @classmethod
    def _valid(cls, v: str) -> str:
        if not _DOMAIN_RE.match(v):
            raise ValueError("domain must be a valid hostname, e.g. lms.edu")
        return v


class InstitutionEmailRunIn(BaseModel):
    """Optional domain override for preview/commit; falls back to the stored
    tenant institution_domain when omitted."""
    domain: Optional[str] = None

    @field_validator("domain", mode="before")
    @classmethod
    def _norm(cls, v):
        return normalize_domain(v) if isinstance(v, str) and v.strip() else None


# Per-user projection row.
# action ∈ ASSIGN | SKIP_HAS_EMAIL | SKIP_NO_IDENTIFIER | CONFLICT
class InstitutionEmailRow(BaseModel):
    user_id: UUID
    full_name: str
    role: str
    login_email: str
    identifier: Optional[str] = None  # usn (student) or employee_id (faculty)
    existing_institution_email: Optional[str] = None
    projected_institution_email: Optional[str] = None
    action: str
    note: Optional[str] = None


class InstitutionEmailPreviewResponse(BaseModel):
    domain: str
    total_users: int
    students: int
    faculty: int
    to_assign: int
    already_have: int
    no_identifier: int
    conflicts: int
    rows: list[InstitutionEmailRow]


class InstitutionEmailCommitResult(BaseModel):
    domain: str
    total_users: int
    assigned: int
    skipped: int
    conflicts: int
    personal_backfilled: int
    batch_ref: Optional[str] = None
    errors: list[str] = []
