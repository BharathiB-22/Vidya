"""
M09.8 Examination Analytics — unit tests.

Pure-function tests over analytics_compute (no DB), plus wiring assertions for
the schemas, router and main.py mount.  Follows the M09 convention of mocking
all DB access; the compute layer is deliberately DB-free so the maths is tested
in isolation.

Coverage
  1. Grade bands       — grade_for_pct boundaries, band ordering
  2. Overview          — appeared/absent, pass/fail, averages, empty inputs
  3. Subject stats     — grouping, hardest-first sort, median/high/low
  4. Faculty stats     — workload, avg awarded %, turnaround, busiest-first
  5. Batch stats       — admission-year grouping, topper, newest-first
  6. Grade dist        — zero-filled buckets, pct_of_total
  7. Revaluation       — increased/unchanged/avg increase, undecided excluded
  8. Moderation        — completed/pending, avg variance, signed delta
  9. Schemas           — response models validate
 10. Router/wiring     — routes present, RBAC groups, mounted in main.py
"""
from __future__ import annotations

import pytest

from app.modules.m09_paper_admin import analytics_compute as c


# ===========================================================================
# 1 — Grade bands
# ===========================================================================

class TestGradeBands:
    @pytest.mark.parametrize("pct,grade", [
        (100, "A+"), (90, "A+"), (89.9, "A"), (80, "A"), (79, "B+"),
        (70, "B+"), (60, "B"), (59, "C"), (50, "C"), (49, "D"),
        (40, "D"), (39.9, "F"), (0, "F"),
    ])
    def test_grade_for_pct_boundaries(self, pct, grade):
        assert c.grade_for_pct(pct) == grade

    def test_grade_order_seven_bands(self):
        assert c.GRADE_ORDER == ["A+", "A", "B+", "B", "C", "D", "F"]

    def test_default_pass_pct(self):
        assert c.DEFAULT_PASS_PCT == 40.0


# ===========================================================================
# 2 — Overview
# ===========================================================================

class TestOverview:
    def _rows(self):
        return [
            c.ScoreRow("s1", "p1", "u1", 90, 100),
            c.ScoreRow("s2", "p1", "u2", 30, 100),
            c.ScoreRow("s3", "p2", "u3", 55, 100),
        ]

    def test_appeared_and_absent(self):
        o = c.compute_overview(self._rows(), total_students=5, pass_pct=40)
        assert o.appeared == 3
        assert o.total_students == 5
        assert o.absent == 2

    def test_pass_fail_counts(self):
        o = c.compute_overview(self._rows(), pass_pct=40)
        assert o.pass_count == 2      # 90, 55
        assert o.fail_count == 1      # 30
        assert o.pass_pct == round(2 / 3 * 100, 1)

    def test_average_high_low(self):
        o = c.compute_overview(self._rows(), pass_pct=40)
        assert o.average_pct == round((90 + 30 + 55) / 3, 1)
        assert o.highest_pct == 90.0
        assert o.lowest_pct == 30.0

    def test_absent_never_negative(self):
        # total smaller than appeared must not yield negative absent
        o = c.compute_overview(self._rows(), total_students=1)
        assert o.absent == 0
        assert o.total_students == 3

    def test_empty_input_no_raise(self):
        o = c.compute_overview([])
        assert o.appeared == 0
        assert o.pass_pct is None
        assert o.average_pct is None

    def test_threshold_changes_pass_count(self):
        rows = [c.ScoreRow("s1", "p1", "u1", 45, 100)]
        assert c.compute_overview(rows, pass_pct=40).pass_count == 1
        assert c.compute_overview(rows, pass_pct=50).pass_count == 0

    def test_zero_max_marks_safe(self):
        rows = [c.ScoreRow("s1", "p1", "u1", 0, 0)]
        o = c.compute_overview(rows)
        assert o.average_pct == 0.0


# ===========================================================================
# 3 — Subject stats
# ===========================================================================

class TestSubjectStats:
    def _rows(self):
        return [
            c.ScoreRow("s1", "easy", "u1", 80, 100),
            c.ScoreRow("s2", "easy", "u2", 90, 100),
            c.ScoreRow("s3", "hard", "u3", 30, 100),
            c.ScoreRow("s4", "hard", "u4", 50, 100),
        ]

    def test_groups_per_paper(self):
        stats = c.compute_subject_stats(self._rows())
        assert {s.exam_paper_id for s in stats} == {"easy", "hard"}

    def test_hardest_first(self):
        stats = c.compute_subject_stats(self._rows())
        assert stats[0].exam_paper_id == "hard"   # avg 40 < 85

    def test_median_high_low(self):
        stats = c.compute_subject_stats(self._rows())
        hard = next(s for s in stats if s.exam_paper_id == "hard")
        assert hard.highest == 50.0
        assert hard.lowest == 30.0
        assert hard.median == 40.0

    def test_pass_fail_pct(self):
        stats = c.compute_subject_stats(self._rows(), pass_pct=40)
        hard = next(s for s in stats if s.exam_paper_id == "hard")
        assert hard.pass_count == 1
        assert hard.fail_count == 1
        assert hard.pass_pct == 50.0
        assert hard.fail_pct == 50.0

    def test_empty(self):
        assert c.compute_subject_stats([]) == []


# ===========================================================================
# 4 — Faculty stats
# ===========================================================================

class TestFacultyStats:
    def _rows(self):
        return [
            c.EvalRow("s1", "f1", 80, 100, turnaround_hours=10),
            c.EvalRow("s2", "f1", 60, 100, turnaround_hours=20),
            c.EvalRow("s3", "f2", 40, 100, turnaround_hours=5),
        ]

    def test_workload_count(self):
        stats = c.compute_faculty_stats(self._rows())
        f1 = next(s for s in stats if s.evaluator_id == "f1")
        assert f1.scripts_evaluated == 2

    def test_busiest_first(self):
        stats = c.compute_faculty_stats(self._rows())
        assert stats[0].evaluator_id == "f1"

    def test_avg_awarded_pct_and_marks(self):
        stats = c.compute_faculty_stats(self._rows())
        f1 = next(s for s in stats if s.evaluator_id == "f1")
        assert f1.average_awarded_pct == 70.0
        assert f1.average_awarded_marks == 70.0

    def test_avg_turnaround(self):
        stats = c.compute_faculty_stats(self._rows())
        f1 = next(s for s in stats if s.evaluator_id == "f1")
        assert f1.avg_turnaround_hours == 15.0

    def test_missing_turnaround_ignored(self):
        rows = [c.EvalRow("s1", "f1", 80, 100, turnaround_hours=None)]
        stats = c.compute_faculty_stats(rows)
        assert stats[0].avg_turnaround_hours is None

    def test_empty(self):
        assert c.compute_faculty_stats([]) == []


# ===========================================================================
# 5 — Batch stats
# ===========================================================================

class TestBatchStats:
    def _rows(self):
        return [
            c.ScoreRow("s1", "p1", "u1", 90, 100, admission_year=2023),
            c.ScoreRow("s2", "p1", "u2", 50, 100, admission_year=2023),
            c.ScoreRow("s3", "p1", "u3", 70, 100, admission_year=2022),
        ]

    def test_groups_by_year(self):
        stats = c.compute_batch_stats(self._rows())
        assert {s.admission_year for s in stats} == {2023, 2022}

    def test_newest_first(self):
        stats = c.compute_batch_stats(self._rows())
        assert stats[0].admission_year == 2023

    def test_topper(self):
        stats = c.compute_batch_stats(self._rows())
        b2023 = next(s for s in stats if s.admission_year == 2023)
        assert b2023.topper_pct == 90.0
        assert b2023.topper_user_id == "u1"

    def test_pass_pct_and_average(self):
        stats = c.compute_batch_stats(self._rows(), pass_pct=40)
        b2023 = next(s for s in stats if s.admission_year == 2023)
        assert b2023.average == 70.0
        assert b2023.pass_pct == 100.0

    def test_unknown_batch_sinks_last(self):
        rows = [
            c.ScoreRow("s1", "p1", "u1", 90, 100, admission_year=None),
            c.ScoreRow("s2", "p1", "u2", 50, 100, admission_year=2024),
        ]
        stats = c.compute_batch_stats(rows)
        assert stats[-1].admission_year is None


# ===========================================================================
# 6 — Grade distribution
# ===========================================================================

class TestGradeDistribution:
    def test_zero_filled_all_bands(self):
        buckets = c.compute_grade_distribution([])
        assert [b.grade for b in buckets] == c.GRADE_ORDER
        assert all(b.count == 0 for b in buckets)
        assert all(b.pct_of_total == 0.0 for b in buckets)

    def test_counts_and_pct(self):
        rows = [
            c.ScoreRow("s1", "p1", "u1", 95, 100),   # A+
            c.ScoreRow("s2", "p1", "u2", 85, 100),   # A
            c.ScoreRow("s3", "p1", "u3", 35, 100),   # F
            c.ScoreRow("s4", "p1", "u4", 38, 100),   # F
        ]
        buckets = {b.grade: b for b in c.compute_grade_distribution(rows)}
        assert buckets["A+"].count == 1
        assert buckets["A"].count == 1
        assert buckets["F"].count == 2
        assert buckets["F"].pct_of_total == 50.0


# ===========================================================================
# 7 — Revaluation stats
# ===========================================================================

class TestRevaluationStats:
    def test_increased_unchanged_avg(self):
        rows = [
            c.RevalRow("r1", "APPROVED", 40, 55),    # +15
            c.RevalRow("r2", "APPROVED", 60, 60),    # unchanged
            c.RevalRow("r3", "APPROVED", 30, 39),    # +9
        ]
        s = c.compute_revaluation_stats(rows)
        assert s.total_requests == 3
        assert s.decided == 3
        assert s.marks_increased == 2
        assert s.marks_unchanged == 1
        assert s.average_increase == 12.0    # (15+9)/2
        assert s.max_increase == 15.0

    def test_undecided_excluded(self):
        rows = [c.RevalRow("r1", "SUBMITTED", 40, None)]
        s = c.compute_revaluation_stats(rows)
        assert s.total_requests == 1
        assert s.decided == 0
        assert s.average_increase is None

    def test_empty(self):
        s = c.compute_revaluation_stats([])
        assert s.total_requests == 0
        assert s.average_increase is None


# ===========================================================================
# 8 — Moderation stats
# ===========================================================================

class TestModerationStats:
    def test_completed_pending_variance_delta(self):
        rows = [
            c.ModRow("m1", "COMPLETE", 40, 60, 33.3, moderated_total=52),  # delta +12
            c.ModRow("m2", "PENDING", 50, 70, 28.5, moderated_total=None),
        ]
        s = c.compute_moderation_stats(rows)
        assert s.scripts_moderated == 2
        assert s.completed == 1
        assert s.pending == 1
        assert s.average_variance_pct == round((33.3 + 28.5) / 2, 2)
        assert s.average_delta == 12.0

    def test_empty(self):
        s = c.compute_moderation_stats([])
        assert s.scripts_moderated == 0
        assert s.average_variance_pct is None


# ===========================================================================
# 9 — Schemas
# ===========================================================================

class TestSchemas:
    def test_overview_response_validates(self):
        from app.modules.m09_paper_admin.analytics_schemas import OverviewResponse
        r = OverviewResponse(
            scope="INSTITUTION", exam_paper_id=None, exam_paper_title=None,
            total_students=10, appeared=9, absent=1, pass_count=7, fail_count=2,
            pass_pct=77.8, average_pct=61.2, highest_pct=95.0, lowest_pct=12.0,
            pass_threshold_pct=40.0, papers_count=3,
        )
        assert r.appeared == 9

    def test_dashboard_response_fields(self):
        from app.modules.m09_paper_admin.analytics_schemas import DashboardResponse
        assert set(DashboardResponse.model_fields) == {
            "overview", "grades", "top_subjects", "revaluation", "moderation",
        }


# ===========================================================================
# 10 — Router & wiring
# ===========================================================================

class TestRouterWiring:
    def test_all_eight_routes_present(self):
        from app.modules.m09_paper_admin.analytics_router import router
        paths = {r.path for r in router.routes}
        assert paths == {
            "/overview", "/subjects", "/grades", "/batches",
            "/faculty", "/revaluation", "/moderation", "/dashboard",
        }

    def test_governance_routes_exclude_faculty(self):
        from app.modules.m09_paper_admin.analytics_router import _GOV, _READ
        from app.core.auth.models import TenantRole
        assert TenantRole.FACULTY in _READ
        assert TenantRole.FACULTY not in _GOV
        assert TenantRole.STUDENT not in _READ   # students never see analytics

    def test_mounted_in_main(self):
        import app.main as main
        routes = [r.path for r in main.app.routes]
        assert any(p.startswith("/exam-analytics") for p in routes)

    def test_service_methods_exist(self):
        from app.modules.m09_paper_admin.analytics_service import ExamAnalyticsService
        for m in ("overview", "subjects", "faculty", "batches", "grades",
                  "revaluation", "moderation", "dashboard"):
            assert hasattr(ExamAnalyticsService, m)
