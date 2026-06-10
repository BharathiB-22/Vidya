"""
M09.2 Moderation Workflow — unit tests (no DB).

Coverage:
  - Variance calculation correctness
  - Manual flag: success
  - Manual flag: wrong status rejected
  - Manual flag: duplicate flag rejected (409)
  - Submit moderation: wrong status rejected
  - Submit moderation: no review row rejected
  - Submit moderation: missing questions rejected
  - Submit moderation: success
  - Submit moderation: short notes rejected by schema
  - Board finalise from MODERATION_COMPLETE uses MODERATION round
  - Board finalise from MARKS_SUBMITTED uses PRIMARY round
  - Board finalise rejects MODERATION_PENDING
  - MODERATION is a separate evaluation round (immutability structural test)
  - Moderation history: returns all three rounds
  - Moderation queue: paginated response
  - Auto-flag paper: flags high-variance, skips low-variance
  - ScriptVarianceResponse schema correctness
  - PaperPipelineStats includes moderation counts
  - Model imports sanity check
  - ScriptStatus includes new moderation values
  - ModerationFlagRequest: short reason rejected
  - ModerationReviewResponse from model instance
  - ModerationRepository.get_threshold fallback
  - AuditEventType includes M09.2 event types
  - ScriptServiceError carries status_code
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m09_paper_admin.models import (
    EvaluationRound,
    ModerationStatus,
    ScannedScript,
    ScriptEvaluation,
    ScriptModerationReview,
    ScriptStatus,
)
from app.modules.m09_paper_admin.repository import (
    ModerationRepository,
    ScriptEvaluationRepository,
    ScriptRepository,
)
from app.modules.m09_paper_admin.schemas import (
    ModerationFlagRequest,
    ModerationMarkEntry,
    ModerationSubmitRequest,
)
from app.modules.m09_paper_admin.service import ModerationService, ScriptService, ScriptServiceError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _make_script(
    *,
    status: ScriptStatus = ScriptStatus.MARKS_SUBMITTED,
    double_eval: bool = True,
    exam_paper_id: uuid.UUID | None = None,
) -> ScannedScript:
    s = ScannedScript()
    s.id = uuid.uuid4()
    s.exam_paper_id = exam_paper_id or uuid.uuid4()
    s.masked_id = "STEST12345"
    s.status = status.value
    s.double_evaluation_enabled = double_eval
    s.evaluator_id = uuid.uuid4()
    s.second_evaluator_id = uuid.uuid4()
    s.student_user_id = uuid.uuid4()
    s.student_roll_ref = None
    return s


def _make_eval(
    *,
    script_id: uuid.UUID,
    question_id: uuid.UUID | None = None,
    evaluation_round: EvaluationRound = EvaluationRound.PRIMARY,
    evaluator_marks: float = 8.0,
    max_marks: float = 10.0,
) -> ScriptEvaluation:
    e = ScriptEvaluation()
    e.id = uuid.uuid4()
    e.script_id = script_id
    e.question_id = question_id or uuid.uuid4()
    e.question_type = "SHORT_ANSWER"
    e.max_marks = Decimal(str(max_marks))
    e.evaluation_round = evaluation_round.value
    e.evaluator_marks = Decimal(str(evaluator_marks))
    e.ai_suggested_marks = Decimal("7.0")
    e.ai_justification = None
    e.ai_model = "gemini"
    e.prompt_hash = "abc123"
    e.final_marks = None
    e.board_adjusted_marks = None
    e.board_adjustment_note = None
    e.evaluator_note = None
    e.keyword_hits = None
    e.rubric_mapping = None
    e.ai_confidence = None
    e.page_range = None
    e.created_at = _NOW
    e.updated_at = _NOW
    return e


def _make_review(
    *,
    script_id: uuid.UUID,
    exam_paper_id: uuid.UUID,
    status: ModerationStatus = ModerationStatus.PENDING,
    variance_pct: float = 25.0,
) -> ScriptModerationReview:
    r = ScriptModerationReview()
    r.id = uuid.uuid4()
    r.script_id = script_id
    r.exam_paper_id = exam_paper_id
    r.primary_total = Decimal("80.0")
    r.secondary_total = Decimal("55.0")
    r.variance_pct = Decimal(str(variance_pct))
    r.variance_threshold = Decimal("20.0")
    r.flag_reason = "AUTO_VARIANCE"
    r.flagged_by = None
    r.status = status.value
    r.moderator_id = None
    r.moderation_notes = None
    r.completed_at = None
    r.flagged_at = _NOW
    r.created_at = _NOW
    return r


# ---------------------------------------------------------------------------
# 1. Variance calculation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_variance_pct_calculation():
    """variance = abs(P - S) / max_marks * 100."""
    p, s, m = 80.0, 55.0, 100.0
    assert round(abs(p - s) / m * 100, 2) == 25.0


@pytest.mark.asyncio
async def test_variance_pct_zero_max_marks():
    """Zero max_marks → 0.0, no division by zero."""
    p, s, m = 10.0, 5.0, 0.0
    result = abs(p - s) / m * 100 if m > 0 else 0.0
    assert result == 0.0


# ---------------------------------------------------------------------------
# 2. Manual flag — success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manual_flag_marks_submitted_to_moderation_pending():
    """Manual flag of MARKS_SUBMITTED script → MODERATION_PENDING, review row created."""
    script = _make_script(status=ScriptStatus.MARKS_SUBMITTED)
    review = _make_review(script_id=script.id, exam_paper_id=script.exam_paper_id)
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_by_script",
              new=AsyncMock(return_value=None)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_evaluator_marks",
              new=AsyncMock(side_effect=[80.0, 55.0])),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_max_marks",
              new=AsyncMock(return_value=100.0)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_threshold",
              new=AsyncMock(return_value=20.0)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.create",
              new=AsyncMock(return_value=review)) as mock_create,
        patch("app.modules.m09_paper_admin.service.ScriptRepository.set_moderation_pending",
              new=AsyncMock()) as mock_pending,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await ModerationService.flag_for_moderation(
            script.id,
            reason="Suspected marking irregularity in question 3",
            flagged_by=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    assert result.status == ModerationStatus.PENDING.value
    mock_pending.assert_called_once()
    mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Manual flag — wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manual_flag_wrong_status_raises():
    """Cannot manually flag a script not in MARKS_SUBMITTED."""
    for bad_status in (ScriptStatus.SCORED, ScriptStatus.BOARD_FINALISED, ScriptStatus.MODERATION_PENDING):
        script = _make_script(status=bad_status)
        mock_db = AsyncMock()
        with patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
                   new=AsyncMock(return_value=script)):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ModerationService.flag_for_moderation(
                    script.id,
                    reason="test reason for flagging",
                    flagged_by=uuid.uuid4(),
                    tenant_id=uuid.uuid4(),
                    db=mock_db,
                )
            assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 4. Manual flag — duplicate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manual_flag_duplicate_raises_409():
    """Cannot flag a script that already has a PENDING moderation review."""
    script = _make_script(status=ScriptStatus.MARKS_SUBMITTED)
    existing = _make_review(script_id=script.id, exam_paper_id=script.exam_paper_id)
    mock_db = AsyncMock()
    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_by_script",
              new=AsyncMock(return_value=existing)),
    ):
        with pytest.raises(ScriptServiceError) as exc_info:
            await ModerationService.flag_for_moderation(
                script.id,
                reason="Another reason for flagging script",
                flagged_by=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# 5. Submit moderation — wrong status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_moderation_wrong_status_raises():
    """Cannot submit moderation for a script not in MODERATION_PENDING."""
    script = _make_script(status=ScriptStatus.MARKS_SUBMITTED)
    mock_db = AsyncMock()
    q_id = uuid.uuid4()
    payload = ModerationSubmitRequest(
        marks={str(q_id): ModerationMarkEntry(evaluator_marks=8.0)},
        moderation_notes="Reviewed both evaluations carefully and agree with primary.",
    )
    with patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
               new=AsyncMock(return_value=script)):
        with pytest.raises(ScriptServiceError) as exc_info:
            await ModerationService.submit_moderation(
                script.id, payload,
                moderator_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 6. Submit moderation — no review row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_moderation_no_review_raises():
    """Cannot submit moderation if no pending moderation review row exists."""
    script = _make_script(status=ScriptStatus.MODERATION_PENDING)
    mock_db = AsyncMock()
    q_id = uuid.uuid4()
    payload = ModerationSubmitRequest(
        marks={str(q_id): ModerationMarkEntry(evaluator_marks=8.0)},
        moderation_notes="Reviewed both evaluations carefully and agree with primary.",
    )
    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_by_script",
              new=AsyncMock(return_value=None)),
    ):
        with pytest.raises(ScriptServiceError) as exc_info:
            await ModerationService.submit_moderation(
                script.id, payload,
                moderator_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "NO_REVIEW"


# ---------------------------------------------------------------------------
# 7. Submit moderation — incomplete questions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_moderation_missing_questions_raises():
    """Moderation submit must cover all PRIMARY round questions."""
    script = _make_script(status=ScriptStatus.MODERATION_PENDING)
    review = _make_review(script_id=script.id, exam_paper_id=script.exam_paper_id)
    q1 = uuid.uuid4()
    q2 = uuid.uuid4()
    primary_evals = [
        _make_eval(script_id=script.id, question_id=q1),
        _make_eval(script_id=script.id, question_id=q2),
    ]
    # Only cover q1 in payload
    payload = ModerationSubmitRequest(
        marks={str(q1): ModerationMarkEntry(evaluator_marks=8.0)},
        moderation_notes="Reviewed both evaluations carefully and align with primary.",
    )
    mock_db = AsyncMock()
    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_by_script",
              new=AsyncMock(return_value=review)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
              new=AsyncMock(return_value=primary_evals)),
    ):
        with pytest.raises(ScriptServiceError) as exc_info:
            await ModerationService.submit_moderation(
                script.id, payload,
                moderator_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INCOMPLETE_MARKS"


# ---------------------------------------------------------------------------
# 8. Submit moderation — success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_moderation_success_creates_moderation_evals():
    """Submit moderation creates MODERATION evals, completes review, advances status."""
    script = _make_script(status=ScriptStatus.MODERATION_PENDING)
    review = _make_review(script_id=script.id, exam_paper_id=script.exam_paper_id)
    q_id = uuid.uuid4()
    primary_eval = _make_eval(script_id=script.id, question_id=q_id)
    mod_eval     = _make_eval(
        script_id=script.id, question_id=q_id,
        evaluation_round=EvaluationRound.MODERATION, evaluator_marks=9.0,
    )
    payload = ModerationSubmitRequest(
        marks={str(q_id): ModerationMarkEntry(evaluator_marks=9.0)},
        moderation_notes="Reviewed both evaluations. Primary was correct. Minor secondary discrepancy.",
    )
    mock_db = AsyncMock()

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_by_script",
              new=AsyncMock(return_value=review)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
              new=AsyncMock(return_value=[primary_eval])),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.bulk_create_moderation_evaluations",
              new=AsyncMock(return_value=[mod_eval])),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.complete",
              new=AsyncMock()) as mock_complete,
        patch("app.modules.m09_paper_admin.service.ScriptRepository.set_moderation_complete",
              new=AsyncMock()) as mock_set_complete,
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        ret_review, ret_evals = await ModerationService.submit_moderation(
            script.id, payload,
            moderator_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_set_complete.assert_called_once()
    mock_complete.assert_called_once()
    assert len(ret_evals) == 1


# ---------------------------------------------------------------------------
# 9. Submit moderation — short notes rejected by schema
# ---------------------------------------------------------------------------

def test_moderation_submit_request_short_notes_raises():
    """moderation_notes must be >= 20 characters."""
    with pytest.raises(Exception):
        ModerationSubmitRequest(
            marks={"some-uuid": ModerationMarkEntry(evaluator_marks=8.0)},
            moderation_notes="Too short",
        )


# ---------------------------------------------------------------------------
# 10. Board finalise uses MODERATION round when present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_board_finalise_uses_moderation_round_when_present():
    """board_finalise picks MODERATION round for final_marks when MODERATION evals exist."""
    script = _make_script(status=ScriptStatus.MODERATION_COMPLETE, double_eval=True)
    q_id = uuid.uuid4()
    mod_eval = _make_eval(
        script_id=script.id, question_id=q_id,
        evaluation_round=EvaluationRound.MODERATION, evaluator_marks=9.0,
    )
    mock_db = AsyncMock()
    ledger_mock = MagicMock()
    ledger_mock.id = uuid.uuid4()

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
              new=AsyncMock(return_value=[mod_eval])),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.set_final_marks",
              new=AsyncMock()) as mock_set_final,
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_final_marks",
              new=AsyncMock(return_value=9.0)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_max_marks",
              new=AsyncMock(return_value=10.0)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_evaluator_marks",
              new=AsyncMock(return_value=9.0)),
        patch("app.modules.m09_paper_admin.service.ExamScoreLedgerRepository.create",
              new=AsyncMock(return_value=ledger_mock)),
        patch("app.modules.m09_paper_admin.service.ScriptRepository.set_finalised",
              new=AsyncMock()),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.modules.m09_paper_admin.schemas import ScriptFinaliseRequest
        await ScriptService.board_finalise(
            script.id, ScriptFinaliseRequest(),
            board_user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_set_final.assert_called_once_with(
        script.id,
        evaluation_round=EvaluationRound.MODERATION.value,
        db=mock_db,
    )


# ---------------------------------------------------------------------------
# 11. Board finalise from MARKS_SUBMITTED uses PRIMARY (unchanged path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_board_finalise_uses_primary_when_no_moderation():
    """board_finalise picks PRIMARY round when no MODERATION evals exist."""
    script = _make_script(status=ScriptStatus.MARKS_SUBMITTED, double_eval=False)
    mock_db = AsyncMock()
    ledger_mock = MagicMock()
    ledger_mock.id = uuid.uuid4()

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
              new=AsyncMock(return_value=[])),   # no MODERATION rows
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.set_final_marks",
              new=AsyncMock()) as mock_set_final,
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_final_marks",
              new=AsyncMock(return_value=8.0)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_max_marks",
              new=AsyncMock(return_value=10.0)),
        patch("app.modules.m09_paper_admin.service.ExamScoreLedgerRepository.create",
              new=AsyncMock(return_value=ledger_mock)),
        patch("app.modules.m09_paper_admin.service.ScriptRepository.set_finalised",
              new=AsyncMock()),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.modules.m09_paper_admin.schemas import ScriptFinaliseRequest
        await ScriptService.board_finalise(
            script.id, ScriptFinaliseRequest(),
            board_user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    mock_set_final.assert_called_once_with(
        script.id,
        evaluation_round=EvaluationRound.PRIMARY.value,
        db=mock_db,
    )


# ---------------------------------------------------------------------------
# 12. Board finalise rejects MODERATION_PENDING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_board_finalise_rejects_moderation_pending():
    """board_finalise must not accept MODERATION_PENDING scripts."""
    script = _make_script(status=ScriptStatus.MODERATION_PENDING)
    mock_db = AsyncMock()
    with patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
               new=AsyncMock(return_value=script)):
        with pytest.raises(ScriptServiceError) as exc_info:
            from app.modules.m09_paper_admin.schemas import ScriptFinaliseRequest
            await ScriptService.board_finalise(
                script.id, ScriptFinaliseRequest(),
                board_user_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# 13. MODERATION is a separate evaluation round (immutability structural)
# ---------------------------------------------------------------------------

def test_moderation_is_separate_evaluation_round():
    """MODERATION round has its own enum value — all three rounds are distinct."""
    vals = {
        EvaluationRound.PRIMARY.value,
        EvaluationRound.SECONDARY.value,
        EvaluationRound.MODERATION.value,
    }
    assert len(vals) == 3
    assert EvaluationRound.MODERATION.value == "MODERATION"


# ---------------------------------------------------------------------------
# 14. Moderation history returns all three rounds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_moderation_history_returns_all_rounds():
    """get_moderation_history returns review + all three eval rounds."""
    script = _make_script(status=ScriptStatus.MODERATION_COMPLETE)
    review = _make_review(script_id=script.id, exam_paper_id=script.exam_paper_id,
                          status=ModerationStatus.COMPLETE)
    q_id = uuid.uuid4()
    p_eval = _make_eval(script_id=script.id, question_id=q_id)
    s_eval = _make_eval(script_id=script.id, question_id=q_id,
                        evaluation_round=EvaluationRound.SECONDARY, evaluator_marks=7.0)
    m_eval = _make_eval(script_id=script.id, question_id=q_id,
                        evaluation_round=EvaluationRound.MODERATION, evaluator_marks=8.0)

    mock_db = AsyncMock()
    round_map = {
        EvaluationRound.PRIMARY.value:    [p_eval],
        EvaluationRound.SECONDARY.value:  [s_eval],
        EvaluationRound.MODERATION.value: [m_eval],
    }

    async def _list_by_script(sid, *, evaluation_round, db):
        return round_map.get(evaluation_round, [])

    with (
        patch("app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
              new=AsyncMock(return_value=script)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_by_script",
              new=AsyncMock(return_value=review)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
              new=AsyncMock(side_effect=_list_by_script)),
    ):
        result = await ModerationService.get_moderation_history(script.id, db=mock_db)

    assert result.review is not None
    assert result.review.status == ModerationStatus.COMPLETE.value
    assert len(result.primary_evals) == 1
    assert len(result.secondary_evals) == 1
    assert len(result.moderation_evals) == 1


# ---------------------------------------------------------------------------
# 15. Moderation queue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_moderation_queue_returns_pending_reviews():
    """list_moderation_queue returns PENDING reviews for a paper."""
    paper_id = uuid.uuid4()
    script1 = _make_script()
    script2 = _make_script()
    reviews = [
        _make_review(script_id=script1.id, exam_paper_id=paper_id, variance_pct=30.0),
        _make_review(script_id=script2.id, exam_paper_id=paper_id, variance_pct=22.0),
    ]
    mock_db = AsyncMock()
    with (
        patch("app.modules.m09_paper_admin.service.ModerationRepository.list_pending_for_paper",
              new=AsyncMock(return_value=reviews)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.count_pending_for_paper",
              new=AsyncMock(return_value=2)),
    ):
        items, total = await ModerationService.list_moderation_queue(
            paper_id, db=mock_db
        )

    assert total == 2
    assert len(items) == 2


# ---------------------------------------------------------------------------
# 16. Auto-flag paper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_flag_paper_flags_high_variance_only():
    """auto_flag_paper flags high-variance scripts; skips low-variance ones."""
    paper_id = uuid.uuid4()
    script_hi = _make_script(exam_paper_id=paper_id)
    script_lo = _make_script(exam_paper_id=paper_id)

    mock_db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [script_hi, script_lo]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_db.execute = AsyncMock(return_value=result_mock)

    # script_hi: primary=85, secondary=50 → variance=35% > 20% → flagged
    # script_lo: primary=80, secondary=79 → variance=1%  < 20% → skipped
    sum_evaluator_calls = iter([85.0, 50.0, 80.0, 79.0])

    async def _sum_evaluator(sid, *, evaluation_round, db):
        return next(sum_evaluator_calls)

    with (
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_threshold",
              new=AsyncMock(return_value=20.0)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.get_by_script",
              new=AsyncMock(return_value=None)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_evaluator_marks",
              new=AsyncMock(side_effect=_sum_evaluator)),
        patch("app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_max_marks",
              new=AsyncMock(return_value=100.0)),
        patch("app.modules.m09_paper_admin.service.ModerationRepository.create",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.modules.m09_paper_admin.service.ScriptRepository.set_moderation_pending",
              new=AsyncMock()),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        result = await ModerationService.auto_flag_paper(
            paper_id,
            flagged_by=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            db=mock_db,
        )

    assert result["checked"] == 2
    assert result["flagged"] == 1
    assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# 17. ScriptVarianceResponse schema
# ---------------------------------------------------------------------------

def test_script_variance_response_schema():
    """ScriptVarianceResponse reflects exceeds_threshold correctly."""
    from app.modules.m09_paper_admin.schemas import ScriptVarianceResponse
    resp = ScriptVarianceResponse(
        script_id=uuid.uuid4(),
        masked_id="STEST12345",
        exam_paper_id=uuid.uuid4(),
        status="MARKS_SUBMITTED",
        double_evaluation_enabled=True,
        primary_total=80.0,
        secondary_total=55.0,
        max_marks_total=100.0,
        variance_pct=25.0,
        threshold_pct=20.0,
        exceeds_threshold=True,
    )
    assert resp.exceeds_threshold is True
    assert resp.variance_pct == 25.0
    assert resp.threshold_pct == 20.0


# ---------------------------------------------------------------------------
# 18. PaperPipelineStats includes moderation counts
# ---------------------------------------------------------------------------

def test_pipeline_stats_includes_moderation_fields():
    """PaperPipelineStats has moderation_pending + moderation_complete."""
    from app.modules.m09_paper_admin.schemas import PaperPipelineStats
    stats = PaperPipelineStats(
        paper_id=uuid.uuid4(),
        total=10,
        pending=0,
        quality_checking=0,
        quality_failed=0,
        ocr_processing=0,
        processing=0,
        scored=0,
        failed=0,
        review_required=0,
        marks_submitted=5,
        moderation_pending=3,
        moderation_complete=2,
        board_finalised=0,
        completion_pct=0.0,
    )
    assert stats.moderation_pending == 3
    assert stats.moderation_complete == 2


# ---------------------------------------------------------------------------
# 19. Model imports sanity check
# ---------------------------------------------------------------------------

def test_model_imports():
    """New M09.2 model classes are importable with expected attributes."""
    assert hasattr(ScriptModerationReview, "__tablename__")
    assert ScriptModerationReview.__tablename__ == "script_moderation_reviews"
    assert ModerationStatus.PENDING.value == "PENDING"
    assert ModerationStatus.COMPLETE.value == "COMPLETE"
    assert ModerationStatus.SKIPPED.value == "SKIPPED"


# ---------------------------------------------------------------------------
# 20. ScriptStatus includes new moderation values
# ---------------------------------------------------------------------------

def test_script_status_has_moderation_values():
    """ScriptStatus includes MODERATION_PENDING and MODERATION_COMPLETE."""
    assert ScriptStatus.MODERATION_PENDING.value  == "MODERATION_PENDING"
    assert ScriptStatus.MODERATION_COMPLETE.value == "MODERATION_COMPLETE"


# ---------------------------------------------------------------------------
# 21. ModerationFlagRequest — short reason rejected
# ---------------------------------------------------------------------------

def test_moderation_flag_request_short_reason_raises():
    """ModerationFlagRequest requires reason >= 10 characters."""
    with pytest.raises(Exception):
        ModerationFlagRequest(reason="Short")


# ---------------------------------------------------------------------------
# 22. ModerationReviewResponse from model instance
# ---------------------------------------------------------------------------

def test_moderation_review_response_schema():
    """ModerationReviewResponse can be built from a model instance."""
    from app.modules.m09_paper_admin.schemas import ModerationReviewResponse
    r = _make_review(script_id=uuid.uuid4(), exam_paper_id=uuid.uuid4())
    out = ModerationReviewResponse.model_validate(r)
    assert out.status == "PENDING"
    assert float(out.variance_pct) == 25.0
    assert float(out.variance_threshold) == 20.0


# ---------------------------------------------------------------------------
# 23. ModerationRepository.get_threshold fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_moderation_repository_get_threshold_fallback():
    """get_threshold returns default_threshold when paper row not found."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    threshold = await ModerationRepository.get_threshold(
        uuid.uuid4(), db=mock_db, default_threshold=15.0
    )
    assert threshold == 15.0


# ---------------------------------------------------------------------------
# 24. AuditEventType includes M09.2 event types
# ---------------------------------------------------------------------------

def test_audit_event_type_includes_moderation_events():
    """M09.2 audit event types are present in AuditEventType enum."""
    from app.core.audit_log.models import AuditEventType
    assert AuditEventType.SCRIPT_MODERATION_FLAGGED.value   == "SCRIPT_MODERATION_FLAGGED"
    assert AuditEventType.SCRIPT_MODERATION_SUBMITTED.value == "SCRIPT_MODERATION_SUBMITTED"


# ---------------------------------------------------------------------------
# 25. ScriptServiceError carries status_code
# ---------------------------------------------------------------------------

def test_script_service_error_carries_status_code():
    """ScriptServiceError with status_code=409 is accessible on the exception."""
    err = ScriptServiceError("ALREADY_FLAGGED", "duplicate flag", 409)
    assert err.code == "ALREADY_FLAGGED"
    assert err.status_code == 409
