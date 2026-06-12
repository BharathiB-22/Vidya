"""M09.9 Compliance & Audit — exam_mark_audit append-only ledger.

Creates the tenant-schema ``exam_mark_audit`` table: an immutable, field-level
record of every examination mark mutation (previous → new value, who, when, why).

Immutability is enforced in the database with the same defence-in-depth pattern
already applied to public.audit_logs (see public migration 0005pub): BEFORE
UPDATE / DELETE / TRUNCATE triggers raise an exception.  The only permitted
write is INSERT.  Each tenant schema gets its own trigger function + triggers
because this migration runs once per tenant schema.

Revision ID: 0048ten
Revises: 0047ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0048ten"
down_revision = "0047ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "exam_mark_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("script_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exam_paper_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_round", sa.String(20),                 nullable=True),
        sa.Column("student_user_id",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("masked_id",        sa.String(),                   nullable=True),
        sa.Column("change_type",      sa.String(30),                 nullable=False),
        sa.Column("previous_marks",   sa.Numeric(6, 2),              nullable=True),
        sa.Column("new_marks",        sa.Numeric(6, 2),              nullable=True),
        sa.Column("max_marks",        sa.Numeric(6, 2),              nullable=True),
        sa.Column("delta",            sa.Numeric(6, 2),              nullable=True),
        sa.Column("actor_user_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role",       sa.String(30),                 nullable=True),
        sa.Column("reason",           sa.Text(),                     nullable=True),
        sa.Column("source_event",     sa.String(60),                 nullable=True),
        sa.Column("metadata",         postgresql.JSONB(),            nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True),    nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_exam_mark_audit_script",     "exam_mark_audit", ["script_id"])
    op.create_index("ix_exam_mark_audit_question",   "exam_mark_audit", ["question_id"])
    op.create_index("ix_exam_mark_audit_exam_paper", "exam_mark_audit", ["exam_paper_id"])
    op.create_index("ix_exam_mark_audit_actor",      "exam_mark_audit", ["actor_user_id"])
    op.create_index("ix_exam_mark_audit_student",    "exam_mark_audit", ["student_user_id"])
    op.create_index("ix_exam_mark_audit_type",       "exam_mark_audit", ["change_type"])
    op.create_index("ix_exam_mark_audit_created",    "exam_mark_audit", ["created_at"])

    # Append-only enforcement (created in the current tenant schema via search_path).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION exam_mark_audit_no_mutate()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'exam_mark_audit is append-only: % operations are not permitted. '
                'Examination mark-change history must be preserved for compliance.',
                TG_OP;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER exam_mark_audit_block_update
            BEFORE UPDATE ON exam_mark_audit
            FOR EACH ROW EXECUTE FUNCTION exam_mark_audit_no_mutate();
        """
    )
    op.execute(
        """
        CREATE TRIGGER exam_mark_audit_block_delete
            BEFORE DELETE ON exam_mark_audit
            FOR EACH ROW EXECUTE FUNCTION exam_mark_audit_no_mutate();
        """
    )
    op.execute(
        """
        CREATE TRIGGER exam_mark_audit_block_truncate
            BEFORE TRUNCATE ON exam_mark_audit
            FOR EACH STATEMENT EXECUTE FUNCTION exam_mark_audit_no_mutate();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS exam_mark_audit_block_truncate ON exam_mark_audit;")
    op.execute("DROP TRIGGER IF EXISTS exam_mark_audit_block_delete   ON exam_mark_audit;")
    op.execute("DROP TRIGGER IF EXISTS exam_mark_audit_block_update   ON exam_mark_audit;")
    op.execute("DROP FUNCTION IF EXISTS exam_mark_audit_no_mutate();")
    op.drop_table("exam_mark_audit")
