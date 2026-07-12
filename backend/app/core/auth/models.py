import uuid
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class TenantRole(str, enum.Enum):
    ADMIN     = "ADMIN"
    DEAN      = "DEAN"
    FACULTY   = "FACULTY"
    STUDENT   = "STUDENT"
    BOARD     = "BOARD"
    GUIDE     = "GUIDE"
    EVALUATOR = "EVALUATOR"


class TenantStatus(str, enum.Enum):
    PROVISIONING        = "PROVISIONING"
    ACTIVE              = "ACTIVE"
    INACTIVE            = "INACTIVE"
    ARCHIVED            = "ARCHIVED"
    FAILED              = "FAILED"
    DELETED             = "DELETED"
    PERMANENTLY_DELETED = "PERMANENTLY_DELETED"


class OTPPurpose(str, enum.Enum):
    PASSWORD_RESET = "PASSWORD_RESET"


class GovernanceType(str, enum.Enum):
    """What a tenant calls its academic governance authority.

    A DISPLAY NAME ONLY. The permissions, endpoints and workflow behind both
    values are identical — the TenantRole.BOARD role backs them either way.
    University A calls it a "Board"; University B calls it "University Members".
    """
    BOARD              = "BOARD"
    UNIVERSITY_MEMBERS = "UNIVERSITY_MEMBERS"


# ---------------------------------------------------------------------------
# PUBLIC SCHEMA MODELS
# ---------------------------------------------------------------------------

class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    schema_name = Column(String, unique=True, nullable=False)
    status = Column(Enum(TenantStatus, native_enum=False), nullable=False, default=TenantStatus.PROVISIONING)
    is_active = Column(Boolean, default=False, nullable=False)
    contact_email = Column(String, nullable=True)
    # P1.2 Task C: email domain for generated institution emails ({usn}@{domain})
    institution_domain = Column(String, nullable=True)
    # Phase A: display name for the academic governance authority. Behaviour is
    # identical for both values — see GovernanceType.
    governance_type = Column(
        String(30),
        nullable=False,
        default=GovernanceType.BOARD.value,
        server_default=text("'BOARD'"),
    )
    # NOTE: default_student_password_pattern intentionally NOT in ORM model.
    # The column is created by migration 0015pub. Add it here ONLY after that migration
    # has been applied to the database, to prevent SELECT failures on older deployments.
    logo_url = Column(String, nullable=True)
    primary_color = Column(String(7), nullable=True)
    secondary_color = Column(String(7), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id = Column(UUID(as_uuid=True), nullable=True)


class PlatformUser(Base):
    __tablename__ = "platform_users"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    avatar_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    refresh_tokens = relationship("PlatformRefreshToken", back_populates="user")
    otp_codes = relationship("PlatformOTPCode", back_populates="user")


class PlatformRefreshToken(Base):
    __tablename__ = "platform_refresh_tokens"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("public.platform_users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    replaced_by = Column(UUID(as_uuid=True), ForeignKey("public.platform_refresh_tokens.id"), nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    user = relationship("PlatformUser", back_populates="refresh_tokens")


class PlatformOTPCode(Base):
    __tablename__ = "platform_otp_codes"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("public.platform_users.id", ondelete="CASCADE"), nullable=False)
    otp_hash = Column(String, nullable=False)
    purpose = Column(Enum(OTPPurpose), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    user = relationship("PlatformUser", back_populates="otp_codes")


class PlatformBranding(Base):
    __tablename__ = "platform_branding"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform_name = Column(String(100), nullable=False, default="VIDYA AI")
    company_name = Column(String(100), nullable=False, default="SherpaVector")
    support_email = Column(String(255), nullable=True)
    support_phone = Column(String(50), nullable=True)
    logo_url = Column(String(500), nullable=True)
    favicon_url = Column(String(500), nullable=True)
    primary_color = Column(String(7), nullable=True)
    accent_color = Column(String(7), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))


class RefreshTokenIndex(Base):
    __tablename__ = "refresh_token_index"
    __table_args__ = {"schema": "public"}

    token_hash = Column(String, primary_key=True)
    schema_name = Column(String, nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))


# ---------------------------------------------------------------------------
# TENANT SCHEMA MODELS
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(TenantRole), nullable=False)
    full_name = Column(String, nullable=False)
    identifier = Column(String, nullable=True)
    # P1.2 Task C: institution email foundation (generation only — login unchanged)
    personal_email = Column(String, nullable=True)
    institution_email = Column(String, nullable=True)
    acad_program_id = Column(UUID(as_uuid=True), ForeignKey("acad_programs.id", ondelete="SET NULL"), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user")
    otp_codes = relationship("OTPCode", back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    replaced_by = Column(UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    user = relationship("User", back_populates="refresh_tokens")


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    otp_hash = Column(String, nullable=False)
    purpose = Column(Enum(OTPPurpose), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    user = relationship("User", back_populates="otp_codes")
