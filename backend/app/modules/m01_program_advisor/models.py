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
    """Curriculum lifecycle. Ownership changes hands exactly twice, and never
    comes back.

    DRAFT / AI_GENERATING / GENERATION_FAILED
        The DEAN owns the curriculum and may edit everything: semesters,
        subjects, credits, labs, projects, elective baskets.
    PENDING_APPROVAL
        The GOVERNANCE AUTHORITY (Board / University Members) owns it. The Dean
        is read-only, permanently — this is a one-way handover. The Board edits
        the structure freely, generates the official syllabus, and approves.
    APPROVED
        Locked by the Board. Structure AND syllabus are frozen for everyone —
        Dean, Board, Faculty, Admin alike. A change is a NEW version.
    PUBLISHED
        The Dean has released the locked curriculum to Faculty and Students.
        Publishing does not unlock anything.

    There is no RETURNED, no REJECTED and no reopen. The Board is the academic
    authority: when it disagrees with the Dean's plan it enhances the plan
    itself rather than handing the work back. Approval is the only freeze, and
    the only way past it is a new version (see `fork_program`).
    """
    DRAFT              = "DRAFT"
    AI_GENERATING      = "AI_GENERATING"
    GENERATION_FAILED  = "GENERATION_FAILED"
    PENDING_APPROVAL   = "PENDING_APPROVAL"
    APPROVED           = "APPROVED"          # approved AND locked by the Board
    PUBLISHED          = "PUBLISHED"


class CourseType(str, enum.Enum):
    """What KIND of course this is — and therefore what official document it carries.

    This is not a label. It decides what the Board of Studies produces:

        THEORY         a full university syllabus: Unit I-V, objectives, outcomes,
                       text books, references
        LAB            a Lab Manual: experiment list, lab outcomes, equipment and
                       software, assessment guidelines. NO theory units — a
                       laboratory is not taught in five units and never was
        INTERNSHIP     no syllabus at all. Guidelines, duration, evaluation rubric,
                       weekly activities, company requirements, report and viva
                       formats
        MINI_PROJECT   no syllabus. Project guidelines, milestones, deliverables,
                       reviews, rubrics
        MAJOR_PROJECT  no syllabus. A project handbook: proposal format, timeline,
                       reviews, rubrics, final report format, demonstration, viva
        SEMINAR        no syllabus. Seminar guidelines

    Generating five units of theory for an internship is not a cosmetic error. It
    is a document the Board would have to throw away, and — if it slipped through —
    a regulation promising lectures that nobody will ever deliver.

    MINI_PROJECT and MAJOR_PROJECT are separate types rather than one PROJECT
    because they are different documents: a mini project is milestones and reviews
    inside one semester, while a major project is a handbook with a proposal, a
    demonstration and a viva. The two were a single PROJECT value until Phase A
    V2.3; migration 0086ten splits the existing rows by title.
    """
    THEORY        = "THEORY"
    LAB           = "LAB"
    INTERNSHIP    = "INTERNSHIP"
    MINI_PROJECT  = "MINI_PROJECT"
    MAJOR_PROJECT = "MAJOR_PROJECT"
    SEMINAR       = "SEMINAR"


# The types whose official document is NOT a syllabus. The Board approves a set of
# guidelines for these, and — unlike a theory syllabus — the Dean may then adapt
# them, because they depend on the company, the supervisor and the institution's
# policy in a way a taught syllabus does not. See m02.service.dean_edit_document.
NON_SYLLABUS_TYPES: frozenset[str] = frozenset({
    CourseType.INTERNSHIP.value,
    CourseType.MINI_PROJECT.value,
    CourseType.MAJOR_PROJECT.value,
    CourseType.SEMINAR.value,
})

# The types the Dean may edit AFTER the Board has approved them. Identical to
# NON_SYLLABUS_TYPES today, and deliberately a separate name: the reason a Dean may
# touch these is that their content depends on industry and supervisor allocation,
# not that they happen to lack units. If the two ever diverge, the call sites that
# mean one must not silently get the other.
DEAN_EDITABLE_TYPES: frozenset[str] = NON_SYLLABUS_TYPES


class ElectiveSlotStatus(str, enum.Enum):
    """An elective slot's own lifecycle, independent of its program's.

    DRAFT     the Dean may add, edit and remove the slot's choices
    PUBLISHED the choice list is frozen; students can see the slot
    OPEN      students may choose (or switch) their one option
    CLOSED    choices are frozen and the roster is final

    Deliberately separate from ProgramStatus: a published curriculum must still
    let the Dean fill in which subjects Elective 1 offers this year, and two
    programs may open their electives at different times.
    """
    DRAFT     = "DRAFT"
    PUBLISHED = "PUBLISHED"
    OPEN      = "OPEN"
    CLOSED    = "CLOSED"


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        Index("ix_programs_status",           "status"),
        Index("ix_programs_created_by",       "created_by_user_id"),
        Index("ix_programs_parent_version",   "parent_version_id"),
        Index("ix_programs_created_at",       "created_at"),
        Index("ix_programs_acad_program_id",  "acad_program_id"),
        # One curriculum version per (program, batch, version). Partial: legacy
        # rows predating batch-bound versioning have NULLs and are exempt.
        Index(
            "uq_programs_curriculum_version",
            "acad_program_id", "effective_from_batch_id", "version",
            unique=True,
            postgresql_where=text(
                "acad_program_id IS NOT NULL AND effective_from_batch_id IS NOT NULL"
            ),
        ),
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
    # Phase A: the Dean submits; the Board approves and locks.
    submitted_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    submitted_at        = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    approved_at         = Column(DateTime(timezone=True), nullable=True)
    locked_by_user_id   = Column(UUID(as_uuid=True), nullable=True)
    locked_at           = Column(DateTime(timezone=True), nullable=True)
    review_comment      = Column(Text, nullable=True)
    published_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    published_at        = Column(DateTime(timezone=True), nullable=True)
    # Stamped automatically the first time the Board generates the official
    # syllabus — the structure the syllabus was written against. There is no
    # "finalize" button and this does NOT freeze editing: the Board may revise
    # the structure right up to approval. What keeps a stale syllabus out of a
    # locked curriculum is the approve gate, not this column (see
    # governance.service.approve_and_lock and m02.service.invalidate_for_course).
    structure_finalized_at         = Column(DateTime(timezone=True), nullable=True)
    structure_finalized_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    # A published curriculum version is identified by
    # (acad_program_id, effective_from_batch_id, version) — "MCA, 2026-2028, v1".
    # Old batches stay on the version they were admitted under, forever.
    academic_year       = Column(String(9), nullable=True)    # '2026-2028'
    regulation_year     = Column(Integer, nullable=True)
    effective_from_batch_id = Column(
        UUID(as_uuid=True), ForeignKey("acad_batches.id", ondelete="SET NULL"), nullable=True,
    )
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
    """ONE curriculum elective slot in one program+semester — e.g. "Elective 1
    (3 credits)" in Semester 3.

    The slot is the curriculum fact. The Dean hangs any number of real,
    interchangeable option courses off it (AI301 Artificial Intelligence,
    DM301 Data Mining, DL301 Deep Learning, ...), each with its own code,
    syllabus, faculty and seats. A student takes exactly ONE of them, so the
    slot contributes `credits` to the curriculum exactly once — never the sum
    of its options. Compliance, semester load and program totals all read
    `credits` here, not from the member courses.

    Once the program is PUBLISHED the slot is itself the offering: a student in
    the matching semester picks ONE of its options (see
    m_academics.ElectiveRegistration). Nothing is opened or closed."""
    __tablename__ = "elective_baskets"
    __table_args__ = (
        Index("ix_elective_baskets_program_semester", "program_id", "semester"),
        Index("ix_elective_baskets_status", "status"),
    )

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id         = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    semester           = Column(Integer, nullable=False)
    name               = Column(String, nullable=False)
    # The slot's curriculum weight, independent of how many options it holds.
    credits            = Column(Integer, nullable=False, default=3, server_default=text("3"))
    description        = Column(Text, nullable=True)
    # The slot's own lifecycle. Choices may only change while this is DRAFT;
    # students may only register while it is OPEN. See ElectiveSlotStatus.
    status                 = Column(String(20), nullable=False, default=ElectiveSlotStatus.DRAFT.value,
                                    server_default=text("'DRAFT'"))
    published_at           = Column(DateTime(timezone=True), nullable=True)
    published_by_user_id   = Column(UUID(as_uuid=True), nullable=True)
    registration_opened_at = Column(DateTime(timezone=True), nullable=True)
    registration_closed_at = Column(DateTime(timezone=True), nullable=True)
    # Set when the curriculum is APPROVED. Freezes the slot's COMPOSITION — which
    # subjects it offers — forever. Distinct from `status` above, which is the
    # student-registration lifecycle and keeps moving on a published curriculum.
    # No elective option may be added or removed once this is set: an option is a
    # subject a student actually takes, so a late addition would smuggle a course
    # with no Board-approved syllabus into a locked curriculum.
    locked_at              = Column(DateTime(timezone=True), nullable=True)
    locked_by_user_id      = Column(UUID(as_uuid=True), nullable=True)
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
