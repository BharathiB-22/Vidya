"""
M06 Labs Evaluator — unit tests for pure-function modules (STEP-16).

Covers:
  1. AI scan heuristics (ai_scan.py)
  2. Plagiarism cosine scoring (plagiarism.py)
  3. Static analyser (static_analyser.py)
  4. Code sandbox (code_sandbox.py)
  5. Rubric scorer (rubric_scorer.py) — mocked LLM
  6. Service layer invariants (service.py)
"""
from __future__ import annotations

import uuid
from textwrap import dedent
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===========================================================================
# 1 — AI content scan
# ===========================================================================

class TestAIScanHeuristics:
    def test_empty_text_returns_zero_probability(self):
        from app.modules.m06_labs_evaluator.ai_scan import scan
        result = scan("")
        assert result.probability == 0.0
        assert result.is_flagged is False

    def test_very_short_text_returns_zero_probability(self):
        from app.modules.m06_labs_evaluator.ai_scan import scan
        result = scan("Hello world")
        assert result.probability == 0.0

    def test_probability_in_0_1_range(self):
        from app.modules.m06_labs_evaluator.ai_scan import scan
        text = " ".join(["word"] * 300)
        result = scan(text)
        assert 0.0 <= result.probability <= 1.0

    def test_highly_repetitive_text_has_elevated_probability(self):
        from app.modules.m06_labs_evaluator.ai_scan import scan
        # Exact repetition of the same sentence → high repetition score
        phrase = "The system processes inputs and produces outputs efficiently."
        text = " ".join([phrase] * 15)
        result = scan(text)
        assert result.repetition_score > 0.1

    def test_bursty_text_lower_ai_probability(self):
        from app.modules.m06_labs_evaluator.ai_scan import scan
        # Mix of very short and very long sentences → bursty → human-like
        bursty = (
            "Yes! "
            "No. "
            "This is a considerably longer sentence that explains the concept in more detail than the previous ones. "
            "Why? "
            "Because the topic demands it, requiring substantial elaboration and careful consideration of multiple factors."
        ) * 10
        result_bursty = scan(bursty)
        # Flat sentences — AI-like
        flat = " ".join(["The system processes data and returns results effectively."] * 20)
        result_flat = scan(flat)
        assert result_bursty.burstiness_score >= result_flat.burstiness_score

    def test_threshold_controls_is_flagged(self):
        from app.modules.m06_labs_evaluator.ai_scan import scan
        text = " ".join(["word"] * 300)
        result_high = scan(text, threshold=1.0)   # impossible threshold
        result_low  = scan(text, threshold=0.001) # always flag
        assert result_high.is_flagged is False
        assert result_low.is_flagged is True

    def test_result_has_all_fields(self):
        from app.modules.m06_labs_evaluator.ai_scan import scan, AIScanResult
        result = scan("Some text about the topic." * 30)
        assert isinstance(result, AIScanResult)
        assert hasattr(result, "probability")
        assert hasattr(result, "burstiness_score")
        assert hasattr(result, "repetition_score")
        assert hasattr(result, "vocab_richness_score")
        assert hasattr(result, "highlights")
        assert isinstance(result.highlights, list)

    def test_highlights_only_present_when_flagged(self):
        from app.modules.m06_labs_evaluator.ai_scan import scan
        text = " ".join(["unique distinct varied creative text"] * 50)
        result = scan(text, threshold=0.9999)
        if not result.is_flagged:
            assert result.highlights == []


class TestAIScanInternals:
    def test_burstiness_signal_short_text_returns_neutral(self):
        from app.modules.m06_labs_evaluator.ai_scan import _burstiness_signal
        assert _burstiness_signal("One sentence.") == 0.5

    def test_repetition_signal_too_short_returns_zero(self):
        from app.modules.m06_labs_evaluator.ai_scan import _repetition_signal
        assert _repetition_signal("hi") == 0.0

    def test_repetition_signal_pure_repeat_is_high(self):
        from app.modules.m06_labs_evaluator.ai_scan import _repetition_signal
        repeated = "cat sat mat bat " * 20
        score = _repetition_signal(repeated)
        assert score > 0.5

    def test_vocab_richness_empty_returns_neutral(self):
        from app.modules.m06_labs_evaluator.ai_scan import _vocab_richness_signal
        assert _vocab_richness_signal("") == 0.5


# ===========================================================================
# 2 — Plagiarism scoring
# ===========================================================================

class TestPlagiarismScoring:
    def _ids(self, n=3):
        return [uuid.uuid4() for _ in range(n)]

    def test_empty_cohort_returns_zero(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        result = compute_plagiarism("some text", cohort=[])
        assert result.max_similarity == 0.0
        assert result.is_flagged is False
        assert result.matches == []

    def test_empty_target_returns_zero(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        ids = self._ids(1)
        result = compute_plagiarism("", cohort=[(ids[0], "some text")])
        assert result.max_similarity == 0.0

    def test_identical_text_has_high_similarity(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        text = "This is a test submission about machine learning algorithms."
        ids = self._ids(1)
        result = compute_plagiarism(text, cohort=[(ids[0], text)])
        assert result.max_similarity > 0.95

    def test_completely_different_text_has_low_similarity(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        ids = self._ids(1)
        result = compute_plagiarism(
            "Python is a programming language used for data science.",
            cohort=[(ids[0], "The quick brown fox jumps over the lazy dog in the park.")],
        )
        assert result.max_similarity < 0.5

    def test_flagged_when_above_threshold(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        text = "This assignment discusses neural networks and backpropagation."
        ids = self._ids(1)
        result = compute_plagiarism(text, cohort=[(ids[0], text)], threshold=0.5)
        assert result.is_flagged is True

    def test_not_flagged_when_below_threshold(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        ids = self._ids(1)
        result = compute_plagiarism(
            "My unique perspective on the subject matter.",
            cohort=[(ids[0], "A completely different discussion about something else.")],
            threshold=0.99,
        )
        assert result.is_flagged is False

    def test_top_k_matches_respected(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        text = "machine learning neural networks deep learning"
        ids = self._ids(5)
        cohort = [(sid, text) for sid in ids]
        result = compute_plagiarism(text, cohort=cohort, top_k=3)
        assert len(result.matches) <= 3

    def test_matches_sorted_descending(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        target = "machine learning algorithms for classification tasks."
        ids = self._ids(3)
        cohort = [
            (ids[0], "machine learning algorithms for classification tasks."),
            (ids[1], "machine learning for tasks in various domains."),
            (ids[2], "unrelated text about cooking and recipes."),
        ]
        result = compute_plagiarism(target, cohort=cohort, top_k=3)
        sims = [m["similarity"] for m in result.matches]
        assert sims == sorted(sims, reverse=True)

    def test_student_ids_included_in_matches(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        sub_id = uuid.uuid4()
        student_id = uuid.uuid4()
        result = compute_plagiarism(
            "test text",
            cohort=[(sub_id, "test text")],
            student_ids={sub_id: student_id},
        )
        assert len(result.matches) == 1
        assert result.matches[0]["student_user_id"] == str(student_id)

    def test_max_similarity_in_0_1_range(self):
        from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
        ids = self._ids(2)
        result = compute_plagiarism(
            "hello world test",
            cohort=[(ids[0], "hello world test"), (ids[1], "foo bar baz")],
        )
        assert 0.0 <= result.max_similarity <= 1.0


# ===========================================================================
# 3 — Static analyser
# ===========================================================================

class TestStaticAnalyser:
    def test_valid_simple_code_returns_no_error(self):
        from app.modules.m06_labs_evaluator.static_analyser import analyse
        code = dedent("""\
            def add(a, b):
                return a + b
            result = add(1, 2)
        """)
        result = analyse(code)
        assert result.parse_error is None

    def test_syntax_error_captured(self):
        from app.modules.m06_labs_evaluator.static_analyser import analyse
        result = analyse("def foo(: pass")
        assert result.parse_error is not None

    def test_complexity_label_present(self):
        from app.modules.m06_labs_evaluator.static_analyser import analyse
        code = dedent("""\
            def foo(x):
                if x > 0:
                    return x
                return -x
        """)
        result = analyse(code)
        assert result.complexity_label in ("A", "B", "C", "D", "E", "F")

    def test_empty_code_returns_result(self):
        from app.modules.m06_labs_evaluator.static_analyser import analyse
        result = analyse("")
        assert result is not None
        assert result.complexity_score == 0

    def test_result_has_issues_list(self):
        from app.modules.m06_labs_evaluator.static_analyser import analyse
        result = analyse("x = 1")
        assert isinstance(result.issues, list)

    def test_unused_import_detected_if_pyflakes_available(self):
        from app.modules.m06_labs_evaluator.static_analyser import analyse
        code = "import os\nx = 1\n"
        result = analyse(code)
        # pyflakes may not be installed; if it is, 'os' should appear as unused
        if result.issues:
            messages = [i["message"] for i in result.issues]
            assert any("os" in m or "imported" in m for m in messages)


# ===========================================================================
# 4 — Code sandbox
# ===========================================================================

class TestCodeSandbox:
    def test_hello_world_runs(self):
        from app.modules.m06_labs_evaluator.code_sandbox import run
        result = run("python", 'print("hello")', stdin="", timeout_s=5)
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_stdin_passed_to_script(self):
        from app.modules.m06_labs_evaluator.code_sandbox import run
        code = "import sys\nprint(sys.stdin.read().strip())"
        result = run("python", code, stdin="hello input", timeout_s=5)
        assert "hello input" in result.stdout

    def test_syntax_error_captured_in_stderr(self):
        from app.modules.m06_labs_evaluator.code_sandbox import run
        result = run("python", "def foo(: pass", stdin="", timeout_s=5)
        assert result.exit_code != 0
        assert result.stderr or result.error

    def test_timeout_triggers(self):
        from app.modules.m06_labs_evaluator.code_sandbox import run
        result = run("python", "import time; time.sleep(60)", stdin="", timeout_s=1)
        assert result.timed_out is True

    def test_unsupported_language_returns_error(self):
        from app.modules.m06_labs_evaluator.code_sandbox import run, SandboxResult
        result = run("java", "System.out.println('hi');", stdin="", timeout_s=5)
        assert isinstance(result, SandboxResult)
        assert result.error is not None

    def test_output_non_zero_on_exception(self):
        from app.modules.m06_labs_evaluator.code_sandbox import run
        result = run("python", "raise ValueError('oops')", stdin="", timeout_s=5)
        assert result.exit_code != 0


# ===========================================================================
# 5 — Rubric scorer (pure functions + mocked LLM)
# ===========================================================================

class TestRubricScorerParsing:
    def _make_rubric(self):
        return [
            {"criterion_id": "c1", "name": "Correctness", "description": "Correct?", "max_marks": 50, "weight": 0.6},
            {"criterion_id": "c2", "name": "Clarity",     "description": "Clear?",   "max_marks": 50, "weight": 0.4},
        ]

    def test_parse_response_happy_path(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response
        raw = '[{"criterion_id":"c1","ai_score":40,"ai_justification":"Good."},{"criterion_id":"c2","ai_score":35,"ai_justification":"Clear."}]'
        scores = _parse_response(raw, self._make_rubric())
        assert len(scores) == 2
        c1 = next(s for s in scores if s.criterion_id == "c1")
        assert c1.ai_score == 40.0
        assert c1.ai_justification == "Good."

    def test_parse_response_clamps_to_max_marks(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response
        raw = '[{"criterion_id":"c1","ai_score":200,"ai_justification":"Over."},{"criterion_id":"c2","ai_score":10,"ai_justification":"Low."}]'
        scores = _parse_response(raw, self._make_rubric())
        c1 = next(s for s in scores if s.criterion_id == "c1")
        assert c1.ai_score <= 50

    def test_parse_response_fills_missing_criterion_with_zero(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response
        raw = '[{"criterion_id":"c1","ai_score":30,"ai_justification":"OK."}]'
        scores = _parse_response(raw, self._make_rubric())
        ids = {s.criterion_id for s in scores}
        assert "c1" in ids and "c2" in ids
        c2 = next(s for s in scores if s.criterion_id == "c2")
        assert c2.ai_score == 0.0

    def test_parse_response_raises_on_invalid_json(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response
        with pytest.raises(ValueError, match="not valid JSON"):
            _parse_response("NOT JSON", self._make_rubric())

    def test_weighted_total_calculation(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import _weighted_total, CriterionScore
        rubric = self._make_rubric()
        scores = [
            CriterionScore(criterion_id="c1", ai_score=40, ai_justification="", max_marks=50),
            CriterionScore(criterion_id="c2", ai_score=30, ai_justification="", max_marks=50),
        ]
        total = _weighted_total(scores, rubric)
        # 40*0.6 + 30*0.4 = 24 + 12 = 36
        assert abs(total - 36.0) < 0.01

    @pytest.mark.asyncio
    async def test_score_submission_empty_text_returns_zero(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import score_submission
        result = await score_submission(
            question="Explain gradient descent.",
            submission_text="",
            rubric=self._make_rubric(),
        )
        assert result.overall_ai_score == 0.0
        assert result.confidence_level == "LOW"

    @pytest.mark.asyncio
    async def test_score_submission_gemini_success(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import score_submission, RubricScoringResult
        mock_result = RubricScoringResult(
            criteria_scores=[],
            overall_ai_score=42.0,
            confidence_level="HIGH",
            ai_model="gemini-2.0-flash",
            prompt_hash="abc123",
        )
        with patch(
            "app.modules.m06_labs_evaluator.rubric_scorer._score_with_gemini",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await score_submission(
                question="Q", submission_text="My answer.", rubric=self._make_rubric()
            )
        assert result.overall_ai_score == 42.0

    @pytest.mark.asyncio
    async def test_score_submission_falls_back_to_groq(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import score_submission, RubricScoringResult
        groq_result = RubricScoringResult(
            criteria_scores=[],
            overall_ai_score=35.0,
            confidence_level="MEDIUM",
            ai_model="groq-llama",
            prompt_hash="def456",
        )
        with (
            patch(
                "app.modules.m06_labs_evaluator.rubric_scorer._score_with_gemini",
                new=AsyncMock(side_effect=Exception("resource_exhausted")),
            ),
            patch(
                "app.modules.m06_labs_evaluator.rubric_scorer._score_with_groq",
                new=AsyncMock(return_value=groq_result),
            ),
        ):
            result = await score_submission(
                question="Q", submission_text="My answer.", rubric=self._make_rubric()
            )
        assert result.overall_ai_score == 35.0

    @pytest.mark.asyncio
    async def test_score_submission_both_fail_returns_zeros(self):
        from app.modules.m06_labs_evaluator.rubric_scorer import score_submission
        with (
            patch(
                "app.modules.m06_labs_evaluator.rubric_scorer._score_with_gemini",
                new=AsyncMock(side_effect=Exception("fail")),
            ),
            patch(
                "app.modules.m06_labs_evaluator.rubric_scorer._score_with_groq",
                new=AsyncMock(side_effect=Exception("fail")),
            ),
        ):
            result = await score_submission(
                question="Q", submission_text="My answer.", rubric=self._make_rubric()
            )
        assert result.overall_ai_score == 0.0
        assert result.confidence_level == "LOW"


# ===========================================================================
# 6 — Service layer invariants
# ===========================================================================

class TestAssignmentServiceInvariants:

    @pytest.mark.asyncio
    async def test_create_code_assignment_requires_language(self):
        from app.modules.m06_labs_evaluator.service import AssignmentService, LabServiceError
        from app.modules.m06_labs_evaluator.schemas import AssignmentCreate

        mock_db = AsyncMock()
        payload = AssignmentCreate(
            title="Test",
            submission_type="CODE",
            language=None,   # missing — should fail
            rubric=[{
                "criterion_id": "c1", "name": "C", "description": "D",
                "max_marks": 100, "weight": 1.0,
            }],
        )
        with pytest.raises(LabServiceError) as exc_info:
            await AssignmentService.create(
                payload=payload,
                created_by_user_id=uuid.uuid4(),
                db=mock_db,
            )
        assert exc_info.value.code == "LANGUAGE_REQUIRED"

    @pytest.mark.asyncio
    async def test_update_published_assignment_raises(self):
        from app.modules.m06_labs_evaluator.service import AssignmentService, LabServiceError
        from app.modules.m06_labs_evaluator.schemas import AssignmentUpdate
        from app.modules.m06_labs_evaluator.models import LabAssignment, AssignmentStatus

        mock_db = AsyncMock()
        assignment = MagicMock(spec=LabAssignment)
        assignment.status = AssignmentStatus.PUBLISHED

        with patch(
            "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
            new=AsyncMock(return_value=assignment),
        ):
            with pytest.raises(LabServiceError) as exc_info:
                await AssignmentService.update(
                    assignment_id=uuid.uuid4(),
                    payload=AssignmentUpdate(title="New title"),
                    db=mock_db,
                )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_get_nonexistent_assignment_raises_not_found(self):
        from app.modules.m06_labs_evaluator.service import AssignmentService, LabServiceError

        mock_db = AsyncMock()

        with patch(
            "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(LabServiceError) as exc_info:
                await AssignmentService.get(
                    assignment_id=uuid.uuid4(),
                    db=mock_db,
                )
        assert exc_info.value.status_code == 404


class TestSubmissionServiceInvariants:
    @pytest.mark.asyncio
    async def test_submit_to_unpublished_assignment_raises(self):
        from app.modules.m06_labs_evaluator.service import SubmissionService, LabServiceError
        from app.modules.m06_labs_evaluator.models import LabAssignment, AssignmentStatus

        mock_db = AsyncMock()
        assignment = MagicMock(spec=LabAssignment)
        assignment.status = AssignmentStatus.DRAFT
        assignment.id = uuid.uuid4()
        assignment.deadline = None
        assignment.allow_late = False

        with patch(
            "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
            new=AsyncMock(return_value=assignment),
        ):
            with pytest.raises(LabServiceError) as exc_info:
                await SubmissionService.submit(
                    assignment_id=assignment.id,
                    student_user_id=uuid.uuid4(),
                    content_text="my answer",
                    tenant_id=uuid.uuid4(),
                    schema_name="test",
                    db=mock_db,
                )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "NOT_PUBLISHED"

    @pytest.mark.asyncio
    async def test_double_submission_raises(self):
        from app.modules.m06_labs_evaluator.service import SubmissionService, LabServiceError
        from app.modules.m06_labs_evaluator.models import LabAssignment, LabSubmission, AssignmentStatus

        mock_db = AsyncMock()
        assignment = MagicMock(spec=LabAssignment)
        assignment.status = AssignmentStatus.PUBLISHED
        assignment.id = uuid.uuid4()
        assignment.deadline = None
        assignment.allow_late = False

        existing_sub = MagicMock(spec=LabSubmission)

        with (
            patch(
                "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
                new=AsyncMock(return_value=assignment),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.SubmissionRepository.get_student_submission",
                new=AsyncMock(return_value=existing_sub),
            ),
        ):
            with pytest.raises(LabServiceError) as exc_info:
                await SubmissionService.submit(
                    assignment_id=assignment.id,
                    student_user_id=uuid.uuid4(),
                    content_text="my second answer",
                    tenant_id=uuid.uuid4(),
                    schema_name="test",
                    db=mock_db,
                )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "ALREADY_SUBMITTED"

    @pytest.mark.asyncio
    async def test_submit_code_assignment_creates_task_job(self):
        """Student submitting a CODE assignment must create a task_jobs row and
        dispatch the Celery task.  Regression for the task_name/task_type mismatch."""
        from app.modules.m06_labs_evaluator.service import SubmissionService
        from app.modules.m06_labs_evaluator.models import (
            AssignmentStatus, LabAssignment, LabSubmission, SubmissionType,
        )

        mock_db = AsyncMock()
        assignment = MagicMock(spec=LabAssignment)
        assignment.status = AssignmentStatus.PUBLISHED
        assignment.submission_type = SubmissionType.CODE
        assignment.id = uuid.uuid4()
        assignment.deadline = None
        assignment.allow_late = False

        submission = MagicMock(spec=LabSubmission)
        submission.id = uuid.uuid4()

        expected_job_id = uuid.uuid4()

        with (
            patch(
                "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
                new=AsyncMock(return_value=assignment),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.SubmissionRepository.get_student_submission",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.SubmissionRepository.create",
                new=AsyncMock(return_value=submission),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.SubmissionRepository.set_eval_job",
                new=AsyncMock(),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.TaskJobPublicRepository.create",
                new=AsyncMock(return_value=expected_job_id),
            ) as mock_task_create,
            patch(
                "app.workers.heavy.evaluate_lab_submission.evaluate_lab_submission.apply_async",
                new=MagicMock(),
            ) as mock_dispatch,
        ):
            result_submission, result_job_id = await SubmissionService.submit(
                assignment_id=assignment.id,
                student_user_id=uuid.uuid4(),
                content_text="print('hello')",
                tenant_id=uuid.uuid4(),
                schema_name="tenant_test",
                db=mock_db,
            )

        # Correct arguments passed to TaskJobPublicRepository.create
        call_kwargs = mock_task_create.call_args.kwargs
        assert "task_name" not in call_kwargs, "task_name is not a valid parameter — use task_type"
        assert call_kwargs["task_type"] == "evaluate_lab_submission"
        assert call_kwargs["queue_name"] == "heavy"
        assert "submission_id" in call_kwargs["payload"]

        # Return values are correct
        assert result_job_id == expected_job_id

        # Celery task was dispatched with the job_id
        dispatch_kwargs = mock_dispatch.call_args.kwargs["kwargs"]
        assert dispatch_kwargs["job_id"] == str(expected_job_id)


class TestGradeLedgerInvariant:
    """Grade ledger must never be written except via the ratify endpoint."""

    @pytest.mark.asyncio
    async def test_ratify_writes_grade_ledger(self):
        from app.modules.m06_labs_evaluator.service import ReviewService
        from app.modules.m06_labs_evaluator.models import LabSubmission, GradeLedger, LabEvaluation, SubmissionStatus

        mock_db = AsyncMock()
        student_id = uuid.uuid4()
        assignment_id = uuid.uuid4()

        submission = MagicMock(spec=LabSubmission)
        submission.id = uuid.uuid4()
        submission.assignment_id = assignment_id
        submission.student_user_id = student_id
        submission.status = SubmissionStatus.REVIEWED

        assignment = MagicMock()
        assignment.max_marks = 100
        assignment.rubric = []

        evaluation = MagicMock(spec=LabEvaluation)
        evaluation.overall_human_score = 80.0
        evaluation.overall_ai_score = 75.0

        ledger_entry = MagicMock(spec=GradeLedger)
        ledger_entry.id = uuid.uuid4()
        ledger_entry.final_score = 80.0

        with (
            patch(
                "app.modules.m06_labs_evaluator.repository.SubmissionRepository.get_by_id",
                new=AsyncMock(return_value=submission),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
                new=AsyncMock(return_value=assignment),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.EvaluationRepository.get_by_submission",
                new=AsyncMock(return_value=evaluation),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.GradeLedgerRepository.get_by_submission",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.GradeLedgerRepository.create",
                new=AsyncMock(return_value=ledger_entry),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.SubmissionRepository.set_status",
                new=AsyncMock(return_value=submission),
            ),
        ):
            result = await ReviewService.ratify(
                submission_id=submission.id,
                ratified_by_user_id=uuid.uuid4(),
                ratification_note="Good work",
                db=mock_db,
            )

        assert result is ledger_entry

    @pytest.mark.asyncio
    async def test_ratify_already_ratified_raises(self):
        from app.modules.m06_labs_evaluator.service import ReviewService, LabServiceError
        from app.modules.m06_labs_evaluator.models import LabSubmission, GradeLedger, SubmissionStatus

        mock_db = AsyncMock()
        submission = MagicMock(spec=LabSubmission)
        submission.id = uuid.uuid4()
        submission.status = SubmissionStatus.RATIFIED

        with (
            patch(
                "app.modules.m06_labs_evaluator.repository.SubmissionRepository.get_by_id",
                new=AsyncMock(return_value=submission),
            ),
        ):
            with pytest.raises(LabServiceError) as exc_info:
                await ReviewService.ratify(
                    submission_id=submission.id,
                    ratified_by_user_id=uuid.uuid4(),
                    db=mock_db,
                )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "ALREADY_RATIFIED"


# ===========================================================================
# 7 — Instructions field + publish guard
# ===========================================================================

class TestInstructionsAndPublishGuard:
    """Tests for the new instructions field and publish validation."""

    def test_assignment_create_schema_accepts_instructions(self):
        from app.modules.m06_labs_evaluator.schemas import AssignmentCreate
        payload = AssignmentCreate(
            title="Test",
            description="Describe a sorting algorithm.",
            instructions="Write a 500-word essay. Use APA citations.",
            submission_type="WRITTEN",
        )
        assert payload.instructions == "Write a 500-word essay. Use APA citations."

    def test_assignment_create_schema_instructions_optional(self):
        from app.modules.m06_labs_evaluator.schemas import AssignmentCreate
        payload = AssignmentCreate(title="Test", submission_type="WRITTEN")
        assert payload.instructions is None

    def test_assignment_update_schema_accepts_instructions(self):
        from app.modules.m06_labs_evaluator.schemas import AssignmentUpdate
        payload = AssignmentUpdate(instructions="Updated instructions text.")
        assert payload.instructions == "Updated instructions text."

    def test_assignment_response_schema_has_instructions_field(self):
        from app.modules.m06_labs_evaluator.schemas import AssignmentResponse
        fields = AssignmentResponse.model_fields
        assert "instructions" in fields

    def test_assignment_response_schema_has_course_fields(self):
        from app.modules.m06_labs_evaluator.schemas import AssignmentResponse
        fields = AssignmentResponse.model_fields
        assert "course_title" in fields
        assert "course_code" in fields

    @pytest.mark.asyncio
    async def test_publish_fails_when_description_is_empty(self):
        from app.modules.m06_labs_evaluator.service import AssignmentService, LabServiceError
        from app.modules.m06_labs_evaluator.models import LabAssignment, AssignmentStatus

        mock_db = AsyncMock()
        assignment = MagicMock(spec=LabAssignment)
        assignment.id = uuid.uuid4()
        assignment.status = AssignmentStatus.DRAFT
        assignment.description = ""          # empty problem statement
        assignment.rubric = [{"criterion_id": "c1", "name": "Q", "max_marks": 10, "weight": 1.0}]

        with patch(
            "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
            new=AsyncMock(return_value=assignment),
        ):
            with pytest.raises(LabServiceError) as exc_info:
                await AssignmentService.publish(assignment.id, db=mock_db)

        assert exc_info.value.code == "NO_PROBLEM_STATEMENT"

    @pytest.mark.asyncio
    async def test_publish_fails_when_description_is_none(self):
        from app.modules.m06_labs_evaluator.service import AssignmentService, LabServiceError
        from app.modules.m06_labs_evaluator.models import LabAssignment, AssignmentStatus

        mock_db = AsyncMock()
        assignment = MagicMock(spec=LabAssignment)
        assignment.id = uuid.uuid4()
        assignment.status = AssignmentStatus.DRAFT
        assignment.description = None        # no problem statement
        assignment.rubric = [{"criterion_id": "c1", "name": "Q", "max_marks": 10, "weight": 1.0}]

        with patch(
            "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
            new=AsyncMock(return_value=assignment),
        ):
            with pytest.raises(LabServiceError) as exc_info:
                await AssignmentService.publish(assignment.id, db=mock_db)

        assert exc_info.value.code == "NO_PROBLEM_STATEMENT"

    @pytest.mark.asyncio
    async def test_publish_succeeds_with_description_and_null_instructions(self):
        """instructions is optional — publish must not require it."""
        from app.modules.m06_labs_evaluator.service import AssignmentService
        from app.modules.m06_labs_evaluator.models import LabAssignment, AssignmentStatus

        mock_db = AsyncMock()
        published = MagicMock(spec=LabAssignment)
        published.status = AssignmentStatus.PUBLISHED
        published.max_marks = 10

        assignment = MagicMock(spec=LabAssignment)
        assignment.id = uuid.uuid4()
        assignment.status = AssignmentStatus.DRAFT
        assignment.description = "Implement a binary search tree."
        assignment.instructions = None       # absent — must not block publish
        assignment.rubric = [{"criterion_id": "c1", "name": "Q", "max_marks": 10, "weight": 1.0}]

        with (
            patch(
                "app.modules.m06_labs_evaluator.repository.AssignmentRepository.get_by_id",
                new=AsyncMock(return_value=assignment),
            ),
            patch(
                "app.modules.m06_labs_evaluator.repository.AssignmentRepository.publish",
                new=AsyncMock(return_value=published),
            ),
        ):
            result = await AssignmentService.publish(assignment.id, db=mock_db)

        assert result.status == AssignmentStatus.PUBLISHED
