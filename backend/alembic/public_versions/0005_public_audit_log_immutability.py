"""public: enforce audit_logs immutability at the database layer

Revision ID: 0005pub
Revises: 0004pub
Create Date: 2026-05-19

Adds three PostgreSQL triggers that raise an exception if any session
(including superusers via the application connection) attempts to UPDATE,
DELETE, or TRUNCATE the public.audit_logs table.

This is a defence-in-depth control that complements the code-level
append-only repository pattern.  The only permitted write operation is
INSERT.  The downgrade() removes all three triggers and the trigger
function, fully reversing the migration.
"""

from alembic import op

revision = "0005pub"
down_revision = "0004pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Trigger function shared by all three triggers.
    # Returns TRIGGER (required for row-level triggers); for TRUNCATE the
    # return value is ignored, but the function signature is the same.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.audit_logs_no_mutate()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs is append-only: % operations are not permitted. '
                'All audit records must be preserved for compliance.',
                TG_OP;
        END;
        $$;
        """
    )

    # Block row-level UPDATE.
    op.execute(
        """
        CREATE TRIGGER audit_logs_block_update
            BEFORE UPDATE ON public.audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION public.audit_logs_no_mutate();
        """
    )

    # Block row-level DELETE.
    op.execute(
        """
        CREATE TRIGGER audit_logs_block_delete
            BEFORE DELETE ON public.audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION public.audit_logs_no_mutate();
        """
    )

    # Block TRUNCATE (statement-level — no OLD/NEW row available).
    op.execute(
        """
        CREATE TRIGGER audit_logs_block_truncate
            BEFORE TRUNCATE ON public.audit_logs
            FOR EACH STATEMENT
            EXECUTE FUNCTION public.audit_logs_no_mutate();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_block_truncate ON public.audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_block_delete   ON public.audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_block_update   ON public.audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS public.audit_logs_no_mutate();")
