"""tenant: create academic master data (departments and programs)

Revision ID: 0015ten
Revises: 0014ten
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0015ten"
down_revision = "0014ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "academic_departments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_academic_departments_code"),
    )
    op.create_table(
        "academic_programs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dept_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column(
            "duration_years",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["dept_id"],
            ["academic_departments.id"],
            name="fk_academic_programs_dept_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_academic_programs_code"),
    )


def downgrade() -> None:
    op.drop_table("academic_programs")
    op.drop_table("academic_departments")
