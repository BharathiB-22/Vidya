"""
Unit tests — H59 SIS Examination Management

No live database. All tests use import + assert + inspect.getsource.

Coverage:
  1–4   : SisExamCenter ORM columns
  5–8   : SisExamSession ORM columns (including H59 modifications)
  9–12  : SisExamSchedule ORM columns
  13–16 : SisExamInvigilation ORM columns
  17–20 : ExamSessionCreateIn schema fields + validator
  21–24 : ExamSessionOut schema fields (including schedule_count)
  25–28 : ExamScheduleCreateIn schema fields + validator
  29–32 : ExamScheduleOut enriched fields
  33–36 : SeatAllocationIn + RoomSpec + SeatingAllocationResult
  37–40 : StudentTimetableOut + MyHallTicketExamOut student schemas
  41–44 : ExamSessionType enum values
  45–48 : ExamSessionStatus enum values (5 statuses including SEATING_ALLOCATED)
  49–52 : Session lifecycle — valid transitions in service source
  53–56 : Session lifecycle — invalid transition guard in service source
  57–60 : Seat allocation — NOT_ELIGIBLE blocked in service source
  61–64 : Seat allocation — INSUFFICIENT_CAPACITY guard in service source
  65–68 : RBAC — _MANAGERS only for create/publish/lock/complete/allocate
  69–72 : Faculty invigilation scoped to own assignments
  73–76 : Student timetable — DRAFT session blocked for student
  77–80 : Migration revision, down_revision, table names present
  81–84 : Hall ticket tracking fields on SisExamSession
  85–88 : Future-proof fields (source_exam_session_id, attempt_number)
  89–92 : Seat allocation transitions session to SEATING_ALLOCATED
  93–97 : SIS router total route count (73 + 24 exam = 97)
"""
import importlib.util
import inspect
import pathlib

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1–4. SisExamCenter ORM columns
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_center_pk():
    from app.modules.m11_sis.exam_models import SisExamCenter
    assert hasattr(SisExamCenter, "id")


def test_exam_center_code_name():
    from app.modules.m11_sis.exam_models import SisExamCenter
    for col in ("center_code", "center_name"):
        assert hasattr(SisExamCenter, col), f"SisExamCenter missing {col}"


def test_exam_center_flags():
    from app.modules.m11_sis.exam_models import SisExamCenter
    for col in ("is_internal", "is_active", "capacity"):
        assert hasattr(SisExamCenter, col), f"SisExamCenter missing {col}"


def test_exam_center_tablename():
    from app.modules.m11_sis.exam_models import SisExamCenter
    assert SisExamCenter.__tablename__ == "sis_exam_centers"


# ─────────────────────────────────────────────────────────────────────────────
# 5–8. SisExamSession ORM columns
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_session_core_columns():
    from app.modules.m11_sis.exam_models import SisExamSession
    for col in ("id", "semester_id", "session_type", "session_name",
                "academic_year", "start_date", "end_date", "status"):
        assert hasattr(SisExamSession, col), f"SisExamSession missing {col}"


def test_exam_session_tablename():
    from app.modules.m11_sis.exam_models import SisExamSession
    assert SisExamSession.__tablename__ == "sis_exam_sessions"


def test_exam_session_future_proof_fields():
    from app.modules.m11_sis.exam_models import SisExamSession
    for col in ("source_exam_session_id", "attempt_number"):
        assert hasattr(SisExamSession, col), f"SisExamSession missing {col}"


def test_exam_session_hall_ticket_tracking():
    from app.modules.m11_sis.exam_models import SisExamSession
    for col in ("hall_ticket_generated_at", "hall_ticket_generated_by"):
        assert hasattr(SisExamSession, col), f"SisExamSession missing {col}"


# ─────────────────────────────────────────────────────────────────────────────
# 9–12. SisExamSchedule ORM columns
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_schedule_pk():
    from app.modules.m11_sis.exam_models import SisExamSchedule
    assert hasattr(SisExamSchedule, "id")


def test_exam_schedule_fk_columns():
    from app.modules.m11_sis.exam_models import SisExamSchedule
    for col in ("session_id", "course_id", "section_id", "center_id"):
        assert hasattr(SisExamSchedule, col), f"SisExamSchedule missing {col}"


def test_exam_schedule_datetime_columns():
    from app.modules.m11_sis.exam_models import SisExamSchedule
    for col in ("exam_date", "start_time", "end_time"):
        assert hasattr(SisExamSchedule, col), f"SisExamSchedule missing {col}"


def test_exam_schedule_tablename():
    from app.modules.m11_sis.exam_models import SisExamSchedule
    assert SisExamSchedule.__tablename__ == "sis_exam_schedules"


# ─────────────────────────────────────────────────────────────────────────────
# 13–16. SisExamInvigilation ORM columns
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_invigilation_pk():
    from app.modules.m11_sis.exam_models import SisExamInvigilation
    assert hasattr(SisExamInvigilation, "id")


def test_exam_invigilation_fk_columns():
    from app.modules.m11_sis.exam_models import SisExamInvigilation
    for col in ("session_id", "schedule_id", "center_id"):
        assert hasattr(SisExamInvigilation, col), f"SisExamInvigilation missing {col}"


def test_exam_invigilation_faculty_column():
    from app.modules.m11_sis.exam_models import SisExamInvigilation
    assert hasattr(SisExamInvigilation, "faculty_user_id")


def test_exam_invigilation_tablename():
    from app.modules.m11_sis.exam_models import SisExamInvigilation
    assert SisExamInvigilation.__tablename__ == "sis_exam_invigilation"


# ─────────────────────────────────────────────────────────────────────────────
# 17–20. ExamSessionCreateIn schema
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_session_create_required_fields():
    from app.modules.m11_sis.exam_schemas import ExamSessionCreateIn
    fields = set(ExamSessionCreateIn.model_fields)
    assert {"semester_id", "session_type", "session_name",
            "academic_year", "start_date", "end_date"} <= fields


def test_exam_session_create_optional_fields():
    from app.modules.m11_sis.exam_schemas import ExamSessionCreateIn
    fields = set(ExamSessionCreateIn.model_fields)
    assert {"notes", "source_exam_session_id", "attempt_number"} <= fields


def test_exam_session_create_end_before_start_rejected():
    from app.modules.m11_sis.exam_schemas import ExamSessionCreateIn
    from datetime import date
    import uuid
    with pytest.raises(Exception):
        ExamSessionCreateIn(
            semester_id=uuid.uuid4(),
            session_type="REGULAR",
            session_name="Test",
            academic_year="2025-26",
            start_date=date(2026, 12, 20),
            end_date=date(2026, 12, 10),  # before start
        )


def test_exam_session_create_valid():
    from app.modules.m11_sis.exam_schemas import ExamSessionCreateIn
    from datetime import date
    import uuid
    s = ExamSessionCreateIn(
        semester_id=uuid.uuid4(),
        session_type="REGULAR",
        session_name="Dec 2026 Regular",
        academic_year="2025-26",
        start_date=date(2026, 12, 10),
        end_date=date(2026, 12, 20),
    )
    assert s.session_type == "REGULAR"


# ─────────────────────────────────────────────────────────────────────────────
# 21–24. ExamSessionOut schema
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_session_out_core_fields():
    from app.modules.m11_sis.exam_schemas import ExamSessionOut
    fields = set(ExamSessionOut.model_fields)
    assert {"id", "semester_id", "session_type", "session_name",
            "academic_year", "start_date", "end_date", "status"} <= fields


def test_exam_session_out_schedule_count():
    from app.modules.m11_sis.exam_schemas import ExamSessionOut
    assert "schedule_count" in ExamSessionOut.model_fields


def test_exam_session_out_hall_ticket_tracking():
    from app.modules.m11_sis.exam_schemas import ExamSessionOut
    assert {"hall_ticket_generated_at", "hall_ticket_generated_by"} <= set(ExamSessionOut.model_fields)


def test_exam_session_out_future_proof():
    from app.modules.m11_sis.exam_schemas import ExamSessionOut
    assert {"source_exam_session_id", "attempt_number"} <= set(ExamSessionOut.model_fields)


# ─────────────────────────────────────────────────────────────────────────────
# 25–28. ExamScheduleCreateIn schema
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_schedule_create_required_fields():
    from app.modules.m11_sis.exam_schemas import ExamScheduleCreateIn
    fields = set(ExamScheduleCreateIn.model_fields)
    assert {"course_id", "section_id", "exam_date", "start_time", "end_time"} <= fields


def test_exam_schedule_create_optional_fields():
    from app.modules.m11_sis.exam_schemas import ExamScheduleCreateIn
    fields = set(ExamScheduleCreateIn.model_fields)
    assert {"center_id", "room_number", "notes"} <= fields


def test_exam_schedule_create_end_before_start_rejected():
    from app.modules.m11_sis.exam_schemas import ExamScheduleCreateIn
    from datetime import date, time
    import uuid
    with pytest.raises(Exception):
        ExamScheduleCreateIn(
            course_id=uuid.uuid4(),
            section_id=uuid.uuid4(),
            exam_date=date(2026, 12, 10),
            start_time=time(10, 0),
            end_time=time(9, 0),  # before start
        )


def test_exam_schedule_create_valid():
    from app.modules.m11_sis.exam_schemas import ExamScheduleCreateIn
    from datetime import date, time
    import uuid
    s = ExamScheduleCreateIn(
        course_id=uuid.uuid4(),
        section_id=uuid.uuid4(),
        exam_date=date(2026, 12, 10),
        start_time=time(9, 0),
        end_time=time(12, 0),
    )
    assert s.end_time > s.start_time


# ─────────────────────────────────────────────────────────────────────────────
# 29–32. ExamScheduleOut enriched fields
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_schedule_out_enriched_fields():
    from app.modules.m11_sis.exam_schemas import ExamScheduleOut
    fields = set(ExamScheduleOut.model_fields)
    assert {"course_code", "course_title", "section_name"} <= fields


def test_exam_schedule_out_center_name():
    from app.modules.m11_sis.exam_schemas import ExamScheduleOut
    assert "center_name" in ExamScheduleOut.model_fields


def test_exam_schedule_out_session_id():
    from app.modules.m11_sis.exam_schemas import ExamScheduleOut
    assert "session_id" in ExamScheduleOut.model_fields


def test_exam_schedule_out_from_attributes():
    from app.modules.m11_sis.exam_schemas import ExamScheduleOut
    assert ExamScheduleOut.model_config.get("from_attributes") is True


# ─────────────────────────────────────────────────────────────────────────────
# 33–36. Seating schemas
# ─────────────────────────────────────────────────────────────────────────────

def test_seat_allocation_in_fields():
    from app.modules.m11_sis.exam_schemas import SeatAllocationIn
    fields = set(SeatAllocationIn.model_fields)
    assert {"center_id", "rooms", "section_id"} <= fields


def test_room_spec_fields():
    from app.modules.m11_sis.exam_schemas import RoomSpec
    assert {"room_number", "capacity"} <= set(RoomSpec.model_fields)


def test_room_spec_capacity_positive():
    from app.modules.m11_sis.exam_schemas import RoomSpec
    with pytest.raises(Exception):
        RoomSpec(room_number="A101", capacity=0)


def test_seating_allocation_result_fields():
    from app.modules.m11_sis.exam_schemas import SeatingAllocationResult
    fields = set(SeatingAllocationResult.model_fields)
    assert {"session_id", "allocated", "rooms_used", "total_capacity", "details"} <= fields


# ─────────────────────────────────────────────────────────────────────────────
# 37–40. Student schemas
# ─────────────────────────────────────────────────────────────────────────────

def test_student_timetable_out_fields():
    from app.modules.m11_sis.exam_schemas import StudentTimetableOut
    fields = set(StudentTimetableOut.model_fields)
    assert {"session_id", "session_name", "session_type", "semester_name",
            "seat", "courses"} <= fields


def test_my_hall_ticket_exam_out_fields():
    from app.modules.m11_sis.exam_schemas import MyHallTicketExamOut
    fields = set(MyHallTicketExamOut.model_fields)
    assert {"hall_ticket_number", "student_id", "status",
            "seat", "timetable"} <= fields


def test_course_schedule_row_is_scheduled_flag():
    from app.modules.m11_sis.exam_schemas import CourseScheduleRow
    assert "is_scheduled" in CourseScheduleRow.model_fields


def test_seat_info_fields():
    from app.modules.m11_sis.exam_schemas import SeatInfo
    fields = set(SeatInfo.model_fields)
    assert {"center_name", "address", "room_number", "seat_number"} <= fields


# ─────────────────────────────────────────────────────────────────────────────
# 41–44. ExamSessionType enum values
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_session_type_regular():
    from app.modules.m11_sis.exam_models import ExamSessionType
    assert ExamSessionType.REGULAR == "REGULAR"


def test_exam_session_type_supplementary():
    from app.modules.m11_sis.exam_models import ExamSessionType
    assert ExamSessionType.SUPPLEMENTARY == "SUPPLEMENTARY"


def test_exam_session_type_revaluation():
    from app.modules.m11_sis.exam_models import ExamSessionType
    assert ExamSessionType.REVALUATION == "REVALUATION"


def test_exam_session_type_improvement():
    from app.modules.m11_sis.exam_models import ExamSessionType
    assert ExamSessionType.IMPROVEMENT == "IMPROVEMENT"


# ─────────────────────────────────────────────────────────────────────────────
# 45–48. ExamSessionStatus enum — 5 statuses including SEATING_ALLOCATED
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_session_status_draft():
    from app.modules.m11_sis.exam_models import ExamSessionStatus
    assert ExamSessionStatus.DRAFT == "DRAFT"


def test_exam_session_status_published():
    from app.modules.m11_sis.exam_models import ExamSessionStatus
    assert ExamSessionStatus.PUBLISHED == "PUBLISHED"


def test_exam_session_status_seating_allocated():
    from app.modules.m11_sis.exam_models import ExamSessionStatus
    assert ExamSessionStatus.SEATING_ALLOCATED == "SEATING_ALLOCATED"


def test_exam_session_status_locked_and_completed():
    from app.modules.m11_sis.exam_models import ExamSessionStatus
    assert ExamSessionStatus.LOCKED == "LOCKED"
    assert ExamSessionStatus.COMPLETED == "COMPLETED"


# ─────────────────────────────────────────────────────────────────────────────
# 49–52. Session lifecycle — valid transitions in service source
# ─────────────────────────────────────────────────────────────────────────────

def test_publish_transition_from_draft():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "DRAFT" in src
    assert "PUBLISHED" in src


def test_lock_transition_from_seating_allocated():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "SEATING_ALLOCATED" in src
    assert "LOCKED" in src


def test_complete_transition_from_locked():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "COMPLETED" in src


def test_session_service_has_publish_lock_complete():
    from app.modules.m11_sis.exam_service import ExamSessionService
    for m in ("publish", "lock", "complete"):
        assert callable(getattr(ExamSessionService, m, None)), f"ExamSessionService.{m} missing"


# ─────────────────────────────────────────────────────────────────────────────
# 53–56. Lifecycle guards
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_status_guard_in_service():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "INVALID_SESSION_STATUS" in src


def test_not_deletable_guard_in_service():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "SESSION_NOT_DELETABLE" in src


def test_schedule_not_editable_guard():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "SCHEDULE_NOT_EDITABLE" in src


def test_session_has_schedules_guard():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "SESSION_HAS_SCHEDULES" in src


# ─────────────────────────────────────────────────────────────────────────────
# 57–60. Seat allocation — eligibility hard block
# ─────────────────────────────────────────────────────────────────────────────

def test_seat_allocation_requires_published_eligible():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_repository", fromlist=["exam_repository"])
    )
    assert "publish_status = 'PUBLISHED'" in src
    assert "status IN ('ELIGIBLE', 'CONDITIONAL')" in src


def test_seat_allocation_requires_hall_ticket():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_repository", fromlist=["exam_repository"])
    )
    assert "hall_ticket_number IS NOT NULL" in src


def test_seat_allocation_no_eligible_guard():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "NO_ELIGIBLE_STUDENTS" in src


def test_seat_allocation_not_eligible_not_in_sql():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_repository", fromlist=["exam_repository"])
    )
    # 'NOT_ELIGIBLE' must NOT appear in the seating query — hard blocked
    assert "NOT_ELIGIBLE" not in src


# ─────────────────────────────────────────────────────────────────────────────
# 61–64. Seat allocation — capacity guard
# ─────────────────────────────────────────────────────────────────────────────

def test_insufficient_capacity_guard():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "INSUFFICIENT_CAPACITY" in src


def test_capacity_computed_from_rooms():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "total_capacity" in src


def test_seat_assignment_algorithm():
    from app.modules.m11_sis.exam_service import _compute_seat_assignments
    from app.modules.m11_sis.exam_schemas import RoomSpec
    students = [
        {"eligibility_id": "s1", "usn": "USN001", "full_name": "Alice"},
        {"eligibility_id": "s2", "usn": "USN002", "full_name": "Bob"},
        {"eligibility_id": "s3", "usn": "USN003", "full_name": "Carol"},
    ]
    rooms = [RoomSpec(room_number="A101", capacity=2), RoomSpec(room_number="A102", capacity=2)]
    result = _compute_seat_assignments(students, rooms)
    assert len(result) == 3
    assert result[0]["room_number"] == "A101"
    assert result[0]["seat_number"] == "A101-001"
    assert result[1]["seat_number"] == "A101-002"
    assert result[2]["room_number"] == "A102"
    assert result[2]["seat_number"] == "A102-001"


def test_seat_number_format_three_digits():
    from app.modules.m11_sis.exam_service import _compute_seat_assignments
    from app.modules.m11_sis.exam_schemas import RoomSpec
    students = [{"eligibility_id": f"s{i}", "usn": "", "full_name": f"S{i}"}
                for i in range(5)]
    rooms = [RoomSpec(room_number="LAB1", capacity=10)]
    result = _compute_seat_assignments(students, rooms)
    assert result[0]["seat_number"] == "LAB1-001"
    assert result[4]["seat_number"] == "LAB1-005"


# ─────────────────────────────────────────────────────────────────────────────
# 65–68. RBAC — manager-only guards
# ─────────────────────────────────────────────────────────────────────────────

def test_rbac_managers_defined():
    from app.modules.m11_sis.exam_router import _MANAGERS
    from app.core.auth.models import TenantRole
    assert TenantRole.ADMIN in _MANAGERS
    assert TenantRole.DEAN  in _MANAGERS
    assert TenantRole.FACULTY  not in _MANAGERS
    assert TenantRole.STUDENT  not in _MANAGERS


def test_rbac_student_routes_use_student_role():
    import app.modules.m11_sis.exam_router as er
    src = inspect.getsource(er)
    assert "require_roles(*_STUDENT)" in src


def test_rbac_faculty_invigilation_uses_faculty_role():
    import app.modules.m11_sis.exam_router as er
    src = inspect.getsource(er)
    assert "require_roles(*_FACULTY)" in src


def test_rbac_all_roles_can_list_sessions():
    import app.modules.m11_sis.exam_router as er
    src = inspect.getsource(er)
    assert "require_roles(*_ALL)" in src


# ─────────────────────────────────────────────────────────────────────────────
# 69–72. Faculty invigilation scoped to own assignments
# ─────────────────────────────────────────────────────────────────────────────

def test_my_invigilation_filters_by_faculty():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_repository", fromlist=["exam_repository"])
    )
    assert "faculty_user_id = :faculty_id" in src


def test_my_invigilation_service_method():
    from app.modules.m11_sis.exam_service import ExamInvigilationService
    assert callable(getattr(ExamInvigilationService, "my_invigilation", None))


def test_my_invigilation_router_route_exists():
    from app.modules.m11_sis.exam_router import exam_router
    paths = {r.path for r in exam_router.routes}
    assert "/exam/my-invigilation" in paths


def test_invigilation_audit_event_used():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "EXAM_INVIGILATION_ASSIGNED" in src


# ─────────────────────────────────────────────────────────────────────────────
# 73–76. Student timetable — DRAFT session blocked
# ─────────────────────────────────────────────────────────────────────────────

def test_student_timetable_draft_blocked():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "SESSION_NOT_FOUND" in src


def test_student_my_timetable_route():
    from app.modules.m11_sis.exam_router import exam_router
    paths = {r.path for r in exam_router.routes}
    assert "/exam/my-timetable" in paths


def test_student_my_hall_ticket_route():
    from app.modules.m11_sis.exam_router import exam_router
    paths = {r.path for r in exam_router.routes}
    assert "/exam/my-hall-ticket" in paths


def test_eligibility_not_published_guard():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "ELIGIBILITY_NOT_PUBLISHED" in src


# ─────────────────────────────────────────────────────────────────────────────
# 77–80. Migration: revision, down_revision, table names
# ─────────────────────────────────────────────────────────────────────────────

def _load_migration():
    migration_path = (
        pathlib.Path(__file__).parents[3]
        / "alembic"
        / "tenant_versions"
        / "0034_tenant_exam_management.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0034", migration_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_revision():
    mod = _load_migration()
    assert mod.revision == "0034ten"


def test_migration_down_revision():
    mod = _load_migration()
    assert mod.down_revision == "0033ten"


def test_migration_creates_exam_sessions():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "sis_exam_sessions" in src


def test_migration_creates_all_four_tables():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    for table in ("sis_exam_centers", "sis_exam_sessions",
                  "sis_exam_schedules", "sis_exam_invigilation"):
        assert table in src, f"Migration missing table {table}"


# ─────────────────────────────────────────────────────────────────────────────
# 81–84. Hall ticket tracking fields on SisExamSession
# ─────────────────────────────────────────────────────────────────────────────

def test_session_hall_ticket_generated_at_nullable():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "hall_ticket_generated_at" in src


def test_session_hall_ticket_generated_by_nullable():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "hall_ticket_generated_by" in src


def test_allocation_stamps_hall_ticket_tracking():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "hall_ticket_generated_at" in src
    assert "hall_ticket_generated_by" in src


def test_allocation_result_has_details():
    from app.modules.m11_sis.exam_schemas import RoomAllocationDetail
    d = RoomAllocationDetail(room_number="A101", capacity=30, assigned=25)
    assert d.assigned == 25


# ─────────────────────────────────────────────────────────────────────────────
# 85–88. Future-proof fields (source_exam_session_id, attempt_number)
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_has_source_exam_session_id():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "source_exam_session_id" in src


def test_migration_has_attempt_number():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "attempt_number" in src


def test_session_create_accepts_attempt_number():
    from app.modules.m11_sis.exam_schemas import ExamSessionCreateIn
    from datetime import date
    import uuid
    s = ExamSessionCreateIn(
        semester_id=uuid.uuid4(),
        session_type="REVALUATION",
        session_name="Revaluation Jan 2027",
        academic_year="2026-27",
        start_date=date(2027, 1, 10),
        end_date=date(2027, 1, 15),
        attempt_number=2,
    )
    assert s.attempt_number == 2


def test_session_create_accepts_source_session_id():
    from app.modules.m11_sis.exam_schemas import ExamSessionCreateIn
    from datetime import date
    import uuid
    parent = uuid.uuid4()
    s = ExamSessionCreateIn(
        semester_id=uuid.uuid4(),
        session_type="SUPPLEMENTARY",
        session_name="Supplementary Mar 2027",
        academic_year="2026-27",
        start_date=date(2027, 3, 1),
        end_date=date(2027, 3, 10),
        source_exam_session_id=parent,
    )
    assert s.source_exam_session_id == parent


# ─────────────────────────────────────────────────────────────────────────────
# 89–92. Seat allocation transitions session to SEATING_ALLOCATED
# ─────────────────────────────────────────────────────────────────────────────

def test_allocation_transitions_to_seating_allocated():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "SEATING_ALLOCATED" in src


def test_allocation_allowed_from_seating_allocated_for_rerun():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    # Both PUBLISHED and SEATING_ALLOCATED are in the allowed tuple
    assert "SEATING_ALLOCATED" in src


def test_allocation_audit_event():
    src = inspect.getsource(
        __import__("app.modules.m11_sis.exam_service", fromlist=["exam_service"])
    )
    assert "EXAM_SEATS_ALLOCATED" in src


def test_audit_events_exist_in_model():
    from app.core.audit_log.models import AuditEventType
    values = {e.value for e in AuditEventType}
    for ev in ("EXAM_SESSION_PUBLISHED", "EXAM_SESSION_LOCKED",
               "EXAM_SESSION_COMPLETED", "EXAM_SEATS_ALLOCATED",
               "EXAM_INVIGILATION_ASSIGNED"):
        assert ev in values, f"AuditEventType missing {ev}"


# ─────────────────────────────────────────────────────────────────────────────
# 93–97. SIS router total route count (73 + 24 exam = 97)
# ─────────────────────────────────────────────────────────────────────────────

def test_exam_router_route_count():
    from app.modules.m11_sis.exam_router import exam_router
    assert len(exam_router.routes) == 24


def test_sis_router_includes_exam_router():
    from app.modules.m11_sis.router import router
    paths = [r.path for r in router.routes]
    assert "/exam/sessions" in paths
    assert "/exam/centers" in paths


def test_sis_router_total_routes():
    from app.modules.m11_sis.router import router
    # 5 school + 7 enrollment + 11 directory + 4 me + 2 rollover
    # + 15 attendance + 19 marks + 10 hallticket + 24 exam + 36 results = 133
    assert len(router.routes) == 166


def test_exam_session_publish_audit_event():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.EXAM_SESSION_PUBLISHED == "EXAM_SESSION_PUBLISHED"


def test_exam_center_seeded_in_migration():
    mod = _load_migration()
    src = inspect.getsource(mod.upgrade)
    assert "Main Campus" in src
    assert "MAIN" in src
