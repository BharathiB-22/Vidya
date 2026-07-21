import re
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional
from app.core.auth.models import TenantRole


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
    section_id: Optional[UUID] = None

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


class AvatarUrlMixin(BaseModel):
    """`avatar_url` is persisted as a storage object key (see core/storage/avatar.py).
    Sign it on the way out so clients always receive a loadable image URL, and
    so pre-existing full URLs and empty values keep behaving as before."""

    @field_validator("avatar_url", mode="after", check_fields=False)
    @classmethod
    def sign_avatar_url(cls, v: Optional[str]) -> Optional[str]:
        from app.core.storage.avatar import resolve_avatar_url

        return resolve_avatar_url(v)


class UserResponse(AvatarUrlMixin):
    id: UUID
    email: str
    role: TenantRole
    full_name: str
    identifier: Optional[str]
    avatar_url: Optional[str] = None
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


class PlatformMeResponse(AvatarUrlMixin):
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
    # The workspace the request is acting as (validated against the user's
    # entitled roles in get_current_user). None ⇒ act as the base role. This is
    # ALWAYS a role the user already holds — it can only re-select among held
    # roles, never elevate — so honouring it can never widen access.
    active_role: Optional[str] = None

    @property
    def is_super_admin(self) -> bool:
        return self.role == "SUPER_ADMIN"

    @property
    def viewing_role(self) -> str:
        """The single role that governs BOTH access and data scope for this
        request: the validated active workspace when one was sent, else the base
        role. Use this — never ``role`` — for permission gates and query scoping,
        so a Dean acting in the Faculty workspace is treated exactly as Faculty.
        ``role`` stays the base identity (for ``/me`` and audit attribution)."""
        return self.active_role or self.role


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
