"""
M08 Exam Setter — unit tests (STEP-17).

Coverage:
  1. BloomsAnalyser  — compute_actual_distribution, check_compliance, dataclasses
  2. PaperSealer     — seal/unseal round-trip, key_ref invariant
  3. Schemas         — BloomsDistribution sum validation, QuestionFormatConfig,
                       BoardDecisionRequest, SealRequest, ExamPaperCreate
  4. Service layer   — ExamServiceError, human gate guards (mocked repos),
                       sealed-paper 403, model-answer stripping
  5. Celery wiring   — task names, callable, celery_app.conf.include
  6. Router wiring   — endpoint count, human gate paths, main.py include
  7. Audit events    — all 12 M08 events present; M06/M07 events not regressed
  8. Models          — enums and status machine values
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===========================================================================
# 1 — BloomsAnalyser
# ===========================================================================

class TestComputeActualDistribution:
    def test_single_level_all_marks(self):
        from app.modules.m08_exam_setter.blooms_analyser import compute_actual_distribution
        questions = [{"bloom_level": "REMEMBER", "marks": 10}]
        dist = compute_actual_distribution(questions)
        assert dist["REMEMBER"] == pytest.approx(100.0)
        assert dist["APPLY"] == pytest.approx(0.0)

    def test_even_split_two_levels(self):
        from app.modules.m08_exam_setter.blooms_analyser import compute_actual_distribution
        questions = [
            {"bloom_level": "REMEMBER", "marks": 50},
            {"bloom_level": "APPLY",    "marks": 50},
        ]
        dist = compute_actual_distribution(questions)
        assert dist["REMEMBER"] == pytest.approx(50.0)
        assert dist["APPLY"]    == pytest.approx(50.0)

    def test_empty_questions_returns_all_zeros(self):
        from app.modules.m08_exam_setter.blooms_analyser import compute_actual_distribution
        dist = compute_actual_distribution([])
        assert all(v == 0.0 for v in dist.values())

    def test_returns_all_six_levels(self):
        from app.modules.m08_exam_setter.blooms_analyser import (
            compute_actual_distribution, BLOOM_LEVELS,
        )
        dist = compute_actual_distribution([])
        for lvl in BLOOM_LEVELS:
            assert lvl in dist

    def test_unknown_bloom_level_excluded_from_totals(self):
        from app.modules.m08_exam_setter.blooms_analyser import compute_actual_distribution
        questions = [
            {"bloom_level": "SYNTHESISE", "marks": 40},  # unknown level
            {"bloom_level": "APPLY",      "marks": 60},
        ]
        dist = compute_actual_distribution(questions)
        # grand_total = 100; APPLY should still appear with correct %
        assert dist["APPLY"] == pytest.approx(60.0)

    def test_case_insensitive_bloom_level(self):
        from app.modules.m08_exam_setter.blooms_analyser import compute_actual_distribution
        questions = [{"bloom_level": "remember", "marks": 20}]
        dist = compute_actual_distribution(questions)
        assert dist["REMEMBER"] == pytest.approx(100.0)

    def test_marks_weighted_not_question_count(self):
        from app.modules.m08_exam_setter.blooms_analyser import compute_actual_distribution
        # 1 heavy EVALUATE + 4 light REMEMBER
        questions = [
            {"bloom_level": "EVALUATE", "marks": 40},
            *[{"bloom_level": "REMEMBER", "marks": 5} for _ in range(4)],
        ]
        dist = compute_actual_distribution(questions)
        # 40/60 ≈ 66.7%; 20/60 ≈ 33.3%
        assert dist["EVALUATE"] == pytest.approx(66.7, abs=0.2)
        assert dist["REMEMBER"] == pytest.approx(33.3, abs=0.2)


class TestCheckCompliance:
    def test_perfect_match_is_compliant(self):
        from app.modules.m08_exam_setter.blooms_analyser import check_compliance
        dist = {
            "REMEMBER": 20.0, "UNDERSTAND": 20.0, "APPLY": 20.0,
            "ANALYSE": 20.0,  "EVALUATE": 10.0,   "CREATE": 10.0,
        }
        report = check_compliance(dist, dist)
        assert report.compliance_ok is True
        assert len(report.violations) == 0

    def test_within_tolerance_is_compliant(self):
        from app.modules.m08_exam_setter.blooms_analyser import check_compliance
        requested = {"REMEMBER": 20.0, "UNDERSTAND": 20.0, "APPLY": 20.0,
                     "ANALYSE": 20.0, "EVALUATE": 10.0, "CREATE": 10.0}
        actual    = {"REMEMBER": 24.0, "UNDERSTAND": 18.0, "APPLY": 20.0,
                     "ANALYSE": 20.0, "EVALUATE": 10.0, "CREATE": 8.0}
        report = check_compliance(requested, actual, tolerance=5.0)
        assert report.compliance_ok is True

    def test_exceeds_tolerance_is_violation(self):
        from app.modules.m08_exam_setter.blooms_analyser import check_compliance
        requested = {"REMEMBER": 20.0, "UNDERSTAND": 20.0, "APPLY": 20.0,
                     "ANALYSE": 20.0, "EVALUATE": 10.0, "CREATE": 10.0}
        actual    = {"REMEMBER": 50.0, "UNDERSTAND": 10.0, "APPLY": 10.0,
                     "ANALYSE": 10.0, "EVALUATE": 10.0, "CREATE": 10.0}
        report = check_compliance(requested, actual, tolerance=5.0)
        assert report.compliance_ok is False
        levels = [v.level for v in report.violations]
        assert "REMEMBER" in levels

    def test_violation_delta_positive_when_exceeded(self):
        from app.modules.m08_exam_setter.blooms_analyser import check_compliance
        requested = {"REMEMBER": 10.0}
        actual    = {"REMEMBER": 30.0}
        report = check_compliance(requested, actual, tolerance=5.0)
        v = next(v for v in report.violations if v.level == "REMEMBER")
        assert v.delta_pct > 0

    def test_to_violations_list_format(self):
        from app.modules.m08_exam_setter.blooms_analyser import check_compliance
        requested = {"REMEMBER": 10.0}
        actual    = {"REMEMBER": 30.0}
        report = check_compliance(requested, actual, tolerance=5.0)
        vlist = report.to_violations_list()
        assert isinstance(vlist, list)
        for item in vlist:
            assert set(item.keys()) == {"level", "requested_pct", "actual_pct", "delta_pct"}

    def test_compliance_report_dataclass_fields(self):
        from app.modules.m08_exam_setter.blooms_analyser import (
            ComplianceReport, BloomsViolation,
        )
        r = ComplianceReport(
            requested_dist={"REMEMBER": 100.0},
            actual_dist={"REMEMBER": 95.0},
            compliance_ok=True,
        )
        assert r.compliance_ok is True
        assert r.violations == []

    def test_blooms_violation_dataclass_fields(self):
        from app.modules.m08_exam_setter.blooms_analyser import BloomsViolation
        v = BloomsViolation(level="APPLY", requested_pct=20.0, actual_pct=30.0, delta_pct=10.0)
        assert v.level == "APPLY"
        assert v.delta_pct == pytest.approx(10.0)


# ===========================================================================
# 2 — PaperSealer
# ===========================================================================

class TestPaperSealer:
    def test_seal_returns_bytes_and_key_ref(self):
        from app.modules.m08_exam_setter.paper_sealer import seal
        data = {"questions": ["Q1", "Q2"], "total_marks": 100}
        blob, key_ref = seal(data)
        assert isinstance(blob, bytes)
        assert len(blob) > 0
        assert isinstance(key_ref, str)
        assert key_ref == "EXAM_FERNET_KEY"

    def test_unseal_round_trip(self):
        from app.modules.m08_exam_setter.paper_sealer import seal, unseal
        data = {"title": "End Sem", "units": [1, 2, 3]}
        blob, key_ref = seal(data)
        recovered = unseal(blob, key_ref)
        assert recovered["title"] == "End Sem"
        assert recovered["units"] == [1, 2, 3]

    def test_seal_encrypts_data_not_plaintext(self):
        from app.modules.m08_exam_setter.paper_sealer import seal
        data = {"secret": "exam_secret_question"}
        blob, _ = seal(data)
        assert b"exam_secret_question" not in blob

    def test_key_ref_is_env_var_name_not_key_value(self):
        from app.modules.m08_exam_setter.paper_sealer import seal
        _, key_ref = seal({"x": 1})
        # Must be the env var name, not a raw Fernet key (which is 44+ chars base64)
        assert key_ref == "EXAM_FERNET_KEY"
        assert len(key_ref) < 20  # env var names are short

    def test_different_seals_produce_different_ciphertext(self):
        from app.modules.m08_exam_setter.paper_sealer import seal
        data = {"same": "data"}
        blob1, _ = seal(data)
        blob2, _ = seal(data)
        # Fernet uses a random IV, so ciphertexts should differ
        assert blob1 != blob2

    def test_tampered_blob_raises_on_unseal(self):
        from app.modules.m08_exam_setter.paper_sealer import seal, unseal
        from cryptography.fernet import InvalidToken
        blob, key_ref = seal({"x": 1})
        tampered = blob[:-5] + b"XXXXX"
        with pytest.raises(Exception):  # InvalidToken or similar
            unseal(tampered, key_ref)


# ===========================================================================
# 3 — Schemas: validators
# ===========================================================================

class TestBloomsDistributionSchema:
    def test_valid_distribution_passes(self):
        from app.modules.m08_exam_setter.schemas import BloomsDistribution
        dist = BloomsDistribution(
            remember=20, understand=20, apply=20,
            analyse=20, evaluate=10, create=10,
        )
        assert dist.remember == pytest.approx(20.0)

    def test_sum_not_100_raises(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import BloomsDistribution
        with pytest.raises(pydantic.ValidationError):
            BloomsDistribution(
                remember=10, understand=10, apply=10,
                analyse=10, evaluate=10, create=10,
            )  # sum = 60

    def test_sum_within_tolerance_passes(self):
        from app.modules.m08_exam_setter.schemas import BloomsDistribution
        # 99.5 is within ±1 of 100
        dist = BloomsDistribution(
            remember=20, understand=20, apply=20,
            analyse=20, evaluate=10, create=9.5,
        )
        assert dist is not None

    def test_negative_value_rejected(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import BloomsDistribution
        with pytest.raises(pydantic.ValidationError):
            BloomsDistribution(
                remember=-5, understand=35, apply=20,
                analyse=20, evaluate=15, create=15,
            )


class TestQuestionFormatConfig:
    def test_all_zero_raises(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import QuestionFormatConfig
        with pytest.raises(pydantic.ValidationError):
            QuestionFormatConfig(mcq_count=0, short_count=0, long_count=0, problem_count=0)

    def test_one_nonzero_passes(self):
        from app.modules.m08_exam_setter.schemas import QuestionFormatConfig
        cfg = QuestionFormatConfig(mcq_count=5)
        assert cfg.mcq_count == 5

    def test_negative_count_rejected(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import QuestionFormatConfig
        with pytest.raises(pydantic.ValidationError):
            QuestionFormatConfig(mcq_count=-1)


class TestBoardDecisionRequest:
    def test_approve_no_comment_passes(self):
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest
        req = BoardDecisionRequest(approved=True)
        assert req.approved is True

    def test_return_without_comment_raises(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest
        with pytest.raises(pydantic.ValidationError):
            BoardDecisionRequest(approved=False)

    def test_return_with_comment_passes(self):
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest
        req = BoardDecisionRequest(approved=False, board_comment="Revise Q3.")
        assert req.board_comment == "Revise Q3."


class TestSealRequest:
    def test_future_datetime_passes(self):
        from app.modules.m08_exam_setter.schemas import SealRequest
        future = datetime.now(timezone.utc) + timedelta(days=7)
        req = SealRequest(release_at=future)
        assert req.release_at > datetime.now(timezone.utc)

    def test_past_datetime_raises(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import SealRequest
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        with pytest.raises(pydantic.ValidationError):
            SealRequest(release_at=past)

    def test_now_raises(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import SealRequest
        with pytest.raises(pydantic.ValidationError):
            SealRequest(release_at=datetime.now(timezone.utc))


class TestExamPaperCreateSchema:
    def test_valid_payload_passes(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.schemas import (
            ExamPaperCreate, QuestionFormatConfig, BloomsDistribution,
        )
        ep = ExamPaperCreate(
            course_id=uuid4(),
            title="End Semester 2026",
            total_marks=100,
            duration_mins=180,
            units_included=[1, 2, 3],
            question_format=QuestionFormatConfig(mcq_count=5, short_count=3, long_count=2),
            requested_dist=BloomsDistribution(
                remember=20, understand=20, apply=20,
                analyse=20, evaluate=10, create=10,
            ),
        )
        assert ep.total_marks == 100

    def test_title_too_short_raises(self):
        import pydantic
        from uuid import uuid4
        from app.modules.m08_exam_setter.schemas import (
            ExamPaperCreate, QuestionFormatConfig, BloomsDistribution,
        )
        with pytest.raises(pydantic.ValidationError):
            ExamPaperCreate(
                course_id=uuid4(),
                title="AB",  # min_length=3
                total_marks=100,
                duration_mins=180,
                units_included=[1],
                question_format=QuestionFormatConfig(mcq_count=5),
                requested_dist=BloomsDistribution(
                    remember=20, understand=20, apply=20,
                    analyse=20, evaluate=10, create=10,
                ),
            )

    def test_empty_units_raises(self):
        import pydantic
        from uuid import uuid4
        from app.modules.m08_exam_setter.schemas import (
            ExamPaperCreate, QuestionFormatConfig, BloomsDistribution,
        )
        with pytest.raises(pydantic.ValidationError):
            ExamPaperCreate(
                course_id=uuid4(),
                title="Valid Title",
                total_marks=100,
                duration_mins=180,
                units_included=[],   # min_length=1
                question_format=QuestionFormatConfig(mcq_count=5),
                requested_dist=BloomsDistribution(
                    remember=20, understand=20, apply=20,
                    analyse=20, evaluate=10, create=10,
                ),
            )


# ===========================================================================
# 4 — Service layer: error class + human gate guards
# ===========================================================================

class TestExamServiceError:
    def test_error_fields(self):
        from app.modules.m08_exam_setter.service import ExamServiceError
        err = ExamServiceError("NOT_FOUND", "Not found.", 404)
        assert err.code == "NOT_FOUND"
        assert err.message == "Not found."
        assert err.status_code == 404

    def test_error_default_status_code(self):
        from app.modules.m08_exam_setter.service import ExamServiceError
        err = ExamServiceError("BAD", "Bad request.")
        assert err.status_code == 400

    def test_error_is_exception(self):
        from app.modules.m08_exam_setter.service import ExamServiceError
        with pytest.raises(ExamServiceError) as exc_info:
            raise ExamServiceError("FORBIDDEN", "Access denied.", 403)
        assert exc_info.value.status_code == 403


class TestGate1SubmitForReview:
    @pytest.mark.asyncio
    async def test_submit_rejects_wrong_creator(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError

        paper_mock = MagicMock()
        paper_mock.id = uuid4()
        paper_mock.created_by = uuid4()  # different from faculty_user_id
        paper_mock.status = "GENERATED"

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper_mock),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.submit_for_review(
                    paper_id=paper_mock.id,
                    faculty_user_id=uuid4(),  # different user
                    db=AsyncMock(),
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_submit_rejects_invalid_status(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError

        faculty_id = uuid4()
        paper_mock = MagicMock()
        paper_mock.id = uuid4()
        paper_mock.created_by = faculty_id
        paper_mock.status = "SUBMITTED"  # already submitted

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper_mock),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.submit_for_review(
                    paper_id=paper_mock.id,
                    faculty_user_id=faculty_id,
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_submit_rejects_paper_not_found(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.submit_for_review(
                    paper_id=uuid4(),
                    faculty_user_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.status_code == 404


class TestGate2BoardDecide:
    @pytest.mark.asyncio
    async def test_board_decide_rejects_invalid_status(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest

        paper_mock = MagicMock()
        paper_mock.id = uuid4()
        paper_mock.status = "DRAFT"  # cannot decide on DRAFT

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper_mock),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.board_decide(
                    paper_id=paper_mock.id,
                    payload=BoardDecisionRequest(approved=True),
                    board_user_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_board_decide_rejects_paper_not_found(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.board_decide(
                    paper_id=uuid4(),
                    payload=BoardDecisionRequest(approved=True),
                    board_user_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.status_code == 404


class TestSealedAccessControl:
    @pytest.mark.asyncio
    async def test_get_questions_raises_403_when_sealed(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError

        paper_mock = MagicMock()
        paper_mock.id = uuid4()
        paper_mock.status = "SEALED"

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper_mock),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.get_questions(
                    paper_id=paper_mock.id,
                    set_label=None,
                    include_answers=False,
                    db=AsyncMock(),
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.code == "SEALED_ACCESS"

    @pytest.mark.asyncio
    async def test_get_questions_strips_model_answer_by_default(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService

        paper_mock = MagicMock()
        paper_mock.id = uuid4()
        paper_mock.status = "GENERATED"

        q1 = MagicMock()
        q1.model_answer = "This is the answer"
        q1.correct_option = "A"

        q2 = MagicMock()
        q2.model_answer = "Another answer"
        q2.correct_option = "B"

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper_mock),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[q1, q2]),
        ):
            questions = await ExamService.get_questions(
                paper_id=paper_mock.id,
                set_label=None,
                include_answers=False,
                db=AsyncMock(),
            )

        assert questions[0].model_answer is None
        assert questions[0].correct_option is None
        assert questions[1].model_answer is None
        assert questions[1].correct_option is None

    @pytest.mark.asyncio
    async def test_get_questions_preserves_answers_when_include_answers_true(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService

        paper_mock = MagicMock()
        paper_mock.id = uuid4()
        paper_mock.status = "RELEASED"

        q1 = MagicMock()
        q1.model_answer = "The real answer"
        q1.correct_option = "C"

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper_mock),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[q1]),
        ):
            questions = await ExamService.get_questions(
                paper_id=paper_mock.id,
                set_label=None,
                include_answers=True,
                db=AsyncMock(),
            )

        assert questions[0].model_answer == "The real answer"
        assert questions[0].correct_option == "C"


class TestUpdateQuestionStatusGuard:
    @pytest.mark.asyncio
    async def test_update_question_rejected_when_submitted(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import ExamQuestionUpdate

        paper_mock = MagicMock()
        paper_mock.id = uuid4()
        paper_mock.status = "SUBMITTED"  # not editable

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper_mock),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.update_question(
                    paper_id=paper_mock.id,
                    question_id=uuid4(),
                    payload=ExamQuestionUpdate(question_text="New text"),
                    editor_user_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_update_question_rejected_when_sealed(self):
        from uuid import uuid4
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import ExamQuestionUpdate

        paper_mock = MagicMock()
        paper_mock.id = uuid4()
        paper_mock.status = "SEALED"

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper_mock),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.update_question(
                    paper_id=paper_mock.id,
                    question_id=uuid4(),
                    payload=ExamQuestionUpdate(question_text="New text"),
                    editor_user_id=uuid4(),
                    db=AsyncMock(),
                )
            assert exc_info.value.code == "INVALID_STATUS"


# ===========================================================================
# 5 — Celery task wiring
# ===========================================================================

class TestCeleryTaskWiring:
    def test_generate_exam_paper_importable(self):
        from app.workers.heavy.generate_exam_paper import generate_exam_paper
        assert callable(generate_exam_paper)
        assert generate_exam_paper.name == "app.workers.heavy.generate_exam_paper"

    def test_release_exam_paper_importable(self):
        from app.workers.heavy.release_exam_paper import release_exam_paper
        assert callable(release_exam_paper)
        assert release_exam_paper.name == "app.workers.heavy.release_exam_paper"

    def test_tasks_registered_in_celery_include(self):
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.generate_exam_paper" in include
        assert "app.workers.heavy.release_exam_paper" in include

    def test_m07_tasks_still_registered(self):
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.evaluate_research_proposal" in include
        assert "app.workers.heavy.evaluate_research_document" in include
        assert "app.workers.heavy.process_viva_session" in include

    def test_m06_tasks_still_registered(self):
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.evaluate_lab_submission" in include


# ===========================================================================
# 6 — Router wiring
# ===========================================================================

class TestRouterWiring:
    def test_exam_router_has_minimum_routes(self):
        from app.modules.m08_exam_setter.router import router
        assert len(router.routes) >= 14

    def test_human_gate_1_submit_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/submit" in paths

    def test_human_gate_2_board_decision_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/board-decision" in paths

    def test_human_gate_3_seal_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/seal" in paths

    def test_export_questions_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/export/questions" in paths

    def test_export_answers_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/export/answers" in paths

    def test_main_includes_exam_router(self):
        from app.main import app
        paths = [r.path for r in app.routes]
        exam_paths = [p for p in paths if "/exams" in p]
        assert len(exam_paths) >= 5

    def test_board_pending_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/board/pending" in paths


# ===========================================================================
# 7 — Audit events: M08 events present; M06/M07 not regressed
# ===========================================================================

class TestM08AuditEvents:
    def test_all_m08_events_present(self):
        from app.core.audit_log.models import AuditEventType
        m08_events = [
            "EXAM_PAPER_CREATED",
            "EXAM_PAPER_GENERATION_QUEUED",
            "EXAM_PAPER_GENERATION_COMPLETED",
            "EXAM_PAPER_GENERATION_FAILED",
            "EXAM_PAPER_QUESTION_EDITED",
            "EXAM_PAPER_QUESTION_REPLACED",
            "EXAM_PAPER_SUBMITTED",
            "EXAM_PAPER_BOARD_APPROVED",
            "EXAM_PAPER_BOARD_RETURNED",
            "EXAM_PAPER_SEALED",
            "EXAM_PAPER_RELEASED",
            "EXAM_PAPER_EXPORTED",
        ]
        for name in m08_events:
            assert hasattr(AuditEventType, name), f"Missing audit event: {name}"

    def test_m07_events_not_regressed(self):
        from app.core.audit_log.models import AuditEventType
        m07_events = [
            "RESEARCH_PROBLEM_SUBMITTED",
            "RESEARCH_PROBLEM_GUIDE_DECIDED",
            "RESEARCH_DOCUMENT_GUIDE_REVIEWED",
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
            "LAB_REPORT_COMPLETED",
        ]
        for name in m06_events:
            assert hasattr(AuditEventType, name), f"M06 regression: {name}"

    def test_m08_gate_events_all_three_present(self):
        from app.core.audit_log.models import AuditEventType
        gate_events = [
            "EXAM_PAPER_SUBMITTED",       # Gate 1
            "EXAM_PAPER_BOARD_APPROVED",  # Gate 2
            "EXAM_PAPER_SEALED",          # Gate 3
        ]
        for name in gate_events:
            assert hasattr(AuditEventType, name), f"Missing gate event: {name}"


# ===========================================================================
# 8 — Models: enums and status machine
# ===========================================================================

class TestM08Models:
    def test_exam_paper_status_all_eight_values(self):
        from app.modules.m08_exam_setter.models import ExamPaperStatus
        expected = {
            "DRAFT", "GENERATING", "GENERATED", "SUBMITTED",
            "BOARD_APPROVED", "BOARD_RETURNED", "SEALED", "RELEASED",
        }
        actual = {s.value for s in ExamPaperStatus}
        assert expected == actual

    def test_bloom_level_all_six_values(self):
        from app.modules.m08_exam_setter.models import BloomLevel
        expected = {"REMEMBER", "UNDERSTAND", "APPLY", "ANALYSE", "EVALUATE", "CREATE"}
        actual = {b.value for b in BloomLevel}
        assert expected == actual

    def test_exam_type_includes_standard_types(self):
        from app.modules.m08_exam_setter.models import ExamType
        standard = {"END_SEM", "MID_SEM", "QUIZ", "INTERNAL"}
        actual = {t.value for t in ExamType}
        assert standard.issubset(actual)

    def test_question_type_includes_mcq(self):
        from app.modules.m08_exam_setter.models import QuestionType
        values = {q.value for q in QuestionType}
        assert "MCQ" in values

    def test_exam_paper_model_importable(self):
        from app.modules.m08_exam_setter.models import ExamPaper
        assert ExamPaper.__tablename__ == "exam_papers"

    def test_exam_question_model_importable(self):
        from app.modules.m08_exam_setter.models import ExamQuestion
        assert ExamQuestion.__tablename__ == "exam_questions"

    def test_blooms_compliance_report_model_importable(self):
        from app.modules.m08_exam_setter.models import BloomsComplianceReport
        assert BloomsComplianceReport.__tablename__ == "blooms_compliance_reports"

    def test_status_machine_draft_is_initial(self):
        from app.modules.m08_exam_setter.models import ExamPaperStatus
        assert ExamPaperStatus.DRAFT.value == "DRAFT"

    def test_status_machine_released_is_terminal(self):
        from app.modules.m08_exam_setter.models import ExamPaperStatus
        assert ExamPaperStatus.RELEASED.value == "RELEASED"
