"""
Unit tests — H60 SIS Results Management

No live database. All tests use import + assert + inspect.getsource.

Coverage:
  1–4   : SisGradingPolicy ORM columns
  5–8   : SisGradingPolicyBand ORM columns + unique constraint
  9–12  : SisResultDeclaration core columns
  13–16 : SisResultDeclaration snapshot columns (academic_year, semester_name, policy_name)
  17–20 : SisResultDeclaration lifecycle + human gate columns
  21–24 : SisResultDeclaration future-proof columns (source_declaration_id, declaration_type)
  25–28 : SisExternalMarks ORM columns
  29–32 : SisSubjectResult ORM columns (marks components)
  33–36 : SisSubjectResult grade + result columns
  37–40 : SisSubjectResult credits + attempt columns
  41–44 : SisSemesterResult columns (SGPA/CGPA/ranks)
  45–48 : SisSemesterResult.overall_result_status column + enum values
  49–52 : SisGraceMarksLog columns (append-only audit)
  53–56 : DeclarationType enum values
  57–60 : DeclarationStatus enum values
  61–64 : ResultStatus enum values
  65–68 : OverallResultStatus enum values
  69–72 : Relationship: SisGradingPolicy → bands
  73–76 : Relationship: SisResultDeclaration → subject_results / semester_results
  77–80 : Relationship: SisResultDeclaration → grace_marks_log
  81–84 : Migration revision and down_revision
  85–88 : Migration table list (all 7 tables present)
  89–92 : SisGradingPolicy.program_id nullable (global vs program-specific)
  93–96 : SisSubjectResult.grace_marks nullable (Dean-gate only)
  97–100: SisGraceMarksLog append-only (no updated_at column)
"""
import importlib.util
import inspect
import pathlib



# ─────────────────────────────────────────────────────────────────────────────
# 1–4: SisGradingPolicy ORM columns
# ─────────────────────────────────────────────────────────────────────────────

def test_grading_policy_pk():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    assert hasattr(SisGradingPolicy, "id")


def test_grading_policy_name_pass_pct():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    for col in ("name", "pass_percentage"):
        assert hasattr(SisGradingPolicy, col), f"SisGradingPolicy missing {col}"


def test_grading_policy_flags():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    for col in ("is_default", "is_active", "created_by"):
        assert hasattr(SisGradingPolicy, col), f"SisGradingPolicy missing {col}"


def test_grading_policy_tablename():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    assert SisGradingPolicy.__tablename__ == "sis_grading_policies"


# ─────────────────────────────────────────────────────────────────────────────
# 5–8: SisGradingPolicyBand ORM columns + unique constraint
# ─────────────────────────────────────────────────────────────────────────────

def test_grading_band_core_columns():
    from app.modules.m11_sis.results_models import SisGradingPolicyBand
    for col in ("id", "policy_id", "grade_letter", "min_percentage",
                "max_percentage", "grade_point", "is_pass"):
        assert hasattr(SisGradingPolicyBand, col), f"SisGradingPolicyBand missing {col}"


def test_grading_band_tablename():
    from app.modules.m11_sis.results_models import SisGradingPolicyBand
    assert SisGradingPolicyBand.__tablename__ == "sis_grading_policy_bands"


def test_grading_band_display_order():
    from app.modules.m11_sis.results_models import SisGradingPolicyBand
    assert hasattr(SisGradingPolicyBand, "display_order")


def test_grading_band_unique_constraint():
    from app.modules.m11_sis.results_models import SisGradingPolicyBand
    constraint_names = [
        c.name for c in SisGradingPolicyBand.__table_args__
        if hasattr(c, "name")
    ]
    assert "uq_grading_bands_policy_letter" in constraint_names


# ─────────────────────────────────────────────────────────────────────────────
# 9–12: SisResultDeclaration core columns
# ─────────────────────────────────────────────────────────────────────────────

def test_result_declaration_pk():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "id")


def test_result_declaration_context_columns():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    for col in ("exam_session_id", "semester_id", "grading_policy_id"):
        assert hasattr(SisResultDeclaration, col), f"SisResultDeclaration missing {col}"


def test_result_declaration_tablename():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert SisResultDeclaration.__tablename__ == "sis_result_declarations"


def test_result_declaration_metadata_columns():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    for col in ("title", "notes", "internal_marks_required"):
        assert hasattr(SisResultDeclaration, col), f"SisResultDeclaration missing {col}"


# ─────────────────────────────────────────────────────────────────────────────
# 13–16: SisResultDeclaration snapshot columns
# ─────────────────────────────────────────────────────────────────────────────

def test_result_declaration_snapshot_academic_year():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "snapshot_academic_year")


def test_result_declaration_snapshot_semester_name():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "snapshot_semester_name")


def test_result_declaration_snapshot_policy_name():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "snapshot_grading_policy_name")


def test_result_declaration_all_three_snapshots():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    snapshots = [
        "snapshot_academic_year",
        "snapshot_semester_name",
        "snapshot_grading_policy_name",
    ]
    for s in snapshots:
        assert hasattr(SisResultDeclaration, s), f"SisResultDeclaration missing snapshot {s}"


# ─────────────────────────────────────────────────────────────────────────────
# 17–20: SisResultDeclaration lifecycle + human gate columns
# ─────────────────────────────────────────────────────────────────────────────

def test_result_declaration_status_column():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "status")


def test_result_declaration_verified_gate():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    for col in ("verified_by", "verified_at"):
        assert hasattr(SisResultDeclaration, col)


def test_result_declaration_published_gate():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    for col in ("published_by", "published_at"):
        assert hasattr(SisResultDeclaration, col)


def test_result_declaration_locked_gate():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    for col in ("locked_by", "locked_at"):
        assert hasattr(SisResultDeclaration, col)


# ─────────────────────────────────────────────────────────────────────────────
# 21–24: SisResultDeclaration future-proof columns
# ─────────────────────────────────────────────────────────────────────────────

def test_result_declaration_type_column():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "declaration_type")


def test_result_declaration_source_id():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "source_declaration_id")


def test_result_declaration_unique_constraint():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    constraint_names = [
        c.name for c in SisResultDeclaration.__table_args__
        if hasattr(c, "name")
    ]
    assert "uq_result_declarations_session_type" in constraint_names


def test_result_declaration_created_by():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "created_by")


# ─────────────────────────────────────────────────────────────────────────────
# 25–28: SisExternalMarks ORM columns
# ─────────────────────────────────────────────────────────────────────────────

def test_external_marks_core_columns():
    from app.modules.m11_sis.results_models import SisExternalMarks
    for col in ("id", "declaration_id", "student_id", "course_id", "section_id"):
        assert hasattr(SisExternalMarks, col), f"SisExternalMarks missing {col}"


def test_external_marks_tablename():
    from app.modules.m11_sis.results_models import SisExternalMarks
    assert SisExternalMarks.__tablename__ == "sis_external_marks"


def test_external_marks_values():
    from app.modules.m11_sis.results_models import SisExternalMarks
    for col in ("external_marks_obtained", "external_marks_max", "is_absent"):
        assert hasattr(SisExternalMarks, col), f"SisExternalMarks missing {col}"


def test_external_marks_tracking():
    from app.modules.m11_sis.results_models import SisExternalMarks
    for col in ("entered_by", "entered_at", "edited_by", "edited_at", "edit_reason"):
        assert hasattr(SisExternalMarks, col), f"SisExternalMarks missing {col}"


# ─────────────────────────────────────────────────────────────────────────────
# 29–32: SisSubjectResult ORM columns (marks components)
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_result_pk_and_context():
    from app.modules.m11_sis.results_models import SisSubjectResult
    for col in ("id", "declaration_id", "student_id", "course_id", "section_id", "semester_id"):
        assert hasattr(SisSubjectResult, col), f"SisSubjectResult missing {col}"


def test_subject_result_tablename():
    from app.modules.m11_sis.results_models import SisSubjectResult
    assert SisSubjectResult.__tablename__ == "sis_subject_results"


def test_subject_result_marks_columns():
    from app.modules.m11_sis.results_models import SisSubjectResult
    for col in ("internal_marks", "external_marks", "grace_marks",
                "total_marks", "max_marks", "percentage"):
        assert hasattr(SisSubjectResult, col), f"SisSubjectResult missing {col}"


def test_subject_result_unique_constraint():
    from app.modules.m11_sis.results_models import SisSubjectResult
    constraint_names = [
        c.name for c in SisSubjectResult.__table_args__
        if hasattr(c, "name")
    ]
    assert "uq_subject_results_declaration_student_course" in constraint_names


# ─────────────────────────────────────────────────────────────────────────────
# 33–36: SisSubjectResult grade + result columns
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_result_grade_columns():
    from app.modules.m11_sis.results_models import SisSubjectResult
    for col in ("grade_letter", "grade_point", "is_pass"):
        assert hasattr(SisSubjectResult, col), f"SisSubjectResult missing {col}"


def test_subject_result_status():
    from app.modules.m11_sis.results_models import SisSubjectResult
    assert hasattr(SisSubjectResult, "result_status")


def test_subject_result_computed_at():
    from app.modules.m11_sis.results_models import SisSubjectResult
    assert hasattr(SisSubjectResult, "computed_at")


def test_subject_result_is_pass_nullable():
    from app.modules.m11_sis.results_models import SisSubjectResult
    col = SisSubjectResult.__table__.c["is_pass"]
    assert col.nullable is True


# ─────────────────────────────────────────────────────────────────────────────
# 37–40: SisSubjectResult credits + attempt columns
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_result_credits_columns():
    from app.modules.m11_sis.results_models import SisSubjectResult
    for col in ("credits_attempted", "credits_earned"):
        assert hasattr(SisSubjectResult, col), f"SisSubjectResult missing {col}"


def test_subject_result_attempt_number():
    from app.modules.m11_sis.results_models import SisSubjectResult
    assert hasattr(SisSubjectResult, "attempt_number")


def test_subject_result_credits_nullable():
    from app.modules.m11_sis.results_models import SisSubjectResult
    for col_name in ("credits_attempted", "credits_earned"):
        col = SisSubjectResult.__table__.c[col_name]
        assert col.nullable is True, f"{col_name} should be nullable (not yet computed)"


def test_subject_result_grace_marks_nullable():
    from app.modules.m11_sis.results_models import SisSubjectResult
    col = SisSubjectResult.__table__.c["grace_marks"]
    assert col.nullable is True


# ─────────────────────────────────────────────────────────────────────────────
# 41–44: SisSemesterResult columns (SGPA/CGPA/ranks)
# ─────────────────────────────────────────────────────────────────────────────

def test_semester_result_core_columns():
    from app.modules.m11_sis.results_models import SisSemesterResult
    for col in ("id", "declaration_id", "student_id", "semester_id"):
        assert hasattr(SisSemesterResult, col), f"SisSemesterResult missing {col}"


def test_semester_result_tablename():
    from app.modules.m11_sis.results_models import SisSemesterResult
    assert SisSemesterResult.__tablename__ == "sis_semester_results"


def test_semester_result_sgpa_cgpa():
    from app.modules.m11_sis.results_models import SisSemesterResult
    for col in ("sgpa", "cgpa", "total_credits_attempted", "total_credits_earned"):
        assert hasattr(SisSemesterResult, col), f"SisSemesterResult missing {col}"


def test_semester_result_ranks():
    from app.modules.m11_sis.results_models import SisSemesterResult
    for col in ("section_rank", "program_rank"):
        assert hasattr(SisSemesterResult, col), f"SisSemesterResult missing {col}"


# ─────────────────────────────────────────────────────────────────────────────
# 45–48: SisSemesterResult.overall_result_status + enum values
# ─────────────────────────────────────────────────────────────────────────────

def test_semester_result_overall_status_column():
    from app.modules.m11_sis.results_models import SisSemesterResult
    assert hasattr(SisSemesterResult, "overall_result_status")


def test_semester_result_overall_status_nullable():
    from app.modules.m11_sis.results_models import SisSemesterResult
    col = SisSemesterResult.__table__.c["overall_result_status"]
    assert col.nullable is True


def test_overall_result_status_enum_values():
    from app.modules.m11_sis.results_models import OverallResultStatus
    assert OverallResultStatus.PASS        == "PASS"
    assert OverallResultStatus.FAIL        == "FAIL"
    assert OverallResultStatus.WITHHELD    == "WITHHELD"
    assert OverallResultStatus.PROVISIONAL == "PROVISIONAL"


def test_overall_result_status_has_four_values():
    from app.modules.m11_sis.results_models import OverallResultStatus
    assert len(list(OverallResultStatus)) == 4


# ─────────────────────────────────────────────────────────────────────────────
# 49–52: SisGraceMarksLog columns (append-only audit)
# ─────────────────────────────────────────────────────────────────────────────

def test_grace_marks_log_core_columns():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    for col in ("id", "declaration_id", "subject_result_id", "student_id", "course_id"):
        assert hasattr(SisGraceMarksLog, col), f"SisGraceMarksLog missing {col}"


def test_grace_marks_log_tablename():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    assert SisGraceMarksLog.__tablename__ == "sis_grace_marks_log"


def test_grace_marks_log_authorization_columns():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    for col in ("grace_marks_applied", "reason", "authorized_by", "authorized_at"):
        assert hasattr(SisGraceMarksLog, col), f"SisGraceMarksLog missing {col}"


def test_grace_marks_log_revocation_columns():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    for col in ("revoked_by", "revoked_at", "revoke_reason"):
        assert hasattr(SisGraceMarksLog, col), f"SisGraceMarksLog missing {col}"


# ─────────────────────────────────────────────────────────────────────────────
# 53–56: DeclarationType enum values
# ─────────────────────────────────────────────────────────────────────────────

def test_declaration_type_regular():
    from app.modules.m11_sis.results_models import DeclarationType
    assert DeclarationType.REGULAR == "REGULAR"


def test_declaration_type_supplementary():
    from app.modules.m11_sis.results_models import DeclarationType
    assert DeclarationType.SUPPLEMENTARY == "SUPPLEMENTARY"


def test_declaration_type_improvement():
    from app.modules.m11_sis.results_models import DeclarationType
    assert DeclarationType.IMPROVEMENT == "IMPROVEMENT"


def test_declaration_type_revaluation():
    from app.modules.m11_sis.results_models import DeclarationType
    assert DeclarationType.REVALUATION == "REVALUATION"


# ─────────────────────────────────────────────────────────────────────────────
# 57–60: DeclarationStatus enum values
# ─────────────────────────────────────────────────────────────────────────────

def test_declaration_status_draft():
    from app.modules.m11_sis.results_models import DeclarationStatus
    assert DeclarationStatus.DRAFT == "DRAFT"


def test_declaration_status_verified():
    from app.modules.m11_sis.results_models import DeclarationStatus
    assert DeclarationStatus.VERIFIED == "VERIFIED"


def test_declaration_status_published():
    from app.modules.m11_sis.results_models import DeclarationStatus
    assert DeclarationStatus.PUBLISHED == "PUBLISHED"


def test_declaration_status_locked():
    from app.modules.m11_sis.results_models import DeclarationStatus
    assert DeclarationStatus.LOCKED == "LOCKED"


# ─────────────────────────────────────────────────────────────────────────────
# 61–64: ResultStatus enum values
# ─────────────────────────────────────────────────────────────────────────────

def test_result_status_pending():
    from app.modules.m11_sis.results_models import ResultStatus
    assert ResultStatus.PENDING == "PENDING"


def test_result_status_pass_fail():
    from app.modules.m11_sis.results_models import ResultStatus
    assert ResultStatus.PASS == "PASS"
    assert ResultStatus.FAIL == "FAIL"


def test_result_status_absent():
    from app.modules.m11_sis.results_models import ResultStatus
    assert ResultStatus.ABSENT == "ABSENT"


def test_result_status_withheld():
    from app.modules.m11_sis.results_models import ResultStatus
    assert ResultStatus.WITHHELD == "WITHHELD"


# ─────────────────────────────────────────────────────────────────────────────
# 65–68: OverallResultStatus enum values (already tested 45–48; extra assertions)
# ─────────────────────────────────────────────────────────────────────────────

def test_overall_status_is_str_enum():
    from app.modules.m11_sis.results_models import OverallResultStatus
    assert issubclass(OverallResultStatus, str)


def test_overall_status_values_are_strings():
    from app.modules.m11_sis.results_models import OverallResultStatus
    for v in OverallResultStatus:
        assert isinstance(v.value, str)


def test_overall_status_withheld_value():
    from app.modules.m11_sis.results_models import OverallResultStatus
    assert OverallResultStatus.WITHHELD.value == "WITHHELD"


def test_overall_status_provisional_value():
    from app.modules.m11_sis.results_models import OverallResultStatus
    assert OverallResultStatus.PROVISIONAL.value == "PROVISIONAL"


# ─────────────────────────────────────────────────────────────────────────────
# 69–72: Relationship SisGradingPolicy → bands
# ─────────────────────────────────────────────────────────────────────────────

def test_grading_policy_bands_relationship():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    assert hasattr(SisGradingPolicy, "bands")


def test_grading_band_policy_back_ref():
    from app.modules.m11_sis.results_models import SisGradingPolicyBand
    assert hasattr(SisGradingPolicyBand, "policy")


def test_grading_policy_band_cascade():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    rel = SisGradingPolicy.bands.property
    assert "delete" in rel.cascade


def test_grading_band_fk_on_cascade():
    from app.modules.m11_sis.results_models import SisGradingPolicyBand
    fk = list(SisGradingPolicyBand.__table__.c["policy_id"].foreign_keys)[0]
    assert fk.ondelete == "CASCADE"


# ─────────────────────────────────────────────────────────────────────────────
# 73–76: Relationship SisResultDeclaration → subject_results / semester_results
# ─────────────────────────────────────────────────────────────────────────────

def test_declaration_subject_results_relationship():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "subject_results")


def test_declaration_semester_results_relationship():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "semester_results")


def test_declaration_external_marks_relationship():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "external_marks")


def test_subject_result_declaration_back_ref():
    from app.modules.m11_sis.results_models import SisSubjectResult
    assert hasattr(SisSubjectResult, "declaration")


# ─────────────────────────────────────────────────────────────────────────────
# 77–80: Relationship SisResultDeclaration → grace_marks_log
# ─────────────────────────────────────────────────────────────────────────────

def test_declaration_grace_marks_log_relationship():
    from app.modules.m11_sis.results_models import SisResultDeclaration
    assert hasattr(SisResultDeclaration, "grace_marks_log")


def test_grace_log_declaration_back_ref():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    assert hasattr(SisGraceMarksLog, "declaration")


def test_subject_result_grace_log_relationship():
    from app.modules.m11_sis.results_models import SisSubjectResult
    assert hasattr(SisSubjectResult, "grace_log")


def test_grace_log_subject_result_back_ref():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    assert hasattr(SisGraceMarksLog, "subject_result")


# ─────────────────────────────────────────────────────────────────────────────
# 81–84: Migration revision and down_revision
# ─────────────────────────────────────────────────────────────────────────────

def _load_migration():
    p = pathlib.Path(
        "backend/alembic/tenant_versions/0035_tenant_results_management.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0035", p)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_revision():
    mod = _load_migration()
    assert mod.revision == "0035ten"


def test_migration_down_revision():
    mod = _load_migration()
    assert mod.down_revision == "0034ten"


def test_migration_has_upgrade():
    mod = _load_migration()
    assert callable(mod.upgrade)


def test_migration_has_downgrade():
    mod = _load_migration()
    assert callable(mod.downgrade)


# ─────────────────────────────────────────────────────────────────────────────
# 85–88: Migration table list (all 7 tables)
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_grading_policy_table():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "sis_grading_policies" in src


def test_migration_policy_bands_table():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "sis_grading_policy_bands" in src


def test_migration_result_declarations_table():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "sis_result_declarations" in src


def test_migration_all_seven_tables():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    expected = [
        "sis_grading_policies",
        "sis_grading_policy_bands",
        "sis_result_declarations",
        "sis_external_marks",
        "sis_subject_results",
        "sis_semester_results",
        "sis_grace_marks_log",
    ]
    for t in expected:
        assert t in src, f"Migration missing table {t}"


# ─────────────────────────────────────────────────────────────────────────────
# 89–92: SisGradingPolicy.program_id nullable (global vs program-specific)
# ─────────────────────────────────────────────────────────────────────────────

def test_grading_policy_program_id_nullable():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    col = SisGradingPolicy.__table__.c["program_id"]
    assert col.nullable is True


def test_grading_policy_no_fk_to_programs():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    # program_id is a plain UUID (no FK) — codebase pattern for cross-module refs
    fks = list(SisGradingPolicy.__table__.c["program_id"].foreign_keys)
    assert len(fks) == 0


def test_grading_policy_created_at_server_default():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    col = SisGradingPolicy.__table__.c["created_at"]
    assert col.server_default is not None


def test_grading_policy_pass_percentage_server_default():
    from app.modules.m11_sis.results_models import SisGradingPolicy
    col = SisGradingPolicy.__table__.c["pass_percentage"]
    assert col.server_default is not None


# ─────────────────────────────────────────────────────────────────────────────
# 93–96: SisSubjectResult.grace_marks nullable (Dean-gate only)
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_result_grace_marks_exists():
    from app.modules.m11_sis.results_models import SisSubjectResult
    assert hasattr(SisSubjectResult, "grace_marks")


def test_subject_result_grace_marks_column_nullable():
    from app.modules.m11_sis.results_models import SisSubjectResult
    col = SisSubjectResult.__table__.c["grace_marks"]
    assert col.nullable is True


def test_subject_result_no_grace_server_default():
    from app.modules.m11_sis.results_models import SisSubjectResult
    col = SisSubjectResult.__table__.c["grace_marks"]
    # No default — grace marks must be explicitly set by Dean gate
    assert col.server_default is None


def test_subject_result_result_status_server_default():
    from app.modules.m11_sis.results_models import SisSubjectResult
    col = SisSubjectResult.__table__.c["result_status"]
    assert col.server_default is not None


# ─────────────────────────────────────────────────────────────────────────────
# 97–100: SisGraceMarksLog append-only (no updated_at column)
# ─────────────────────────────────────────────────────────────────────────────

def test_grace_marks_log_no_updated_at():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    assert not hasattr(SisGraceMarksLog, "updated_at"), \
        "sis_grace_marks_log must be append-only — no updated_at"


def test_grace_marks_log_has_created_at():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    assert hasattr(SisGraceMarksLog, "created_at")


def test_grace_marks_log_reason_not_nullable():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    col = SisGraceMarksLog.__table__.c["reason"]
    assert col.nullable is False


def test_grace_marks_log_authorized_by_not_nullable():
    from app.modules.m11_sis.results_models import SisGraceMarksLog
    col = SisGraceMarksLog.__table__.c["authorized_by"]
    assert col.nullable is False
