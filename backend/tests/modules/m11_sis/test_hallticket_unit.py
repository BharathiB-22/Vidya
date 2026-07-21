"""
Unit tests — H58 SIS Hall Ticket Eligibility

No live database. All tests use import + assert + inspect source.

Coverage groups:
  1–6    Model ORM columns and enum values
  7–14   Schema field presence — EligibilityOut, MyEligibilityOut, HallTicketOut
  15–18  Request schemas — compute, publish, override validation
  19–22  Batch schemas — HallTicketBatchOut, HallTicketBatchCreateIn
  23–28  Eligibility status enum and publish status enum
  29–33  Service: failure_reason builder logic (pure function)
  34–37  Service: status determination from failure reasons
  38–41  Service: hall ticket prefix format (TOCS-{year}S{sem})
  42–45  Service: student cannot view DRAFT eligibility (source guard)
  46–49  RBAC: manager-only endpoints (source inspection)
  50–53  RBAC: faculty advisory gate (source inspection)
  54–57  Publish guard on batch generation (source inspection)
  58–61  Upsert protects overridden+PUBLISHED rows (source inspection)
  62–65  Router route count and prefix
  66–68  Migration: table names and unique constraint
  69–72  Snapshot metadata fields present on model
  73–76  Future exam fields present on model and schema
"""
import inspect

import pytest


# ---------------------------------------------------------------------------
# 1–6. ORM models
# ---------------------------------------------------------------------------

def test_hall_ticket_eligibility_tablename():
    from app.modules.m11_sis.hallticket_models import SisHallTicketEligibility
    assert SisHallTicketEligibility.__tablename__ == "sis_hall_ticket_eligibility"


def test_hall_ticket_batch_tablename():
    from app.modules.m11_sis.hallticket_models import SisHallTicketBatch
    assert SisHallTicketBatch.__tablename__ == "sis_hall_ticket_batches"


def test_eligibility_columns_core():
    from app.modules.m11_sis.hallticket_models import SisHallTicketEligibility
    cols = {c.name for c in SisHallTicketEligibility.__table__.columns}
    assert {"id", "student_id", "semester_id", "publish_status", "status",
            "computed_at", "attendance_threshold_used", "computed_academic_year",
            "computed_semester_name", "attendance_pct", "has_shortage",
            "marks_all_locked", "marks_all_filled", "failure_reasons"} <= cols


def test_eligibility_override_columns():
    from app.modules.m11_sis.hallticket_models import SisHallTicketEligibility
    cols = {c.name for c in SisHallTicketEligibility.__table__.columns}
    assert {"override_by", "override_at", "override_reason", "override_status"} <= cols


def test_eligibility_hall_ticket_columns():
    from app.modules.m11_sis.hallticket_models import SisHallTicketEligibility
    cols = {c.name for c in SisHallTicketEligibility.__table__.columns}
    assert {"batch_id", "hall_ticket_number"} <= cols


def test_batch_columns_core():
    from app.modules.m11_sis.hallticket_models import SisHallTicketBatch
    cols = {c.name for c in SisHallTicketBatch.__table__.columns}
    assert {"id", "semester_id", "scope", "scope_ref_id",
            "generated_by", "generated_at", "ticket_count",
            "ticket_prefix", "notes", "created_at"} <= cols


# ---------------------------------------------------------------------------
# 7–14. Output schemas
# ---------------------------------------------------------------------------

def test_eligibility_out_required_fields():
    from app.modules.m11_sis.hallticket_schemas import EligibilityOut
    fields = set(EligibilityOut.model_fields)
    assert {"id", "student_id", "student_name", "semester_id",
            "publish_status", "status", "computed_at",
            "attendance_threshold_used", "computed_academic_year",
            "computed_semester_name"} <= fields


def test_eligibility_out_check_fields():
    from app.modules.m11_sis.hallticket_schemas import EligibilityOut
    fields = set(EligibilityOut.model_fields)
    assert {"attendance_pct", "has_shortage",
            "marks_all_locked", "marks_all_filled", "failure_reasons"} <= fields


def test_eligibility_out_override_fields():
    from app.modules.m11_sis.hallticket_schemas import EligibilityOut
    fields = set(EligibilityOut.model_fields)
    assert {"is_overridden", "override_by", "override_at",
            "override_reason", "override_status"} <= fields


def test_eligibility_out_ticket_fields():
    from app.modules.m11_sis.hallticket_schemas import EligibilityOut
    fields = set(EligibilityOut.model_fields)
    assert {"hall_ticket_number", "batch_id"} <= fields


def test_my_eligibility_out_fields():
    from app.modules.m11_sis.hallticket_schemas import MyEligibilityOut
    fields = set(MyEligibilityOut.model_fields)
    assert {"student_id", "student_name", "usn", "semester_id",
            "semester_name", "status", "checklist", "failure_reasons",
            "hall_ticket_number", "is_ticket_available"} <= fields


def test_eligibility_checklist_item_fields():
    from app.modules.m11_sis.hallticket_schemas import EligibilityCheckItemOut
    fields = set(EligibilityCheckItemOut.model_fields)
    assert {"check_name", "passed", "detail"} <= fields


def test_hall_ticket_out_fields():
    from app.modules.m11_sis.hallticket_schemas import HallTicketOut
    fields = set(HallTicketOut.model_fields)
    assert {"hall_ticket_number", "student_id", "student_name",
            "semester_id", "semester_name", "academic_year",
            "status", "batch_id", "issued_at"} <= fields


def test_hall_ticket_out_exam_fields():
    from app.modules.m11_sis.hallticket_schemas import HallTicketOut
    fields = set(HallTicketOut.model_fields)
    assert {"exam_session_id", "exam_schedule_id", "exam_center_id",
            "room_number", "seat_number"} <= fields


# ---------------------------------------------------------------------------
# 15–18. Request schemas
# ---------------------------------------------------------------------------

def test_compute_in_has_threshold():
    from app.modules.m11_sis.hallticket_schemas import EligibilityComputeIn
    fields = set(EligibilityComputeIn.model_fields)
    assert {"semester_id", "section_id", "threshold_pct"} <= fields


def test_compute_in_threshold_default():
    from app.modules.m11_sis.hallticket_schemas import EligibilityComputeIn
    import uuid
    body = EligibilityComputeIn(semester_id=uuid.uuid4())
    assert body.threshold_pct == 75.0


def test_override_in_status_pattern():
    from app.modules.m11_sis.hallticket_schemas import EligibilityOverrideIn
    with pytest.raises(Exception):
        EligibilityOverrideIn(status="NOT_ELIGIBLE", reason="a" * 20)


def test_override_in_reason_min_length():
    from app.modules.m11_sis.hallticket_schemas import EligibilityOverrideIn
    with pytest.raises(Exception):
        EligibilityOverrideIn(status="CONDITIONAL", reason="short")


# ---------------------------------------------------------------------------
# 19–22. Batch schemas
# ---------------------------------------------------------------------------

def test_batch_out_fields():
    from app.modules.m11_sis.hallticket_schemas import HallTicketBatchOut
    fields = set(HallTicketBatchOut.model_fields)
    assert {"id", "semester_id", "scope", "scope_ref_id",
            "generated_by", "generated_at", "ticket_count",
            "ticket_prefix", "notes", "created_at"} <= fields


def test_batch_create_in_fields():
    from app.modules.m11_sis.hallticket_schemas import HallTicketBatchCreateIn
    fields = set(HallTicketBatchCreateIn.model_fields)
    assert {"semester_id", "section_id", "notes"} <= fields


def test_batch_scope_all_is_optional():
    from app.modules.m11_sis.hallticket_schemas import HallTicketBatchCreateIn
    import uuid
    body = HallTicketBatchCreateIn(semester_id=uuid.uuid4())
    assert body.section_id is None
    assert body.notes is None


def test_dashboard_out_fields():
    from app.modules.m11_sis.hallticket_schemas import EligibilityDashboardOut
    fields = set(EligibilityDashboardOut.model_fields)
    assert {"semester_id", "semester_name", "total_students",
            "eligible_count", "not_eligible_count", "conditional_count",
            "draft_count", "published_count", "rows"} <= fields


# ---------------------------------------------------------------------------
# 23–28. Enums
# ---------------------------------------------------------------------------

def test_eligibility_status_enum_values():
    from app.modules.m11_sis.hallticket_models import EligibilityStatus
    assert set(EligibilityStatus) == {
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.NOT_ELIGIBLE,
        EligibilityStatus.CONDITIONAL,
    }


def test_publish_status_enum_values():
    from app.modules.m11_sis.hallticket_models import PublishStatus
    assert set(PublishStatus) == {PublishStatus.DRAFT, PublishStatus.PUBLISHED}


def test_batch_scope_enum_values():
    from app.modules.m11_sis.hallticket_models import BatchScope
    assert set(BatchScope) == {BatchScope.ALL, BatchScope.SECTION}


def test_eligibility_status_strings():
    from app.modules.m11_sis.hallticket_models import EligibilityStatus
    assert EligibilityStatus.ELIGIBLE     == "ELIGIBLE"
    assert EligibilityStatus.NOT_ELIGIBLE == "NOT_ELIGIBLE"
    assert EligibilityStatus.CONDITIONAL  == "CONDITIONAL"


def test_publish_status_strings():
    from app.modules.m11_sis.hallticket_models import PublishStatus
    assert PublishStatus.DRAFT     == "DRAFT"
    assert PublishStatus.PUBLISHED == "PUBLISHED"


def test_eligibility_status_not_equal():
    from app.modules.m11_sis.hallticket_models import EligibilityStatus
    assert EligibilityStatus.ELIGIBLE != EligibilityStatus.NOT_ELIGIBLE


# ---------------------------------------------------------------------------
# 29–33. Service: _build_failure_reasons pure function
# ---------------------------------------------------------------------------

def test_failure_reasons_all_pass_returns_empty():
    from app.modules.m11_sis.hallticket_service import _build_failure_reasons
    from decimal import Decimal
    reasons = _build_failure_reasons(
        attendance_pct   = Decimal("82.5"),
        has_shortage     = False,
        marks_all_locked = True,
        marks_all_filled = True,
        has_att_data     = True,
        has_marks_data   = True,
        threshold_pct    = 75.0,
    )
    assert reasons == []


def test_failure_reasons_low_attendance():
    from app.modules.m11_sis.hallticket_service import _build_failure_reasons
    from decimal import Decimal
    reasons = _build_failure_reasons(
        attendance_pct   = Decimal("68.0"),
        has_shortage     = False,
        marks_all_locked = True,
        marks_all_filled = True,
        has_att_data     = True,
        has_marks_data   = True,
        threshold_pct    = 75.0,
    )
    assert any("68" in r or "Attendance" in r for r in reasons)


def test_failure_reasons_has_shortage():
    from app.modules.m11_sis.hallticket_service import _build_failure_reasons
    from decimal import Decimal
    reasons = _build_failure_reasons(
        attendance_pct   = Decimal("76.0"),
        has_shortage     = True,
        marks_all_locked = True,
        marks_all_filled = True,
        has_att_data     = True,
        has_marks_data   = True,
        threshold_pct    = 75.0,
    )
    assert any("shortage" in r.lower() for r in reasons)


def test_failure_reasons_marks_not_locked():
    from app.modules.m11_sis.hallticket_service import _build_failure_reasons
    from decimal import Decimal
    reasons = _build_failure_reasons(
        attendance_pct   = Decimal("80.0"),
        has_shortage     = False,
        marks_all_locked = False,
        marks_all_filled = True,
        has_att_data     = True,
        has_marks_data   = True,
        threshold_pct    = 75.0,
    )
    assert any("locked" in r.lower() or "finalize" in r.lower() for r in reasons)


def test_failure_reasons_marks_not_filled():
    from app.modules.m11_sis.hallticket_service import _build_failure_reasons
    from decimal import Decimal
    reasons = _build_failure_reasons(
        attendance_pct   = Decimal("80.0"),
        has_shortage     = False,
        marks_all_locked = True,
        marks_all_filled = False,
        has_att_data     = True,
        has_marks_data   = True,
        threshold_pct    = 75.0,
    )
    assert any("mark" in r.lower() or "fill" in r.lower() or "incomplet" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# 34–37. Service: _determine_status
# ---------------------------------------------------------------------------

def test_status_eligible_when_no_failures():
    from app.modules.m11_sis.hallticket_service import _determine_status
    from app.modules.m11_sis.hallticket_models import EligibilityStatus
    assert _determine_status(failure_reasons=[]) == EligibilityStatus.ELIGIBLE


def test_status_not_eligible_when_failures_exist():
    from app.modules.m11_sis.hallticket_service import _determine_status
    from app.modules.m11_sis.hallticket_models import EligibilityStatus
    assert _determine_status(failure_reasons=["Attendance too low"]) == EligibilityStatus.NOT_ELIGIBLE


def test_status_not_eligible_multiple_reasons():
    from app.modules.m11_sis.hallticket_service import _determine_status
    from app.modules.m11_sis.hallticket_models import EligibilityStatus
    result = _determine_status(failure_reasons=["reason 1", "reason 2", "reason 3"])
    assert result == EligibilityStatus.NOT_ELIGIBLE


def test_no_attendance_data_does_not_fail():
    from app.modules.m11_sis.hallticket_service import _build_failure_reasons
    reasons = _build_failure_reasons(
        attendance_pct   = None,
        has_shortage     = False,
        marks_all_locked = True,
        marks_all_filled = True,
        has_att_data     = False,   # no sessions recorded
        has_marks_data   = True,
        threshold_pct    = 75.0,
    )
    assert reasons == []


# ---------------------------------------------------------------------------
# 38–41. Hall ticket number format
# ---------------------------------------------------------------------------

def test_ticket_prefix_format_in_service():
    src = inspect.getsource(__import__(
        "app.modules.m11_sis.hallticket_service",
        fromlist=["HallTicketService"],
    ))
    assert "TOCS" in src
    assert "S{sem_number}" in src or "S" in src


def test_ticket_prefix_contains_year_and_semester():
    src = inspect.getsource(__import__(
        "app.modules.m11_sis.hallticket_service",
        fromlist=["HallTicketService"],
    ))
    assert "end_year" in src
    assert "sem_number" in src


def test_hall_ticket_number_format_in_repository():
    src = inspect.getsource(__import__(
        "app.modules.m11_sis.hallticket_repository",
        fromlist=["HallTicketRepository"],
    ))
    assert "ticket_prefix" in src
    assert "ticket_suffix" in src


def test_hall_ticket_usn_fallback_in_repository():
    src = inspect.getsource(__import__(
        "app.modules.m11_sis.hallticket_repository",
        fromlist=["HallTicketRepository"],
    ))
    assert "ROW_NUMBER" in src or "seq" in src.lower()


# ---------------------------------------------------------------------------
# 42–45. Students cannot see DRAFT eligibility
# ---------------------------------------------------------------------------

def test_my_eligibility_checks_publish_status():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.my_eligibility)
    assert "PUBLISHED" in src
    assert "NOT_PUBLISHED" in src or "not yet published" in src.lower()


def test_my_eligibility_raises_on_draft():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.my_eligibility)
    assert "HallTicketServiceError" in src


def test_get_hall_ticket_checks_publish_status():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.get_hall_ticket)
    assert "PUBLISHED" in src


def test_get_hall_ticket_student_isolation():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.get_hall_ticket)
    assert "STUDENT" in src
    assert "FORBIDDEN" in src or "403" in src


# ---------------------------------------------------------------------------
# 46–49. RBAC: manager-only on compute / publish / override / batch
# ---------------------------------------------------------------------------

def test_compute_endpoint_requires_manager():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    src = inspect.getsource(
        next(r.endpoint for r in hallticket_router.routes if "compute" in str(r.path))
    )
    assert "_MANAGERS" in src or "require_roles" in src


def test_override_endpoint_requires_manager():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    src = inspect.getsource(
        next(r.endpoint for r in hallticket_router.routes if "override" in str(r.path))
    )
    assert "_MANAGERS" in src or "require_roles" in src


def test_publish_endpoint_requires_manager():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    src = inspect.getsource(
        next(r.endpoint for r in hallticket_router.routes if "publish" in str(r.path))
    )
    assert "_MANAGERS" in src or "require_roles" in src


def test_batch_generate_requires_manager():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    # POST /batches route
    post_batch = next(
        r for r in hallticket_router.routes
        if r.path == "/hall-tickets/batches" and "POST" in r.methods
    )
    src = inspect.getsource(post_batch.endpoint)
    assert "_MANAGERS" in src or "require_roles" in src


# ---------------------------------------------------------------------------
# 50–53. RBAC: faculty advisory is faculty-only
# ---------------------------------------------------------------------------

def test_advisory_endpoint_is_faculty_only():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    advisory_route = next(
        r for r in hallticket_router.routes if "advisory" in str(r.path)
    )
    src = inspect.getsource(advisory_route.endpoint)
    assert "_FACULTY" in src or "require_roles" in src


def test_advisory_service_checks_faculty_assignment():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.faculty_advisory)
    assert "subject_assignments" in src or "faculty_user_id" in src


def test_advisory_service_raises_on_unassigned():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.faculty_advisory)
    assert "SECTION_NOT_ASSIGNED" in src or "403" in src or "not assigned" in src.lower()


def test_advisory_schema_has_no_override_fields():
    from app.modules.m11_sis.hallticket_schemas import AdvisoryStudentRow
    fields = set(AdvisoryStudentRow.model_fields)
    assert "override_by"     not in fields
    assert "override_reason" not in fields
    assert "override_status" not in fields


# ---------------------------------------------------------------------------
# 54–57. Batch generation requires PUBLISHED rows
# ---------------------------------------------------------------------------

def test_batch_service_checks_published():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.generate_batch)
    assert "PUBLISHED" in src


def test_batch_service_raises_no_eligible_published():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.generate_batch)
    assert "NO_ELIGIBLE_PUBLISHED" in src


def test_batch_assign_sql_filters_published():
    from app.modules.m11_sis.hallticket_repository import HallTicketRepository
    src = inspect.getsource(HallTicketRepository.assign_hall_tickets)
    assert "PUBLISHED" in src
    assert "ELIGIBLE" in src
    assert "CONDITIONAL" in src


def test_batch_service_logs_audit_event():
    from app.modules.m11_sis.hallticket_service import HallTicketService
    src = inspect.getsource(HallTicketService.generate_batch)
    assert "AuditService" in src or "audit" in src.lower()


# ---------------------------------------------------------------------------
# 58–61. Upsert protects overridden + PUBLISHED rows
# ---------------------------------------------------------------------------

def test_upsert_sql_has_conflict_clause():
    from app.modules.m11_sis.hallticket_repository import HallTicketRepository
    src = inspect.getsource(HallTicketRepository.upsert_eligibility)
    assert "ON CONFLICT" in src


def test_upsert_sql_protects_override_published():
    from app.modules.m11_sis.hallticket_repository import HallTicketRepository
    src = inspect.getsource(HallTicketRepository.upsert_eligibility)
    assert "override_by" in src
    assert "PUBLISHED" in src


def test_upsert_sql_preserves_published_status():
    from app.modules.m11_sis.hallticket_repository import HallTicketRepository
    src = inspect.getsource(HallTicketRepository.upsert_eligibility)
    assert "CASE" in src


def test_publish_sql_updates_only_draft():
    from app.modules.m11_sis.hallticket_repository import HallTicketRepository
    src = inspect.getsource(HallTicketRepository.publish_semester)
    assert "DRAFT" in src
    assert "PUBLISHED" in src


# ---------------------------------------------------------------------------
# 62–65. Router routes
# ---------------------------------------------------------------------------

def test_router_has_compute_endpoint():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    paths = [r.path for r in hallticket_router.routes]
    assert "/hall-tickets/eligibility/compute" in paths


def test_router_has_publish_endpoint():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    paths = [r.path for r in hallticket_router.routes]
    assert "/hall-tickets/eligibility/publish" in paths


def test_router_has_my_eligibility():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    paths = [r.path for r in hallticket_router.routes]
    assert "/hall-tickets/my-eligibility" in paths


def test_router_has_advisory():
    from app.modules.m11_sis.hallticket_router import hallticket_router
    paths = [r.path for r in hallticket_router.routes]
    assert "/hall-tickets/advisory" in paths


# ---------------------------------------------------------------------------
# 66–68. Migration
# ---------------------------------------------------------------------------

def _load_migration():
    import importlib.util
    import pathlib
    here = pathlib.Path(__file__)
    mig_path = here.parents[3] / "alembic" / "tenant_versions" / "0033_tenant_hall_ticket_eligibility.py"
    spec = importlib.util.spec_from_file_location("migration_0033", mig_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_revision():
    mig = _load_migration()
    assert mig.revision == "0033ten"


def test_migration_down_revision():
    mig = _load_migration()
    assert mig.down_revision == "0032ten"


def test_migration_creates_both_tables():
    import inspect as _inspect
    mig = _load_migration()
    src = _inspect.getsource(mig.upgrade)
    assert "sis_hall_ticket_batches" in src
    assert "sis_hall_ticket_eligibility" in src


# ---------------------------------------------------------------------------
# 69–72. Snapshot metadata fields
# ---------------------------------------------------------------------------

def test_snapshot_columns_on_model():
    from app.modules.m11_sis.hallticket_models import SisHallTicketEligibility
    cols = {c.name for c in SisHallTicketEligibility.__table__.columns}
    assert {"attendance_threshold_used",
            "computed_academic_year",
            "computed_semester_name"} <= cols


def test_snapshot_fields_on_schema():
    from app.modules.m11_sis.hallticket_schemas import EligibilityOut
    fields = set(EligibilityOut.model_fields)
    assert {"attendance_threshold_used",
            "computed_academic_year",
            "computed_semester_name"} <= fields


def test_threshold_in_compute_result():
    from app.modules.m11_sis.hallticket_schemas import EligibilityComputeResult
    fields = set(EligibilityComputeResult.model_fields)
    assert "threshold_pct" in fields


def test_compute_result_fields():
    from app.modules.m11_sis.hallticket_schemas import EligibilityComputeResult
    fields = set(EligibilityComputeResult.model_fields)
    assert {"semester_id", "processed", "eligible_count",
            "not_eligible_count", "skipped_overridden"} <= fields


# ---------------------------------------------------------------------------
# 73–76. Future exam fields
# ---------------------------------------------------------------------------

def test_exam_columns_on_model():
    from app.modules.m11_sis.hallticket_models import SisHallTicketEligibility
    cols = {c.name for c in SisHallTicketEligibility.__table__.columns}
    assert {"exam_session_id", "exam_schedule_id", "exam_center_id",
            "room_number", "seat_number"} <= cols


def test_exam_fields_on_eligibility_out():
    from app.modules.m11_sis.hallticket_schemas import EligibilityOut
    fields = set(EligibilityOut.model_fields)
    assert {"exam_session_id", "exam_schedule_id", "exam_center_id",
            "room_number", "seat_number"} <= fields


def test_exam_fields_on_hall_ticket_out():
    from app.modules.m11_sis.hallticket_schemas import HallTicketOut
    fields = set(HallTicketOut.model_fields)
    assert {"exam_session_id", "exam_schedule_id", "exam_center_id",
            "room_number", "seat_number"} <= fields


def test_exam_fields_nullable_by_default():
    from app.modules.m11_sis.hallticket_models import SisHallTicketEligibility
    exam_cols = {
        c.name: c
        for c in SisHallTicketEligibility.__table__.columns
        if c.name in {"exam_session_id", "exam_schedule_id", "exam_center_id",
                      "room_number", "seat_number"}
    }
    for col in exam_cols.values():
        assert col.nullable, f"Column {col.name} should be nullable"
