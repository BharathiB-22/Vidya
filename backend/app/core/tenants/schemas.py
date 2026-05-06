from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator

from app.core.auth.models import TenantStatus


class CreateTenantRequest(BaseModel):
    name: str
    admin_email: EmailStr
    admin_password: str
    admin_full_name: str

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
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Admin password must be at least 8 characters")
        return v


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    schema_name: str
    status: TenantStatus
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantUpdateRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

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
