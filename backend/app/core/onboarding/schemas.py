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
    warnings: list[str] = Field(default_factory=list)
    section_id: Optional[UUID] = None
    section_resolved: bool = False
    acad_program_id: Optional[UUID] = None
    program_resolved: bool = False
    # USN projection (students) — Phase 1 / Step 4
    school_code: Optional[str] = None
    admission_year: Optional[int] = None
    projected_usn: Optional[str] = None
    # Program mappings (faculty) — Phase 1 / Step 4
    resolved_program_codes: list[str] = Field(default_factory=list)
    unresolved_program_codes: list[str] = Field(default_factory=list)
    # Responsibility grants (faculty) — Phase 1.5
    resolved_roles: list[str] = Field(default_factory=list)
    unresolved_roles: list[str] = Field(default_factory=list)
    # Generated faculty identity (faculty) — Phase 1.5 (projected in preview)
    projected_faculty_code: Optional[str] = None
    projected_institution_email: Optional[str] = None


class ImportUsnRange(BaseModel):
    """Projected USN range for one (school, year, program) triple in an import."""
    school_code: str
    admission_year: int
    program_code: str
    count: int
    first_usn: str
    last_usn: str


class StudentSummaryMeta(BaseModel):
    """Dashboard-ready rollup for a student import preview."""
    total_rows: int
    valid_rows: int
    invalid_rows: int
    # Distinct EXISTING academic entities the valid rows resolve to
    schools_count: int
    departments_count: int
    programs_count: int
    batches_count: int
    sections_count: int
    # Students that would receive a freshly-minted USN on commit
    projected_usns_count: int
    # Distinct entities REFERENCED in the file that do not exist yet
    new_schools: int
    new_departments: int
    new_programs: int
    new_batches: int
    new_sections: int


class FacultySummaryMeta(BaseModel):
    """Dashboard-ready rollup for a faculty import preview."""
    total_rows: int
    valid_rows: int
    invalid_rows: int
    faculty_count: int
    unique_programs: int
    new_program_assignments: int
    reactivated_assignments: int
    # Responsibility grants (Phase 1.5)
    new_role_grants: int = 0
    reactivated_role_grants: int = 0
    # Generated identity (Phase 1.5)
    faculty_codes_to_assign: int = 0
    institution_emails_to_assign: int = 0


class ProgramAssignmentCount(BaseModel):
    """How many faculty an import maps to a given program (for charts)."""
    program_code: str
    faculty_count: int


class CSVPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_in_file: int = 0
    duplicate_in_db: int = 0
    rows: list[CSVRowResult]
    # Students: projected USN ranges that would be minted on commit
    projected_usn_ranges: list[ImportUsnRange] = Field(default_factory=list)
    # Dashboard rollup — StudentSummaryMeta or FacultySummaryMeta shape
    summary_meta: Optional[dict] = None
    # Faculty: per-program faculty counts for charts
    program_assignment_summary: list[ProgramAssignmentCount] = Field(default_factory=list)


class CSVCommitResult(BaseModel):
    total: int
    created: int
    skipped: int
    errors: list[str]
    enrollments_created: int = 0
    # Students: USNs minted via UsnAllocator during this commit
    usns_assigned: int = 0
    # Students: institution emails auto-generated from minted USNs during this commit
    institution_emails_assigned: int = 0
    # Faculty: program mappings applied via FacultyProgramService
    program_mappings_created: int = 0
    program_mappings_reactivated: int = 0
    program_mappings_skipped: int = 0
    # Faculty: responsibility grants applied via FacultyRoleGrantService (Phase 1.5)
    role_grants_created: int = 0
    role_grants_reactivated: int = 0
    role_grants_skipped: int = 0
    # Faculty: generated identity (Phase 1.5)
    faculty_codes_assigned: int = 0
    faculty_institution_emails_assigned: int = 0


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
