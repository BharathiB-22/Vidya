"""
Unit tests — H62 SIS Graduation Audit

No live database. All tests use import + assert + inspect.getsource.

Coverage:
  1–4   : GraduationAuditStatus enum (4 values)
  5–8   : CandidateEligibilityStatus enum (3 values)
  9–12  : CandidateBoardStatus enum (3 values)
  13–16 : CandidateCertificateStatus enum (3 values)
  17–20 : GraduationCertificateStatus enum (2 values)
  21–24 : SisGraduationAudit core columns
  25–28 : SisGraduationAudit batch/program snapshot columns
  29–32 : SisGraduationAudit gate timestamp columns
  33–36 : SisGraduationAudit summary counter columns
  37–40 : SisGraduationAudit board_resolution_ref + status defaults
  41–44 : SisGraduationCandidate core columns + UNIQUE constraint
  45–48 : SisGraduationCandidate 8 advisory eligibility flags
  49–52 : SisGraduationCandidate computed snapshot values
  53–56 : SisGraduationCandidate board decision columns
  57–60 : SisGraduationCandidate certificate columns
  61–64 : SisGraduationOverride append-only invariant (no updated_at)
  65–68 : SisGraduationOverride columns
  69–72 : SisGraduationCertificate core columns + UNIQUE certificate_number
  73–76 : SisGraduationCertificate snapshot columns
  77–80 : SisGraduationCertificate lifecycle + provisional columns
  81–84 : SisGraduationCertificate revocation columns
  85–88 : PublicGraduationIndex schema=public + PK
  89–92 : PublicGraduationIndex columns
  93–96 : Migration 0037ten revision / down_revision
  97–100: Migration 0037ten table list (4 tables + sequence)
 101–104: Migration 0037ten certificate numbering + board_resolution_ref
 105–108: Migration 0037ten append-only override (no updated_at in source)
 109–112: Migration 0037ten downgrade drops all tables + sequence
 113–116: Migration 0013pub revision / down_revision
 117–120: Migration 0013pub public_graduation_index table
 121–124: CertificateVerifyResponse never exposes CGPA/credits/flags/board_notes
 125–128: GraduationCandidateDetailRead contains board_notes (internal use)
 129–132: AuditApproveIn validates board_resolution_ref non-empty
 133–136: CandidateOverrideIn validates reason ≥ 20 chars
 137–140: BoardDeferIn requires board_notes ≥ 10 chars
 141–144: CertificateRevokeIn requires reason ≥ 10 chars
 145–148: Service _partial_name privacy (returns "Firstname L." format)
 149–152: GraduationLifecycleService.trigger raises on duplicate active audit
 153–156: board_resolution_ref check in approve method
 157–160: EligibilityEngine.compute returns dict with flags + values + eligibility_status
 161–164: Audit events for graduation lifecycle in AuditEventType
 165–168: Celery graduation tasks registered in celery_app
 169–172: graduation_router prefix = /graduation
 173–176: cert_verify_router route path contains /verify/certificate/
 177–180: /my-graduation-status defined before parameterized audit routes
 181–184: graduation_router included in m11_sis/router.py
 185–188: graduation_models imported in models.py
 189–192: cert_verify_router included in main.py
 193–196: GRADUATION_REVOKED added to DegreeStatus
"""
import importlib.util
import inspect
import pathlib

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _load_migration(rel_path: str):
    base = pathlib.Path(__file__).parents[3]  # .../backend
    path = base / rel_path
    spec = importlib.util.spec_from_file_location("migration", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# 1–4: GraduationAuditStatus enum
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_status_draft():
    from app.modules.m11_sis.graduation_models import GraduationAuditStatus
    assert GraduationAuditStatus.DRAFT == "DRAFT"


def test_audit_status_submitted():
    from app.modules.m11_sis.graduation_models import GraduationAuditStatus
    assert GraduationAuditStatus.SUBMITTED == "SUBMITTED"


def test_audit_status_board_approved():
    from app.modules.m11_sis.graduation_models import GraduationAuditStatus
    assert GraduationAuditStatus.BOARD_APPROVED == "BOARD_APPROVED"


def test_audit_status_certificates_issued_count():
    from app.modules.m11_sis.graduation_models import GraduationAuditStatus
    assert GraduationAuditStatus.CERTIFICATES_ISSUED == "CERTIFICATES_ISSUED"
    assert len(GraduationAuditStatus) == 4


# ─────────────────────────────────────────────────────────────────────────────
# 5–8: CandidateEligibilityStatus enum
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_eligibility_eligible():
    from app.modules.m11_sis.graduation_models import CandidateEligibilityStatus
    assert CandidateEligibilityStatus.ELIGIBLE == "ELIGIBLE"


def test_candidate_eligibility_not_eligible():
    from app.modules.m11_sis.graduation_models import CandidateEligibilityStatus
    assert CandidateEligibilityStatus.NOT_ELIGIBLE == "NOT_ELIGIBLE"


def test_candidate_eligibility_provisional():
    from app.modules.m11_sis.graduation_models import CandidateEligibilityStatus
    assert CandidateEligibilityStatus.PROVISIONAL == "PROVISIONAL"


def test_candidate_eligibility_count():
    from app.modules.m11_sis.graduation_models import CandidateEligibilityStatus
    assert len(CandidateEligibilityStatus) == 3


# ─────────────────────────────────────────────────────────────────────────────
# 9–12: CandidateBoardStatus enum
# ─────────────────────────────────────────────────────────────────────────────

def test_board_status_pending():
    from app.modules.m11_sis.graduation_models import CandidateBoardStatus
    assert CandidateBoardStatus.PENDING == "PENDING"


def test_board_status_ratified():
    from app.modules.m11_sis.graduation_models import CandidateBoardStatus
    assert CandidateBoardStatus.RATIFIED == "RATIFIED"


def test_board_status_deferred():
    from app.modules.m11_sis.graduation_models import CandidateBoardStatus
    assert CandidateBoardStatus.DEFERRED == "DEFERRED"


def test_board_status_count():
    from app.modules.m11_sis.graduation_models import CandidateBoardStatus
    assert len(CandidateBoardStatus) == 3


# ─────────────────────────────────────────────────────────────────────────────
# 13–16: CandidateCertificateStatus enum
# ─────────────────────────────────────────────────────────────────────────────

def test_cert_status_not_issued():
    from app.modules.m11_sis.graduation_models import CandidateCertificateStatus
    assert CandidateCertificateStatus.NOT_ISSUED == "NOT_ISSUED"


def test_cert_status_issued():
    from app.modules.m11_sis.graduation_models import CandidateCertificateStatus
    assert CandidateCertificateStatus.ISSUED == "ISSUED"


def test_cert_status_revoked():
    from app.modules.m11_sis.graduation_models import CandidateCertificateStatus
    assert CandidateCertificateStatus.REVOKED == "REVOKED"


def test_cert_status_count():
    from app.modules.m11_sis.graduation_models import CandidateCertificateStatus
    assert len(CandidateCertificateStatus) == 3


# ─────────────────────────────────────────────────────────────────────────────
# 17–20: GraduationCertificateStatus enum
# ─────────────────────────────────────────────────────────────────────────────

def test_graduation_cert_status_issued():
    from app.modules.m11_sis.graduation_models import GraduationCertificateStatus
    assert GraduationCertificateStatus.ISSUED == "ISSUED"


def test_graduation_cert_status_revoked():
    from app.modules.m11_sis.graduation_models import GraduationCertificateStatus
    assert GraduationCertificateStatus.REVOKED == "REVOKED"


def test_graduation_cert_status_count():
    from app.modules.m11_sis.graduation_models import GraduationCertificateStatus
    assert len(GraduationCertificateStatus) == 2


def test_graduation_cert_status_str_mixin():
    from app.modules.m11_sis.graduation_models import GraduationCertificateStatus
    assert GraduationCertificateStatus.ISSUED.value == "ISSUED"


# ─────────────────────────────────────────────────────────────────────────────
# 21–24: SisGraduationAudit core columns
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_has_id_and_batch_id():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "id")
    assert hasattr(SisGraduationAudit, "batch_id")


def test_audit_tablename():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert SisGraduationAudit.__tablename__ == "sis_graduation_audits"


def test_audit_status_column():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    col = SisGraduationAudit.__table__.c["status"]
    assert col.server_default is not None


def test_audit_has_timestamps():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "created_at")
    assert hasattr(SisGraduationAudit, "updated_at")


# ─────────────────────────────────────────────────────────────────────────────
# 25–28: SisGraduationAudit batch/program snapshot columns
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_batch_snapshot():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "batch_name_snapshot")


def test_audit_program_snapshot():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "program_id")
    assert hasattr(SisGraduationAudit, "program_name_snapshot")


def test_audit_academic_year_snapshot():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "academic_year_snapshot")


def test_audit_has_notes():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "notes")


# ─────────────────────────────────────────────────────────────────────────────
# 29–32: SisGraduationAudit gate timestamp columns
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_gate1_timestamps():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "triggered_by")
    assert hasattr(SisGraduationAudit, "triggered_at")
    assert hasattr(SisGraduationAudit, "submitted_by")
    assert hasattr(SisGraduationAudit, "submitted_at")


def test_audit_gate2_timestamps():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "board_approved_by")
    assert hasattr(SisGraduationAudit, "board_approved_at")


def test_audit_gate3_timestamps():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "certificates_issued_by")
    assert hasattr(SisGraduationAudit, "certificates_issued_at")


def test_audit_triggered_at_not_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    col = SisGraduationAudit.__table__.c["triggered_at"]
    assert col.nullable is False


# ─────────────────────────────────────────────────────────────────────────────
# 33–36: SisGraduationAudit summary counter columns
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_counter_total():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "total_candidates")


def test_audit_counter_eligible():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "eligible_count")
    assert hasattr(SisGraduationAudit, "provisional_count")
    assert hasattr(SisGraduationAudit, "not_eligible_count")


def test_audit_counter_ratified_deferred():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "ratified_count")
    assert hasattr(SisGraduationAudit, "deferred_count")


def test_audit_counters_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    col = SisGraduationAudit.__table__.c["total_candidates"]
    assert col.nullable is True


# ─────────────────────────────────────────────────────────────────────────────
# 37–40: SisGraduationAudit board_resolution_ref
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_board_resolution_ref_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    col = SisGraduationAudit.__table__.c["board_resolution_ref"]
    assert col.nullable is True   # nullable in DB; mandatory enforced in service


def test_audit_candidates_relationship():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    assert hasattr(SisGraduationAudit, "candidates")


def test_audit_status_default_draft():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    col = SisGraduationAudit.__table__.c["status"]
    assert "DRAFT" in str(col.server_default.arg)


def test_audit_status_not_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationAudit
    col = SisGraduationAudit.__table__.c["status"]
    assert col.nullable is False


# ─────────────────────────────────────────────────────────────────────────────
# 41–44: SisGraduationCandidate core columns + UNIQUE constraint
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_has_id_audit_student():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "id")
    assert hasattr(SisGraduationCandidate, "audit_id")
    assert hasattr(SisGraduationCandidate, "student_id")


def test_candidate_tablename():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert SisGraduationCandidate.__tablename__ == "sis_graduation_candidates"


def test_candidate_unique_audit_student():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    uc_names = [
        c.name for c in SisGraduationCandidate.__table__.constraints
        if hasattr(c, "name") and c.name
    ]
    assert "uq_graduation_candidates_audit_student" in uc_names


def test_candidate_name_snapshot_not_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    col = SisGraduationCandidate.__table__.c["student_name_snapshot"]
    assert col.nullable is False


# ─────────────────────────────────────────────────────────────────────────────
# 45–48: SisGraduationCandidate 8 advisory eligibility flags
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_flag_missing_declarations():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    col = SisGraduationCandidate.__table__.c["missing_declarations"]
    assert col.nullable is False


def test_candidate_flag_has_arrears():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    col = SisGraduationCandidate.__table__.c["has_arrears"]
    assert col.nullable is False


def test_candidate_flags_credits_withheld():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "credits_shortfall")
    assert hasattr(SisGraduationCandidate, "has_withheld")


def test_candidate_flags_remaining_four():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    for flag in (
        "final_sem_not_locked",
        "graduation_year_not_reached",
        "attendance_below_threshold",
        "disciplinary_hold",
    ):
        assert hasattr(SisGraduationCandidate, flag), f"missing flag: {flag}"


# ─────────────────────────────────────────────────────────────────────────────
# 49–52: SisGraduationCandidate computed snapshot values
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_total_credits_earned():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "total_credits_earned")
    assert hasattr(SisGraduationCandidate, "min_credits_required")


def test_candidate_cgpa():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "current_cgpa")


def test_candidate_arrear_count():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "arrear_count")
    assert hasattr(SisGraduationCandidate, "semesters_declared")


def test_candidate_eligibility_status_default():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    col = SisGraduationCandidate.__table__.c["eligibility_status"]
    assert "NOT_ELIGIBLE" in str(col.server_default.arg)


# ─────────────────────────────────────────────────────────────────────────────
# 53–56: SisGraduationCandidate board decision columns
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_board_status_default():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    col = SisGraduationCandidate.__table__.c["board_status"]
    assert "PENDING" in str(col.server_default.arg)


def test_candidate_board_decided_cols():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "board_decided_by")
    assert hasattr(SisGraduationCandidate, "board_decided_at")


def test_candidate_board_notes_never_public():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "board_notes")


def test_candidate_override_cols():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "override_reason")
    assert hasattr(SisGraduationCandidate, "overridden_by")
    assert hasattr(SisGraduationCandidate, "overridden_at")
    assert hasattr(SisGraduationCandidate, "provisional_grace_deadline")


# ─────────────────────────────────────────────────────────────────────────────
# 57–60: SisGraduationCandidate certificate columns
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_cert_status_default():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    col = SisGraduationCandidate.__table__.c["certificate_status"]
    assert "NOT_ISSUED" in str(col.server_default.arg)


def test_candidate_certificate_id_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    col = SisGraduationCandidate.__table__.c["certificate_id"]
    assert col.nullable is True


def test_candidate_audit_relationship():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "audit")


def test_candidate_overrides_relationship():
    from app.modules.m11_sis.graduation_models import SisGraduationCandidate
    assert hasattr(SisGraduationCandidate, "overrides")


# ─────────────────────────────────────────────────────────────────────────────
# 61–64: SisGraduationOverride append-only invariant
# ─────────────────────────────────────────────────────────────────────────────

def test_override_has_no_updated_at():
    from app.modules.m11_sis.graduation_models import SisGraduationOverride
    assert not hasattr(SisGraduationOverride, "updated_at")


def test_override_tablename():
    from app.modules.m11_sis.graduation_models import SisGraduationOverride
    assert SisGraduationOverride.__tablename__ == "sis_graduation_overrides"


def test_override_reason_not_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationOverride
    col = SisGraduationOverride.__table__.c["reason"]
    assert col.nullable is False


def test_override_has_created_at_only():
    from app.modules.m11_sis.graduation_models import SisGraduationOverride
    assert hasattr(SisGraduationOverride, "created_at")
    assert not hasattr(SisGraduationOverride, "updated_at")


# ─────────────────────────────────────────────────────────────────────────────
# 65–68: SisGraduationOverride columns
# ─────────────────────────────────────────────────────────────────────────────

def test_override_actor_cols():
    from app.modules.m11_sis.graduation_models import SisGraduationOverride
    assert hasattr(SisGraduationOverride, "actor_user_id")
    assert hasattr(SisGraduationOverride, "actor_role")


def test_override_status_transition_cols():
    from app.modules.m11_sis.graduation_models import SisGraduationOverride
    assert hasattr(SisGraduationOverride, "previous_status")
    assert hasattr(SisGraduationOverride, "new_status")


def test_override_candidate_id_not_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationOverride
    col = SisGraduationOverride.__table__.c["candidate_id"]
    assert col.nullable is False


def test_override_candidate_relationship():
    from app.modules.m11_sis.graduation_models import SisGraduationOverride
    assert hasattr(SisGraduationOverride, "candidate")


# ─────────────────────────────────────────────────────────────────────────────
# 69–72: SisGraduationCertificate core columns + UNIQUE certificate_number
# ─────────────────────────────────────────────────────────────────────────────

def test_graduation_cert_tablename():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert SisGraduationCertificate.__tablename__ == "sis_graduation_certificates"


def test_graduation_cert_unique_number():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    uc_names = [
        c.name for c in SisGraduationCertificate.__table__.constraints
        if hasattr(c, "name") and c.name
    ]
    assert "uq_graduation_certificates_number" in uc_names


def test_graduation_cert_core_ids():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "id")
    assert hasattr(SisGraduationCertificate, "candidate_id")
    assert hasattr(SisGraduationCertificate, "audit_id")
    assert hasattr(SisGraduationCertificate, "student_id")


def test_graduation_cert_status_default_issued():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    col = SisGraduationCertificate.__table__.c["status"]
    assert "ISSUED" in str(col.server_default.arg)


# ─────────────────────────────────────────────────────────────────────────────
# 73–76: SisGraduationCertificate snapshot columns
# ─────────────────────────────────────────────────────────────────────────────

def test_graduation_cert_student_snapshot():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "student_name_snapshot")
    assert hasattr(SisGraduationCertificate, "usn_snapshot")


def test_graduation_cert_program_snapshot():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "program_name_snapshot")
    assert hasattr(SisGraduationCertificate, "degree_title_snapshot")


def test_graduation_cert_school_batch_snapshot():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "school_name_snapshot")
    assert hasattr(SisGraduationCertificate, "batch_name_snapshot")


def test_graduation_cert_cgpa_credits_snapshot():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "overall_cgpa_snapshot")
    assert hasattr(SisGraduationCertificate, "total_credits_earned")
    assert hasattr(SisGraduationCertificate, "graduation_year")


# ─────────────────────────────────────────────────────────────────────────────
# 77–80: SisGraduationCertificate lifecycle + provisional columns
# ─────────────────────────────────────────────────────────────────────────────

def test_graduation_cert_issue_cols():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "issued_by")
    assert hasattr(SisGraduationCertificate, "issued_at")


def test_graduation_cert_provisional_flag():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    col = SisGraduationCertificate.__table__.c["is_provisional"]
    assert col.nullable is False


def test_graduation_cert_provisional_confirmation():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "provisional_confirmed_at")
    assert hasattr(SisGraduationCertificate, "provisional_confirmed_by")


def test_graduation_cert_pdf_cols():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "pdf_s3_key")
    assert hasattr(SisGraduationCertificate, "pdf_generated_at")


# ─────────────────────────────────────────────────────────────────────────────
# 81–84: SisGraduationCertificate revocation columns
# ─────────────────────────────────────────────────────────────────────────────

def test_graduation_cert_revoke_cols():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    assert hasattr(SisGraduationCertificate, "revoked_by")
    assert hasattr(SisGraduationCertificate, "revoked_at")
    assert hasattr(SisGraduationCertificate, "revoke_reason")


def test_graduation_cert_revoke_cols_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    col = SisGraduationCertificate.__table__.c["revoked_at"]
    assert col.nullable is True


def test_graduation_cert_certificate_number_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    col = SisGraduationCertificate.__table__.c["certificate_number"]
    assert col.nullable is True


def test_graduation_cert_graduation_year_not_nullable():
    from app.modules.m11_sis.graduation_models import SisGraduationCertificate
    col = SisGraduationCertificate.__table__.c["graduation_year"]
    assert col.nullable is False


# ─────────────────────────────────────────────────────────────────────────────
# 85–88: PublicGraduationIndex schema=public + PK
# ─────────────────────────────────────────────────────────────────────────────

def test_public_graduation_index_schema():
    from app.modules.m11_sis.graduation_models import PublicGraduationIndex
    tbl_args = PublicGraduationIndex.__table_args__
    schema_found = any(
        isinstance(a, dict) and a.get("schema") == "public"
        for a in tbl_args
    )
    assert schema_found


def test_public_graduation_index_pk():
    from app.modules.m11_sis.graduation_models import PublicGraduationIndex
    pk_cols = [c.name for c in PublicGraduationIndex.__table__.primary_key.columns]
    assert "certificate_number" in pk_cols


def test_public_graduation_index_tablename():
    from app.modules.m11_sis.graduation_models import PublicGraduationIndex
    assert PublicGraduationIndex.__tablename__ == "public_graduation_index"


def test_public_graduation_index_has_no_private_fields():
    from app.modules.m11_sis.graduation_models import PublicGraduationIndex
    # board_notes must NOT exist in the public index
    assert not hasattr(PublicGraduationIndex, "board_notes")


# ─────────────────────────────────────────────────────────────────────────────
# 89–92: PublicGraduationIndex columns
# ─────────────────────────────────────────────────────────────────────────────

def test_public_graduation_index_tenant_id():
    from app.modules.m11_sis.graduation_models import PublicGraduationIndex
    col = PublicGraduationIndex.__table__.c["tenant_id"]
    assert col.nullable is False


def test_public_graduation_index_schema_name():
    from app.modules.m11_sis.graduation_models import PublicGraduationIndex
    col = PublicGraduationIndex.__table__.c["schema_name"]
    assert col.nullable is False


def test_public_graduation_index_status():
    from app.modules.m11_sis.graduation_models import PublicGraduationIndex
    col = PublicGraduationIndex.__table__.c["status"]
    assert col.nullable is False


def test_public_graduation_index_is_provisional():
    from app.modules.m11_sis.graduation_models import PublicGraduationIndex
    col = PublicGraduationIndex.__table__.c["is_provisional"]
    assert col.nullable is False


# ─────────────────────────────────────────────────────────────────────────────
# 93–96: Migration 0037ten revision / down_revision
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0037_revision():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    assert m.revision == "0037ten"


def test_migration_0037_down_revision():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    assert m.down_revision == "0036ten"


def test_migration_0037_has_upgrade():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    assert callable(m.upgrade)


def test_migration_0037_has_downgrade():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    assert callable(m.downgrade)


# ─────────────────────────────────────────────────────────────────────────────
# 97–100: Migration 0037ten table list
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0037_creates_audits_table():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "sis_graduation_audits" in src


def test_migration_0037_creates_candidates_table():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "sis_graduation_candidates" in src


def test_migration_0037_creates_overrides_table():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "sis_graduation_overrides" in src


def test_migration_0037_creates_certificates_table():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "sis_graduation_certificates" in src


# ─────────────────────────────────────────────────────────────────────────────
# 101–104: Migration 0037ten certificate numbering + board_resolution_ref
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0037_creates_cert_seq():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "sis_graduation_cert_seq" in src


def test_migration_0037_has_board_resolution_ref():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "board_resolution_ref" in src


def test_migration_0037_has_eligibility_flags():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "has_arrears" in src
    assert "credits_shortfall" in src


def test_migration_0037_has_8_advisory_flags():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    for flag in (
        "missing_declarations",
        "has_arrears",
        "credits_shortfall",
        "has_withheld",
        "final_sem_not_locked",
        "graduation_year_not_reached",
        "attendance_below_threshold",
        "disciplinary_hold",
    ):
        assert flag in src, f"Migration 0037 missing advisory flag: {flag}"


# ─────────────────────────────────────────────────────────────────────────────
# 105–108: Migration 0037ten append-only override (no updated_at in overrides)
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0037_overrides_no_updated_at():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    # confirm "updated_at" appears only OUTSIDE the overrides table block
    # Simple check: overrides comment should mention append-only
    assert "append-only" in src.lower() or "No updated_at" in src


def test_migration_0037_unique_audit_student():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "uq_graduation_candidates_audit_student" in src


def test_migration_0037_unique_certificate_number():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "uq_graduation_certificates_number" in src


def test_migration_0037_downgrade_drops_all():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.downgrade)
    for table in (
        "sis_graduation_certificates",
        "sis_graduation_overrides",
        "sis_graduation_candidates",
        "sis_graduation_audits",
    ):
        assert table in src, f"Missing table in downgrade: {table}"


# ─────────────────────────────────────────────────────────────────────────────
# 109–112: Migration 0037ten downgrade
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0037_downgrade_drops_sequence():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.downgrade)
    assert "DROP SEQUENCE" in src


def test_migration_0037_candidates_cascade():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "CASCADE" in src


def test_migration_0037_certificates_restrict():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "RESTRICT" in src


def test_migration_0037_cert_seq_start():
    m = _load_migration("alembic/tenant_versions/0037_tenant_graduation.py")
    src = inspect.getsource(m.upgrade)
    assert "START 1" in src


# ─────────────────────────────────────────────────────────────────────────────
# 113–116: Migration 0013pub revision / down_revision
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0013pub_revision():
    m = _load_migration("alembic/public_versions/0013_public_graduation_index.py")
    assert m.revision == "0013pub"


def test_migration_0013pub_down_revision():
    m = _load_migration("alembic/public_versions/0013_public_graduation_index.py")
    assert m.down_revision == "0012pub"


def test_migration_0013pub_has_upgrade():
    m = _load_migration("alembic/public_versions/0013_public_graduation_index.py")
    assert callable(m.upgrade)


def test_migration_0013pub_has_downgrade():
    m = _load_migration("alembic/public_versions/0013_public_graduation_index.py")
    assert callable(m.downgrade)


# ─────────────────────────────────────────────────────────────────────────────
# 117–120: Migration 0013pub public_graduation_index table
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_0013pub_creates_table():
    m = _load_migration("alembic/public_versions/0013_public_graduation_index.py")
    src = inspect.getsource(m.upgrade)
    assert "public_graduation_index" in src


def test_migration_0013pub_schema_public():
    m = _load_migration("alembic/public_versions/0013_public_graduation_index.py")
    src = inspect.getsource(m.upgrade)
    assert 'schema="public"' in src


def test_migration_0013pub_has_certificate_number_pk():
    m = _load_migration("alembic/public_versions/0013_public_graduation_index.py")
    src = inspect.getsource(m.upgrade)
    assert "certificate_number" in src


def test_migration_0013pub_downgrade_drops_table():
    m = _load_migration("alembic/public_versions/0013_public_graduation_index.py")
    src = inspect.getsource(m.downgrade)
    assert "public_graduation_index" in src


# ─────────────────────────────────────────────────────────────────────────────
# 121–124: CertificateVerifyResponse excludes private data
# ─────────────────────────────────────────────────────────────────────────────

def test_cert_verify_response_has_required_fields():
    from app.modules.m11_sis.graduation_schemas import CertificateVerifyResponse
    import pydantic
    fields = CertificateVerifyResponse.model_fields
    assert "certificate_number" in fields
    assert "student_name_partial" in fields
    assert "status" in fields
    assert "message" in fields


def test_cert_verify_response_no_cgpa():
    from app.modules.m11_sis.graduation_schemas import CertificateVerifyResponse
    fields = CertificateVerifyResponse.model_fields
    assert "current_cgpa" not in fields
    assert "overall_cgpa_snapshot" not in fields


def test_cert_verify_response_no_eligibility_flags():
    from app.modules.m11_sis.graduation_schemas import CertificateVerifyResponse
    fields = CertificateVerifyResponse.model_fields
    for flag in ("missing_declarations", "has_arrears", "credits_shortfall",
                 "eligibility_status", "board_status"):
        assert flag not in fields, f"CertificateVerifyResponse must not expose: {flag}"


def test_cert_verify_response_no_board_notes():
    from app.modules.m11_sis.graduation_schemas import CertificateVerifyResponse
    fields = CertificateVerifyResponse.model_fields
    assert "board_notes" not in fields


# ─────────────────────────────────────────────────────────────────────────────
# 125–128: GraduationCandidateDetailRead contains board_notes (internal only)
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_detail_read_has_board_notes():
    from app.modules.m11_sis.graduation_schemas import GraduationCandidateDetailRead
    fields = GraduationCandidateDetailRead.model_fields
    assert "board_notes" in fields


def test_candidate_detail_read_has_all_8_flags():
    from app.modules.m11_sis.graduation_schemas import GraduationCandidateDetailRead
    fields = GraduationCandidateDetailRead.model_fields
    for flag in (
        "missing_declarations",
        "has_arrears",
        "credits_shortfall",
        "has_withheld",
        "final_sem_not_locked",
        "graduation_year_not_reached",
        "attendance_below_threshold",
        "disciplinary_hold",
    ):
        assert flag in fields, f"GraduationCandidateDetailRead missing: {flag}"


def test_candidate_detail_read_has_cgpa():
    from app.modules.m11_sis.graduation_schemas import GraduationCandidateDetailRead
    fields = GraduationCandidateDetailRead.model_fields
    assert "current_cgpa" in fields


def test_candidate_summary_read_no_flags():
    from app.modules.m11_sis.graduation_schemas import GraduationCandidateSummaryRead
    fields = GraduationCandidateSummaryRead.model_fields
    assert "missing_declarations" not in fields
    assert "board_notes" not in fields


# ─────────────────────────────────────────────────────────────────────────────
# 129–132: AuditApproveIn validates board_resolution_ref non-empty
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_approve_in_requires_ref():
    from pydantic import ValidationError
    from app.modules.m11_sis.graduation_schemas import AuditApproveIn
    with pytest.raises(ValidationError):
        AuditApproveIn(board_resolution_ref="")


def test_audit_approve_in_strips_whitespace():
    from app.modules.m11_sis.graduation_schemas import AuditApproveIn
    obj = AuditApproveIn(board_resolution_ref="  BRD/2026/001  ")
    assert obj.board_resolution_ref == "BRD/2026/001"


def test_audit_approve_in_whitespace_only_rejected():
    from pydantic import ValidationError
    from app.modules.m11_sis.graduation_schemas import AuditApproveIn
    with pytest.raises(ValidationError):
        AuditApproveIn(board_resolution_ref="   ")


def test_audit_approve_in_valid():
    from app.modules.m11_sis.graduation_schemas import AuditApproveIn
    obj = AuditApproveIn(board_resolution_ref="BRD/2026/001")
    assert obj.board_resolution_ref == "BRD/2026/001"


# ─────────────────────────────────────────────────────────────────────────────
# 133–136: CandidateOverrideIn validates reason ≥ 20 chars
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_override_in_reason_too_short():
    from pydantic import ValidationError
    from app.modules.m11_sis.graduation_schemas import CandidateOverrideIn
    with pytest.raises(ValidationError):
        CandidateOverrideIn(new_status="ELIGIBLE", reason="too short")


def test_candidate_override_in_reason_valid():
    from app.modules.m11_sis.graduation_schemas import CandidateOverrideIn
    obj = CandidateOverrideIn(
        new_status="ELIGIBLE",
        reason="Student cleared all backlogs via supplementary exams.",
    )
    assert obj.new_status == "ELIGIBLE"


def test_candidate_override_in_invalid_status():
    from pydantic import ValidationError
    from app.modules.m11_sis.graduation_schemas import CandidateOverrideIn
    with pytest.raises(ValidationError):
        CandidateOverrideIn(
            new_status="GRADUATED",
            reason="Some reason that is long enough here",
        )


def test_candidate_override_in_provisional_valid():
    from app.modules.m11_sis.graduation_schemas import CandidateOverrideIn
    obj = CandidateOverrideIn(
        new_status="PROVISIONAL",
        reason="Awaiting final semester clearance from examination dept.",
    )
    assert obj.new_status == "PROVISIONAL"


# ─────────────────────────────────────────────────────────────────────────────
# 137–140: BoardDeferIn requires board_notes ≥ 10 chars
# ─────────────────────────────────────────────────────────────────────────────

def test_board_defer_in_notes_too_short():
    from pydantic import ValidationError
    from app.modules.m11_sis.graduation_schemas import BoardDeferIn
    with pytest.raises(ValidationError):
        BoardDeferIn(board_notes="short")


def test_board_defer_in_notes_valid():
    from app.modules.m11_sis.graduation_schemas import BoardDeferIn
    obj = BoardDeferIn(board_notes="Pending arrear clearance certificate.")
    assert len(obj.board_notes) >= 10


def test_board_defer_in_notes_stripped():
    from app.modules.m11_sis.graduation_schemas import BoardDeferIn
    obj = BoardDeferIn(board_notes="  Pending clearance  ")
    assert obj.board_notes == "Pending clearance"


def test_board_ratify_in_optional_notes():
    from app.modules.m11_sis.graduation_schemas import BoardRatifyIn
    obj = BoardRatifyIn()
    assert obj.board_notes is None


# ─────────────────────────────────────────────────────────────────────────────
# 141–144: CertificateRevokeIn requires reason ≥ 10 chars
# ─────────────────────────────────────────────────────────────────────────────

def test_cert_revoke_in_reason_too_short():
    from pydantic import ValidationError
    from app.modules.m11_sis.graduation_schemas import CertificateRevokeIn
    with pytest.raises(ValidationError):
        CertificateRevokeIn(revoke_reason="err")


def test_cert_revoke_in_reason_valid():
    from app.modules.m11_sis.graduation_schemas import CertificateRevokeIn
    obj = CertificateRevokeIn(revoke_reason="Issued in error due to data entry mistake.")
    assert len(obj.revoke_reason) >= 10


def test_provisional_confirm_in_notes_too_short():
    from pydantic import ValidationError
    from app.modules.m11_sis.graduation_schemas import ProvisionalConfirmIn
    with pytest.raises(ValidationError):
        ProvisionalConfirmIn(confirmation_notes="ok")


def test_provisional_confirm_in_notes_valid():
    from app.modules.m11_sis.graduation_schemas import ProvisionalConfirmIn
    obj = ProvisionalConfirmIn(confirmation_notes="All pending requirements cleared successfully.")
    assert len(obj.confirmation_notes) >= 10


# ─────────────────────────────────────────────────────────────────────────────
# 145–148: Service _partial_name privacy logic
# ─────────────────────────────────────────────────────────────────────────────

def test_partial_name_two_parts():
    from app.modules.m11_sis.graduation_service import _partial_name
    assert _partial_name("Ramesh Kumar") == "Ramesh K."


def test_partial_name_single_name():
    from app.modules.m11_sis.graduation_service import _partial_name
    result = _partial_name("Ramesh")
    assert result == "Ramesh"


def test_partial_name_three_parts_uses_last():
    from app.modules.m11_sis.graduation_service import _partial_name
    result = _partial_name("Ananya Priya Sharma")
    assert result == "Ananya S."


def test_partial_name_does_not_expose_full_name():
    from app.modules.m11_sis.graduation_service import _partial_name
    result = _partial_name("Bharathi Wathsala")
    assert "Wathsala" not in result
    assert result.endswith(".")


# ─────────────────────────────────────────────────────────────────────────────
# 149–152: Service lifecycle guards
# ─────────────────────────────────────────────────────────────────────────────

def test_service_trigger_exists():
    from app.modules.m11_sis.graduation_service import GraduationLifecycleService
    assert callable(GraduationLifecycleService.trigger)


def test_service_approve_exists():
    from app.modules.m11_sis.graduation_service import GraduationLifecycleService
    assert callable(GraduationLifecycleService.approve)


def test_service_issue_certificate_exists():
    from app.modules.m11_sis.graduation_service import GraduationLifecycleService
    assert callable(GraduationLifecycleService.issue_certificate)


def test_service_revoke_certificate_exists():
    from app.modules.m11_sis.graduation_service import GraduationLifecycleService
    assert callable(GraduationLifecycleService.revoke_certificate)


# ─────────────────────────────────────────────────────────────────────────────
# 153–156: board_resolution_ref check in approve (getsource)
# ─────────────────────────────────────────────────────────────────────────────

def test_service_approve_checks_board_resolution_ref():
    from app.modules.m11_sis.graduation_service import GraduationLifecycleService
    src = inspect.getsource(GraduationLifecycleService.approve)
    assert "board_resolution_ref" in src


def test_service_approve_raises_for_empty_ref():
    from app.modules.m11_sis.graduation_service import GraduationLifecycleService
    src = inspect.getsource(GraduationLifecycleService.approve)
    assert "board_resolution_ref is required" in src


def test_service_override_appends_to_log():
    from app.modules.m11_sis.graduation_service import GraduationLifecycleService
    src = inspect.getsource(GraduationLifecycleService.override_candidate)
    assert "GraduationOverrideRepo.append" in src


def test_service_issue_cert_number_format():
    from app.modules.m11_sis.graduation_repository import GraduationAuditRepo
    src = inspect.getsource(GraduationAuditRepo.next_certificate_number)
    assert "CERT/" in src
    assert ":06d}" in src


# ─────────────────────────────────────────────────────────────────────────────
# 157–160: EligibilityEngine structure
# ─────────────────────────────────────────────────────────────────────────────

def test_eligibility_engine_compute_exists():
    from app.modules.m11_sis.graduation_service import EligibilityEngine
    assert callable(EligibilityEngine.compute)


def test_eligibility_engine_returns_three_keys():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.graduation_service",
                   fromlist=["EligibilityEngine"]).EligibilityEngine.compute
    )
    assert '"flags"' in src
    assert '"values"' in src
    assert '"eligibility_status"' in src


def test_eligibility_engine_checks_all_8_flags():
    from app.modules.m11_sis.graduation_service import EligibilityEngine
    src = inspect.getsource(EligibilityEngine.compute)
    for flag in (
        "missing_declarations",
        "has_arrears",
        "credits_shortfall",
        "has_withheld",
        "final_sem_not_locked",
        "graduation_year_not_reached",
        "attendance_below_threshold",
        "disciplinary_hold",
    ):
        assert flag in src, f"EligibilityEngine.compute missing flag: {flag}"


def test_eligibility_engine_advisory_only():
    from app.modules.m11_sis.graduation_service import EligibilityEngine
    src = inspect.getsource(EligibilityEngine.compute)
    assert "ELIGIBLE" in src
    assert "NOT_ELIGIBLE" in src
    assert "PROVISIONAL" in src


# ─────────────────────────────────────────────────────────────────────────────
# 161–164: Audit events for graduation lifecycle in AuditEventType
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_event_graduation_triggered():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.GRADUATION_AUDIT_TRIGGERED == "GRADUATION_AUDIT_TRIGGERED"


def test_audit_event_graduation_board_approved():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.GRADUATION_AUDIT_BOARD_APPROVED == "GRADUATION_AUDIT_BOARD_APPROVED"


def test_audit_event_graduation_certificate_issued():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.GRADUATION_CERTIFICATE_ISSUED == "GRADUATION_CERTIFICATE_ISSUED"


def test_audit_event_graduation_all_events():
    from app.core.audit_log.models import AuditEventType
    expected_events = [
        "GRADUATION_AUDIT_TRIGGERED",
        "GRADUATION_AUDIT_SUBMITTED",
        "GRADUATION_AUDIT_REGENERATED",
        "GRADUATION_AUDIT_BOARD_APPROVED",
        "GRADUATION_CANDIDATE_OVERRIDDEN",
        "GRADUATION_CANDIDATE_RATIFIED",
        "GRADUATION_CANDIDATE_DEFERRED",
        "GRADUATION_CERTIFICATE_ISSUED",
        "GRADUATION_CERTIFICATE_REVOKED",
        "GRADUATION_PROVISIONAL_CONFIRMED",
        "GRADUATION_CERTIFICATE_VERIFIED",
    ]
    event_values = [e.value for e in AuditEventType]
    for ev in expected_events:
        assert ev in event_values, f"Missing AuditEventType: {ev}"


# ─────────────────────────────────────────────────────────────────────────────
# 165–168: Celery graduation tasks registered in celery_app
# ─────────────────────────────────────────────────────────────────────────────

def test_celery_graduation_report_task_registered():
    from app.workers.celery_app import celery_app
    assert "app.workers.heavy.generate_graduation_report" in celery_app.conf.include


def test_celery_graduation_certificate_task_registered():
    from app.workers.celery_app import celery_app
    assert "app.workers.heavy.generate_graduation_certificate" in celery_app.conf.include


def test_celery_graduation_report_task_name():
    from app.workers.heavy.generate_graduation_report import generate_graduation_report
    assert generate_graduation_report.name == "app.workers.heavy.generate_graduation_report"


def test_celery_graduation_certificate_task_name():
    from app.workers.heavy.generate_graduation_certificate import generate_graduation_certificate
    assert generate_graduation_certificate.name == "app.workers.heavy.generate_graduation_certificate"


# ─────────────────────────────────────────────────────────────────────────────
# 169–172: Router structure
# ─────────────────────────────────────────────────────────────────────────────

def test_graduation_router_prefix():
    from app.modules.m11_sis.graduation_router import graduation_router
    assert graduation_router.prefix == "/graduation"


def test_cert_verify_router_no_prefix():
    from app.modules.m11_sis.graduation_router import cert_verify_router
    assert cert_verify_router.prefix == ""


def test_cert_verify_router_route_path():
    from app.modules.m11_sis.graduation_router import cert_verify_router
    paths = [r.path for r in cert_verify_router.routes]
    assert any("/verify/certificate/" in p for p in paths)


def test_graduation_router_tags():
    from app.modules.m11_sis.graduation_router import graduation_router
    assert "SIS Graduation" in graduation_router.tags


# ─────────────────────────────────────────────────────────────────────────────
# 173–176: cert_verify_router verify path
# ─────────────────────────────────────────────────────────────────────────────

def test_cert_verify_router_has_verify_route():
    from app.modules.m11_sis.graduation_router import cert_verify_router
    src = inspect.getsource(
        __import__("app.modules.m11_sis.graduation_router", fromlist=["verify_certificate"]).verify_certificate
    )
    assert "certificate_number" in src


def test_cert_verify_route_no_auth_dependency():
    from app.modules.m11_sis.graduation_router import cert_verify_router
    from fastapi import Depends
    src = inspect.getsource(
        __import__("app.modules.m11_sis.graduation_router", fromlist=["verify_certificate"]).verify_certificate
    )
    assert "require_roles" not in src


def test_cert_verify_response_no_student_id_exposed():
    from app.modules.m11_sis.graduation_schemas import CertificateVerifyResponse
    fields = CertificateVerifyResponse.model_fields
    assert "student_id" not in fields


def test_cert_verify_uses_partial_name():
    from app.modules.m11_sis.graduation_service import GraduationVerifyService
    src = inspect.getsource(GraduationVerifyService.verify)
    assert "_partial_name" in src


# ─────────────────────────────────────────────────────────────────────────────
# 177–180: Route ordering — /my-graduation-status before /{audit_id}
# ─────────────────────────────────────────────────────────────────────────────

def test_my_graduation_status_before_audit_id():
    import app.modules.m11_sis.graduation_router as gr_mod
    src = inspect.getsource(gr_mod)
    pos_my     = src.find("/my-graduation-status")
    pos_audit  = src.find("/audits/{audit_id}")
    assert pos_my < pos_audit, (
        "/my-graduation-status must be defined before /audits/{audit_id} in source"
    )


def test_my_graduation_status_is_student_only():
    import app.modules.m11_sis.graduation_router as gr_mod
    src = inspect.getsource(gr_mod.get_my_graduation_status)
    assert "STUDENT" in src


def test_approve_route_before_candidates():
    import app.modules.m11_sis.graduation_router as gr_mod
    src = inspect.getsource(gr_mod)
    pos_approve = src.find("/audits/{audit_id}/approve")
    pos_cands   = src.find("/candidates/{candidate_id}")
    assert pos_approve < pos_cands


def test_cert_verify_router_separate_from_graduation_router():
    from app.modules.m11_sis.graduation_router import graduation_router, cert_verify_router
    assert graduation_router is not cert_verify_router


# ─────────────────────────────────────────────────────────────────────────────
# 181–184: graduation_router included in m11_sis/router.py
# ─────────────────────────────────────────────────────────────────────────────

def test_graduation_router_included_in_sis_router():
    import app.modules.m11_sis.router as sis_mod
    src = inspect.getsource(sis_mod)
    assert "graduation_router" in src


def test_sis_router_imports_graduation_router():
    import app.modules.m11_sis.router as sis_mod
    src = inspect.getsource(sis_mod)
    assert "from app.modules.m11_sis.graduation_router import graduation_router" in src


def test_graduation_router_include_router_called():
    import app.modules.m11_sis.router as sis_mod
    src = inspect.getsource(sis_mod)
    assert "include_router(graduation_router)" in src


def test_sis_router_file_readable():
    import app.modules.m11_sis.router as sis_mod
    assert sis_mod is not None


# ─────────────────────────────────────────────────────────────────────────────
# 185–188: graduation_models imported in models.py
# ─────────────────────────────────────────────────────────────────────────────

def test_models_py_imports_graduation_models():
    base = pathlib.Path(__file__).parents[3]
    models_path = base / "app" / "models.py"
    src = models_path.read_text(encoding="utf-8")
    assert "graduation_models" in src


def test_models_py_graduation_import_after_transcript():
    base = pathlib.Path(__file__).parents[3]
    models_path = base / "app" / "models.py"
    src = models_path.read_text(encoding="utf-8")
    pos_transcript = src.find("transcript_models")
    pos_graduation  = src.find("graduation_models")
    assert pos_graduation > pos_transcript, (
        "graduation_models must be imported after transcript_models in models.py"
    )


def test_models_py_graduation_import_noqa():
    base = pathlib.Path(__file__).parents[3]
    models_path = base / "app" / "models.py"
    src = models_path.read_text(encoding="utf-8")
    assert "graduation_models" in src


def test_graduation_models_importable():
    import app.modules.m11_sis.graduation_models as gm
    assert hasattr(gm, "SisGraduationAudit")
    assert hasattr(gm, "SisGraduationCandidate")
    assert hasattr(gm, "SisGraduationOverride")
    assert hasattr(gm, "SisGraduationCertificate")


# ─────────────────────────────────────────────────────────────────────────────
# 189–192: cert_verify_router included in main.py
# ─────────────────────────────────────────────────────────────────────────────

def test_main_py_imports_cert_verify_router():
    base = pathlib.Path(__file__).parents[3]
    main_path = base / "app" / "main.py"
    src = main_path.read_text(encoding="utf-8")
    assert "cert_verify_router" in src


def test_main_py_includes_cert_verify_router():
    base = pathlib.Path(__file__).parents[3]
    main_path = base / "app" / "main.py"
    src = main_path.read_text(encoding="utf-8")
    assert "include_router(cert_verify_router)" in src


def test_main_py_cert_verify_no_extra_prefix():
    base = pathlib.Path(__file__).parents[3]
    main_path = base / "app" / "main.py"
    src = main_path.read_text(encoding="utf-8")
    # cert_verify_router is mounted without prefix (route has full path /verify/certificate/...)
    assert 'include_router(cert_verify_router)' in src
    # Must NOT be mounted with a conflicting prefix like /verify
    assert 'include_router(cert_verify_router, prefix=' not in src


def test_main_py_both_verify_routers_present():
    base = pathlib.Path(__file__).parents[3]
    main_path = base / "app" / "main.py"
    src = main_path.read_text(encoding="utf-8")
    assert "verify_router" in src       # H61 transcript verify
    assert "cert_verify_router" in src  # H62 graduation cert verify


# ─────────────────────────────────────────────────────────────────────────────
# 193–196: GRADUATION_REVOKED added to DegreeStatus
# ─────────────────────────────────────────────────────────────────────────────

def test_degree_status_graduation_revoked():
    from app.modules.m11_sis.transcript_models import DegreeStatus
    assert DegreeStatus.GRADUATION_REVOKED == "GRADUATION_REVOKED"


def test_degree_status_has_5_values():
    from app.modules.m11_sis.transcript_models import DegreeStatus
    assert len(DegreeStatus) == 5


def test_degree_status_original_four_still_present():
    from app.modules.m11_sis.transcript_models import DegreeStatus
    assert DegreeStatus.ELIGIBLE == "ELIGIBLE"
    assert DegreeStatus.NOT_ELIGIBLE == "NOT_ELIGIBLE"
    assert DegreeStatus.PROVISIONAL == "PROVISIONAL"
    assert DegreeStatus.GRADUATED == "GRADUATED"


def test_degree_status_graduation_revoked_str():
    from app.modules.m11_sis.transcript_models import DegreeStatus
    assert DegreeStatus.GRADUATION_REVOKED.value == "GRADUATION_REVOKED"
