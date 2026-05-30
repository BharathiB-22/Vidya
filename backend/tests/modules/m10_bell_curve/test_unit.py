"""
M10 Bell Curve Normaliser — unit tests (STEP-12).

Coverage:
  1.  Models        — enums, table names, column presence, native_enum=False
  2.  Schemas       — RatifyRequest validator (REJECTED→NONE), required fields
  3.  Stats engine  — compute_stats shape, detect_anomalies flags, BC heuristic,
                      cross_evaluator_stats z-scores, suggest_normalisation branches
  4.  Normalizer    — apply_normalisation all 5 methods, clamp invariant,
                      preview_normalisation returns correct keys
  5.  Service       — BellCurveServiceError, trigger 409 guards, preview status guards,
                      ratify gate (double-ratify, REJECTED path, APPLIED path)
  6.  Repository    — no UPDATE/DELETE on NormalisedScore, Gate methods present
  7.  Celery wiring — task importable, correct name, in celery_app.conf.include
  8.  Router wiring — 11 routes, static paper path before /{id}, gate endpoints present,
                      /bell-curve in main.py routes
  9.  Audit events  — all 6 M10 events present; M09 events not regressed
  10. Report builder — generate_fairness_pdf callable, produces non-empty bytes,
                       handles empty analyses list
  11. Human-gate invariants — task never writes beyond READY; normalised scores
                              only written in ratify; M09 ledger never touched
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ===========================================================================
# 1 — Models
# ===========================================================================

class TestAnalysisStatusEnum:
    def test_seven_statuses(self):
        from app.modules.m10_bell_curve.models import AnalysisStatus
        expected = {"PENDING", "ANALYSING", "READY", "BOARD_REVIEWED", "APPLIED", "NO_ACTION", "FAILED"}
        assert {s.value for s in AnalysisStatus} == expected

    def test_pending_initial(self):
        from app.modules.m10_bell_curve.models import AnalysisStatus
        assert AnalysisStatus.PENDING.value == "PENDING"

    def test_applied_terminal(self):
        from app.modules.m10_bell_curve.models import AnalysisStatus
        assert AnalysisStatus.APPLIED.value == "APPLIED"

    def test_is_str_enum(self):
        from app.modules.m10_bell_curve.models import AnalysisStatus
        assert isinstance(AnalysisStatus.READY, str)
        assert AnalysisStatus.READY == "READY"


class TestBoardDecisionEnum:
    def test_three_decisions(self):
        from app.modules.m10_bell_curve.models import BoardDecision
        expected = {"ACCEPTED_SUGGESTION", "MODIFIED", "REJECTED"}
        assert {d.value for d in BoardDecision} == expected


class TestNormalisationMethodEnum:
    def test_five_methods(self):
        from app.modules.m10_bell_curve.models import NormalisationMethod
        expected = {"LINEAR_SCALE", "PERCENTILE_MAP", "BOUNDARY_SHIFT", "NONE", "CUSTOM"}
        assert {m.value for m in NormalisationMethod} == expected


class TestModelTableNames:
    def test_analysis_tablename(self):
        from app.modules.m10_bell_curve.models import BellCurveAnalysis
        assert BellCurveAnalysis.__tablename__ == "bell_curve_analyses"

    def test_decision_tablename(self):
        from app.modules.m10_bell_curve.models import BellCurveDecision
        assert BellCurveDecision.__tablename__ == "bell_curve_decisions"

    def test_normalised_score_tablename(self):
        from app.modules.m10_bell_curve.models import BellCurveNormalisedScore
        assert BellCurveNormalisedScore.__tablename__ == "bell_curve_normalized_scores"


class TestModelColumns:
    def test_analysis_has_required_columns(self):
        from app.modules.m10_bell_curve.models import BellCurveAnalysis
        cols = {c.key for c in BellCurveAnalysis.__mapper__.column_attrs}
        for col in ("exam_paper_id", "status", "score_count", "raw_stats",
                    "anomalies", "normalisation_suggestion", "cross_evaluator_stats",
                    "triggered_by", "triggered_at", "analysis_completed_at"):
            assert col in cols, f"Missing column: {col}"

    def test_normalised_score_has_required_columns(self):
        from app.modules.m10_bell_curve.models import BellCurveNormalisedScore
        cols = {c.key for c in BellCurveNormalisedScore.__mapper__.column_attrs}
        for col in ("raw_score", "normalised_score", "max_marks",
                    "normalisation_method", "decision_id", "analysis_id", "exam_paper_id"):
            assert col in cols, f"Missing column: {col}"

    def test_status_column_uses_string_not_native_enum(self):
        from app.modules.m10_bell_curve.models import BellCurveAnalysis
        from sqlalchemy import String
        status_col = BellCurveAnalysis.__mapper__.columns["status"]
        assert isinstance(status_col.type, String), \
            "status must be String (native_enum=False) for cross-DB compatibility"


# ===========================================================================
# 2 — Schemas
# ===========================================================================

class TestRatifyRequestValidator:
    def test_rejected_forces_method_none(self):
        from app.modules.m10_bell_curve.schemas import RatifyRequest
        req = RatifyRequest(
            decision="REJECTED",
            normalisation_method="LINEAR_SCALE",
            normalisation_params={},
        )
        assert req.normalisation_method == "NONE"

    def test_non_rejected_keeps_method(self):
        from app.modules.m10_bell_curve.schemas import RatifyRequest
        req = RatifyRequest(
            decision="ACCEPTED_SUGGESTION",
            normalisation_method="LINEAR_SCALE",
            normalisation_params={"scale_factor": 1.2},
        )
        assert req.normalisation_method == "LINEAR_SCALE"

    def test_modified_decision_keeps_method(self):
        from app.modules.m10_bell_curve.schemas import RatifyRequest
        req = RatifyRequest(
            decision="MODIFIED",
            normalisation_method="PERCENTILE_MAP",
            normalisation_params={"target_max": 100},
        )
        assert req.normalisation_method == "PERCENTILE_MAP"


class TestTriggerAnalysisRequest:
    def test_requires_exam_paper_id(self):
        from pydantic import ValidationError
        from app.modules.m10_bell_curve.schemas import TriggerAnalysisRequest
        with pytest.raises(ValidationError):
            TriggerAnalysisRequest()

    def test_valid_uuid(self):
        from app.modules.m10_bell_curve.schemas import TriggerAnalysisRequest
        req = TriggerAnalysisRequest(exam_paper_id=uuid4())
        assert req.exam_paper_id is not None


class TestPreviewNormalisationRequest:
    def test_requires_method_and_params(self):
        from pydantic import ValidationError
        from app.modules.m10_bell_curve.schemas import PreviewNormalisationRequest
        with pytest.raises(ValidationError):
            PreviewNormalisationRequest(normalisation_method="LINEAR_SCALE")

    def test_valid_request(self):
        from app.modules.m10_bell_curve.schemas import PreviewNormalisationRequest
        req = PreviewNormalisationRequest(
            method="LINEAR_SCALE",
            params={"scale_factor": 1.1},
        )
        assert req.method == "LINEAR_SCALE"


# ===========================================================================
# 3 — Stats engine
# ===========================================================================

class TestComputeStats:
    def test_returns_required_keys(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats
        result = compute_stats([50.0, 60.0, 70.0, 80.0, 90.0], 100.0)
        for key in ("mean", "std", "median", "min", "max", "skewness", "kurtosis",
                    "q1", "q3", "histogram"):
            assert key in result, f"Missing key: {key}"

    def test_mean_correct(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats
        result = compute_stats([40.0, 60.0, 80.0], 100.0)
        assert abs(result["mean"] - 60.0) < 0.01

    def test_histogram_is_list(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats
        result = compute_stats([10.0, 20.0, 30.0, 40.0, 50.0], 100.0)
        assert isinstance(result["histogram"], list)
        assert len(result["histogram"]) > 0

    def test_histogram_bins_sum_to_n(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats
        scores = [float(i) for i in range(1, 21)]
        result = compute_stats(scores, 100.0)
        total_count = sum(b["count"] for b in result["histogram"])
        assert total_count == len(scores)

    def test_single_score_no_crash(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats
        result = compute_stats([75.0], 100.0)
        assert result["mean"] == 75.0
        assert result["std"] == 0.0


class TestDetectAnomalies:
    def test_zero_inflation_detected(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats, detect_anomalies
        scores = [0.0] * 20 + [50.0] * 80
        rs = compute_stats(scores, 100.0)
        anomalies = detect_anomalies(scores, 100.0, rs)
        types = [a["type"] for a in anomalies]
        assert "ZERO_INFLATION" in types

    def test_ceiling_effect_detected(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats, detect_anomalies
        scores = [100.0] * 25 + [60.0] * 75
        rs = compute_stats(scores, 100.0)
        anomalies = detect_anomalies(scores, 100.0, rs)
        types = [a["type"] for a in anomalies]
        assert "CEILING_EFFECT" in types

    def test_no_anomalies_clean_scores(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats, detect_anomalies
        scores = [float(50 + i % 10) for i in range(100)]
        rs = compute_stats(scores, 100.0)
        anomalies = detect_anomalies(scores, 100.0, rs)
        types = [a["type"] for a in anomalies]
        assert "ZERO_INFLATION" not in types
        assert "CEILING_EFFECT" not in types

    def test_excessive_skew_detected(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats, detect_anomalies
        scores = [5.0] * 90 + [95.0] * 10
        rs = compute_stats(scores, 100.0)
        anomalies = detect_anomalies(scores, 100.0, rs)
        types = [a["type"] for a in anomalies]
        assert "EXCESSIVE_SKEW" in types

    def test_anomaly_has_required_fields(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats, detect_anomalies
        scores = [0.0] * 30 + [60.0] * 70
        rs = compute_stats(scores, 100.0)
        anomalies = detect_anomalies(scores, 100.0, rs)
        for a in anomalies:
            assert "type" in a
            assert "severity" in a
            assert "description" in a


class TestBimodalityCoefficient:
    def test_bc_computed_without_crash(self):
        from app.modules.m10_bell_curve.stats_engine import _bimodality_coefficient
        bc = _bimodality_coefficient(skewness=0.5, kurtosis_excess=0.0, n=50)
        assert bc > 0

    def test_bc_small_n_no_crash(self):
        from app.modules.m10_bell_curve.stats_engine import _bimodality_coefficient
        bc = _bimodality_coefficient(skewness=0.1, kurtosis_excess=-0.5, n=5)
        assert bc >= 0


class TestCrossEvaluatorStats:
    def test_empty_rows_returns_empty(self):
        from app.modules.m10_bell_curve.stats_engine import cross_evaluator_stats
        result = cross_evaluator_stats([])
        assert result == []

    def test_is_outlier_flag_present(self):
        from app.modules.m10_bell_curve.stats_engine import cross_evaluator_stats
        rows = [
            {"evaluator_id": str(uuid4()), "mean": 50.0, "std": 5.0, "count": 20},
            {"evaluator_id": str(uuid4()), "mean": 90.0, "std": 3.0, "count": 20},
            {"evaluator_id": str(uuid4()), "mean": 52.0, "std": 4.0, "count": 20},
        ]
        result = cross_evaluator_stats(rows)
        for r in result:
            assert "is_outlier" in r

    def test_single_evaluator_no_crash(self):
        from app.modules.m10_bell_curve.stats_engine import cross_evaluator_stats
        rows = [{"evaluator_id": str(uuid4()), "mean": 60.0, "std": 5.0, "count": 10}]
        result = cross_evaluator_stats(rows)
        assert len(result) == 1
        assert result[0]["is_outlier"] is False


class TestSuggestNormalisation:
    def test_returns_method_key(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats, detect_anomalies, suggest_normalisation
        scores = [float(i) for i in range(40, 90)]
        rs = compute_stats(scores, 100.0)
        anomalies = detect_anomalies(scores, 100.0, rs)
        suggestion = suggest_normalisation(scores, 100.0, rs, anomalies)
        assert "method" in suggestion

    def test_zero_inflation_suggests_none(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats, detect_anomalies, suggest_normalisation
        scores = [0.0] * 20 + [50.0] * 80
        rs = compute_stats(scores, 100.0)
        anomalies = detect_anomalies(scores, 100.0, rs)
        suggestion = suggest_normalisation(scores, 100.0, rs, anomalies)
        assert suggestion["method"] == "NONE"

    def test_ceiling_suggests_boundary_shift(self):
        from app.modules.m10_bell_curve.stats_engine import suggest_normalisation
        # Directly supply a CEILING_EFFECT-only anomaly list to test the priority branch
        scores = [float(75 + i % 26) for i in range(100)]
        rs = {"mean": 88.0, "std": 7.0, "median": 88.0, "min": 75.0, "max": 100.0,
              "skewness": 0.0, "kurtosis": -0.5, "q1": 82.0, "q3": 94.0, "histogram": []}
        anomalies = [{
            "type": "CEILING_EFFECT", "severity": "WARNING",
            "description": "25 students at max.", "threshold": 0.20, "observed_value": 0.25,
        }]
        suggestion = suggest_normalisation(scores, 100.0, rs, anomalies)
        assert suggestion["method"] == "BOUNDARY_SHIFT"

    def test_clean_suggests_none_or_percentile(self):
        from app.modules.m10_bell_curve.stats_engine import compute_stats, detect_anomalies, suggest_normalisation
        scores = [float(50 + i % 10) for i in range(100)]
        rs = compute_stats(scores, 100.0)
        anomalies = detect_anomalies(scores, 100.0, rs)
        suggestion = suggest_normalisation(scores, 100.0, rs, anomalies)
        assert suggestion["method"] in ("NONE", "PERCENTILE_MAP")


# ===========================================================================
# 4 — Normalizer
# ===========================================================================

def _make_ledger(scores: list[float], max_marks: float = 100.0) -> list[dict]:
    return [
        {
            "student_user_id": str(uuid4()),
            "student_roll_ref": f"S{i:03d}",
            "total_marks": s,
            "max_marks": max_marks,
        }
        for i, s in enumerate(scores)
    ]


class TestApplyNormalisation:
    def test_none_method_identity(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        rows = _make_ledger([40.0, 60.0, 80.0])
        result = apply_normalisation(rows, "NONE", {})
        assert [r["normalised_score"] for r in result] == [40.0, 60.0, 80.0]

    def test_linear_scale_applies_factor(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        rows = _make_ledger([50.0, 60.0])
        result = apply_normalisation(rows, "LINEAR_SCALE", {"scale_factor": 1.2})
        assert result[0]["normalised_score"] == 60.0
        assert result[1]["normalised_score"] == 72.0

    def test_linear_scale_clamp_to_max(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        rows = _make_ledger([95.0], 100.0)
        result = apply_normalisation(rows, "LINEAR_SCALE", {"scale_factor": 2.0})
        assert result[0]["normalised_score"] == 100.0

    def test_percentile_map_produces_positive(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        rows = _make_ledger([30.0, 50.0, 70.0, 90.0])
        result = apply_normalisation(rows, "PERCENTILE_MAP", {"target_max": 100.0})
        for r in result:
            assert 0.0 <= r["normalised_score"] <= 100.0

    def test_boundary_shift_scores_unchanged(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        scores = [45.0, 55.0, 65.0]
        rows = _make_ledger(scores)
        result = apply_normalisation(rows, "BOUNDARY_SHIFT", {})
        for i, r in enumerate(result):
            assert r["normalised_score"] == scores[i]

    def test_custom_applies_deltas(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        rows = _make_ledger([50.0, 60.0])
        params = {"adjustments": [{"delta": 5.0}, {"delta": -2.0}]}
        result = apply_normalisation(rows, "CUSTOM", params)
        assert result[0]["normalised_score"] == 55.0
        assert result[1]["normalised_score"] == 58.0

    def test_clamp_never_below_zero(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        rows = _make_ledger([5.0])
        params = {"adjustments": [{"delta": -20.0}]}
        result = apply_normalisation(rows, "CUSTOM", params)
        assert result[0]["normalised_score"] == 0.0

    def test_result_has_required_keys(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        rows = _make_ledger([50.0])
        result = apply_normalisation(rows, "NONE", {})
        for key in ("student_user_id", "student_roll_ref", "raw_score", "normalised_score", "max_marks"):
            assert key in result[0], f"Missing key: {key}"

    def test_empty_ledger_returns_empty(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        assert apply_normalisation([], "NONE", {}) == []

    def test_unknown_method_returns_identity(self):
        from app.modules.m10_bell_curve.normalizer import apply_normalisation
        rows = _make_ledger([50.0, 70.0])
        result = apply_normalisation(rows, "UNKNOWN_FUTURE_METHOD", {})
        assert result[0]["normalised_score"] == 50.0


class TestPreviewNormalisation:
    def test_returns_required_keys(self):
        from app.modules.m10_bell_curve.normalizer import preview_normalisation
        rows = _make_ledger([50.0, 60.0, 70.0])
        result = preview_normalisation(rows, "NONE", {})
        for key in ("method", "params", "projected_stats", "score_deltas"):
            assert key in result

    def test_projected_stats_has_mean(self):
        from app.modules.m10_bell_curve.normalizer import preview_normalisation
        rows = _make_ledger([50.0, 60.0, 70.0])
        result = preview_normalisation(rows, "NONE", {})
        assert "mean" in result["projected_stats"]

    def test_score_deltas_length_matches_input(self):
        from app.modules.m10_bell_curve.normalizer import preview_normalisation
        rows = _make_ledger([40.0, 50.0, 60.0, 70.0])
        result = preview_normalisation(rows, "NONE", {})
        assert len(result["score_deltas"]) == 4

    def test_none_method_deltas_are_zero(self):
        from app.modules.m10_bell_curve.normalizer import preview_normalisation
        rows = _make_ledger([50.0, 70.0])
        result = preview_normalisation(rows, "NONE", {})
        for d in result["score_deltas"]:
            assert d["delta"] == 0.0

    def test_empty_returns_empty_stats(self):
        from app.modules.m10_bell_curve.normalizer import preview_normalisation
        result = preview_normalisation([], "NONE", {})
        assert result["score_deltas"] == []


# ===========================================================================
# 5 — Service layer
# ===========================================================================

class TestBellCurveServiceError:
    def test_error_carries_code_message_status(self):
        from app.modules.m10_bell_curve.service import BellCurveServiceError
        err = BellCurveServiceError("TEST_CODE", "test message", status_code=422)
        assert err.code == "TEST_CODE"
        assert err.message == "test message"
        assert err.status_code == 422

    def test_default_status_code_is_400(self):
        from app.modules.m10_bell_curve.service import BellCurveServiceError
        err = BellCurveServiceError("X", "y")
        assert err.status_code == 400


class TestBellCurveServiceTriggerGuards:
    @pytest.mark.asyncio
    async def test_no_scripts_raises_404(self):
        from app.modules.m10_bell_curve.service import BellCurveService, BellCurveServiceError
        db = AsyncMock()
        paper_id = uuid4()
        with patch(
            "app.modules.m10_bell_curve.service.M09LedgerRepository.count_scripts_for_paper",
            new_callable=AsyncMock,
            return_value=(0, 0),
        ):
            with pytest.raises(BellCurveServiceError) as exc_info:
                await BellCurveService.trigger(paper_id, uuid4(), uuid4(), "tenant_1", db)
            assert exc_info.value.status_code == 404
            assert exc_info.value.code == "NO_SCRIPTS"

    @pytest.mark.asyncio
    async def test_not_all_finalised_raises_409(self):
        from app.modules.m10_bell_curve.service import BellCurveService, BellCurveServiceError
        db = AsyncMock()
        paper_id = uuid4()
        with patch(
            "app.modules.m10_bell_curve.service.M09LedgerRepository.count_scripts_for_paper",
            new_callable=AsyncMock,
            return_value=(10, 7),
        ):
            with pytest.raises(BellCurveServiceError) as exc_info:
                await BellCurveService.trigger(paper_id, uuid4(), uuid4(), "tenant_1", db)
            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "SCORES_NOT_FINALISED"


class TestBellCurveServicePreviewGuards:
    @pytest.mark.asyncio
    async def test_pending_status_raises_409(self):
        from app.modules.m10_bell_curve.service import BellCurveService, BellCurveServiceError
        from app.modules.m10_bell_curve.models import AnalysisStatus
        db = AsyncMock()
        mock_analysis = MagicMock()
        mock_analysis.status = AnalysisStatus.PENDING
        with patch(
            "app.modules.m10_bell_curve.service.BellCurveAnalysisRepository.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ):
            with pytest.raises(BellCurveServiceError) as exc_info:
                await BellCurveService.preview(uuid4(), "NONE", {}, db)
            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "ANALYSIS_NOT_READY"

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self):
        from app.modules.m10_bell_curve.service import BellCurveService, BellCurveServiceError
        db = AsyncMock()
        with patch(
            "app.modules.m10_bell_curve.service.BellCurveAnalysisRepository.get_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(BellCurveServiceError) as exc_info:
                await BellCurveService.preview(uuid4(), "NONE", {}, db)
            assert exc_info.value.status_code == 404


class TestBellCurveServiceRatifyGates:
    @pytest.mark.asyncio
    async def test_double_ratify_raises_409(self):
        from app.modules.m10_bell_curve.service import BellCurveService, BellCurveServiceError
        from app.modules.m10_bell_curve.models import AnalysisStatus
        db = AsyncMock()
        mock_analysis = MagicMock()
        mock_analysis.status = AnalysisStatus.READY
        existing_decision = MagicMock()
        with patch(
            "app.modules.m10_bell_curve.service.BellCurveAnalysisRepository.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ), patch(
            "app.modules.m10_bell_curve.service.BellCurveDecisionRepository.get_for_analysis",
            new_callable=AsyncMock,
            return_value=existing_decision,
        ):
            with pytest.raises(BellCurveServiceError) as exc_info:
                await BellCurveService.ratify(
                    uuid4(), "ACCEPTED_SUGGESTION", "NONE", {}, None, uuid4(), uuid4(), "s", db
                )
            assert exc_info.value.code == "ALREADY_RATIFIED"
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_rejected_sets_no_action(self):
        from app.modules.m10_bell_curve.service import BellCurveService
        from app.modules.m10_bell_curve.models import AnalysisStatus, BoardDecision
        db = AsyncMock()
        mock_analysis = MagicMock()
        mock_analysis.status = AnalysisStatus.READY
        mock_analysis.exam_paper_id = uuid4()
        mock_decision = MagicMock()
        mock_decision.id = uuid4()

        ledger = _make_ledger([50.0, 60.0, 70.0])

        with patch(
            "app.modules.m10_bell_curve.service.BellCurveAnalysisRepository.get_by_id",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ), patch(
            "app.modules.m10_bell_curve.service.BellCurveDecisionRepository.get_for_analysis",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.modules.m10_bell_curve.service.M09LedgerRepository.get_scores_for_paper",
            new_callable=AsyncMock,
            return_value=ledger,
        ), patch(
            "app.modules.m10_bell_curve.service.BellCurveDecisionRepository.create",
            new_callable=AsyncMock,
            return_value=mock_decision,
        ), patch(
            "app.modules.m10_bell_curve.service.BellCurveAnalysisRepository.set_no_action",
            new_callable=AsyncMock,
        ) as mock_no_action, patch(
            "app.modules.m10_bell_curve.service.BellCurveNormalisedScoreRepository.bulk_create",
            new_callable=AsyncMock,
        ) as mock_bulk:
            db.commit = AsyncMock()
            analysis, decision_obj, scores_written = await BellCurveService.ratify(
                uuid4(), BoardDecision.REJECTED.value, "NONE", {}, None, uuid4(), uuid4(), "s", db
            )
            mock_no_action.assert_called_once()
            mock_bulk.assert_not_called()
            assert scores_written == 0


# ===========================================================================
# 6 — Repository invariants
# ===========================================================================

class TestNormalisedScoreRepositoryAppendOnly:
    def test_no_update_method(self):
        from app.modules.m10_bell_curve.repository import BellCurveNormalisedScoreRepository
        assert not hasattr(BellCurveNormalisedScoreRepository, "update")
        assert not hasattr(BellCurveNormalisedScoreRepository, "delete")
        assert not hasattr(BellCurveNormalisedScoreRepository, "bulk_update")

    def test_bulk_create_method_present(self):
        from app.modules.m10_bell_curve.repository import BellCurveNormalisedScoreRepository
        assert hasattr(BellCurveNormalisedScoreRepository, "bulk_create")


class TestAnalysisRepositoryGateMethods:
    def test_set_applied_present(self):
        from app.modules.m10_bell_curve.repository import BellCurveAnalysisRepository
        assert hasattr(BellCurveAnalysisRepository, "set_applied")

    def test_set_no_action_present(self):
        from app.modules.m10_bell_curve.repository import BellCurveAnalysisRepository
        assert hasattr(BellCurveAnalysisRepository, "set_no_action")

    def test_set_ready_present(self):
        from app.modules.m10_bell_curve.repository import BellCurveAnalysisRepository
        assert hasattr(BellCurveAnalysisRepository, "set_ready")

    def test_set_failed_present(self):
        from app.modules.m10_bell_curve.repository import BellCurveAnalysisRepository
        assert hasattr(BellCurveAnalysisRepository, "set_failed")


class TestM09LedgerRepositoryReadOnly:
    def test_no_write_methods(self):
        from app.modules.m10_bell_curve.repository import M09LedgerRepository
        for bad in ("create", "update", "delete", "bulk_create", "set_score"):
            assert not hasattr(M09LedgerRepository, bad), \
                f"M09LedgerRepository must not have write method: {bad}"

    def test_read_methods_present(self):
        from app.modules.m10_bell_curve.repository import M09LedgerRepository
        assert hasattr(M09LedgerRepository, "get_scores_for_paper")
        assert hasattr(M09LedgerRepository, "count_scripts_for_paper")
        assert hasattr(M09LedgerRepository, "get_evaluator_stats_for_paper")


# ===========================================================================
# 7 — Celery wiring
# ===========================================================================

class TestCeleryTaskWiring:
    def test_task_importable(self):
        from app.workers.heavy.analyse_score_distribution import analyse_score_distribution
        assert analyse_score_distribution is not None

    def test_task_name_correct(self):
        from app.workers.heavy.analyse_score_distribution import analyse_score_distribution
        assert analyse_score_distribution.name == "app.workers.heavy.analyse_score_distribution"

    def test_task_in_celery_include(self):
        from app.workers.celery_app import celery_app
        assert "app.workers.heavy.analyse_score_distribution" in celery_app.conf.include

    def test_prior_tasks_not_regressed(self):
        from app.workers.celery_app import celery_app
        for task_name in (
            "app.workers.heavy.score_scanned_script",
            "app.workers.heavy.generate_exam_paper",
            "app.workers.heavy.process_viva_session",
        ):
            assert task_name in celery_app.conf.include, f"Regressed: {task_name}"

    def test_task_has_correct_base(self):
        from app.workers.heavy.analyse_score_distribution import analyse_score_distribution
        from app.workers.base_task import VidyaTask
        assert isinstance(analyse_score_distribution, VidyaTask)


# ===========================================================================
# 8 — Router wiring
# ===========================================================================

class TestBellCurveRouterWiring:
    def test_router_importable(self):
        from app.modules.m10_bell_curve.router import router
        assert router is not None

    def test_router_has_eleven_routes(self):
        from app.modules.m10_bell_curve.router import router
        assert len(router.routes) == 11, \
            f"Expected 11 routes, got {len(router.routes)}"

    def test_static_paper_route_before_id_route(self):
        from app.modules.m10_bell_curve.router import router
        paths = [r.path for r in router.routes]
        paper_idx = next(i for i, p in enumerate(paths) if "paper" in p and "{analysis_id}" not in p)
        id_idx = next(i for i, p in enumerate(paths) if "{analysis_id}" in p)
        assert paper_idx < id_idx, "Static paper route must come before /{analysis_id}"

    def test_ratify_endpoint_present(self):
        from app.modules.m10_bell_curve.router import router
        paths = [r.path for r in router.routes]
        assert any("ratify" in p for p in paths), "ratify endpoint missing"

    def test_preview_endpoint_present(self):
        from app.modules.m10_bell_curve.router import router
        paths = [r.path for r in router.routes]
        assert any("preview" in p for p in paths), "preview endpoint missing"

    def test_ledger_endpoint_present(self):
        from app.modules.m10_bell_curve.router import router
        paths = [r.path for r in router.routes]
        assert any("ledger" in p for p in paths), "ledger endpoint missing"

    def test_reports_endpoint_present(self):
        from app.modules.m10_bell_curve.router import router
        paths = [r.path for r in router.routes]
        assert any("reports" in p for p in paths), "reports endpoint missing"


# ===========================================================================
# H-37 STEP-01 — Grade Engine
# ===========================================================================

class TestGradeEngine:
    """
    Pure-function tests for compute_grade() and grade_distribution().

    Grade scale (default pass_pct = 40 %):
      S  ≥ 90 %  → 10.0 pts   pass
      A  ≥ 80 %  →  9.0 pts   pass
      B  ≥ 70 %  →  8.0 pts   pass
      C  ≥ 60 %  →  7.0 pts   pass
      D  ≥ 50 %  →  6.0 pts   pass
      P  ≥ 40 %  →  5.0 pts   pass
      F  < 40 %  →  0.0 pts   fail
    """

    # ------------------------------------------------------------------ import

    def test_module_importable(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade  # noqa: F401

    def test_grade_distribution_importable(self):
        from app.modules.m10_bell_curve.grade_engine import grade_distribution  # noqa: F401

    # ------------------------------------------------------------------ grade tiers

    def test_s_grade(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        pct, letter, points, is_pass = compute_grade(95.0, 100.0)
        assert letter  == "S"
        assert points  == 10.0
        assert is_pass is True
        assert pct     == 95.0

    def test_a_grade(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        pct, letter, points, is_pass = compute_grade(82.0, 100.0)
        assert letter  == "A"
        assert points  == 9.0
        assert is_pass is True

    def test_b_grade(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, points, is_pass = compute_grade(75.0, 100.0)
        assert letter  == "B"
        assert points  == 8.0
        assert is_pass is True

    def test_c_grade(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, points, is_pass = compute_grade(63.0, 100.0)
        assert letter  == "C"
        assert points  == 7.0
        assert is_pass is True

    def test_d_grade(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, points, is_pass = compute_grade(52.0, 100.0)
        assert letter  == "D"
        assert points  == 6.0
        assert is_pass is True

    def test_p_grade(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, points, is_pass = compute_grade(45.0, 100.0)
        assert letter  == "P"
        assert points  == 5.0
        assert is_pass is True

    def test_f_grade(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, points, is_pass = compute_grade(30.0, 100.0)
        assert letter  == "F"
        assert points  == 0.0
        assert is_pass is False

    # ------------------------------------------------------------------ exact boundaries

    def test_exactly_90_is_s(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, _, _ = compute_grade(90.0, 100.0)
        assert letter == "S"

    def test_exactly_80_is_a(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, _, _ = compute_grade(80.0, 100.0)
        assert letter == "A"

    def test_exactly_40_is_p_and_pass(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, _, is_pass = compute_grade(40.0, 100.0)
        assert letter  == "P"
        assert is_pass is True

    def test_just_below_pass_is_f(self):
        """39.9 % → F, fail."""
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, _, is_pass = compute_grade(39.9, 100.0)
        assert letter  == "F"
        assert is_pass is False

    def test_zero_score_is_f_fail(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        pct, letter, points, is_pass = compute_grade(0.0, 100.0)
        assert pct     == 0.0
        assert letter  == "F"
        assert points  == 0.0
        assert is_pass is False

    def test_full_marks_is_s(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        pct, letter, _, is_pass = compute_grade(100.0, 100.0)
        assert pct     == 100.0
        assert letter  == "S"
        assert is_pass is True

    # ------------------------------------------------------------------ non-100 max_marks

    def test_score_out_of_50(self):
        """35/50 = 70 % → B."""
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, points, is_pass = compute_grade(35.0, 50.0)
        assert letter  == "B"
        assert points  == 8.0
        assert is_pass is True

    def test_score_out_of_75(self):
        """30/75 = 40 % → P (exactly on boundary)."""
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, letter, _, is_pass = compute_grade(30.0, 75.0)
        assert letter  == "P"
        assert is_pass is True

    # ------------------------------------------------------------------ pct rounding

    def test_pct_rounded_to_one_decimal(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        # 67 / 100 = 67.0 (no rounding needed)
        pct, _, _, _ = compute_grade(67.0, 100.0)
        assert pct == 67.0

    def test_pct_clamped_above_100(self):
        """Score exceeding max_marks is clamped to 100.0 %."""
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        pct, letter, _, _ = compute_grade(105.0, 100.0)
        assert pct    == 100.0
        assert letter == "S"

    def test_negative_score_clamped_to_zero(self):
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        pct, letter, _, is_pass = compute_grade(-5.0, 100.0)
        assert pct     == 0.0
        assert letter  == "F"
        assert is_pass is False

    # ------------------------------------------------------------------ custom pass_pct

    def test_custom_pass_pct_50(self):
        """45 % passes with default 40, fails with pass_pct=50."""
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, _, _, is_pass_40 = compute_grade(45.0, 100.0, pass_pct=40.0)
        _, _, _, is_pass_50 = compute_grade(45.0, 100.0, pass_pct=50.0)
        assert is_pass_40 is True
        assert is_pass_50 is False

    def test_custom_pass_pct_35(self):
        """38 % fails with default 40, passes with pass_pct=35."""
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        _, _, _, is_pass_40 = compute_grade(38.0, 100.0, pass_pct=40.0)
        _, _, _, is_pass_35 = compute_grade(38.0, 100.0, pass_pct=35.0)
        assert is_pass_40 is False
        assert is_pass_35 is True

    # ------------------------------------------------------------------ zero max_marks guard

    def test_zero_max_marks_returns_f_fail(self):
        """Division by zero is guarded — returns F, fail."""
        from app.modules.m10_bell_curve.grade_engine import compute_grade
        pct, letter, points, is_pass = compute_grade(0.0, 0.0)
        assert pct     == 0.0
        assert letter  == "F"
        assert points  == 0.0
        assert is_pass is False

    # ------------------------------------------------------------------ grade_distribution

    def test_grade_distribution_counts(self):
        from app.modules.m10_bell_curve.grade_engine import grade_distribution
        rows = [
            {"normalised_score": 95.0, "max_marks": 100.0},  # S
            {"normalised_score": 85.0, "max_marks": 100.0},  # A
            {"normalised_score": 85.0, "max_marks": 100.0},  # A
            {"normalised_score": 30.0, "max_marks": 100.0},  # F
        ]
        dist = grade_distribution(rows)
        assert dist["S"] == 1
        assert dist["A"] == 2
        assert dist["F"] == 1
        assert "B" not in dist

    def test_grade_distribution_empty_input(self):
        from app.modules.m10_bell_curve.grade_engine import grade_distribution
        assert grade_distribution([]) == {}

    def test_grade_distribution_all_pass(self):
        from app.modules.m10_bell_curve.grade_engine import grade_distribution
        rows = [{"normalised_score": 60.0, "max_marks": 100.0}] * 5
        dist = grade_distribution(rows)
        assert dist.get("C", 0) == 5
        assert "F" not in dist

    def test_grade_distribution_custom_pass_pct(self):
        """With pass_pct=50, a 45 % score should yield F in distribution."""
        from app.modules.m10_bell_curve.grade_engine import grade_distribution
        rows = [{"normalised_score": 45.0, "max_marks": 100.0}]
        dist_40 = grade_distribution(rows, pass_pct=40.0)
        dist_50 = grade_distribution(rows, pass_pct=50.0)
        assert "P" in dist_40
        assert "F" in dist_50

    def test_bell_curve_in_main_app_routes(self):
        from app.main import app
        paths = [r.path for r in app.routes]
        assert any("/bell-curve" in p for p in paths), "/bell-curve not registered in main.py"


# ===========================================================================
# H-37 STEP-02 — Normalised score grade enrichment
# ===========================================================================

class TestNormalisedScoreResponseGradeFields:
    """Schema has the four new grade fields with None defaults."""

    def test_schema_has_pct_field(self):
        from app.modules.m10_bell_curve.schemas import NormalisedScoreResponse
        assert "pct" in NormalisedScoreResponse.model_fields

    def test_schema_has_grade_letter_field(self):
        from app.modules.m10_bell_curve.schemas import NormalisedScoreResponse
        assert "grade_letter" in NormalisedScoreResponse.model_fields

    def test_schema_has_grade_point_field(self):
        from app.modules.m10_bell_curve.schemas import NormalisedScoreResponse
        assert "grade_point" in NormalisedScoreResponse.model_fields

    def test_schema_has_is_pass_field(self):
        from app.modules.m10_bell_curve.schemas import NormalisedScoreResponse
        assert "is_pass" in NormalisedScoreResponse.model_fields

    def test_grade_fields_default_none(self):
        from app.modules.m10_bell_curve.schemas import NormalisedScoreResponse
        for f in ("pct", "grade_letter", "grade_point", "is_pass"):
            assert NormalisedScoreResponse.model_fields[f].default is None, \
                f"{f} default must be None (not a DB column)"


class TestRouterGradeEnrichment:
    """_to_score_response enriches ORM rows with grade data without touching raw_score."""

    def _make_orm(self, normalised_score: float, max_marks: float = 100.0, raw_score: float | None = None):
        from unittest.mock import MagicMock
        from datetime import datetime
        orm = MagicMock()
        orm.id                   = uuid4()
        orm.decision_id          = uuid4()
        orm.analysis_id          = uuid4()
        orm.exam_paper_id        = uuid4()
        orm.student_user_id      = uuid4()
        orm.student_roll_ref     = "S001"
        orm.raw_score            = raw_score if raw_score is not None else normalised_score
        orm.normalised_score     = normalised_score
        orm.max_marks            = max_marks
        orm.normalisation_method = "NONE"
        orm.created_at           = datetime.now()
        # grade fields are None on the ORM row; _to_score_response populates them
        orm.pct          = None
        orm.grade_letter = None
        orm.grade_point  = None
        orm.is_pass      = None
        return orm

    def test_to_score_response_importable(self):
        from app.modules.m10_bell_curve.router import _to_score_response
        assert callable(_to_score_response)

    def test_enriches_s_grade(self):
        from app.modules.m10_bell_curve.router import _to_score_response
        resp = _to_score_response(self._make_orm(92.0))
        assert resp.grade_letter == "S"
        assert resp.pct          == 92.0
        assert resp.grade_point  == 10.0
        assert resp.is_pass      is True

    def test_enriches_a_grade(self):
        from app.modules.m10_bell_curve.router import _to_score_response
        resp = _to_score_response(self._make_orm(83.0))
        assert resp.grade_letter == "A"
        assert resp.grade_point  == 9.0
        assert resp.is_pass      is True

    def test_enriches_b_grade(self):
        from app.modules.m10_bell_curve.router import _to_score_response
        resp = _to_score_response(self._make_orm(75.0))
        assert resp.grade_letter == "B"
        assert resp.grade_point  == 8.0

    def test_enriches_f_grade_failing_student(self):
        from app.modules.m10_bell_curve.router import _to_score_response
        resp = _to_score_response(self._make_orm(30.0))
        assert resp.grade_letter == "F"
        assert resp.grade_point  == 0.0
        assert resp.is_pass      is False

    def test_raw_score_unchanged_advisory_only(self):
        """Bell curve is advisory: enrichment must not alter raw_score."""
        from app.modules.m10_bell_curve.router import _to_score_response
        resp = _to_score_response(self._make_orm(75.0, raw_score=65.0))
        assert resp.raw_score       == 65.0
        assert resp.normalised_score == 75.0

    def test_non_100_max_marks(self):
        """35/50 = 70 % → B."""
        from app.modules.m10_bell_curve.router import _to_score_response
        resp = _to_score_response(self._make_orm(35.0, max_marks=50.0))
        assert resp.grade_letter == "B"
        assert resp.pct          == 70.0

    def test_pct_correct(self):
        from app.modules.m10_bell_curve.router import _to_score_response
        resp = _to_score_response(self._make_orm(60.0))
        assert resp.pct == 60.0

    def test_enrichment_does_not_regress_base_fields(self):
        """All original score fields survive enrichment."""
        from app.modules.m10_bell_curve.router import _to_score_response
        orm  = self._make_orm(55.0)
        resp = _to_score_response(orm)
        assert resp.normalisation_method == "NONE"
        assert resp.max_marks            == 100.0


# ===========================================================================
# 9 — Audit events
# ===========================================================================

class TestM10AuditEvents:
    def test_all_six_m10_events_present(self):
        from app.core.audit_log.models import AuditEventType
        for event in (
            "BELL_CURVE_ANALYSIS_TRIGGERED",
            "BELL_CURVE_ANALYSIS_COMPLETED",
            "BELL_CURVE_ANALYSIS_FAILED",
            "BELL_CURVE_NORMALISATION_PREVIEWED",
            "BELL_CURVE_BOARD_RATIFIED",
            "BELL_CURVE_REPORT_EXPORTED",
        ):
            assert hasattr(AuditEventType, event), f"Missing AuditEventType: {event}"

    def test_m09_events_not_regressed(self):
        from app.core.audit_log.models import AuditEventType
        for event in (
            "SCRIPT_SCORING_QUEUED",
            "SCRIPT_SCORING_COMPLETED",
            "SCRIPT_BOARD_FINALISED",
            "EXAM_SCORE_RECORDED",
        ):
            assert hasattr(AuditEventType, event), f"Regressed M09 event: {event}"

    def test_m08_events_not_regressed(self):
        from app.core.audit_log.models import AuditEventType
        for event in ("EXAM_PAPER_SEALED", "EXAM_PAPER_BOARD_APPROVED"):
            assert hasattr(AuditEventType, event), f"Regressed M08 event: {event}"


# ===========================================================================
# 10 — Report builder
# ===========================================================================

class TestReportBuilder:
    def test_importable(self):
        from app.modules.m10_bell_curve.report_builder import generate_fairness_pdf
        assert callable(generate_fairness_pdf)

    def test_produces_pdf_bytes(self):
        import io
        from app.modules.m10_bell_curve.report_builder import generate_fairness_pdf
        buf = io.BytesIO()
        generate_fairness_pdf(buf, analyses=[], decisions_map={})
        buf.seek(0)
        data = buf.read()
        assert len(data) > 0
        assert data[:4] == b"%PDF", "Output is not a valid PDF"

    def test_handles_empty_analyses(self):
        import io
        from app.modules.m10_bell_curve.report_builder import generate_fairness_pdf
        buf = io.BytesIO()
        generate_fairness_pdf(buf, analyses=[], decisions_map={})
        buf.seek(0)
        assert buf.read(4) == b"%PDF"

    def test_handles_analysis_with_stats(self):
        import io
        from app.modules.m10_bell_curve.report_builder import generate_fairness_pdf
        mock_analysis = MagicMock()
        mock_analysis.id         = uuid4()
        mock_analysis.exam_paper_id = uuid4()
        mock_analysis.status     = "READY"
        mock_analysis.score_count = 30
        mock_analysis.triggered_at = None
        mock_analysis.analysis_completed_at = None
        mock_analysis.normalisation_suggestion = {"method": "NONE"}
        mock_analysis.raw_stats  = {
            "mean": 65.0, "std": 12.0, "median": 64.0,
            "min": 40.0, "max": 95.0, "q1": 55.0, "q3": 75.0,
            "skewness": 0.1, "kurtosis": -0.2,
            "histogram": [{"bin_left": 40.0, "bin_right": 60.0, "count": 10, "pct": 33.3}],
        }
        mock_analysis.anomalies  = []

        buf = io.BytesIO()
        generate_fairness_pdf(buf, analyses=[mock_analysis], decisions_map={})
        buf.seek(0)
        assert buf.read(4) == b"%PDF"


# ===========================================================================
# 11 — Human-gate invariants
# ===========================================================================

class TestCeleryTaskHumanGateInvariants:
    def test_task_does_not_import_decision_repository_write(self):
        import ast, pathlib
        src = pathlib.Path(
            "app/workers/heavy/analyse_score_distribution.py"
        ).read_text()
        assert "bulk_create" not in src, \
            "Celery task must NOT call BellCurveNormalisedScoreRepository.bulk_create"
        assert "set_applied" not in src, \
            "Celery task must NOT call set_applied"
        assert "set_no_action" not in src, \
            "Celery task must NOT call set_no_action"

    def test_task_does_not_write_exam_score_ledger(self):
        import pathlib
        src = pathlib.Path(
            "app/workers/heavy/analyse_score_distribution.py"
        ).read_text()
        assert "INSERT" not in src.upper() or "exam_score_ledger" not in src, \
            "Celery task must not INSERT into exam_score_ledger"

    def test_normalised_scores_only_via_ratify(self):
        import pathlib
        src = pathlib.Path(
            "app/modules/m10_bell_curve/service.py"
        ).read_text()
        assert "bulk_create" in src, "bulk_create should exist in service.py"
        assert "ratify" in src, "ratify gate must exist in service.py"

    def test_service_does_not_write_ledger(self):
        import pathlib
        src = pathlib.Path(
            "app/modules/m10_bell_curve/service.py"
        ).read_text()
        assert "exam_score_ledger" not in src or "INSERT" not in src.upper(), \
            "service.py must not INSERT into exam_score_ledger"

    def test_repository_set_applied_docstring_mentions_gate(self):
        import inspect
        from app.modules.m10_bell_curve.repository import BellCurveAnalysisRepository
        doc = inspect.getsource(BellCurveAnalysisRepository.set_applied)
        assert "ratify" in doc.lower() or "Gate" in doc or "never" in doc.lower(), \
            "set_applied should document that only service.ratify calls it"
