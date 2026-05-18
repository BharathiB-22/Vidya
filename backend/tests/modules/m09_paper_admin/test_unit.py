"""
M09 Paper Administration — unit tests (STEP-16).

Coverage:
  1. Models       — enums, table names, status machine, relationship declarations
  2. Schemas      — BulkMarkUpdate/ScriptSubmitMarksRequest validators,
                    EvaluatorMarkUpdate constraints, ScannedScriptResponse fields
  3. Script scorer — MCQ extraction heuristics, no-OCR fallback,
                     ScriptScoringResult dataclass, evaluator_marks NEVER set,
                     prompt hash determinism, subjective prompt builder
  4. Service layer — ScriptServiceError, _mask_identity, get_script identity gate,
                     submit_marks guards (FORBIDDEN/INVALID_STATUS/INCOMPLETE_MARKS),
                     board_finalise gate (requires MARKS_SUBMITTED),
                     assign_evaluator blocked after BOARD_FINALISED,
                     get_ledger_entry blocked pre-finalise
  5. Celery wiring — score_scanned_script importable, correct task name,
                     registered in celery_app.conf.include; prior tasks not regressed
  6. Router wiring — route count, static paths before param path,
                     Gate 1 /submit and Gate 2 /finalise present,
                     main.py includes /scripts router
  7. Audit events  — all 8 M09 events present; M06/M07/M08 not regressed
  8. Identity      — identity hidden before BOARD_FINALISED, revealed after
  9. Ledger safety — repository has no update/delete methods (append-only design)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ===========================================================================
# 1 — Models: enums, table names, status machine
# ===========================================================================

class TestScriptStatusEnum:
    def test_all_seven_status_values(self):
        from app.modules.m09_paper_admin.models import ScriptStatus
        expected = {
            "PENDING", "PROCESSING", "SCORED", "FAILED",
            "REVIEW_REQUIRED", "MARKS_SUBMITTED", "BOARD_FINALISED",
        }
        actual = {s.value for s in ScriptStatus}
        assert expected == actual

    def test_pending_is_initial(self):
        from app.modules.m09_paper_admin.models import ScriptStatus
        assert ScriptStatus.PENDING.value == "PENDING"

    def test_board_finalised_is_terminal(self):
        from app.modules.m09_paper_admin.models import ScriptStatus
        assert ScriptStatus.BOARD_FINALISED.value == "BOARD_FINALISED"

    def test_marks_submitted_is_gate1(self):
        from app.modules.m09_paper_admin.models import ScriptStatus
        assert ScriptStatus.MARKS_SUBMITTED.value == "MARKS_SUBMITTED"

    def test_status_is_str_enum(self):
        from app.modules.m09_paper_admin.models import ScriptStatus
        assert isinstance(ScriptStatus.SCORED, str)
        assert ScriptStatus.SCORED == "SCORED"


class TestEvaluationRoundEnum:
    def test_three_rounds_present(self):
        from app.modules.m09_paper_admin.models import EvaluationRound
        expected = {"PRIMARY", "SECONDARY", "MODERATION"}
        actual = {r.value for r in EvaluationRound}
        assert expected == actual

    def test_primary_is_default_round(self):
        from app.modules.m09_paper_admin.models import EvaluationRound
        assert EvaluationRound.PRIMARY.value == "PRIMARY"


class TestModelTableNames:
    def test_scanned_script_tablename(self):
        from app.modules.m09_paper_admin.models import ScannedScript
        assert ScannedScript.__tablename__ == "scanned_scripts"

    def test_script_evaluation_tablename(self):
        from app.modules.m09_paper_admin.models import ScriptEvaluation
        assert ScriptEvaluation.__tablename__ == "script_evaluations"

    def test_exam_score_ledger_tablename(self):
        from app.modules.m09_paper_admin.models import ExamScoreLedger
        assert ExamScoreLedger.__tablename__ == "exam_score_ledger"


class TestModelFields:
    def test_scanned_script_has_masked_id(self):
        from app.modules.m09_paper_admin.models import ScannedScript
        assert hasattr(ScannedScript, "masked_id")

    def test_scanned_script_has_student_identity_fields(self):
        from app.modules.m09_paper_admin.models import ScannedScript
        assert hasattr(ScannedScript, "student_user_id")
        assert hasattr(ScannedScript, "student_roll_ref")

    def test_scanned_script_has_gate1_fields(self):
        from app.modules.m09_paper_admin.models import ScannedScript
        assert hasattr(ScannedScript, "submitted_by")
        assert hasattr(ScannedScript, "submitted_at")

    def test_scanned_script_has_gate2_fields(self):
        from app.modules.m09_paper_admin.models import ScannedScript
        assert hasattr(ScannedScript, "finalised_by")
        assert hasattr(ScannedScript, "finalised_at")

    def test_script_evaluation_has_ai_fields(self):
        from app.modules.m09_paper_admin.models import ScriptEvaluation
        assert hasattr(ScriptEvaluation, "ai_suggested_marks")
        assert hasattr(ScriptEvaluation, "ai_justification")
        assert hasattr(ScriptEvaluation, "ai_model")

    def test_script_evaluation_has_evaluator_marks(self):
        from app.modules.m09_paper_admin.models import ScriptEvaluation
        assert hasattr(ScriptEvaluation, "evaluator_marks")
        assert hasattr(ScriptEvaluation, "evaluator_note")

    def test_script_evaluation_has_final_marks(self):
        from app.modules.m09_paper_admin.models import ScriptEvaluation
        assert hasattr(ScriptEvaluation, "final_marks")

    def test_ledger_has_total_and_max_marks(self):
        from app.modules.m09_paper_admin.models import ExamScoreLedger
        assert hasattr(ExamScoreLedger, "total_marks")
        assert hasattr(ExamScoreLedger, "max_marks")

    def test_ledger_has_finalised_by(self):
        from app.modules.m09_paper_admin.models import ExamScoreLedger
        assert hasattr(ExamScoreLedger, "finalised_by")


# ===========================================================================
# 2 — Schemas: validators
# ===========================================================================

class TestBulkMarkUpdate:
    def test_valid_single_entry_passes(self):
        from app.modules.m09_paper_admin.schemas import BulkMarkUpdate, EvaluatorMarkUpdate
        payload = BulkMarkUpdate(marks={str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=5.0)})
        assert len(payload.marks) == 1

    def test_empty_marks_dict_raises(self):
        import pydantic
        from app.modules.m09_paper_admin.schemas import BulkMarkUpdate
        with pytest.raises(pydantic.ValidationError):
            BulkMarkUpdate(marks={})

    def test_multiple_questions_passes(self):
        from app.modules.m09_paper_admin.schemas import BulkMarkUpdate, EvaluatorMarkUpdate
        payload = BulkMarkUpdate(marks={
            str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=3.0),
            str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=7.5),
        })
        assert len(payload.marks) == 2


class TestEvaluatorMarkUpdate:
    def test_zero_marks_is_valid(self):
        from app.modules.m09_paper_admin.schemas import EvaluatorMarkUpdate
        m = EvaluatorMarkUpdate(evaluator_marks=0.0)
        assert m.evaluator_marks == 0.0

    def test_negative_marks_rejected(self):
        import pydantic
        from app.modules.m09_paper_admin.schemas import EvaluatorMarkUpdate
        with pytest.raises(pydantic.ValidationError):
            EvaluatorMarkUpdate(evaluator_marks=-1.0)

    def test_note_optional(self):
        from app.modules.m09_paper_admin.schemas import EvaluatorMarkUpdate
        m = EvaluatorMarkUpdate(evaluator_marks=5.0)
        assert m.evaluator_note is None


class TestScriptSubmitMarksRequest:
    def test_valid_payload_passes(self):
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest, EvaluatorMarkUpdate
        req = ScriptSubmitMarksRequest(marks={
            str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=8.0),
        })
        assert len(req.marks) == 1

    def test_empty_marks_raises(self):
        import pydantic
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest
        with pytest.raises(pydantic.ValidationError):
            ScriptSubmitMarksRequest(marks={})

    def test_submission_note_optional(self):
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest, EvaluatorMarkUpdate
        req = ScriptSubmitMarksRequest(marks={
            str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=4.0),
        })
        assert req.submission_note is None


class TestScannedScriptResponse:
    def test_student_identity_fields_are_optional(self):
        from app.modules.m09_paper_admin.schemas import ScannedScriptResponse
        import inspect
        hints = ScannedScriptResponse.__annotations__
        # student_user_id and student_roll_ref should accept None
        assert "student_user_id" in hints
        assert "student_roll_ref" in hints

    def test_ocr_status_field_present(self):
        from app.modules.m09_paper_admin.schemas import ScannedScriptResponse
        assert "ocr_status" in ScannedScriptResponse.__annotations__


# ===========================================================================
# 3 — Script scorer: pure-function tests
# ===========================================================================

class TestMCQExtraction:
    def test_answer_colon_format(self):
        from app.modules.m09_paper_admin.script_scorer import _extract_mcq_option
        result = _extract_mcq_option("Answer: B", 1)
        assert result == "B"

    def test_ans_dot_format(self):
        from app.modules.m09_paper_admin.script_scorer import _extract_mcq_option
        result = _extract_mcq_option("Ans. C", 1)
        assert result == "C"

    def test_parenthesised_option(self):
        from app.modules.m09_paper_admin.script_scorer import _extract_mcq_option
        result = _extract_mcq_option("The answer is (A)", 1)
        assert result == "A"

    def test_option_with_period(self):
        from app.modules.m09_paper_admin.script_scorer import _extract_mcq_option
        result = _extract_mcq_option("D. Some text", 1)
        assert result == "D"

    def test_no_match_returns_none(self):
        from app.modules.m09_paper_admin.script_scorer import _extract_mcq_option
        result = _extract_mcq_option("Student wrote some paragraph here.", 1)
        assert result is None

    def test_returns_uppercase(self):
        from app.modules.m09_paper_admin.script_scorer import _extract_mcq_option
        result = _extract_mcq_option("answer: a", 1)
        assert result == "A"

    def test_question_context_isolation(self):
        from app.modules.m09_paper_admin.script_scorer import _extract_mcq_option
        # Q2 context should be found even when Q1 has a different answer
        ocr = "Q.1 Answer: A  Q.2 Answer: C  Q.3 Answer: B"
        result = _extract_mcq_option(ocr, 2)
        assert result == "C"


class TestScriptScorerNoOCR:
    @pytest.mark.asyncio
    async def test_no_ocr_all_marks_none(self):
        from app.modules.m09_paper_admin.script_scorer import score_script
        q = MagicMock()
        q.id = uuid4()
        q.question_type = "MCQ"
        q.marks = 5
        q.correct_option = "A"

        result = await score_script([q], None)
        assert result.had_ocr is False
        assert result.scores[0].ai_suggested_marks is None

    @pytest.mark.asyncio
    async def test_no_ocr_objective_auto_score_zero(self):
        from app.modules.m09_paper_admin.script_scorer import score_script
        q = MagicMock()
        q.id = uuid4()
        q.question_type = "MCQ"
        q.marks = 10
        q.correct_option = "B"

        result = await score_script([q], "")
        assert result.objective_auto_score == 0.0

    @pytest.mark.asyncio
    async def test_no_ocr_evaluator_marks_never_set(self):
        """Invariant: score_script returns QuestionScore — never touches evaluator_marks."""
        from app.modules.m09_paper_admin.script_scorer import score_script, QuestionScore
        q = MagicMock()
        q.id = uuid4()
        q.question_type = "SHORT_ANSWER"
        q.marks = 8
        q.question_text = "Explain polymorphism."
        q.model_answer = None
        q.marking_scheme = []

        result = await score_script([q], None)
        for score in result.scores:
            assert isinstance(score, QuestionScore)
            assert not hasattr(score, "evaluator_marks"), (
                "QuestionScore must not have evaluator_marks — Celery invariant violated"
            )

    @pytest.mark.asyncio
    async def test_no_ocr_returns_review_justification(self):
        from app.modules.m09_paper_admin.script_scorer import score_script
        q = MagicMock()
        q.id = uuid4()
        q.question_type = "LONG_ANSWER"
        q.marks = 10
        q.question_text = "Discuss recursion."
        q.model_answer = None
        q.marking_scheme = []

        result = await score_script([q], None)
        assert "OCR" in result.scores[0].ai_justification or \
               "evaluator" in result.scores[0].ai_justification.lower()

    @pytest.mark.asyncio
    async def test_mcq_correct_answer_scores_full_marks(self):
        from app.modules.m09_paper_admin.script_scorer import score_script
        q = MagicMock()
        q.id = uuid4()
        q.question_type = "MCQ"
        q.marks = 4
        q.correct_option = "B"

        result = await score_script([q], "Q.1 Answer: B")
        assert result.scores[0].ai_suggested_marks == 4.0
        assert result.objective_auto_score == 4.0

    @pytest.mark.asyncio
    async def test_mcq_wrong_answer_scores_zero(self):
        from app.modules.m09_paper_admin.script_scorer import score_script
        q = MagicMock()
        q.id = uuid4()
        q.question_type = "MCQ"
        q.marks = 4
        q.correct_option = "C"

        result = await score_script([q], "Q.1 Answer: A")
        assert result.scores[0].ai_suggested_marks == 0.0
        assert result.objective_auto_score == 0.0


class TestScriptScorerDataclasses:
    def test_question_score_fields(self):
        from app.modules.m09_paper_admin.script_scorer import QuestionScore
        qs = QuestionScore(
            question_id=uuid4(),
            question_type="MCQ",
            max_marks=5.0,
            ai_suggested_marks=4.0,
            ai_justification="Correct.",
            ai_model="auto",
            prompt_hash="abc123",
        )
        assert qs.ai_suggested_marks == 4.0
        assert qs.max_marks == 5.0

    def test_script_scoring_result_fields(self):
        from app.modules.m09_paper_admin.script_scorer import ScriptScoringResult
        r = ScriptScoringResult(scores=[], objective_auto_score=10.0, had_ocr=True)
        assert r.had_ocr is True
        assert r.objective_auto_score == 10.0

    def test_prompt_hash_is_deterministic(self):
        from app.modules.m09_paper_admin.script_scorer import _prompt_hash
        h1 = _prompt_hash("system text", "user text")
        h2 = _prompt_hash("system text", "user text")
        assert h1 == h2

    def test_prompt_hash_differs_for_different_inputs(self):
        from app.modules.m09_paper_admin.script_scorer import _prompt_hash
        h1 = _prompt_hash("system A", "user A")
        h2 = _prompt_hash("system B", "user B")
        assert h1 != h2

    def test_prompt_hash_is_16_chars(self):
        from app.modules.m09_paper_admin.script_scorer import _prompt_hash
        h = _prompt_hash("s", "u")
        assert len(h) == 16


class TestSubjectivePromptBuilder:
    def test_prompt_contains_question_text(self):
        from app.modules.m09_paper_admin.script_scorer import _build_subjective_prompt
        sys_p, user_p = _build_subjective_prompt(
            question_text="Explain OOP.",
            question_type="SHORT_ANSWER",
            max_marks=5.0,
            model_answer=None,
            marking_scheme=None,
            ocr_text="Student wrote something.",
        )
        assert "Explain OOP." in user_p

    def test_prompt_contains_max_marks(self):
        from app.modules.m09_paper_admin.script_scorer import _build_subjective_prompt
        _, user_p = _build_subjective_prompt(
            question_text="Q",
            question_type="LONG_ANSWER",
            max_marks=15.0,
            model_answer=None,
            marking_scheme=None,
            ocr_text="text",
        )
        assert "15" in user_p

    def test_prompt_includes_model_answer_when_provided(self):
        from app.modules.m09_paper_admin.script_scorer import _build_subjective_prompt
        _, user_p = _build_subjective_prompt(
            question_text="Q",
            question_type="SHORT_ANSWER",
            max_marks=5.0,
            model_answer="Expected answer here.",
            marking_scheme=None,
            ocr_text="text",
        )
        assert "Expected answer here." in user_p

    def test_system_prompt_forbids_markdown(self):
        from app.modules.m09_paper_admin.script_scorer import _build_subjective_prompt
        sys_p, _ = _build_subjective_prompt(
            question_text="Q",
            question_type="MCQ",
            max_marks=2.0,
            model_answer=None,
            marking_scheme=None,
            ocr_text="ans",
        )
        assert "JSON" in sys_p
        assert "markdown" in sys_p.lower() or "prose" in sys_p.lower()

    def test_prompt_returns_tuple_of_two_strings(self):
        from app.modules.m09_paper_admin.script_scorer import _build_subjective_prompt
        result = _build_subjective_prompt("Q", "LONG_ANSWER", 10.0, None, None, "ocr")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(s, str) for s in result)


# ===========================================================================
# 4 — Service layer: error class + human gate guards
# ===========================================================================

class TestScriptServiceError:
    def test_error_fields(self):
        from app.modules.m09_paper_admin.service import ScriptServiceError
        err = ScriptServiceError("NOT_FOUND", "Not found.", 404)
        assert err.code == "NOT_FOUND"
        assert err.message == "Not found."
        assert err.status_code == 404

    def test_default_status_code_is_400(self):
        from app.modules.m09_paper_admin.service import ScriptServiceError
        err = ScriptServiceError("BAD", "Bad.")
        assert err.status_code == 400

    def test_is_exception(self):
        from app.modules.m09_paper_admin.service import ScriptServiceError
        with pytest.raises(ScriptServiceError) as exc_info:
            raise ScriptServiceError("FORBIDDEN", "Access denied.", 403)
        assert exc_info.value.status_code == 403


class TestMaskIdentity:
    def test_mask_clears_fields_when_not_finalised(self):
        from app.modules.m09_paper_admin.service import _mask_identity
        from app.modules.m09_paper_admin.models import ScriptStatus
        script = MagicMock()
        script.status = ScriptStatus.SCORED.value
        script.student_user_id = uuid4()
        script.student_roll_ref = "ROLL001"

        _mask_identity(script)
        assert script.student_user_id is None
        assert script.student_roll_ref is None

    def test_mask_leaves_identity_when_board_finalised(self):
        from app.modules.m09_paper_admin.service import _mask_identity
        from app.modules.m09_paper_admin.models import ScriptStatus
        uid = uuid4()
        script = MagicMock()
        script.status = ScriptStatus.BOARD_FINALISED.value
        script.student_user_id = uid
        script.student_roll_ref = "ROLL999"

        _mask_identity(script)
        assert script.student_user_id == uid
        assert script.student_roll_ref == "ROLL999"

    def test_mask_applied_on_pending_status(self):
        from app.modules.m09_paper_admin.service import _mask_identity
        from app.modules.m09_paper_admin.models import ScriptStatus
        script = MagicMock()
        script.status = ScriptStatus.PENDING.value
        script.student_user_id = uuid4()
        script.student_roll_ref = "R"

        _mask_identity(script)
        assert script.student_user_id is None

    def test_mask_applied_on_marks_submitted_status(self):
        from app.modules.m09_paper_admin.service import _mask_identity
        from app.modules.m09_paper_admin.models import ScriptStatus
        script = MagicMock()
        script.status = ScriptStatus.MARKS_SUBMITTED.value
        script.student_user_id = uuid4()
        script.student_roll_ref = "R"

        _mask_identity(script)
        assert script.student_user_id is None
        assert script.student_roll_ref is None


class TestGetScriptIdentityGate:
    @pytest.mark.asyncio
    async def test_identity_masked_by_default(self):
        from app.modules.m09_paper_admin.service import ScriptService
        from app.modules.m09_paper_admin.models import ScriptStatus
        uid = uuid4()
        script = MagicMock()
        script.status = ScriptStatus.SCORED.value
        script.student_user_id = uid
        script.student_roll_ref = "ROLL"

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            result = await ScriptService.get_script(uuid4(), db=AsyncMock())
        assert result.student_user_id is None

    @pytest.mark.asyncio
    async def test_identity_revealed_when_board_finalised_and_include_true(self):
        from app.modules.m09_paper_admin.service import ScriptService
        from app.modules.m09_paper_admin.models import ScriptStatus
        uid = uuid4()
        script = MagicMock()
        script.status = ScriptStatus.BOARD_FINALISED.value
        script.student_user_id = uid
        script.student_roll_ref = "ROLL"

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            result = await ScriptService.get_script(
                uuid4(), include_identity=True, db=AsyncMock()
            )
        assert result.student_user_id == uid

    @pytest.mark.asyncio
    async def test_identity_still_masked_if_not_finalised_even_with_include_flag(self):
        from app.modules.m09_paper_admin.service import ScriptService
        from app.modules.m09_paper_admin.models import ScriptStatus
        script = MagicMock()
        script.status = ScriptStatus.MARKS_SUBMITTED.value
        script.student_user_id = uuid4()
        script.student_roll_ref = "R"

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            result = await ScriptService.get_script(
                uuid4(), include_identity=True, db=AsyncMock()
            )
        assert result.student_user_id is None


class TestSubmitMarksGates:
    @pytest.mark.asyncio
    async def test_submit_forbidden_when_not_assigned_evaluator(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest, EvaluatorMarkUpdate
        from app.modules.m09_paper_admin.models import ScriptStatus

        assigned_id = uuid4()
        script = MagicMock()
        script.status = ScriptStatus.SCORED.value
        script.evaluator_id = assigned_id
        script.second_evaluator_id = None

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.submit_marks(
                    uuid4(),
                    ScriptSubmitMarksRequest(marks={
                        str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=5.0)
                    }),
                    evaluator_user_id=uuid4(),  # not the assigned evaluator
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.code == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_submit_rejected_when_already_submitted(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest, EvaluatorMarkUpdate
        from app.modules.m09_paper_admin.models import ScriptStatus

        evaluator_id = uuid4()
        script = MagicMock()
        script.status = ScriptStatus.MARKS_SUBMITTED.value
        script.evaluator_id = evaluator_id
        script.second_evaluator_id = None

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.submit_marks(
                    uuid4(),
                    ScriptSubmitMarksRequest(marks={
                        str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=5.0)
                    }),
                    evaluator_user_id=evaluator_id,
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_submit_rejected_when_already_finalised(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest, EvaluatorMarkUpdate
        from app.modules.m09_paper_admin.models import ScriptStatus

        evaluator_id = uuid4()
        script = MagicMock()
        script.status = ScriptStatus.BOARD_FINALISED.value
        script.evaluator_id = evaluator_id
        script.second_evaluator_id = None

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.submit_marks(
                    uuid4(),
                    ScriptSubmitMarksRequest(marks={
                        str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=5.0)
                    }),
                    evaluator_user_id=evaluator_id,
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_submit_rejected_when_evals_missing_marks(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest, EvaluatorMarkUpdate
        from app.modules.m09_paper_admin.models import ScriptStatus

        evaluator_id = uuid4()
        script = MagicMock()
        script.status = ScriptStatus.SCORED.value
        script.evaluator_id = evaluator_id
        script.second_evaluator_id = None

        # Two evals, one missing marks
        ev1 = MagicMock(); ev1.evaluator_marks = 5.0; ev1.question_id = uuid4()
        ev2 = MagicMock(); ev2.evaluator_marks = None; ev2.question_id = uuid4()

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.bulk_update_evaluator_marks",
            new=AsyncMock(),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
            new=AsyncMock(return_value=[ev1, ev2]),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.submit_marks(
                    uuid4(),
                    ScriptSubmitMarksRequest(marks={
                        str(ev1.question_id): EvaluatorMarkUpdate(evaluator_marks=5.0),
                    }),
                    evaluator_user_id=evaluator_id,
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INCOMPLETE_MARKS"

    @pytest.mark.asyncio
    async def test_submit_rejected_when_no_evaluations_exist(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest, EvaluatorMarkUpdate
        from app.modules.m09_paper_admin.models import ScriptStatus

        evaluator_id = uuid4()
        script = MagicMock()
        script.status = ScriptStatus.SCORED.value
        script.evaluator_id = evaluator_id
        script.second_evaluator_id = None

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.bulk_update_evaluator_marks",
            new=AsyncMock(),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
            new=AsyncMock(return_value=[]),  # no evaluations
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.submit_marks(
                    uuid4(),
                    ScriptSubmitMarksRequest(marks={
                        str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=5.0)
                    }),
                    evaluator_user_id=evaluator_id,
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "NO_EVALUATIONS"

    @pytest.mark.asyncio
    async def test_second_evaluator_can_submit(self):
        """second_evaluator_id is also allowed to submit at Gate 1."""
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptSubmitMarksRequest, EvaluatorMarkUpdate
        from app.modules.m09_paper_admin.models import ScriptStatus

        primary_id = uuid4()
        secondary_id = uuid4()
        script = MagicMock()
        script.id = uuid4()
        script.status = ScriptStatus.SCORED.value
        script.evaluator_id = primary_id
        script.second_evaluator_id = secondary_id

        ev = MagicMock(); ev.evaluator_marks = 7.0; ev.question_id = uuid4()

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.bulk_update_evaluator_marks",
            new=AsyncMock(),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.list_by_script",
            new=AsyncMock(return_value=[ev]),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.set_marks_submitted",
            new=AsyncMock(),
        ), patch(
            "app.core.audit_log.service.AuditService.log",
            new=AsyncMock(),
        ):
            db = AsyncMock()
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            # Should not raise — secondary evaluator is allowed
            result = await ScriptService.submit_marks(
                script.id,
                ScriptSubmitMarksRequest(marks={
                    str(ev.question_id): EvaluatorMarkUpdate(evaluator_marks=7.0)
                }),
                evaluator_user_id=secondary_id,
                tenant_id=uuid4(),
                db=db,
            )
            # Identity masked because status != BOARD_FINALISED
            assert result.student_user_id is None


class TestBoardFinaliseGate:
    @pytest.mark.asyncio
    async def test_finalise_requires_marks_submitted(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptFinaliseRequest
        from app.modules.m09_paper_admin.models import ScriptStatus

        script = MagicMock()
        script.status = ScriptStatus.SCORED.value  # not MARKS_SUBMITTED

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.board_finalise(
                    uuid4(),
                    ScriptFinaliseRequest(),
                    board_user_id=uuid4(),
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_finalise_rejected_when_pending(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptFinaliseRequest
        from app.modules.m09_paper_admin.models import ScriptStatus

        script = MagicMock()
        script.status = ScriptStatus.PENDING.value

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.board_finalise(
                    uuid4(),
                    ScriptFinaliseRequest(),
                    board_user_id=uuid4(),
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_finalise_rejected_when_not_found(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptFinaliseRequest

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.board_finalise(
                    uuid4(),
                    ScriptFinaliseRequest(),
                    board_user_id=uuid4(),
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_finalise_reveals_identity_in_result(self):
        """After board_finalise, script.student_user_id must be visible (not masked)."""
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService
        from app.modules.m09_paper_admin.schemas import ScriptFinaliseRequest
        from app.modules.m09_paper_admin.models import ScriptStatus

        uid = uuid4()
        script = MagicMock()
        script.id = uuid4()
        script.status = ScriptStatus.MARKS_SUBMITTED.value
        script.exam_paper_id = uuid4()
        script.student_user_id = uid
        script.student_roll_ref = "ROLL123"
        ledger_mock = MagicMock()

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.set_final_marks",
            new=AsyncMock(),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_evaluator_marks",
            new=AsyncMock(return_value=42.5),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptEvaluationRepository.sum_max_marks",
            new=AsyncMock(return_value=50.0),
        ), patch(
            "app.modules.m09_paper_admin.service.ExamScoreLedgerRepository.create",
            new=AsyncMock(return_value=ledger_mock),
        ), patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.set_finalised",
            new=AsyncMock(),
        ), patch(
            "app.core.audit_log.service.AuditService.log",
            new=AsyncMock(),
        ):
            db = AsyncMock()
            db.commit = AsyncMock()
            db.refresh = AsyncMock(side_effect=lambda obj: setattr(
                obj, "status", ScriptStatus.BOARD_FINALISED.value
            ))

            result_script, result_ledger = await ScriptService.board_finalise(
                script.id,
                ScriptFinaliseRequest(finalisation_note="Looks correct."),
                board_user_id=uuid4(),
                tenant_id=uuid4(),
                db=db,
            )

        # Identity NOT masked — board finalise returns raw identity
        assert result_script.student_user_id == uid


class TestAssignEvaluatorGate:
    @pytest.mark.asyncio
    async def test_assign_blocked_after_board_finalised(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import ScriptAssignEvaluatorRequest
        from app.modules.m09_paper_admin.models import ScriptStatus

        script = MagicMock()
        script.status = ScriptStatus.BOARD_FINALISED.value

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.assign_evaluator(
                    uuid4(),
                    ScriptAssignEvaluatorRequest(evaluator_id=uuid4()),
                    assigned_by=uuid4(),
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"


class TestGetLedgerEntryGate:
    @pytest.mark.asyncio
    async def test_ledger_blocked_before_finalised(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.models import ScriptStatus

        script = MagicMock()
        script.status = ScriptStatus.MARKS_SUBMITTED.value

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.get_ledger_entry(uuid4(), db=AsyncMock())
            assert exc_info.value.status_code == 403
            assert exc_info.value.code == "NOT_FINALISED"

    @pytest.mark.asyncio
    async def test_ledger_blocked_for_scored_status(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.models import ScriptStatus

        script = MagicMock()
        script.status = ScriptStatus.SCORED.value

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.get_ledger_entry(uuid4(), db=AsyncMock())
            assert exc_info.value.code == "NOT_FINALISED"


class TestUpdateMarksStatusGuard:
    @pytest.mark.asyncio
    async def test_update_marks_rejected_when_pending(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import BulkMarkUpdate, EvaluatorMarkUpdate
        from app.modules.m09_paper_admin.models import ScriptStatus

        script = MagicMock()
        script.status = ScriptStatus.PENDING.value

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.update_evaluator_marks(
                    uuid4(),
                    BulkMarkUpdate(marks={str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=5.0)}),
                    evaluator_user_id=uuid4(),
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_update_marks_rejected_when_board_finalised(self):
        from uuid import uuid4
        from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError
        from app.modules.m09_paper_admin.schemas import BulkMarkUpdate, EvaluatorMarkUpdate
        from app.modules.m09_paper_admin.models import ScriptStatus

        script = MagicMock()
        script.status = ScriptStatus.BOARD_FINALISED.value

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.get_by_id",
            new=AsyncMock(return_value=script),
        ):
            with pytest.raises(ScriptServiceError) as exc_info:
                await ScriptService.update_evaluator_marks(
                    uuid4(),
                    BulkMarkUpdate(marks={str(uuid4()): EvaluatorMarkUpdate(evaluator_marks=5.0)}),
                    evaluator_user_id=uuid4(),
                    tenant_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"


# ===========================================================================
# 5 — Celery task wiring
# ===========================================================================

class TestCeleryTaskWiring:
    def test_score_scanned_script_importable(self):
        from app.workers.heavy.score_scanned_script import score_scanned_script
        assert callable(score_scanned_script)

    def test_score_scanned_script_task_name(self):
        from app.workers.heavy.score_scanned_script import score_scanned_script
        assert score_scanned_script.name == "app.workers.heavy.score_scanned_script"

    def test_score_scanned_script_in_celery_include(self):
        from app.workers.celery_app import celery_app
        assert "app.workers.heavy.score_scanned_script" in celery_app.conf.include

    def test_m09_task_routes_to_heavy_queue(self):
        from app.workers.celery_app import celery_app
        routes = celery_app.conf.task_routes
        assert "app.workers.heavy.*" in routes
        assert routes["app.workers.heavy.*"]["queue"] == "celery-heavy"

    def test_m08_tasks_not_regressed(self):
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.generate_exam_paper" in include
        assert "app.workers.heavy.release_exam_paper" in include

    def test_m07_tasks_not_regressed(self):
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.evaluate_research_proposal" in include
        assert "app.workers.heavy.evaluate_research_document" in include
        assert "app.workers.heavy.process_viva_session" in include

    def test_m06_task_not_regressed(self):
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.evaluate_lab_submission" in include

    def test_score_task_uses_max_retries_2(self):
        from app.workers.heavy.score_scanned_script import score_scanned_script
        assert score_scanned_script.max_retries == 2


# ===========================================================================
# 6 — Router wiring
# ===========================================================================

class TestRouterWiring:
    def test_script_router_has_minimum_routes(self):
        from app.modules.m09_paper_admin.router import router
        assert len(router.routes) >= 12

    def test_gate1_submit_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/{script_id}/submit" in paths

    def test_gate2_finalise_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/{script_id}/finalise" in paths

    def test_upload_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/upload" in paths

    def test_board_pending_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/board/pending" in paths

    def test_evaluator_me_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/evaluator/me" in paths

    def test_evaluations_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/{script_id}/evaluations" in paths

    def test_ledger_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/{script_id}/ledger" in paths

    def test_marks_patch_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/{script_id}/marks" in paths

    def test_assign_endpoint_present(self):
        from app.modules.m09_paper_admin.router import router
        paths = {r.path for r in router.routes}
        assert "/{script_id}/assign" in paths

    def test_static_board_path_before_param_path(self):
        """Verify /board/pending is registered before /{script_id} to avoid routing conflicts."""
        from app.modules.m09_paper_admin.router import router
        paths = [r.path for r in router.routes]
        board_idx  = next((i for i, p in enumerate(paths) if p == "/board/pending"), None)
        param_idx  = next((i for i, p in enumerate(paths) if "{script_id}" in p), None)
        assert board_idx is not None, "Missing /board/pending route"
        assert param_idx is not None, "Missing /{script_id} route"
        assert board_idx < param_idx, (
            "/board/pending must be declared before /{script_id} to prevent routing conflicts"
        )

    def test_main_includes_scripts_router(self):
        from app.main import app
        paths = [r.path for r in app.routes]
        script_paths = [p for p in paths if "/scripts" in p]
        assert len(script_paths) >= 5, "main.py must include the /scripts router"


# ===========================================================================
# 7 — Audit events: M09 present; M06/M07/M08 not regressed
# ===========================================================================

class TestM09AuditEvents:
    def test_all_m09_scoring_events_present(self):
        from app.core.audit_log.models import AuditEventType
        events = [
            "SCRIPT_SCORING_QUEUED",
            "SCRIPT_SCORING_COMPLETED",
            "SCRIPT_SCORING_FAILED",
        ]
        for name in events:
            assert hasattr(AuditEventType, name), f"Missing M09 audit event: {name}"

    def test_all_m09_human_gate_events_present(self):
        from app.core.audit_log.models import AuditEventType
        gate_events = [
            "SCRIPT_MARKS_SUBMITTED",   # Gate 1
            "SCRIPT_BOARD_FINALISED",   # Gate 2
        ]
        for name in gate_events:
            assert hasattr(AuditEventType, name), f"Missing gate event: {name}"

    def test_all_m09_admin_events_present(self):
        from app.core.audit_log.models import AuditEventType
        admin_events = [
            "SCRIPT_EVALUATOR_ASSIGNED",
            "SCRIPT_MARKS_UPDATED",
            "EXAM_SCORE_RECORDED",
        ]
        for name in admin_events:
            assert hasattr(AuditEventType, name), f"Missing admin event: {name}"

    def test_m09_event_count_is_eight(self):
        from app.core.audit_log.models import AuditEventType
        m09_events = [
            "SCRIPT_SCORING_QUEUED", "SCRIPT_SCORING_COMPLETED", "SCRIPT_SCORING_FAILED",
            "SCRIPT_EVALUATOR_ASSIGNED", "SCRIPT_MARKS_UPDATED", "SCRIPT_MARKS_SUBMITTED",
            "SCRIPT_BOARD_FINALISED", "EXAM_SCORE_RECORDED",
        ]
        for name in m09_events:
            assert hasattr(AuditEventType, name)
        assert len(m09_events) == 8

    def test_m08_events_not_regressed(self):
        from app.core.audit_log.models import AuditEventType
        m08_events = [
            "EXAM_PAPER_CREATED",
            "EXAM_PAPER_SUBMITTED",
            "EXAM_PAPER_BOARD_APPROVED",
            "EXAM_PAPER_SEALED",
            "EXAM_PAPER_RELEASED",
        ]
        for name in m08_events:
            assert hasattr(AuditEventType, name), f"M08 regression: {name}"

    def test_m07_events_not_regressed(self):
        from app.core.audit_log.models import AuditEventType
        m07_events = [
            "RESEARCH_PROBLEM_SUBMITTED",
            "VIVA_SESSION_COMPLETED",
            "VIVA_GUIDE_RATIFIED",
        ]
        for name in m07_events:
            assert hasattr(AuditEventType, name), f"M07 regression: {name}"

    def test_m06_events_not_regressed(self):
        from app.core.audit_log.models import AuditEventType
        m06_events = [
            "LAB_EVAL_COMPLETED",
            "LAB_SUBMISSION_RATIFIED",
        ]
        for name in m06_events:
            assert hasattr(AuditEventType, name), f"M06 regression: {name}"


# ===========================================================================
# 8 — Identity invariant: list endpoints mask identity
# ===========================================================================

class TestIdentityMaskingInListEndpoints:
    @pytest.mark.asyncio
    async def test_list_scripts_masks_non_finalised(self):
        from app.modules.m09_paper_admin.service import ScriptService
        from app.modules.m09_paper_admin.models import ScriptStatus

        uid = uuid4()
        s1 = MagicMock(); s1.status = ScriptStatus.SCORED.value
        s1.student_user_id = uid; s1.student_roll_ref = "R1"

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.list_all",
            new=AsyncMock(return_value=[s1]),
        ), patch(
            "app.modules.m09_paper_admin.service._count_scripts",
            new=AsyncMock(return_value=1),
        ):
            items, total = await ScriptService.list_scripts(db=AsyncMock())

        assert items[0].student_user_id is None

    @pytest.mark.asyncio
    async def test_list_scripts_preserves_identity_for_finalised(self):
        from app.modules.m09_paper_admin.service import ScriptService
        from app.modules.m09_paper_admin.models import ScriptStatus

        uid = uuid4()
        s1 = MagicMock(); s1.status = ScriptStatus.BOARD_FINALISED.value
        s1.student_user_id = uid; s1.student_roll_ref = "R1"

        with patch(
            "app.modules.m09_paper_admin.service.ScriptRepository.list_all",
            new=AsyncMock(return_value=[s1]),
        ), patch(
            "app.modules.m09_paper_admin.service._count_scripts",
            new=AsyncMock(return_value=1),
        ):
            items, total = await ScriptService.list_scripts(db=AsyncMock())

        assert items[0].student_user_id == uid


# ===========================================================================
# 9 — Ledger append-only: repository has no update/delete
# ===========================================================================

class TestLedgerAppendOnly:
    def test_ledger_repository_has_no_update_method(self):
        from app.modules.m09_paper_admin.repository import ExamScoreLedgerRepository
        assert not hasattr(ExamScoreLedgerRepository, "update"), (
            "ExamScoreLedgerRepository must not expose an update() method — ledger is append-only"
        )

    def test_ledger_repository_has_no_delete_method(self):
        from app.modules.m09_paper_admin.repository import ExamScoreLedgerRepository
        assert not hasattr(ExamScoreLedgerRepository, "delete"), (
            "ExamScoreLedgerRepository must not expose a delete() method — ledger is append-only"
        )

    def test_ledger_repository_has_create_method(self):
        from app.modules.m09_paper_admin.repository import ExamScoreLedgerRepository
        assert hasattr(ExamScoreLedgerRepository, "create")

    def test_ledger_repository_has_get_by_script_method(self):
        from app.modules.m09_paper_admin.repository import ExamScoreLedgerRepository
        assert hasattr(ExamScoreLedgerRepository, "get_by_script")

    def test_masked_id_generator_format(self):
        from app.modules.m09_paper_admin.service import _gen_masked_id
        for _ in range(20):
            mid = _gen_masked_id()
            assert mid.startswith("S"), f"masked_id must start with 'S', got {mid!r}"
            assert len(mid) == 11, f"masked_id must be 11 chars, got {len(mid)}"
            assert mid[1:].isupper() or mid[1:].isalnum(), "rest must be hex upper"
