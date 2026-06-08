"""0037 – H62: Graduation Audit

New tables (4):
  sis_graduation_audits        — one per batch audit run
  sis_graduation_candidates    — per-student eligibility + board decision per audit
  sis_graduation_overrides     — append-only Dean override log (no UPDATE/DELETE)
  sis_graduation_certificates  — issued graduation certificate

Sequence (1):
  sis_graduation_cert_seq  — per-tenant certificate number counter

Certificate numbering:
  CERT/{TENANT_CODE}/{YEAR}/{SEQ:06d}

Human gates:
  Gate 1: Dean submits → SUBMITTED
  Gate 2a: Board ratifies/defers per candidate
  Gate 2b: Board approves batch (board_resolution_ref mandatory)
  Gate 3: Registrar issues certificate

sis_graduation_overrides is append-only — no UPDATE or DELETE ever.
No automatic graduation. AI advises, humans decide.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0037ten"
down_revision = "0036ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── Sequence for human-readable certificate numbers ───────────────────────
    op.execute("CREATE SEQUENCE IF NOT EXISTS sis_graduation_cert_seq START 1 INCREMENT 1")

    # ── sis_graduation_audits ─────────────────────────────────────────────────
    op.create_table(
        "sis_graduation_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        # Batch / program context
        sa.Column("batch_id",               postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_name_snapshot",    sa.String(100), nullable=True),
        sa.Column("program_id",             postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("program_name_snapshot",  sa.String(200), nullable=True),
        sa.Column("academic_year_snapshot", sa.String(20),  nullable=True),
        # Lifecycle
        sa.Column("status", sa.String(25), nullable=False, server_default=sa.text("'DRAFT'")),
        # Gate timestamps
        sa.Column("triggered_by",           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_at",           sa.TIMESTAMP(timezone=True),   nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("submitted_by",           postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at",           sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("board_approved_by",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("board_approved_at",      sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("board_resolution_ref",   sa.String(200),                nullable=True),
        sa.Column("certificates_issued_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("certificates_issued_at", sa.TIMESTAMP(timezone=True),   nullable=True),
        # Summary counters
        sa.Column("total_candidates",    sa.SmallInteger, nullable=True),
        sa.Column("eligible_count",      sa.SmallInteger, nullable=True),
        sa.Column("provisional_count",   sa.SmallInteger, nullable=True),
        sa.Column("not_eligible_count",  sa.SmallInteger, nullable=True),
        sa.Column("ratified_count",      sa.SmallInteger, nullable=True),
        sa.Column("deferred_count",      sa.SmallInteger, nullable=True),
        sa.Column("notes",      sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graduation_audits_batch_id",   "sis_graduation_audits", ["batch_id"])
    op.create_index("ix_graduation_audits_status",     "sis_graduation_audits", ["status"])
    op.create_index("ix_graduation_audits_program_id", "sis_graduation_audits", ["program_id"])

    # ── sis_graduation_candidates ─────────────────────────────────────────────
    op.create_table(
        "sis_graduation_candidates",
        sa.Column("id",         postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Student snapshot
        sa.Column("usn_snapshot",          sa.String(30),  nullable=True),
        sa.Column("student_name_snapshot", sa.String(200), nullable=False),
        sa.Column("program_name_snapshot", sa.String(200), nullable=True),
        # Eligibility flags (advisory)
        sa.Column("missing_declarations",        sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("has_arrears",                 sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("credits_shortfall",           sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("has_withheld",                sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("final_sem_not_locked",        sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("graduation_year_not_reached", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("attendance_below_threshold",  sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("disciplinary_hold",           sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        # Computed snapshot values
        sa.Column("total_credits_earned", sa.Numeric(6, 2), nullable=True),
        sa.Column("min_credits_required", sa.Numeric(6, 2), nullable=True),
        sa.Column("current_cgpa",         sa.Numeric(4, 2), nullable=True),
        sa.Column("arrear_count",         sa.SmallInteger,  nullable=True),
        sa.Column("semesters_declared",   sa.SmallInteger,  nullable=True),
        # Eligibility outcome
        sa.Column("eligibility_status", sa.String(20), nullable=False,
                  server_default=sa.text("'NOT_ELIGIBLE'")),
        sa.Column("override_reason",    sa.Text, nullable=True),
        sa.Column("overridden_by",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("overridden_at",      sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("provisional_grace_deadline", sa.Date, nullable=True),
        # Board decision
        sa.Column("board_status",     sa.String(20), nullable=False,
                  server_default=sa.text("'PENDING'")),
        sa.Column("board_decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("board_decided_at", sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("board_notes",      sa.Text, nullable=True),
        # Certificate
        sa.Column("certificate_status", sa.String(20), nullable=False,
                  server_default=sa.text("'NOT_ISSUED'")),
        sa.Column("certificate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id", "student_id",
                            name="uq_graduation_candidates_audit_student"),
        sa.ForeignKeyConstraint(["audit_id"], ["sis_graduation_audits.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_graduation_candidates_audit_id",
                    "sis_graduation_candidates", ["audit_id"])
    op.create_index("ix_graduation_candidates_student_id",
                    "sis_graduation_candidates", ["student_id"])
    op.create_index("ix_graduation_candidates_eligibility_status",
                    "sis_graduation_candidates", ["eligibility_status"])
    op.create_index("ix_graduation_candidates_board_status",
                    "sis_graduation_candidates", ["board_status"])

    # ── sis_graduation_overrides  (append-only) ───────────────────────────────
    op.create_table(
        "sis_graduation_overrides",
        sa.Column("id",           postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role",    sa.String(30), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=False),
        sa.Column("new_status",       sa.String(20), nullable=False),
        sa.Column("reason",           sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        # No updated_at — append-only invariant
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["candidate_id"], ["sis_graduation_candidates.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_graduation_overrides_candidate_id",
                    "sis_graduation_overrides", ["candidate_id"])
    op.create_index("ix_graduation_overrides_actor_id",
                    "sis_graduation_overrides", ["actor_user_id"])

    # ── sis_graduation_certificates ───────────────────────────────────────────
    op.create_table(
        "sis_graduation_certificates",
        sa.Column("id",           postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id",   postgresql.UUID(as_uuid=True), nullable=False),
        # Student snapshot
        sa.Column("usn_snapshot",          sa.String(30),  nullable=True),
        sa.Column("student_name_snapshot", sa.String(200), nullable=False),
        sa.Column("program_name_snapshot", sa.String(200), nullable=True),
        sa.Column("degree_title_snapshot", sa.String(200), nullable=True),
        sa.Column("school_name_snapshot",  sa.String(200), nullable=True),
        sa.Column("batch_name_snapshot",   sa.String(100), nullable=True),
        sa.Column("graduation_year",       sa.SmallInteger, nullable=False),
        sa.Column("overall_cgpa_snapshot", sa.Numeric(4, 2), nullable=True),
        sa.Column("total_credits_earned",  sa.Numeric(6, 2), nullable=True),
        # Identity
        sa.Column("certificate_number", sa.String(50), nullable=True),
        sa.Column("is_provisional",     sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        # Provisional confirmation
        sa.Column("provisional_confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("provisional_confirmed_by", postgresql.UUID(as_uuid=True), nullable=True),
        # Lifecycle
        sa.Column("status",     sa.String(20), nullable=False,
                  server_default=sa.text("'ISSUED'")),
        sa.Column("issued_by",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at",  sa.TIMESTAMP(timezone=True),   nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("revoked_by",     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at",     sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("revoke_reason",  sa.Text, nullable=True),
        # PDF
        sa.Column("pdf_s3_key",       sa.String(500), nullable=True),
        sa.Column("pdf_generated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("certificate_number",
                            name="uq_graduation_certificates_number"),
        sa.ForeignKeyConstraint(["audit_id"], ["sis_graduation_audits.id"],
                                ondelete="RESTRICT"),
    )
    op.create_index("ix_graduation_certificates_student_id",
                    "sis_graduation_certificates", ["student_id"])
    op.create_index("ix_graduation_certificates_audit_id",
                    "sis_graduation_certificates", ["audit_id"])
    op.create_index("ix_graduation_certificates_status",
                    "sis_graduation_certificates", ["status"])


def downgrade() -> None:
    op.drop_table("sis_graduation_certificates")
    op.drop_table("sis_graduation_overrides")
    op.drop_table("sis_graduation_candidates")
    op.drop_table("sis_graduation_audits")
    op.execute("DROP SEQUENCE IF EXISTS sis_graduation_cert_seq")
