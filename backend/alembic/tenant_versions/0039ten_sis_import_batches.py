"""tenant: SIS import batch tracking — H64.1

Revision ID: 0039ten
Revises: 0038ten
Create Date: 2026-06-09

Summary of changes
------------------

CREATE TABLE sis_import_batches
    Tracks every bulk CSV/XLSX import committed via BulkProfileImportService.
    One row per commit call; rollback logic added in H64.2.

ALTER sis_student_profiles
    + import_batch_id  UUID FK → sis_import_batches.id  NULL ON DELETE SET NULL

ALTER sis_faculty_profiles
    + import_batch_id  UUID FK → sis_import_batches.id  NULL ON DELETE SET NULL

Human-gate invariants:
    is_rolled_back is set ONLY by ImportBatchService.rollback_batch() (H64.2).
    Rows in this table are append-only from the import side;
    rollback writes rolled_back_by / rolled_back_at in-place (not a new row).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0039ten"
down_revision = "0038ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. sis_import_batches
    # ------------------------------------------------------------------
    op.create_table(
        "sis_import_batches",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_ref",     sa.String(30),  nullable=False),
        sa.Column("imported_by",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("imported_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("record_type",   sa.String(20),  nullable=False),   # STUDENT | FACULTY
        sa.Column("total_records", sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("failed_count",  sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("is_rolled_back",sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("rolled_back_by",postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rolled_back_at",sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("batch_ref", name="uq_sis_import_batches_batch_ref"),
    )
    op.create_index("ix_sis_import_batches_imported_by",   "sis_import_batches", ["imported_by"])
    op.create_index("ix_sis_import_batches_imported_at",   "sis_import_batches", ["imported_at"])
    op.create_index("ix_sis_import_batches_is_rolled_back","sis_import_batches", ["is_rolled_back"])

    # ------------------------------------------------------------------
    # 2. sis_student_profiles — batch FK
    # ------------------------------------------------------------------
    op.add_column(
        "sis_student_profiles",
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sis_import_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sis_student_profiles_import_batch_id",
        "sis_student_profiles",
        ["import_batch_id"],
    )

    # ------------------------------------------------------------------
    # 3. sis_faculty_profiles — batch FK
    # ------------------------------------------------------------------
    op.add_column(
        "sis_faculty_profiles",
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sis_import_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sis_faculty_profiles_import_batch_id",
        "sis_faculty_profiles",
        ["import_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sis_faculty_profiles_import_batch_id",  table_name="sis_faculty_profiles")
    op.drop_column("sis_faculty_profiles",  "import_batch_id")

    op.drop_index("ix_sis_student_profiles_import_batch_id", table_name="sis_student_profiles")
    op.drop_column("sis_student_profiles", "import_batch_id")

    op.drop_index("ix_sis_import_batches_is_rolled_back", table_name="sis_import_batches")
    op.drop_index("ix_sis_import_batches_imported_at",    table_name="sis_import_batches")
    op.drop_index("ix_sis_import_batches_imported_by",    table_name="sis_import_batches")
    op.drop_table("sis_import_batches")
