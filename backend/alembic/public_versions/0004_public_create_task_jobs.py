"""public: create task_jobs table

Revision ID: 0004pub
Revises: 0003pub
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004pub"
down_revision = "0003pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_jobs",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_type",    sa.String(), nullable=False),
        sa.Column("queue_name",   sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED",
                name="taskjobstatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("payload",      postgresql.JSONB(), nullable=True),
        sa.Column("result",       postgresql.JSONB(), nullable=True),
        sa.Column("error",        sa.Text(),          nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["public.tenants.id"],
            ondelete="SET NULL",
        ),
        schema="public",
    )

    op.create_index(
        "ix_task_jobs_tenant_created",
        "task_jobs",
        ["tenant_id", "created_at"],
        schema="public",
    )
    op.create_index(
        "ix_task_jobs_status_created",
        "task_jobs",
        ["status", "created_at"],
        schema="public",
    )
    op.create_index(
        "ix_task_jobs_tenant_status",
        "task_jobs",
        ["tenant_id", "status"],
        schema="public",
    )
    op.create_index(
        "ix_task_jobs_created",
        "task_jobs",
        ["created_at"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_task_jobs_created",        table_name="task_jobs", schema="public")
    op.drop_index("ix_task_jobs_tenant_status",  table_name="task_jobs", schema="public")
    op.drop_index("ix_task_jobs_status_created", table_name="task_jobs", schema="public")
    op.drop_index("ix_task_jobs_tenant_created", table_name="task_jobs", schema="public")
    op.drop_table("task_jobs", schema="public")
