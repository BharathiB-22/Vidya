"""
SIS Bulk Profile Import — H53 Service.

Two-phase flow:
  preview()  — parse, validate, resolve students, check USN uniqueness.
               Returns row-annotated preview with no DB writes.
  commit()   — re-runs full validation, then calls StudentDirectoryService.upsert_profile()
               per valid row.  Partial success: a per-row DirectoryServiceError is caught,
               logged, and added to the result errors list.  Other rows continue.

Audit logging and H52 notifications fire automatically through upsert_profile().
"""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.bulk_import_schemas import (
    ProfileImportCommitResult,
    ProfileImportPreviewResponse,
    ProfileImportRowResult,
)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+$")

# Columns that the import understands (beyond the required email key).
# Any column not in this list is silently ignored.
_PROFILE_COLS = {
    "usn", "admission_year", "phone",
    "address_line1", "address_city", "address_state",
    "emergency_contact_name", "emergency_contact_phone",
}


class BulkProfileImportService:

    # ------------------------------------------------------------------ #
    # File parsing — delegates to OnboardingService helpers               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_file(
        content: bytes,
        filename: str,
    ) -> tuple[list[dict], str | None]:
        from app.core.onboarding.service import OnboardingService
        return OnboardingService._parse_file(content, filename, required_cols=["email"])

    # ------------------------------------------------------------------ #
    # Per-row field parsing                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_row(
        row_num: int,
        raw: dict,
        seen_emails: set[str],
        seen_usns: set[str],
    ) -> tuple[ProfileImportRowResult, bool, bool]:
        """
        Returns (row_result, incremented_dup_email, incremented_dup_usn).
        The booleans allow the caller to maintain running counters.
        """
        errors: list[str] = []
        dup_email = False
        dup_usn   = False

        # --- email (required lookup key) ---
        email = raw.get("email", "").strip().lower()
        if not email:
            errors.append("email is required")
        elif not _EMAIL_RE.match(email):
            errors.append(f"'{email}' is not a valid email address")
        elif email in seen_emails:
            errors.append("duplicate email within this file")
            dup_email = True

        # --- usn (optional, strip + upper) ---
        usn_raw = raw.get("usn", "").strip()
        usn: str | None = usn_raw.upper() if usn_raw else None
        if usn is not None and usn in seen_usns:
            errors.append("duplicate USN within this file")
            dup_usn = True

        # --- admission_year (optional int, range-checked) ---
        admission_year: int | None = None
        yr_raw = raw.get("admission_year", "").strip()
        if yr_raw:
            try:
                admission_year = int(yr_raw)
                if not (1900 < admission_year < 2100):
                    errors.append(
                        f"admission_year {admission_year} is out of the valid range (1901–2099)"
                    )
                    admission_year = None
            except ValueError:
                errors.append(f"admission_year '{yr_raw}' must be an integer year")

        # --- optional string fields ---
        phone                   = raw.get("phone",                   "").strip() or None
        address_line1           = raw.get("address_line1",           "").strip() or None
        address_city            = raw.get("address_city",            "").strip() or None
        address_state           = raw.get("address_state",           "").strip() or None
        emergency_contact_name  = raw.get("emergency_contact_name",  "").strip() or None
        emergency_contact_phone = raw.get("emergency_contact_phone", "").strip() or None

        # --- require at least one profile field ---
        has_profile_data = any([
            usn, admission_year,
            phone, address_line1, address_city, address_state,
            emergency_contact_name, emergency_contact_phone,
        ])
        if not errors and not has_profile_data:
            errors.append(
                "no profile fields provided — include at least one of: "
                "usn, admission_year, phone, address, emergency_contact"
            )

        # Track seen values (only for valid new entries)
        if email and _EMAIL_RE.match(email) and email not in seen_emails:
            seen_emails.add(email)
        if usn and usn not in seen_usns:
            seen_usns.add(usn)

        return (
            ProfileImportRowResult(
                row_number=row_num,
                email=email,
                student_name=None,
                student_id=None,
                usn=usn,
                admission_year=admission_year,
                phone=phone,
                address_line1=address_line1,
                address_city=address_city,
                address_state=address_state,
                emergency_contact_name=emergency_contact_name,
                emergency_contact_phone=emergency_contact_phone,
                is_valid=len(errors) == 0,
                errors=errors,
            ),
            dup_email,
            dup_usn,
        )

    # ------------------------------------------------------------------ #
    # DB resolution — batch lookups                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _resolve_students(
        rows: list[ProfileImportRowResult],
        db: AsyncSession,
    ) -> tuple[list[ProfileImportRowResult], int]:
        """
        Fills in student_id and student_name for each valid row by matching email
        to an active STUDENT user.  Returns (updated_rows, not_found_count).
        """
        valid_emails = [r.email for r in rows if r.is_valid and r.email]
        if not valid_emails:
            return rows, 0

        result = await db.execute(
            text(
                "SELECT id, full_name, role, is_active "
                "FROM users "
                "WHERE LOWER(email) = ANY(:emails)"
            ),
            {"emails": valid_emails},
        )
        user_map: dict[str, dict] = {
            str(r["full_name"]).lower(): r  # temporary — we key by email below
            for r in result.mappings().all()
        }
        # Re-build keyed by LOWER(email)
        result2 = await db.execute(
            text(
                "SELECT id, full_name, role, is_active, LOWER(email) AS lower_email "
                "FROM users "
                "WHERE LOWER(email) = ANY(:emails)"
            ),
            {"emails": valid_emails},
        )
        email_map: dict[str, dict] = {
            row["lower_email"]: dict(row) for row in result2.mappings().all()
        }

        not_found = 0
        for row in rows:
            if not row.is_valid:
                continue
            user = email_map.get(row.email)
            if user is None:
                row.errors.append("no student account found with this email")
                row.is_valid = False
                not_found += 1
            elif user["role"] != "STUDENT":
                row.errors.append(
                    f"this account has role '{user['role']}' — only STUDENT accounts can be updated"
                )
                row.is_valid = False
                not_found += 1
            elif not user["is_active"]:
                row.errors.append("this student account is inactive")
                row.is_valid = False
                not_found += 1
            else:
                row.student_id   = UUID(str(user["id"]))
                row.student_name = user["full_name"]

        return rows, not_found

    @staticmethod
    async def _check_usn_db_uniqueness(
        rows: list[ProfileImportRowResult],
        db: AsyncSession,
    ) -> tuple[list[ProfileImportRowResult], int]:
        """
        For each valid row that carries a USN, verify it is not already assigned
        to a *different* student in the DB.  Returns (updated_rows, dup_usn_db_count).
        """
        usn_rows = [(r.usn, r.student_id) for r in rows if r.is_valid and r.usn]
        if not usn_rows:
            return rows, 0

        file_usns = [u for u, _ in usn_rows]
        result = await db.execute(
            text(
                "SELECT usn, user_id "
                "FROM sis_student_profiles "
                "WHERE usn = ANY(:usns)"
            ),
            {"usns": file_usns},
        )
        db_usn_map: dict[str, str] = {
            row["usn"]: str(row["user_id"]) for row in result.mappings().all()
        }

        dup_count = 0
        for row in rows:
            if not row.is_valid or not row.usn:
                continue
            existing_owner = db_usn_map.get(row.usn)
            if existing_owner is not None and existing_owner != str(row.student_id):
                row.errors.append(
                    f"USN '{row.usn}' is already assigned to a different student"
                )
                row.is_valid = False
                dup_count += 1

        return rows, dup_count

    # ------------------------------------------------------------------ #
    # Preview                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def preview(
        content: bytes,
        db: AsyncSession,
        *,
        filename: str = "students.csv",
    ) -> ProfileImportPreviewResponse:
        raw_rows, parse_err = BulkProfileImportService._parse_file(content, filename)
        if parse_err:
            return ProfileImportPreviewResponse(
                total_rows=0,
                valid_rows=0,
                invalid_rows=0,
                rows=[ProfileImportRowResult(
                    row_number=0,
                    email="",
                    is_valid=False,
                    errors=[parse_err],
                )],
            )

        seen_emails: set[str] = set()
        seen_usns:   set[str] = set()
        dup_email_count = 0
        dup_usn_file_count = 0
        rows: list[ProfileImportRowResult] = []

        for i, raw in enumerate(raw_rows):
            row, is_dup_email, is_dup_usn = BulkProfileImportService._parse_row(
                i + 1, raw, seen_emails, seen_usns
            )
            if is_dup_email:
                dup_email_count += 1
            if is_dup_usn:
                dup_usn_file_count += 1
            rows.append(row)

        rows, not_found = await BulkProfileImportService._resolve_students(rows, db)
        rows, dup_usn_db = await BulkProfileImportService._check_usn_db_uniqueness(rows, db)

        valid = sum(1 for r in rows if r.is_valid)
        return ProfileImportPreviewResponse(
            total_rows=len(rows),
            valid_rows=valid,
            invalid_rows=len(rows) - valid,
            not_found_in_db=not_found,
            duplicate_email_in_file=dup_email_count,
            duplicate_usn_in_file=dup_usn_file_count,
            duplicate_usn_in_db=dup_usn_db,
            rows=rows,
        )

    # ------------------------------------------------------------------ #
    # Commit                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def commit(
        content: bytes,
        db: AsyncSession,
        *,
        filename: str = "students.csv",
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
    ) -> ProfileImportCommitResult:
        from app.modules.m11_sis.directory_schemas import StudentProfileUpsert
        from app.modules.m11_sis.directory_service import (
            DirectoryServiceError,
            StudentDirectoryService,
        )

        # Always re-validate — never trust the client to re-send the same file
        preview = await BulkProfileImportService.preview(content, db, filename=filename)

        updated = 0
        row_errors: list[str] = []

        for row in preview.rows:
            if not row.is_valid or row.student_id is None:
                if row.errors:
                    row_errors.append(
                        f"Row {row.row_number} ({row.email}): {', '.join(row.errors)}"
                    )
                continue

            body = StudentProfileUpsert(
                usn=row.usn,
                admission_year=row.admission_year,
                phone=row.phone,
                address_line1=row.address_line1,
                address_city=row.address_city,
                address_state=row.address_state,
                emergency_contact_name=row.emergency_contact_name,
                emergency_contact_phone=row.emergency_contact_phone,
            )

            try:
                await StudentDirectoryService.upsert_profile(
                    row.student_id,
                    body,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    tenant_id=tenant_id,
                    schema_name=schema_name,
                    db=db,
                )
                updated += 1
            except DirectoryServiceError as exc:
                row_errors.append(
                    f"Row {row.row_number} ({row.email}): {exc.message}"
                )
            except Exception as exc:
                row_errors.append(
                    f"Row {row.row_number} ({row.email}): unexpected error — {exc}"
                )

        skipped = preview.total_rows - updated
        return ProfileImportCommitResult(
            total=preview.total_rows,
            updated=updated,
            skipped=skipped,
            errors=row_errors,
        )
