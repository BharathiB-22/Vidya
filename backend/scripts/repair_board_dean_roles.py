#!/usr/bin/env python3
"""
Repair script: upgrade legacy BOARD/DEAN-grant FACULTY users to proper primary roles.

Pre-Phase 1.7, BOARD (and sometimes DEAN) were imported as:
  users.role = 'FACULTY'  +  faculty_role_grants.role_code = 'BOARD' | 'DEAN'

This script for each active tenant schema:
  1. Finds FACULTY users with an active BOARD or DEAN grant
  2. Updates users.role to the grant role (BOARD or DEAN)
  3. Deletes sis_faculty_profiles for these users (removes faculty_code etc.)
  4. Soft-revokes ALL grants for these users (they are no longer FACULTY)
  5. Deletes faculty_program_assignments for these users

Usage:
  DATABASE_URL=postgresql://vidya:pass@localhost:5432/vidya \\
      python backend/scripts/repair_board_dean_roles.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import sys

DRY_RUN = "--dry-run" in sys.argv
REPAIR_GRANTS = ["BOARD", "DEAN"]


async def repair_schema(conn, schema: str, tenant_name: str) -> int:
    """Repair one tenant schema. Returns number of users changed."""
    await conn.execute(f"SET LOCAL search_path = {schema}, public")

    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (u.id) u.id, u.full_name, u.email, frg.role_code
        FROM users u
        JOIN faculty_role_grants frg ON frg.faculty_user_id = u.id
        WHERE u.role = 'FACULTY'
          AND frg.role_code = ANY($1)
          AND frg.is_active = true
        ORDER BY u.id, frg.role_code
        """,
        REPAIR_GRANTS,
    )

    if not rows:
        print(f"  [{schema}] no legacy users — nothing to do")
        return 0

    changed = 0
    for row in rows:
        uid       = row["id"]
        name      = row["full_name"]
        email     = row["email"]
        new_role  = row["role_code"]
        prefix    = "  [DRY RUN]" if DRY_RUN else "  "
        print(f"{prefix} [{schema}] {name} <{email}>  FACULTY → {new_role}")

        if DRY_RUN:
            continue

        # 1. Promote the primary role
        await conn.execute(
            "UPDATE users SET role = $1, updated_at = now() WHERE id = $2",
            new_role, uid,
        )

        # 2. Remove faculty profile (includes faculty_code / employee_id)
        deleted_profile = await conn.fetchval(
            "DELETE FROM sis_faculty_profiles WHERE user_id = $1 RETURNING 1",
            uid,
        )

        # 3. Soft-revoke ALL active grants (user is no longer a FACULTY account)
        revoked = await conn.fetchval(
            """
            WITH r AS (
                UPDATE faculty_role_grants
                SET is_active  = false,
                    revoked_by = $2,
                    revoked_at = now(),
                    updated_at = now()
                WHERE faculty_user_id = $1 AND is_active = true
                RETURNING 1
            ) SELECT count(*) FROM r
            """,
            uid, uid,
        )

        # 4. Remove program assignments (teaching loads don't apply to governance roles)
        del_assignments = await conn.fetchval(
            """
            WITH d AS (
                DELETE FROM faculty_program_assignments
                WHERE faculty_user_id = $1
                RETURNING 1
            ) SELECT count(*) FROM d
            """,
            uid,
        )

        print(
            f"         profile={'removed' if deleted_profile else 'missing'}, "
            f"grants_revoked={revoked}, assignments_removed={del_assignments}"
        )
        changed += 1

    return changed


async def main() -> None:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        print("ERROR: asyncpg not found. Run: pip install asyncpg", file=sys.stderr)
        sys.exit(1)

    import asyncpg

    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    # Strip SQLAlchemy dialect prefix if present
    pg_url = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(pg_url)
    try:
        tenants = await conn.fetch(
            "SELECT name, schema_name FROM public.tenants ORDER BY name"
        )
    except Exception as exc:
        print(f"ERROR: Could not query public.tenants — {exc}", file=sys.stderr)
        await conn.close()
        sys.exit(1)

    if not tenants:
        print("No tenants found in public.tenants.")
        await conn.close()
        return

    mode = "DRY RUN — no changes will be made" if DRY_RUN else "LIVE RUN"
    print(f"\n{mode}")
    print(f"Scanning {len(tenants)} tenant(s)…\n")

    total = 0
    for t in tenants:
        schema = t["schema_name"]
        name   = t["name"]
        print(f"[{name}]  schema={schema}")
        async with conn.transaction():
            count = await repair_schema(conn, schema, name)
            total += count
        print()

    verb = "Would update" if DRY_RUN else "Updated"
    print(f"{verb} {total} user(s) across {len(tenants)} tenant(s).")

    if DRY_RUN and total > 0:
        print("\nRe-run without --dry-run to apply changes.")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
