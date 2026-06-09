"""Global Search schemas — H64.7."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class StudentHit(BaseModel):
    id:          UUID
    full_name:   str
    email:       str
    usn:         Optional[str]
    is_active:   bool


class FacultyHit(BaseModel):
    id:          UUID
    full_name:   str
    email:       str
    employee_id: Optional[str]
    is_active:   bool


class SectionHit(BaseModel):
    id:        UUID
    name:      str
    is_active: bool


class CourseHit(BaseModel):
    id:    UUID
    code:  str
    title: str


class SearchResultsOut(BaseModel):
    query:    str
    students: list[StudentHit]
    faculty:  list[FacultyHit]
    sections: list[SectionHit]
    courses:  list[CourseHit]
