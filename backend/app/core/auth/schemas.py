from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional
from app.core.auth.models import TenantRole, OTPPurpose


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PlatformLoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleAuthRequest(BaseModel):
    credential: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetVerifyIn(BaseModel):
    email: EmailStr
    otp: str


class PasswordResetConfirmIn(BaseModel):
    reset_token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: TenantRole
    identifier: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[TenantRole] = None
    is_active: Optional[bool] = None
    identifier: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class PasswordResetTokenResponse(BaseModel):
    reset_token: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: TenantRole
    full_name: str
    identifier: Optional[str]
    is_active: bool
    must_change_password: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class MeResponse(UserResponse):
    tenant_id: Optional[UUID]
    schema_name: Optional[str]
    first_login: bool = False


# ---------------------------------------------------------------------------
# Internal schema (not serialized to HTTP responses directly)
# ---------------------------------------------------------------------------

class CurrentUser(BaseModel):
    user_id: UUID
    tenant_id: Optional[UUID]
    schema_name: Optional[str]
    role: str          # str not TenantRole so SUPER_ADMIN fits without being in TenantRole
    email: str

    @property
    def is_super_admin(self) -> bool:
        return self.role == "SUPER_ADMIN"


# ---------------------------------------------------------------------------
# TenantInfo (used by resolve_tenant dependency)
# ---------------------------------------------------------------------------

class TenantInfo(BaseModel):
    id: UUID
    slug: str
    schema_name: str
