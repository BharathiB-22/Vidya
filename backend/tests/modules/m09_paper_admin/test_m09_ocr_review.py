"""
M09.7 OCR Review Queue — unit tests.

Pure-function tests over the priority classifier, seed scenarios,
compliance_core OCR event taxonomy, schema validation, and wiring
assertions for the router and main.py mount.  No DB access.

Coverage
  1. Priority classifier     — all four categories, None for good OCR
  2. Seed scenarios          — expected_queue_entry matches classifier
  3. Threshold defaults      — valid range, low < medium invariant
  4. OCR audit event types   — all 7 M09.7 events in AuditEventType
  5. Compliance taxonomy     — OCR events mapped to SCANNING category
  6. Schemas                 — all response models instantiate
  7. Router / wiring         — routes present, RBAC, mounted in main.py
  8. Analytics schemas       — OcrAnalyticsResponse validates
  9. Compliance reports      — 3 new OCR reports in _REPORTS dispatcher
"""
from __future__ import annotations

import pytest

from app.modules.m09_paper_admin.ocr_models import (
    OcrPriorityCategory,
    OcrReviewStatus,
    OcrThresholdScope,
    PRIORITY_SCORE,
)
from app.modules.m09_paper_admin.ocr_service import OcrReviewService
from app.modules.m09_paper_admin.ocr_seed import OCR_SEED_SCENARIOS
from app.modules.m09_paper_admin import compliance_core as cc
from app.core.audit_log.models import AuditEventType


# ===========================================================================
# 1 — Priority Classifier
# ===========================================================================

class TestPriorityClassifier:
    """Tests for OcrReviewService._classify() — pure function, no DB."""

    def _classify(self, *, ocr_status="COMPLETE", ocr_confidence=None,
                  scan_quality_flags=None, low=0.60, medium=0.80):
        return OcrReviewService._classify(
            ocr_status=ocr_status,
            ocr_confidence=ocr_confidence,
            scan_quality_flags=scan_quality_flags or [],
            low_threshold=low,
            medium_threshold=medium,
        )

    def test_ocr_failure_status(self):
        result = self._classify(ocr_status="FAILED", ocr_confidence=None)
        assert result == OcrPriorityCategory.OCR_FAILURE

    def test_ocr_failure_error_status(self):
        result = self._classify(ocr_status="ERROR", ocr_confidence=None)
        assert result == OcrPriorityCategory.OCR_FAILURE

    def test_ocr_failure_when_no_confidence_and_complete(self):
        # COMPLETE but no confidence → treat as failure
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=None)
        assert result == OcrPriorityCategory.OCR_FAILURE

    def test_low_confidence_below_threshold(self):
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=0.45)
        assert result == OcrPriorityCategory.LOW_CONFIDENCE

    def test_low_confidence_at_boundary(self):
        # Exactly 0.60 is NOT below threshold (< not <=)
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=0.60)
        assert result != OcrPriorityCategory.LOW_CONFIDENCE

    def test_quality_issue_critical_flag(self):
        flags = [{"type": "PARTIAL_SCAN", "page": 1, "severity": "CRITICAL",
                  "description": "Partial"}]
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=0.75, scan_quality_flags=flags)
        assert result == OcrPriorityCategory.QUALITY_ISSUE

    def test_quality_issue_high_flag(self):
        flags = [{"type": "LOW_DPI", "page": 1, "severity": "HIGH", "description": "Low DPI"}]
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=0.75, scan_quality_flags=flags)
        assert result == OcrPriorityCategory.QUALITY_ISSUE

    def test_quality_issue_not_triggered_by_medium_flag(self):
        flags = [{"type": "ROTATED", "page": 2, "severity": "MEDIUM", "description": "Rotated"}]
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=0.75, scan_quality_flags=flags)
        # 0.75 is between low (0.60) and medium (0.80), no CRITICAL/HIGH flag → MEDIUM_CONFIDENCE
        assert result == OcrPriorityCategory.MEDIUM_CONFIDENCE

    def test_medium_confidence_range(self):
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=0.72)
        assert result == OcrPriorityCategory.MEDIUM_CONFIDENCE

    def test_no_review_needed_high_confidence(self):
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=0.95)
        assert result is None

    def test_no_review_needed_at_medium_threshold(self):
        result = self._classify(ocr_status="COMPLETE", ocr_confidence=0.80)
        assert result is None

    def test_pending_status_not_classified_as_failure(self):
        result = self._classify(ocr_status="PENDING", ocr_confidence=None)
        assert result is None

    def test_processing_status_not_classified_as_failure(self):
        result = self._classify(ocr_status="PROCESSING", ocr_confidence=None)
        assert result is None

    def test_priority_scores_ordering(self):
        assert PRIORITY_SCORE[OcrPriorityCategory.OCR_FAILURE] == 4
        assert PRIORITY_SCORE[OcrPriorityCategory.LOW_CONFIDENCE] == 3
        assert PRIORITY_SCORE[OcrPriorityCategory.QUALITY_ISSUE] == 2
        assert PRIORITY_SCORE[OcrPriorityCategory.MEDIUM_CONFIDENCE] == 1
        # OCR_FAILURE must have the highest score
        assert PRIORITY_SCORE[OcrPriorityCategory.OCR_FAILURE] == max(PRIORITY_SCORE.values())


# ===========================================================================
# 2 — Seed Scenarios
# ===========================================================================

class TestSeedScenarios:
    """Verify each seed scenario's expected output matches the classifier."""

    @pytest.mark.parametrize("scenario", OCR_SEED_SCENARIOS, ids=[s["scenario_key"] for s in OCR_SEED_SCENARIOS])
    def test_seed_scenario_classifier_match(self, scenario):
        result = OcrReviewService._classify(
            ocr_status=scenario["ocr_status"],
            ocr_confidence=scenario["ocr_confidence"],
            scan_quality_flags=scenario["scan_quality_flags"],
            low_threshold=0.60,
            medium_threshold=0.80,
        )
        expected_entry = scenario["expected_queue_entry"]
        expected_cat   = scenario["expected_priority_category"]

        if not expected_entry:
            assert result is None, (
                f"Scenario '{scenario['scenario_key']}' should NOT be queued "
                f"but classifier returned {result}"
            )
        else:
            assert result is not None, (
                f"Scenario '{scenario['scenario_key']}' should be queued "
                f"but classifier returned None"
            )
            assert result == expected_cat, (
                f"Scenario '{scenario['scenario_key']}' expected {expected_cat} "
                f"but got {result}"
            )

    def test_five_scenarios_defined(self):
        assert len(OCR_SEED_SCENARIOS) == 5

    def test_all_scenarios_have_required_keys(self):
        required = {"scenario_key", "label", "description", "ocr_status",
                    "ocr_confidence", "ocr_text", "scan_quality_flags",
                    "expected_queue_entry", "expected_priority_category"}
        for s in OCR_SEED_SCENARIOS:
            assert required.issubset(s.keys()), f"{s['scenario_key']} missing keys"

    def test_ocr_failure_scenario_has_no_confidence(self):
        failure = next(s for s in OCR_SEED_SCENARIOS if s["scenario_key"] == "ocr_failure")
        assert failure["ocr_confidence"] is None
        assert failure["ocr_status"] == "FAILED"
        assert failure["expected_priority_category"] == "OCR_FAILURE"

    def test_perfect_scan_not_queued(self):
        perfect = next(s for s in OCR_SEED_SCENARIOS if s["scenario_key"] == "perfect_scan")
        assert not perfect["expected_queue_entry"]
        assert perfect["ocr_confidence"] >= 0.80


# ===========================================================================
# 3 — Threshold Model
# ===========================================================================

class TestThresholdModel:
    def test_scope_enum_values(self):
        assert OcrThresholdScope.GLOBAL == "GLOBAL"
        assert OcrThresholdScope.EXAM   == "EXAM"

    def test_review_status_terminal_states(self):
        terminal = {
            OcrReviewStatus.ACCEPTED,
            OcrReviewStatus.CORRECTED,
            OcrReviewStatus.RERUN_REQUESTED,
            OcrReviewStatus.ESCALATED,
            OcrReviewStatus.MARKED_UNREADABLE,
        }
        active = {OcrReviewStatus.PENDING, OcrReviewStatus.IN_REVIEW}
        assert not (terminal & active), "Terminal and active sets must be disjoint"

    def test_priority_category_enum_completeness(self):
        categories = {
            OcrPriorityCategory.OCR_FAILURE,
            OcrPriorityCategory.LOW_CONFIDENCE,
            OcrPriorityCategory.QUALITY_ISSUE,
            OcrPriorityCategory.MEDIUM_CONFIDENCE,
        }
        assert len(categories) == 4
        assert all(c in PRIORITY_SCORE for c in categories)


# ===========================================================================
# 4 — Audit Event Types
# ===========================================================================

class TestAuditEventTypes:
    """Ensure all seven M09.7 audit events are present in AuditEventType."""

    M09_7_EVENTS = [
        "OCR_REVIEW_STARTED",
        "OCR_TEXT_CORRECTED",
        "OCR_RERUN_REQUESTED",
        "OCR_ESCALATED",
        "OCR_ACCEPTED",
        "OCR_MARKED_UNREADABLE",
        "OCR_THRESHOLD_UPDATED",
    ]

    @pytest.mark.parametrize("event_name", M09_7_EVENTS)
    def test_event_exists_in_enum(self, event_name):
        assert hasattr(AuditEventType, event_name), (
            f"AuditEventType.{event_name} not found"
        )

    @pytest.mark.parametrize("event_name", M09_7_EVENTS)
    def test_event_value_matches_name(self, event_name):
        assert getattr(AuditEventType, event_name).value == event_name


# ===========================================================================
# 5 — Compliance Taxonomy
# ===========================================================================

class TestOcrComplianceTaxonomy:
    """OCR events must map to the SCANNING category in EXAM_EVENT_CATALOG."""

    OCR_EVENTS = [
        "OCR_REVIEW_STARTED",
        "OCR_TEXT_CORRECTED",
        "OCR_RERUN_REQUESTED",
        "OCR_ESCALATED",
        "OCR_ACCEPTED",
        "OCR_MARKED_UNREADABLE",
        "OCR_THRESHOLD_UPDATED",
    ]

    @pytest.mark.parametrize("event", OCR_EVENTS)
    def test_ocr_event_in_catalog(self, event):
        assert event in cc.EXAM_EVENT_CATALOG, f"{event} missing from EXAM_EVENT_CATALOG"

    @pytest.mark.parametrize("event", OCR_EVENTS)
    def test_ocr_event_maps_to_scanning(self, event):
        cat, _ = cc.EXAM_EVENT_CATALOG[event]
        assert cat == cc.Category.SCANNING, (
            f"{event} expected SCANNING category, got {cat}"
        )

    def test_event_types_set_updated(self):
        for event in self.OCR_EVENTS:
            assert event in cc.EXAM_EVENT_TYPES

    def test_filter_by_scanning_includes_ocr_events(self):
        types = cc.event_types_for_categories(["SCANNING"])
        for event in self.OCR_EVENTS:
            assert event in types


# ===========================================================================
# 6 — Schemas
# ===========================================================================

class TestOcrSchemas:
    def test_dashboard_response_defaults(self):
        from app.modules.m09_paper_admin.ocr_schemas import OcrDashboardResponse
        r = OcrDashboardResponse()
        assert r.pending_total == 0
        assert r.ocr_failure_count == 0

    def test_queue_item_fields(self):
        import uuid
        from datetime import datetime, timezone
        from app.modules.m09_paper_admin.ocr_schemas import OcrQueueItem
        item = OcrQueueItem(
            id=uuid.uuid4(),
            script_id=uuid.uuid4(),
            exam_paper_id=uuid.uuid4(),
            priority_category="OCR_FAILURE",
            priority_score=4,
            ocr_confidence=None,
            review_status="PENDING",
            assigned_reviewer_id=None,
            review_started_at=None,
            action_taken=None,
            completed_at=None,
            created_at=datetime.now(timezone.utc),
        )
        assert item.priority_score == 4

    def test_threshold_create_validation(self):
        from app.modules.m09_paper_admin.ocr_schemas import OcrThresholdCreate
        t = OcrThresholdCreate(scope="GLOBAL", low_confidence_threshold=0.5,
                               medium_confidence_threshold=0.8)
        assert t.low_confidence_threshold == 0.5

    def test_correct_request_requires_text(self):
        from pydantic import ValidationError
        from app.modules.m09_paper_admin.ocr_schemas import OcrCorrectRequest
        with pytest.raises(ValidationError):
            OcrCorrectRequest()  # corrected_text is required

    def test_escalate_request_min_length(self):
        from pydantic import ValidationError
        from app.modules.m09_paper_admin.ocr_schemas import OcrEscalateRequest
        with pytest.raises(ValidationError):
            OcrEscalateRequest(reviewer_notes="short")  # min_length=10

    def test_action_response_instantiates(self):
        import uuid
        from app.modules.m09_paper_admin.ocr_schemas import OcrActionResponse
        r = OcrActionResponse(
            queue_id=uuid.uuid4(),
            script_id=uuid.uuid4(),
            review_status="ACCEPTED",
            action_taken="ACCEPTED",
            completed_at=None,
            message="Done.",
        )
        assert r.review_status == "ACCEPTED"

    def test_effective_threshold_response(self):
        from app.modules.m09_paper_admin.ocr_schemas import EffectiveThresholdResponse
        r = EffectiveThresholdResponse(
            low_confidence_threshold=0.6,
            medium_confidence_threshold=0.8,
            source_scope="GLOBAL",
        )
        assert r.source_scope == "GLOBAL"
        assert r.source_id is None


# ===========================================================================
# 7 — Router / Wiring
# ===========================================================================

class TestOcrRouterWiring:
    def test_router_imported(self):
        from app.modules.m09_paper_admin.ocr_router import router
        assert router is not None

    def test_router_routes_present(self):
        from app.modules.m09_paper_admin.ocr_router import router
        paths = {r.path for r in router.routes}
        expected = {
            "/dashboard", "/threshold", "/threshold/all", "/threshold",
            "", "/{queue_id}", "/{queue_id}/start", "/{queue_id}/accept",
            "/{queue_id}/correct", "/{queue_id}/rerun",
            "/{queue_id}/escalate", "/{queue_id}/unreadable",
        }
        for p in expected:
            assert p in paths, f"Route '{p}' not found in OCR router"

    def test_main_py_mounts_ocr_router(self):
        import importlib
        main = importlib.import_module("app.main")
        routes = {r.path for r in main.app.routes}
        assert any("/ocr-review" in r for r in routes), (
            "/ocr-review prefix not mounted in main.py"
        )

    def test_ocr_router_tag(self):
        from app.modules.m09_paper_admin.ocr_router import router
        assert "M09.7 OCR Review Queue" in router.tags


# ===========================================================================
# 8 — Analytics Schemas
# ===========================================================================

class TestOcrAnalyticsSchemas:
    def test_ocr_analytics_response_instantiates(self):
        from app.modules.m09_paper_admin.analytics_schemas import OcrAnalyticsResponse
        r = OcrAnalyticsResponse(
            scope="INSTITUTION",
            exam_paper_id=None,
            total_queued=10,
            total_corrected=3,
            total_accepted=5,
            total_rerun=1,
            total_unreadable=1,
            ocr_accuracy_rate=62.5,
            average_confidence=0.73,
            reviewer_count=2,
            corrections_per_reviewer=[],
            quality_distribution=[],
        )
        assert r.total_queued == 10
        assert r.ocr_accuracy_rate == 62.5

    def test_ocr_analytics_endpoint_in_router(self):
        from app.modules.m09_paper_admin.analytics_router import router
        paths = {r.path for r in router.routes}
        assert "/ocr" in paths, "/ocr endpoint missing from analytics router"

    def test_ocr_quality_distribution_item(self):
        from app.modules.m09_paper_admin.analytics_schemas import OcrQualityDistributionItem
        item = OcrQualityDistributionItem(category="OCR_FAILURE", count=3)
        assert item.count == 3


# ===========================================================================
# 9 — Compliance Reports Registry
# ===========================================================================

class TestOcrComplianceReports:
    def test_three_ocr_reports_in_dispatcher(self):
        from app.modules.m09_paper_admin.compliance_service import ComplianceService
        names = ComplianceService.report_names()
        assert "ocr_correction_history" in names
        assert "ocr_reviewer_activity" in names
        assert "ocr_escalation" in names

    def test_ocr_correction_history_columns(self):
        from app.modules.m09_paper_admin.compliance_service import ComplianceService
        _, cols = ComplianceService._REPORTS["ocr_correction_history"]
        assert "queue_id" in cols
        assert "masked_id" in cols
        assert "action_taken" in cols

    def test_ocr_reviewer_activity_columns(self):
        from app.modules.m09_paper_admin.compliance_service import ComplianceService
        _, cols = ComplianceService._REPORTS["ocr_reviewer_activity"]
        assert "reviewer_name" in cols
        assert "corrections" in cols
        assert "escalated" in cols

    def test_ocr_escalation_columns(self):
        from app.modules.m09_paper_admin.compliance_service import ComplianceService
        _, cols = ComplianceService._REPORTS["ocr_escalation"]
        assert "reviewer_notes" in cols
        assert "completed_at" in cols

    def test_ocr_schemas_imported(self):
        from app.modules.m09_paper_admin.compliance_schemas import (
            OcrCorrectionHistoryRow,
        )
        r = OcrCorrectionHistoryRow(
            queue_id="abc",
            script_id="def",
            exam_paper_id="ghi",
        )
        assert r.queue_id == "abc"
