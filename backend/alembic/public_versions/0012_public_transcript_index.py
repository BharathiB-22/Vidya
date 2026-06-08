"""0012pub – H61: Public transcript verification index

Creates public.public_transcript_index so that the platform-level
GET /verify/{code} endpoint can resolve which tenant schema to query
without requiring the caller to supply a tenant slug.

Written at issuance; updated on revocation / supersession.
Append-friendly: verification_code is globally unique (UUID4 collision
probability ~2^-64; UNIQUE constraint enforces this at DB level).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0012pub"
down_revision = "0011pub"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "public_transcript_index",
        sa.Column("verification_code", postgresql.UUID(as_uuid=True),
                  nullable=False, primary_key=True),
        sa.Column("tenant_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_name",         sa.String(100), nullable=False),
        sa.Column("transcript_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_number",   sa.String(50),  nullable=True),
        sa.Column("status",              sa.String(15),  nullable=False),
        sa.Column("issued_at",           sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at",          sa.TIMESTAMP(timezone=True), nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_public_transcript_index_tenant_id",
        "public_transcript_index",
        ["tenant_id"],
        schema="public",
    )
    op.create_index(
        "ix_public_transcript_index_transcript_id",
        "public_transcript_index",
        ["transcript_id"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_public_transcript_index_transcript_id",
        table_name="public_transcript_index",
        schema="public",
    )
    op.drop_index(
        "ix_public_transcript_index_tenant_id",
        table_name="public_transcript_index",
        schema="public",
    )
    op.drop_table("public_transcript_index", schema="public")
