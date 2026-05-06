"""public: create audit_logs table

Revision ID: 0003pub
Revises: 0002pub
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003pub"
down_revision = "0002pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_name", sa.String(), nullable=True),
        sa.Column("target_entity", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["public.tenants.id"],
            ondelete="SET NULL",
        ),
        schema="public",
    )

    op.create_index(
        "ix_audit_logs_tenant_created",
        "audit_logs",
        ["tenant_id", "created_at"],
        schema="public",
    )
    op.create_index(
        "ix_audit_logs_event_created",
        "audit_logs",
        ["event_type", "created_at"],
        schema="public",
    )
    op.create_index(
        "ix_audit_logs_actor_created",
        "audit_logs",
        ["actor_user_id", "created_at"],
        schema="public",
    )
    op.create_index(
        "ix_audit_logs_created",
        "audit_logs",
        ["created_at"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created",        table_name="audit_logs", schema="public")
    op.drop_index("ix_audit_logs_actor_created",  table_name="audit_logs", schema="public")
    op.drop_index("ix_audit_logs_event_created",  table_name="audit_logs", schema="public")
    op.drop_index("ix_audit_logs_tenant_created", table_name="audit_logs", schema="public")
    op.drop_table("audit_logs", schema="public")
