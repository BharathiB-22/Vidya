"""Faculty identity backfill — assign faculty_code + institution_email to
EXISTING faculty (ERP Onboarding Phase 1.5).

Preview-first and idempotent.  Rules (mirror the USN / institution-email
backfills):
  * Only ``users.role = 'FACULTY'`` rows are touched — ADMINs are never affected.
  * faculty_code / institution_email are assigned only when still NULL.
  * personal_email is backfilled from the login ``email`` (retained); the login
    ``email`` column is never modified — login is unchanged.
  * sis_faculty_profiles rows are created on demand for faculty that lack one.

Runs under the ``_admin_db`` dependency's ``session.begin()`` — atomic, no
explicit commit here.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.onboarding.faculty_backfill_schemas import (
    FacultyBackfillCommitResult,
    FacultyBackfillPreviewResponse,
    FacultyBackfillRow,
)
from app.core.onboarding.faculty_code_allocator import (
    DEFAULT_FACULTY_PREFIX,
    FacultyCodeAllocator,
)
from app.core.onboarding.faculty_institution_email import build_faculty_email

# All active FACULTY with their (optional) profile identity columns.
_LOAD_SQL = text(
    """
    SELECT u.id              AS user_id,
           u.full_name       AS full_name,
           u.email           AS login_email,
           p.faculty_code    AS faculty_code,
           p.institution_email AS institution_email
    FROM users u
    LEFT JOIN sis_faculty_profiles p ON p.user_id = u.id
    WHERE u.is_active = true AND u.role = 'FACULTY'
    ORDER BY u.full_name, u.id
    """
)


async def _domain(db: AsyncSession) -> str | None:
    row = await db.execute(
        text("SELECT institution_domain FROM public.tenants WHERE schema_name = current_schema()")
    )
    return row.scalar_one_or_none()


async def _existing_emails(db: AsyncSession) -> set[str]:
    taken: set[str] = set()
    for tbl, col in (("sis_faculty_profiles", "institution_email"), ("users", "institution_email")):
        res = await db.execute(text(f"SELECT {col} FROM {tbl} WHERE {col} IS NOT NULL"))
        taken.update((v or "").strip().lower() for v in res.scalars().all())
    return taken


def _effective_next(counter: int | None, existing_max: int) -> int:
    return max(int(counter or 1), int(existing_max or 0) + 1, 1)


async def _counter_and_max(db: AsyncSession, prefix: str) -> tuple[int | None, int]:
    counter = (
        await db.execute(
            text("SELECT next_value FROM faculty_code_counters WHERE prefix = :p"),
            {"p": prefix},
        )
    ).scalar_one_or_none()
    existing_max = (
        await db.execute(
            text(
                "SELECT COALESCE(MAX("
                "  CAST(SUBSTRING(faculty_code FROM (char_length(:p) + 1)) AS INTEGER)"
                "), 0) "
                "FROM sis_faculty_profiles "
                "WHERE faculty_code ~ ('^' || :p || '[0-9]+$')"
            ),
            {"p": prefix},
        )
    ).scalar_one()
    return counter, int(existing_max or 0)


class FacultyBackfillService:

    @staticmethod
    async def preview(db: AsyncSession, *, prefix: str = DEFAULT_FACULTY_PREFIX) -> FacultyBackfillPreviewResponse:
        rows_raw = (await db.execute(_LOAD_SQL)).mappings().all()
        domain = await _domain(db)
        taken = await _existing_emails(db)
        counter, existing_max = await _counter_and_max(db, prefix)
        next_seq = _effective_next(counter, existing_max)

        out: list[FacultyBackfillRow] = []
        codes_to_assign = emails_to_assign = already = 0
        for r in rows_raw:
            need_code = not r["faculty_code"]
            need_email = (not r["institution_email"]) and bool(domain)
            row = FacultyBackfillRow(
                user_id=r["user_id"],
                full_name=r["full_name"],
                login_email=r["login_email"],
                existing_faculty_code=r["faculty_code"],
                existing_institution_email=r["institution_email"],
                action="SKIP_COMPLETE",
            )
            if need_code:
                row.projected_faculty_code = FacultyCodeAllocator.format_code(prefix, next_seq)
                next_seq += 1
                codes_to_assign += 1
            if need_email:
                proj = build_faculty_email(r["full_name"], domain, taken)
                if proj:
                    row.projected_institution_email = proj
                    emails_to_assign += 1
            if need_code and row.projected_institution_email:
                row.action = "ASSIGN_BOTH"
            elif need_code:
                row.action = "ASSIGN_CODE"
            elif row.projected_institution_email:
                row.action = "ASSIGN_EMAIL"
            else:
                already += 1
                if not domain and not r["institution_email"]:
                    row.note = "no institution domain configured — email skipped"
            out.append(row)

        return FacultyBackfillPreviewResponse(
            domain=domain,
            total_faculty=len(rows_raw),
            codes_to_assign=codes_to_assign,
            emails_to_assign=emails_to_assign,
            already_complete=already,
            rows=out,
        )

    @staticmethod
    async def commit(
        db: AsyncSession,
        *,
        actor_user_id: UUID,
        prefix: str = DEFAULT_FACULTY_PREFIX,
    ) -> FacultyBackfillCommitResult:
        from app.modules.m11_sis.import_batch_service import ImportBatchService

        rows_raw = (await db.execute(_LOAD_SQL)).mappings().all()
        domain = await _domain(db)
        taken = await _existing_emails(db)

        need_code_rows = [r for r in rows_raw if not r["faculty_code"]]
        await FacultyCodeAllocator.seed_counter_from_existing(db, prefix=prefix)
        codes: list[str] = []
        if need_code_rows:
            codes = await FacultyCodeAllocator.allocate_codes(db, prefix=prefix, count=len(need_code_rows))
        code_by_uid = {str(r["user_id"]): c for r, c in zip(need_code_rows, codes)}

        codes_assigned = emails_assigned = personal_backfilled = profiles_created = 0
        errors: list[str] = []

        for r in rows_raw:
            uid = str(r["user_id"])
            new_code = code_by_uid.get(uid)
            new_email = None
            if (not r["institution_email"]) and domain:
                new_email = build_faculty_email(r["full_name"], domain, taken)
            if not new_code and not new_email:
                continue

            # Upsert the profile: set the columns that are still NULL only.
            res = await db.execute(
                text(
                    "INSERT INTO sis_faculty_profiles "
                    "    (user_id, faculty_code, institution_email, is_active, lifecycle_status) "
                    "VALUES (:uid, :code, :email, true, 'ACTIVE') "
                    "ON CONFLICT (user_id) DO UPDATE SET "
                    "    faculty_code      = COALESCE(sis_faculty_profiles.faculty_code, EXCLUDED.faculty_code), "
                    "    institution_email = COALESCE(sis_faculty_profiles.institution_email, EXCLUDED.institution_email), "
                    "    updated_at        = now() "
                    "RETURNING (xmax = 0) AS inserted"
                ),
                {"uid": uid, "code": new_code, "email": new_email},
            )
            inserted = bool(res.scalar_one())
            if inserted:
                profiles_created += 1
            if new_code:
                codes_assigned += 1
            if new_email:
                emails_assigned += 1

        # Backfill personal_email from the login email (login unchanged).
        pe = await db.execute(
            text(
                "UPDATE users SET personal_email = email "
                "WHERE role = 'FACULTY' AND is_active = true AND personal_email IS NULL"
            )
        )
        personal_backfilled = pe.rowcount or 0

        batch_ref = None
        if codes_assigned or emails_assigned:
            batch = await ImportBatchService.create_batch(
                imported_by=actor_user_id,
                record_type="FACULTY_BACKFILL",
                total_records=len(rows_raw),
                success_count=codes_assigned + emails_assigned,
                failed_count=len(errors),
                db=db,
            )
            batch_ref = batch.batch_ref

        return FacultyBackfillCommitResult(
            domain=domain,
            total_faculty=len(rows_raw),
            codes_assigned=codes_assigned,
            emails_assigned=emails_assigned,
            personal_emails_backfilled=personal_backfilled,
            profiles_created=profiles_created,
            batch_ref=batch_ref,
            errors=errors,
        )
