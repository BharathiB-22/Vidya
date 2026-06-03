"""
SIS Semester Rollover — H54 Pydantic schemas.

No new tables. Uses existing acad_* tables only.

Two-phase API:
  POST /sis/rollover/preview  → dry-run, returns row-level plan
  POST /sis/rollover/commit   → executes after admin confirms; re-validates server-side

Rollover moves active students from Semester N sections to Semester N+1 sections,
matching by section name within the same batch.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Request (shared by preview and commit)
# ---------------------------------------------------------------------------

class RolloverScopeIn(BaseModel):
    scope: Literal["all_programs", "program", "batch", "semester"]
    program_id:         Optional[UUID] = None
    batch_id:           Optional[UUID] = None
    source_semester_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Preview — row-level result
# ---------------------------------------------------------------------------

class RolloverRowOut(BaseModel):
    enrollment_id:           UUID
    student_id:              UUID
    student_name:            str
    student_email:           str
    current_section_id:      UUID
    current_section_name:    str
    current_semester_number: int
    batch_name:              str
    program_name:            str
    target_semester_number:  Optional[int]   # None if Sem N+1 does not exist
    target_section_id:       Optional[UUID]  # None if no name match in target sem
    target_section_name:     Optional[str]
    status:                  Literal["ready", "blocked"]
    reason:                  Optional[str]   # human-readable explanation when blocked


class RolloverSummary(BaseModel):
    total:   int
    ready:   int
    blocked: int


class RolloverPreviewResponse(BaseModel):
    scope:   str
    summary: RolloverSummary
    rows:    list[RolloverRowOut]


# ---------------------------------------------------------------------------
# Commit — row-level result
# ---------------------------------------------------------------------------

class RolloverCommitRowResult(BaseModel):
    enrollment_id:     UUID
    student_id:        UUID
    student_name:      str
    target_section_id: Optional[UUID]
    outcome:           Literal["moved", "skipped", "error"]
    reason:            Optional[str]


class RolloverCommitResult(BaseModel):
    moved:   int
    skipped: int
    errors:  int
    rows:    list[RolloverCommitRowResult]
