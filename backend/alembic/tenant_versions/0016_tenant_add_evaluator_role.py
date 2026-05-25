"""tenant: add EVALUATOR role and evaluator_assignments table

Revision ID: 0016ten
Revises: 0015ten
Create Date: 2026-05-25

Notes:
  ALTER TYPE ADD VALUE IF NOT EXISTS is safe inside a transaction on PG 12+.
  Downgrade removes the table but cannot remove the enum value (Postgres
  limitation); document this in release notes.
"""

from alembic import op

revision = "0016ten"
down_revision = "0015ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend the tenantrole enum — safe in transaction on PG 12+
    op.execute("ALTER TYPE tenantrole ADD VALUE IF NOT EXISTS 'EVALUATOR'")

    # Evaluator-to-assignment mapping table
    op.execute("""
        CREATE TABLE evaluator_assignments (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            assignment_id       UUID        NOT NULL
                REFERENCES lab_assignments(id) ON DELETE CASCADE,
            evaluator_user_id   UUID        NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,
            assigned_by_user_id UUID        NOT NULL
                REFERENCES users(id),
            assigned_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
            UNIQUE (assignment_id, evaluator_user_id)
        )
    """)
    op.execute(
        "CREATE INDEX ix_evaluator_assignments_evaluator "
        "ON evaluator_assignments(evaluator_user_id)"
    )
    op.execute(
        "CREATE INDEX ix_evaluator_assignments_assignment "
        "ON evaluator_assignments(assignment_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evaluator_assignments")
    # Cannot remove 'EVALUATOR' value from tenantrole enum in Postgres.
    # Document: downgrade leaves the enum value but removes the table.
