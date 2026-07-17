"""My Subjects / Subject Details — Pydantic schemas (student self-service)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.modules.m11_sis.marks_schemas import StudentCourseMarks


class MySubjectSummary(BaseModel):
    course_id: UUID
    course_code: str
    course_title: str
    credits: int
    semester: int
    course_type: Optional[str] = None
    is_elective: bool
    section_id: UUID
    section_name: str
    faculty_user_id: Optional[UUID] = None
    faculty_name: Optional[str] = None
    faculty_designation: Optional[str] = None
    syllabus_id: Optional[UUID] = None
    syllabus_status: Optional[str] = None


class MySubjectsOut(BaseModel):
    student_id: UUID
    student_name: str
    usn: Optional[str] = None
    semester_id: Optional[UUID] = None
    subjects: list[MySubjectSummary]


class SubjectFacultyInfo(BaseModel):
    user_id: UUID
    name: str
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    office_location: Optional[str] = None
    photo_url: Optional[str] = None


class SubjectUnitTopicOut(BaseModel):
    """One entry of SyllabusUnit.topics — the structured breakdown under the
    unit's printed prose."""
    title: str
    description: Optional[str] = None
    hours_estimate: Optional[int] = None


class SyllabusUnitOut(BaseModel):
    unit_number: int
    title: str
    hours: Optional[int] = None
    # The unit's official prose block — what prints in the regulation.
    content: Optional[str] = None
    topics: list[SubjectUnitTopicOut] = []
    pedagogy: Optional[str] = None


class SubjectSyllabusReferenceOut(BaseModel):
    """A bibliography entry. `ref_type` drives which printed section the student
    sees it under (Text Books / Reference Books / Suggested Reading / Web
    Resources) — the same buckets m02.formatting.BIBLIOGRAPHY_SECTIONS uses."""
    title: str
    authors: list[str] = []
    year: Optional[int] = None
    ref_type: str
    publisher: Optional[str] = None
    doi: Optional[str] = None
    isbn: Optional[str] = None
    url: Optional[str] = None


class SubjectCourseOutcomeOut(BaseModel):
    code: str
    description: str
    bloom_level: Optional[str] = None
    display_order: Optional[int] = None


class SubjectDetailOut(BaseModel):
    course_id: UUID
    course_code: str
    course_title: str
    credits: int
    semester: int
    course_type: Optional[str] = None
    is_elective: bool
    description: Optional[str] = None
    hours_lecture: Optional[int] = None
    hours_tutorial: Optional[int] = None
    hours_practical: Optional[int] = None
    section_id: UUID
    section_name: str
    faculty: Optional[SubjectFacultyInfo] = None
    syllabus_id: Optional[UUID] = None
    syllabus_version: Optional[int] = None
    syllabus_status: Optional[str] = None
    syllabus_teaching_hours: Optional[int] = None
    syllabus_hours_per_week: Optional[int] = None
    objectives: list[str] = []
    practical_components: list[str] = []
    internal_assessment: list[str] = []
    units: list[SyllabusUnitOut] = []
    references: list[SubjectSyllabusReferenceOut] = []
    course_outcomes: list[SubjectCourseOutcomeOut] = []
    internal_marks: Optional[StudentCourseMarks] = None
