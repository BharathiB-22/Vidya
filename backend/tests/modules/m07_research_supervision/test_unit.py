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
