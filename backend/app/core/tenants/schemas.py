import re
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.core.auth.models import GovernanceType, TenantStatus

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
    # Phase A: what this institution calls its curriculum approval authority.
    # Display name only — permissions are identical either way.
    governance_type: GovernanceType = GovernanceType.BOARD

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
    governance_type: GovernanceType = GovernanceType.BOARD
    created_at: datetime
    deleted_at: Optional[datetime] = None
    deleted_by_user_id: Optional[UUID] = None

    model_config = {"from_attributes": True}


class TenantUpdateRequest(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    status: Optional[TenantStatus] = None
    is_active: Optional[bool] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    governance_type: Optional[GovernanceType] = None

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

    @field_validator("status")
    @classmethod
    def status_transition_allowed(cls, v: Optional[TenantStatus]) -> Optional[TenantStatus]:
        if v is None:
            return v
        _blocked = (
            TenantStatus.PROVISIONING,
            TenantStatus.FAILED,
            TenantStatus.DELETED,
            TenantStatus.PERMANENTLY_DELETED,
        )
        if v in _blocked:
            raise ValueError(
                "Cannot set status to PROVISIONING, FAILED, DELETED, or PERMANENTLY_DELETED "
                "via update request — use the dedicated lifecycle endpoints"
            )
        return v

    @field_validator("primary_color", "secondary_color", mode="before")
    @classmethod
    def color_format(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class DeleteTenantRequest(BaseModel):
    confirm_slug: str


class PermanentDeleteTenantRequest(BaseModel):
    confirm_slug: str


# ---------------------------------------------------------------------------
# Platform monitoring stats
# ---------------------------------------------------------------------------

class ServiceHealthItem(BaseModel):
    service: str
    label:   str
    status:  str          # "healthy" | "unhealthy" | "skipped"
    latency_ms: float
    error_msg: Optional[str] = None


class TenantCounts(BaseModel):
    total:       int
    active:      int
    inactive:    int
    archived:    int
    provisioning: int
    failed:      int


class JobCounts(BaseModel):
    pending:    int
    running:    int
    completed:  int
    failed:     int
    total_24h:  int


class AIServiceInfo(BaseModel):
    name:       str
    configured: bool
    model:      str
    active:     bool      # True when this provider is currently selected


class AuditEventSummary(BaseModel):
    event_type:  str
    created_at:  datetime
    schema_name: Optional[str] = None
    metadata_:   Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class PlatformStatsResponse(BaseModel):
    health:         list[ServiceHealthItem]
    all_healthy:    bool
    tenants:        TenantCounts
    jobs:           JobCounts
    ai_services:    list[AIServiceInfo]
    recent_events:  list[AuditEventSummary]
    generated_at:   datetime


class TenantMigrationStatus(BaseModel):
    """Per-tenant migration state, returned by GET /tenants/migrations."""
    tenant_id: str
    tenant_name: str
    schema_name: str
    current_revision: Optional[str]
    head_revision: str
    is_current: bool
    last_status: Optional[str] = None       # 'success' | 'failed' | None
    last_migration_at: Optional[datetime] = None
    last_error: Optional[str] = None


class TenantMigrationResult(BaseModel):
    """Returned by POST /tenants/{id}/migrations/retry."""
    schema_name: str
    status: str                             # 'success' | 'failed' | 'current'
    from_revision: Optional[str] = None
    to_revision: Optional[str] = None
    error: Optional[str] = None


class PlatformSettingsResponse(BaseModel):
    # Platform profile
    platform_name:  str
    company_name:   str
    support_email:  str
    environment:    str
    build_version:  str

    # AI configuration (no secrets — only configured boolean + model name)
    ai_provider:          str
    gemini_configured:    bool
    gemini_model:         str
    gemini_enabled:       bool
    groq_configured:      bool
    groq_model:           str
    groq_enabled:         bool
    deepseek_configured:  bool
    deepseek_model:       str
    deepseek_enabled:     bool

    # Storage
    storage_provider: str
    s3_endpoint:      str
    s3_bucket:        str
    s3_region:        str
    s3_use_ssl:       bool
    max_upload_mb:    int

    # Email
    smtp_host:     str
    smtp_from:     str
    email_enabled: bool

    # Security (architectural constants exposed for transparency)
    jwt_enabled:           bool
    rbac_enabled:          bool
    tenant_isolation:      bool
    audit_logging_enabled: bool
    soft_delete_enabled:   bool
    access_token_expire_minutes: int
    refresh_token_expire_days:   int
