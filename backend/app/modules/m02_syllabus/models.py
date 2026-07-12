import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class SyllabusStatus(str, enum.Enum):
    """The official syllabus belongs to the Board, which both writes it and
    approves it. There is therefore no submit/review handoff and no pending or
    rejected state — those existed only when Faculty authored syllabi for a Dean
    to review, which is the workflow Phase A removed.

    DRAFT          the Board is working on it (AI-generated or hand-written)
    AI_GENERATING  a generation job is in flight
    APPROVED       the Board has signed this syllabus off
    LOCKED         frozen with the curriculum at approval — nobody edits, ever

    A structural edit to the course (credits, L-T-P, title, semester) sends an
    APPROVED syllabus back to DRAFT: it was written against a structure that has
    since moved, so the Board must look at it again before the curriculum can be
    approved. See m02.service.invalidate_for_course.
    """
    DRAFT          = "DRAFT"
    AI_GENERATING  = "AI_GENERATING"
    APPROVED       = "APPROVED"
    LOCKED         = "LOCKED"


class BloomLevel(str, enum.Enum):
    REMEMBER   = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY      = "APPLY"
    ANALYSE    = "ANALYSE"
    EVALUATE   = "EVALUATE"
    CREATE     = "CREATE"


class MappingStrength(str, enum.Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


class RefType(str, enum.Enum):
    """A reference's type, and the bibliography section it prints under.

    An official university syllabus ends with four sections; these six types fold
    into them (see m02.formatting.BIBLIOGRAPHY_SECTIONS):

        Text Books        <- TEXTBOOK
        Reference Books   <- REFERENCE, JOURNAL
        Suggested Reading <- SUGGESTED_READING
        Web Resources     <- WEB_RESOURCE, ONLINE
    """
    TEXTBOOK          = "TEXTBOOK"
    REFERENCE         = "REFERENCE"
    JOURNAL           = "JOURNAL"
    ONLINE            = "ONLINE"
    SUGGESTED_READING = "SUGGESTED_READING"
    WEB_RESOURCE      = "WEB_RESOURCE"


class RefSource(str, enum.Enum):
    CROSSREF    = "CROSSREF"
    OPENLIBRARY = "OPENLIBRARY"
    MANUAL      = "MANUAL"


class Syllabus(Base):
    __tablename__ = "syllabi"
    __table_args__ = (
        Index("ix_syllabi_course",          "course_id"),
        Index("ix_syllabi_course_version",  "course_id", "version"),
        Index("ix_syllabi_status",          "status"),
        Index("ix_syllabi_created_by",      "created_by_user_id"),
        Index("ix_syllabi_parent_version",  "parent_version_id"),
        Index("ix_syllabi_doc_type",        "doc_type"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id           = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    version             = Column(Integer, nullable=False, default=1)
    parent_version_id   = Column(UUID(as_uuid=True), ForeignKey("syllabi.id"), nullable=True)
    status              = Column(
        Enum(SyllabusStatus, native_enum=False),
        nullable=False,
        default=SyllabusStatus.DRAFT,
    )
    custom_instructions = Column(Text, nullable=True)
    change_note         = Column(Text, nullable=True)
    ai_model            = Column(String, nullable=True)
    prompt_hash         = Column(String, nullable=True)

    # WHICH official document this row is — THEORY | LAB | INTERNSHIP |
    # MINI_PROJECT | MAJOR_PROJECT | SEMINAR (m01.models.CourseType).
    #
    # A SNAPSHOT of the course's type taken when the document was generated, not a
    # read-through to courses.course_type. If a Dean reclassifies a course from LAB
    # to THEORY after the Board approved its lab manual, that approved document is
    # still a lab manual, and this row must keep saying so rather than re-labelling
    # an experiment list as a syllabus.
    doc_type            = Column(String(20), nullable=False, server_default="THEORY")

    # The body of every NON-theory document: the lab manual's experiments and
    # equipment, the internship's rubric and weekly activities, the project
    # handbook's milestones and viva. Validated per type by the *Document schemas
    # in m02/schemas.py — see DOCUMENT_SCHEMAS.
    #
    # Empty ({}) for THEORY, whose document IS its units, outcomes and references.
    document            = Column(JSONB, nullable=False, server_default="{}")

    # Course Objectives — a list of strings. Distinct from Course Outcomes: the
    # objectives say what the course sets out to teach, the outcomes what the
    # student can do afterwards. Official university syllabi carry both.
    objectives          = Column(JSONB, nullable=False, server_default="[]")
    # Practical Components — a list of strings. Populated for Lab courses and any
    # course with practical hours; empty otherwise.
    practical_components = Column(JSONB, nullable=False, server_default="[]")
    # Internal Assessment suggestions — CIE components, weightings, assignment
    # patterns. A list of strings, and legitimately empty for some courses.
    internal_assessment  = Column(JSONB, nullable=False, server_default="[]")
    created_by_user_id  = Column(UUID(as_uuid=True), nullable=False)
    approved_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    approved_at         = Column(DateTime(timezone=True), nullable=True)
    locked_by_user_id   = Column(UUID(as_uuid=True), nullable=True)
    locked_at           = Column(DateTime(timezone=True), nullable=True)
    board_comment       = Column(Text, nullable=True)

    # The Dean's post-approval adaptation of a guideline document (Internship, Mini
    # Project, Major Project, Seminar — never a theory syllabus). Those documents
    # depend on the company, the supervisor and institutional policy, so the Dean
    # may adjust them after the Board has signed off; a taught syllabus they may not
    # touch. See m02.service.dean_edit_document.
    #
    # Stamped because the edit lands on an APPROVED, otherwise-immutable row.
    # Without it, the Board's approved document and the Dean's adaptation of it are
    # indistinguishable in the record, and the governance trail cannot say who wrote
    # the rubric a student was marked against.
    dean_edited_at         = Column(DateTime(timezone=True), nullable=True)
    dean_edited_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at          = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    parent_version = relationship(
        "Syllabus",
        remote_side=[id],
        foreign_keys=[parent_version_id],
    )
    outcomes    = relationship("CourseOutcome",    back_populates="syllabus", cascade="all, delete-orphan")
    units       = relationship("SyllabusUnit",     back_populates="syllabus", cascade="all, delete-orphan")
    references  = relationship("SyllabusReference", back_populates="syllabus", cascade="all, delete-orphan")


class CourseOutcome(Base):
    __tablename__ = "course_outcomes"
    __table_args__ = (
        UniqueConstraint("syllabus_id", "code"),
        Index("ix_course_outcomes_syllabus", "syllabus_id"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id   = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False)
    code          = Column(String, nullable=False)
    description   = Column(Text, nullable=False)
    bloom_level   = Column(
        Enum(BloomLevel, native_enum=False),
        nullable=False,
    )
    display_order = Column(Integer, nullable=False, default=0)
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at    = Column(DateTime(timezone=True), nullable=True)

    syllabus = relationship("Syllabus", back_populates="outcomes")
    mappings = relationship("COPOMapping", back_populates="outcome", cascade="all, delete-orphan")


class COPOMapping(Base):
    __tablename__ = "co_po_mappings"
    __table_args__ = (
        UniqueConstraint("co_id", "po_id"),
        Index("ix_co_po_mappings_co",  "co_id"),
        Index("ix_co_po_mappings_po",  "po_id"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    co_id            = Column(UUID(as_uuid=True), ForeignKey("course_outcomes.id", ondelete="CASCADE"), nullable=False)
    po_id            = Column(UUID(as_uuid=True), ForeignKey("program_outcomes.id", ondelete="CASCADE"), nullable=False)
    mapping_strength = Column(
        Enum(MappingStrength, native_enum=False),
        nullable=False,
        default=MappingStrength.MEDIUM,
    )
    justification    = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    outcome = relationship("CourseOutcome", back_populates="mappings")


class SyllabusUnit(Base):
    __tablename__ = "syllabus_units"
    __table_args__ = (
        UniqueConstraint("syllabus_id", "unit_number"),
        Index("ix_syllabus_units_syllabus", "syllabus_id"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id   = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False)
    unit_number   = Column(Integer, nullable=False)
    title         = Column(String, nullable=False)

    # The unit's official prose block — the thing that actually PRINTS in the
    # regulation document:
    #
    #     Introduction to Computer Systems, Evolution of Computing, Von Neumann
    #     Architecture, Instruction Cycle, Processor Organization, Memory
    #     Hierarchy, Cache Memory, Input/Output Organization, Performance Metrics.
    #
    # A flowing sequence of the concepts the unit covers, in teaching order. NOT a
    # bullet list — a Board of Studies publishes prose, not an outline.
    content       = Column(Text, nullable=True)

    # The structured breakdown UNDERNEATH the document: topic titles, their
    # descriptions, sub-concepts and hour estimates.
    #
    # Deliberately kept alongside `content` rather than replaced by it. The two
    # serve different readers: `content` is what a human sees in the published
    # syllabus, while `topics` is what the course-kit generator reads to plan
    # lessons (workers/heavy/course_kit_generation.py builds its unit_topics from
    # this). Collapsing them into prose would silently degrade every course kit
    # generated from the syllabus afterwards.
    topics        = Column(JSONB, nullable=False, server_default="[]")

    total_hours   = Column(Integer, nullable=False)
    pedagogy      = Column(String, nullable=True)
    bloom_summary = Column(JSONB, nullable=True)
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at    = Column(DateTime(timezone=True), nullable=True)

    syllabus = relationship("Syllabus", back_populates="units")


class SyllabusReference(Base):
    __tablename__ = "syllabus_references"
    __table_args__ = (
        Index("ix_syllabus_references_syllabus", "syllabus_id"),
        Index("ix_syllabus_references_source",   "source"),
    )

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id  = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False)
    title        = Column(Text, nullable=False)
    authors      = Column(JSONB, nullable=False, server_default="[]")
    year         = Column(Integer, nullable=True)
    ref_type     = Column(
        Enum(RefType, native_enum=False),
        nullable=False,
        default=RefType.TEXTBOOK,
    )
    source       = Column(
        Enum(RefSource, native_enum=False),
        nullable=False,
        default=RefSource.MANUAL,
    )
    doi          = Column(String, nullable=True)
    isbn         = Column(String, nullable=True)
    url          = Column(Text, nullable=True)
    publisher    = Column(String, nullable=True)
    is_confirmed = Column(Boolean, nullable=False, default=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at   = Column(DateTime(timezone=True), nullable=True)

    syllabus = relationship("Syllabus", back_populates="references")
