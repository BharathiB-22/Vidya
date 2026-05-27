from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from app.modules.m_academics.models import DegreeType


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------

class DepartmentCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None

    @field_validator("name", "code", mode="before")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("code", mode="after")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.upper()

    @field_validator("name", "code", mode="after")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be empty")
        return v


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("code", mode="after")
    @classmethod
    def uppercase_code(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


class DepartmentOut(BaseModel):
    id: UUID
    name: str
    code: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------

class ProgramCreate(BaseModel):
    department_id: UUID
    name: str
    code: str
    degree_type: DegreeType
    duration_years: int

    @field_validator("name", "code", mode="before")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("code", mode="after")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.upper()

    @field_validator("duration_years")
    @classmethod
    def valid_duration(cls, v: int) -> int:
        if not 1 <= v <= 6:
            raise ValueError("duration_years must be between 1 and 6")
        return v


class ProgramUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    degree_type: Optional[DegreeType] = None
    duration_years: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("code", mode="after")
    @classmethod
    def uppercase_code(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v

    @field_validator("duration_years")
    @classmethod
    def valid_duration(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not 1 <= v <= 6:
            raise ValueError("duration_years must be between 1 and 6")
        return v


class ProgramOut(BaseModel):
    id: UUID
    department_id: UUID
    name: str
    code: str
    degree_type: str
    duration_years: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

class BatchCreate(BaseModel):
    program_id: UUID
    name: str
    start_year: int
    end_year: int

    @field_validator("name", mode="before")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("start_year", "end_year")
    @classmethod
    def plausible_year(cls, v: int) -> int:
        if not 2000 <= v <= 2100:
            raise ValueError("year must be between 2000 and 2100")
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "BatchCreate":
        if self.end_year <= self.start_year:
            raise ValueError("end_year must be greater than start_year")
        return self


class BatchUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class BatchOut(BaseModel):
    id: UUID
    program_id: UUID
    name: str
    start_year: int
    end_year: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Semester
# ---------------------------------------------------------------------------

class SemesterCreate(BaseModel):
    batch_id: UUID
    number: int
    label: Optional[str] = None

    @field_validator("number")
    @classmethod
    def valid_number(cls, v: int) -> int:
        if not 1 <= v <= 12:
            raise ValueError("number must be between 1 and 12")
        return v


class SemesterUpdate(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None


class SemesterOut(BaseModel):
    id: UUID
    batch_id: UUID
    number: int
    label: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerateSemestersOut(BaseModel):
    created: int
    skipped: int
    semesters: List[SemesterOut]


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

class SectionCreate(BaseModel):
    semester_id: UUID
    name: str
    max_strength: Optional[int] = None

    @field_validator("name", mode="before")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("name", mode="after")
    @classmethod
    def uppercase_name(cls, v: str) -> str:
        return v.upper()

    @field_validator("max_strength")
    @classmethod
    def positive_strength(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("max_strength must be a positive integer")
        return v


class SectionUpdate(BaseModel):
    name: Optional[str] = None
    max_strength: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("name", mode="after")
    @classmethod
    def uppercase_name(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


class SectionOut(BaseModel):
    id: UUID
    semester_id: UUID
    name: str
    max_strength: Optional[int]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
