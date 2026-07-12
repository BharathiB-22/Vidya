"""
SIS Internal Marks — H57 Pydantic schemas.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Component templates — built-in suggestions for faculty
# ---------------------------------------------------------------------------

class ComponentTemplate(BaseModel):
    template_key:   str
    component_type: str
    name:           str
    max_marks:      Decimal
    display_order:  int

    model_config = ConfigDict(from_attributes=True)


BUILT_IN_TEMPLATES: list[ComponentTemplate] = [
    ComponentTemplate(template_key="CIE_1",     component_type="CIE",        name="CIE-1",     max_marks=Decimal("30"), display_order=1),
    ComponentTemplate(template_key="CIE_2",     component_type="CIE",        name="CIE-2",     max_marks=Decimal("30"), display_order=2),
    ComponentTemplate(template_key="ASSIGNMENT", component_type="ASSIGNMENT", name="Assignment", max_marks=Decimal("20"), display_order=3),
    ComponentTemplate(template_key="QUIZ",       component_type="QUIZ",       name="Quiz",       max_marks=Decimal("10"), display_order=4),
    ComponentTemplate(template_key="LAB",        component_type="LAB",        name="Lab",        max_marks=Decimal("25"), display_order=5),
]


# ---------------------------------------------------------------------------
# Component — input schemas
# ---------------------------------------------------------------------------

class ComponentCreateIn(BaseModel):
    """A component belongs to exactly one class.

    Regular course: pass `section_id` (and `semester_id`).
    Elective course: pass `semester_id` and leave `section_id` unset — the class
    is every student who chose the elective, across all sections.
    """
    course_id:      UUID
    section_id:     Optional[UUID] = None
    semester_id:    UUID
    component_type: str = Field(..., pattern="^(CIE|ASSIGNMENT|QUIZ|LAB|OTHER)$")
    name:           str = Field(..., min_length=1, max_length=100)
    max_marks:      Decimal = Field(..., gt=0, le=999.99)
    weightage:      Optional[Decimal] = Field(None, ge=0, le=100)
    due_date:       Optional[date]    = None
    display_order:  Optional[int]     = None


class ComponentUpdateIn(BaseModel):
    component_type: Optional[str]     = Field(None, pattern="^(CIE|ASSIGNMENT|QUIZ|LAB|OTHER)$")
    name:           Optional[str]     = Field(None, min_length=1, max_length=100)
    max_marks:      Optional[Decimal] = Field(None, gt=0, le=999.99)
    weightage:      Optional[Decimal] = Field(None, ge=0, le=100)
    due_date:       Optional[date]    = None
    display_order:  Optional[int]     = None


class ReopenComponentIn(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


# ---------------------------------------------------------------------------
# Component — output schema
# ---------------------------------------------------------------------------

class ComponentOut(BaseModel):
    id:              UUID
    course_id:       UUID
    course_code:     Optional[str]    = None
    course_title:    Optional[str]    = None
    # Null for an elective group — the class spans every section that chose it.
    section_id:      Optional[UUID]   = None
    section_name:    Optional[str]    = None
    semester_id:     UUID
    created_by:      UUID
    component_type:  str
    name:            str
    max_marks:       Decimal
    weightage:       Optional[Decimal] = None
    due_date:        Optional[date]    = None
    display_order:   Optional[int]     = None
    status:          str
    published_at:    Optional[datetime] = None
    locked_at:       Optional[datetime] = None
    locked_by:       Optional[UUID]     = None
    reopened_by:     Optional[UUID]     = None
    reopened_at:     Optional[datetime] = None
    reopen_reason:   Optional[str]      = None
    is_active:       bool
    entries_count:   int = 0            # total enrolled
    filled_count:    int = 0            # entries with marks_obtained IS NOT NULL
    created_at:      datetime
    updated_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Mark entry — input schemas
# ---------------------------------------------------------------------------

class MarkEntryItem(BaseModel):
    student_id:     UUID
    marks_obtained: Optional[Decimal] = Field(None, ge=0, le=999.99)
    remarks:        Optional[str]     = None


class BulkMarkEntryIn(BaseModel):
    entries:     list[MarkEntryItem]
    edit_reason: Optional[str] = None   # mandatory when component.status = PUBLISHED and editing


class SingleMarkEditIn(BaseModel):
    marks_obtained: Optional[Decimal] = Field(None, ge=0, le=999.99)
    remarks:        Optional[str]     = None
    edit_reason:    Optional[str]     = None   # mandatory when component.status = PUBLISHED


# ---------------------------------------------------------------------------
# Mark entry — output schema
# ---------------------------------------------------------------------------

class MarkEntryOut(BaseModel):
    id:             UUID
    component_id:   UUID
    student_id:     UUID
    student_name:   Optional[str]     = None
    usn:            Optional[str]     = None
    marks_obtained: Optional[Decimal] = None
    remarks:        Optional[str]     = None
    marked_by:      Optional[UUID]    = None
    marked_at:      Optional[datetime] = None
    edited_by:      Optional[UUID]    = None
    edited_at:      Optional[datetime] = None
    edit_reason:    Optional[str]     = None
    created_at:     datetime
    updated_at:     Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BulkMarkEntryResult(BaseModel):
    component_id: UUID
    saved:        int
    first_marks:  int
    edits:        int


# ---------------------------------------------------------------------------
# Excel import schemas (2-phase preview/commit)
# ---------------------------------------------------------------------------

class MarksImportRowResult(BaseModel):
    row_number:     int
    student_name:   Optional[str]    = None
    student_id:     Optional[UUID]   = None
    usn:            Optional[str]    = None
    email:          Optional[str]    = None
    marks_obtained: Optional[Decimal] = None
    remarks:        Optional[str]    = None
    is_valid:       bool
    errors:         list[str]        = Field(default_factory=list)


class MarksImportPreviewOut(BaseModel):
    component_id:   UUID
    component_name: str
    max_marks:      Decimal
    total_rows:     int
    valid_rows:     int
    invalid_rows:   int
    rows:           list[MarksImportRowResult]


class MarksImportCommitResult(BaseModel):
    component_id: UUID
    total:        int
    saved:        int
    skipped:      int
    errors:       list[str]


# ---------------------------------------------------------------------------
# Student self-view
# ---------------------------------------------------------------------------

class StudentComponentView(BaseModel):
    component_id:   UUID
    component_type: str
    name:           str
    max_marks:      Decimal
    weightage:      Optional[Decimal]  = None
    due_date:       Optional[date]     = None
    display_order:  Optional[int]      = None
    status:         str                # PUBLISHED or LOCKED
    marks_obtained: Optional[Decimal]  = None
    remarks:        Optional[str]      = None

    model_config = ConfigDict(from_attributes=True)


class StudentCourseMarks(BaseModel):
    course_id:             UUID
    course_code:           str
    course_title:          str
    section_id:            UUID
    section_name:          str
    total_marks_obtained:  Optional[Decimal] = None   # sum of entered marks across PUBLISHED+LOCKED
    total_max_marks:       Optional[Decimal] = None   # sum of max_marks across PUBLISHED+LOCKED
    components:            list[StudentComponentView]


class MyMarksOut(BaseModel):
    student_id:   UUID
    student_name: str
    usn:          Optional[str] = None
    courses:      list[StudentCourseMarks]


# ---------------------------------------------------------------------------
# Analytics — Dean/Admin section report
# ---------------------------------------------------------------------------

class SectionStudentMarks(BaseModel):
    student_id:   UUID
    student_name: str
    usn:          Optional[str]    = None
    total_marks:  Optional[Decimal] = None
    total_max:    Optional[Decimal] = None
    fill_pct:     Optional[float]  = None   # % of components with marks entered

    model_config = ConfigDict(from_attributes=True)


class SectionMarksReportOut(BaseModel):
    section_id:      UUID
    section_name:    str
    course_id:       UUID
    course_code:     str
    course_title:    str
    components:      list[ComponentOut]
    students:        list[SectionStudentMarks]


# ---------------------------------------------------------------------------
# Faculty course overview
# ---------------------------------------------------------------------------

class FacultyCourseComponentSummary(BaseModel):
    course_id:      UUID
    course_code:    str
    course_title:   str
    section_id:     UUID
    section_name:   str
    total_students: int
    components:     list[ComponentOut]


# ---------------------------------------------------------------------------
# Readiness indicators — hall-ticket eligibility pre-check
# ---------------------------------------------------------------------------

class StudentReadiness(BaseModel):
    student_id:            UUID
    student_name:          str
    usn:                   Optional[str]  = None
    attendance_ready:      bool           # no attendance shortage in finalized sessions
    internal_marks_ready:  bool           # all LOCKED components filled for this student
    attendance_pct:        Optional[float] = None
    marks_fill_pct:        Optional[float] = None   # % of locked components with entries
    notes:                 list[str]      = Field(default_factory=list)


class SectionReadinessOut(BaseModel):
    section_id:         UUID
    section_name:       str
    course_id:          Optional[UUID]  = None
    course_code:        Optional[str]   = None
    total_students:     int
    attendance_ready_count:     int
    internal_marks_ready_count: int
    fully_ready_count:          int
    students:           list[StudentReadiness]

    @field_validator("fully_ready_count", mode="before")
    @classmethod
    def _compute_fully_ready(cls, v, info):
        return v
