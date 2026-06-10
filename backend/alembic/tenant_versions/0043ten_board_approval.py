"""M09.4 Board Approval — exam_board_sessions + exam_board_course_approvals tables.

Adds Examination Board results-approval workflow tables.
One session per paper per decision cycle; one stats snapshot per session.

Human-gate invariants are enforced in the service layer, not DDL:
  - approve: session.status OPEN → APPROVED
  - reject:  session.status OPEN → REJECTED
  - declare: session.status APPROVED → DECLARED
  - mark adjustments blocked after APPROVED / DECLARED

Revision ID: 0043ten
Revises: 0042ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0043ten"
down_revision = "0042ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # exam_board_sessions
    op.create_table(
        "exam_board_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("exam_paper_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_title",  sa.Text,                       nullable=False),
        sa.Column("convened_by",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "convened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column("board_remarks", sa.Text,                        nullable=True),
        sa.Column("decided_by",    postgresql.UUID(as_uuid=True),  nullable=True),
        sa.Column("decided_at",    sa.DateTime(timezone=True),     nullable=True),
        sa.Column("declared_by",   postgresql.UUID(as_uuid=True),  nullable=True),
        sa.Column("declared_at",   sa.DateTime(timezone=True),     nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_board_sessions_exam_paper",  "exam_board_sessions", ["exam_paper_id"])
    op.create_index("ix_board_sessions_status",       "exam_board_sessions", ["status"])
    op.create_index("ix_board_sessions_convened_by",  "exam_board_sessions", ["convened_by"])
    op.create_index("ix_board_sessions_created_at",   "exam_board_sessions", ["created_at"])

    # exam_board_course_approvals
    op.create_table(
        "exam_board_course_approvals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_board_sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("exam_paper_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mean_marks",      sa.Numeric(6, 2),              nullable=True),
        sa.Column("max_marks",       sa.Numeric(6, 2),              nullable=True),
        sa.Column("pass_count",      sa.Integer,                    nullable=True),
        sa.Column("fail_count",      sa.Integer,                    nullable=True),
        sa.Column("total_scripts",   sa.Integer,                    nullable=True),
        sa.Column("pass_rate_pct",   sa.Numeric(5, 2),              nullable=True),
        sa.Column(
            "approval_status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_board_course_approvals_session",    "exam_board_course_approvals", ["session_id"]
    )
    op.create_index(
        "ix_board_course_approvals_exam_paper", "exam_board_course_approvals", ["exam_paper_id"]
    )
    op.create_index(
        "ix_board_course_approvals_status",     "exam_board_course_approvals", ["approval_status"]
    )


def downgrade() -> None:
    op.drop_index("ix_board_course_approvals_status",     table_name="exam_board_course_approvals")
    op.drop_index("ix_board_course_approvals_exam_paper", table_name="exam_board_course_approvals")
    op.drop_index("ix_board_course_approvals_session",    table_name="exam_board_course_approvals")
    op.drop_table("exam_board_course_approvals")

    op.drop_index("ix_board_sessions_created_at",  table_name="exam_board_sessions")
    op.drop_index("ix_board_sessions_convened_by", table_name="exam_board_sessions")
    op.drop_index("ix_board_sessions_status",      table_name="exam_board_sessions")
    op.drop_index("ix_board_sessions_exam_paper",  table_name="exam_board_sessions")
    op.drop_table("exam_board_sessions")
