from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
    section_id: Optional[UUID] = Field(
        None,
        description="acad_section UUID — if provided, enrolls every created student here",
    )
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
    enrollments_created: int = 0


# ---------------------------------------------------------------------------
# File import (CSV and XLSX)
# ---------------------------------------------------------------------------

class CSVRowResult(BaseModel):
    row_number: int
    full_name: str
    email: str
    identifier: Optional[str]
    is_valid: bool
    errors: list[str]
    section_id: Optional[UUID] = None
    section_resolved: bool = False
    acad_program_id: Optional[UUID] = None
    program_resolved: bool = False


class CSVPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_in_file: int = 0
    duplicate_in_db: int = 0
    rows: list[CSVRowResult]


class CSVCommitResult(BaseModel):
    total: int
    created: int
    skipped: int
    errors: list[str]
    enrollments_created: int = 0


# ---------------------------------------------------------------------------
# USN backfill (Phase 1 / Step 2)
# ---------------------------------------------------------------------------

class UsnBackfillRow(BaseModel):
    """One existing student evaluated for USN backfill."""
    user_id: UUID
    full_name: str
    email: str
    # Derived academic identity (None when the chain could not be resolved)
    school_code: Optional[str] = None
    program_code: Optional[str] = None
    admission_year: Optional[int] = None
    # Existing vs projected USN
    existing_usn: Optional[str] = None
    projected_usn: Optional[str] = None
    # Outcome for this row
    action: str                       # SKIP_HAS_USN | ASSIGN | ERROR | CONFLICT
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class UsnProjectedRange(BaseModel):
    """Projected USN range for one (school, year, program) triple."""
    school_code: str
    admission_year: int
    program_code: str
    seed_next_seq: int                # counter start used for this run
    count: int                        # students to be assigned in this triple
    first_usn: str
    last_usn: str


class UsnBackfillPreviewResponse(BaseModel):
    total_students: int
    already_have_usn: int             # skipped
    to_assign: int
    errors_count: int
    conflicts_count: int
    warnings_count: int
    projected_ranges: list[UsnProjectedRange]
    rows: list[UsnBackfillRow]


class UsnBackfillCommitResult(BaseModel):
    total_students: int
    assigned: int
    skipped: int                      # already had a USN
    failed: int                       # errors + conflicts not assigned
    counters_seeded: int              # triples whose counter was advanced from existing USNs
    batch_ref: Optional[str] = None   # sis_import_batches reference for traceability
    errors: list[str] = Field(default_factory=list)
