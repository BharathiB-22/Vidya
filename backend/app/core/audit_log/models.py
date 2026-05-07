import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class AuditEventType(str, enum.Enum):
    # Tenant auth flows
    AUTH_LOGIN_SUCCESS               = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILURE               = "AUTH_LOGIN_FAILURE"
    AUTH_LOGOUT                      = "AUTH_LOGOUT"
    AUTH_LOGOUT_ALL                  = "AUTH_LOGOUT_ALL"
    AUTH_TOKEN_REFRESH               = "AUTH_TOKEN_REFRESH"
    AUTH_TOKEN_REUSE_DETECTED        = "AUTH_TOKEN_REUSE_DETECTED"
    AUTH_PASSWORD_RESET_REQUESTED    = "AUTH_PASSWORD_RESET_REQUESTED"
    AUTH_PASSWORD_RESET_OTP_FAILED   = "AUTH_PASSWORD_RESET_OTP_FAILED"
    AUTH_PASSWORD_RESET_VERIFIED     = "AUTH_PASSWORD_RESET_VERIFIED"
    AUTH_PASSWORD_RESET_COMPLETED    = "AUTH_PASSWORD_RESET_COMPLETED"

    # Platform auth flows (SUPER_ADMIN)
    PLATFORM_LOGIN_SUCCESS             = "PLATFORM_LOGIN_SUCCESS"
    PLATFORM_LOGIN_FAILURE             = "PLATFORM_LOGIN_FAILURE"
    PLATFORM_LOGOUT                    = "PLATFORM_LOGOUT"
    PLATFORM_LOGOUT_ALL                = "PLATFORM_LOGOUT_ALL"
    PLATFORM_TOKEN_REFRESH             = "PLATFORM_TOKEN_REFRESH"
    PLATFORM_TOKEN_REUSE_DETECTED      = "PLATFORM_TOKEN_REUSE_DETECTED"
    PLATFORM_PASSWORD_RESET_REQUESTED  = "PLATFORM_PASSWORD_RESET_REQUESTED"
    PLATFORM_PASSWORD_RESET_OTP_FAILED = "PLATFORM_PASSWORD_RESET_OTP_FAILED"
    PLATFORM_PASSWORD_RESET_VERIFIED   = "PLATFORM_PASSWORD_RESET_VERIFIED"
    PLATFORM_PASSWORD_RESET_COMPLETED  = "PLATFORM_PASSWORD_RESET_COMPLETED"

    # User management (tenant-scoped)
    USER_CREATED      = "USER_CREATED"
    USER_UPDATED      = "USER_UPDATED"
    USER_DEACTIVATED  = "USER_DEACTIVATED"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"

    # Tenant management (platform-level)
    TENANT_PROVISIONED = "TENANT_PROVISIONED"
    TENANT_UPDATED     = "TENANT_UPDATED"
    TENANT_DEACTIVATED = "TENANT_DEACTIVATED"

    # Storage operations (tenant-scoped)
    STORAGE_ASSET_CREATED    = "STORAGE_ASSET_CREATED"
    STORAGE_ASSET_DOWNLOADED = "STORAGE_ASSET_DOWNLOADED"
    STORAGE_ASSET_DELETED    = "STORAGE_ASSET_DELETED"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_created",  "tenant_id",     "created_at"),
        Index("ix_audit_logs_event_created",   "event_type",    "created_at"),
        Index("ix_audit_logs_actor_created",   "actor_user_id", "created_at"),
        Index("ix_audit_logs_created",         "created_at"),
        {"schema": "public"},
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type    = Column(String, nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), nullable=True)
    actor_role    = Column(String, nullable=True)
    tenant_id     = Column(
        UUID(as_uuid=True),
        ForeignKey("public.tenants.id", ondelete="SET NULL"),
        nullable=True,
    )
    schema_name   = Column(String, nullable=True)
    target_entity = Column(String, nullable=True)
    target_id     = Column(String, nullable=True)
    metadata_     = Column("metadata", JSONB, nullable=True)
    ip_address    = Column(String, nullable=True)
    user_agent    = Column(String, nullable=True)
    created_at    = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
