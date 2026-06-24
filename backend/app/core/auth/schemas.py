import re
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
    acad_program_id: Optional[UUID] = None
    department_id: Optional[UUID] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @model_validator(mode="after")
    def student_requires_program(self) -> "CreateUserRequest":
        if self.role == TenantRole.STUDENT and not self.acad_program_id:
            raise ValueError("acad_program_id is required when role is STUDENT")
        return self


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[TenantRole] = None
    is_active: Optional[bool] = None
    identifier: Optional[str] = None
    email: Optional[EmailStr] = None
    acad_program_id: Optional[UUID] = None
    department_id: Optional[UUID] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UpdatePlatformProfileRequest(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip() if v else v


class UpdatePlatformEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str


class PlatformChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "PlatformChangePasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class PlatformBrandingRequest(BaseModel):
    platform_name: Optional[str] = None
    company_name: Optional[str] = None
    support_email: Optional[EmailStr] = None
    support_phone: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None

    @field_validator("primary_color", "accent_color", mode="before")
    @classmethod
    def color_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        v = v.strip()
        if not re.match(r"^#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$", v):
            raise ValueError("Color must be a hex code like #2563eb or #abc")
        return v.lower()


class PlatformBrandingResponse(BaseModel):
    id: UUID
    platform_name: str
    company_name: str
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlatformSessionsResponse(BaseModel):
    active_session_count: int
    last_login_at: Optional[datetime] = None


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
    acad_program_id: Optional[UUID] = None
    acad_program_name: Optional[str] = None
    # Academic ownership fields (populated by list_users; None for non-applicable roles)
    department_name: Optional[str] = None
    department_code: Optional[str] = None
    academic_id: Optional[str] = None      # faculty_code (FACULTY/DEAN) | USN (STUDENT)
    program_names: list[str] = []          # all governed/teaching/enrolled programs
    program_ids: list[str] = []            # parallel list of program UUIDs (for filter)
    is_active: bool
    must_change_password: bool = False
    created_at: datetime
    grants: list[str] = []

    model_config = {"from_attributes": True}


class MeResponse(UserResponse):
    tenant_id: Optional[UUID]
    schema_name: Optional[str]
    first_login: bool = False


class PlatformMeResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    role: str = "SUPER_ADMIN"
    is_active: bool
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


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


# ---------------------------------------------------------------------------
# Institution branding (GET /auth/branding, PATCH /auth/branding)
# ---------------------------------------------------------------------------

class BrandingResponse(BaseModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None

    model_config = {"from_attributes": True}


class BrandingUpdateRequest(BaseModel):
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None

    @field_validator("logo_url", mode="before")
    @classmethod
    def empty_logo_to_none(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("primary_color", "secondary_color", mode="before")
    @classmethod
    def color_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        v = v.strip()
        if not re.match(r"^#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$", v):
            raise ValueError("Color must be a hex code like #2563eb or #abc")
        return v.lower()
