"""Institution email foundation — Phase 1.2 / Task C.

Generates institutional email addresses for existing members:

    Student :  {usn}@{institution_domain}          e.g. sca26bca001@lms.edu
    Faculty :  {employee_id}@{institution_domain}   e.g. emp001@lms.edu

Preview-first and idempotent.  Rules:
  * institution_email is unique per tenant (enforced by uq_users_institution_email).
  * personal_email is backfilled from the existing `email` (retained), never lost.
  * the existing `email` column (used for login) is left untouched.

The `institution_domain` lives on public.tenants.  Both the preview and the
commit read it (the _admin_db session's search_path includes `public`).  A
domain can be passed in to override / set the stored value.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.onboarding.institution_email_schemas import (
    InstitutionDomainOut,
    InstitutionEmailCommitResult,
    InstitutionEmailPreviewResponse,
    InstitutionEmailRow,
    normalize_domain,
)


class InstitutionEmailError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def format_email(local_part: str, domain: str) -> str:
    """{usn|employee_id}@{domain}, lower-cased."""
    return f"{local_part.strip().lower()}@{normalize_domain(domain)}"


_LOAD_SQL = text(
    """
    SELECT
        u.id                AS user_id,
        u.full_name         AS full_name,
        u.role              AS role,
        u.email             AS login_email,
        u.institution_email AS existing_inst,
        sp.usn              AS usn,
        fp.employee_id      AS employee_id
    FROM users u
    LEFT JOIN sis_student_profiles sp ON sp.user_id = u.id
    LEFT JOIN sis_faculty_profiles fp ON fp.user_id = u.id
    WHERE u.is_active = true AND u.role IN ('STUDENT', 'FACULTY')
    ORDER BY u.full_name, u.id
    """
)

# Assigns institution_email only when still NULL; backfills personal_email from
# the login email (retained); never touches the login `email` column.
_WRITE_SQL = text(
    """
    UPDATE users
       SET institution_email = :inst,
           personal_email     = COALESCE(personal_email, email)
     WHERE id = :uid AND institution_email IS NULL
    """
)


def _local_part(row: dict) -> tuple[str | None, str]:
    """Return (local_part, kind) for a user row."""
    if row["role"] == "STUDENT":
        return (row["usn"], "usn")
    return (row["employee_id"], "employee_id")


class InstitutionEmailService:

    # ------------------------------------------------------------------ #
    # Domain accessors (public.tenants)                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_domain(db: AsyncSession, *, schema_name: str) -> InstitutionDomainOut:
        result = await db.execute(
            text("SELECT institution_domain FROM public.tenants WHERE schema_name = :s"),
            {"s": schema_name},
        )
        return InstitutionDomainOut(institution_domain=result.scalar_one_or_none())

    @staticmethod
    async def set_domain(db: AsyncSession, *, schema_name: str, domain: str) -> InstitutionDomainOut:
        dom = normalize_domain(domain)
        await db.execute(
            text("UPDATE public.tenants SET institution_domain = :d WHERE schema_name = :s"),
            {"d": dom, "s": schema_name},
        )
        return InstitutionDomainOut(institution_domain=dom)

    @staticmethod
    async def _resolve_domain(
        db: AsyncSession, *, schema_name: str, override: str | None
    ) -> str:
        dom = normalize_domain(override) if override else None
        if not dom:
            stored = (await InstitutionEmailService.get_domain(db, schema_name=schema_name)).institution_domain
            dom = normalize_domain(stored) if stored else None
        if not dom:
            raise InstitutionEmailError(
                "NO_DOMAIN",
                "No institution domain configured. Set one (e.g. lms.edu) first.",
                422,
            )
        return dom

    @staticmethod
    async def _load(db: AsyncSession) -> list[dict]:
        result = await db.execute(_LOAD_SQL)
        return [dict(r) for r in result.mappings().all()]

    # ------------------------------------------------------------------ #
    # Preview (read-only)                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def preview(
        db: AsyncSession, *, schema_name: str, override_domain: str | None = None
    ) -> InstitutionEmailPreviewResponse:
        domain = await InstitutionEmailService._resolve_domain(
            db, schema_name=schema_name, override=override_domain
        )
        rows = await InstitutionEmailService._load(db)

        # Emails already taken (so a projection that collides is a CONFLICT).
        taken = {
            (r["existing_inst"] or "").strip().lower()
            for r in rows if r["existing_inst"]
        }

        out: list[InstitutionEmailRow] = []
        students = faculty = to_assign = already = no_id = conflicts = 0

        for r in rows:
            if r["role"] == "STUDENT":
                students += 1
            else:
                faculty += 1

            local, kind = _local_part(r)
            row = InstitutionEmailRow(
                user_id=r["user_id"],
                full_name=r["full_name"],
                role=r["role"],
                login_email=r["login_email"],
                identifier=local,
                existing_institution_email=r["existing_inst"],
                action="",
            )

            if r["existing_inst"]:
                row.action = "SKIP_HAS_EMAIL"
                already += 1
                out.append(row)
                continue

            if not (local and str(local).strip()):
                row.action = "SKIP_NO_IDENTIFIER"
                row.note = f"no {kind} on record"
                no_id += 1
                out.append(row)
                continue

            projected = format_email(str(local), domain)
            if projected in taken:
                row.action = "CONFLICT"
                row.projected_institution_email = projected
                row.note = f"{projected} already assigned to another user"
                conflicts += 1
                out.append(row)
                continue

            row.action = "ASSIGN"
            row.projected_institution_email = projected
            taken.add(projected)  # reserve within this preview run
            to_assign += 1
            out.append(row)

        return InstitutionEmailPreviewResponse(
            domain=domain,
            total_users=len(rows),
            students=students,
            faculty=faculty,
            to_assign=to_assign,
            already_have=already,
            no_identifier=no_id,
            conflicts=conflicts,
            rows=out,
        )

    # ------------------------------------------------------------------ #
    # Commit (atomic, idempotent)                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def commit(
        db: AsyncSession,
        *,
        schema_name: str,
        actor_user_id: UUID,
        override_domain: str | None = None,
    ) -> InstitutionEmailCommitResult:
        from app.modules.m11_sis.import_batch_service import ImportBatchService

        domain = await InstitutionEmailService._resolve_domain(
            db, schema_name=schema_name, override=override_domain
        )
        # Persist an explicitly-supplied domain so future operations reuse it.
        if override_domain:
            await InstitutionEmailService.set_domain(db, schema_name=schema_name, domain=domain)

        rows = await InstitutionEmailService._load(db)
        taken = {
            (r["existing_inst"] or "").strip().lower()
            for r in rows if r["existing_inst"]
        }

        assigned = skipped = conflicts = personal_backfilled = 0
        errors: list[str] = []

        for r in rows:
            if r["existing_inst"]:
                skipped += 1
                continue
            local, kind = _local_part(r)
            if not (local and str(local).strip()):
                skipped += 1
                continue
            projected = format_email(str(local), domain)
            if projected in taken:
                conflicts += 1
                errors.append(f"{r['login_email']}: {projected} already assigned — skipped")
                continue
            res = await db.execute(_WRITE_SQL, {"inst": projected, "uid": str(r["user_id"])})
            if res.rowcount and res.rowcount > 0:
                assigned += 1
                personal_backfilled += 1  # COALESCE may have been a no-op, but the row was touched
                taken.add(projected)
            else:
                # Already had an institution_email (race) — treat as skipped.
                skipped += 1

        batch_ref = None
        if assigned > 0:
            batch = await ImportBatchService.create_batch(
                imported_by=actor_user_id,
                record_type="INSTITUTION_EMAIL_BACKFILL",
                total_records=len(rows),
                success_count=assigned,
                failed_count=conflicts,
                db=db,
            )
            batch_ref = batch.batch_ref

        # No explicit commit: the _admin_db dependency's session.begin() commits
        # the whole run atomically.
        return InstitutionEmailCommitResult(
            domain=domain,
            total_users=len(rows),
            assigned=assigned,
            skipped=skipped,
            conflicts=conflicts,
            personal_backfilled=personal_backfilled,
            batch_ref=batch_ref,
            errors=errors,
        )
