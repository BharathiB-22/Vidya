"""
M07 Research Supervision — unit tests (STEP-15).

Coverage:
  1. Novelty search (novelty_search.py) — TF-IDF, cosine, graceful degradation
  2. Document eval (document_eval.py) — format compliance, score types
  3. Viva engine (viva_engine.py) — prompt builders, dataclasses
  4. Service layer invariants (service.py) — human gate guards, error class
  5. Schemas validation (schemas.py) — validators, field constraints
  6. Celery task wiring — task names, callable
  7. Router wiring — endpoint count, human gate routes
  8. Audit event types — all M07 events present
"""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===========================================================================
# 1 — Novelty search: TF-IDF + cosine
# ===========================================================================

class TestNoveltySearch:
    def test_tokenize_basic(self):
        from app.modules.m07_research_supervision.novelty_search import _tokenize
        tokens = _tokenize("Hello world hello")
        assert tokens.count("hello") == 2
        assert "world" in tokens

    def test_tokenize_removes_stopwords(self):
        from app.modules.m07_research_supervision.novelty_search import _tokenize
        tokens = _tokenize("the quick brown fox and a")
        assert "the" not in tokens
        assert "a" not in tokens
        assert "fox" in tokens

    def test_tf_scores_sum_to_one(self):
        from app.modules.m07_research_supervision.novelty_search import _tf
        tokens = ["a", "b", "a", "c"]
        tf = _tf(tokens)
        assert abs(sum(tf.values()) - 1.0) < 1e-6
        assert tf["a"] == pytest.approx(0.5)

    def test_cosine_identical_vectors_is_one(self):
        from app.modules.m07_research_supervision.novelty_search import _cosine
        v = {"x": 1.0, "y": 2.0}
        assert _cosine(v, v) == pytest.approx(1.0)

    def test_cosine_orthogonal_vectors_is_zero(self):
        from app.modules.m07_research_supervision.novelty_search import _cosine
        v1 = {"a": 1.0}
        v2 = {"b": 1.0}
        assert _cosine(v1, v2) == pytest.approx(0.0)

    def test_cosine_empty_vector_is_zero(self):
        from app.modules.m07_research_supervision.novelty_search import _cosine
        assert _cosine({}, {"a": 1.0}) == pytest.approx(0.0)

    def test_novelty_result_dataclass_fields(self):
        from app.modules.m07_research_supervision.novelty_search import NoveltyResult
        nr = NoveltyResult(
            novelty_score=0.8,
            max_similarity=0.2,
            papers=[],
            query_used="test query",
            error=None,
        )
        assert nr.novelty_score == 0.8
        assert nr.max_similarity == 0.2

    @patch("app.modules.m07_research_supervision.novelty_search.urllib.request.urlopen")
    def test_graceful_degradation_on_api_failure(self, mock_urlopen):
        from app.modules.m07_research_supervision.novelty_search import compute_novelty
        mock_urlopen.side_effect = OSError("Network error")
        result = compute_novelty("AI Research", "This is a test abstract.", ["Q1?"])
        assert result.novelty_score == pytest.approx(0.5)
        assert result.error is not None

    @patch("app.modules.m07_research_supervision.novelty_search.urllib.request.urlopen")
    def test_novelty_score_in_0_1_range_on_success(self, mock_urlopen):
        from app.modules.m07_research_supervision.novelty_search import compute_novelty
        # Simulate empty Atom feed response
        xml = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = xml
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = compute_novelty("Deep Learning", "Neural networks abstract.", ["How?"])
        assert 0.0 <= result.novelty_score <= 1.0


# ===========================================================================
# 2 — Document eval: format compliance
# ===========================================================================

class TestDocumentEval:
    def test_format_check_complete_document(self):
        from app.modules.m07_research_supervision.document_eval import _check_format
        # All 5 sections + 500+ words + 3+ citations
        text = (
            "Introduction " + "word " * 120 +
            "Literature review " + "word " * 120 +
            "Methodology " + "word " * 120 +
            "Objectives " + "word " * 120 +
            "References [1] Smith, J. [2] Jones, A. [3] Brown, K. " + "word " * 10
        )
        score, issues = _check_format(text)
        assert score == pytest.approx(1.0)
        assert len(issues) == 0

    def test_format_check_empty_document(self):
        from app.modules.m07_research_supervision.document_eval import _check_format
        score, issues = _check_format("")
        assert score < 0.5
        assert len(issues) > 0

    def test_format_check_missing_sections_penalised(self):
        from app.modules.m07_research_supervision.document_eval import _check_format
        text = "Introduction " + "word " * 600  # missing most sections
        score, issues = _check_format(text)
        assert score < 1.0

    def test_document_eval_result_dataclass(self):
        from app.modules.m07_research_supervision.document_eval import DocumentEvalResult
        r = DocumentEvalResult(
            plagiarism_score=0.1,
            ai_content_score=0.2,
            format_score=0.9,
            clarity_score=0.85,
            evaluation_report={"sections": []},
            ai_model="mock",
            prompt_hash="abc123",
        )
        assert r.format_score == pytest.approx(0.9)


# ===========================================================================
# 3 — Viva engine: prompt builders + dataclasses
# ===========================================================================

class TestVivaEngine:
    def test_build_questions_prompt_contains_count(self):
        from app.modules.m07_research_supervision.viva_engine import _build_questions_prompt
        prompt = _build_questions_prompt("Research on AI ethics.", 8)
        assert "8" in prompt

    def test_build_questions_prompt_contains_viva_keyword(self):
        from app.modules.m07_research_supervision.viva_engine import _build_questions_prompt
        prompt = _build_questions_prompt("Research on AI ethics.", 6)
        assert "viva" in prompt.lower()

    def test_build_followup_prompt_contains_probe_or_follow(self):
        from app.modules.m07_research_supervision.viva_engine import _build_followup_prompt
        prompt = _build_followup_prompt("What is your method?", "We used surveys.")
        assert any(kw in prompt.lower() for kw in ["follow", "probe", "elaborate", "question"])

    def test_build_eval_prompt_contains_scoring_criteria(self):
        from app.modules.m07_research_supervision.viva_engine import _build_eval_prompt
        prompt = _build_eval_prompt([{"question": "Q?", "response": "A."}])
        assert "coherence" in prompt
        assert "accuracy" in prompt

    def test_viva_question_dataclass(self):
        from app.modules.m07_research_supervision.viva_engine import VivaQuestion
        vq = VivaQuestion(id="q1", text="What?", source="base", based_on_qid=None, order=1)
        assert vq.id == "q1"
        assert vq.source == "base"
        assert vq.based_on_qid is None

    def test_response_eval_dataclass(self):
        from app.modules.m07_research_supervision.viva_engine import ResponseEval
        re = ResponseEval(
            question_id="q1",
            coherence=7.5,
            accuracy=8.0,
            depth=6.5,
            comment="Good depth.",
        )
        assert re.coherence == pytest.approx(7.5)
        assert re.depth == pytest.approx(6.5)

    def test_viva_evaluation_result_has_per_question(self):
        from app.modules.m07_research_supervision.viva_engine import VivaEvaluationResult, ResponseEval
        result = VivaEvaluationResult(
            per_question=[
                ResponseEval("q1", 7.0, 8.0, 6.0, "Good"),
            ],
            overall_score=7.0,
            ai_model="mock",
        )
        assert len(result.per_question) == 1
        assert result.overall_score == pytest.approx(7.0)


# ===========================================================================
# 4 — Service layer: error class + human gate guards
# ===========================================================================

class TestServiceErrorClass:
    def test_error_fields(self):
        from app.modules.m07_research_supervision.service import ResearchServiceError
        err = ResearchServiceError("NOT_FOUND", "Not found.", 404)
        assert err.code == "NOT_FOUND"
        assert err.message == "Not found."
        assert err.status_code == 404

    def test_error_default_status_code(self):
        from app.modules.m07_research_supervision.service import ResearchServiceError
        err = ResearchServiceError("BAD", "Bad request.")
        assert err.status_code == 400

    def test_error_is_exception(self):
        from app.modules.m07_research_supervision.service import ResearchServiceError
        with pytest.raises(ResearchServiceError) as exc_info:
            raise ResearchServiceError("FORBIDDEN", "Access denied.", 403)
        assert exc_info.value.status_code == 403


class TestProblemServiceGuideDecide:
    @pytest.mark.asyncio
    async def test_guide_decide_rejects_wrong_guide(self):
        from uuid import uuid4
        from app.modules.m07_research_supervision.service import ProblemService, ResearchServiceError
        from app.modules.m07_research_supervision.schemas import GuideDecisionRequest

        problem_mock = MagicMock()
        problem_mock.guide_user_id = uuid4()
        problem_mock.status = "PENDING_REVIEW"

        with patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.get_by_id",
            new=AsyncMock(return_value=problem_mock),
        ):
            with pytest.raises(ResearchServiceError) as exc_info:
                await ProblemService.guide_decide(
                    problem_id=problem_mock.guide_user_id,
                    payload=GuideDecisionRequest(decision="ACCEPT"),
                    guide_user_id=uuid4(),  # different user
                    db=AsyncMock(),
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_guide_decide_rejects_invalid_status(self):
        from uuid import uuid4
        from app.modules.m07_research_supervision.service import ProblemService, ResearchServiceError
        from app.modules.m07_research_supervision.schemas import GuideDecisionRequest

        guide_id = uuid4()
        problem_mock = MagicMock()
        problem_mock.id = uuid4()
        problem_mock.guide_user_id = guide_id
        problem_mock.status = "DRAFT"  # cannot decide on DRAFT

        with patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.get_by_id",
            new=AsyncMock(return_value=problem_mock),
        ):
            with pytest.raises(ResearchServiceError) as exc_info:
                await ProblemService.guide_decide(
                    problem_id=problem_mock.id,
                    payload=GuideDecisionRequest(decision="ACCEPT"),
                    guide_user_id=guide_id,
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"


class TestDocumentServiceGuideReview:
    @pytest.mark.asyncio
    async def test_guide_review_rejects_unevaluated_doc(self):
        from uuid import uuid4
        from app.modules.m07_research_supervision.service import DocumentService, ResearchServiceError
        from app.modules.m07_research_supervision.schemas import GuideDocumentReviewRequest

        guide_id = uuid4()
        doc_mock = MagicMock()
        doc_mock.id = uuid4()
        doc_mock.research_problem_id = uuid4()
        doc_mock.status = "SUBMITTED"  # not yet evaluated

        problem_mock = MagicMock()
        problem_mock.guide_user_id = guide_id

        with patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.get_by_id",
            new=AsyncMock(return_value=doc_mock),
        ), patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.get_by_id",
            new=AsyncMock(return_value=problem_mock),
        ):
            with pytest.raises(ResearchServiceError) as exc_info:
                await DocumentService.guide_review(
                    doc_id=doc_mock.id,
                    payload=GuideDocumentReviewRequest(decision="APPROVE"),
                    guide_user_id=guide_id,
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"


# ===========================================================================
# 5 — Schemas: validators
# ===========================================================================

class TestSchemas:
    def test_problem_create_requires_at_least_one_question(self):
        from uuid import uuid4
        from app.modules.m07_research_supervision.schemas import ProblemCreate
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ProblemCreate(
                guide_user_id=str(uuid4()),
                title="T",
                abstract="A",
                research_questions=[],
            )

    def test_problem_create_max_five_questions(self):
        from uuid import uuid4
        from app.modules.m07_research_supervision.schemas import ProblemCreate, ResearchQuestion
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ProblemCreate(
                guide_user_id=str(uuid4()),
                title="T",
                abstract="A",
                research_questions=[
                    ResearchQuestion(question=f"Q{i}?") for i in range(6)
                ],
            )

    def test_guide_decision_request_valid_decisions(self):
        from app.modules.m07_research_supervision.schemas import GuideDecisionRequest
        for d in ("ACCEPT", "REVISE", "REJECT"):
            req = GuideDecisionRequest(decision=d)
            assert req.decision == d

    def test_guide_decision_request_rejects_invalid(self):
        from app.modules.m07_research_supervision.schemas import GuideDecisionRequest
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            GuideDecisionRequest(decision="APPROVE")

    def test_guide_document_review_valid(self):
        from app.modules.m07_research_supervision.schemas import GuideDocumentReviewRequest
        r = GuideDocumentReviewRequest(decision="APPROVE", guide_comment="Looks good.")
        assert r.decision == "APPROVE"

    def test_viva_ratify_question_override_score_bounds(self):
        from app.modules.m07_research_supervision.schemas import QuestionScoreOverride
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            QuestionScoreOverride(question_id="q1", score_override=11.0)  # max is 10

    def test_research_question_accepts_short_text(self):
        """min_length=1 — any non-empty question string should be valid."""
        from app.modules.m07_research_supervision.schemas import ResearchQuestion
        q = ResearchQuestion(question="Why?")
        assert q.question == "Why?"

    def test_research_question_rejects_empty_string(self):
        from app.modules.m07_research_supervision.schemas import ResearchQuestion
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ResearchQuestion(question="")

    def test_problem_create_valid_with_short_question(self):
        """Proposal with a short (< 10 char) question should now validate."""
        from uuid import uuid4
        from app.modules.m07_research_supervision.schemas import ProblemCreate, ResearchQuestion
        payload = ProblemCreate(
            guide_user_id=str(uuid4()),
            title="My Research Title",
            abstract=None,
            research_questions=[ResearchQuestion(question="Why?")],
        )
        assert len(payload.research_questions) == 1


# ===========================================================================
# 9 — Guide validation in create_student_proposal
# ===========================================================================

class TestCreateStudentProposalValidation:
    @pytest.mark.asyncio
    async def test_invalid_guide_raises_clear_error(self):
        """Non-existent guide_user_id must raise INVALID_GUIDE, not 500."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.service import ProblemService, ResearchServiceError
        from app.modules.m07_research_supervision.schemas import ProblemCreate, ResearchQuestion

        payload = ProblemCreate(
            guide_user_id=str(uuid4()),
            title="My Research Title",
            abstract="A brief abstract for the proposal.",
            research_questions=[ResearchQuestion(question="What is the impact?")],
        )

        mock_db = AsyncMock(spec=AsyncSession)
        # Simulate: no user found for the given guide_user_id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ResearchServiceError) as exc_info:
            await ProblemService.create_student_proposal(
                payload,
                student_user_id=uuid4(),
                tenant_id=uuid4(),
                schema_name="tenant_test",
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_GUIDE"
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_wrong_role_guide_raises_clear_error(self):
        """User with role != GUIDE must raise INVALID_GUIDE."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.service import ProblemService, ResearchServiceError
        from app.modules.m07_research_supervision.schemas import ProblemCreate, ResearchQuestion
        from app.core.auth.models import TenantRole

        payload = ProblemCreate(
            guide_user_id=str(uuid4()),
            title="My Research Title",
            abstract="A brief abstract for the proposal.",
            research_questions=[ResearchQuestion(question="What is the impact?")],
        )

        # Simulate: user found but is a FACULTY, not a GUIDE
        fake_user = MagicMock()
        fake_user.role = TenantRole.FACULTY
        fake_user.is_active = True

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user
        mock_db.execute.return_value = mock_result

        with pytest.raises(ResearchServiceError) as exc_info:
            await ProblemService.create_student_proposal(
                payload,
                student_user_id=uuid4(),
                tenant_id=uuid4(),
                schema_name="tenant_test",
                db=mock_db,
            )
        assert exc_info.value.code == "INVALID_GUIDE"

    @pytest.mark.asyncio
    async def test_duplicate_proposal_raises_clear_error(self):
        """Existing active proposal with same guide must raise DUPLICATE_PROPOSAL."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, call
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.service import ProblemService, ResearchServiceError
        from app.modules.m07_research_supervision.schemas import ProblemCreate, ResearchQuestion
        from app.core.auth.models import TenantRole

        guide_id = uuid4()
        payload = ProblemCreate(
            guide_user_id=str(guide_id),
            title="My Research Title",
            abstract="A brief abstract for the proposal.",
            research_questions=[ResearchQuestion(question="What is the impact?")],
        )

        fake_guide = MagicMock()
        fake_guide.role = TenantRole.GUIDE
        fake_guide.is_active = True

        fake_duplicate = MagicMock()  # existing proposal

        mock_db = AsyncMock(spec=AsyncSession)
        # First execute → guide lookup; second → duplicate lookup
        guide_result = MagicMock()
        guide_result.scalar_one_or_none.return_value = fake_guide
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = fake_duplicate
        mock_db.execute.side_effect = [guide_result, dup_result]

        with pytest.raises(ResearchServiceError) as exc_info:
            await ProblemService.create_student_proposal(
                payload,
                student_user_id=uuid4(),
                tenant_id=uuid4(),
                schema_name="tenant_test",
                db=mock_db,
            )
        assert exc_info.value.code == "DUPLICATE_PROPOSAL"
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_successful_proposal_creation_returns_problem_and_job_id(self):
        """Happy path: valid guide + no duplicate → returns (problem, UUID job_id)."""
        from uuid import UUID, uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.service import ProblemService
        from app.modules.m07_research_supervision.schemas import ProblemCreate, ResearchQuestion
        from app.core.auth.models import TenantRole

        guide_id = uuid4()
        fake_job_id = uuid4()
        fake_problem = MagicMock()
        fake_problem.id = uuid4()

        payload = ProblemCreate(
            guide_user_id=str(guide_id),
            title="Valid Research Title",
            abstract="A valid abstract.",
            research_questions=[ResearchQuestion(question="What is the impact?")],
        )

        fake_guide = MagicMock()
        fake_guide.role = TenantRole.GUIDE
        fake_guide.is_active = True

        mock_db = AsyncMock(spec=AsyncSession)
        guide_result = MagicMock()
        guide_result.scalar_one_or_none.return_value = fake_guide
        mock_db.execute.return_value = guide_result

        mock_pub_db = AsyncMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_pub_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory = MagicMock(return_value=mock_session_ctx)

        with patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.find_active_by_student",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.create",
            new=AsyncMock(return_value=fake_problem),
        ), patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.set_eval_job",
            new=AsyncMock(),
        ), patch(
            "app.database.AsyncSessionLocal",
            mock_session_factory,
        ), patch(
            "app.modules.m07_research_supervision.service.TaskJobPublicRepository.create",
            new=AsyncMock(return_value=fake_job_id),
        ), patch(
            "app.workers.heavy.evaluate_research_proposal.evaluate_research_proposal.apply_async",
            new=MagicMock(),
        ):
            problem, job_id = await ProblemService.create_student_proposal(
                payload,
                student_user_id=uuid4(),
                tenant_id=uuid4(),
                schema_name="tenant_test",
                db=mock_db,
            )

        assert problem is fake_problem
        assert isinstance(job_id, UUID)
        assert job_id == fake_job_id


# ===========================================================================
# 5b — DocumentService.submit: task dispatch (BUG-009 regression)
# ===========================================================================

class TestDocumentServiceSubmitDispatch:
    """Regression tests for M07-BUG-009: evaluate_research_document not queued."""

    def _make_accepted_problem(self, student_id):
        from app.modules.m07_research_supervision.models import ProblemStatus
        problem = MagicMock()
        problem.id = __import__("uuid").uuid4()
        problem.student_user_id = student_id
        problem.status = ProblemStatus.ACCEPTED.value
        return problem

    @pytest.mark.asyncio
    async def test_submit_with_file_url_queues_evaluate_research_document(self):
        """When file_url is provided in POST, evaluate_research_document.apply_async
        must be called with job_id, document_id, schema_name, queue='celery-heavy'."""
        from uuid import UUID, uuid4
        from unittest.mock import AsyncMock, MagicMock, patch, call
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.service import DocumentService
        from app.modules.m07_research_supervision.schemas import DocumentSubmit

        student_id = uuid4()
        fake_doc_id = uuid4()
        fake_job_id = uuid4()

        fake_doc = MagicMock()
        fake_doc.id = fake_doc_id

        fake_problem = self._make_accepted_problem(student_id)

        payload = DocumentSubmit(
            research_problem_id=str(fake_problem.id),
            file_url="tenant_dsu/research/doc.pdf",
            file_name="doc.pdf",
        )

        mock_db = AsyncMock(spec=AsyncSession)
        mock_pub_db = AsyncMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_pub_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        apply_async_mock = MagicMock()

        with patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.get_by_id",
            new=AsyncMock(return_value=fake_problem),
        ), patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.next_version_for_problem",
            new=AsyncMock(return_value=1),
        ), patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.create",
            new=AsyncMock(return_value=fake_doc),
        ), patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.set_eval_job",
            new=AsyncMock(),
        ), patch(
            "app.database.AsyncSessionLocal",
            return_value=mock_session_ctx,
        ), patch(
            "app.modules.m07_research_supervision.service.TaskJobPublicRepository.create",
            new=AsyncMock(return_value=fake_job_id),
        ), patch(
            "app.workers.heavy.evaluate_research_document.evaluate_research_document.apply_async",
            apply_async_mock,
        ):
            doc, job_id = await DocumentService.submit(
                payload,
                student_user_id=student_id,
                tenant_id=uuid4(),
                schema_name="tenant_test",
                db=mock_db,
            )

        # Task MUST be queued
        apply_async_mock.assert_called_once()
        call_kwargs = apply_async_mock.call_args
        task_kwargs = call_kwargs.kwargs.get("kwargs") or call_kwargs.args[0] if call_kwargs.args else {}
        if not task_kwargs:
            task_kwargs = call_kwargs.kwargs.get("kwargs", {})
        assert str(fake_doc_id) == task_kwargs.get("document_id"), (
            "document_id must be the newly created document's UUID"
        )
        assert task_kwargs.get("schema_name") == "tenant_test"
        assert task_kwargs.get("job_id") == str(fake_job_id)
        # Must route to celery-heavy
        assert call_kwargs.kwargs.get("queue") == "celery-heavy", (
            "apply_async must specify queue='celery-heavy'"
        )
        assert job_id == fake_job_id

    @pytest.mark.asyncio
    async def test_submit_without_file_url_does_not_queue_task(self):
        """When file_url is None (two-step flow), no task is dispatched from submit().
        The task will be dispatched from update_file_url() after the PATCH upload."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.service import DocumentService
        from app.modules.m07_research_supervision.schemas import DocumentSubmit

        student_id = uuid4()
        fake_doc = MagicMock()
        fake_doc.id = uuid4()

        fake_problem = self._make_accepted_problem(student_id)

        payload = DocumentSubmit(
            research_problem_id=str(fake_problem.id),
            file_url=None,
            file_name=None,
        )

        mock_db = AsyncMock(spec=AsyncSession)
        apply_async_mock = MagicMock()

        with patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.get_by_id",
            new=AsyncMock(return_value=fake_problem),
        ), patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.next_version_for_problem",
            new=AsyncMock(return_value=1),
        ), patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.create",
            new=AsyncMock(return_value=fake_doc),
        ), patch(
            "app.workers.heavy.evaluate_research_document.evaluate_research_document.apply_async",
            apply_async_mock,
        ):
            doc, job_id = await DocumentService.submit(
                payload,
                student_user_id=student_id,
                tenant_id=uuid4(),
                schema_name="tenant_test",
                db=mock_db,
            )

        apply_async_mock.assert_not_called()
        assert job_id is None

    @pytest.mark.asyncio
    async def test_update_file_url_queues_evaluate_research_document(self):
        """PATCH /student/documents/{id}/file must dispatch evaluate_research_document
        so the two-step upload flow reaches the AI pipeline."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.service import DocumentService

        student_id = uuid4()
        doc_id = uuid4()
        fake_job_id = uuid4()

        fake_doc = MagicMock()
        fake_doc.id = doc_id
        fake_doc.student_user_id = student_id

        mock_db = AsyncMock(spec=AsyncSession)
        mock_pub_db = AsyncMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_pub_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        apply_async_mock = MagicMock()

        with patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.get_by_id",
            new=AsyncMock(return_value=fake_doc),
        ), patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.set_eval_job",
            new=AsyncMock(),
        ), patch(
            "app.database.AsyncSessionLocal",
            return_value=mock_session_ctx,
        ), patch(
            "app.modules.m07_research_supervision.service.TaskJobPublicRepository.create",
            new=AsyncMock(return_value=fake_job_id),
        ), patch(
            "app.workers.heavy.evaluate_research_document.evaluate_research_document.apply_async",
            apply_async_mock,
        ):
            await DocumentService.update_file_url(
                doc_id,
                file_url="tenant_dsu/research/doc.pdf",
                file_name="doc.pdf",
                student_user_id=student_id,
                tenant_id=uuid4(),
                schema_name="tenant_test",
                db=mock_db,
            )

        apply_async_mock.assert_called_once()
        call_kwargs = apply_async_mock.call_args
        task_kwargs = call_kwargs.kwargs.get("kwargs", {})
        assert task_kwargs.get("document_id") == str(doc_id)
        assert task_kwargs.get("schema_name") == "tenant_test"
        assert task_kwargs.get("job_id") == str(fake_job_id)
        assert call_kwargs.kwargs.get("queue") == "celery-heavy", (
            "apply_async must route to celery-heavy"
        )


# ===========================================================================
# 5c — VivaService.schedule: student_user_id derived from document (BUG-011)
# ===========================================================================

class TestVivaScheduleStudentIdDerivation:
    """Regression for M07-BUG-011: schedule_viva must succeed without
    student_user_id in the request payload by deriving it from the document."""

    def _make_mock_doc(self, student_id, status="APPROVED"):
        doc = MagicMock()
        doc.id = __import__("uuid").uuid4()
        doc.student_user_id = student_id
        doc.status = status
        return doc

    def _make_mock_problem(self, guide_id):
        from app.modules.m07_research_supervision.models import ProblemStatus
        problem = MagicMock()
        problem.id = __import__("uuid").uuid4()
        problem.guide_user_id = guide_id
        problem.status = ProblemStatus.ACCEPTED.value
        problem.title = "Test Research"
        problem.abstract = "Test abstract."
        return problem

    @pytest.mark.asyncio
    async def test_schedule_viva_without_student_user_id_uses_document(self):
        """Payload without student_user_id must succeed — student_user_id is
        taken from the approved document record."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.service import VivaService
        from app.modules.m07_research_supervision.schemas import VivaScheduleRequest

        guide_id = uuid4()
        student_id = uuid4()
        fake_problem = self._make_mock_problem(guide_id)
        fake_doc = self._make_mock_doc(student_id)

        fake_viva = MagicMock()
        fake_viva.id = uuid4()
        fake_viva.student_user_id = student_id

        mock_db = AsyncMock(spec=AsyncSession)

        payload = VivaScheduleRequest(
            research_problem_id=fake_problem.id,
            document_id=fake_doc.id,
            # student_user_id intentionally omitted
        )

        with patch(
            "app.modules.m07_research_supervision.service.ProblemRepository.get_by_id",
            new=AsyncMock(return_value=fake_problem),
        ), patch(
            "app.modules.m07_research_supervision.service.DocumentRepository.get_by_id",
            new=AsyncMock(return_value=fake_doc),
        ), patch(
            "app.modules.m07_research_supervision.viva_engine.generate_base_questions",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.modules.m07_research_supervision.service.VivaRepository.create",
            new=AsyncMock(return_value=fake_viva),
        ):
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()
            result = await VivaService.schedule(payload, guide_user_id=guide_id, db=mock_db)

        assert result is fake_viva
        assert result.student_user_id == student_id

    @pytest.mark.asyncio
    async def test_schedule_viva_schema_accepts_omitted_student_user_id(self):
        """VivaScheduleRequest must not raise ValidationError when
        student_user_id is absent from the payload."""
        from uuid import uuid4
        import pydantic
        from app.modules.m07_research_supervision.schemas import VivaScheduleRequest

        # Must not raise
        req = VivaScheduleRequest(
            research_problem_id=str(uuid4()),
            document_id=str(uuid4()),
        )
        assert req.student_user_id is None

    @pytest.mark.asyncio
    async def test_schedule_viva_schema_still_accepts_explicit_student_user_id(self):
        """Explicit student_user_id in payload must still be accepted (backward compat)."""
        from uuid import uuid4
        from app.modules.m07_research_supervision.schemas import VivaScheduleRequest

        student_id = uuid4()
        req = VivaScheduleRequest(
            research_problem_id=str(uuid4()),
            document_id=str(uuid4()),
            student_user_id=str(student_id),
        )
        assert req.student_user_id == student_id


# ===========================================================================
# 6 — Celery task wiring
# ===========================================================================

class TestCeleryTaskWiring:
    def test_evaluate_research_proposal_importable(self):
        from app.workers.heavy.evaluate_research_proposal import evaluate_research_proposal
        assert callable(evaluate_research_proposal)
        assert evaluate_research_proposal.name == "app.workers.heavy.evaluate_research_proposal"

    def test_evaluate_research_document_importable(self):
        from app.workers.heavy.evaluate_research_document import evaluate_research_document
        assert callable(evaluate_research_document)
        assert evaluate_research_document.name == "app.workers.heavy.evaluate_research_document"

    def test_process_viva_session_importable(self):
        from app.workers.heavy.process_viva_session import process_viva_session
        assert callable(process_viva_session)
        assert process_viva_session.name == "app.workers.heavy.process_viva_session"

    def test_tasks_registered_in_celery_include(self):
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.evaluate_research_proposal" in include
        assert "app.workers.heavy.evaluate_research_document" in include
        assert "app.workers.heavy.process_viva_session" in include


# ===========================================================================
# 7 — Router: endpoint count + human gates
# ===========================================================================

class TestRouterWiring:
    def test_router_has_minimum_routes(self):
        from app.modules.m07_research_supervision.router import router
        assert len(router.routes) >= 20

    def test_human_gate_endpoints_present(self):
        from app.modules.m07_research_supervision.router import router
        paths = {r.path for r in router.routes}
        assert "/problems/{problem_id}/decide" in paths
        assert "/documents/{doc_id}/review" in paths
        assert "/vivas/{viva_id}/ratify" in paths

    def test_main_includes_research_router(self):
        from app.main import app
        paths = [r.path for r in app.routes]
        research_paths = [p for p in paths if "/research" in p]
        assert len(research_paths) >= 5


# ===========================================================================
# 8 — Audit event types
# ===========================================================================

class TestM07AuditEvents:
    def test_all_m07_events_present(self):
        from app.core.audit_log.models import AuditEventType
        m07_events = [
            "RESEARCH_PROBLEM_SUBMITTED",
            "RESEARCH_PROBLEM_EVAL_QUEUED",
            "RESEARCH_PROBLEM_AI_EVALUATED",
            "RESEARCH_PROBLEM_GUIDE_DECIDED",
            "RESEARCH_PROBLEM_AI_GENERATED",
            "RESEARCH_DOCUMENT_SUBMITTED",
            "RESEARCH_DOCUMENT_EVAL_QUEUED",
            "RESEARCH_DOCUMENT_AI_EVALUATED",
            "RESEARCH_DOCUMENT_GUIDE_REVIEWED",
            "VIVA_SESSION_SCHEDULED",
            "VIVA_SESSION_STARTED",
            "VIVA_SESSION_COMPLETED",
            "VIVA_AI_EVALUATED",
            "VIVA_GUIDE_RATIFIED",
        ]
        for name in m07_events:
            assert hasattr(AuditEventType, name), f"Missing: {name}"

    def test_m06_events_not_regressed(self):
        from app.core.audit_log.models import AuditEventType
        for name in ["LAB_EVAL_COMPLETED", "LAB_SUBMISSION_RATIFIED", "LAB_REPORT_COMPLETED"]:
            assert hasattr(AuditEventType, name), f"M06 regression: {name}"


# ===========================================================================
# 9 — Worker/repo alignment: BUG-005 + BUG-006 regression suite
# ===========================================================================

class TestWorkerRepoSignatureAlignment:
    """Regression tests for M07-BUG-005 (param mismatch) and M07-BUG-006 (event-loop)."""

    # ── Static signature / source tests ───────────────────────────────────────

    def test_set_eval_result_has_no_new_status_param(self):
        """set_eval_result must not accept new_status — it hardcodes EVALUATED."""
        import inspect
        from app.modules.m07_research_supervision.repository import DocumentRepository
        sig = inspect.signature(DocumentRepository.set_eval_result)
        assert "new_status" not in sig.parameters

    def test_set_eval_result_has_all_worker_kwargs(self):
        """Every kwarg the worker passes to set_eval_result must be in the signature."""
        import inspect
        from app.modules.m07_research_supervision.repository import DocumentRepository
        sig = inspect.signature(DocumentRepository.set_eval_result)
        required = {
            "plagiarism_score", "ai_content_score", "format_score",
            "clarity_score", "evaluation_report", "ai_model", "prompt_hash", "db",
        }
        missing = required - set(sig.parameters)
        assert not missing, f"Missing params in set_eval_result: {missing}"

    def test_worker_source_does_not_pass_new_status_to_set_eval_result(self):
        """Worker call to set_eval_result must not include new_status= kwarg."""
        import inspect, re
        import app.workers.heavy.evaluate_research_document as mod
        src = inspect.getsource(mod._run_document_evaluation)
        call_block = re.search(r"set_eval_result\(.*?\)", src, re.DOTALL)
        assert call_block is not None, "set_eval_result call not found in worker source"
        assert "new_status" not in call_block.group(0)

    def test_worker_corpus_texts_built_as_tuples(self):
        """corpus_texts must be [(doc_id, text)] tuples, not plain strings."""
        import inspect
        import app.workers.heavy.evaluate_research_document as mod
        src = inspect.getsource(mod._run_document_evaluation)
        assert "(d.id," in src, (
            "corpus_texts list comprehension must yield (d.id, text) tuples"
        )

    def test_guide_review_no_spurious_new_status_column(self):
        """set_guide_review must not pass new_status= as a column to SQLAlchemy values()."""
        import inspect, re
        from app.modules.m07_research_supervision.repository import DocumentRepository
        src = inspect.getsource(DocumentRepository.set_guide_review)
        assert not re.search(r"new_status\s*=\s*new_status", src), (
            "set_guide_review must not use new_status= as a column name; "
            "the column is 'status', not 'new_status'"
        )

    # ── BUG-006: NullPool / no cached engine ──────────────────────────────────

    def test_no_cached_global_async_engine(self):
        """Worker must not have a module-level _async_engine — kills event-loop reuse."""
        import app.workers.heavy.evaluate_research_document as mod
        assert not hasattr(mod, "_async_engine"), (
            "Module-level _async_engine must not exist; use _make_async_engine() instead"
        )

    def test_worker_uses_nullpool(self):
        """_make_async_engine must pass poolclass=NullPool to avoid cross-loop errors."""
        from sqlalchemy.pool import NullPool
        from unittest.mock import patch, MagicMock
        import app.workers.heavy.evaluate_research_document as mod

        captured: dict = {}

        def spy_create(url, **kw):
            captured["poolclass"] = kw.get("poolclass")
            return MagicMock()

        with patch("sqlalchemy.ext.asyncio.create_async_engine", side_effect=spy_create):
            mod._make_async_engine("tenant_test")

        assert captured.get("poolclass") is NullPool, (
            "_make_async_engine must pass poolclass=NullPool"
        )

    def test_make_async_engine_returns_fresh_instance_each_call(self):
        """Each _make_async_engine() call must return a new engine, never a cached one."""
        from unittest.mock import patch, MagicMock
        import app.workers.heavy.evaluate_research_document as mod

        created: list = []

        def spy_create(url, **kw):
            e = MagicMock()
            created.append(e)
            return e

        with patch("sqlalchemy.ext.asyncio.create_async_engine", side_effect=spy_create):
            e1 = mod._make_async_engine("tenant_test")
            e2 = mod._make_async_engine("tenant_test")

        assert len(created) == 2, "_make_async_engine must create a new engine every call"
        assert e1 is not e2

    # ── BUG-007: tenant search_path via server_settings ───────────────────────

    def test_make_async_engine_passes_schema_in_server_settings(self):
        """search_path must reach asyncpg via server_settings, not just a SET statement.

        SQLAlchemy releases the connection after each session.commit(), so a
        one-time 'SET search_path' is lost.  server_settings is applied to
        every new connection created by asyncpg.
        """
        from unittest.mock import patch, MagicMock
        import app.workers.heavy.evaluate_research_document as mod

        captured: dict = {}

        def spy_create(url, **kw):
            captured.update(kw)
            return MagicMock()

        with patch("sqlalchemy.ext.asyncio.create_async_engine", side_effect=spy_create):
            mod._make_async_engine("tenant_myschema")

        connect_args = captured.get("connect_args", {})
        server_settings = connect_args.get("server_settings", {})
        assert "search_path" in server_settings, (
            "_make_async_engine must pass search_path via connect_args['server_settings']"
        )
        assert "tenant_myschema" in server_settings["search_path"], (
            "server_settings search_path must include the tenant schema name"
        )
        assert "public" in server_settings["search_path"], (
            "server_settings search_path must include 'public' as fallback"
        )

    def test_worker_source_sets_search_path_as_belt_and_suspenders(self):
        """Worker must also issue SET search_path inside the session as belt-and-suspenders."""
        import inspect
        import app.workers.heavy.evaluate_research_document as mod
        src = inspect.getsource(mod._run_document_evaluation)
        assert "SET search_path" in src, (
            "_run_document_evaluation must issue SET search_path inside the session "
            "as a belt-and-suspenders guard"
        )

    @pytest.mark.asyncio
    async def test_worker_raises_for_invalid_schema_name(self):
        """Empty or non-tenant schema_name must raise ValueError before any DB access."""
        from uuid import uuid4
        from app.workers.heavy.evaluate_research_document import _run_document_evaluation

        for bad_schema in ("", "public", "random_schema"):
            with pytest.raises(ValueError, match="schema_name"):
                await _run_document_evaluation(uuid4(), bad_schema)

    def test_eval_failed_audit_event_exists(self):
        """RESEARCH_DOCUMENT_EVAL_FAILED must be in AuditEventType."""
        from app.core.audit_log.models import AuditEventType
        assert hasattr(AuditEventType, "RESEARCH_DOCUMENT_EVAL_FAILED")

    # ── Repo-level async tests ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_set_eval_result_accepts_valid_call_without_new_status(self):
        """set_eval_result must accept the correct kwargs and not raise TypeError."""
        from uuid import uuid4
        from unittest.mock import AsyncMock
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.repository import DocumentRepository

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()
        await DocumentRepository.set_eval_result(
            uuid4(),
            plagiarism_score=0.1,
            ai_content_score=0.2,
            format_score=0.8,
            clarity_score=0.9,
            evaluation_report={"format_issues": []},
            ai_model="test-model",
            prompt_hash="abc123",
            db=mock_db,
        )
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_eval_result_rejected_with_new_status_kwarg(self):
        """Passing new_status= to set_eval_result must raise TypeError immediately."""
        from uuid import uuid4
        from unittest.mock import AsyncMock
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.modules.m07_research_supervision.repository import DocumentRepository

        mock_db = AsyncMock(spec=AsyncSession)
        with pytest.raises(TypeError, match="new_status"):
            await DocumentRepository.set_eval_result(
                uuid4(),
                plagiarism_score=0.1,
                ai_content_score=0.2,
                format_score=0.8,
                clarity_score=0.9,
                evaluation_report={},
                ai_model="m",
                prompt_hash="h",
                new_status="EVALUATED",
                db=mock_db,
            )

    # ── Worker failure-path end-to-end test ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_worker_resets_document_and_audits_on_evaluation_failure(self):
        """On failure: rollback → reset to SUBMITTED → audit EVAL_FAILED → dispose engine."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.modules.m07_research_supervision.models import DocumentStatus
        from app.core.audit_log.models import AuditEventType
        from app.workers.heavy.evaluate_research_document import _run_document_evaluation

        doc_id = uuid4()
        fake_doc = MagicMock()
        fake_doc.id = doc_id
        fake_doc.research_problem_id = uuid4()
        fake_doc.file_url = None
        fake_doc.file_name = None

        fake_problem = MagicMock()
        fake_problem.title = "Test"
        fake_problem.abstract = "Abstract"

        set_status_mock = AsyncMock()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        audit_mock = AsyncMock()

        with patch(
            "app.workers.heavy.evaluate_research_document._make_async_engine",
            return_value=mock_engine,
        ), patch(
            "sqlalchemy.ext.asyncio.AsyncSession",
            return_value=session_cm,
        ), patch(
            "app.modules.m07_research_supervision.repository.DocumentRepository.get_by_id",
            AsyncMock(return_value=fake_doc),
        ), patch(
            "app.modules.m07_research_supervision.repository.ProblemRepository.get_by_id",
            AsyncMock(return_value=fake_problem),
        ), patch(
            "app.modules.m07_research_supervision.repository.DocumentRepository.set_status",
            set_status_mock,
        ), patch(
            "app.modules.m07_research_supervision.repository.DocumentRepository.list_for_problem",
            AsyncMock(return_value=[]),
        ), patch(
            "app.modules.m07_research_supervision.document_eval.evaluate_document",
            AsyncMock(side_effect=RuntimeError("LLM timeout")),
        ), patch(
            "app.core.audit_log.service.AuditService.log",
            audit_mock,
        ):
            with pytest.raises(RuntimeError, match="LLM timeout"):
                await _run_document_evaluation(doc_id, "tenant_test")

        # Status: first call → EVALUATING, second call → SUBMITTED
        status_calls = [c.args[1] for c in set_status_mock.call_args_list]
        assert DocumentStatus.EVALUATING.value in status_calls
        assert DocumentStatus.SUBMITTED.value in status_calls

        # rollback must precede the SUBMITTED reset
        mock_session.rollback.assert_called_once()

        # engine.dispose() must run even on failure (try/finally)
        mock_engine.dispose.assert_called_once()

        # failure audit event must be emitted
        audit_event_args = [c.args[0] for c in audit_mock.call_args_list]
        assert AuditEventType.RESEARCH_DOCUMENT_EVAL_FAILED in audit_event_args


# ===========================================================================
# 10 — Worker success path (BUG-010 regression)
# ===========================================================================

class TestWorkerSuccessPath:
    """Verify the happy path of _run_document_evaluation (BUG-010)."""

    @pytest.mark.asyncio
    async def test_worker_sets_evaluated_and_returns_scores(self):
        """Happy path: worker runs evaluation, writes scores, sets EVALUATED status."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.workers.heavy.evaluate_research_document import _run_document_evaluation
        from app.modules.m07_research_supervision.models import DocumentStatus
        from app.modules.m07_research_supervision.document_eval import DocumentEvalResult
        from app.core.audit_log.models import AuditEventType

        doc_id = uuid4()

        fake_doc = MagicMock()
        fake_doc.id = doc_id
        fake_doc.research_problem_id = uuid4()
        fake_doc.file_url = "tenant_dsu/research/thesis.pdf"
        fake_doc.file_name = "thesis.pdf"

        fake_problem = MagicMock()
        fake_problem.title = "AI in Education"
        fake_problem.abstract = "This research investigates AI-assisted learning outcomes."

        fake_eval_result = DocumentEvalResult(
            plagiarism_score=0.05,
            ai_content_score=0.15,
            format_score=0.80,
            clarity_score=0.88,
            evaluation_report={
                "format_issues": [],
                "plagiarism_matches": [],
                "ai_highlights": [],
                "clarity_notes": "Well-structured research document.",
                "word_count": 512,
                "ai_scan": {
                    "probability": 0.15,
                    "confidence": 0.9,
                    "burstiness_score": 0.7,
                    "repetition_score": 0.05,
                    "vocab_richness_score": 0.82,
                },
            },
            ai_model="groq/llama-3.3-70b-versatile",
            prompt_hash="abcd1234",
        )

        set_status_mock = AsyncMock()
        set_eval_result_mock = AsyncMock()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        audit_mock = AsyncMock()

        with patch(
            "app.workers.heavy.evaluate_research_document._make_async_engine",
            return_value=mock_engine,
        ), patch(
            "sqlalchemy.ext.asyncio.AsyncSession",
            return_value=session_cm,
        ), patch(
            "app.modules.m07_research_supervision.repository.DocumentRepository.get_by_id",
            AsyncMock(return_value=fake_doc),
        ), patch(
            "app.modules.m07_research_supervision.repository.ProblemRepository.get_by_id",
            AsyncMock(return_value=fake_problem),
        ), patch(
            "app.modules.m07_research_supervision.repository.DocumentRepository.set_status",
            set_status_mock,
        ), patch(
            "app.modules.m07_research_supervision.repository.DocumentRepository.list_for_problem",
            AsyncMock(return_value=[]),
        ), patch(
            "app.modules.m07_research_supervision.repository.DocumentRepository.set_eval_result",
            set_eval_result_mock,
        ), patch(
            "app.modules.m07_research_supervision.document_eval.evaluate_document",
            AsyncMock(return_value=fake_eval_result),
        ), patch(
            "app.core.audit_log.service.AuditService.log",
            audit_mock,
        ):
            result = await _run_document_evaluation(doc_id, "tenant_test")

        # Status must be set to EVALUATING during processing
        status_calls = [c.args[1] for c in set_status_mock.call_args_list]
        assert DocumentStatus.EVALUATING.value in status_calls, (
            "Worker must set status EVALUATING before evaluation"
        )
        # Status must NOT be reverted to SUBMITTED (success path)
        assert DocumentStatus.SUBMITTED.value not in status_calls, (
            "Worker must NOT revert to SUBMITTED on success"
        )

        # set_eval_result must be called with all score fields
        set_eval_result_mock.assert_called_once()
        eval_kwargs = set_eval_result_mock.call_args.kwargs
        assert eval_kwargs["plagiarism_score"] == pytest.approx(0.05)
        assert eval_kwargs["ai_content_score"] == pytest.approx(0.15)
        assert eval_kwargs["format_score"] == pytest.approx(0.80)
        assert eval_kwargs["clarity_score"] == pytest.approx(0.88)
        assert eval_kwargs["ai_model"] == "groq/llama-3.3-70b-versatile"
        assert "format_issues" in eval_kwargs["evaluation_report"]
        assert "clarity_notes" in eval_kwargs["evaluation_report"]

        # Engine disposed after success
        mock_engine.dispose.assert_called_once()

        # No rollback on success path
        mock_session.rollback.assert_not_called()

        # Return dict contains all expected score keys
        assert result["document_id"] == str(doc_id)
        assert result["plagiarism_score"] == pytest.approx(0.05)
        assert result["ai_content_score"] == pytest.approx(0.15)
        assert result["format_score"] == pytest.approx(0.80)
        assert result["clarity_score"] == pytest.approx(0.88)

        # Success audit event emitted (not failure)
        audit_event_args = [c.args[0] for c in audit_mock.call_args_list]
        assert AuditEventType.RESEARCH_DOCUMENT_AI_EVALUATED in audit_event_args
        assert AuditEventType.RESEARCH_DOCUMENT_EVAL_FAILED not in audit_event_args

    def test_evaluation_report_structure_matches_frontend_types(self):
        """The evaluation_report dict shape from document_eval must match frontend EvaluationReport.

        Backend must produce: format_issues, plagiarism_matches, ai_highlights,
        clarity_notes, word_count, ai_scan — matching types/research.ts EvaluationReport.
        """
        import inspect
        import app.modules.m07_research_supervision.document_eval as mod
        src = inspect.getsource(mod.evaluate_document)

        # Fields the frontend EvaluationReport interface expects (from types/research.ts)
        expected_keys = [
            "format_issues",
            "plagiarism_matches",
            "ai_highlights",
            "clarity_notes",
            "word_count",
            "ai_scan",
        ]
        for key in expected_keys:
            assert f'"{key}"' in src, (
                f"evaluation_report must include key '{key}' to match frontend EvaluationReport type"
            )

    def test_evaluation_report_does_not_use_legacy_sections_key(self):
        """evaluation_report must NOT use 'sections' key — frontend type uses format_issues."""
        import inspect
        import app.modules.m07_research_supervision.document_eval as mod
        src = inspect.getsource(mod.evaluate_document)
        assert '"sections"' not in src, (
            "evaluation_report must not use 'sections' key — the frontend EvaluationReport "
            "type uses 'format_issues'. Using 'sections' causes a silent rendering mismatch."
        )
