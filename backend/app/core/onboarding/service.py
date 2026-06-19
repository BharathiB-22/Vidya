import csv
import io
import re
import uuid as _uuid
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.security import hash_password
from app.core.onboarding.repository import OnboardingRepository
from app.core.onboarding.schemas import (
    CSVCommitResult,
    CSVPreviewResponse,
    CSVRowResult,
    FacultySummaryMeta,
    GenerateStudentsRequest,
    GenerateStudentsResult,
    ImportUsnRange,
    ProgramAssignmentCount,
    StudentSummaryMeta,
)
from app.core.onboarding.usn_mint import MintItem, ProjectItem, mint_usns, project_usns
from app.core.onboarding.faculty_code_allocator import (
    DEFAULT_FACULTY_PREFIX as _FACULTY_CODE_PREFIX,
    FacultyCodeAllocator,
)
from app.core.onboarding.faculty_institution_email import build_faculty_email
from app.core.onboarding.faculty_role_grant_schemas import GRANTABLE_ROLES as _GRANTABLE_ROLES

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+$")


class OnboardingError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _generate_usn(prefix: str, year: int, program_code: str, seq: int, width: int) -> str:
    return f"{prefix.upper()}{year:02d}{program_code.upper()}{seq:0{width}d}"


def _generate_email(usn: str, domain: str) -> str:
    return f"{usn.lower()}@{domain.lower().strip('.')}"


class OnboardingService:

    # ------------------------------------------------------------------ #
    # File parsing helpers                                                  #
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
    def _parse_csv_rows(
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
    def _parse_excel_rows(
        content: bytes,
        required_cols: list[str],
    ) -> tuple[list[dict], str | None]:
        try:
            import openpyxl  # noqa: PLC0415
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                wb.close()
                return [], "Excel workbook has no active sheet."

            rows_iter = ws.iter_rows(values_only=True)
            header_row = next(rows_iter, None)
            if header_row is None:
                wb.close()
                return [], "Excel file has no header row."

            headers = [
                str(h).strip().lower() if h is not None else ""
                for h in header_row
            ]
            missing = [c for c in required_cols if c not in headers]
            if missing:
                wb.close()
                return [], f"Missing required columns: {', '.join(missing)}"

            rows = []
            for raw_row in rows_iter:
                if all(v is None for v in raw_row):
                    continue
                row_dict = {
                    headers[i]: str(raw_row[i]).strip() if raw_row[i] is not None else ""
                    for i in range(min(len(headers), len(raw_row)))
                }
                rows.append(row_dict)

            wb.close()
            return rows, None
        except Exception as exc:
            return [], f"Could not read Excel file: {exc}"

    @staticmethod
    def _parse_file(
        content: bytes,
        filename: str,
        required_cols: list[str],
    ) -> tuple[list[dict], str | None]:
        if filename.lower().endswith(".xlsx"):
            return OnboardingService._parse_excel_rows(content, required_cols)
        return OnboardingService._parse_csv_rows(content, required_cols)

    # ------------------------------------------------------------------ #
    # Common row validation                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate_common(
        row_num: int,
        raw: dict,
        identifier_col: str,
        seen_emails: set[str],
        seen_ids: set[str],
    ) -> CSVRowResult:
        errors: list[str] = []
        full_name  = raw.get("full_name", "")
        email      = raw.get("email", "")
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
        valid_emails = [r.email      for r in rows if r.is_valid and r.email]
        valid_ids    = [r.identifier for r in rows if r.is_valid and r.identifier]

        existing_emails = await OnboardingRepository.get_existing_emails(valid_emails, db)
        existing_ids    = await OnboardingRepository.get_existing_identifiers(valid_ids, db)

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
    # Section resolution helpers                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _validate_section_active(section_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            text("SELECT id FROM acad_sections WHERE id = :sid AND is_active = true"),
            {"sid": str(section_id)},
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def _resolve_section(
        program_code: str,
        batch_year_str: str,
        section_name: str,
        db: AsyncSession,
    ) -> UUID | None:
        try:
            batch_year = int(batch_year_str)
        except (ValueError, TypeError):
            return None

        prog_row = await db.execute(
            text(
                "SELECT id FROM acad_programs "
                "WHERE UPPER(code) = :code AND is_active = true"
            ),
            {"code": program_code.upper()},
        )
        prog_id = prog_row.scalar_one_or_none()
        if not prog_id:
            return None

        batch_row = await db.execute(
            text(
                "SELECT id FROM acad_batches "
                "WHERE program_id = :pid AND start_year = :yr AND is_active = true"
            ),
            {"pid": str(prog_id), "yr": batch_year},
        )
        batch_id = batch_row.scalar_one_or_none()
        if not batch_id:
            return None

        sem_row = await db.execute(
            text(
                "SELECT id FROM acad_semesters "
                "WHERE batch_id = :bid AND is_active = true "
                "ORDER BY number ASC LIMIT 1"
            ),
            {"bid": str(batch_id)},
        )
        sem_id = sem_row.scalar_one_or_none()
        if not sem_id:
            return None

        sec_row = await db.execute(
            text(
                "SELECT id FROM acad_sections "
                "WHERE semester_id = :sid AND UPPER(name) = :name AND is_active = true"
            ),
            {"sid": str(sem_id), "name": section_name.upper()},
        )
        return sec_row.scalar_one_or_none()

    # ------------------------------------------------------------------ #
    # USN-triple resolution helpers (Phase 1 / Step 4)                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _resolve_program_identity(
        program_id: UUID, db: AsyncSession
    ) -> tuple[str | None, str | None, str | None]:
        """Return (program_code, school_code, department_code) — school via dept."""
        row = await db.execute(
            text(
                "SELECT p.code AS program_code, sch.code AS school_code, "
                "       d.code AS department_code "
                "FROM acad_programs p "
                "LEFT JOIN acad_departments d ON d.id = p.department_id "
                "LEFT JOIN sis_schools    sch ON sch.id = d.school_id "
                "WHERE p.id = :pid"
            ),
            {"pid": str(program_id)},
        )
        m = row.mappings().one_or_none()
        if m is None:
            return None, None, None
        return m["program_code"], m["school_code"], m["department_code"]

    @staticmethod
    async def _batch_exists(program_code: str, batch_year: int, db: AsyncSession) -> bool:
        row = await db.execute(
            text(
                "SELECT 1 FROM acad_batches b "
                "JOIN acad_programs p ON p.id = b.program_id "
                "WHERE UPPER(p.code) = :code AND b.start_year = :yr LIMIT 1"
            ),
            {"code": program_code.upper(), "yr": batch_year},
        )
        return row.scalar_one_or_none() is not None

    @staticmethod
    async def _admission_year_from_section(
        section_id: UUID, db: AsyncSession
    ) -> int | None:
        """Authoritative admission year = the section's batch start_year."""
        row = await db.execute(
            text(
                "SELECT b.start_year FROM acad_sections sec "
                "JOIN acad_semesters sem ON sem.id = sec.semester_id "
                "JOIN acad_batches    b   ON b.id   = sem.batch_id "
                "WHERE sec.id = :sec"
            ),
            {"sec": str(section_id)},
        )
        val = row.scalar_one_or_none()
        return int(val) if val is not None else None

    @staticmethod
    async def _resolve_section_context(
        section_id: UUID, db: AsyncSession
    ) -> dict:
        """
        Return a dict with program/batch/semester/section UUIDs and display names
        for stamping on SisImportBatch.  Returns empty dict when section not found.
        """
        row = await db.execute(
            text(
                "SELECT p.id AS program_id, p.name AS program_name, "
                "       b.id AS batch_id,   b.name AS batch_name, "
                "       sem.id AS semester_id, sem.number AS semester_number, "
                "       sem.label AS semester_label, "
                "       sec.id AS section_id, sec.name AS section_name "
                "FROM acad_sections sec "
                "JOIN acad_semesters sem ON sem.id = sec.semester_id "
                "JOIN acad_batches   b   ON b.id   = sem.batch_id "
                "JOIN acad_programs  p   ON p.id   = b.program_id "
                "WHERE sec.id = :sid"
            ),
            {"sid": str(section_id)},
        )
        m = row.mappings().one_or_none()
        if m is None:
            return {}
        sem_name = m["semester_label"] or f"Semester {m['semester_number']}"
        return {
            "program_id":   m["program_id"],
            "program_name": m["program_name"],
            "batch_id":     m["batch_id"],
            "batch_name":   m["batch_name"],
            "semester_id":  m["semester_id"],
            "semester_name": sem_name,
            "section_id":   m["section_id"],
            "section_name": m["section_name"],
        }

    @staticmethod
    def _split_codes(raw_value: str) -> list[str]:
        """Parse a pipe/comma-delimited list of program codes (deduped, upper)."""
        parts = re.split(r"[|,]", raw_value or "")
        seen: list[str] = []
        for p in parts:
            c = p.strip().upper()
            if c and c not in seen:
                seen.append(c)
        return seen

    # ------------------------------------------------------------------ #
    # Bulk student generation                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def generate_students(
        req: GenerateStudentsRequest,
        db: AsyncSession,
        *,
        actor_user_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> GenerateStudentsResult:
        if req.section_id is not None:
            if not await OnboardingService._validate_section_active(req.section_id, db):
                raise OnboardingError(
                    "SECTION_NOT_FOUND",
                    f"Section {req.section_id} does not exist or is not active",
                )

        usns = [
            _generate_usn(req.usn_prefix, req.batch_year, req.program_code, req.start_seq + i, req.seq_width)
            for i in range(req.count)
        ]
        emails = [_generate_email(u, req.email_domain) for u in usns]

        existing_ids    = await OnboardingRepository.get_existing_identifiers(usns, db)
        existing_emails = await OnboardingRepository.get_existing_emails(emails, db)

        duplicate_usns   = [u for u in usns   if u in existing_ids]
        duplicate_emails = [e for e in emails if e in existing_emails]

        pw_hash = hash_password(req.default_password)
        rows_to_insert: list[dict] = []

        for usn, email in zip(usns, emails):
            if usn in existing_ids or email in existing_emails:
                continue
            rows_to_insert.append({
                "id":              str(_uuid.uuid4()),
                "email":           email,
                "pw_hash":         pw_hash,
                "role":            "STUDENT",
                "full_name":       usn,
                "identifier":      usn,
                "acad_program_id": None,
            })

        created = await OnboardingRepository.bulk_insert_users(rows_to_insert, db)

        enrollments_created = 0
        if req.section_id is not None and rows_to_insert:
            pairs = [(row["id"], str(req.section_id)) for row in rows_to_insert]
            enrollments_created = await OnboardingRepository.bulk_upsert_enrollments(pairs, db)

        # Record in Import History when an actor is known.
        if created > 0 and actor_user_id is not None:
            from sqlalchemy import update as _sa_update
            from app.modules.m11_sis.import_batch_service import ImportBatchService
            from app.modules.m11_sis.models import SisStudentProfile

            ctx: dict = {}
            if req.section_id is not None:
                ctx = await OnboardingService._resolve_section_context(req.section_id, db)

            batch = await ImportBatchService.create_batch(
                imported_by=actor_user_id,
                record_type="STUDENT",
                total_records=req.count,
                success_count=created,
                failed_count=req.count - created,
                db=db,
                **ctx,
            )
            created_uids = [_uuid.UUID(r["id"]) for r in rows_to_insert]
            await db.execute(
                _sa_update(SisStudentProfile)
                .where(SisStudentProfile.user_id.in_(created_uids))
                .values(import_batch_id=batch.id)
            )

        return GenerateStudentsResult(
            created=created,
            skipped=req.count - created,
            duplicate_usns=duplicate_usns,
            duplicate_emails=duplicate_emails,
            default_password=req.default_password,
            enrollments_created=enrollments_created,
        )

    # ------------------------------------------------------------------ #
    # Duplicate counter helpers                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _count_duplicates(rows: list[CSVRowResult]) -> tuple[int, int]:
        dup_file = sum(1 for r in rows if any("within this file" in e for e in r.errors))
        dup_db   = sum(1 for r in rows if any("already exists in this institution" in e for e in r.errors))
        return dup_file, dup_db

    # ------------------------------------------------------------------ #
    # Students file import                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def preview_students_csv(
        content: bytes,
        db: AsyncSession,
        *,
        filename: str = "students.csv",
        context_program_id: UUID | None = None,
        context_section_id: UUID | None = None,
    ) -> CSVPreviewResponse:
        # When a context program is supplied, program_code column is not required
        required = ["full_name", "email"]
        if context_program_id is None:
            required.append("program_code")

        raw_rows, err = OnboardingService._parse_file(content, filename, required)
        if err:
            return CSVPreviewResponse(
                total_rows=0, valid_rows=0, invalid_rows=0,
                rows=[CSVRowResult(
                    row_number=0, full_name="", email="", identifier=None,
                    is_valid=False, errors=[err],
                )],
            )

        # Fail-fast: validate context section if provided
        if context_section_id is not None:
            if not await OnboardingService._validate_section_active(context_section_id, db):
                return CSVPreviewResponse(
                    total_rows=0, valid_rows=0, invalid_rows=0,
                    rows=[CSVRowResult(
                        row_number=0, full_name="", email="", identifier=None,
                        is_valid=False,
                        errors=["Selected section does not exist or is not active"],
                    )],
                )

        seen_emails: set[str] = set()
        seen_ids:    set[str] = set()
        _program_cache: dict[str, UUID | None] = {}
        _section_cache: dict[tuple, UUID | None] = {}
        _identity_cache: dict[str, tuple] = {}   # program_id -> (program_code, school_code, dept_code)
        _year_cache: dict[str, int | None] = {}  # section_id -> admission_year

        # Referenced-but-missing structure (for summary_meta.new_*)
        _new_programs: set[str] = set()
        _new_batches: set[tuple] = set()
        _new_sections: set[tuple] = set()

        rows: list[CSVRowResult] = []
        for i, raw in enumerate(raw_rows):
            row = OnboardingService._validate_common(i + 1, raw, "identifier", seen_emails, seen_ids)

            # Program resolution
            if context_program_id is not None:
                row.acad_program_id  = context_program_id
                row.program_resolved = True
            else:
                prog_code = raw.get("program_code", "").strip()
                if not prog_code:
                    row.errors.append("program_code is required")
                    row.is_valid = False
                else:
                    if prog_code.upper() not in _program_cache:
                        _program_cache[prog_code.upper()] = await OnboardingRepository.resolve_program_by_code(
                            prog_code, db
                        )
                    prog_id = _program_cache[prog_code.upper()]
                    if prog_id is not None:
                        row.acad_program_id  = prog_id
                        row.program_resolved = True
                    else:
                        row.errors.append(f"Program not found: '{prog_code}'")
                        row.is_valid = False
                        _new_programs.add(prog_code.upper())

            # Section resolution
            if context_section_id is not None:
                row.section_id       = context_section_id
                row.section_resolved = True
            else:
                batch_yr_str = raw.get("batch_year",   "").strip()
                sec_name     = raw.get("section_name", "").strip()
                prog_code    = raw.get("program_code", "").strip()
                if prog_code and batch_yr_str and sec_name:
                    cache_key = (prog_code.upper(), batch_yr_str, sec_name.upper())
                    if cache_key not in _section_cache:
                        _section_cache[cache_key] = await OnboardingService._resolve_section(
                            prog_code, batch_yr_str, sec_name, db
                        )
                    resolved = _section_cache[cache_key]
                    if resolved is not None:
                        row.section_id       = resolved
                        row.section_resolved = True
                    else:
                        row.errors.append(
                            f"Section not found: program='{prog_code}' "
                            f"year={batch_yr_str} section='{sec_name}'"
                        )
                        row.is_valid = False
                        # Classify the gap as a missing batch vs a missing section.
                        if batch_yr_str.isdigit() and not await OnboardingService._batch_exists(
                            prog_code, int(batch_yr_str), db
                        ):
                            _new_batches.add((prog_code.upper(), int(batch_yr_str)))
                        else:
                            _new_sections.add((prog_code.upper(), batch_yr_str, sec_name.upper()))

            # USN triple derivation (school_code, admission_year, program_code).
            if row.acad_program_id is not None:
                pid_key = str(row.acad_program_id)
                if pid_key not in _identity_cache:
                    _identity_cache[pid_key] = await OnboardingService._resolve_program_identity(
                        row.acad_program_id, db
                    )
                prog_code_resolved, school_code, _dept_code = _identity_cache[pid_key]
                row.school_code = school_code

                admission_year: int | None = None
                if row.section_id is not None:
                    sec_key = str(row.section_id)
                    if sec_key not in _year_cache:
                        _year_cache[sec_key] = await OnboardingService._admission_year_from_section(
                            row.section_id, db
                        )
                    admission_year = _year_cache[sec_key]
                if admission_year is None:
                    byr = raw.get("batch_year", "").strip()
                    if byr.isdigit():
                        admission_year = int(byr)
                row.admission_year = admission_year

                if not (prog_code_resolved and school_code and admission_year is not None):
                    row.warnings.append(
                        "USN will not be auto-generated — missing school link "
                        "or admission year for this program"
                    )

            rows.append(row)

        rows = await OnboardingService._check_db_duplicates(rows, db)

        # Project USNs (read-only) for valid rows whose triple is complete.
        project_pairs: list[tuple[CSVRowResult, ProjectItem]] = []
        for row in rows:
            if not row.is_valid or row.acad_program_id is None:
                continue
            prog_code_resolved, _sc, _dc = _identity_cache.get(str(row.acad_program_id), (None, None, None))
            if prog_code_resolved and row.school_code and row.admission_year is not None:
                item = ProjectItem(
                    triple=(row.school_code, row.admission_year, prog_code_resolved),
                    full_name=row.full_name, email=row.email,
                )
                project_pairs.append((row, item))

        ranges = await project_usns(db, [it for _, it in project_pairs])
        for row, item in project_pairs:
            row.projected_usn = item.projected

        valid = sum(1 for r in rows if r.is_valid)
        dup_file, dup_db = OnboardingService._count_duplicates(rows)

        # ---- Dashboard rollup (summary_meta) ----
        schools: set[str] = set()
        departments: set[str] = set()
        programs: set[str] = set()
        batches: set[tuple] = set()
        sections: set[str] = set()
        projected_count = 0
        for r in rows:
            if not r.is_valid:
                continue
            if r.acad_program_id is not None:
                programs.add(str(r.acad_program_id))
                _pc, sc, dc = _identity_cache.get(str(r.acad_program_id), (None, None, None))
                if sc:
                    schools.add(sc.upper())
                if dc:
                    departments.add(dc.upper())
                if r.admission_year is not None:
                    batches.add((str(r.acad_program_id), r.admission_year))
            if r.section_id is not None:
                sections.add(str(r.section_id))
            if r.projected_usn:
                projected_count += 1

        summary = StudentSummaryMeta(
            total_rows=len(rows), valid_rows=valid, invalid_rows=len(rows) - valid,
            schools_count=len(schools), departments_count=len(departments),
            programs_count=len(programs), batches_count=len(batches),
            sections_count=len(sections),
            projected_usns_count=projected_count,
            # A student CSV references existing structure; schools/departments are
            # always reached via an existing program, so they are never "new".
            new_schools=0, new_departments=0,
            new_programs=len(_new_programs),
            new_batches=len(_new_batches),
            new_sections=len(_new_sections),
        )

        return CSVPreviewResponse(
            total_rows=len(rows),
            valid_rows=valid,
            invalid_rows=len(rows) - valid,
            duplicate_in_file=dup_file,
            duplicate_in_db=dup_db,
            rows=rows,
            projected_usn_ranges=[
                ImportUsnRange(
                    school_code=r.school_code, admission_year=r.admission_year,
                    program_code=r.program_code, count=r.count,
                    first_usn=r.first_usn, last_usn=r.last_usn,
                )
                for r in ranges
            ],
            summary_meta=summary.model_dump(),
        )

    @staticmethod
    async def commit_students_csv(
        content: bytes,
        default_password: str,
        db: AsyncSession,
        *,
        filename: str = "students.csv",
        context_program_id: UUID | None = None,
        context_section_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> CSVCommitResult:
        preview = await OnboardingService.preview_students_csv(
            content, db,
            filename=filename,
            context_program_id=context_program_id,
            context_section_id=context_section_id,
        )
        pw_hash = hash_password(default_password)

        rows_to_insert: list[dict] = []
        enroll_pairs:   list[tuple[str, str]] = []
        mint_items:     list[MintItem] = []
        _identity_cache: dict[str, tuple] = {}

        for r in preview.rows:
            if not r.is_valid:
                continue
            uid_obj = _uuid.uuid4()
            uid = str(uid_obj)
            rows_to_insert.append({
                "id":              uid,
                "email":           r.email,
                "pw_hash":         pw_hash,
                "role":            "STUDENT",
                "full_name":       r.full_name,
                "identifier":      r.identifier,
                "acad_program_id": str(r.acad_program_id) if r.acad_program_id else None,
            })
            if r.section_resolved and r.section_id is not None:
                enroll_pairs.append((uid, str(r.section_id)))

            # Queue for USN minting when the triple is complete.
            if r.acad_program_id is not None and r.school_code and r.admission_year is not None:
                pid_key = str(r.acad_program_id)
                if pid_key not in _identity_cache:
                    _identity_cache[pid_key] = await OnboardingService._resolve_program_identity(
                        r.acad_program_id, db
                    )
                prog_code_resolved, _sc, _dc = _identity_cache[pid_key]
                if prog_code_resolved:
                    mint_items.append(MintItem(
                        triple=(r.school_code, r.admission_year, prog_code_resolved),
                        user_id=uid_obj, full_name=r.full_name, email=r.email,
                    ))

        created = await OnboardingRepository.bulk_insert_users(rows_to_insert, db)
        enrollments_created = await OnboardingRepository.bulk_upsert_enrollments(enroll_pairs, db)

        # Mint USNs via UsnAllocator (only target users just created in this run).
        usn_map, usns_assigned = await mint_usns(db, mint_items)

        # Auto-generate institution emails for students that received a USN.
        # Silently skips when no domain is configured — the backfill endpoint
        # handles the catch-up once the admin sets a domain.
        institution_emails_assigned = 0
        if schema_name and usn_map:
            from sqlalchemy import text as _text
            from app.core.onboarding.institution_email_service import format_email as _fmt_email
            dom_row = await db.execute(
                _text("SELECT institution_domain FROM public.tenants WHERE schema_name = :s"),
                {"s": schema_name},
            )
            domain = dom_row.scalar_one_or_none()
            if domain:
                domain = domain.strip().lower().lstrip("@")
                for user_id, usn in usn_map.items():
                    inst_email = _fmt_email(usn, domain)
                    res = await db.execute(
                        _text(
                            "UPDATE users SET institution_email = :inst,"
                            " personal_email = COALESCE(personal_email, email)"
                            " WHERE id = :uid AND institution_email IS NULL"
                        ),
                        {"inst": inst_email, "uid": str(user_id)},
                    )
                    if res.rowcount and res.rowcount > 0:
                        institution_emails_assigned += 1

        # Audit trail: record this import as a batch and stamp it onto the
        # student profiles created in this run.  Academic context (program/batch/
        # semester/section) is resolved from context_section_id when available.
        if created > 0 and actor_user_id is not None:
            from sqlalchemy import update as _sa_update
            from app.modules.m11_sis.import_batch_service import ImportBatchService
            from app.modules.m11_sis.models import SisStudentProfile

            ctx: dict = {}
            if context_section_id is not None:
                ctx = await OnboardingService._resolve_section_context(context_section_id, db)

            batch = await ImportBatchService.create_batch(
                imported_by=actor_user_id,
                record_type="STUDENT",
                total_records=preview.total_rows,
                success_count=created,
                failed_count=preview.invalid_rows,
                source_filename=filename,
                db=db,
                **ctx,
            )
            created_uids = [_uuid.UUID(r["id"]) for r in rows_to_insert]
            await db.execute(
                _sa_update(SisStudentProfile)
                .where(SisStudentProfile.user_id.in_(created_uids))
                .values(import_batch_id=batch.id)
            )

        return CSVCommitResult(
            total=preview.total_rows,
            created=created,
            skipped=preview.invalid_rows,
            errors=[
                f"Row {r.row_number}: {', '.join(r.errors)}"
                for r in preview.rows
                if not r.is_valid
            ],
            enrollments_created=enrollments_created,
            usns_assigned=usns_assigned,
            institution_emails_assigned=institution_emails_assigned,
        )

    # ------------------------------------------------------------------ #
    # Faculty file import                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def preview_faculty_csv(
        content: bytes,
        db: AsyncSession,
        *,
        filename: str = "faculty.csv",
    ) -> CSVPreviewResponse:
        # Phase 1.5: employee_id is no longer collected; the canonical login
        # column is `personal_email` (legacy `email` header still accepted).
        raw_rows, err = OnboardingService._parse_file(content, filename, required_cols=["full_name"])
        if err:
            return CSVPreviewResponse(
                total_rows=0, valid_rows=0, invalid_rows=0,
                rows=[CSVRowResult(
                    row_number=0, full_name="", email="", identifier=None,
                    is_valid=False, errors=[err],
                )],
            )
        if raw_rows and not any(k in raw_rows[0] for k in ("email", "personal_email")):
            return CSVPreviewResponse(
                total_rows=0, valid_rows=0, invalid_rows=0,
                rows=[CSVRowResult(
                    row_number=0, full_name="", email="", identifier=None,
                    is_valid=False,
                    errors=["Missing required column: 'personal_email'"],
                )],
            )

        seen_emails: set[str] = set()
        seen_ids:    set[str] = set()
        _program_cache: dict[str, UUID | None] = {}

        rows: list[CSVRowResult] = []
        for i, raw in enumerate(raw_rows):
            # personal_email is the login identity; alias the legacy `email` header.
            raw["email"] = (raw.get("email") or raw.get("personal_email") or "").strip()
            row = OnboardingService._validate_common(i + 1, raw, "employee_id", seen_emails, seen_ids)

            # Resolve optional program mappings (pipe/comma-delimited).
            codes = OnboardingService._split_codes(raw.get("program_codes", ""))
            for code in codes:
                if code not in _program_cache:
                    _program_cache[code] = await OnboardingRepository.resolve_program_by_code(code, db)
                if _program_cache[code] is not None:
                    row.resolved_program_codes.append(code)
                else:
                    row.unresolved_program_codes.append(code)
                    row.warnings.append(f"Program not found (mapping skipped): '{code}'")

            # Resolve responsibility grants (pipe/comma-delimited).
            for rc in OnboardingService._split_codes(raw.get("roles", "")):
                if rc in _GRANTABLE_ROLES:
                    row.resolved_roles.append(rc)
                else:
                    row.unresolved_roles.append(rc)
                    row.warnings.append(f"Unknown responsibility (grant skipped): '{rc}'")

            rows.append(row)

        rows = await OnboardingService._check_db_duplicates(rows, db)
        valid = sum(1 for r in rows if r.is_valid)
        dup_file, dup_db = OnboardingService._count_duplicates(rows)

        # ---- Dashboard rollup: predict the mappings/grants commit would apply ----
        unique_programs: set[str] = set()
        faculty_emails: set[str] = set()
        prog_faculty: dict[str, set[str]] = {}   # program_code -> set(faculty email)
        new_assignments = reactivated = 0
        new_role_grants = reactivated_role_grants = 0
        valid_new_rows: list[CSVRowResult] = []

        for r in rows:
            # Resolve the faculty identity this row would map to.
            faculty_id: UUID | None = None
            is_new = False
            if r.is_valid:
                is_new = True                       # brand-new faculty (created on commit)
                valid_new_rows.append(r)
                faculty_emails.add(r.email.lower())
            elif r.email:
                existing = await OnboardingService._get_user_by_email(r.email, db)
                if existing is not None and existing[1].upper() == "FACULTY":
                    faculty_id = existing[0]
                    faculty_emails.add(r.email.lower())
                else:
                    continue                        # not creatable, not existing faculty
            else:
                continue

            for code in r.resolved_program_codes:
                unique_programs.add(code)
                prog_faculty.setdefault(code, set()).add(r.email.lower())
                if is_new:
                    new_assignments += 1            # no prior state possible
                    continue
                pid = _program_cache.get(code)
                state = await OnboardingService._assignment_state(faculty_id, pid, db) if pid else "none"
                if state == "revoked":
                    reactivated += 1
                elif state == "none":
                    new_assignments += 1            # else 'active' → duplicate, skipped

            for rc in r.resolved_roles:
                if is_new:
                    new_role_grants += 1
                    continue
                gstate = await OnboardingService._grant_state(faculty_id, rc, db)
                if gstate == "revoked":
                    reactivated_role_grants += 1
                elif gstate == "none":
                    new_role_grants += 1            # else 'active' → duplicate, skipped

        # ---- Project generated identity for brand-new faculty (Phase 1.5) ----
        domain = await OnboardingService._get_institution_domain(db)
        taken = await OnboardingService._existing_institution_emails(db)
        code_start = await OnboardingService._faculty_code_effective_next(db)
        emails_projected = 0
        for idx, r in enumerate(valid_new_rows):
            r.projected_faculty_code = FacultyCodeAllocator.format_code(
                _FACULTY_CODE_PREFIX, code_start + idx
            )
            if domain:
                proj = build_faculty_email(r.full_name, domain, taken)
                if proj:
                    r.projected_institution_email = proj
                    emails_projected += 1
            else:
                r.warnings.append("No institution domain configured — institution email will be skipped")

        summary = FacultySummaryMeta(
            total_rows=len(rows), valid_rows=valid, invalid_rows=len(rows) - valid,
            faculty_count=len(faculty_emails),
            unique_programs=len(unique_programs),
            new_program_assignments=new_assignments,
            reactivated_assignments=reactivated,
            new_role_grants=new_role_grants,
            reactivated_role_grants=reactivated_role_grants,
            faculty_codes_to_assign=len(valid_new_rows),
            institution_emails_to_assign=emails_projected,
        )
        program_assignment_summary = [
            ProgramAssignmentCount(program_code=code, faculty_count=len(emails))
            for code, emails in sorted(prog_faculty.items())
        ]

        return CSVPreviewResponse(
            total_rows=len(rows),
            valid_rows=valid,
            invalid_rows=len(rows) - valid,
            duplicate_in_file=dup_file,
            duplicate_in_db=dup_db,
            rows=rows,
            summary_meta=summary.model_dump(),
            program_assignment_summary=program_assignment_summary,
        )

    @staticmethod
    async def _get_user_by_email(email: str, db: AsyncSession) -> tuple[UUID, str] | None:
        row = await db.execute(
            text("SELECT id, role FROM users WHERE LOWER(email) = :email"),
            {"email": email.lower()},
        )
        m = row.mappings().one_or_none()
        if m is None:
            return None
        return m["id"], str(m["role"])

    @staticmethod
    async def _assignment_state(faculty_id: UUID, program_id: UUID, db: AsyncSession) -> str:
        """Current mapping state for a (faculty, program) pair: active|revoked|none."""
        row = await db.execute(
            text(
                "SELECT bool_or(is_active) AS has_active, count(*) AS n "
                "FROM faculty_program_assignments "
                "WHERE faculty_user_id = :f AND program_id = :p"
            ),
            {"f": str(faculty_id), "p": str(program_id)},
        )
        m = row.mappings().one()
        if not m["n"]:
            return "none"
        return "active" if m["has_active"] else "revoked"

    @staticmethod
    async def _grant_state(faculty_id: UUID, role_code: str, db: AsyncSession) -> str:
        """Current state for a (faculty, role_code) grant: active|revoked|none."""
        row = await db.execute(
            text(
                "SELECT bool_or(is_active) AS has_active, count(*) AS n "
                "FROM faculty_role_grants "
                "WHERE faculty_user_id = :f AND role_code = :r"
            ),
            {"f": str(faculty_id), "r": role_code},
        )
        m = row.mappings().one()
        if not m["n"]:
            return "none"
        return "active" if m["has_active"] else "revoked"

    @staticmethod
    async def _get_institution_domain(db: AsyncSession) -> str | None:
        """Read this tenant's institution_domain from public.tenants.

        The _admin_db search_path is `<schema>, public`, so current_schema()
        resolves to the tenant schema that keys its public.tenants row.
        """
        row = await db.execute(
            text(
                "SELECT institution_domain FROM public.tenants "
                "WHERE schema_name = current_schema()"
            )
        )
        return row.scalar_one_or_none()

    @staticmethod
    async def _existing_institution_emails(db: AsyncSession) -> set[str]:
        """All institution emails already taken in this tenant (faculty + students)."""
        taken: set[str] = set()
        for tbl, col in (
            ("sis_faculty_profiles", "institution_email"),
            ("users", "institution_email"),
        ):
            res = await db.execute(
                text(f"SELECT {col} FROM {tbl} WHERE {col} IS NOT NULL")
            )
            taken.update((v or "").strip().lower() for v in res.scalars().all())
        return taken

    @staticmethod
    async def _faculty_code_effective_next(db: AsyncSession, prefix: str = _FACULTY_CODE_PREFIX) -> int:
        """Projection-only: the next FAC sequence number without reserving it.

        max(live counter, highest-existing-code + 1, 1).  Mint-on-commit reserves
        the real block atomically; this is advisory for the preview.
        """
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
        return max(int(counter or 1), int(existing_max or 0) + 1, 1)

    @staticmethod
    async def commit_faculty_csv(
        content: bytes,
        default_password: str,
        db: AsyncSession,
        *,
        filename: str = "faculty.csv",
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> CSVCommitResult:
        from app.core.onboarding.faculty_program_service import (
            FacultyProgramService,
            FacultyProgramServiceError,
        )
        from app.core.onboarding.faculty_role_grant_service import (
            FacultyRoleGrantService,
            FacultyRoleGrantServiceError,
        )

        preview = await OnboardingService.preview_faculty_csv(content, db, filename=filename)
        pw_hash = hash_password(default_password)

        # Create valid (new) faculty users; remember email -> new uid (ordered).
        rows_to_insert: list[dict] = []
        new_uid_by_email: dict[str, UUID] = {}
        new_rows: list[tuple[UUID, CSVRowResult]] = []
        for r in preview.rows:
            if not r.is_valid:
                continue
            uid_obj = _uuid.uuid4()
            new_uid_by_email[r.email.lower()] = uid_obj
            new_rows.append((uid_obj, r))
            rows_to_insert.append({
                "id":              str(uid_obj),
                "email":           r.email,      # personal_email is the login identity
                "pw_hash":         pw_hash,
                "role":            "FACULTY",
                "full_name":       r.full_name,
                "identifier":      None,         # employee_id no longer collected
                "acad_program_id": None,
            })
        created = await OnboardingRepository.bulk_insert_users(rows_to_insert, db)

        # personal_email = the login email for the created faculty (login unchanged).
        if rows_to_insert:
            await db.execute(
                text("UPDATE users SET personal_email = email WHERE id = ANY(:ids)"),
                {"ids": [r["id"] for r in rows_to_insert]},
            )

        # Mint faculty_code (atomic) + generate institution_email; create profiles.
        codes_assigned = inst_emails_assigned = 0
        created_uids: list[str] = []
        if new_rows:
            await FacultyCodeAllocator.seed_counter_from_existing(db, prefix=_FACULTY_CODE_PREFIX)
            codes = await FacultyCodeAllocator.allocate_codes(
                db, prefix=_FACULTY_CODE_PREFIX, count=len(new_rows)
            )
            domain = await OnboardingService._get_institution_domain(db)
            taken = await OnboardingService._existing_institution_emails(db)
            for (uid_obj, r), code in zip(new_rows, codes):
                inst_email = build_faculty_email(r.full_name, domain, taken) if domain else None
                await db.execute(
                    text(
                        "INSERT INTO sis_faculty_profiles "
                        "    (user_id, faculty_code, institution_email, is_active, lifecycle_status) "
                        "VALUES (:uid, :code, :inst, true, 'ACTIVE')"
                    ),
                    {"uid": str(uid_obj), "code": code, "inst": inst_email},
                )
                created_uids.append(str(uid_obj))
                codes_assigned += 1
                if inst_email:
                    inst_emails_assigned += 1

        errors = [
            f"Row {r.row_number}: {', '.join(r.errors)}"
            for r in preview.rows
            if not r.is_valid
        ]

        # Resolve the faculty user id for a row: brand-new, or an existing FACULTY.
        async def _resolve_faculty_uid(r: CSVRowResult) -> UUID | None:
            uid = new_uid_by_email.get(r.email.lower())
            if uid is not None:
                return uid
            existing = await OnboardingService._get_user_by_email(r.email, db)
            if existing is None or existing[1].upper() != "FACULTY":
                return None
            return existing[0]

        # Apply program mappings via FacultyProgramService.  Covers both faculty
        # just created AND existing-by-email faculty (reactivation path).
        m_created = m_reactivated = m_skipped = 0
        _prog_id_cache: dict[str, UUID | None] = {}
        _dept_id_cache: dict[str, UUID | None] = {}   # program_id -> department_id
        # First resolved program's department per faculty — used to derive the
        # faculty's home department (primary_department_id) below.
        dept_by_faculty: dict[str, UUID] = {}
        for r in preview.rows:
            if not r.resolved_program_codes:
                continue
            faculty_uid = await _resolve_faculty_uid(r)
            if faculty_uid is None:
                continue
            for code in r.resolved_program_codes:
                if code not in _prog_id_cache:
                    _prog_id_cache[code] = await OnboardingRepository.resolve_program_by_code(code, db)
                pid = _prog_id_cache[code]
                if pid is None:
                    continue
                # Remember the first resolved program's department for this faculty.
                fuid_str = str(faculty_uid)
                if fuid_str not in dept_by_faculty:
                    pid_str = str(pid)
                    if pid_str not in _dept_id_cache:
                        _dept_id_cache[pid_str] = (
                            await OnboardingRepository.resolve_department_by_program(pid, db)
                        )
                    dep = _dept_id_cache[pid_str]
                    if dep is not None:
                        dept_by_faculty[fuid_str] = dep
                try:
                    out = await FacultyProgramService.assign_program(
                        db,
                        faculty_user_id=faculty_uid,
                        program_id=pid,
                        assigned_by=actor_user_id or faculty_uid,
                        actor_role=actor_role,
                        tenant_id=tenant_id,
                        schema_name=schema_name,
                    )
                    m_reactivated += 1 if out.reactivated else 0
                    m_created += 0 if out.reactivated else 1
                except FacultyProgramServiceError as e:
                    if e.code == "DUPLICATE_ASSIGNMENT":
                        m_skipped += 1
                    else:
                        errors.append(f"Row {r.row_number}: program '{code}' — {e.message}")

        # Derive each faculty's home department (primary_department_id) from their
        # first resolved program — but ONLY when the profile has none, so a
        # Dean-set department is never overwritten (Faculty Directory Option 1).
        depts_derived = 0
        for fuid_str, dep in dept_by_faculty.items():
            res = await db.execute(
                text(
                    "UPDATE sis_faculty_profiles "
                    "SET primary_department_id = :dep, updated_at = now() "
                    "WHERE user_id = :uid AND primary_department_id IS NULL"
                ),
                {"dep": str(dep), "uid": fuid_str},
            )
            depts_derived += res.rowcount or 0

        # Apply responsibility grants via FacultyRoleGrantService (same pattern).
        g_created = g_reactivated = g_skipped = 0
        for r in preview.rows:
            if not r.resolved_roles:
                continue
            faculty_uid = await _resolve_faculty_uid(r)
            if faculty_uid is None:
                continue
            for rc in r.resolved_roles:
                try:
                    out = await FacultyRoleGrantService.grant(
                        db,
                        faculty_user_id=faculty_uid,
                        role_code=rc,
                        granted_by=actor_user_id or faculty_uid,
                        actor_role=actor_role,
                        tenant_id=tenant_id,
                        schema_name=schema_name,
                    )
                    g_reactivated += 1 if out.reactivated else 0
                    g_created += 0 if out.reactivated else 1
                except FacultyRoleGrantServiceError as e:
                    if e.code == "DUPLICATE_GRANT":
                        g_skipped += 1
                    else:
                        errors.append(f"Row {r.row_number}: responsibility '{rc}' — {e.message}")

        # Audit trail: record the faculty import batch (SIS → Import History) and
        # stamp it on the profiles just created.
        if created > 0 and actor_user_id is not None:
            from app.modules.m11_sis.import_batch_service import ImportBatchService
            batch = await ImportBatchService.create_batch(
                imported_by=actor_user_id,
                record_type="FACULTY",
                total_records=preview.total_rows,
                success_count=created,
                failed_count=preview.invalid_rows,
                source_filename=filename,
                db=db,
            )
            if created_uids:
                await db.execute(
                    text(
                        "UPDATE sis_faculty_profiles SET import_batch_id = :bid "
                        "WHERE user_id = ANY(:ids)"
                    ),
                    {"bid": str(batch.id), "ids": created_uids},
                )

        return CSVCommitResult(
            total=preview.total_rows,
            created=created,
            skipped=preview.invalid_rows,
            errors=errors,
            program_mappings_created=m_created,
            program_mappings_reactivated=m_reactivated,
            program_mappings_skipped=m_skipped,
            role_grants_created=g_created,
            role_grants_reactivated=g_reactivated,
            role_grants_skipped=g_skipped,
            faculty_codes_assigned=codes_assigned,
            faculty_institution_emails_assigned=inst_emails_assigned,
            faculty_primary_departments_derived=depts_derived,
        )
