"""Legacy onboarding academic models.

These tables were renamed to _legacy_* by migration 0020ten.
Master data is now owned by acad_departments / acad_programs (m_academics).
These classes are kept so SQLAlchemy metadata stays consistent but are no
longer referenced by any live code path.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from app.database import Base


class LegacyAcademicDepartment(Base):
    __tablename__ = "_legacy_academic_departments"
    __table_args__ = (UniqueConstraint("code", name="uq_academic_departments_code"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    code = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    programs = relationship("LegacyAcademicProgram", back_populates="department", lazy="select")


class LegacyAcademicProgram(Base):
    __tablename__ = "_legacy_academic_programs"
    __table_args__ = (UniqueConstraint("code", name="uq_academic_programs_code"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dept_id = Column(UUID(as_uuid=True), ForeignKey("_legacy_academic_departments.id"), nullable=True)
    name = Column(String(200), nullable=False)
    code = Column(String(20), nullable=False)
    duration_years = Column(Integer, nullable=False, default=2)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    department = relationship("LegacyAcademicDepartment", back_populates="programs")
