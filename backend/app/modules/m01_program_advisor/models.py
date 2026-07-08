import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ProgramStatus(str, enum.Enum):
    DRAFT              = "DRAFT"
    AI_GENERATING      = "AI_GENERATING"
    GENERATION_FAILED  = "GENERATION_FAILED"
    PENDING_APPROVAL   = "PENDING_APPROVAL"
    APPROVED           = "APPROVED"
    PUBLISHED          = "PUBLISHED"


class CourseType(str, enum.Enum):
    THEORY     = "THEORY"
    LAB        = "LAB"
    PROJECT    = "PROJECT"
    INTERNSHIP = "INTERNSHIP"
    SEMINAR    = "SEMINAR"


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        Index("ix_programs_status",           "status"),
        Index("ix_programs_created_by",       "created_by_user_id"),
        Index("ix_programs_parent_version",   "parent_version_id"),
        Index("ix_programs_created_at",       "created_at"),
        Index("ix_programs_acad_program_id",  "acad_program_id"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version             = Column(Integer, nullable=False, default=1)
    parent_version_id   = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True)
    title               = Column(String, nullable=False)
    degree_type         = Column(String, nullable=False)
    department          = Column(String, nullable=False)
    duration_years      = Column(Integer, nullable=False)
    total_credits       = Column(Integer, nullable=False)
    acad_program_id     = Column(UUID(as_uuid=True), ForeignKey("acad_programs.id", ondelete="SET NULL"), nullable=True)
    status              = Column(
        Enum(ProgramStatus, native_enum=False),
        nullable=False,
        default=ProgramStatus.DRAFT,
    )
    ai_model            = Column(String, nullable=True)
    prompt_hash         = Column(String, nullable=True)
    ai_instructions     = Column(Text, nullable=True)
    approved_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    approved_at         = Column(DateTime(timezone=True), nullable=True)
    published_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    published_at        = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id  = Column(UUID(as_uuid=True), nullable=False)
    created_at          = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    parent_version = relationship(
        "Program",
        remote_side=[id],
        foreign_keys=[parent_version_id],
    )
    outcomes         = relationship("ProgramOutcome",  back_populates="program", cascade="all, delete-orphan")
    courses          = relationship("Course",          back_populates="program", cascade="all, delete-orphan")
    elective_baskets = relationship("ElectiveBasket",  back_populates="program", cascade="all, delete-orphan")


class ProgramOutcome(Base):
    __tablename__ = "program_outcomes"
    __table_args__ = (
        UniqueConstraint("program_id", "code"),
        Index("ix_program_outcomes_program", "program_id"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id    = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    code          = Column(String, nullable=False)
    description   = Column(Text, nullable=False)
    bloom_level   = Column(String, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    program = relationship("Program", back_populates="outcomes")


class ElectiveBasket(Base):
    """A named group of elective courses within one program+semester (e.g.
    'Artificial Intelligence Electives' containing AI, DL, ML, CV, NLP...).

    Electives are never modeled as a single standalone course — a course is
    only offerable as an elective once it belongs to a basket. Students
    register for ONE course from within an open basket (see
    m_academics.ElectiveOffering/ElectiveRegistration)."""
    __tablename__ = "elective_baskets"
    __table_args__ = (
        Index("ix_elective_baskets_program_semester", "program_id", "semester"),
    )

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id         = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    semester           = Column(Integer, nullable=False)
    name               = Column(String, nullable=False)
    description        = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at         = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at         = Column(DateTime(timezone=True), nullable=True)

    program = relationship("Program", back_populates="elective_baskets")
    courses = relationship("Course", back_populates="elective_basket")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("program_id", "code"),
        Index("ix_courses_program",          "program_id"),
        Index("ix_courses_program_semester", "program_id", "semester"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id          = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    code                = Column(String, nullable=False)
    title               = Column(String, nullable=False)
    credits             = Column(Integer, nullable=False)
    semester            = Column(Integer, nullable=False)
    course_type         = Column(String(20), nullable=True)
    is_elective         = Column(Boolean, nullable=False, default=False)
    elective_basket_id  = Column(UUID(as_uuid=True), ForeignKey("elective_baskets.id", ondelete="SET NULL"), nullable=True)
    is_ai_generated     = Column(Boolean, nullable=False, default=False)
    hours_lecture       = Column(Integer, nullable=True)
    hours_tutorial      = Column(Integer, nullable=True)
    hours_practical     = Column(Integer, nullable=True)
    description         = Column(Text, nullable=True)
    created_at          = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    program         = relationship("Program", back_populates="courses")
    elective_basket = relationship("ElectiveBasket", back_populates="courses")
    prerequisites   = relationship(
        "CoursePrerequisite",
        foreign_keys="CoursePrerequisite.course_id",
        back_populates="course",
        cascade="all, delete-orphan",
    )


class CoursePrerequisite(Base):
    __tablename__ = "course_prerequisites"
    __table_args__ = (
        UniqueConstraint("course_id", "prerequisite_course_id"),
        Index("ix_course_prereqs_course",  "course_id"),
        Index("ix_course_prereqs_prereq",  "prerequisite_course_id"),
    )

    id                     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id              = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    prerequisite_course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)

    course              = relationship("Course", foreign_keys=[course_id],              back_populates="prerequisites")
    prerequisite_course = relationship("Course", foreign_keys=[prerequisite_course_id])
