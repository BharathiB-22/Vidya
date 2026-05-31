"""0028 – M11 SIS: create sis_schools; add school_id to acad_departments"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sis_schools",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_sis_schools_code", "sis_schools", ["code"])
    op.create_unique_constraint("uq_sis_schools_name", "sis_schools", ["name"])
    op.create_index("ix_sis_schools_is_active", "sis_schools", ["is_active"])

    op.add_column(
        "acad_departments",
        sa.Column("school_id", UUID(as_uuid=True), sa.ForeignKey("sis_schools.id"), nullable=True),
    )
    op.create_index("ix_acad_departments_school_id", "acad_departments", ["school_id"])


def downgrade() -> None:
    op.drop_index("ix_acad_departments_school_id", table_name="acad_departments")
    op.drop_column("acad_departments", "school_id")
    op.drop_index("ix_sis_schools_is_active", table_name="sis_schools")
    op.drop_constraint("uq_sis_schools_name", "sis_schools", type_="unique")
    op.drop_constraint("uq_sis_schools_code", "sis_schools", type_="unique")
    op.drop_table("sis_schools")
