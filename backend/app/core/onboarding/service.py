import csv
import io
import re
import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.security import hash_password
from app.core.onboarding.repository import OnboardingRepository
from app.core.onboarding.schemas import (
    CSVCommitResult,
    CSVPreviewResponse,
    CSVRowResult,
    GenerateStudentsRequest,
    GenerateStudentsResult,
)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+$")


def _generate_usn(prefix: str, year: int, program_code: str, seq: int, width: int) -> str:
    return f"{prefix.upper()}{year:02d}{program_code.upper()}{seq:0{width}d}"


def _generate_email(usn: str, domain: str) -> str:
    return f"{usn.lower()}@{domain.lower().strip('.')}"


class OnboardingService:

    # ------------------------------------------------------------------ #
    # Bulk student generation                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def generate_students(
        req: GenerateStudentsRequest,
        db: AsyncSession,
    ) -> GenerateStudentsResult:
        usns = [
            _generate_usn(req.usn_prefix, req.batch_year, req.program_code, req.start_seq + i, req.seq_width)
            for i in range(req.count)
        ]
        emails = [_generate_email(u, req.email_domain) for u in usns]

        existing_ids = await OnboardingRepository.get_existing_identifiers(usns, db)
        existing_emails = await OnboardingRepository.get_existing_emails(emails, db)

        duplicate_usns = [u for u in usns if u in existing_ids]
        duplicate_emails = [e for e in emails if e in existing_emails]

        pw_hash = hash_password(req.default_password)
        rows_to_insert: list[dict] = []

        for usn, email in zip(usns, emails):
            if usn in existing_ids or email in existing_emails:
                continue
            rows_to_insert.append({
                "id": str(_uuid.uuid4()),
                "email": email,
                "pw_hash": pw_hash,
                "role": "STUDENT",
                "full_name": usn,
                "identifier": usn,
            })

        created = await OnboardingRepository.bulk_insert_users(rows_to_insert, db)

        return GenerateStudentsResult(
            created=created,
            skipped=req.count - created,
            duplicate_usns=duplicate_usns,
            duplicate_emails=duplicate_emails,
            default_password=req.default_password,
        )

    # ------------------------------------------------------------------ #
    # CSV parsing helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _decode_csv(content: bytes) -> tuple[str, str | None]:
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return content.decode(encoding), None
            except (UnicodeDecodeError, ValueError):
                continue
        return "", "Could not decode file — please use UTF-8 or Latin-1 encoding."

    @staticmethod
    def _parse_raw_rows(
        content: bytes,
        required_cols: list[str],
    ) -> tuple[list[dict], str | None]:
        text_content, err = OnboardingService._decode_csv(content)
        if err:
            return [], err
        if not text_content.strip():
            return [], "CSV file is empty."

        reader = csv.DictReader(io.StringIO(text_content))
        if not reader.fieldnames:
            return [], "CSV has no header row."

        normalized_headers = {h.strip().lower() for h in reader.fieldnames}
        missing = [c for c in required_cols if c not in normalized_headers]
        if missing:
            return [], f"Missing required columns: {', '.join(missing)}"

        rows = []
        for raw in reader:
            rows.append({k.strip().lower(): (v.strip() if v else "") for k, v in raw.items()})
        return rows, None

    @staticmethod
    def _validate_common(
        row_num: int,
        raw: dict,
        identifier_col: str,
        seen_emails: set[str],
        seen_ids: set[str],
    ) -> CSVRowResult:
        errors: list[str] = []
        full_name = raw.get("full_name", "")
        email = raw.get("email", "")
        identifier = raw.get(identifier_col, "") or None

        if not full_name:
            errors.append("full_name is required")
        elif len(full_name) > 200:
            errors.append("full_name must be ≤ 200 characters")

        if not email:
            errors.append("email is required")
        elif not _EMAIL_RE.match(email):
            errors.append(f"'{email}' is not a valid email address")
        elif email.lower() in seen_emails:
            errors.append("duplicate email within this file")

        if identifier and identifier in seen_ids:
            errors.append(f"duplicate {identifier_col} within this file")

        if email and _EMAIL_RE.match(email):
            seen_emails.add(email.lower())
        if identifier:
            seen_ids.add(identifier)

        return CSVRowResult(
            row_number=row_num,
            full_name=full_name,
            email=email,
            identifier=identifier,
            is_valid=len(errors) == 0,
            errors=errors,
        )

    @staticmethod
    async def _check_db_duplicates(
        rows: list[CSVRowResult],
        db: AsyncSession,
    ) -> list[CSVRowResult]:
        valid_emails = [r.email for r in rows if r.is_valid and r.email]
        valid_ids = [r.identifier for r in rows if r.is_valid and r.identifier]

        existing_emails = await OnboardingRepository.get_existing_emails(valid_emails, db)
        existing_ids = await OnboardingRepository.get_existing_identifiers(valid_ids, db)

        for row in rows:
            if not row.is_valid:
                continue
            if row.email.lower() in existing_emails:
                row.errors.append("email already exists in this institution")
                row.is_valid = False
            elif row.identifier and row.identifier in existing_ids:
                row.errors.append("identifier already exists in this institution")
                row.is_valid = False
        return rows

    # ------------------------------------------------------------------ #
    # Students CSV                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def preview_students_csv(content: bytes, db: AsyncSession) -> CSVPreviewResponse:
        raw_rows, err = OnboardingService._parse_raw_rows(
            content, required_cols=["full_name", "email"]
        )
        if err:
            return CSVPreviewResponse(
                total_rows=0, valid_rows=0, invalid_rows=0,
                rows=[CSVRowResult(row_number=0, full_name="", email="", identifier=None, is_valid=False, errors=[err])],
            )

        seen_emails: set[str] = set()
        seen_ids: set[str] = set()
        rows = [
            OnboardingService._validate_common(i + 1, raw, "identifier", seen_emails, seen_ids)
            for i, raw in enumerate(raw_rows)
        ]
        rows = await OnboardingService._check_db_duplicates(rows, db)
        valid = sum(1 for r in rows if r.is_valid)
        return CSVPreviewResponse(
            total_rows=len(rows), valid_rows=valid, invalid_rows=len(rows) - valid, rows=rows
        )

    @staticmethod
    async def commit_students_csv(
        content: bytes, default_password: str, db: AsyncSession
    ) -> CSVCommitResult:
        preview = await OnboardingService.preview_students_csv(content, db)
        pw_hash = hash_password(default_password)
        rows_to_insert = [
            {
                "id": str(_uuid.uuid4()),
                "email": r.email,
                "pw_hash": pw_hash,
                "role": "STUDENT",
                "full_name": r.full_name,
                "identifier": r.identifier,
            }
            for r in preview.rows
            if r.is_valid
        ]
        created = await OnboardingRepository.bulk_insert_users(rows_to_insert, db)
        return CSVCommitResult(
            total=preview.total_rows,
            created=created,
            skipped=preview.invalid_rows,
            errors=[f"Row {r.row_number}: {', '.join(r.errors)}" for r in preview.rows if not r.is_valid],
        )

    # ------------------------------------------------------------------ #
    # Faculty CSV                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def preview_faculty_csv(content: bytes, db: AsyncSession) -> CSVPreviewResponse:
        raw_rows, err = OnboardingService._parse_raw_rows(
            content, required_cols=["full_name", "email"]
        )
        if err:
            return CSVPreviewResponse(
                total_rows=0, valid_rows=0, invalid_rows=0,
                rows=[CSVRowResult(row_number=0, full_name="", email="", identifier=None, is_valid=False, errors=[err])],
            )

        seen_emails: set[str] = set()
        seen_ids: set[str] = set()
        rows = [
            OnboardingService._validate_common(i + 1, raw, "employee_id", seen_emails, seen_ids)
            for i, raw in enumerate(raw_rows)
        ]
        rows = await OnboardingService._check_db_duplicates(rows, db)
        valid = sum(1 for r in rows if r.is_valid)
        return CSVPreviewResponse(
            total_rows=len(rows), valid_rows=valid, invalid_rows=len(rows) - valid, rows=rows
        )

    @staticmethod
    async def commit_faculty_csv(
        content: bytes, default_password: str, db: AsyncSession
    ) -> CSVCommitResult:
        preview = await OnboardingService.preview_faculty_csv(content, db)
        pw_hash = hash_password(default_password)
        rows_to_insert = [
            {
                "id": str(_uuid.uuid4()),
                "email": r.email,
                "pw_hash": pw_hash,
                "role": "FACULTY",
                "full_name": r.full_name,
                "identifier": r.identifier,
            }
            for r in preview.rows
            if r.is_valid
        ]
        created = await OnboardingRepository.bulk_insert_users(rows_to_insert, db)
        return CSVCommitResult(
            total=preview.total_rows,
            created=created,
            skipped=preview.invalid_rows,
            errors=[f"Row {r.row_number}: {', '.join(r.errors)}" for r in preview.rows if not r.is_valid],
        )
