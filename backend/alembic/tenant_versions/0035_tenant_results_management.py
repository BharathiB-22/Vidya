"""0035 – H60: Results Management

New tables (7):
  sis_grading_policies       — configurable grade band definition per tenant/program
  sis_grading_policy_bands   — one row per grade letter per policy
  sis_result_declarations    — one per exam session; drives result lifecycle
  sis_external_marks         — university/external exam marks entry
  sis_subject_results        — computed per-student per-course result
  sis_semester_results       — SGPA / CGPA / ranks per student per declaration
  sis_grace_marks_log        — append-only Dean-authorised grace mark audit trail

Result declaration lifecycle:
  DRAFT → VERIFIED → PUBLISHED → LOCKED

Snapshot fields on sis_result_declarations preserve historical grade card accuracy
even when semester labels or grading policy names are later renamed.

sis_semester_results.overall_result_status supports graduation audits and
degree eligibility flows (PASS / FAIL / WITHHELD / PROVISIONAL).

Future-proof via declaration_type + source_declaration_id + attempt_number
for SUPPLEMENTARY, REVALUATION, and IMPROVEMENT exam chains.

No changes to existing tables.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0035ten"
down_revision = "0034ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── sis_grading_policies ──────────────────────────────────────────────────
    op.create_table(
        "sis_grading_policies",
        sa.Column("id",              postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name",            sa.String(100), nullable=False),
        sa.Column("program_id",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pass_percentage", sa.Numeric(5, 2), nullable=False,
                  server_default=sa.text("40.0")),
        sa.Column("is_default",      sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("is_active",       sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_by",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",      sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grading_policies_is_default", "sis_grading_policies",
                    ["is_default", "is_active"])
    op.create_index("ix_grading_policies_program_id", "sis_grading_policies", ["program_id"])

    # ── sis_grading_policy_bands ──────────────────────────────────────────────
    op.create_table(
        "sis_grading_policy_bands",
        sa.Column("id",             postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("policy_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grade_letter",   sa.String(5),     nullable=False),
        sa.Column("min_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("max_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("grade_point",    sa.Numeric(4, 2), nullable=False),
        sa.Column("is_pass",        sa.Boolean,       nullable=False,
                  server_default=sa.text("true")),
        sa.Column("display_order",  sa.SmallInteger,  nullable=True),
        sa.Column("created_at",     sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["policy_id"], ["sis_grading_policies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("policy_id", "grade_letter", name="uq_grading_bands_policy_letter"),
    )
    op.create_index("ix_grading_bands_policy_id", "sis_grading_policy_bands", ["policy_id"])

    # ── sis_result_declarations ───────────────────────────────────────────────
    op.create_table(
        "sis_result_declarations",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("exam_session_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester_id",          postgresql.UUID(as_uuid=True), nullable=False),
        # Snapshot columns
        sa.Column("snapshot_academic_year",       sa.String(20),  nullable=False,
                  server_default=sa.text("''")),
        sa.Column("snapshot_semester_name",       sa.String(100), nullable=False,
                  server_default=sa.text("''")),
        sa.Column("snapshot_grading_policy_name", sa.String(100), nullable=False,
                  server_default=sa.text("''")),
        # Classification
        sa.Column("declaration_type",     sa.String(20),  nullable=False,
                  server_default=sa.text("'REGULAR'")),
        sa.Column("source_declaration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("grading_policy_id",    postgresql.UUID(as_uuid=True), nullable=False),
        # Metadata
        sa.Column("title",                sa.String(200), nullable=True),
        sa.Column("notes",                sa.Text,        nullable=True),
        sa.Column("internal_marks_required", sa.Boolean,  nullable=False,
                  server_default=sa.text("true")),
        # Lifecycle
        sa.Column("status",               sa.String(15),  nullable=False,
                  server_default=sa.text("'DRAFT'")),
        # Human gates
        sa.Column("verified_by",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at",          sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("published_by",         postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at",         sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("locked_by",            postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locked_at",            sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("created_by",           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",           sa.TIMESTAMP(timezone=True),   nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["exam_session_id"],  ["sis_exam_sessions.id"],      ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["semester_id"],       ["acad_semesters.id"],         ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["grading_policy_id"], ["sis_grading_policies.id"],   ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_declaration_id"], ["sis_result_declarations.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "exam_session_id", "declaration_type",
            name="uq_result_declarations_session_type",
        ),
    )
    op.create_index("ix_result_declarations_semester_status",
                    "sis_result_declarations", ["semester_id", "status"])
    op.create_index("ix_result_declarations_status",
                    "sis_result_declarations", ["status"])
    op.create_index("ix_result_declarations_type",
                    "sis_result_declarations", ["declaration_type"])
    op.create_index("ix_result_declarations_exam_session",
                    "sis_result_declarations", ["exam_session_id"])

    # ── sis_external_marks ────────────────────────────────────────────────────
    op.create_table(
        "sis_external_marks",
        sa.Column("id",                      postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("declaration_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id",              postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id",               postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id",              postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_marks_obtained", sa.Numeric(6, 2), nullable=True),
        sa.Column("external_marks_max",      sa.Numeric(6, 2), nullable=False),
        sa.Column("is_absent",               sa.Boolean,       nullable=False,
                  server_default=sa.text("false")),
        sa.Column("attempt_number",          sa.SmallInteger,  nullable=False,
                  server_default=sa.text("1")),
        sa.Column("entered_by",              postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entered_at",              sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("edited_by",               postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("edited_at",               sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("edit_reason",             sa.Text,                       nullable=True),
        sa.Column("created_at",              sa.TIMESTAMP(timezone=True),   nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",              sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["declaration_id"], ["sis_result_declarations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_id"],      ["courses.id"],                 ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["section_id"],     ["acad_sections.id"],           ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "declaration_id", "student_id", "course_id",
            name="uq_external_marks_declaration_student_course",
        ),
    )
    op.create_index("ix_external_marks_declaration_section",
                    "sis_external_marks", ["declaration_id", "section_id"])
    op.create_index("ix_external_marks_student",
                    "sis_external_marks", ["student_id"])
    op.create_index("ix_external_marks_declaration_id",
                    "sis_external_marks", ["declaration_id"])

    # ── sis_subject_results ───────────────────────────────────────────────────
    op.create_table(
        "sis_subject_results",
        sa.Column("id",               postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("declaration_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("internal_marks",   sa.Numeric(6, 2), nullable=True),
        sa.Column("external_marks",   sa.Numeric(6, 2), nullable=True),
        sa.Column("grace_marks",      sa.Numeric(6, 2), nullable=True),
        sa.Column("total_marks",      sa.Numeric(6, 2), nullable=True),
        sa.Column("max_marks",        sa.Numeric(6, 2), nullable=False),
        sa.Column("percentage",       sa.Numeric(5, 2), nullable=True),
        sa.Column("grade_letter",     sa.String(5),     nullable=True),
        sa.Column("grade_point",      sa.Numeric(4, 2), nullable=True),
        sa.Column("is_pass",          sa.Boolean,       nullable=True),
        sa.Column("result_status",    sa.String(10),    nullable=False,
                  server_default=sa.text("'PENDING'")),
        sa.Column("credits_attempted", sa.Numeric(4, 2), nullable=True),
        sa.Column("credits_earned",    sa.Numeric(4, 2), nullable=True),
        sa.Column("attempt_number",   sa.SmallInteger,  nullable=False,
                  server_default=sa.text("1")),
        sa.Column("computed_at",      sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",       sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",       sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["declaration_id"], ["sis_result_declarations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_id"],      ["courses.id"],                 ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["section_id"],     ["acad_sections.id"],           ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["semester_id"],    ["acad_semesters.id"],          ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "declaration_id", "student_id", "course_id",
            name="uq_subject_results_declaration_student_course",
        ),
    )
    op.create_index("ix_subject_results_student_semester",
                    "sis_subject_results", ["student_id", "semester_id"])
    op.create_index("ix_subject_results_declaration_status",
                    "sis_subject_results", ["declaration_id", "result_status"])
    op.create_index("ix_subject_results_declaration_section",
                    "sis_subject_results", ["declaration_id", "section_id"])
    op.create_index("ix_subject_results_student",
                    "sis_subject_results", ["student_id"])

    # ── sis_semester_results ──────────────────────────────────────────────────
    op.create_table(
        "sis_semester_results",
        sa.Column("id",                      postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("declaration_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id",              postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester_id",             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sgpa",                    sa.Numeric(4, 2), nullable=True),
        sa.Column("cgpa",                    sa.Numeric(4, 2), nullable=True),
        sa.Column("total_credits_attempted", sa.Numeric(6, 2), nullable=True),
        sa.Column("total_credits_earned",    sa.Numeric(6, 2), nullable=True),
        sa.Column("overall_result_status",   sa.String(15),    nullable=True),
        sa.Column("section_rank",            sa.Integer,       nullable=True),
        sa.Column("program_rank",            sa.Integer,       nullable=True),
        sa.Column("computed_at",             sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",              sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",              sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["declaration_id"], ["sis_result_declarations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["semester_id"],    ["acad_semesters.id"],          ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "declaration_id", "student_id",
            name="uq_semester_results_declaration_student",
        ),
    )
    op.create_index("ix_semester_results_student",
                    "sis_semester_results", ["student_id"])
    op.create_index("ix_semester_results_declaration_sgpa",
                    "sis_semester_results", ["declaration_id", "sgpa"])
    op.create_index("ix_semester_results_semester",
                    "sis_semester_results", ["semester_id"])

    # ── sis_grace_marks_log ───────────────────────────────────────────────────
    op.create_table(
        "sis_grace_marks_log",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("declaration_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_result_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id",           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grace_marks_applied", sa.Numeric(6, 2), nullable=False),
        sa.Column("reason",              sa.Text,           nullable=False),
        sa.Column("authorized_by",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authorized_at",       sa.TIMESTAMP(timezone=True),   nullable=False),
        sa.Column("revoked_by",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at",          sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("revoke_reason",       sa.Text,                       nullable=True),
        sa.Column("created_at",          sa.TIMESTAMP(timezone=True),   nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["declaration_id"],    ["sis_result_declarations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["subject_result_id"], ["sis_subject_results.id"],     ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_grace_marks_log_declaration",
                    "sis_grace_marks_log", ["declaration_id"])
    op.create_index("ix_grace_marks_log_student_course",
                    "sis_grace_marks_log", ["student_id", "course_id"])
    op.create_index("ix_grace_marks_log_subject_result",
                    "sis_grace_marks_log", ["subject_result_id"])

    # ── Seed default grading policy (10-point scale) ─────────────────────────
    op.execute(
        """
        DO $$
        DECLARE
            pol_id UUID;
        BEGIN
            INSERT INTO sis_grading_policies
                (id, name, pass_percentage, is_default, is_active,
                 created_by, created_at)
            VALUES
                (gen_random_uuid(), 'Default 10-Point Scale', 40.0,
                 true, true, '00000000-0000-0000-0000-000000000000', now())
            ON CONFLICT DO NOTHING
            RETURNING id INTO pol_id;

            IF pol_id IS NOT NULL THEN
                INSERT INTO sis_grading_policy_bands
                    (id, policy_id, grade_letter, min_percentage, max_percentage,
                     grade_point, is_pass, display_order, created_at)
                VALUES
                    (gen_random_uuid(), pol_id, 'O',  90, 100, 10.0, true,  1, now()),
                    (gen_random_uuid(), pol_id, 'A+', 80,  89, 9.0,  true,  2, now()),
                    (gen_random_uuid(), pol_id, 'A',  70,  79, 8.0,  true,  3, now()),
                    (gen_random_uuid(), pol_id, 'B+', 60,  69, 7.0,  true,  4, now()),
                    (gen_random_uuid(), pol_id, 'B',  55,  59, 6.0,  true,  5, now()),
                    (gen_random_uuid(), pol_id, 'C',  50,  54, 5.0,  true,  6, now()),
                    (gen_random_uuid(), pol_id, 'P',  40,  49, 4.0,  true,  7, now()),
                    (gen_random_uuid(), pol_id, 'F',   0,  39, 0.0,  false, 8, now());
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("sis_grace_marks_log")
    op.drop_table("sis_semester_results")
    op.drop_table("sis_subject_results")
    op.drop_table("sis_external_marks")
    op.drop_table("sis_result_declarations")
    op.drop_table("sis_grading_policy_bands")
    op.drop_table("sis_grading_policies")
