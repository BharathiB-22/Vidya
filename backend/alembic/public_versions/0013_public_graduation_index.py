"""0013pub – H62: Public graduation certificate verification index

Creates public.public_graduation_index so that the platform-level
GET /verify/certificate/{number} endpoint can resolve which tenant schema to
query without requiring the caller to supply a tenant slug.

Written at certificate issuance; updated on revocation.
certificate_number is globally unique (CERT/{TENANT}/{YEAR}/{SEQ}).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0013pub"
down_revision = "0012pub"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "public_graduation_index",
        sa.Column("certificate_number", sa.String(50),
                  nullable=False, primary_key=True),
        sa.Column("tenant_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_name",        sa.String(100),                nullable=False),
        sa.Column("certificate_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id",         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_provisional",     sa.Boolean,                    nullable=False,
                  server_default=sa.text("false")),
        sa.Column("status",             sa.String(20),                 nullable=False),
        sa.Column("graduation_year",    sa.SmallInteger,               nullable=True),
        sa.Column("issued_at",          sa.TIMESTAMP(timezone=True),   nullable=True),
        sa.Column("updated_at",         sa.TIMESTAMP(timezone=True),   nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_public_graduation_index_tenant_id",
        "public_graduation_index",
        ["tenant_id"],
        schema="public",
    )
    op.create_index(
        "ix_public_graduation_index_certificate_id",
        "public_graduation_index",
        ["certificate_id"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_public_graduation_index_certificate_id",
        table_name="public_graduation_index",
        schema="public",
    )
    op.drop_index(
        "ix_public_graduation_index_tenant_id",
        table_name="public_graduation_index",
        schema="public",
    )
    op.drop_table("public_graduation_index", schema="public")
