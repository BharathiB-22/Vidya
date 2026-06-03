"""0029 – SIS H50: create sis_student_profiles"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0029ten"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sis_student_profiles",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("usn",                    sa.String(30),  nullable=True),
        sa.Column("admission_year",         sa.Integer,     nullable=True),
        sa.Column("date_of_birth",          sa.Date,        nullable=True),
        sa.Column("phone",                  sa.String(20),  nullable=True),
        sa.Column("address_line1",          sa.String(200), nullable=True),
        sa.Column("address_city",           sa.String(100), nullable=True),
        sa.Column("address_state",          sa.String(100), nullable=True),
        sa.Column("emergency_contact_name", sa.String(100), nullable=True),
        sa.Column("emergency_contact_phone",sa.String(20),  nullable=True),
        sa.Column("photo_url",              sa.String(500), nullable=True),
        sa.Column("notes",                  sa.Text,        nullable=True),
        sa.Column("is_active",              sa.Boolean,     nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",             sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",             sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_sis_student_profiles_usn", "sis_student_profiles", ["usn"])
    op.create_index("ix_sis_student_profiles_usn", "sis_student_profiles", ["usn"])
    op.create_index("ix_sis_student_profiles_admission_year", "sis_student_profiles", ["admission_year"])


def downgrade() -> None:
    op.drop_index("ix_sis_student_profiles_admission_year", table_name="sis_student_profiles")
    op.drop_index("ix_sis_student_profiles_usn", table_name="sis_student_profiles")
    op.drop_constraint("uq_sis_student_profiles_usn", "sis_student_profiles", type_="unique")
    op.drop_table("sis_student_profiles")
