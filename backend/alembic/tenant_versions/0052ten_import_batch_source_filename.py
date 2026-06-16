"""tenant: record source file name on import batches — Phase 1.1 (Task A)

Revision ID: 0052ten
Revises: 0051ten
Create Date: 2026-06-16

Summary of changes
------------------

ALTER sis_import_batches
    + source_filename  VARCHAR(255)  NULL

Captures the uploaded CSV/XLSX file name for every import batch so the audit
trail (SIS → Import History) can show where a batch came from.  Nullable and
additive: existing rows keep NULL, and the shared ImportBatchService.create_batch
treats the field as optional, so older callers are unaffected.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0052ten"
down_revision = "0051ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "sis_import_batches",
        sa.Column("source_filename", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sis_import_batches", "source_filename")
