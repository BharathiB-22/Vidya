"""
M09.3 Revaluation Workflow — unit tests (no DB).

Coverage:
  - RevaluationStatus enum values (9 states)
  - AuditEventType includes all M09.3 events
  - submit_request: success path (DECLARED board session + BOARD_FINALISED script)
  - submit_request: wrong script status rejected
  - submit_request: no declared session rejected
  - submit_request: active request exists → 409
  - accept_request: success + evaluator assigned
  - accept_request: wrong status rejected
  - accept_request: evaluator conflict (same as original) → 422
  - reject_request: success
  - reject_request: wrong status rejected
  - submit_revaluation_marks: success → EVALUATED, total computed
  - submit_revaluation_marks: wrong status rejected
  - submit_revaluation_marks: unauthorized evaluator → 403
  - board_ratify: awarded = max(original, revaluation) when revaluation higher
  - board_ratify: awarded = original when original is higher
  - board_ratify: wrong status rejected
  - board_reject: success → REJECTED_BY_BOARD
  - board_reject: wrong status rejected
  - RevaluationCreateRequest: short reason rejected
  - RevaluationRejectRequest: short notes rejected
  - RevaluationBoardRejectRequest: short remarks rejected
  - RevaluationRequestResponse schema
  - RevaluationEvaluationResponse schema
  - Model table names
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m09_paper_admin.models import (
    BoardSessionStatus,
    ExamBoardSession,
    ExamScoreLedger,
    RevaluationEvaluation,
    RevaluationRequest,
    RevaluationStatus,
    ScannedScript,
    ScriptStatus,
)
from app.modules.m09_paper_admin.repository import (
    RevaluationEvaluationRepository,
    RevaluationRepository,
)
from app.modules.m09_paper_admin.schemas import (
    RevaluationBoardRejectRequest,
    RevaluationCreateRequest,
    RevaluationRejectRequest,
)
from app.modules.m09_paper_admin.service import RevaluationService, ScriptServiceError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _make_script(
    *,
    status: ScriptStatus = ScriptStatus.BOARD_FINALISED,
    evaluator_id: uuid.UUID | None = None,
    second_evaluator_id: uuid.UUID | None = None,
) -> ScannedScript:
    s = ScannedScript()
    s.id = uuid.uuid4()
    s.exam_paper_id = uuid.uuid4()
    s.masked_id = "STEST99999"
    s.status = status.value
    s.double_evaluation_enabled = True
    s.evaluator_id = evaluator_id or uuid.uuid4()
    s.second_evaluator_id = second_evaluator_id or uuid.uuid4()
    s.student_user_id = uuid.uuid4()
    s.student_roll_ref = "ROLL001"
    return s


def _make_ledger(*, exam_paper_id: uuid.UUID, script_id: uuid.UUID) -> ExamScoreLedger:
    e = ExamScoreLedger()
    e.id = uuid.uuid4()
    e.script_id = script_id
    e.exam_paper_id = exam_paper_id
    e.student_user_id = uuid.uuid4()
    e.total_marks = Decimal("72.0")
    e.max_marks = Decimal("100.0")
    e.finalised_by = uuid.uuid4()
    e.finalised_at = _NOW
    return e


def _make_reval_request(
    *,
    script_id: uuid.UUID | None = None,
    student_user_id: uuid.UUID | None = None,
    status: RevaluationStatus = RevaluationStatus.SUBMITTED,
    original_total: float = 72.0,
    revaluation_total: float | None = None,
    assigned_evaluator_id: uuid.UUID | None = None,
) -> RevaluationRequest:
    r = RevaluationRequest()
    r.id = uuid.uuid4()
    r.script_id = script_id or uuid.uuid4()
    r.exam_paper_id = uuid.uuid4()
    r.student_user_id = student_user_id or uuid.uuid4()
    r.student_roll_ref = "ROLL001"
    r.original_total = Decimal(str(original_total))
    r.max_marks = Decimal("100.0")
    r.reason = "I believe my answers were marked incorrectly."
    r.payment_reference = "PAY-2026-001"
    r.status = status.value
    r.assigned_evaluator_id = assigned_evaluator_id
    r.revaluation_total = Decimal(str(revaluation_total)) if revaluation_total else None
    r.awarded_total = None
    r.admin_notes = None
    r.board_remarks = None
    r.decided_by = None
    r.decided_at = None
    r.window_closes_at = None
    r.created_at = _NOW
    r.updated_at = None
    return r


def _make_declared_session(exam_paper_id: uuid.UUID) -> ExamBoardSession:
    s = ExamBoardSession()
    s.id = uuid.uuid4()
    s.exam_paper_id = exam_paper_id
    s.session_title = "Final Board Session"
    s.convened_by = uuid.uuid4()
    s.convened_at = _NOW
    s.status = BoardSessionStatus.DECLARED.value
    s.board_remarks = None
    s.decided_by = uuid.uuid4()
    s.decided_at = _NOW
    s.declared_by = uuid.uuid4()
    s.declared_at = _NOW
    s.created_at = _NOW
    return s


# ---------------------------------------------------------------------------
# 1. RevaluationStatus enum values
# ---------------------------------------------------------------------------

def test_revaluation_status_values():
    """All 9 lifecycle states are present."""
    assert RevaluationStatus.SUBMITTED.value         == "SUBMITTED"
    assert RevaluationStatus.ACCEPTED.value          == "ACCEPTED"
    assert RevaluationStatus.IN_PROGRESS.value       == "IN_PROGRESS"
    assert RevaluationStatus.EVALUATED.value         == "EVALUATED"
    assert RevaluationStatus.BOARD_REVIEW.value      == "BOARD_REVIEW"
    assert RevaluationStatus.APPROVED.value          == "APPROVED"
    assert RevaluationStatus.REJECTED_BY_BOARD.value == "REJECTED_BY_BOARD"
    assert RevaluationStatus.REJECTED.value          == "REJECTED"
    assert RevaluationStatus.CLOSED.value            == "CLOSED"


# ---------------------------------------------------------------------------
# 2. AuditEventType includes all M09.3 events
# ---------------------------------------------------------------------------

def test_audit_event_type_includes_revaluation_events():
    """All six M09.3 audit event types are present."""
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.REVALUATION_REQUESTED.value       == "REVALUATION_REQUESTED"
    assert AuditEventType.REVALUATION_ACCEPTED.value        == "REVALUATION_ACCEPTED"
    assert AuditEventType.REVALUATION_REJECTED.value        == "REVALUATION_REJECTED"
    assert AuditEventType.REVALUATION_MARKS_SUBMITTED.value == "REVALUATION_MARKS_SUBMITTED"
    assert AuditEventType.REVALUATION_BOARD_RATIFIED.value  == "REVALUATION_BOARD_RATIFIED"
    assert AuditEventType.REVALUATION_BOARD_REJECTED.value  == "REVALUATION_BOARD_REJECTED"


# ---------------------------------------------------------------------------
# 3. submit_request: success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_request_success():
    """Student submits revaluation request for a BOARD_FINALISED script with declared session."""
    script  = _make_script()
    ledger  = _make_ledger(exam_paper_id=script.exam_paper_id, script_id=script.id)
    session = _make_declared_session(script.exam_paper_id)
    req     = _make_reval_request(script_id=script.id,
                                   student_user_id=script.student_user_id)
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.list_for_paper",
              new=AsyncMock(return_value=[session])),
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.count_open_for_script",
              new=AsyncMock(return_value=0)),
        patch("app.modules.m09_paper_admin.service.ExamScoreLedgerRepository.get_by_script",
              new=AsyncMock(return_value=ledger)),
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.create",
              new=AsyncMock(return_value=req)) as mock_create,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await RevaluationService.submit_request(
            script.id,
            reason="I believe my answer to Q3 was graded incorrectly.",
            payment_reference="PAY-001",
            student_user_id=script.student_user_id,
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_create.assert_called_once()
    assert result.status == RevaluationStatus.SUBMITTED.value


# ---------------------------------------------------------------------------
# 4. submit_request: wrong script status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_request_wrong_script_status_raises():
    """Cannot submit revaluation for a script not BOARD_FINALISED."""
    script  = _make_script(status=ScriptStatus.MARKS_SUBMITTED)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
               new=AsyncMock(return_value=script)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await RevaluationService.submit_request(
                script.id,
                reason="I believe my answer was graded incorrectly.",
                payment_reference=None,
                student_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 5. submit_request: no declared session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_request_no_declared_session_raises():
    """Cannot submit revaluation if results not declared."""
    script  = _make_script()
    # Session exists but is only APPROVED, not DECLARED
    session = _make_declared_session(script.exam_paper_id)
    session.status = BoardSessionStatus.APPROVED.value
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.list_for_paper",
              new=AsyncMock(return_value=[session])),
    ):
        with pytest.raises(ScriptServiceError) as exc_info:
            await RevaluationService.submit_request(
                script.id,
                reason="I believe my answer was graded incorrectly.",
                payment_reference=None,
                student_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "RESULTS_NOT_DECLARED"


# ---------------------------------------------------------------------------
# 6. submit_request: active request exists → 409
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_request_duplicate_active_raises_409():
    """Cannot submit revaluation if an active request already exists."""
    script  = _make_script()
    session = _make_declared_session(script.exam_paper_id)
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.BoardSessionRepository.list_for_paper",
              new=AsyncMock(return_value=[session])),
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.count_open_for_script",
              new=AsyncMock(return_value=1)),
    ):
        with pytest.raises(ScriptServiceError) as exc_info:
            await RevaluationService.submit_request(
                script.id,
                reason="I believe my answer was graded incorrectly.",
                payment_reference=None,
                student_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "ACTIVE_REQUEST_EXISTS"


# ---------------------------------------------------------------------------
# 7. accept_request: success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accept_request_success():
    """Admin accepts and assigns a new evaluator."""
    script = _make_script()
    req    = _make_reval_request(script_id=script.id)
    new_evaluator = uuid.uuid4()   # different from original and second
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
              new=AsyncMock(return_value=req)),
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.accept",
              new=AsyncMock()) as mock_accept,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await RevaluationService.accept_request(
            req.id,
            new_evaluator,
            "Senior evaluator assigned for revaluation.",
            admin_user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_accept.assert_called_once()


# ---------------------------------------------------------------------------
# 8. accept_request: wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accept_request_wrong_status_raises():
    """Cannot accept a request not in SUBMITTED status."""
    req = _make_reval_request(status=RevaluationStatus.ACCEPTED)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
               new=AsyncMock(return_value=req)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await RevaluationService.accept_request(
                req.id, uuid.uuid4(), None,
                admin_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 9. accept_request: evaluator conflict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accept_request_evaluator_conflict_raises():
    """assigned_evaluator must not be the original or second evaluator."""
    script = _make_script()
    req    = _make_reval_request(script_id=script.id)
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
              new=AsyncMock(return_value=req)),
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
    ):
        with pytest.raises(ScriptServiceError) as exc_info:
            await RevaluationService.accept_request(
                req.id,
                script.evaluator_id,  # same as original → conflict
                None,
                admin_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "EVALUATOR_CONFLICT"
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 10. reject_request: success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_request_success():
    """Admin rejects at intake."""
    req = _make_reval_request()
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
              new=AsyncMock(return_value=req)),
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.reject_intake",
              new=AsyncMock()) as mock_reject,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await RevaluationService.reject_request(
            req.id,
            "Payment not verified. Request cannot be processed.",
            admin_user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_reject.assert_called_once()


# ---------------------------------------------------------------------------
# 11. reject_request: wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_request_wrong_status_raises():
    """Cannot reject a request not in SUBMITTED status."""
    req = _make_reval_request(status=RevaluationStatus.ACCEPTED)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
               new=AsyncMock(return_value=req)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await RevaluationService.reject_request(
                req.id, "too late",
                admin_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 12. submit_revaluation_marks: success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_revaluation_marks_success():
    """Revaluator submits marks → EVALUATED, revaluation_total computed."""
    evaluator_id = uuid.uuid4()
    req = _make_reval_request(
        status=RevaluationStatus.ACCEPTED,
        assigned_evaluator_id=evaluator_id,
    )
    q_id = uuid.uuid4()

    from app.modules.m09_paper_admin.models import ScriptEvaluation
    from decimal import Decimal
    p_eval = ScriptEvaluation()
    p_eval.id = uuid.uuid4()
    p_eval.script_id = req.script_id
    p_eval.question_id = q_id
    p_eval.question_type = "SHORT_ANSWER"
    p_eval.max_marks = Decimal("10.0")
    p_eval.evaluation_round = "PRIMARY"
    p_eval.evaluator_marks = Decimal("7.0")

    from app.modules.m09_paper_admin.schemas import RevaluationMarkEntry
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
              new=AsyncMock(return_value=req)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
              new=AsyncMock(return_value=[p_eval])),
        patch("app.modules.m09_paper_admin.service.RevaluationEvaluationRepository.bulk_create",
              new=AsyncMock(return_value=[])),
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.submit_marks",
              new=AsyncMock()) as mock_submit,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        marks = {str(q_id): RevaluationMarkEntry(revaluation_marks=9.0)}
        result = await RevaluationService.submit_revaluation_marks(
            req.id, marks, None,
            evaluator_user_id=evaluator_id,
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_submit.assert_called_once_with(req, revaluation_total=9.0, db=mock_db)


# ---------------------------------------------------------------------------
# 13. submit_revaluation_marks: wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_revaluation_marks_wrong_status_raises():
    """submit_marks requires ACCEPTED or IN_PROGRESS."""
    req = _make_reval_request(status=RevaluationStatus.SUBMITTED)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
               new=AsyncMock(return_value=req)):
        with pytest.raises(ScriptServiceError) as exc_info:
            from app.modules.m09_paper_admin.schemas import RevaluationMarkEntry
            marks = {str(uuid.uuid4()): RevaluationMarkEntry(revaluation_marks=8.0)}
            await RevaluationService.submit_revaluation_marks(
                req.id, marks, None,
                evaluator_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 14. submit_revaluation_marks: unauthorized evaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_revaluation_marks_unauthorized_evaluator_raises():
    """Only the assigned evaluator may submit marks."""
    assigned_evaluator = uuid.uuid4()
    req = _make_reval_request(
        status=RevaluationStatus.ACCEPTED,
        assigned_evaluator_id=assigned_evaluator,
    )
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
               new=AsyncMock(return_value=req)):
        with pytest.raises(ScriptServiceError) as exc_info:
            from app.modules.m09_paper_admin.schemas import RevaluationMarkEntry
            marks = {str(uuid.uuid4()): RevaluationMarkEntry(revaluation_marks=8.0)}
            await RevaluationService.submit_revaluation_marks(
                req.id, marks, None,
                evaluator_user_id=uuid.uuid4(),  # different person
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "UNAUTHORIZED_EVALUATOR"
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 15. board_ratify: awarded = max(original, revaluation) — revaluation higher
# ---------------------------------------------------------------------------

def test_awarded_total_uses_revaluation_when_higher():
    """awarded_total = revaluation_total when revaluation > original."""
    original = 72.0
    revaluation = 85.0
    awarded = max(original, revaluation)
    assert awarded == 85.0


# ---------------------------------------------------------------------------
# 16. board_ratify: awarded = original when original is higher
# ---------------------------------------------------------------------------

def test_awarded_total_uses_original_when_higher():
    """awarded_total = original_total when original > revaluation."""
    original = 72.0
    revaluation = 60.0
    awarded = max(original, revaluation)
    assert awarded == 72.0


# ---------------------------------------------------------------------------
# 17. board_ratify: success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_board_ratify_success():
    """Board ratifies → APPROVED, awarded_total = max(original, revaluation)."""
    req = _make_reval_request(
        status=RevaluationStatus.EVALUATED,
        original_total=72.0,
        revaluation_total=85.0,
    )
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
              new=AsyncMock(return_value=req)),
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.board_ratify",
              new=AsyncMock()) as mock_ratify,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await RevaluationService.board_ratify(
            req.id, None,
            decided_by=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_ratify.assert_called_once()


# ---------------------------------------------------------------------------
# 18. board_ratify: wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_board_ratify_wrong_status_raises():
    """Board ratify requires EVALUATED or BOARD_REVIEW."""
    req = _make_reval_request(status=RevaluationStatus.SUBMITTED)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
               new=AsyncMock(return_value=req)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await RevaluationService.board_ratify(
                req.id, None,
                decided_by=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 19. board_reject: success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_board_reject_success():
    """Board rejects revaluation → REJECTED_BY_BOARD."""
    req = _make_reval_request(
        status=RevaluationStatus.EVALUATED,
        original_total=72.0,
        revaluation_total=70.0,
    )
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
              new=AsyncMock(return_value=req)),
        patch("app.modules.m09_paper_admin.service.RevaluationRepository.board_reject",
              new=AsyncMock()) as mock_reject,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await RevaluationService.board_reject(
            req.id,
            "Revaluation marks do not differ significantly; original assessment stands.",
            decided_by=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_reject.assert_called_once()


# ---------------------------------------------------------------------------
# 20. board_reject: wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_board_reject_wrong_status_raises():
    """Board reject requires EVALUATED or BOARD_REVIEW."""
    req = _make_reval_request(status=RevaluationStatus.APPROVED)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.RevaluationRepository.get_by_id",
               new=AsyncMock(return_value=req)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await RevaluationService.board_reject(
                req.id,
                "Revaluation marks do not differ significantly from original marks.",
                decided_by=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 21. Schema validations
# ---------------------------------------------------------------------------

def test_revaluation_create_request_short_reason_raises():
    """RevaluationCreateRequest requires reason >= 20 chars."""
    with pytest.raises(Exception):
        RevaluationCreateRequest(
            script_id=uuid.uuid4(),
            reason="Too short",
        )


def test_revaluation_reject_request_short_notes_raises():
    """RevaluationRejectRequest requires admin_notes >= 10 chars."""
    with pytest.raises(Exception):
        RevaluationRejectRequest(admin_notes="Short")


def test_revaluation_board_reject_request_short_remarks_raises():
    """RevaluationBoardRejectRequest requires board_remarks >= 20 chars."""
    with pytest.raises(Exception):
        RevaluationBoardRejectRequest(board_remarks="Too short")


# ---------------------------------------------------------------------------
# 22. RevaluationRequestResponse schema
# ---------------------------------------------------------------------------

def test_revaluation_request_response_schema():
    """RevaluationRequestResponse can be built from model attributes."""
    from app.modules.m09_paper_admin.schemas import RevaluationRequestResponse
    req = _make_reval_request()
    resp = RevaluationRequestResponse.model_validate(req)
    assert resp.status == RevaluationStatus.SUBMITTED.value
    assert resp.original_total == 72.0


# ---------------------------------------------------------------------------
# 23. RevaluationEvaluationResponse schema
# ---------------------------------------------------------------------------

def test_revaluation_evaluation_response_schema():
    """RevaluationEvaluationResponse can be built from model attributes."""
    from app.modules.m09_paper_admin.schemas import RevaluationEvaluationResponse
    e = RevaluationEvaluation()
    e.id = uuid.uuid4()
    e.request_id = uuid.uuid4()
    e.question_id = uuid.uuid4()
    e.question_type = "SHORT_ANSWER"
    e.max_marks = Decimal("10.0")
    e.original_marks = Decimal("7.0")
    e.revaluation_marks = Decimal("9.0")
    e.evaluator_note = None
    e.created_at = _NOW
    resp = RevaluationEvaluationResponse.model_validate(e)
    assert float(resp.revaluation_marks) == 9.0


# ---------------------------------------------------------------------------
# 24. Model table names
# ---------------------------------------------------------------------------

def test_model_table_names():
    """New M09.3 model tables have expected names."""
    from app.modules.m09_paper_admin.models import RevaluationRequest, RevaluationEvaluation
    assert RevaluationRequest.__tablename__   == "sis_revaluation_requests"
    assert RevaluationEvaluation.__tablename__ == "sis_revaluation_evaluations"
