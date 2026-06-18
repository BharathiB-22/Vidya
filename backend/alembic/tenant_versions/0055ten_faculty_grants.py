"""Faculty identity & multi-responsibility — faculty_code, institution_email,
role grants, and the FAC code counter.

Phase 1.5 of the Intelligent ERP Onboarding programme.

Adds (all additive / backward-compatible):
  * sis_faculty_profiles.faculty_code       — official internal id (e.g. FAC0001),
                                               nullable at DB level, app-guaranteed,
                                               tenant-unique (partial-unique index).
  * sis_faculty_profiles.institution_email  — generated directory/SSO address;
                                               NOT a login identity. tenant-unique.
  * sis_faculty_profiles.employee_id        — NOT NULL constraint DROPPED
                                               (employee_id is no longer collected).
  * faculty_role_grants                     — GUIDE / EVALUATOR / BOARD / DEAN
                                               responsibilities held by a single
                                               FACULTY account. Soft-revoke only;
                                               a partial-unique index enforces at
                                               most one ACTIVE grant per
                                               (faculty_user_id, role_code).
  * faculty_code_counters                   — atomic FAC sequence allocation,
                                               keyed by prefix (mirrors
                                               usn_sequence_counters).

Tenant-scoped tables carry NO tenant_id column — isolation is via search_path,
consistent with faculty_program_assignments and usn_sequence_counters.

Revision ID: 0055ten
Revises: 0054ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0055ten"
down_revision = "0054ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ---- faculty_role_grants -------------------------------------------- #
    op.create_table(
        "faculty_role_grants",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("faculty_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_code",       sa.String(20), nullable=False),
        sa.Column("is_active",       sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("granted_by",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_at",      sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_by",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True), nullable=True),
    )
    # At most one ACTIVE grant per (faculty, role); revoked rows are exempt so
    # re-granting after revocation reactivates the same row.
    op.create_index(
        "uq_frg_active_faculty_role",
        "faculty_role_grants",
        ["faculty_user_id", "role_code"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index("ix_frg_role",           "faculty_role_grants", ["role_code", "is_active"])
    op.create_index("ix_frg_faculty_active", "faculty_role_grants", ["faculty_user_id", "is_active"])

    # ---- faculty_code_counters ------------------------------------------ #
    op.create_table(
        "faculty_code_counters",
        sa.Column("prefix",     sa.String(15), primary_key=True),
        sa.Column("next_value", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ---- sis_faculty_profiles additive columns -------------------------- #
    op.add_column("sis_faculty_profiles", sa.Column("faculty_code",      sa.String(20),  nullable=True))
    op.add_column("sis_faculty_profiles", sa.Column("institution_email", sa.String(255), nullable=True))
    # employee_id is no longer collected — loosen the NOT NULL constraint so
    # profiles created without one are valid.  Loosening never invalidates rows.
    op.alter_column("sis_faculty_profiles", "employee_id", existing_type=sa.String(30), nullable=True)

    op.create_index(
        "uq_faculty_profiles_faculty_code",
        "sis_faculty_profiles",
        ["faculty_code"],
        unique=True,
        postgresql_where=sa.text("faculty_code IS NOT NULL"),
    )
    op.create_index(
        "uq_faculty_profiles_institution_email",
        "sis_faculty_profiles",
        ["institution_email"],
        unique=True,
        postgresql_where=sa.text("institution_email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_faculty_profiles_institution_email", table_name="sis_faculty_profiles")
    op.drop_index("uq_faculty_profiles_faculty_code",      table_name="sis_faculty_profiles")
    op.drop_column("sis_faculty_profiles", "institution_email")
    op.drop_column("sis_faculty_profiles", "faculty_code")
    # NOTE: employee_id is intentionally left nullable on downgrade. Re-adding
    # NOT NULL could fail if profiles were created without one while this
    # revision was live; restoring it is left to a deliberate forward migration.

    op.drop_table("faculty_code_counters")

    op.drop_index("ix_frg_faculty_active",       table_name="faculty_role_grants")
    op.drop_index("ix_frg_role",                 table_name="faculty_role_grants")
    op.drop_index("uq_frg_active_faculty_role",  table_name="faculty_role_grants")
    op.drop_table("faculty_role_grants")
