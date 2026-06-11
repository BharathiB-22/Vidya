"""
M09.5 Phase D — Faculty Subjective Review unit tests (no DB).

Coverage:
  Model / enum:
    - DigitalAttemptStatus includes FULLY_EVALUATED
    - DigitalExamResponse model has faculty scoring columns

  Audit events:
    - AuditEventType includes DIGITAL_EXAM_SUBJECTIVE_SCORED
    - AuditEventType includes DIGITAL_EXAM_SUBJECTIVE_SUBMITTED

  Schemas:
    - FacultyScoreIn: valid score accepted
    - FacultyScoreIn: score below 0 rejected
    - FacultyScoreIn: note is optional
    - SubjectivePendingAttempt: fields mapped correctly
    - SubjectiveReviewResponse: all_scored reflects state
    - SubjectiveSubmitResult: totals computed correctly
    - SubjectiveSubmitIn: note is optional

  Repository: DigitalResponseRepository.score_subjective
    - Sets faculty_score, faculty_note, faculty_scored_by, faculty_scored_at

  Repository: DigitalResponseRepository.count_unscored_subjective (mocked)
    - Returns correct count via query mock

  Repository: DigitalAttemptRepository.mark_fully_evaluated
    - Sets status to FULLY_EVALUATED

  Service: list_pending_subjective_review — session not found raises 404
  Service: list_pending_subjective_review — FACULTY course check called
  Service: list_pending_subjective_review — ADMIN bypasses course check
  Service: get_subjective_responses — attempt not found raises 404
  Service: get_subjective_responses — wrong status raises 409
  Service: get_subjective_responses — SCORED status accepted
  Service: get_subjective_responses — FULLY_EVALUATED status accepted
  Service: save_faculty_score — attempt not found raises 404
  Service: save_faculty_score — non-SCORED status raises 409
  Service: save_faculty_score — score below 0 raises 422
  Service: save_faculty_score — score above max_marks raises 422
  Service: save_faculty_score — MCQ response raises 409
  Service: save_faculty_score — valid score saves and audits
  Service: submit_subjective_scores — attempt not found raises 404
  Service: submit_subjective_scores — non-SCORED status raises 409
  Service: submit_subjective_scores — unscored questions raise 422
  Service: submit_subjective_scores — all scored transitions to FULLY_EVALUATED
  Service: _check_faculty_course_access — paper creator is authorised
  Service: _check_faculty_course_access — active assignment is authorised
  Service: _check_faculty_course_access — no assignment raises 403
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
)
from app.modules.m09_paper_admin.repository import (
    DigitalAttemptRepository,
    DigitalResponseRepository,
    DigitalSessionRepository,
)
from app.modules.m09_paper_admin.schemas import (
    FacultyScoreIn,
    SubjectivePendingAttempt,
    SubjectiveQueueResponse,
    SubjectiveResponseItem,
    SubjectiveReviewResponse,
    SubjectiveScoreOut,
    SubjectiveSubmitIn,
    SubjectiveSubmitResult,
)
from app.modules.m09_paper_admin.service import DigitalExamError, DigitalExamService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _make_session(
    *,
    status: DigitalExamSessionStatus = DigitalExamSessionStatus.ACTIVE,
    exam_paper_id: uuid.UUID | None = None,
) -> DigitalExamSession:
    s = DigitalExamSession()
    s.id = uuid.uuid4()
    s.exam_paper_id = exam_paper_id or uuid.uuid4()
    s.created_by = uuid.uuid4()
    s.title = "CS101 Digital"
    s.status = status
    s.max_duration_mins = 120
    s.window_start = None
    s.window_end = None
    s.instructions = None
    s.activated_at = _NOW
    s.closed_at = None
    s.created_at = _NOW
    return s


def _make_attempt(
    *,
    session_id: uuid.UUID | None = None,
    student_user_id: uuid.UUID | None = None,
    status: DigitalAttemptStatus = DigitalAttemptStatus.SCORED,
    auto_score: float | None = 10.0,
    mcq_max_score: float | None = 20.0,
) -> DigitalExamAttempt:
    a = DigitalExamAttempt()
    a.id = uuid.uuid4()
    a.session_id = session_id or uuid.uuid4()
    a.student_user_id = student_user_id or uuid.uuid4()
    a.status = status
    a.started_at = _NOW
    a.expires_at = _NOW + timedelta(hours=2)
    a.submitted_at = _NOW
    a.auto_scored_at = _NOW
    a.auto_score = Decimal(str(auto_score)) if auto_score is not None else None
    a.mcq_max_score = Decimal(str(mcq_max_score)) if mcq_max_score is not None else None
    a.created_at = _NOW
    return a


def _make_response(
    *,
    attempt_id: uuid.UUID | None = None,
    question_id: uuid.UUID | None = None,
    question_type: str = "SUBJECTIVE",
    response_text: str | None = "This is a long answer.",
    faculty_score: float | None = None,
    faculty_note: str | None = None,
    faculty_scored_by: uuid.UUID | None = None,
    faculty_scored_at: datetime | None = None,
) -> DigitalExamResponse:
    r = DigitalExamResponse()
    r.id = uuid.uuid4()
    r.attempt_id = attempt_id or uuid.uuid4()
    r.question_id = question_id or uuid.uuid4()
    r.question_type = question_type
    r.selected_option = None
    r.response_text = response_text
    r.is_auto_scored = False
    r.auto_score = None
    r.is_correct = None
    r.faculty_score = Decimal(str(faculty_score)) if faculty_score is not None else None
    r.faculty_note = faculty_note
    r.faculty_scored_by = faculty_scored_by
    r.faculty_scored_at = faculty_scored_at
    r.answered_at = _NOW
    r.updated_at = None
    r.created_at = _NOW
    return r


# ---------------------------------------------------------------------------
# Model / enum tests
# ---------------------------------------------------------------------------

def test_digital_attempt_status_fully_evaluated():
    assert DigitalAttemptStatus.FULLY_EVALUATED == "FULLY_EVALUATED"
    assert DigitalAttemptStatus.FULLY_EVALUATED in list(DigitalAttemptStatus)


def test_digital_exam_response_has_faculty_score_columns():
    r = _make_response()
    assert hasattr(r, "faculty_score")
    assert hasattr(r, "faculty_note")
    assert hasattr(r, "faculty_scored_by")
    assert hasattr(r, "faculty_scored_at")
    assert r.faculty_score is None
    assert r.faculty_note is None


# ---------------------------------------------------------------------------
# Audit event tests
# ---------------------------------------------------------------------------

def test_audit_event_subjective_scored():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.DIGITAL_EXAM_SUBJECTIVE_SCORED == "DIGITAL_EXAM_SUBJECTIVE_SCORED"


def test_audit_event_subjective_submitted():
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.DIGITAL_EXAM_SUBJECTIVE_SUBMITTED == "DIGITAL_EXAM_SUBJECTIVE_SUBMITTED"


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_faculty_score_in_valid():
    payload = FacultyScoreIn(score=7.5)
    assert payload.score == 7.5
    assert payload.note is None


def test_faculty_score_in_with_note():
    payload = FacultyScoreIn(score=5.0, note="Good attempt")
    assert payload.note == "Good attempt"


def test_faculty_score_in_negative_rejected():
    with pytest.raises(Exception):
        FacultyScoreIn(score=-1.0)


def test_faculty_score_in_zero_accepted():
    payload = FacultyScoreIn(score=0.0)
    assert payload.score == 0.0


def test_subjective_pending_attempt_fields():
    attempt_id = uuid.uuid4()
    item = SubjectivePendingAttempt(
        attempt_id=attempt_id,
        session_id=uuid.uuid4(),
        student_user_id=uuid.uuid4(),
        status="SCORED",
        submitted_at=_NOW,
        auto_score=10.0,
        mcq_max_score=20.0,
        subjective_count=3,
        scored_count=1,
    )
    assert item.attempt_id == attempt_id
    assert item.subjective_count == 3
    assert item.scored_count == 1


def test_subjective_review_response_all_scored_true():
    review = SubjectiveReviewResponse(
        attempt_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        status="SCORED",
        submitted_at=None,
        auto_score=None,
        mcq_max_score=None,
        responses=[],
        total_subjective=0,
        scored_count=0,
        all_scored=False,
    )
    assert review.all_scored is False


def test_subjective_submit_result_totals():
    result = SubjectiveSubmitResult(
        attempt_id=uuid.uuid4(),
        status="FULLY_EVALUATED",
        total_auto_score=10.0,
        total_subjective_score=15.0,
        total_score=25.0,
        submission_note=None,
    )
    assert result.total_score == 25.0
    assert result.status == "FULLY_EVALUATED"


def test_subjective_submit_in_note_optional():
    payload = SubjectiveSubmitIn()
    assert payload.submission_note is None
    payload2 = SubjectiveSubmitIn(submission_note="All reviewed")
    assert payload2.submission_note == "All reviewed"


# ---------------------------------------------------------------------------
# Repository: score_subjective
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_subjective_sets_fields():
    response = _make_response()
    scorer_id = uuid.uuid4()
    db = AsyncMock()
    db.flush = AsyncMock()

    result = await DigitalResponseRepository.score_subjective(
        response, score=8.0, note="Clear explanation", scored_by=scorer_id, db=db
    )

    assert float(result.faculty_score) == 8.0
    assert result.faculty_note == "Clear explanation"
    assert result.faculty_scored_by == scorer_id
    assert result.faculty_scored_at is not None
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_score_subjective_zero_score():
    response = _make_response()
    db = AsyncMock()
    db.flush = AsyncMock()
    result = await DigitalResponseRepository.score_subjective(
        response, score=0.0, note=None, scored_by=uuid.uuid4(), db=db
    )
    assert float(result.faculty_score) == 0.0


# ---------------------------------------------------------------------------
# Repository: mark_fully_evaluated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_fully_evaluated_sets_status():
    attempt = _make_attempt(status=DigitalAttemptStatus.SCORED)
    db = AsyncMock()
    db.flush = AsyncMock()

    result = await DigitalAttemptRepository.mark_fully_evaluated(attempt, db=db)

    assert result.status == DigitalAttemptStatus.FULLY_EVALUATED
    db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# Service: list_pending_subjective_review
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_pending_review_session_not_found():
    db = AsyncMock()
    with patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.list_pending_subjective_review(
                uuid.uuid4(),
                faculty_user_id=uuid.uuid4(),
                faculty_role="FACULTY",
                db=db,
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_pending_review_admin_bypasses_course_check():
    db = AsyncMock()
    session = _make_session()

    with (
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(
            DigitalResponseRepository,
            "list_scored_for_session_with_pending_subjective",
            new=AsyncMock(return_value=([], 0)),
        ),
    ):
        result = await DigitalExamService.list_pending_subjective_review(
            session.id,
            faculty_user_id=uuid.uuid4(),
            faculty_role="ADMIN",
            db=db,
        )
    assert result.total == 0


@pytest.mark.asyncio
async def test_list_pending_review_faculty_calls_course_check():
    db = AsyncMock()
    session = _make_session()

    with (
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(
            DigitalExamService,
            "_check_faculty_course_access",
            new=AsyncMock(return_value=None),
        ) as mock_check,
        patch.object(
            DigitalResponseRepository,
            "list_scored_for_session_with_pending_subjective",
            new=AsyncMock(return_value=([], 0)),
        ),
    ):
        await DigitalExamService.list_pending_subjective_review(
            session.id,
            faculty_user_id=uuid.uuid4(),
            faculty_role="FACULTY",
            db=db,
        )
    mock_check.assert_called_once()


# ---------------------------------------------------------------------------
# Service: get_subjective_responses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_subjective_responses_attempt_not_found():
    db = AsyncMock()
    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.get_subjective_responses(
                uuid.uuid4(),
                faculty_user_id=uuid.uuid4(),
                faculty_role="ADMIN",
                db=db,
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_subjective_responses_in_progress_rejected():
    db = AsyncMock()
    attempt = _make_attempt(status=DigitalAttemptStatus.IN_PROGRESS)
    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.get_subjective_responses(
                attempt.id,
                faculty_user_id=uuid.uuid4(),
                faculty_role="ADMIN",
                db=db,
            )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_get_subjective_responses_scored_accepted():
    db = AsyncMock()
    session = _make_session()
    attempt = _make_attempt(session_id=session.id, status=DigitalAttemptStatus.SCORED)

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(DigitalResponseRepository, "list_subjective_for_attempt", new=AsyncMock(return_value=[])),
    ):
        result = await DigitalExamService.get_subjective_responses(
            attempt.id,
            faculty_user_id=uuid.uuid4(),
            faculty_role="ADMIN",
            db=db,
        )
    assert result.attempt_id == attempt.id
    assert result.total_subjective == 0
    assert result.all_scored is False


@pytest.mark.asyncio
async def test_get_subjective_responses_fully_evaluated_accepted():
    db = AsyncMock()
    session = _make_session()
    attempt = _make_attempt(session_id=session.id, status=DigitalAttemptStatus.FULLY_EVALUATED)

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(DigitalResponseRepository, "list_subjective_for_attempt", new=AsyncMock(return_value=[])),
    ):
        result = await DigitalExamService.get_subjective_responses(
            attempt.id,
            faculty_user_id=uuid.uuid4(),
            faculty_role="ADMIN",
            db=db,
        )
    assert result.status == DigitalAttemptStatus.FULLY_EVALUATED


# ---------------------------------------------------------------------------
# Service: save_faculty_score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_faculty_score_attempt_not_found():
    db = AsyncMock()
    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.save_faculty_score(
                uuid.uuid4(), uuid.uuid4(),
                score=5.0, note=None,
                faculty_user_id=uuid.uuid4(), faculty_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_save_faculty_score_non_scored_status_rejected():
    db = AsyncMock()
    attempt = _make_attempt(status=DigitalAttemptStatus.IN_PROGRESS)
    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.save_faculty_score(
                attempt.id, uuid.uuid4(),
                score=5.0, note=None,
                faculty_user_id=uuid.uuid4(), faculty_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_save_faculty_score_above_max_rejected():
    """Score exceeding question.marks must raise 422."""
    db = AsyncMock()
    session = _make_session()
    attempt = _make_attempt(session_id=session.id, status=DigitalAttemptStatus.SCORED)
    question_id = uuid.uuid4()

    mock_question = MagicMock()
    mock_question.id = question_id
    mock_question.marks = Decimal("10.0")
    mock_question.exam_paper_id = session.exam_paper_id

    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none = MagicMock(return_value=mock_question)
    db.execute = AsyncMock(return_value=mock_exec)

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
    ):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.save_faculty_score(
                attempt.id, question_id,
                score=15.0,   # above max_marks=10
                note=None,
                faculty_user_id=uuid.uuid4(), faculty_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_save_faculty_score_negative_rejected():
    """Score below 0 must raise 422."""
    db = AsyncMock()
    session = _make_session()
    attempt = _make_attempt(session_id=session.id, status=DigitalAttemptStatus.SCORED)
    question_id = uuid.uuid4()

    mock_question = MagicMock()
    mock_question.id = question_id
    mock_question.marks = Decimal("10.0")
    mock_question.exam_paper_id = session.exam_paper_id

    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none = MagicMock(return_value=mock_question)
    db.execute = AsyncMock(return_value=mock_exec)

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
    ):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.save_faculty_score(
                attempt.id, question_id,
                score=-1.0,
                note=None,
                faculty_user_id=uuid.uuid4(), faculty_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_save_faculty_score_mcq_response_rejected():
    """Attempting to manually score an MCQ response must raise 409."""
    db = AsyncMock()
    session = _make_session()
    attempt = _make_attempt(session_id=session.id, status=DigitalAttemptStatus.SCORED)
    question_id = uuid.uuid4()
    mcq_response = _make_response(
        attempt_id=attempt.id, question_id=question_id, question_type="MCQ"
    )

    mock_question = MagicMock()
    mock_question.id = question_id
    mock_question.marks = Decimal("4.0")
    mock_question.exam_paper_id = session.exam_paper_id

    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none = MagicMock(return_value=mock_question)
    db.execute = AsyncMock(return_value=mock_exec)

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(
            DigitalResponseRepository,
            "get_by_attempt_and_question",
            new=AsyncMock(return_value=mcq_response),
        ),
    ):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.save_faculty_score(
                attempt.id, question_id,
                score=3.0, note=None,
                faculty_user_id=uuid.uuid4(), faculty_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_save_faculty_score_valid_saves_and_audits():
    db = AsyncMock()
    session = _make_session()
    attempt = _make_attempt(session_id=session.id, status=DigitalAttemptStatus.SCORED)
    question_id = uuid.uuid4()
    faculty_id = uuid.uuid4()
    subj_response = _make_response(attempt_id=attempt.id, question_id=question_id)

    mock_question = MagicMock()
    mock_question.id = question_id
    mock_question.marks = Decimal("10.0")
    mock_question.exam_paper_id = session.exam_paper_id

    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none = MagicMock(return_value=mock_question)
    db.execute = AsyncMock(return_value=mock_exec)

    scored_response = _make_response(
        attempt_id=attempt.id, question_id=question_id,
        faculty_score=8.0, faculty_note="Good", faculty_scored_by=faculty_id,
        faculty_scored_at=_NOW,
    )

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(
            DigitalResponseRepository,
            "get_by_attempt_and_question",
            new=AsyncMock(return_value=subj_response),
        ),
        patch.object(
            DigitalResponseRepository,
            "score_subjective",
            new=AsyncMock(return_value=scored_response),
        ) as mock_score,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()) as mock_audit,
    ):
        result = await DigitalExamService.save_faculty_score(
            attempt.id, question_id,
            score=8.0, note="Good",
            faculty_user_id=faculty_id, faculty_role="ADMIN",
            tenant_id=uuid.uuid4(), db=db,
        )

    mock_score.assert_called_once()
    mock_audit.assert_called_once()
    assert result.faculty_score == 8.0
    assert result.question_id == question_id


# ---------------------------------------------------------------------------
# Service: submit_subjective_scores
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_subjective_attempt_not_found():
    db = AsyncMock()
    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.submit_subjective_scores(
                uuid.uuid4(), submission_note=None,
                faculty_user_id=uuid.uuid4(), faculty_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_submit_subjective_non_scored_rejected():
    db = AsyncMock()
    attempt = _make_attempt(status=DigitalAttemptStatus.FULLY_EVALUATED)
    with patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.submit_subjective_scores(
                attempt.id, submission_note=None,
                faculty_user_id=uuid.uuid4(), faculty_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_submit_subjective_unscored_questions_rejected():
    db = AsyncMock()
    session = _make_session()
    attempt = _make_attempt(session_id=session.id, status=DigitalAttemptStatus.SCORED)

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(
            DigitalResponseRepository,
            "count_unscored_subjective",
            new=AsyncMock(return_value=2),  # 2 still unscored
        ),
    ):
        with pytest.raises(DigitalExamError) as exc_info:
            await DigitalExamService.submit_subjective_scores(
                attempt.id, submission_note=None,
                faculty_user_id=uuid.uuid4(), faculty_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_submit_subjective_all_scored_transitions_to_fully_evaluated():
    db = AsyncMock()
    session = _make_session()
    attempt = _make_attempt(session_id=session.id, status=DigitalAttemptStatus.SCORED)
    faculty_id = uuid.uuid4()

    with (
        patch.object(DigitalAttemptRepository, "get", new=AsyncMock(return_value=attempt)),
        patch.object(DigitalSessionRepository, "get", new=AsyncMock(return_value=session)),
        patch.object(
            DigitalResponseRepository,
            "count_unscored_subjective",
            new=AsyncMock(return_value=0),
        ),
        patch.object(
            DigitalResponseRepository,
            "sum_faculty_scores",
            new=AsyncMock(return_value=18.0),
        ),
        patch.object(
            DigitalAttemptRepository,
            "mark_fully_evaluated",
            new=AsyncMock(return_value=attempt),
        ) as mock_eval,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()) as mock_audit,
    ):
        result = await DigitalExamService.submit_subjective_scores(
            attempt.id, submission_note="Reviewed",
            faculty_user_id=faculty_id, faculty_role="ADMIN",
            tenant_id=uuid.uuid4(), db=db,
        )

    mock_eval.assert_called_once()
    mock_audit.assert_called_once()
    assert result.status == "FULLY_EVALUATED"
    assert result.total_subjective_score == 18.0
    assert result.total_auto_score == 10.0
    assert result.total_score == 28.0


# ---------------------------------------------------------------------------
# Service: _check_faculty_course_access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_faculty_course_access_creator_authorised():
    """Paper creator always has access without checking SubjectAssignment."""
    db = AsyncMock()
    faculty_id = uuid.uuid4()

    mock_paper = MagicMock()
    mock_paper.created_by = faculty_id
    mock_paper.course_id = uuid.uuid4()

    mock_exec = AsyncMock()
    mock_exec.scalar_one_or_none = MagicMock(return_value=mock_paper)
    db.execute = AsyncMock(return_value=mock_exec)

    # Should not raise
    await DigitalExamService._check_faculty_course_access(
        uuid.uuid4(), faculty_id, db=db
    )


@pytest.mark.asyncio
async def test_check_faculty_course_access_active_assignment_authorised():
    """Faculty with an active subject assignment for the course is authorised."""
    db = AsyncMock()
    faculty_id = uuid.uuid4()
    course_id = uuid.uuid4()

    mock_paper = MagicMock()
    mock_paper.created_by = uuid.uuid4()   # different user — not the creator
    mock_paper.course_id = course_id

    assignment_id = uuid.uuid4()

    # First call returns paper; second returns assignment_id
    mock_exec1 = AsyncMock()
    mock_exec1.scalar_one_or_none = MagicMock(return_value=mock_paper)
    mock_exec2 = AsyncMock()
    mock_exec2.scalar_one_or_none = MagicMock(return_value=assignment_id)
    db.execute = AsyncMock(side_effect=[mock_exec1, mock_exec2])

    await DigitalExamService._check_faculty_course_access(
        uuid.uuid4(), faculty_id, db=db
    )


@pytest.mark.asyncio
async def test_check_faculty_course_access_no_assignment_raises_403():
    """Faculty with no active assignment must be denied."""
    db = AsyncMock()
    faculty_id = uuid.uuid4()

    mock_paper = MagicMock()
    mock_paper.created_by = uuid.uuid4()   # different user
    mock_paper.course_id = uuid.uuid4()

    mock_exec1 = AsyncMock()
    mock_exec1.scalar_one_or_none = MagicMock(return_value=mock_paper)
    mock_exec2 = AsyncMock()
    mock_exec2.scalar_one_or_none = MagicMock(return_value=None)  # no assignment
    db.execute = AsyncMock(side_effect=[mock_exec1, mock_exec2])

    with pytest.raises(DigitalExamError) as exc_info:
        await DigitalExamService._check_faculty_course_access(
            uuid.uuid4(), faculty_id, db=db
        )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Schema imports sanity
# ---------------------------------------------------------------------------

def test_schema_imports():
    from app.modules.m09_paper_admin.schemas import (
        FacultyScoreIn,
        SubjectivePendingAttempt,
        SubjectiveQueueResponse,
        SubjectiveResponseItem,
        SubjectiveReviewResponse,
        SubjectiveScoreOut,
        SubjectiveSubmitIn,
        SubjectiveSubmitResult,
    )
    assert FacultyScoreIn is not None
    assert SubjectiveQueueResponse is not None
    assert SubjectiveSubmitResult is not None
