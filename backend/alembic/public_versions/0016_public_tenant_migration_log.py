"""public: create tenant_migration_log table

Records every automatic tenant schema migration run — at startup or via
the admin retry endpoint.  Powers the System → Tenant Migrations page.

Revision ID: 0016pub
Revises: 0015pub
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0016pub"
down_revision = "0015pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_migration_log",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("from_revision", sa.Text(), nullable=True),
        sa.Column("to_revision", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        schema="public",
    )
    op.create_index(
        "ix_tenant_migration_log_schema_name",
        "tenant_migration_log",
        ["schema_name"],
        schema="public",
    )
    op.create_index(
        "ix_tenant_migration_log_started_at",
        "tenant_migration_log",
        ["started_at"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_migration_log_started_at", table_name="tenant_migration_log", schema="public")
    op.drop_index("ix_tenant_migration_log_schema_name", table_name="tenant_migration_log", schema="public")
    op.drop_table("tenant_migration_log", schema="public")
