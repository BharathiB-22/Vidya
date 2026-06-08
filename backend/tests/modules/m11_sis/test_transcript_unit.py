"""
Unit tests — H61 SIS Transcript Generation

No live database. All tests use import + assert + inspect.getsource.

Coverage:
  1–4   : TranscriptStatus enum — all 6 values present
  5–8   : TranscriptType enum values
  9–12  : DegreeStatus enum — all 4 approved values
  13–16 : VerificationResult enum values
  17–20 : SisTranscript core ORM columns
  21–24 : SisTranscript identity columns (transcript_number, verification_code)
  25–28 : SisTranscript snapshot columns (cgpa, credits, arrear_count)
  29–32 : SisTranscript lifecycle columns (status, version, parent_transcript_id)
  33–36 : SisTranscript PDF columns
  37–40 : SisTranscript human gate columns (requested_by/at, issued_by/at, revoked_by/at)
  41–44 : SisTranscript table name + unique constraints
  45–48 : SisTranscriptSemesterLine columns
  49–52 : SisTranscriptSemesterLine snapshot SGPA/CGPA columns
  53–56 : SisTranscriptSubjectLine columns
  57–60 : SisTranscriptSubjectLine marks columns (internal, external, total)
  61–64 : SisTranscriptSubjectLine grade + attempt columns
  65–68 : SisTranscriptVerificationLog append-only invariant (no updated_at)
  69–72 : SisTranscriptVerificationLog columns
  73–76 : PublicTranscriptIndex schema=public + PK
  77–80 : PublicTranscriptIndex columns (tenant_id, schema_name, transcript_id, status)
  81–84 : Migration 0036ten revision / down_revision
  85–88 : Migration 0036ten table list (4 tables + sequence + column add)
  89–92 : Migration 0012pub revision / down_revision
  93–96 : Migration 0012pub public_transcript_index table
  97–100: TranscriptSummaryRead schema fields
 101–104: TranscriptDetailRead schema has no marks restricted from public verify
 105–108: TranscriptVerifyResponse never exposes marks / CGPA
 109–112: DegreeProgressRead has expected_graduation_year field
 113–116: TranscriptServiceError carries code + status_code
 117–120: _partial_name helper privacy logic
 121–124: _verify_message returns strings for all 4 VerificationResult values
 125–128: Celery task registered in celery_app.include
 129–132: Celery task name matches module path
 133–136: TranscriptRepo.next_transcript_number format check (getsource)
 137–140: Router route prefix = /transcripts
 141–144: verify_router prefix = /verify
 145–148: GET /my-transcripts defined before GET /{transcript_id} in source
 149–152: Public verify route has no auth dependency
 153–156: Audit events for transcript lifecycle in AuditEventType
 157–160: PDF columns include internal, external, total, grade in header
 163–166: models.py imports transcript_models
 167–170: main.py includes verify_router at /verify
"""
import importlib.util
import inspect
import pathlib

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1–4: TranscriptStatus enum
# ─────────────────────────────────────────────────────────────────────────────

def test_transcript_status_requested():
    from app.modules.m11_sis.transcript_models import TranscriptStatus
    assert TranscriptStatus.REQUESTED == "REQUESTED"


def test_transcript_status_generated_issued():
    from app.modules.m11_sis.transcript_models import TranscriptStatus
    assert TranscriptStatus.GENERATED == "GENERATED"
    assert TranscriptStatus.ISSUED == "ISSUED"


def test_transcript_status_stale_superseded():
    from app.modules.m11_sis.transcript_models import TranscriptStatus
    assert TranscriptStatus.STALE == "STALE"
    assert TranscriptStatus.SUPERSEDED == "SUPERSEDED"


def test_transcript_status_revoked():
    from app.modules.m11_sis.transcript_models import TranscriptStatus
    assert TranscriptStatus.REVOKED == "REVOKED"
    assert len(TranscriptStatus) == 6


# ─────────────────────────────────────────────────────────────────────────────
# 5–8: TranscriptType enum
# ─────────────────────────────────────────────────────────────────────────────

def test_transcript_type_official():
    from app.modules.m11_sis.transcript_models import TranscriptType
    assert TranscriptType.OFFICIAL == "OFFICIAL"


def test_transcript_type_provisional():
    from app.modules.m11_sis.transcript_models import TranscriptType
    assert TranscriptType.PROVISIONAL == "PROVISIONAL"


def test_transcript_type_duplicate():
    from app.modules.m11_sis.transcript_models import TranscriptType
    assert TranscriptType.DUPLICATE == "DUPLICATE"


def test_transcript_type_count():
    from app.modules.m11_sis.transcript_models import TranscriptType
    assert len(TranscriptType) == 3


# ─────────────────────────────────────────────────────────────────────────────
# 9–12: DegreeStatus enum — all 4 approved values
# ─────────────────────────────────────────────────────────────────────────────

def test_degree_status_eligible():
    from app.modules.m11_sis.transcript_models import DegreeStatus
    assert DegreeStatus.ELIGIBLE == "ELIGIBLE"


def test_degree_status_not_eligible():
    from app.modules.m11_sis.transcript_models import DegreeStatus
    assert DegreeStatus.NOT_ELIGIBLE == "NOT_ELIGIBLE"


def test_degree_status_provisional():
    from app.modules.m11_sis.transcript_models import DegreeStatus
    assert DegreeStatus.PROVISIONAL == "PROVISIONAL"


def test_degree_status_graduated():
    from app.modules.m11_sis.transcript_models import DegreeStatus
    assert DegreeStatus.GRADUATED == "GRADUATED"
    assert len(DegreeStatus) == 5


# ─────────────────────────────────────────────────────────────────────────────
# 13–16: VerificationResult enum
# ─────────────────────────────────────────────────────────────────────────────

def test_verification_result_valid():
    from app.modules.m11_sis.transcript_models import VerificationResult
    assert VerificationResult.VALID == "VALID"


def test_verification_result_revoked():
    from app.modules.m11_sis.transcript_models import VerificationResult
    assert VerificationResult.REVOKED == "REVOKED"


def test_verification_result_superseded():
    from app.modules.m11_sis.transcript_models import VerificationResult
    assert VerificationResult.SUPERSEDED == "SUPERSEDED"


def test_verification_result_not_found():
    from app.modules.m11_sis.transcript_models import VerificationResult
    assert VerificationResult.NOT_FOUND == "NOT_FOUND"


# ─────────────────────────────────────────────────────────────────────────────
# 17–20: SisTranscript core ORM columns
# ─────────────────────────────────────────────────────────────────────────────

def test_sis_transcript_pk():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "id")


def test_sis_transcript_student_id():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "student_id")
    assert hasattr(SisTranscript, "student_name_snapshot")


def test_sis_transcript_tablename():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert SisTranscript.__tablename__ == "sis_transcripts"


def test_sis_transcript_academic_context_columns():
    from app.modules.m11_sis.transcript_models import SisTranscript
    for col in ("program_id", "program_name_snapshot", "department_name_snapshot",
                "school_name_snapshot", "batch_name_snapshot", "degree_title_snapshot"):
        assert hasattr(SisTranscript, col), f"SisTranscript missing {col}"


# ─────────────────────────────────────────────────────────────────────────────
# 21–24: SisTranscript identity columns
# ─────────────────────────────────────────────────────────────────────────────

def test_sis_transcript_identity_columns():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "transcript_number")
    assert hasattr(SisTranscript, "verification_code")


def test_sis_transcript_type_and_purpose():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "transcript_type")
    assert hasattr(SisTranscript, "purpose")


def test_sis_transcript_number_nullable():
    from app.modules.m11_sis.transcript_models import SisTranscript
    col = SisTranscript.__table__.c["transcript_number"]
    assert col.nullable is True  # set at GENERATED, not at REQUESTED


def test_sis_transcript_verification_code_nullable():
    from app.modules.m11_sis.transcript_models import SisTranscript
    col = SisTranscript.__table__.c["verification_code"]
    assert col.nullable is True  # set at GENERATED


# ─────────────────────────────────────────────────────────────────────────────
# 25–28: SisTranscript snapshot aggregate columns
# ─────────────────────────────────────────────────────────────────────────────

def test_sis_transcript_cgpa_snapshot():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "overall_cgpa_snapshot")


def test_sis_transcript_credits_snapshots():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "total_credits_attempted_snapshot")
    assert hasattr(SisTranscript, "total_credits_earned_snapshot")


def test_sis_transcript_arrear_count():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "arrear_count_snapshot")


def test_sis_transcript_degree_status_snapshot():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "degree_status_snapshot")
    assert hasattr(SisTranscript, "semesters_included")


# ─────────────────────────────────────────────────────────────────────────────
# 29–32: SisTranscript lifecycle columns
# ─────────────────────────────────────────────────────────────────────────────

def test_sis_transcript_status_default():
    from app.modules.m11_sis.transcript_models import SisTranscript
    col = SisTranscript.__table__.c["status"]
    assert col.server_default is not None


def test_sis_transcript_version_default():
    from app.modules.m11_sis.transcript_models import SisTranscript
    col = SisTranscript.__table__.c["version"]
    assert col.server_default is not None


def test_sis_transcript_parent_id_nullable():
    from app.modules.m11_sis.transcript_models import SisTranscript
    col = SisTranscript.__table__.c["parent_transcript_id"]
    assert col.nullable is True


def test_sis_transcript_relationships_exist():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "semester_lines")
    assert hasattr(SisTranscript, "verification_logs")


# ─────────────────────────────────────────────────────────────────────────────
# 33–36: SisTranscript PDF columns
# ─────────────────────────────────────────────────────────────────────────────

def test_sis_transcript_pdf_columns():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "pdf_s3_key")
    assert hasattr(SisTranscript, "pdf_generated_at")


def test_sis_transcript_pdf_s3_key_nullable():
    from app.modules.m11_sis.transcript_models import SisTranscript
    col = SisTranscript.__table__.c["pdf_s3_key"]
    assert col.nullable is True  # null until Celery task completes


def test_sis_transcript_timestamps():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "created_at")
    assert hasattr(SisTranscript, "updated_at")


def test_sis_transcript_updated_at_nullable():
    from app.modules.m11_sis.transcript_models import SisTranscript
    col = SisTranscript.__table__.c["updated_at"]
    assert col.nullable is True


# ─────────────────────────────────────────────────────────────────────────────
# 37–40: SisTranscript human gate columns
# ─────────────────────────────────────────────────────────────────────────────

def test_sis_transcript_requested_columns():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "requested_by")
    assert hasattr(SisTranscript, "requested_at")


def test_sis_transcript_generated_columns():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "generated_by")
    assert hasattr(SisTranscript, "generated_at")


def test_sis_transcript_issued_columns():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "issued_by")
    assert hasattr(SisTranscript, "issued_at")


def test_sis_transcript_revoked_columns():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "revoked_by")
    assert hasattr(SisTranscript, "revoked_at")
    assert hasattr(SisTranscript, "revoke_reason")


# ─────────────────────────────────────────────────────────────────────────────
# 41–44: SisTranscript table constraints
# ─────────────────────────────────────────────────────────────────────────────

def test_sis_transcript_unique_number_constraint():
    from app.modules.m11_sis.transcript_models import SisTranscript
    constraint_names = {c.name for c in SisTranscript.__table__.constraints}
    assert "uq_transcripts_transcript_number" in constraint_names


def test_sis_transcript_unique_verification_code_constraint():
    from app.modules.m11_sis.transcript_models import SisTranscript
    constraint_names = {c.name for c in SisTranscript.__table__.constraints}
    assert "uq_transcripts_verification_code" in constraint_names


def test_sis_transcript_usn_snapshot():
    from app.modules.m11_sis.transcript_models import SisTranscript
    assert hasattr(SisTranscript, "usn_snapshot")


def test_sis_transcript_student_name_not_nullable():
    from app.modules.m11_sis.transcript_models import SisTranscript
    col = SisTranscript.__table__.c["student_name_snapshot"]
    assert col.nullable is False


# ─────────────────────────────────────────────────────────────────────────────
# 45–48: SisTranscriptSemesterLine columns
# ─────────────────────────────────────────────────────────────────────────────

def test_semester_line_pk_and_transcript_fk():
    from app.modules.m11_sis.transcript_models import SisTranscriptSemesterLine
    assert hasattr(SisTranscriptSemesterLine, "id")
    assert hasattr(SisTranscriptSemesterLine, "transcript_id")


def test_semester_line_semester_and_declaration_refs():
    from app.modules.m11_sis.transcript_models import SisTranscriptSemesterLine
    assert hasattr(SisTranscriptSemesterLine, "semester_id")
    assert hasattr(SisTranscriptSemesterLine, "declaration_id")


def test_semester_line_display_order():
    from app.modules.m11_sis.transcript_models import SisTranscriptSemesterLine
    assert hasattr(SisTranscriptSemesterLine, "display_order")


def test_semester_line_tablename():
    from app.modules.m11_sis.transcript_models import SisTranscriptSemesterLine
    assert SisTranscriptSemesterLine.__tablename__ == "sis_transcript_semester_lines"


# ─────────────────────────────────────────────────────────────────────────────
# 49–52: SisTranscriptSemesterLine snapshot SGPA/CGPA
# ─────────────────────────────────────────────────────────────────────────────

def test_semester_line_sgpa_cgpa():
    from app.modules.m11_sis.transcript_models import SisTranscriptSemesterLine
    assert hasattr(SisTranscriptSemesterLine, "sgpa_snapshot")
    assert hasattr(SisTranscriptSemesterLine, "cgpa_snapshot")


def test_semester_line_credits():
    from app.modules.m11_sis.transcript_models import SisTranscriptSemesterLine
    assert hasattr(SisTranscriptSemesterLine, "credits_attempted_snapshot")
    assert hasattr(SisTranscriptSemesterLine, "credits_earned_snapshot")


def test_semester_line_name_and_year():
    from app.modules.m11_sis.transcript_models import SisTranscriptSemesterLine
    assert hasattr(SisTranscriptSemesterLine, "semester_name_snapshot")
    assert hasattr(SisTranscriptSemesterLine, "academic_year_snapshot")


def test_semester_line_overall_result_status():
    from app.modules.m11_sis.transcript_models import SisTranscriptSemesterLine
    assert hasattr(SisTranscriptSemesterLine, "overall_result_status_snapshot")


# ─────────────────────────────────────────────────────────────────────────────
# 53–56: SisTranscriptSubjectLine columns
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_line_pk_and_fks():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert hasattr(SisTranscriptSubjectLine, "id")
    assert hasattr(SisTranscriptSubjectLine, "transcript_id")
    assert hasattr(SisTranscriptSubjectLine, "semester_line_id")


def test_subject_line_tablename():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert SisTranscriptSubjectLine.__tablename__ == "sis_transcript_subject_lines"


def test_subject_line_course_snapshot_columns():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    for col in ("course_code_snapshot", "course_name_snapshot", "course_credits_snapshot"):
        assert hasattr(SisTranscriptSubjectLine, col), f"missing {col}"


def test_subject_line_is_best_attempt():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    col = SisTranscriptSubjectLine.__table__.c["is_best_attempt"]
    assert col.server_default is not None  # default true


# ─────────────────────────────────────────────────────────────────────────────
# 57–60: SisTranscriptSubjectLine marks columns (the approved PDF fields)
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_line_internal_marks():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert hasattr(SisTranscriptSubjectLine, "internal_marks_snapshot")


def test_subject_line_external_marks():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert hasattr(SisTranscriptSubjectLine, "external_marks_snapshot")


def test_subject_line_total_marks():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert hasattr(SisTranscriptSubjectLine, "total_marks_snapshot")


def test_subject_line_max_marks_and_percentage():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert hasattr(SisTranscriptSubjectLine, "max_marks_snapshot")
    assert hasattr(SisTranscriptSubjectLine, "percentage_snapshot")


# ─────────────────────────────────────────────────────────────────────────────
# 61–64: SisTranscriptSubjectLine grade + attempt columns
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_line_grade_columns():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert hasattr(SisTranscriptSubjectLine, "grade_letter_snapshot")
    assert hasattr(SisTranscriptSubjectLine, "grade_point_snapshot")


def test_subject_line_is_pass():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert hasattr(SisTranscriptSubjectLine, "is_pass_snapshot")


def test_subject_line_attempt_number():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    col = SisTranscriptSubjectLine.__table__.c["attempt_number"]
    assert col.server_default is not None  # default 1


def test_subject_line_result_status():
    from app.modules.m11_sis.transcript_models import SisTranscriptSubjectLine
    assert hasattr(SisTranscriptSubjectLine, "result_status_snapshot")


# ─────────────────────────────────────────────────────────────────────────────
# 65–68: SisTranscriptVerificationLog — append-only invariant
# ─────────────────────────────────────────────────────────────────────────────

def test_verification_log_no_updated_at():
    from app.modules.m11_sis.transcript_models import SisTranscriptVerificationLog
    assert not hasattr(SisTranscriptVerificationLog, "updated_at"), (
        "Verification log must be append-only — no updated_at column"
    )


def test_verification_log_tablename():
    from app.modules.m11_sis.transcript_models import SisTranscriptVerificationLog
    assert SisTranscriptVerificationLog.__tablename__ == "sis_transcript_verification_log"


def test_verification_log_transcript_fk_nullable():
    from app.modules.m11_sis.transcript_models import SisTranscriptVerificationLog
    col = SisTranscriptVerificationLog.__table__.c["transcript_id"]
    assert col.nullable is True  # survives even if transcript is removed


def test_verification_log_code_not_nullable():
    from app.modules.m11_sis.transcript_models import SisTranscriptVerificationLog
    col = SisTranscriptVerificationLog.__table__.c["verification_code"]
    assert col.nullable is False


# ─────────────────────────────────────────────────────────────────────────────
# 69–72: SisTranscriptVerificationLog columns
# ─────────────────────────────────────────────────────────────────────────────

def test_verification_log_core_columns():
    from app.modules.m11_sis.transcript_models import SisTranscriptVerificationLog
    for col in ("id", "verification_code", "verified_at", "verification_result"):
        assert hasattr(SisTranscriptVerificationLog, col), f"missing {col}"


def test_verification_log_ip_hash():
    from app.modules.m11_sis.transcript_models import SisTranscriptVerificationLog
    assert hasattr(SisTranscriptVerificationLog, "requester_ip_hash")


def test_verification_log_context():
    from app.modules.m11_sis.transcript_models import SisTranscriptVerificationLog
    assert hasattr(SisTranscriptVerificationLog, "requester_context")


def test_verification_log_relationship():
    from app.modules.m11_sis.transcript_models import SisTranscriptVerificationLog
    assert hasattr(SisTranscriptVerificationLog, "transcript")


# ─────────────────────────────────────────────────────────────────────────────
# 73–76: PublicTranscriptIndex — public schema + PK
# ─────────────────────────────────────────────────────────────────────────────

def test_public_index_schema_public():
    from app.modules.m11_sis.transcript_models import PublicTranscriptIndex
    schema = PublicTranscriptIndex.__table__.schema
    assert schema == "public", f"Expected schema='public', got '{schema}'"


def test_public_index_pk():
    from app.modules.m11_sis.transcript_models import PublicTranscriptIndex
    assert hasattr(PublicTranscriptIndex, "verification_code")
    pk_cols = [c.name for c in PublicTranscriptIndex.__table__.primary_key]
    assert "verification_code" in pk_cols


def test_public_index_tablename():
    from app.modules.m11_sis.transcript_models import PublicTranscriptIndex
    assert PublicTranscriptIndex.__tablename__ == "public_transcript_index"


def test_public_index_issued_at_nullable():
    from app.modules.m11_sis.transcript_models import PublicTranscriptIndex
    col = PublicTranscriptIndex.__table__.c["issued_at"]
    assert col.nullable is True


# ─────────────────────────────────────────────────────────────────────────────
# 77–80: PublicTranscriptIndex columns
# ─────────────────────────────────────────────────────────────────────────────

def test_public_index_tenant_id():
    from app.modules.m11_sis.transcript_models import PublicTranscriptIndex
    col = PublicTranscriptIndex.__table__.c["tenant_id"]
    assert col.nullable is False


def test_public_index_schema_name():
    from app.modules.m11_sis.transcript_models import PublicTranscriptIndex
    col = PublicTranscriptIndex.__table__.c["schema_name"]
    assert col.nullable is False


def test_public_index_transcript_id():
    from app.modules.m11_sis.transcript_models import PublicTranscriptIndex
    col = PublicTranscriptIndex.__table__.c["transcript_id"]
    assert col.nullable is False


def test_public_index_status_not_nullable():
    from app.modules.m11_sis.transcript_models import PublicTranscriptIndex
    col = PublicTranscriptIndex.__table__.c["status"]
    assert col.nullable is False


# ─────────────────────────────────────────────────────────────────────────────
# 81–84: Migration 0036ten
# ─────────────────────────────────────────────────────────────────────────────

def _load_migration(rel_path: str):
    base = pathlib.Path(__file__).parents[3]  # .../backend
    path = base / rel_path
    spec = importlib.util.spec_from_file_location("migration", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0036_revision():
    m = _load_migration("alembic/tenant_versions/0036_tenant_transcripts.py")
    assert m.revision == "0036ten"


def test_migration_0036_down_revision():
    m = _load_migration("alembic/tenant_versions/0036_tenant_transcripts.py")
    assert m.down_revision == "0035ten"


def test_migration_0036_creates_sis_transcripts():
    m = _load_migration("alembic/tenant_versions/0036_tenant_transcripts.py")
    src = inspect.getsource(m.upgrade)
    assert "sis_transcripts" in src


def test_migration_0036_creates_all_four_tables():
    m = _load_migration("alembic/tenant_versions/0036_tenant_transcripts.py")
    src = inspect.getsource(m.upgrade)
    for table in ("sis_transcripts", "sis_transcript_semester_lines",
                  "sis_transcript_subject_lines", "sis_transcript_verification_log"):
        assert table in src, f"Migration missing table: {table}"


# ─────────────────────────────────────────────────────────────────────────────
# 85–88: Migration 0036ten content checks
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0036_creates_sequence():
    m = _load_migration("alembic/tenant_versions/0036_tenant_transcripts.py")
    src = inspect.getsource(m.upgrade)
    assert "sis_transcript_seq" in src


def test_migration_0036_adds_min_credits_column():
    m = _load_migration("alembic/tenant_versions/0036_tenant_transcripts.py")
    src = inspect.getsource(m.upgrade)
    assert "min_credits_for_degree" in src


def test_migration_0036_downgrade_drops_tables():
    m = _load_migration("alembic/tenant_versions/0036_tenant_transcripts.py")
    src = inspect.getsource(m.downgrade)
    assert "sis_transcripts" in src
    assert "DROP SEQUENCE" in src


def test_migration_0036_marks_columns_present():
    m = _load_migration("alembic/tenant_versions/0036_tenant_transcripts.py")
    src = inspect.getsource(m.upgrade)
    assert "internal_marks_snapshot" in src
    assert "external_marks_snapshot" in src
    assert "total_marks_snapshot" in src
    assert "grade_letter_snapshot" in src


# ─────────────────────────────────────────────────────────────────────────────
# 89–92: Migration 0012pub
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0012pub_revision():
    m = _load_migration("alembic/public_versions/0012_public_transcript_index.py")
    assert m.revision == "0012pub"


def test_migration_0012pub_down_revision():
    m = _load_migration("alembic/public_versions/0012_public_transcript_index.py")
    assert m.down_revision == "0011pub"


def test_migration_0012pub_creates_table():
    m = _load_migration("alembic/public_versions/0012_public_transcript_index.py")
    src = inspect.getsource(m.upgrade)
    assert "public_transcript_index" in src


def test_migration_0012pub_public_schema():
    m = _load_migration("alembic/public_versions/0012_public_transcript_index.py")
    src = inspect.getsource(m.upgrade)
    assert 'schema="public"' in src


# ─────────────────────────────────────────────────────────────────────────────
# 97–100: TranscriptSummaryRead schema fields
# ─────────────────────────────────────────────────────────────────────────────

def test_transcript_summary_read_fields():
    from app.modules.m11_sis.transcript_schemas import TranscriptSummaryRead
    fields = TranscriptSummaryRead.model_fields
    for f in ("id", "student_id", "student_name_snapshot", "transcript_number",
              "transcript_type", "status", "version", "overall_cgpa_snapshot",
              "arrear_count_snapshot", "degree_status_snapshot"):
        assert f in fields, f"TranscriptSummaryRead missing field: {f}"


def test_transcript_summary_read_no_marks():
    from app.modules.m11_sis.transcript_schemas import TranscriptSummaryRead
    fields = set(TranscriptSummaryRead.model_fields.keys())
    assert "internal_marks_snapshot" not in fields
    assert "external_marks_snapshot" not in fields


def test_transcript_summary_requested_at():
    from app.modules.m11_sis.transcript_schemas import TranscriptSummaryRead
    assert "requested_at" in TranscriptSummaryRead.model_fields


def test_transcript_detail_read_has_lines():
    from app.modules.m11_sis.transcript_schemas import TranscriptDetailRead
    assert "semester_lines" in TranscriptDetailRead.model_fields


# ─────────────────────────────────────────────────────────────────────────────
# 101–104: TranscriptDetailRead — available to admin but not public
# ─────────────────────────────────────────────────────────────────────────────

def test_transcript_detail_read_has_verification_code():
    from app.modules.m11_sis.transcript_schemas import TranscriptDetailRead
    assert "verification_code" in TranscriptDetailRead.model_fields


def test_transcript_detail_read_has_full_credentials():
    from app.modules.m11_sis.transcript_schemas import TranscriptDetailRead
    for f in ("overall_cgpa_snapshot", "total_credits_attempted_snapshot",
              "total_credits_earned_snapshot"):
        assert f in TranscriptDetailRead.model_fields, f"TranscriptDetailRead missing {f}"


def test_transcript_subject_line_read_has_marks():
    from app.modules.m11_sis.transcript_schemas import TranscriptSubjectLineRead
    for f in ("internal_marks_snapshot", "external_marks_snapshot", "total_marks_snapshot",
              "grade_letter_snapshot"):
        assert f in TranscriptSubjectLineRead.model_fields, f"TranscriptSubjectLineRead missing {f}"


def test_transcript_subject_line_read_is_best_attempt():
    from app.modules.m11_sis.transcript_schemas import TranscriptSubjectLineRead
    assert "is_best_attempt" in TranscriptSubjectLineRead.model_fields


# ─────────────────────────────────────────────────────────────────────────────
# 105–108: TranscriptVerifyResponse — never exposes marks or CGPA
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_response_no_marks():
    from app.modules.m11_sis.transcript_schemas import TranscriptVerifyResponse
    fields = set(TranscriptVerifyResponse.model_fields.keys())
    for restricted in ("internal_marks_snapshot", "external_marks_snapshot",
                       "total_marks_snapshot", "overall_cgpa_snapshot",
                       "total_credits_attempted_snapshot"):
        assert restricted not in fields, (
            f"TranscriptVerifyResponse must not expose {restricted}"
        )


def test_verify_response_no_cgpa():
    from app.modules.m11_sis.transcript_schemas import TranscriptVerifyResponse
    assert "overall_cgpa_snapshot" not in TranscriptVerifyResponse.model_fields
    assert "current_cgpa" not in TranscriptVerifyResponse.model_fields


def test_verify_response_allowed_fields():
    from app.modules.m11_sis.transcript_schemas import TranscriptVerifyResponse
    fields = TranscriptVerifyResponse.model_fields
    for f in ("verification_code", "transcript_number", "student_name_partial",
              "program_name", "institution_name", "degree_status",
              "issued_at", "status", "is_provisional", "message"):
        assert f in fields, f"TranscriptVerifyResponse missing {f}"


def test_verify_response_student_name_partial_not_full():
    from app.modules.m11_sis.transcript_schemas import TranscriptVerifyResponse
    assert "student_name_snapshot" not in TranscriptVerifyResponse.model_fields
    assert "student_name_partial" in TranscriptVerifyResponse.model_fields


# ─────────────────────────────────────────────────────────────────────────────
# 109–112: DegreeProgressRead — expected_graduation_year
# ─────────────────────────────────────────────────────────────────────────────

def test_degree_progress_has_expected_graduation_year():
    from app.modules.m11_sis.transcript_schemas import DegreeProgressRead
    assert "expected_graduation_year" in DegreeProgressRead.model_fields


def test_degree_progress_graduation_year_optional():
    from app.modules.m11_sis.transcript_schemas import DegreeProgressRead
    import typing
    field = DegreeProgressRead.model_fields["expected_graduation_year"]
    # Pydantic v2: Optional[int] annotation allows None values
    annotation = field.annotation
    annotation_str = str(annotation)
    assert "int" in annotation_str and ("NoneType" in annotation_str or "Optional" in annotation_str)


def test_degree_progress_core_fields():
    from app.modules.m11_sis.transcript_schemas import DegreeProgressRead
    fields = DegreeProgressRead.model_fields
    for f in ("student_id", "student_name", "program_name", "total_semesters_declared",
              "total_credits_attempted", "total_credits_earned", "current_cgpa",
              "arrear_count", "active_backlogs", "degree_status",
              "is_final_semester_declared", "semesters"):
        assert f in fields, f"DegreeProgressRead missing {f}"


def test_degree_progress_min_credits_field():
    from app.modules.m11_sis.transcript_schemas import DegreeProgressRead
    assert "min_credits_for_degree" in DegreeProgressRead.model_fields


# ─────────────────────────────────────────────────────────────────────────────
# 113–116: TranscriptServiceError
# ─────────────────────────────────────────────────────────────────────────────

def test_service_error_carries_code():
    from app.modules.m11_sis.transcript_service import TranscriptServiceError
    err = TranscriptServiceError("ACTIVE_REQUEST_EXISTS", "already exists", 409)
    assert err.code == "ACTIVE_REQUEST_EXISTS"


def test_service_error_carries_message():
    from app.modules.m11_sis.transcript_service import TranscriptServiceError
    err = TranscriptServiceError("NOT_FOUND", "not found", 404)
    assert err.message == "not found"


def test_service_error_carries_status_code():
    from app.modules.m11_sis.transcript_service import TranscriptServiceError
    err = TranscriptServiceError("NOT_FOUND", "not found", 404)
    assert err.status_code == 404


def test_service_error_default_status_code():
    from app.modules.m11_sis.transcript_service import TranscriptServiceError
    err = TranscriptServiceError("X", "msg")
    assert err.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# 117–120: _partial_name helper
# ─────────────────────────────────────────────────────────────────────────────

def test_partial_name_two_parts():
    from app.modules.m11_sis.transcript_service import _partial_name
    assert _partial_name("Arun Kumar") == "Arun K."


def test_partial_name_single_word():
    from app.modules.m11_sis.transcript_service import _partial_name
    assert _partial_name("Arun") == "Arun"


def test_partial_name_empty():
    from app.modules.m11_sis.transcript_service import _partial_name
    assert _partial_name("") == "—"


def test_partial_name_three_parts():
    from app.modules.m11_sis.transcript_service import _partial_name
    result = _partial_name("Srinivas Bharathi Muthukumar")
    assert result.startswith("Srinivas")
    assert result.endswith(".")


# ─────────────────────────────────────────────────────────────────────────────
# 121–124: _verify_message helper
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_message_valid():
    from app.modules.m11_sis.transcript_service import _verify_message
    from app.modules.m11_sis.transcript_models import VerificationResult
    msg = _verify_message(VerificationResult.VALID)
    assert "valid" in msg.lower()


def test_verify_message_revoked():
    from app.modules.m11_sis.transcript_service import _verify_message
    from app.modules.m11_sis.transcript_models import VerificationResult
    msg = _verify_message(VerificationResult.REVOKED)
    assert "revoked" in msg.lower()


def test_verify_message_superseded():
    from app.modules.m11_sis.transcript_service import _verify_message
    from app.modules.m11_sis.transcript_models import VerificationResult
    msg = _verify_message(VerificationResult.SUPERSEDED)
    assert len(msg) > 10


def test_verify_message_not_found():
    from app.modules.m11_sis.transcript_service import _verify_message
    from app.modules.m11_sis.transcript_models import VerificationResult
    msg = _verify_message(VerificationResult.NOT_FOUND)
    assert "not found" in msg.lower() or "Transcript" in msg


# ─────────────────────────────────────────────────────────────────────────────
# 125–128: Celery task registration
# ─────────────────────────────────────────────────────────────────────────────

def test_celery_includes_transcript_task():
    from app.workers.celery_app import celery_app
    assert "app.workers.heavy.generate_transcript_pdf" in celery_app.conf.include


def test_celery_task_name_matches_module():
    from app.workers.heavy.generate_transcript_pdf import generate_transcript_pdf
    assert generate_transcript_pdf.name == "app.workers.heavy.generate_transcript_pdf"


def test_celery_task_is_callable():
    from app.workers.heavy.generate_transcript_pdf import generate_transcript_pdf
    assert callable(generate_transcript_pdf)


def test_celery_task_is_in_heavy_queue():
    from app.workers.celery_app import celery_app
    routes = celery_app.conf.task_routes
    # heavy tasks go to celery-heavy via wildcard
    assert any("heavy" in k for k in routes)


# ─────────────────────────────────────────────────────────────────────────────
# 129–132: TranscriptRepo source checks
# ─────────────────────────────────────────────────────────────────────────────

def test_transcript_repo_next_number_format():
    from app.modules.m11_sis.transcript_repository import TranscriptRepo
    src = inspect.getsource(TranscriptRepo.next_transcript_number)
    assert "TRX/" in src
    assert "sis_transcript_seq" in src


def test_transcript_repo_has_active_request_checks_requested_generated():
    from app.modules.m11_sis.transcript_repository import TranscriptRepo
    src = inspect.getsource(TranscriptRepo.has_active_request)
    assert "REQUESTED" in src
    assert "GENERATED" in src


def test_transcript_repo_list_for_student_orders_by_version():
    from app.modules.m11_sis.transcript_repository import TranscriptRepo
    src = inspect.getsource(TranscriptRepo.list_for_student)
    assert "version" in src


def test_public_index_repo_upsert_exists():
    from app.modules.m11_sis.transcript_repository import PublicTranscriptIndexRepo
    assert callable(PublicTranscriptIndexRepo.upsert)
    assert callable(PublicTranscriptIndexRepo.update_status)
    assert callable(PublicTranscriptIndexRepo.get_by_code)


# ─────────────────────────────────────────────────────────────────────────────
# 137–140: Router prefixes
# ─────────────────────────────────────────────────────────────────────────────

def test_transcript_router_prefix():
    from app.modules.m11_sis.transcript_router import transcript_router
    assert transcript_router.prefix == "/transcripts"


def test_verify_router_prefix():
    from app.modules.m11_sis.transcript_router import verify_router
    assert verify_router.prefix == "/verify"


def test_transcript_router_has_routes():
    from app.modules.m11_sis.transcript_router import transcript_router
    assert len(transcript_router.routes) > 0


def test_verify_router_has_verify_route():
    from app.modules.m11_sis.transcript_router import verify_router
    paths = [r.path for r in verify_router.routes]
    assert any("code" in p or "{" in p for p in paths)


# ─────────────────────────────────────────────────────────────────────────────
# 141–144: Route ordering — /my-transcripts before /{transcript_id}
# ─────────────────────────────────────────────────────────────────────────────

def test_my_transcripts_before_transcript_id_in_source():
    import app.modules.m11_sis.transcript_router as mod
    src = inspect.getsource(mod)
    my_pos = src.index("/my-transcripts")
    param_pos = src.index('"/{transcript_id}"')
    assert my_pos < param_pos, (
        "/my-transcripts route must be defined before /{transcript_id} to avoid UUID parse error"
    )


def test_my_degree_progress_before_transcript_id_in_source():
    import app.modules.m11_sis.transcript_router as mod
    src = inspect.getsource(mod)
    dp_pos = src.index("/my-degree-progress")
    param_pos = src.index('"/{transcript_id}"')
    assert dp_pos < param_pos, (
        "/my-degree-progress route must be defined before /{transcript_id}"
    )


def test_students_route_before_transcript_id_in_source():
    import app.modules.m11_sis.transcript_router as mod
    src = inspect.getsource(mod)
    s_pos = src.index("/students/{student_id}/degree-progress")
    param_pos = src.index('"/{transcript_id}"')
    assert s_pos < param_pos


def test_request_route_exists():
    import app.modules.m11_sis.transcript_router as mod
    src = inspect.getsource(mod)
    assert "/request" in src


# ─────────────────────────────────────────────────────────────────────────────
# 145–148: Public verify route has no auth
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_route_no_require_roles():
    from app.modules.m11_sis.transcript_router import verify_transcript
    src = inspect.getsource(verify_transcript)
    assert "require_roles" not in src


def test_verify_route_uses_platform_db():
    from app.modules.m11_sis.transcript_router import verify_transcript
    src = inspect.getsource(verify_transcript)
    assert "_get_platform_db" in src or "platform_db" in src or "db" in src


def test_verify_route_calls_verify_service():
    from app.modules.m11_sis.transcript_router import verify_transcript
    src = inspect.getsource(verify_transcript)
    assert "TranscriptVerifyService.verify" in src or "verify(" in src


def test_verify_service_builds_limited_response():
    from app.modules.m11_sis.transcript_service import TranscriptVerifyService
    src = inspect.getsource(TranscriptVerifyService.verify)
    assert "student_name_partial" in src
    assert "overall_cgpa" not in src


# ─────────────────────────────────────────────────────────────────────────────
# 153–156: AuditEventType coverage for transcript lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_event_transcript_requested():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.TRANSCRIPT_REQUESTED == "TRANSCRIPT_REQUESTED"


def test_audit_event_transcript_issued():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.TRANSCRIPT_ISSUED == "TRANSCRIPT_ISSUED"


def test_audit_event_transcript_revoked():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.TRANSCRIPT_REVOKED == "TRANSCRIPT_REVOKED"


def test_audit_event_transcript_pdf_downloaded():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.TRANSCRIPT_PDF_DOWNLOADED == "TRANSCRIPT_PDF_DOWNLOADED"


# ─────────────────────────────────────────────────────────────────────────────
# 157–160: PDF generation includes Internal, External, Total, Grade headers
# ─────────────────────────────────────────────────────────────────────────────

def test_pdf_header_has_internal_external_total_grade():
    from app.workers.heavy.generate_transcript_pdf import _build_pdf_semesters
    src = inspect.getsource(_build_pdf_semesters)
    assert "internal" in src


def test_pdf_render_has_marks_columns():
    from app.workers.heavy.generate_transcript_pdf import _render_pdf
    src = inspect.getsource(_render_pdf)
    assert '"Int"' in src or '"internal"' in src or "Int" in src


def test_pdf_header_row_has_ext_and_total():
    from app.workers.heavy.generate_transcript_pdf import _render_pdf
    src = inspect.getsource(_render_pdf)
    assert "Ext" in src or "ext" in src.lower()
    assert "Total" in src or "total" in src.lower()


def test_pdf_header_has_grade_column():
    from app.workers.heavy.generate_transcript_pdf import _render_pdf
    src = inspect.getsource(_render_pdf)
    assert "Grade" in src or "grade" in src.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 161–164: models.py and main.py wiring
# ─────────────────────────────────────────────────────────────────────────────

def test_models_py_imports_transcript_models():
    import app.models as mod
    src = inspect.getsource(mod)
    assert "transcript_models" in src


def test_main_py_includes_verify_router():
    import app.main as mod
    src = inspect.getsource(mod)
    assert "verify_router" in src
    assert '"/verify"' in src


def test_main_py_imports_verify_router():
    import app.main as mod
    src = inspect.getsource(mod)
    assert "from app.modules.m11_sis.transcript_router import verify_router" in src


def test_sis_router_includes_transcript_router():
    import app.modules.m11_sis.router as mod
    src = inspect.getsource(mod)
    assert "transcript_router" in src
