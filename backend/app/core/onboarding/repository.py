from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class OnboardingRepository:

    # ------------------------------------------------------------------ #
    # Duplicate-check helpers (raw SQL to stay in current search_path)    #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_existing_identifiers(identifiers: list[str], db: AsyncSession) -> set[str]:
        if not identifiers:
            return set()
        result = await db.execute(
            text("SELECT identifier FROM users WHERE identifier = ANY(:ids)"),
            {"ids": identifiers},
        )
        return {row[0] for row in result.fetchall()}

    @staticmethod
    async def get_existing_emails(emails: list[str], db: AsyncSession) -> set[str]:
        if not emails:
            return set()
        lowered = [e.lower() for e in emails]
        result = await db.execute(
            text("SELECT LOWER(email) FROM users WHERE LOWER(email) = ANY(:emails)"),
            {"emails": lowered},
        )
        return {row[0] for row in result.fetchall()}

    # ------------------------------------------------------------------ #
    # Bulk user insert (raw SQL to avoid asyncpg native-enum OID issues)  #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def bulk_insert_users(rows: list[dict], db: AsyncSession) -> int:
        """Insert user rows atomically.

        Each dict must contain: id, email, pw_hash, role, full_name, identifier.
        Uses CAST(:role AS tenantrole) so PostgreSQL resolves the enum from
        the current search_path rather than relying on SQLAlchemy metadata.
        """
        if not rows:
            return 0
        for row in rows:
            await db.execute(
                text(
                    "INSERT INTO users "
                    "    (id, email, password_hash, role, full_name, identifier, "
                    "     is_active, must_change_password) "
                    "VALUES "
                    "    (:id, :email, :pw_hash, CAST(:role AS tenantrole), "
                    "     :full_name, :identifier, true, true)"
                ),
                row,
            )
        return len(rows)

    # ------------------------------------------------------------------ #
    # Enrollment upsert                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def bulk_upsert_enrollments(
        pairs: list[tuple[str, str]], db: AsyncSession
    ) -> int:
        """Upsert student→section enrollments.

        pairs = [(student_id_str, section_id_str), ...]
        ON CONFLICT (student_id): update section_id and re-activate.
        """
        if not pairs:
            return 0
        for student_id, section_id in pairs:
            await db.execute(
                text(
                    "INSERT INTO acad_enrollments (id, student_id, section_id) "
                    "VALUES (gen_random_uuid(), :sid, :sec) "
                    "ON CONFLICT (student_id) DO UPDATE "
                    "SET section_id = EXCLUDED.section_id, is_active = true"
                ),
                {"sid": student_id, "sec": section_id},
            )
        return len(pairs)
