"""
SIS Results Management — H60 SQLAlchemy models.

Tables:
  sis_grading_policies       — configurable grade band definition per tenant/program
  sis_grading_policy_bands   — one row per grade letter per policy
  sis_result_declarations    — one per exam session; drives result lifecycle
  sis_external_marks         — university/external exam marks entry
  sis_subject_results        — computed per-student per-course result (immutable after LOCKED)
  sis_semester_results       — SGPA / CGPA / ranks per student per declaration
  sis_grace_marks_log        — append-only Dean-authorised grace mark audit trail

Result declaration lifecycle:
  DRAFT → VERIFIED → PUBLISHED → LOCKED

Students only see PUBLISHED declarations.
Grace marks require Dean gate with mandatory reason; logged in sis_grace_marks_log.

Future-proof for: SUPPLEMENTARY, REVALUATION, IMPROVEMENT via declaration_type +
source_declaration_id + attempt_number chain.

Snapshot fields on sis_result_declarations preserve historical grade card accuracy
even when semester labels or grading policy names are later renamed.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index,
    Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class DeclarationType(str, enum.Enum):
    REGULAR       = "REGULAR"
    SUPPLEMENTARY = "SUPPLEMENTARY"
    IMPROVEMENT   = "IMPROVEMENT"
    REVALUATION   = "REVALUATION"


class DeclarationStatus(str, enum.Enum):
    DRAFT     = "DRAFT"
    VERIFIED  = "VERIFIED"
    PUBLISHED = "PUBLISHED"
    LOCKED    = "LOCKED"


class ResultStatus(str, enum.Enum):
    PENDING   = "PENDING"
    PASS      = "PASS"
    FAIL      = "FAIL"
    ABSENT    = "ABSENT"
    WITHHELD  = "WITHHELD"


class OverallResultStatus(str, enum.Enum):
    PASS        = "PASS"
    FAIL        = "FAIL"
    WITHHELD    = "WITHHELD"
    PROVISIONAL = "PROVISIONAL"


# ─────────────────────────────────────────────────────────────────────────────
# Table 1: sis_grading_policies
# ─────────────────────────────────────────────────────────────────────────────

class SisGradingPolicy(Base):
    __tablename__ = "sis_grading_policies"
    __table_args__ = (
        Index("ix_grading_policies_is_default", "is_default", "is_active"),
        Index("ix_grading_policies_program_id", "program_id"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name             = Column(String(100), nullable=False)
    # NULL = global policy; non-NULL = program-specific (overrides global)
    program_id       = Column(UUID(as_uuid=True), nullable=True)
    pass_percentage  = Column(Numeric(5, 2), nullable=False, server_default=text("40.0"))
    is_default       = Column(Boolean, nullable=False, server_default=text("false"))
    is_active        = Column(Boolean, nullable=False, server_default=text("true"))
    created_by       = Column(UUID(as_uuid=True), nullable=False)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at       = Column(DateTime(timezone=True), nullable=True)

    bands = relationship(
        "SisGradingPolicyBand",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="SisGradingPolicyBand.display_order",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Table 2: sis_grading_policy_bands
# ─────────────────────────────────────────────────────────────────────────────

class SisGradingPolicyBand(Base):
    __tablename__ = "sis_grading_policy_bands"
    __table_args__ = (
        UniqueConstraint("policy_id", "grade_letter", name="uq_grading_bands_policy_letter"),
        Index("ix_grading_bands_policy_id", "policy_id"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id       = Column(UUID(as_uuid=True),
                             ForeignKey("sis_grading_policies.id", ondelete="CASCADE"),
                             nullable=False)
    grade_letter    = Column(String(5),     nullable=False)   # A+, A, B+, B, C+, C, D, F
    min_percentage  = Column(Numeric(5, 2), nullable=False)   # inclusive lower bound
    max_percentage  = Column(Numeric(5, 2), nullable=False)   # inclusive upper bound
    grade_point     = Column(Numeric(4, 2), nullable=False)   # 10.0, 9.0, 8.5, …
    is_pass         = Column(Boolean,       nullable=False, server_default=text("true"))
    display_order   = Column(SmallInteger,  nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    policy = relationship("SisGradingPolicy", back_populates="bands")


# ─────────────────────────────────────────────────────────────────────────────
# Table 3: sis_result_declarations
# ─────────────────────────────────────────────────────────────────────────────

class SisResultDeclaration(Base):
    __tablename__ = "sis_result_declarations"
    __table_args__ = (
        UniqueConstraint(
            "exam_session_id", "declaration_type",
            name="uq_result_declarations_session_type",
        ),
        Index("ix_result_declarations_semester_status", "semester_id", "status"),
        Index("ix_result_declarations_status",          "status"),
        Index("ix_result_declarations_type",            "declaration_type"),
        Index("ix_result_declarations_exam_session",    "exam_session_id"),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Context
    exam_session_id      = Column(UUID(as_uuid=True),
                                  ForeignKey("sis_exam_sessions.id", ondelete="RESTRICT"),
                                  nullable=False)
    semester_id          = Column(UUID(as_uuid=True),
                                  ForeignKey("acad_semesters.id", ondelete="RESTRICT"),
                                  nullable=False)

    # Snapshots — preserve historical grade card accuracy
    snapshot_academic_year       = Column(String(20),  nullable=False, server_default=text("''"))
    snapshot_semester_name       = Column(String(100), nullable=False, server_default=text("''"))
    snapshot_grading_policy_name = Column(String(100), nullable=False, server_default=text("''"))

    # Classification
    declaration_type     = Column(String(20),  nullable=False, server_default=text("'REGULAR'"))
    # Link back to original for SUPPLEMENTARY / REVALUATION chains
    source_declaration_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sis_result_declarations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Grading policy (pinned at declaration creation)
    grading_policy_id    = Column(UUID(as_uuid=True),
                                  ForeignKey("sis_grading_policies.id", ondelete="RESTRICT"),
                                  nullable=False)

    # Metadata
    title                = Column(String(200), nullable=True)
    notes                = Column(Text,        nullable=True)
    # When true, compute() checks that all internal marks components are LOCKED
    internal_marks_required = Column(Boolean, nullable=False, server_default=text("true"))

    # Lifecycle status
    status               = Column(String(15), nullable=False, server_default=text("'DRAFT'"))

    # Human gates
    verified_by          = Column(UUID(as_uuid=True),         nullable=True)
    verified_at          = Column(DateTime(timezone=True),     nullable=True)
    published_by         = Column(UUID(as_uuid=True),         nullable=True)
    published_at         = Column(DateTime(timezone=True),     nullable=True)
    locked_by            = Column(UUID(as_uuid=True),         nullable=True)
    locked_at            = Column(DateTime(timezone=True),     nullable=True)

    created_by           = Column(UUID(as_uuid=True),         nullable=False)
    created_at           = Column(DateTime(timezone=True),    nullable=False, server_default=text("now()"))
    updated_at           = Column(DateTime(timezone=True),    nullable=True)

    external_marks   = relationship("SisExternalMarks",   back_populates="declaration",
                                    cascade="all, delete-orphan")
    subject_results  = relationship("SisSubjectResult",   back_populates="declaration",
                                    cascade="all, delete-orphan")
    semester_results = relationship("SisSemesterResult",  back_populates="declaration",
                                    cascade="all, delete-orphan")
    grace_marks_log  = relationship("SisGraceMarksLog",   back_populates="declaration")


# ─────────────────────────────────────────────────────────────────────────────
# Table 4: sis_external_marks
# ─────────────────────────────────────────────────────────────────────────────

class SisExternalMarks(Base):
    __tablename__ = "sis_external_marks"
    __table_args__ = (
        UniqueConstraint(
            "declaration_id", "student_id", "course_id",
            name="uq_external_marks_declaration_student_course",
        ),
        Index("ix_external_marks_declaration_section", "declaration_id", "section_id"),
        Index("ix_external_marks_student",             "student_id"),
        Index("ix_external_marks_declaration_id",      "declaration_id"),
    )

    id                       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    declaration_id           = Column(UUID(as_uuid=True),
                                      ForeignKey("sis_result_declarations.id", ondelete="RESTRICT"),
                                      nullable=False)
    student_id               = Column(UUID(as_uuid=True), nullable=False)   # plain UUID
    course_id                = Column(UUID(as_uuid=True),
                                      ForeignKey("courses.id", ondelete="RESTRICT"),
                                      nullable=False)
    section_id               = Column(UUID(as_uuid=True),
                                      ForeignKey("acad_sections.id", ondelete="RESTRICT"),
                                      nullable=False)

    external_marks_obtained  = Column(Numeric(6, 2), nullable=True)    # NULL = not yet entered
    external_marks_max       = Column(Numeric(6, 2), nullable=False)

    is_absent                = Column(Boolean,       nullable=False, server_default=text("false"))
    attempt_number           = Column(SmallInteger,  nullable=False, server_default=text("1"))

    # Entry tracking
    entered_by   = Column(UUID(as_uuid=True),         nullable=True)
    entered_at   = Column(DateTime(timezone=True),     nullable=True)
    # Edit tracking (mandatory reason after DRAFT)
    edited_by    = Column(UUID(as_uuid=True),         nullable=True)
    edited_at    = Column(DateTime(timezone=True),     nullable=True)
    edit_reason  = Column(Text,                        nullable=True)

    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at   = Column(DateTime(timezone=True), nullable=True)

    declaration = relationship("SisResultDeclaration", back_populates="external_marks")


# ─────────────────────────────────────────────────────────────────────────────
# Table 5: sis_subject_results
# ─────────────────────────────────────────────────────────────────────────────

class SisSubjectResult(Base):
    __tablename__ = "sis_subject_results"
    __table_args__ = (
        UniqueConstraint(
            "declaration_id", "student_id", "course_id",
            name="uq_subject_results_declaration_student_course",
        ),
        Index("ix_subject_results_student_semester",    "student_id", "semester_id"),
        Index("ix_subject_results_declaration_status",  "declaration_id", "result_status"),
        Index("ix_subject_results_declaration_section", "declaration_id", "section_id"),
        Index("ix_subject_results_student",             "student_id"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    declaration_id  = Column(UUID(as_uuid=True),
                             ForeignKey("sis_result_declarations.id", ondelete="RESTRICT"),
                             nullable=False)
    student_id      = Column(UUID(as_uuid=True), nullable=False)   # plain UUID
    course_id       = Column(UUID(as_uuid=True),
                             ForeignKey("courses.id", ondelete="RESTRICT"),
                             nullable=False)
    section_id      = Column(UUID(as_uuid=True),
                             ForeignKey("acad_sections.id", ondelete="RESTRICT"),
                             nullable=False)
    semester_id     = Column(UUID(as_uuid=True),
                             ForeignKey("acad_semesters.id", ondelete="RESTRICT"),
                             nullable=False)

    # Marks components
    internal_marks  = Column(Numeric(6, 2), nullable=True)   # aggregated from locked entries
    external_marks  = Column(Numeric(6, 2), nullable=True)
    # Grace marks: nullable; only set via Dean gate; see sis_grace_marks_log
    grace_marks     = Column(Numeric(6, 2), nullable=True)
    total_marks     = Column(Numeric(6, 2), nullable=True)   # internal + external + grace
    max_marks       = Column(Numeric(6, 2), nullable=False)
    percentage      = Column(Numeric(5, 2), nullable=True)

    # Grade
    grade_letter    = Column(String(5),     nullable=True)
    grade_point     = Column(Numeric(4, 2), nullable=True)
    is_pass         = Column(Boolean,       nullable=True)

    # Result
    result_status   = Column(String(10), nullable=False, server_default=text("'PENDING'"))

    # Credits
    credits_attempted = Column(Numeric(4, 2), nullable=True)
    credits_earned    = Column(Numeric(4, 2), nullable=True)   # 0 if FAIL

    attempt_number  = Column(SmallInteger, nullable=False, server_default=text("1"))
    computed_at     = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at      = Column(DateTime(timezone=True), nullable=True)

    declaration  = relationship("SisResultDeclaration", back_populates="subject_results")
    grace_log    = relationship("SisGraceMarksLog",     back_populates="subject_result")


# ─────────────────────────────────────────────────────────────────────────────
# Table 6: sis_semester_results
# ─────────────────────────────────────────────────────────────────────────────

class SisSemesterResult(Base):
    __tablename__ = "sis_semester_results"
    __table_args__ = (
        UniqueConstraint(
            "declaration_id", "student_id",
            name="uq_semester_results_declaration_student",
        ),
        Index("ix_semester_results_student",          "student_id"),
        Index("ix_semester_results_declaration_sgpa", "declaration_id", "sgpa"),
        Index("ix_semester_results_semester",         "semester_id"),
    )

    id                      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    declaration_id          = Column(UUID(as_uuid=True),
                                     ForeignKey("sis_result_declarations.id", ondelete="RESTRICT"),
                                     nullable=False)
    student_id              = Column(UUID(as_uuid=True), nullable=False)   # plain UUID
    semester_id             = Column(UUID(as_uuid=True),
                                     ForeignKey("acad_semesters.id", ondelete="RESTRICT"),
                                     nullable=False)

    sgpa                    = Column(Numeric(4, 2), nullable=True)
    cgpa                    = Column(Numeric(4, 2), nullable=True)
    total_credits_attempted = Column(Numeric(6, 2), nullable=True)
    total_credits_earned    = Column(Numeric(6, 2), nullable=True)

    # Overall semester result for graduation audits / transcripts
    overall_result_status   = Column(String(15), nullable=True)   # PASS/FAIL/WITHHELD/PROVISIONAL

    # Rank within section and program for this semester
    section_rank            = Column(Integer,     nullable=True)
    program_rank            = Column(Integer,     nullable=True)

    computed_at             = Column(DateTime(timezone=True), nullable=True)
    created_at              = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at              = Column(DateTime(timezone=True), nullable=True)

    declaration = relationship("SisResultDeclaration", back_populates="semester_results")


# ─────────────────────────────────────────────────────────────────────────────
# Table 7: sis_grace_marks_log  (append-only audit)
# ─────────────────────────────────────────────────────────────────────────────

class SisGraceMarksLog(Base):
    __tablename__ = "sis_grace_marks_log"
    __table_args__ = (
        Index("ix_grace_marks_log_declaration",        "declaration_id"),
        Index("ix_grace_marks_log_student_course",     "student_id", "course_id"),
        Index("ix_grace_marks_log_subject_result",     "subject_result_id"),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    declaration_id       = Column(UUID(as_uuid=True),
                                  ForeignKey("sis_result_declarations.id", ondelete="RESTRICT"),
                                  nullable=False)
    subject_result_id    = Column(UUID(as_uuid=True),
                                  ForeignKey("sis_subject_results.id", ondelete="RESTRICT"),
                                  nullable=False)
    student_id           = Column(UUID(as_uuid=True), nullable=False)   # plain UUID
    course_id            = Column(UUID(as_uuid=True), nullable=False)   # plain UUID

    grace_marks_applied  = Column(Numeric(6, 2), nullable=False)
    reason               = Column(Text,           nullable=False)   # mandatory Dean rationale

    # Dean gate
    authorized_by        = Column(UUID(as_uuid=True),      nullable=False)
    authorized_at        = Column(DateTime(timezone=True),  nullable=False)

    # Revocation (pre-publish only; never deletes this row)
    revoked_by           = Column(UUID(as_uuid=True),      nullable=True)
    revoked_at           = Column(DateTime(timezone=True),  nullable=True)
    revoke_reason        = Column(Text,                     nullable=True)

    created_at           = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    declaration    = relationship("SisResultDeclaration", back_populates="grace_marks_log")
    subject_result = relationship("SisSubjectResult",     back_populates="grace_log")
