"""USN sequence counters — concurrency-safe per (school, year, program) allocation.

Phase 1 / Step 1 of the Intelligent ERP Onboarding programme.

`next_seq` is the next sequence number to hand out (starts at 1).  Blocks are
reserved atomically by UsnAllocator via
    INSERT ... ON CONFLICT (school_code, admission_year, program_code)
    DO UPDATE SET next_seq = next_seq + :n RETURNING next_seq
The ON CONFLICT row lock serialises concurrent callers, so every issued USN
sequence is contiguous, gap-free, and never double-assigned.  Sequence resets
per (school, admission_year, program): SCA/2026/MCA is independent of
SCA/2026/BCA and of SCA/2027/MCA.

admission_year is stored full (e.g. 2026); the USN string renders the 2-digit
suffix.  Import-layer year validation keeps years within a single century so the
2-digit rendering stays unambiguous.

Revision ID: 0050ten
Revises: 0049ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "0050ten"
down_revision = "0049ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "usn_sequence_counters",
        sa.Column("school_code",    sa.String(10), nullable=False),
        sa.Column("admission_year", sa.Integer,    nullable=False),
        sa.Column("program_code",   sa.String(10), nullable=False),
        sa.Column("next_seq",       sa.Integer,    nullable=False, server_default="1"),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",     sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "school_code", "admission_year", "program_code",
            name="pk_usn_sequence_counters",
        ),
    )


def downgrade() -> None:
    op.drop_table("usn_sequence_counters")
