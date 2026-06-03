"""0030 – SIS H50: create sis_faculty_profiles"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0030ten"
down_revision = "0029ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sis_faculty_profiles",
        sa.Column("user_id",               UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("employee_id",           sa.String(30),  nullable=False),
        sa.Column("designation",           sa.String(100), nullable=True),
        sa.Column("qualifications",        sa.Text,        nullable=True),
        sa.Column("bio",                   sa.Text,        nullable=True),
        sa.Column("office_location",       sa.String(200), nullable=True),
        sa.Column("phone",                 sa.String(20),  nullable=True),
        sa.Column("joining_date",          sa.Date,        nullable=True),
        sa.Column("specialization",        sa.String(200), nullable=True),
        sa.Column("primary_department_id", UUID(as_uuid=True),
                  sa.ForeignKey("acad_departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("photo_url",             sa.String(500), nullable=True),
        sa.Column("is_active",             sa.Boolean,     nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",            sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",            sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_sis_faculty_profiles_employee_id", "sis_faculty_profiles", ["employee_id"])
    op.create_index("ix_sis_faculty_profiles_employee_id", "sis_faculty_profiles", ["employee_id"])
    op.create_index("ix_sis_faculty_profiles_primary_department_id", "sis_faculty_profiles", ["primary_department_id"])


def downgrade() -> None:
    op.drop_index("ix_sis_faculty_profiles_primary_department_id", table_name="sis_faculty_profiles")
    op.drop_index("ix_sis_faculty_profiles_employee_id", table_name="sis_faculty_profiles")
    op.drop_constraint("uq_sis_faculty_profiles_employee_id", "sis_faculty_profiles", type_="unique")
    op.drop_table("sis_faculty_profiles")
