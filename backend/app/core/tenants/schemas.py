import re
from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator

from app.core.auth.models import TenantStatus

_PW_UPPER = re.compile(r"[A-Z]")
_PW_LOWER = re.compile(r"[a-z]")
_PW_DIGIT = re.compile(r"\d")
_PW_SPECIAL = re.compile(r"[^A-Za-z0-9]")
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$")


def _validate_password_complexity(v: str) -> str:
    errors = []
    if len(v) < 8:
        errors.append("at least 8 characters")
    if not _PW_UPPER.search(v):
        errors.append("one uppercase letter")
    if not _PW_LOWER.search(v):
        errors.append("one lowercase letter")
    if not _PW_DIGIT.search(v):
        errors.append("one digit")
    if not _PW_SPECIAL.search(v):
        errors.append("one special character")
    if errors:
        raise ValueError("Password must contain " + ", ".join(errors))
    return v


def _validate_hex_color(v: Optional[str]) -> Optional[str]:
    if v is None or v.strip() == "":
        return None
    v = v.strip()
    if not _HEX_COLOR.match(v):
        raise ValueError("Color must be a hex code like #2563eb or #abc")
    return v.lower()


class CreateTenantRequest(BaseModel):
    name: str
    admin_email: EmailStr
    admin_password: str
    admin_full_name: str
    contact_email: Optional[EmailStr] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_length(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Tenant name must be at least 3 characters")
        if len(v) > 100:
            raise ValueError("Tenant name must be at most 100 characters")
        return v

    @field_validator("admin_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)

    @field_validator("primary_color", "secondary_color", mode="before")
    @classmethod
    def color_format(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    schema_name: str
    status: TenantStatus
    is_active: bool
    contact_email: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantUpdateRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_length(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Tenant name must be at least 3 characters")
        if len(v) > 100:
            raise ValueError("Tenant name must be at most 100 characters")
        return v

    @field_validator("primary_color", "secondary_color", mode="before")
    @classmethod
    def color_format(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)
