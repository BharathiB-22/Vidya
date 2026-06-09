"""SIS Bulk Operations — H64.5 Pydantic schemas."""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BulkStudentIn(BaseModel):
    student_ids: list[UUID] = Field(..., min_length=1, max_length=200)
    action:      Literal["DEACTIVATE", "ARCHIVE"]
    reason:      Optional[str] = None


class BulkFacultyIn(BaseModel):
    faculty_ids: list[UUID] = Field(..., min_length=1, max_length=200)
    action:      Literal["DEACTIVATE", "ARCHIVE"]
    reason:      Optional[str] = None


class BulkOpResult(BaseModel):
    action:    str
    requested: int
    succeeded: int
    failed:    int
    errors:    list[str]
