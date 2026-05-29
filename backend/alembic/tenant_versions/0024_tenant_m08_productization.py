"""tenant: M08 productization — workflow split, sections, CO coverage, question bank, internal marks

Revision ID: 0024ten
Revises: 0023ten
Create Date: 2026-05-29

Summary of changes
------------------

exam_papers (ALTER):
  + exam_workflow VARCHAR NOT NULL DEFAULT 'BOARD_EXAM'
      Drives workflow routing: INTERNAL (faculty-only approval gate)
      vs BOARD_EXAM (full 3-gate Board workflow).
  + section_config JSONB NULL
      Optional paper structure: [{label, instruction, total_q, answer_q,
      marks_each, order}]. Enables Part A / Part B / Part C layouts.
  + co_coverage_report JSONB NULL
      Per-CO coverage after generation: [{co_id, co_code, covered, question_count}].
      Advisory only — never blocks workflow.
  + unit_coverage_report JSONB NULL
      Per-unit coverage: [{unit_no, covered, question_count}].
  + scrutinizer_id UUID NULL
      Optional second-faculty review before Board submission (BOARD_EXAM only).
  + scrutinized_at TIMESTAMPTZ NULL
  + scrutinizer_comment TEXT NULL

exam_questions (ALTER):
  + section_label VARCHAR(4) NULL  — e.g. "A", "B", "C"
  + choice_group INT NULL          — groups either/or pairs within a section
  + co_ids JSONB NULL              — array of CO UUIDs from M02 CourseOutcome

blooms_compliance_reports (ALTER):
  + co_coverage_ok BOOLEAN NULL DEFAULT false
  + unit_coverage_ok BOOLEAN NULL DEFAULT false

NEW TABLE: question_bank
  Stores approved questions promoted from BOARD_APPROVED / RELEASED papers.
  Faculty can pull from this bank in future paper generation (Addition 1).
  Human gate: promotion happens at Board approval; never autonomously.

NEW TABLE: internal_marks_summary
  Per-student, per-course, per-semester internal assessment marks.
  Faculty submits → Dean locks (human gate). Board cannot seal a semester
  exam paper until the Dean has locked internal marks for that course
  (enforced at service layer, not here). (Addition 2)

Unchanged invariants
--------------------
* exam_papers.status transitions remain gated by service/router — no change.
* Model answers remain inaccessible when status == SEALED.
* Audit log remains append-only.
* All columns are nullable or have safe server_defaults; no existing rows broken.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0024ten"
down_revision = "0023ten"
branch_labels = None
depends_on    = None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:

    # ------------------------------------------------------------------
    # 1. exam_papers — new columns
    # ------------------------------------------------------------------
    op.add_column(
        "exam_papers",
        sa.Column(
            "exam_workflow",
            sa.String(),
            nullable=False,
            server_default="BOARD_EXAM",
        ),
    )
    op.add_column(
        "exam_papers",
        sa.Column("section_config", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "exam_papers",
        sa.Column("co_coverage_report", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "exam_papers",
        sa.Column("unit_coverage_report", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "exam_papers",
        sa.Column("scrutinizer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "exam_papers",
        sa.Column("scrutinized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "exam_papers",
        sa.Column("scrutinizer_comment", sa.Text(), nullable=True),
    )

    op.create_index("ix_exam_papers_workflow", "exam_papers", ["exam_workflow"])

    # ------------------------------------------------------------------
    # 2. exam_questions — new columns
    # ------------------------------------------------------------------
    op.add_column(
        "exam_questions",
        sa.Column("section_label", sa.String(4), nullable=True),
    )
    op.add_column(
        "exam_questions",
        sa.Column("choice_group", sa.Integer(), nullable=True),
    )
    op.add_column(
        "exam_questions",
        sa.Column("co_ids", postgresql.JSONB(), nullable=True),
    )

    op.create_index("ix_exam_questions_section", "exam_questions", ["section_label"])

    # ------------------------------------------------------------------
    # 3. blooms_compliance_reports — coverage flags
    # ------------------------------------------------------------------
    op.add_column(
        "blooms_compliance_reports",
        sa.Column(
            "co_coverage_ok",
            sa.Boolean(),
            nullable=True,
            server_default="false",
        ),
    )
    op.add_column(
        "blooms_compliance_reports",
        sa.Column(
            "unit_coverage_ok",
            sa.Boolean(),
            nullable=True,
            server_default="false",
        ),
    )

    # ------------------------------------------------------------------
    # 4. question_bank — new table (Addition 1)
    #
    # Stores questions promoted from BOARD_APPROVED or RELEASED papers.
    # source_paper_id SET NULL on delete so the bank survives paper deletion.
    # usage_count incremented each time a question is reused in a new paper.
    # Human gate: is_approved=true set only when Board approves the source paper.
    # ------------------------------------------------------------------
    op.create_table(
        "question_bank",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True),
        # Denormalised course reference (no FK — course lives in M01 schema)
        sa.Column("course_id",       postgresql.UUID(as_uuid=True), nullable=False),
        # Source paper — nullable FK; SET NULL if source paper deleted
        sa.Column(
            "source_paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_papers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("unit_number",     sa.Integer(),                   nullable=False),
        # Array of CO UUIDs from M02 (nullable — older questions may not have CO mapping)
        sa.Column("co_ids",          postgresql.JSONB(),              nullable=True),
        sa.Column("bloom_level",     sa.String(),                    nullable=False),
        sa.Column("question_type",   sa.String(),                    nullable=False),
        sa.Column("question_text",   sa.Text(),                      nullable=False),
        # MCQ options [{label, text}] — nullable for non-MCQ
        sa.Column("options",         postgresql.JSONB(),              nullable=True),
        sa.Column("correct_option",  sa.String(),                    nullable=True),
        sa.Column("marks",           sa.Numeric(5, 1),               nullable=False),
        sa.Column("model_answer",    sa.Text(),                      nullable=True),
        # [{criterion, marks, description}]
        sa.Column("marking_scheme",  postgresql.JSONB(),              nullable=True),
        # Which section this question belongs to in its source paper
        sa.Column("section_label",   sa.String(4),                   nullable=True),
        # Human gate: true only after Board approves the source paper
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        # Incremented each time question is reused in a new paper
        sa.Column("usage_count",     sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("ai_generated",    sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_qbank_course",    "question_bank", ["course_id"])
    op.create_index("ix_qbank_bloom",     "question_bank", ["bloom_level"])
    op.create_index("ix_qbank_type",      "question_bank", ["question_type"])
    op.create_index("ix_qbank_source",    "question_bank", ["source_paper_id"])
    op.create_index("ix_qbank_approved",  "question_bank", ["is_approved"])
    op.create_index("ix_qbank_unit",      "question_bank", ["unit_number"])

    # ------------------------------------------------------------------
    # 5. internal_marks_summary — new table (Addition 2)
    #
    # Per-student, per-course, per-semester internal assessment marks.
    # Workflow: PENDING → FACULTY_SUBMITTED → DEAN_LOCKED
    # Human gates:
    #   submitted_by + submitted_at set by faculty submit endpoint.
    #   locked_by + locked_at set by Dean lock endpoint.
    # Never auto-computed; marks are always entered by faculty.
    # ------------------------------------------------------------------
    op.create_table(
        "internal_marks_summary",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True),
        # Denormalised — no FK constraints across schemas
        sa.Column("student_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester",         sa.Integer(),                   nullable=False),
        # e.g. "2025-26"
        sa.Column("academic_year",    sa.String(10),                  nullable=False),
        # Individual component marks (all nullable — filled incrementally)
        sa.Column("internal1_marks",  sa.Numeric(5, 1), nullable=True),
        sa.Column("internal2_marks",  sa.Numeric(5, 1), nullable=True),
        sa.Column("assignment_marks", sa.Numeric(5, 1), nullable=True),
        sa.Column("attendance_marks", sa.Numeric(5, 1), nullable=True),
        # Computed total; service layer sets this when faculty submits
        sa.Column("total_internal",   sa.Numeric(5, 1), nullable=True),
        # Maximum marks for internal assessment (institution-configurable, default 40)
        sa.Column("max_internal",     sa.Integer(), nullable=False, server_default="40"),
        # Workflow status: PENDING / FACULTY_SUBMITTED / DEAN_LOCKED
        sa.Column("status",           sa.String(),  nullable=False, server_default="PENDING"),
        # Gate 1: faculty submits
        sa.Column("submitted_by",     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at",     sa.DateTime(timezone=True),    nullable=True),
        # Gate 2: Dean locks (marks immutable after lock)
        sa.Column("locked_by",        postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locked_at",        sa.DateTime(timezone=True),    nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_ims_student",   "internal_marks_summary", ["student_id"])
    op.create_index("ix_ims_course",    "internal_marks_summary", ["course_id"])
    op.create_index("ix_ims_status",    "internal_marks_summary", ["status"])
    op.create_index("ix_ims_year_sem",  "internal_marks_summary", ["academic_year", "semester"])

    # One row per student per course per semester per academic year
    op.create_unique_constraint(
        "uq_ims_student_course_year_sem",
        "internal_marks_summary",
        ["student_id", "course_id", "academic_year", "semester"],
    )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop new tables
    op.drop_table("internal_marks_summary")
    op.drop_table("question_bank")

    # blooms_compliance_reports
    op.drop_column("blooms_compliance_reports", "unit_coverage_ok")
    op.drop_column("blooms_compliance_reports", "co_coverage_ok")

    # exam_questions
    op.drop_index("ix_exam_questions_section", table_name="exam_questions")
    op.drop_column("exam_questions", "co_ids")
    op.drop_column("exam_questions", "choice_group")
    op.drop_column("exam_questions", "section_label")

    # exam_papers
    op.drop_index("ix_exam_papers_workflow", table_name="exam_papers")
    op.drop_column("exam_papers", "scrutinizer_comment")
    op.drop_column("exam_papers", "scrutinized_at")
    op.drop_column("exam_papers", "scrutinizer_id")
    op.drop_column("exam_papers", "unit_coverage_report")
    op.drop_column("exam_papers", "co_coverage_report")
    op.drop_column("exam_papers", "section_config")
    op.drop_column("exam_papers", "exam_workflow")
