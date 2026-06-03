"""
SIS Bulk Profile Import — H53 Pydantic schemas.

Two-phase preview → commit flow for updating sis_student_profiles in bulk.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ProfileImportRowResult(BaseModel):
    row_number:              int
    email:                   str
    student_name:            Optional[str] = None   # resolved from DB
    student_id:              Optional[UUID] = None  # resolved from DB
    usn:                     Optional[str] = None
    admission_year:          Optional[int] = None
    phone:                   Optional[str] = None
    address_line1:           Optional[str] = None
    address_city:            Optional[str] = None
    address_state:           Optional[str] = None
    emergency_contact_name:  Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    is_valid:                bool
    errors:                  list[str]


class ProfileImportPreviewResponse(BaseModel):
    total_rows:              int
    valid_rows:              int
    invalid_rows:            int
    not_found_in_db:         int = 0
    duplicate_email_in_file: int = 0
    duplicate_usn_in_file:   int = 0
    duplicate_usn_in_db:     int = 0
    rows:                    list[ProfileImportRowResult]


class ProfileImportCommitResult(BaseModel):
    total:   int
    updated: int
    skipped: int
    errors:  list[str]
