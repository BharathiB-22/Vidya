"""
Unit tests — H52 SIS Notifications

No live database. All tests use import + assert + AsyncMock.

Coverage:
  1.  NotificationType — ENROLLMENT_CREATED present
  2.  NotificationType — ENROLLMENT_MOVED present
  3.  NotificationType — ENROLLMENT_UNENROLLED present
  4.  NotificationType — USN_ASSIGNED present
  5.  NotificationType — ADMISSION_YEAR_ASSIGNED present
  6.  NotificationType — COURSE_ASSIGNED present
  7.  NotificationType — COURSE_ASSIGNMENT_REVOKED present
  8.  _notify_safe — calls NotificationService.send on success
  9.  _notify_safe — swallows exception, never raises
 10.  _notify_safe — swallows without calling send when send raises
 11.  enrollment_service source — ENROLLMENT_CREATED wired in enroll_student
 12.  enrollment_service source — ENROLLMENT_UNENROLLED wired in unenroll
 13.  enrollment_service source — ENROLLMENT_MOVED wired in move_student
 14.  directory_service source — USN_ASSIGNED wired in upsert_profile
 15.  directory_service source — ADMISSION_YEAR_ASSIGNED wired in upsert_profile
 16.  assignment_service source — COURSE_ASSIGNED wired in create
 17.  assignment_service source — COURSE_ASSIGNMENT_REVOKED wired in revoke
 18.  _notify_safe in enrollment_service — is async
 19.  _notify_safe in directory_service — is async
 20.  _notify_safe in assignment_service — is async
"""
import asyncio
import inspect
import uuid
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1–7. NotificationType enum has all 7 new values
# ---------------------------------------------------------------------------

def test_notification_type_enrollment_created():
    from app.core.notifications.models import NotificationType
    assert NotificationType.ENROLLMENT_CREATED == "ENROLLMENT_CREATED"


def test_notification_type_enrollment_moved():
    from app.core.notifications.models import NotificationType
    assert NotificationType.ENROLLMENT_MOVED == "ENROLLMENT_MOVED"


def test_notification_type_enrollment_unenrolled():
    from app.core.notifications.models import NotificationType
    assert NotificationType.ENROLLMENT_UNENROLLED == "ENROLLMENT_UNENROLLED"


def test_notification_type_usn_assigned():
    from app.core.notifications.models import NotificationType
    assert NotificationType.USN_ASSIGNED == "USN_ASSIGNED"


def test_notification_type_admission_year_assigned():
    from app.core.notifications.models import NotificationType
    assert NotificationType.ADMISSION_YEAR_ASSIGNED == "ADMISSION_YEAR_ASSIGNED"


def test_notification_type_course_assigned():
    from app.core.notifications.models import NotificationType
    assert NotificationType.COURSE_ASSIGNED == "COURSE_ASSIGNED"


def test_notification_type_course_assignment_revoked():
    from app.core.notifications.models import NotificationType
    assert NotificationType.COURSE_ASSIGNMENT_REVOKED == "COURSE_ASSIGNMENT_REVOKED"


# ---------------------------------------------------------------------------
# 8–10. _notify_safe helper behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_safe_calls_notification_service():
    """_notify_safe delegates to NotificationService.send when no error."""
    from app.core.notifications.models import NotificationType
    from app.modules.m11_sis.enrollment_service import _notify_safe

    mock_send = AsyncMock()
    mock_db = AsyncMock()

    with patch("app.core.notifications.service.NotificationService.send", mock_send):
        await _notify_safe(
            notification_type=NotificationType.ENROLLMENT_CREATED,
            recipient_user_id=uuid.uuid4(),
            recipient_email="student@test.com",
            title="Test",
            body="Body",
            entity_type="acad_enrollment",
            entity_id=str(uuid.uuid4()),
            db=mock_db,
        )

    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_notify_safe_swallows_exception():
    """_notify_safe must not propagate errors from NotificationService.send."""
    from app.core.notifications.models import NotificationType
    from app.modules.m11_sis.enrollment_service import _notify_safe

    exploding_send = AsyncMock(side_effect=RuntimeError("Redis down"))
    mock_db = AsyncMock()

    with patch("app.core.notifications.service.NotificationService.send", exploding_send):
        # Must not raise
        await _notify_safe(
            notification_type=NotificationType.ENROLLMENT_CREATED,
            recipient_user_id=uuid.uuid4(),
            recipient_email=None,
            title="Test",
            body="Body",
            entity_type="acad_enrollment",
            entity_id=str(uuid.uuid4()),
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_notify_safe_directory_swallows_exception():
    """_notify_safe in directory_service must not propagate errors."""
    from app.core.notifications.models import NotificationType
    from app.modules.m11_sis.directory_service import _notify_safe

    exploding_send = AsyncMock(side_effect=ConnectionError("DB down"))
    mock_db = AsyncMock()

    with patch("app.core.notifications.service.NotificationService.send", exploding_send):
        await _notify_safe(
            notification_type=NotificationType.USN_ASSIGNED,
            recipient_user_id=uuid.uuid4(),
            recipient_email=None,
            title="USN",
            body="Assigned",
            entity_type="sis_student_profile",
            entity_id=str(uuid.uuid4()),
            db=mock_db,
        )


# ---------------------------------------------------------------------------
# 11–13. enrollment_service source wiring checks
# ---------------------------------------------------------------------------

def test_enrollment_service_wires_enrollment_created():
    import app.modules.m11_sis.enrollment_service as svc
    src = inspect.getsource(svc.EnrollmentService.enroll_student)
    assert "ENROLLMENT_CREATED" in src
    assert "_notify_safe" in src


def test_enrollment_service_wires_enrollment_unenrolled():
    import app.modules.m11_sis.enrollment_service as svc
    src = inspect.getsource(svc.EnrollmentService.unenroll)
    assert "ENROLLMENT_UNENROLLED" in src
    assert "_notify_safe" in src


def test_enrollment_service_wires_enrollment_moved():
    import app.modules.m11_sis.enrollment_service as svc
    src = inspect.getsource(svc.EnrollmentService.move_student)
    assert "ENROLLMENT_MOVED" in src
    assert "_notify_safe" in src


# ---------------------------------------------------------------------------
# 14–15. directory_service source wiring checks
# ---------------------------------------------------------------------------

def test_directory_service_wires_usn_assigned():
    import app.modules.m11_sis.directory_service as svc
    src = inspect.getsource(svc.StudentDirectoryService.upsert_profile)
    assert "USN_ASSIGNED" in src
    assert "_notify_safe" in src


def test_directory_service_wires_admission_year_assigned():
    import app.modules.m11_sis.directory_service as svc
    src = inspect.getsource(svc.StudentDirectoryService.upsert_profile)
    assert "ADMISSION_YEAR_ASSIGNED" in src


# ---------------------------------------------------------------------------
# 16–17. assignment_service source wiring checks
# ---------------------------------------------------------------------------

def test_assignment_service_wires_course_assigned():
    import app.modules.m_academics.assignment_service as svc
    src = inspect.getsource(svc.AssignmentService.create)
    assert "COURSE_ASSIGNED" in src
    assert "_notify_safe" in src


def test_assignment_service_wires_course_assignment_revoked():
    import app.modules.m_academics.assignment_service as svc
    src = inspect.getsource(svc.AssignmentService.revoke)
    assert "COURSE_ASSIGNMENT_REVOKED" in src
    assert "_notify_safe" in src


# ---------------------------------------------------------------------------
# 18–20. _notify_safe helpers are async coroutines
# ---------------------------------------------------------------------------

def test_notify_safe_enrollment_is_async():
    from app.modules.m11_sis.enrollment_service import _notify_safe
    assert asyncio.iscoroutinefunction(_notify_safe)


def test_notify_safe_directory_is_async():
    from app.modules.m11_sis.directory_service import _notify_safe
    assert asyncio.iscoroutinefunction(_notify_safe)


def test_notify_safe_assignment_is_async():
    from app.modules.m_academics.assignment_service import _notify_safe
    assert asyncio.iscoroutinefunction(_notify_safe)
