"""M09.5 Digital Exams Phase 1 — digital_exam_sessions, digital_exam_attempts, digital_exam_responses.

Students take exams online; MCQ responses are auto-scored on submit.
Subjective responses are stored for evaluator review in Phase 2.

Revision ID: 0045ten
Revises: 0044ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0045ten"
down_revision = "0044ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # digital_exam_sessions
    op.create_table(
        "digital_exam_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("exam_paper_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title",             sa.String(),                   nullable=False),
        sa.Column("status",            sa.String(20),                 nullable=False, server_default="DRAFT"),
        sa.Column("window_start",      sa.DateTime(timezone=True),    nullable=True),
        sa.Column("window_end",        sa.DateTime(timezone=True),    nullable=True),
        sa.Column("max_duration_mins", sa.Integer(),                  nullable=False, server_default="180"),
        sa.Column("instructions",      sa.Text(),                     nullable=True),
        sa.Column("activated_at",      sa.DateTime(timezone=True),    nullable=True),
        sa.Column("closed_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",        sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_digital_sessions_paper",   "digital_exam_sessions", ["exam_paper_id"])
    op.create_index("ix_digital_sessions_status",  "digital_exam_sessions", ["status"])
    op.create_index("ix_digital_sessions_created", "digital_exam_sessions", ["created_at"])

    # digital_exam_attempts
    op.create_table(
        "digital_exam_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("digital_exam_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("student_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status",          sa.String(20),                 nullable=False, server_default="IN_PROGRESS"),
        sa.Column("started_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at",      sa.DateTime(timezone=True),    nullable=True),
        sa.Column("submitted_at",    sa.DateTime(timezone=True),    nullable=True),
        sa.Column("auto_scored_at",  sa.DateTime(timezone=True),    nullable=True),
        sa.Column("auto_score",      sa.Numeric(6, 2),              nullable=True),
        sa.Column("mcq_max_score",   sa.Numeric(6, 2),              nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_digital_attempt_session_student",
        "digital_exam_attempts",
        ["session_id", "student_user_id"],
    )
    op.create_index("ix_digital_attempts_session",   "digital_exam_attempts", ["session_id"])
    op.create_index("ix_digital_attempts_student",   "digital_exam_attempts", ["student_user_id"])
    op.create_index("ix_digital_attempts_status",    "digital_exam_attempts", ["status"])
    op.create_index("ix_digital_attempts_submitted", "digital_exam_attempts", ["submitted_at"])

    # digital_exam_responses
    op.create_table(
        "digital_exam_responses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("digital_exam_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_type",   sa.String(30),                 nullable=True),
        sa.Column("selected_option", sa.String(4),                  nullable=True),
        sa.Column("response_text",   sa.Text(),                     nullable=True),
        sa.Column("is_auto_scored",  sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("auto_score",      sa.Numeric(6, 2),              nullable=True),
        sa.Column("is_correct",      sa.Boolean(),                  nullable=True),
        sa.Column("answered_at",     sa.DateTime(timezone=True),    nullable=True),
        sa.Column("updated_at",      sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_digital_response_attempt_question",
        "digital_exam_responses",
        ["attempt_id", "question_id"],
    )
    op.create_index("ix_digital_responses_attempt",  "digital_exam_responses", ["attempt_id"])
    op.create_index("ix_digital_responses_question", "digital_exam_responses", ["question_id"])


def downgrade() -> None:
    op.drop_table("digital_exam_responses")
    op.drop_table("digital_exam_attempts")
    op.drop_table("digital_exam_sessions")
