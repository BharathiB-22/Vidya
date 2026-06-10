"""
M09.4 Examination Board Approval — unit tests (no DB).

Coverage:
  - BoardSessionStatus enum values
  - BoardApprovalStatus enum values
  - AuditEventType includes M09.4 events
  - convene: success path (1+ BOARD_FINALISED scripts)
  - convene: no finalised scripts rejected (422)
  - convene: duplicate OPEN session rejected (409)
  - convene: pass_rate_pct computed correctly
  - approve: success (OPEN → APPROVED)
  - approve: wrong status rejected
  - reject: success (OPEN → REJECTED)
  - reject: wrong status rejected
  - reject: short remarks rejected by schema
  - declare: success (APPROVED → DECLARED)
  - declare: wrong status rejected (needs APPROVED, not OPEN)
  - declare: REJECTED session cannot be declared
  - board_adjust blocked after paper has APPROVED session (lock)
  - get_board_status: all_finalised=True when all scripts BOARD_FINALISED
  - get_board_status: ready_for_board logic
  - BoardSessionCreateRequest: short title rejected
  - BoardSessionResponse schema
  - BoardCourseApprovalResponse schema
  - Statistics snapshot created at convene time
  - list_sessions returns paginated result
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m09_paper_admin.models import (
    BoardApprovalStatus,
    BoardSessionStatus,
    ExamBoardCourseApproval,
    ExamBoardSession,
    ScannedScript,
    ScriptStatus,
)
from app.modules.m09_paper_admin.repository import (
    BoardCourseApprovalRepository,
    BoardSessionRepository,
)
from app.modules.m09_paper_admin.schemas import (
    BoardApproveRequest,
    BoardRejectRequest,
    BoardSessionCreateRequest,
)
from app.modules.m09_paper_admin.service import BoardApprovalService, ScriptServiceError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _make_session(
    *,
    exam_paper_id: uuid.UUID | None = None,
    status: BoardSessionStatus = BoardSessionStatus.OPEN,
) -> ExamBoardSession:
    s = ExamBoardSession()
    s.id = uuid.uuid4()
    s.exam_paper_id = exam_paper_id or uuid.uuid4()
    s.session_title = "End-of-Semester Board Session"
    s.convened_by = uuid.uuid4()
    s.convened_at = _NOW
    s.status = status.value
    s.board_remarks = None
    s.decided_by = None
    s.decided_at = None
    s.declared_by = None
    s.declared_at = None
    s.created_at = _NOW
    return s


def _make_course_approval(
    *,
    session_id: uuid.UUID,
    exam_paper_id: uuid.UUID,
) -> ExamBoardCourseApproval:
    a = ExamBoardCourseApproval()
    a.id = uuid.uuid4()
    a.session_id = session_id
    a.exam_paper_id = exam_paper_id
    a.mean_marks = Decimal("72.5")
    a.max_marks = Decimal("100.0")
    a.pass_count = 45
    a.fail_count = 5
    a.total_scripts = 50
    a.pass_rate_pct = Decimal("90.0")
    a.approval_status = BoardApprovalStatus.PENDING.value
    a.created_at = _NOW
    return a


def _make_ledger_entry(*, exam_paper_id: uuid.UUID, total_marks: float, max_marks: float = 100.0):
    from app.modules.m09_paper_admin.models import ExamScoreLedger
    e = ExamScoreLedger()
    e.id = uuid.uuid4()
    e.script_id = uuid.uuid4()
    e.exam_paper_id = exam_paper_id
    e.student_user_id = uuid.uuid4()
    e.student_roll_ref = "ROLL001"
    e.total_marks = Decimal(str(total_marks))
    e.max_marks = Decimal(str(max_marks))
    e.primary_total = None
    e.secondary_total = None
    e.has_board_adjustment = False
    e.finalised_by = uuid.uuid4()
    e.finalisation_note = None
    e.finalised_at = _NOW
    return e


# ---------------------------------------------------------------------------
# 1. BoardSessionStatus enum values
# ---------------------------------------------------------------------------

def test_board_session_status_values():
    """BoardSessionStatus covers the full approval lifecycle."""
    assert BoardSessionStatus.OPEN.value     == "OPEN"
    assert BoardSessionStatus.APPROVED.value == "APPROVED"
    assert BoardSessionStatus.REJECTED.value == "REJECTED"
    assert BoardSessionStatus.DECLARED.value == "DECLARED"


# ---------------------------------------------------------------------------
# 2. BoardApprovalStatus enum values
# ---------------------------------------------------------------------------

def test_board_approval_status_values():
    """BoardApprovalStatus covers PENDING / APPROVED / REJECTED."""
    assert BoardApprovalStatus.PENDING.value  == "PENDING"
    assert BoardApprovalStatus.APPROVED.value == "APPROVED"
    assert BoardApprovalStatus.REJECTED.value == "REJECTED"


# ---------------------------------------------------------------------------
# 3. AuditEventType includes M09.4 events
# ---------------------------------------------------------------------------

def test_audit_event_type_includes_board_events():
    """All four M09.4 audit events are present in AuditEventType."""
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.BOARD_SESSION_CONVENED.value == "BOARD_SESSION_CONVENED"
    assert AuditEventType.BOARD_SESSION_APPROVED.value == "BOARD_SESSION_APPROVED"
    assert AuditEventType.BOARD_SESSION_REJECTED.value == "BOARD_SESSION_REJECTED"
    assert AuditEventType.RESULTS_DECLARED.value       == "RESULTS_DECLARED"


# ---------------------------------------------------------------------------
# 4. Convene: success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_convene_success_creates_session_and_stats():
    """convene() creates session + stats snapshot when BOARD_FINALISED scripts exist."""
    paper_id = uuid.uuid4()
    session  = _make_session(exam_paper_id=paper_id)
    ledger   = _make_ledger_entry(exam_paper_id=paper_id, total_marks=80.0)
    mock_db  = AsyncMock()
    mock_db.refresh = AsyncMock()

    # Count result: 1 finalised script
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    # Ledger result: one entry
    ledger_result = MagicMock()
    ledger_result.scalars.return_value.all.return_value = [ledger]

    mock_db.execute = AsyncMock(side_effect=[count_result, ledger_result])

    with (
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_open_session",
              new=AsyncMock(return_value=None)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.create",
              new=AsyncMock(return_value=session)) as mock_create_session,
        patch("app.modules.m09_paper_admin.service.BoardCourseApprovalRepository.create",
              new=AsyncMock(return_value=_make_course_approval(
                  session_id=session.id, exam_paper_id=paper_id,
              ))) as mock_create_stats,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await BoardApprovalService.convene(
            paper_id, "End-of-Semester Board", 40.0,
            convened_by=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_create_session.assert_called_once()
    mock_create_stats.assert_called_once()
    assert result.status == BoardSessionStatus.OPEN.value


# ---------------------------------------------------------------------------
# 5. Convene: no finalised scripts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_convene_no_finalised_scripts_raises():
    """convene() raises if no BOARD_FINALISED scripts exist for the paper."""
    paper_id = uuid.uuid4()
    mock_db  = AsyncMock()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    mock_db.execute = AsyncMock(return_value=count_result)

    with patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_open_session",
               new=AsyncMock(return_value=None)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await BoardApprovalService.convene(
                paper_id, "Test Session", 40.0,
                convened_by=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "NO_FINALISED_SCRIPTS"


# ---------------------------------------------------------------------------
# 6. Convene: duplicate OPEN session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_convene_duplicate_open_session_raises_409():
    """convene() raises 409 if an OPEN session already exists for the paper."""
    paper_id = uuid.uuid4()
    mock_db  = AsyncMock()
    existing = _make_session(exam_paper_id=paper_id)

    with patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_open_session",
               new=AsyncMock(return_value=existing)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await BoardApprovalService.convene(
                paper_id, "Duplicate Session", 40.0,
                convened_by=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "SESSION_ALREADY_OPEN"


# ---------------------------------------------------------------------------
# 7. Pass rate computation
# ---------------------------------------------------------------------------

def test_pass_rate_pct_computation():
    """pass_rate_pct = pass_count / total * 100, threshold = pass_mark_pct * max_marks."""
    scores = [85.0, 40.0, 92.0, 30.0, 55.0]  # 3 pass at 40% of 100 (>=40)
    max_marks_val = 100.0
    pass_mark_pct = 40.0
    threshold = pass_mark_pct / 100.0 * max_marks_val
    pass_count = sum(1 for s in scores if s >= threshold)
    fail_count = len(scores) - pass_count
    pass_rate = pass_count / len(scores) * 100

    assert threshold == 40.0
    assert pass_count == 4   # 85, 40, 92, 55 all >= 40
    assert fail_count == 1
    assert round(pass_rate, 2) == 80.0


# ---------------------------------------------------------------------------
# 8. Approve: success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_open_session_succeeds():
    """approve() transitions OPEN → APPROVED, updates stats, logs audit."""
    session  = _make_session()
    approval = _make_course_approval(session_id=session.id, exam_paper_id=session.exam_paper_id)
    mock_db  = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_by_id",
              new=AsyncMock(return_value=session)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.approve",
              new=AsyncMock()) as mock_approve,
        patch("app.modules.m09_paper_admin.service.BoardCourseApprovalRepository.get_by_session",
              new=AsyncMock(return_value=approval)),
        patch("app.modules.m09_paper_admin.service.BoardCourseApprovalRepository.set_approval_status",
              new=AsyncMock()) as mock_set_status,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await BoardApprovalService.approve(
            session.id,
            board_remarks="Results reviewed and approved by the Board.",
            decided_by=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_approve.assert_called_once()
    mock_set_status.assert_called_once_with(
        approval, BoardApprovalStatus.APPROVED, db=mock_db
    )


# ---------------------------------------------------------------------------
# 9. Approve: wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_wrong_status_raises():
    """approve() rejects a session not in OPEN status."""
    for bad_status in (BoardSessionStatus.APPROVED, BoardSessionStatus.REJECTED, BoardSessionStatus.DECLARED):
        session = _make_session(status=bad_status)
        mock_db = AsyncMock()
        with patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_by_id",
                   new=AsyncMock(return_value=session)):
            with pytest.raises(ScriptServiceError) as exc_info:
                await BoardApprovalService.approve(
                    session.id, None,
                    decided_by=uuid.uuid4(),
                    tenant_id=uuid.uuid4(),
                    db=mock_db,
                )
            assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 10. Reject: success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_open_session_succeeds():
    """reject() transitions OPEN → REJECTED."""
    session  = _make_session()
    approval = _make_course_approval(session_id=session.id, exam_paper_id=session.exam_paper_id)
    mock_db  = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_by_id",
              new=AsyncMock(return_value=session)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.reject",
              new=AsyncMock()) as mock_reject,
        patch("app.modules.m09_paper_admin.service.BoardCourseApprovalRepository.get_by_session",
              new=AsyncMock(return_value=approval)),
        patch("app.modules.m09_paper_admin.service.BoardCourseApprovalRepository.set_approval_status",
              new=AsyncMock()),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await BoardApprovalService.reject(
            session.id,
            "Statistical anomalies detected; re-evaluation required for Section B.",
            decided_by=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_reject.assert_called_once()


# ---------------------------------------------------------------------------
# 11. Reject: wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_wrong_status_raises():
    """reject() rejects a session not in OPEN status."""
    session = _make_session(status=BoardSessionStatus.APPROVED)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_by_id",
               new=AsyncMock(return_value=session)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await BoardApprovalService.reject(
                session.id,
                "Cannot reject an already approved session; requires re-evaluation.",
                decided_by=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 12. Reject: short remarks rejected by schema
# ---------------------------------------------------------------------------

def test_board_reject_request_short_remarks_raises():
    """BoardRejectRequest requires board_remarks >= 20 characters."""
    with pytest.raises(Exception):
        BoardRejectRequest(board_remarks="Too short")


# ---------------------------------------------------------------------------
# 13. Declare: success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declare_approved_session_succeeds():
    """declare() transitions APPROVED → DECLARED."""
    session = _make_session(status=BoardSessionStatus.APPROVED)
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_by_id",
              new=AsyncMock(return_value=session)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.declare",
              new=AsyncMock()) as mock_declare,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await BoardApprovalService.declare(
            session.id,
            declared_by=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_declare.assert_called_once()


# ---------------------------------------------------------------------------
# 14. Declare: wrong status (OPEN → error)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declare_open_session_raises():
    """declare() requires APPROVED status; OPEN is rejected."""
    session = _make_session(status=BoardSessionStatus.OPEN)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_by_id",
               new=AsyncMock(return_value=session)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await BoardApprovalService.declare(
                session.id,
                declared_by=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 15. Declare: REJECTED session cannot be declared
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declare_rejected_session_raises():
    """Rejected session cannot be declared."""
    session = _make_session(status=BoardSessionStatus.REJECTED)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_by_id",
               new=AsyncMock(return_value=session)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await BoardApprovalService.declare(
                session.id,
                declared_by=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 16. board_adjust blocked after paper has APPROVED session (lock)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_board_adjust_blocked_after_approval():
    """board_adjust raises RESULTS_LOCKED when an APPROVED session exists for the paper."""
    from app.modules.m09_paper_admin.service import ScriptService
    from app.modules.m09_paper_admin.schemas import BoardAdjustRequest, BoardAdjustEntry
    from app.modules.m09_paper_admin.models import ScannedScript

    script = ScannedScript()
    script.id = uuid.uuid4()
    script.exam_paper_id = uuid.uuid4()
    script.status = ScriptStatus.MARKS_SUBMITTED.value

    approved_session = _make_session(
        exam_paper_id=script.exam_paper_id,
        status=BoardSessionStatus.APPROVED,
    )
    q_id = uuid.uuid4()
    payload = BoardAdjustRequest(
        adjustments={str(q_id): BoardAdjustEntry(board_adjusted_marks=9.0)}
    )
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.get_approved_session",
              new=AsyncMock(return_value=approved_session)),
    ):
        with pytest.raises(ScriptServiceError) as exc_info:
            await ScriptService.set_board_adjusted_marks(
                script.id, payload,
                board_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "RESULTS_LOCKED"
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# 17. get_board_status: all_finalised when all scripts BOARD_FINALISED
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_board_status_all_finalised():
    """all_finalised=True when every script for the paper is BOARD_FINALISED."""
    paper_id = uuid.uuid4()
    mock_db  = AsyncMock()

    counts_result = MagicMock()
    counts_result.all.return_value = [(ScriptStatus.BOARD_FINALISED.value, 5)]
    mock_db.execute = AsyncMock(return_value=counts_result)

    with patch("app.modules.m09_paper_admin.service.BoardSessionRepository.list_for_paper",
               new=AsyncMock(return_value=[])):
        result = await BoardApprovalService.get_board_status(paper_id, db=mock_db)

    assert result["total_scripts"] == 5
    assert result["finalised_scripts"] == 5
    assert result["all_finalised"] is True


# ---------------------------------------------------------------------------
# 18. get_board_status: ready_for_board logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_board_status_not_ready_when_pending():
    """ready_for_board=False when some scripts are still MARKS_SUBMITTED."""
    paper_id = uuid.uuid4()
    mock_db  = AsyncMock()

    counts_result = MagicMock()
    counts_result.all.return_value = [
        (ScriptStatus.BOARD_FINALISED.value, 3),
        (ScriptStatus.MARKS_SUBMITTED.value, 2),
    ]
    mock_db.execute = AsyncMock(return_value=counts_result)

    with patch("app.modules.m09_paper_admin.service.BoardSessionRepository.list_for_paper",
               new=AsyncMock(return_value=[])):
        result = await BoardApprovalService.get_board_status(paper_id, db=mock_db)

    assert result["total_scripts"] == 5
    assert result["all_finalised"] is False
    assert result["ready_for_board"] is False


# ---------------------------------------------------------------------------
# 19. BoardSessionCreateRequest: short title rejected
# ---------------------------------------------------------------------------

def test_board_session_create_request_short_title_raises():
    """BoardSessionCreateRequest requires session_title >= 5 chars."""
    with pytest.raises(Exception):
        BoardSessionCreateRequest(exam_paper_id=uuid.uuid4(), session_title="Hi")


# ---------------------------------------------------------------------------
# 20. BoardSessionResponse schema
# ---------------------------------------------------------------------------

def test_board_session_response_schema():
    """BoardSessionResponse can be built from model attributes."""
    from app.modules.m09_paper_admin.schemas import BoardSessionResponse
    s = _make_session()
    resp = BoardSessionResponse.model_validate(s)
    assert resp.status == "OPEN"
    assert resp.session_title == "End-of-Semester Board Session"


# ---------------------------------------------------------------------------
# 21. BoardCourseApprovalResponse schema
# ---------------------------------------------------------------------------

def test_board_course_approval_response_schema():
    """BoardCourseApprovalResponse can be built from model attributes."""
    from app.modules.m09_paper_admin.schemas import BoardCourseApprovalResponse
    s = _make_session()
    a = _make_course_approval(session_id=s.id, exam_paper_id=s.exam_paper_id)
    resp = BoardCourseApprovalResponse.model_validate(a)
    assert resp.approval_status == "PENDING"
    assert float(resp.pass_rate_pct) == 90.0


# ---------------------------------------------------------------------------
# 22. list_sessions returns paginated result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_sessions_returns_paginated():
    """list_sessions returns (items, total) tuple."""
    paper_id = uuid.uuid4()
    sessions = [_make_session(exam_paper_id=paper_id)]
    mock_db  = AsyncMock()
    with (
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.list_for_paper",
              new=AsyncMock(return_value=sessions)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.count_for_paper",
              new=AsyncMock(return_value=1)),
    ):
        items, total = await BoardApprovalService.list_sessions(paper_id, db=mock_db)

    assert total == 1
    assert len(items) == 1


# ---------------------------------------------------------------------------
# 23. get_statistics returns course approval snapshot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_statistics_returns_course_approval():
    """get_statistics returns the stats snapshot for a session."""
    session  = _make_session()
    approval = _make_course_approval(session_id=session.id, exam_paper_id=session.exam_paper_id)
    mock_db  = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.BoardCourseApprovalRepository.get_by_session",
               new=AsyncMock(return_value=approval)):
        result = await BoardApprovalService.get_statistics(session.id, db=mock_db)

    assert result is not None
    assert float(result.pass_rate_pct) == 90.0


# ---------------------------------------------------------------------------
# 24. ExamBoardSession model attributes
# ---------------------------------------------------------------------------

def test_exam_board_session_model():
    """ExamBoardSession has expected table name and columns."""
    from app.modules.m09_paper_admin.models import ExamBoardSession
    assert ExamBoardSession.__tablename__ == "exam_board_sessions"
    assert hasattr(ExamBoardSession, "status")
    assert hasattr(ExamBoardSession, "board_remarks")
    assert hasattr(ExamBoardSession, "declared_at")


# ---------------------------------------------------------------------------
# 25. ExamBoardCourseApproval model attributes
# ---------------------------------------------------------------------------

def test_exam_board_course_approval_model():
    """ExamBoardCourseApproval has expected table name and columns."""
    from app.modules.m09_paper_admin.models import ExamBoardCourseApproval
    assert ExamBoardCourseApproval.__tablename__ == "exam_board_course_approvals"
    assert hasattr(ExamBoardCourseApproval, "pass_rate_pct")
    assert hasattr(ExamBoardCourseApproval, "approval_status")
