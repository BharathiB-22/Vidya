from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class SchoolCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None

    @field_validator("code", "name", mode="before")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("code", mode="after")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.upper()

    @field_validator("code", "name", mode="after")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be empty")
        return v


class SchoolUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("code", mode="after")
    @classmethod
    def uppercase_code(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


class SchoolOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
