"""public: add governance_type to tenants — Phase A (Academic Governance V1)

Revision ID: 0017pub
Revises: 0016pub
Create Date: 2026-07-11

Summary of changes
------------------

ALTER public.tenants
    + governance_type  VARCHAR(30)  NOT NULL  DEFAULT 'BOARD'

The academic governance authority of a tenant. Purely a *display name* choice
made by the Platform Admin when the tenant is created — the permissions behind
BOARD and UNIVERSITY_MEMBERS are byte-for-byte identical. A university that
calls its curriculum authority "Board of Studies" and one that calls it
"University Members" run the same code path; only the label rendered in the UI
differs.

Existing tenants default to 'BOARD', which is the label the platform used
implicitly before this migration.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0017pub"
down_revision = "0016pub"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "governance_type",
            sa.String(30),
            nullable=False,
            server_default="BOARD",
        ),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "governance_type", schema="public")
