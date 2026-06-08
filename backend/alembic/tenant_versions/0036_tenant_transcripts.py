"""0036 – H61: Transcript Generation

New tables (4):
  sis_transcripts                  — one record per issued transcript (with version chain)
  sis_transcript_semester_lines    — frozen semester snapshot per transcript
  sis_transcript_subject_lines     — frozen subject snapshot per transcript
  sis_transcript_verification_log  — append-only QR scan audit log

Sequence (1):
  sis_transcript_seq  — per-tenant sequential number for transcript_number

Column added (1):
  acad_programs.min_credits_for_degree — degree eligibility threshold

Transcript lifecycle:
  REQUESTED → GENERATED → ISSUED → SUPERSEDED | REVOKED | STALE

Degree status values: ELIGIBLE / NOT_ELIGIBLE / PROVISIONAL / GRADUATED

All snapshot columns are frozen at generation time; underlying result
changes do NOT silently change an issued transcript.

sis_transcript_verification_log is append-only — no UPDATE or DELETE.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0036ten"
down_revision = "0035ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── Sequence for human-readable transcript numbers ────────────────────────
    op.execute("CREATE SEQUENCE IF NOT EXISTS sis_transcript_seq START 1 INCREMENT 1")

    # ── sis_transcripts ───────────────────────────────────────────────────────
    op.create_table(
        "sis_transcripts",
        sa.Column("id",              postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        # Student context
        sa.Column("student_id",                postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usn_snapshot",              sa.String(30),   nullable=True),
        sa.Column("student_name_snapshot",     sa.String(200),  nullable=False),
        # Academic context (frozen at generation)
        sa.Column("program_id",                postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("program_name_snapshot",     sa.String(200),  nullable=True),
        sa.Column("department_name_snapshot",  sa.String(200),  nullable=True),
        sa.Column("school_name_snapshot",      sa.String(200),  nullable=True),
        sa.Column("batch_name_snapshot",       sa.String(100),  nullable=True),
        sa.Column("degree_title_snapshot",     sa.String(200),  nullable=True),
        # Identity
        sa.Column("transcript_number",         sa.String(50),   nullable=True),
        sa.Column("verification_code",         postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transcript_type",           sa.String(20),   nullable=False,
                  server_default=sa.text("'OFFICIAL'")),
        sa.Column("purpose",                   sa.Text,         nullable=True),
        # Computed snapshot fields
        sa.Column("overall_cgpa_snapshot",             sa.Numeric(4, 2), nullable=True),
        sa.Column("total_credits_attempted_snapshot",  sa.Numeric(6, 2), nullable=True),
        sa.Column("total_credits_earned_snapshot",     sa.Numeric(6, 2), nullable=True),
        sa.Column("arrear_count_snapshot",             sa.SmallInteger,  nullable=True),
        sa.Column("degree_status_snapshot",            sa.String(20),    nullable=True),
        sa.Column("semesters_included",                sa.SmallInteger,  nullable=True),
        # Lifecycle
        sa.Column("status",        sa.String(15), nullable=False,
                  server_default=sa.text("'REQUESTED'")),
        sa.Column("version",       sa.SmallInteger, nullable=False,
                  server_default=sa.text("1")),
        sa.Column("parent_transcript_id", postgresql.UUID(as_uuid=True), nullable=True),
        # PDF storage
        sa.Column("pdf_s3_key",        sa.String(500), nullable=True),
        sa.Column("pdf_generated_at",  sa.TIMESTAMP(timezone=True), nullable=True),
        # Human actor timestamps
        sa.Column("requested_by",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_at",  sa.TIMESTAMP(timezone=True),   nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("generated_by",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at",  sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("issued_by",     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_at",     sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("revoked_by",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at",    sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("revoke_reason", sa.Text, nullable=True),
        sa.Column("created_at",    sa.TIMESTAMP(timezone=True),   nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["parent_transcript_id"], ["sis_transcripts.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("transcript_number", name="uq_transcripts_transcript_number"),
        sa.UniqueConstraint("verification_code",  name="uq_transcripts_verification_code"),
    )
    op.create_index("ix_transcripts_student_status",
                    "sis_transcripts", ["student_id", "status"])
    op.create_index("ix_transcripts_verification_code",
                    "sis_transcripts", ["verification_code"])
    op.create_index("ix_transcripts_status",
                    "sis_transcripts", ["status"])
    op.create_index("ix_transcripts_student_id",
                    "sis_transcripts", ["student_id"])

    # ── sis_transcript_semester_lines ─────────────────────────────────────────
    op.create_table(
        "sis_transcript_semester_lines",
        sa.Column("id",              postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("transcript_id",   postgresql.UUID(as_uuid=True), nullable=False),
        # Reference fields (not enforced FKs — snapshot is independent)
        sa.Column("semester_id",     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("declaration_id",  postgresql.UUID(as_uuid=True), nullable=True),
        # Frozen snapshot
        sa.Column("semester_number_snapshot",      sa.SmallInteger, nullable=True),
        sa.Column("semester_name_snapshot",        sa.String(100),  nullable=True),
        sa.Column("academic_year_snapshot",        sa.String(20),   nullable=True),
        sa.Column("sgpa_snapshot",                 sa.Numeric(4, 2), nullable=True),
        sa.Column("cgpa_snapshot",                 sa.Numeric(4, 2), nullable=True),
        sa.Column("credits_attempted_snapshot",    sa.Numeric(6, 2), nullable=True),
        sa.Column("credits_earned_snapshot",       sa.Numeric(6, 2), nullable=True),
        sa.Column("overall_result_status_snapshot", sa.String(15),   nullable=True),
        sa.Column("display_order",  sa.SmallInteger, nullable=False),
        sa.Column("created_at",     sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["transcript_id"], ["sis_transcripts.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_transcript_semester_lines_transcript_id",
                    "sis_transcript_semester_lines", ["transcript_id"])

    # ── sis_transcript_subject_lines ──────────────────────────────────────────
    op.create_table(
        "sis_transcript_subject_lines",
        sa.Column("id",               postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("transcript_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Reference
        sa.Column("course_id",        postgresql.UUID(as_uuid=True), nullable=True),
        # Frozen snapshot
        sa.Column("course_code_snapshot",    sa.String(20),  nullable=True),
        sa.Column("course_name_snapshot",    sa.String(200), nullable=True),
        sa.Column("course_credits_snapshot", sa.Numeric(4, 2), nullable=True),
        sa.Column("internal_marks_snapshot", sa.Numeric(6, 2), nullable=True),
        sa.Column("external_marks_snapshot", sa.Numeric(6, 2), nullable=True),
        sa.Column("grace_marks_snapshot",    sa.Numeric(6, 2), nullable=True),
        sa.Column("total_marks_snapshot",    sa.Numeric(6, 2), nullable=True),
        sa.Column("max_marks_snapshot",      sa.Numeric(6, 2), nullable=True),
        sa.Column("percentage_snapshot",     sa.Numeric(5, 2), nullable=True),
        sa.Column("grade_letter_snapshot",   sa.String(5),     nullable=True),
        sa.Column("grade_point_snapshot",    sa.Numeric(4, 2), nullable=True),
        sa.Column("is_pass_snapshot",        sa.Boolean,       nullable=True),
        sa.Column("result_status_snapshot",  sa.String(10),    nullable=True),
        sa.Column("attempt_number",          sa.SmallInteger,  nullable=False,
                  server_default=sa.text("1")),
        sa.Column("declaration_type_snapshot", sa.String(20),  nullable=True),
        sa.Column("is_best_attempt",         sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("display_order",           sa.SmallInteger, nullable=False),
        sa.Column("created_at",              sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["transcript_id"],    ["sis_transcripts.id"],              ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["semester_line_id"], ["sis_transcript_semester_lines.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_transcript_subject_lines_transcript_id",
                    "sis_transcript_subject_lines", ["transcript_id"])
    op.create_index("ix_transcript_subject_lines_semester_line",
                    "sis_transcript_subject_lines", ["semester_line_id"])
    op.create_index("ix_transcript_subject_lines_best",
                    "sis_transcript_subject_lines", ["transcript_id", "is_best_attempt"])

    # ── sis_transcript_verification_log  (append-only) ───────────────────────
    op.create_table(
        "sis_transcript_verification_log",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("transcript_id",       postgresql.UUID(as_uuid=True), nullable=True),
        # Denormalised code so logs survive even if transcript is removed
        sa.Column("verification_code",   sa.String(50),  nullable=False),
        sa.Column("verified_at",         sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("requester_ip_hash",   sa.String(64),  nullable=True),
        sa.Column("requester_context",   sa.String(100), nullable=True),
        sa.Column("verification_result", sa.String(15),  nullable=False),
        sa.Column("created_at",          sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["transcript_id"], ["sis_transcripts.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_verification_log_transcript_id",
                    "sis_transcript_verification_log", ["transcript_id"])
    op.create_index("ix_verification_log_code",
                    "sis_transcript_verification_log", ["verification_code"])
    op.create_index("ix_verification_log_verified_at",
                    "sis_transcript_verification_log", ["verified_at"])

    # ── acad_programs.min_credits_for_degree ─────────────────────────────────
    op.add_column(
        "acad_programs",
        sa.Column("min_credits_for_degree", sa.Numeric(6, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("acad_programs", "min_credits_for_degree")
    op.drop_table("sis_transcript_verification_log")
    op.drop_table("sis_transcript_subject_lines")
    op.drop_table("sis_transcript_semester_lines")
    op.drop_table("sis_transcripts")
    op.execute("DROP SEQUENCE IF EXISTS sis_transcript_seq")
