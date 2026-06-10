"""
M09.5 Digital Exams Phase 1 — unit tests (no DB).

Coverage:
  - DigitalExamSession model fields and enum values
  - DigitalExamAttempt model fields and status enum
  - DigitalExamResponse model fields
  - DigitalSessionCreate schema validation
  - DigitalResponseIn schema: requires at least one field
  - DigitalResponseIn: MCQ option accepted
  - DigitalResponseIn: subjective text accepted
  - DigitalResponseIn: both provided — accepted
  - DigitalResponseIn: neither provided — rejected
  - DigitalSessionResponse.attempt_count default
  - DigitalResultResponse fields
  - Repository: DigitalSessionRepository.create (mocked)
  - Repository: DigitalAttemptRepository.get_for_student (mocked)
  - Repository: DigitalResponseRepository.score_mcq correct answer
  - Repository: DigitalResponseRepository.score_mcq wrong answer
  - Repository: DigitalResponseRepository.score_mcq missing option
  - Service: create_session calls repo and audit (mocked)
  - Service: activate_session rejects non-DRAFT (mocked)
  - Service: activate_session DRAFT success (mocked)
  - Service: close_session already CLOSED rejected (mocked)
  - Service: close_session ACTIVE success (mocked)
  - Service: start_or_resume_attempt rejects non-ACTIVE session (mocked)
  - Service: start_or_resume_attempt creates new attempt (mocked)
  - Service: start_or_resume_attempt returns existing attempt (mocked)
  - Service: start_or_resume_attempt rejects already-submitted (mocked)
  - Service: save_response rejects non-IN_PROGRESS attempt (mocked)
  - Service: submit_attempt rejects non-IN_PROGRESS (mocked)
  - AuditEventType includes M09.5 digital exam events
  - Model imports sanity check
  - DigitalExamSessionStatus enum values
  - DigitalAttemptStatus enum values
  - ScriptStatus still includes all M09.1–M09.4 values
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m09_paper_admin.models import (
    DigitalAttemptStatus,
    DigitalExamAttempt,
    DigitalExamResponse,
    DigitalExamSession,
    DigitalExamSessionStatus,
    ScriptStatus,
)
from app.modules.m09_paper_admin.repository import (
    DigitalAttemptRepository,
    DigitalResponseRepository,
    DigitalSessionRepository,
)
from app.modules.m09_paper_admin.schemas import (
    DigitalAttemptResponse,
    DigitalResponseIn,
    DigitalResultResponse,
    DigitalSessionCreate,
    DigitalSessionResponse,
)
from app.modules.m09_paper_admin.service import DigitalExamError, DigitalExamService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _make_session(
    *,
    status: DigitalExamSessionStatus = DigitalExamSessionStatus.DRAFT,
    exam_paper_id: uuid.UUID | None = None,
    max_duration_mins: int = 180,
) -> DigitalExamSession:
    s = DigitalExamSession()
    s.id = uuid.uuid4()
    s.exam_paper_id = exam_paper_id or uuid.uuid4()
    s.created_by = uuid.uuid4()
    s.title = "End Sem CS101 Digital"
    s.status = status
    s.max_duration_mins = max_duration_mins
    s.window_start = None
    s.window_end = None
    s.instructions = None
    s.activated_at = None
    s.closed_at = None
    s.created_at = _NOW
    return s


def _make_attempt(
    *,
    session_id: uuid.UUID | None = None,
    student_user_id: uuid.UUID | None = None,
    status: DigitalAttemptStatus = DigitalAttemptStatus.IN_PROGRESS,
    expires_at=None,
) -> DigitalExamAttempt:
    a = DigitalExamAttempt()
    a.id = uuid.uuid4()
    a.session_id = session_id or uuid.uuid4()
    a.student_user_id = student_user_id or uuid.uuid4()
    a.status = status
    a.started_at = _NOW
    a.expires_at = expires_at or (_NOW + timedelta(hours=3))
    a.submitted_at = None
    a.auto_scored_at = None
    a.auto_score = None
    a.mcq_max_score = None
    a.created_at = _NOW
    return a


def _make_response(
    *,
    attempt_id: uuid.UUID | None = None,
    question_id: uuid.UUID | None = None,
    question_type: str = "MCQ",
    selected_option: str | None = "A",
    response_text: str | None = None,
    is_auto_scored: bool = False,
    auto_score=None,
    is_correct=None,
) -> DigitalExamResponse:
    r = DigitalExamResponse()
    r.id = uuid.uuid4()
    r.attempt_id = attempt_id or uuid.uuid4()
    r.question_id = question_id or uuid.uuid4()
    r.question_type = question_type
    r.selected_option = selected_option
    r.response_text = response_text
    r.is_auto_scored = is_auto_scored
    r.auto_score = auto_score
    r.is_correct = is_correct
    r.answered_at = _NOW
    r.updated_at = None
    r.created_at = _NOW
    return r


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

def test_digital_exam_session_model_fields():
    s = _make_session()
    assert s.status == DigitalExamSessionStatus.DRAFT
    assert s.max_duration_mins == 180
    assert s.activated_at is None


def test_digital_exam_attempt_model_fields():
    a = _make_attempt()
    assert a.status == DigitalAttemptStatus.IN_PROGRESS
    assert a.auto_score is None
    assert a.submitted_at is None


def test_digital_exam_response_model_fields():
    r = _make_response()
    assert r.question_type == "MCQ"
    assert r.selected_option == "A"
    assert r.is_auto_scored is False


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------

def test_digital_exam_session_status_values():
    assert DigitalExamSessionStatus.DRAFT  == "DRAFT"
    assert DigitalExamSessionStatus.ACTIVE == "ACTIVE"
    assert DigitalExamSessionStatus.CLOSED == "CLOSED"


def test_digital_attempt_status_values():
    assert DigitalAttemptStatus.IN_PROGRESS == "IN_PROGRESS"
    assert DigitalAttemptStatus.SUBMITTED   == "SUBMITTED"
    assert DigitalAttemptStatus.SCORED      == "SCORED"


def test_script_status_still_has_m09_values():
    assert ScriptStatus.BOARD_FINALISED       in list(ScriptStatus)
    assert ScriptStatus.MODERATION_PENDING    in list(ScriptStatus)
    assert ScriptStatus.MODERATION_COMPLETE   in list(ScriptStatus)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_digital_session_create_schema():
    payload = DigitalSessionCreate(
        exam_paper_id=uuid.uuid4(),
        title="CS101 Digital End Sem",
        max_duration_mins=120,
    )
    assert payload.max_duration_mins == 120
    assert payload.window_start is None


def test_digital_session_create_defaults():
    payload = DigitalSessionCreate(
        exam_paper_id=uuid.uuid4(),
        title="Quick Test",
    )
    assert payload.max_duration_mins == 180


def test_digital_session_create_duration_bounds():
    with pytest.raises(Exception):
        DigitalSessionCreate(exam_paper_id=uuid.uuid4(), title="X", max_duration_mins=5)
    with pytest.raises(Exception):
        DigitalSessionCreate(exam_paper_id=uuid.uuid4(), title="X", max_duration_mins=700)


def test_digital_response_in_mcq_only():
    payload = DigitalResponseIn(selected_option="B")
    assert payload.selected_option == "B"
    assert payload.response_text is None


def test_digital_response_in_subjective_only():
    payload = DigitalResponseIn(response_text="Paris is the capital of France.")
    assert payload.response_text is not None
    assert payload.selected_option is None


def test_digital_response_in_both_fields():
    payload = DigitalResponseIn(selected_option="C", response_text="extra")
    assert payload.selected_option == "C"


def test_digital_response_in_neither_rejected():
    with pytest.raises(Exception):
        DigitalResponseIn()


def test_digital_session_response_attempt_count_default():
    session = _make_session()
    out = DigitalSessionResponse(
        id=session.id,
        exam_paper_id=session.exam_paper_id,
        created_by=session.created_by,
        title=session.title,
        status=session.status,
        max_duration_mins=session.max_duration_mins,
        window_start=None,
        window_end=None,
        instructions=None,
        activated_at=None,
        closed_at=None,
        created_at=session.created_at,
    )
    assert out.attempt_count == 0
    assert out.scored_count == 0


def test_digital_result_response_fields():
    attempt = _make_attempt(status=DigitalAttemptStatus.SCORED)
    attempt.auto_score = Decimal("30.0")
    attempt.mcq_max_score = Decimal("40.0")
    out = DigitalResultResponse(
        attempt=DigitalAttemptResponse(
            id=attempt.id,
            session_id=attempt.session_id,
            student_user_id=attempt.student_user_id,
            status=attempt.status,
            started_at=attempt.started_at,
            expires_at=attempt.expires_at,
            submitted_at=None,
            auto_scored_at=None,
            auto_score=30.0,
            mcq_max_score=40.0,
            created_at=attempt.created_at,
        ),
        responses=[],
        total_questions=10,
        mcq_questions=4,
        subjective_questions=6,
        attempted_count=3,
        correct_mcq=3,
    )
    assert out.correct_mcq == 3
    assert out.mcq_questions == 4


# ---------------------------------------------------------------------------
# Repository: DigitalResponseRepository.score_mcq
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_mcq_correct_answer():
    response = _make_response(selected_option="B")
    db = AsyncMock()
    db.flush = AsyncMock()
    result = await DigitalResponseRepository.score_mcq(response, "B", 4.0, db=db)
    assert result.is_correct is True
    assert float(result.auto_score) == 4.0
    assert result.is_auto_scored is True


@pytest.mark.asyncio
async def test_score_mcq_wrong_answer():
    response = _make_response(selected_option="A")
    db = AsyncMock()
    db.flush = AsyncMock()
    result = await DigitalResponseRepository.score_mcq(response, "C", 4.0, db=db)
    assert result.is_correct is False
    assert float(result.auto_score) == 0.0


@pytest.mark.asyncio
async def test_score_mcq_case_insensitive():
    response = _make_response(selected_option="b")
    db = AsyncMock()
    db.flush = AsyncMock()
    result = await DigitalResponseRepository.score_mcq(response, "B", 2.0, db=db)
    assert result.is_correct is True


@pytest.mark.asyncio
async def test_score_mcq_no_selection():
    response = _make_response(selected_option=None)
    db = AsyncMock()
    db.flush = AsyncMock()
    result = await DigitalResponseRepository.score_mcq(response, "A", 2.0, db=db)
    assert result.is_correct is False
    assert float(result.auto_score) == 0.0


@pytest.mark.asyncio
async def test_score_mcq_no_correct_option_in_paper():
    response = _make_response(selected_option="A")
    db = AsyncMock()
    db.flush = AsyncMock()
    result = await DigitalResponseRepository.score_mcq(response, None, 2.0, db=db)
    assert result.is_correct is False


# ---------------------------------------------------------------------------
# Service: create_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_session_calls_repo_and_audit():
    db = AsyncMock()
    created_session = _make_session()

    with (
        patch.object(DigitalSessionRepository, "create", new=AsyncMock(return_value=created_session)) as mock_create,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await DigitalExamService.create_session(
            exam_paper_id=created_session.exam_paper_id,
            created_by=created_session.created_by,
            title=created_session.title,
            max_duration_mins=180,
            window_start=None,
            window_end=None,
            instructions=None,
            db=db,
        )
    assert result.id == created_session.id
    mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# Service: activate_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_activate_session_draft_success():
    db = AsyncMock()
    session = _make_session(status=DigitalExamSessionStatus.DRAFT)

    with (
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(DigitalSessionRepository, "activate", new=AsyncMock(return_value=session)),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await DigitalExamService.activate_session(
            session.id, actor_user_id=uuid.uuid4(), db=db
        )
    assert result.id == session.id


@pytest.mark.asyncio
async def test_activate_session_already_active_rejected():
    db = AsyncMock()
    session = _make_session(status=DigitalExamSessionStatus.ACTIVE)

    with patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.activate_session(
                session.id, actor_user_id=uuid.uuid4(), db=db
            )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_activate_session_not_found():
    db = AsyncMock()
    with patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.activate_session(uuid.uuid4(), actor_user_id=uuid.uuid4(), db=db)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Service: close_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_session_active_success():
    db = AsyncMock()
    session = _make_session(status=DigitalExamSessionStatus.ACTIVE)

    with (
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(DigitalSessionRepository, "close", new=AsyncMock(return_value=session)),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await DigitalExamService.close_session(
            session.id, actor_user_id=uuid.uuid4(), db=db
        )
    assert result.id == session.id


@pytest.mark.asyncio
async def test_close_session_already_closed_rejected():
    db = AsyncMock()
    session = _make_session(status=DigitalExamSessionStatus.CLOSED)

    with patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.close_session(
                session.id, actor_user_id=uuid.uuid4(), db=db
            )
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Service: start_or_resume_attempt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_attempt_non_active_session_rejected():
    db = AsyncMock()
    session = _make_session(status=DigitalExamSessionStatus.DRAFT)

    with patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.start_or_resume_attempt(
                session.id, student_user_id=uuid.uuid4(), db=db
            )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_start_attempt_new_creates_record():
    db = AsyncMock()
    session = _make_session(status=DigitalExamSessionStatus.ACTIVE)
    student_id = uuid.uuid4()
    attempt = _make_attempt(session_id=session.id, student_user_id=student_id)

    with (
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(DigitalAttemptRepository, "get_for_student", new=AsyncMock(return_value=None)),
        patch.object(DigitalAttemptRepository, "create", new=AsyncMock(return_value=attempt)),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await DigitalExamService.start_or_resume_attempt(
            session.id, student_user_id=student_id, db=db
        )
    assert result.id == attempt.id


@pytest.mark.asyncio
async def test_start_attempt_resumes_existing():
    db = AsyncMock()
    session = _make_session(status=DigitalExamSessionStatus.ACTIVE)
    student_id = uuid.uuid4()
    existing = _make_attempt(session_id=session.id, student_user_id=student_id)

    with (
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(DigitalAttemptRepository, "get_for_student", new=AsyncMock(return_value=existing)),
    ):
        result = await DigitalExamService.start_or_resume_attempt(
            session.id, student_user_id=student_id, db=db
        )
    assert result.id == existing.id


@pytest.mark.asyncio
async def test_start_attempt_already_submitted_rejected():
    db = AsyncMock()
    session = _make_session(status=DigitalExamSessionStatus.ACTIVE)
    student_id = uuid.uuid4()
    existing = _make_attempt(
        session_id=session.id,
        student_user_id=student_id,
        status=DigitalAttemptStatus.SUBMITTED,
    )

    with (
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(DigitalAttemptRepository, "get_for_student", new=AsyncMock(return_value=existing)),
    ):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.start_or_resume_attempt(
                session.id, student_user_id=student_id, db=db
            )
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Service: save_response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_response_rejects_submitted_attempt():
    db = AsyncMock()
    student_id = uuid.uuid4()
    session = _make_session(status=DigitalExamSessionStatus.ACTIVE)
    attempt = _make_attempt(
        student_user_id=student_id,
        status=DigitalAttemptStatus.SUBMITTED,
    )

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
    ):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.save_response(
                attempt.id,
                uuid.uuid4(),
                student_user_id=student_id,
                selected_option="A",
                response_text=None,
                db=db,
            )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_save_response_rejects_wrong_student():
    db = AsyncMock()
    attempt = _make_attempt(student_user_id=uuid.uuid4())

    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.save_response(
                attempt.id,
                uuid.uuid4(),
                student_user_id=uuid.uuid4(),  # different student
                selected_option="A",
                response_text=None,
                db=db,
            )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Service: submit_attempt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_rejects_already_submitted():
    db = AsyncMock()
    student_id = uuid.uuid4()
    attempt = _make_attempt(student_user_id=student_id, status=DigitalAttemptStatus.SUBMITTED)

    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.submit_attempt(
                attempt.id, student_user_id=student_id, db=db
            )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_submit_rejects_wrong_student():
    db = AsyncMock()
    attempt = _make_attempt(student_user_id=uuid.uuid4(), status=DigitalAttemptStatus.IN_PROGRESS)

    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.submit_attempt(
                attempt.id, student_user_id=uuid.uuid4(), db=db
            )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------

def test_audit_event_type_includes_digital_exam_events():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.DIGITAL_EXAM_SESSION_CREATED   == "DIGITAL_EXAM_SESSION_CREATED"
    assert AuditEventType.DIGITAL_EXAM_SESSION_ACTIVATED == "DIGITAL_EXAM_SESSION_ACTIVATED"
    assert AuditEventType.DIGITAL_EXAM_SESSION_CLOSED    == "DIGITAL_EXAM_SESSION_CLOSED"
    assert AuditEventType.DIGITAL_EXAM_ATTEMPT_STARTED   == "DIGITAL_EXAM_ATTEMPT_STARTED"
    assert AuditEventType.DIGITAL_EXAM_RESPONSE_SAVED    == "DIGITAL_EXAM_RESPONSE_SAVED"
    assert AuditEventType.DIGITAL_EXAM_SUBMITTED         == "DIGITAL_EXAM_SUBMITTED"
    assert AuditEventType.DIGITAL_EXAM_AUTO_SCORED       == "DIGITAL_EXAM_AUTO_SCORED"


# ---------------------------------------------------------------------------
# Model imports sanity
# ---------------------------------------------------------------------------

def test_model_imports():
    from app.modules.m09_paper_admin.models import (
        DigitalAttemptStatus,
        DigitalExamAttempt,
        DigitalExamResponse,
        DigitalExamSession,
        DigitalExamSessionStatus,
    )
    assert DigitalExamSession.__tablename__ == "digital_exam_sessions"
    assert DigitalExamAttempt.__tablename__ == "digital_exam_attempts"
    assert DigitalExamResponse.__tablename__ == "digital_exam_responses"


def test_repository_imports():
    from app.modules.m09_paper_admin.repository import (
        DigitalAttemptRepository,
        DigitalResponseRepository,
        DigitalSessionRepository,
    )
    assert callable(DigitalSessionRepository.create)
    assert callable(DigitalAttemptRepository.create)
    assert callable(DigitalResponseRepository.upsert)


def test_service_imports():
    from app.modules.m09_paper_admin.service import DigitalExamError, DigitalExamService
    assert callable(DigitalExamService.create_session)
    assert callable(DigitalExamService.submit_attempt)
    assert issubclass(DigitalExamError, Exception)
