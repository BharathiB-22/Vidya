from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Academic master data
# ---------------------------------------------------------------------------

class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    code: str = Field(..., min_length=1, max_length=20)


class DepartmentResponse(BaseModel):
    id: UUID
    name: str
    code: str
    is_active: bool

    model_config = {"from_attributes": True}


class ProgramCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    code: str = Field(..., min_length=1, max_length=20)
    dept_id: Optional[UUID] = None
    duration_years: int = Field(default=2, ge=1, le=10)


class ProgramResponse(BaseModel):
    id: UUID
    name: str
    code: str
    dept_id: Optional[UUID]
    duration_years: int
    is_active: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Bulk student generation
# ---------------------------------------------------------------------------

class GenerateStudentsRequest(BaseModel):
    usn_prefix: str = Field(
        ..., min_length=2, max_length=10,
        description="Institution code prefix, e.g. ABC",
    )
    program_code: str = Field(
        ..., min_length=2, max_length=10,
        description="Program code, e.g. MCA",
    )
    batch_year: int = Field(
        ..., ge=1, le=99,
        description="2-digit batch year suffix, e.g. 26 for 2026",
    )
    section: Optional[str] = Field(None, max_length=5, description="Section label, e.g. A")
    count: int = Field(..., ge=1, le=500, description="Number of students to generate")
    start_seq: int = Field(default=1, ge=1, description="Starting sequence number")
    seq_width: int = Field(default=3, ge=2, le=4, description="Zero-pad width for sequence digits")
    email_domain: str = Field(
        ..., min_length=3, max_length=100,
        description="Email domain, e.g. abc.edu",
    )
    default_password: str = Field(default="Student@123", min_length=8)


class GenerateStudentsResult(BaseModel):
    created: int
    skipped: int
    duplicate_usns: list[str]
    duplicate_emails: list[str]
    default_password: str


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

class CSVRowResult(BaseModel):
    row_number: int
    full_name: str
    email: str
    identifier: Optional[str]
    is_valid: bool
    errors: list[str]


class CSVPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[CSVRowResult]


class CSVCommitResult(BaseModel):
    total: int
    created: int
    skipped: int
    errors: list[str]
