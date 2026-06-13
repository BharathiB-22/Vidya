"""
M09.9 Compliance & Audit — unit tests.

Pure-function tests over compliance_core (no DB), plus schema validation and
wiring assertions for the router, service dispatcher, model immutability and the
main.py mount.  Follows the M09 convention: the DB-free core carries the logic
so it is tested in isolation; DB layers are covered by the wiring assertions.

Coverage
  1. Taxonomy        — catalog mapping, category/label, category→types
  2. Timeline        — exam-event filtering, ordering, name enrichment, counts
  3. Mark lineage    — derived per-question value steps, delta
  4. CSV export      — header always emitted, None/datetime/bool cells
  5. Schemas         — response models validate
  6. Mark recorder   — payload shaping (delta, anonymity)
  7. Router/wiring   — routes present, RBAC (FACULTY excluded), reports, mount
  8. Immutability    — append-only model/repository/migration guarantees
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.m09_paper_admin import compliance_core as c


# ===========================================================================
# 1 — Taxonomy
# ===========================================================================

class TestTaxonomy:
    def test_catalog_non_empty_and_typed(self):
        assert len(c.EXAM_EVENT_CATALOG) >= 20
        for et, (cat, label) in c.EXAM_EVENT_CATALOG.items():
            assert cat in c.ALL_CATEGORIES
            assert isinstance(label, str) and label

    def test_event_types_set_matches_catalog(self):
        assert c.EXAM_EVENT_TYPES == frozenset(c.EXAM_EVENT_CATALOG.keys())

    def test_is_exam_event(self):
        assert c.is_exam_event("SCRIPT_MARKS_UPDATED")
        assert not c.is_exam_event("AUTH_LOGIN_SUCCESS")

    def test_category_for_known_and_unknown(self):
        assert c.category_for("RESULTS_DECLARED") == c.Category.PUBLICATION
        assert c.category_for("NOT_A_REAL_EVENT") is None

    def test_label_fallback_titlecases(self):
        assert c.label_for("SCRIPT_MARKS_UPDATED") == "Marks changed"
        assert c.label_for("SOME_NEW_EVENT") == "Some New Event"

    def test_event_types_for_categories(self):
        types = c.event_types_for_categories(["REVALUATION"])
        assert "REVALUATION_REQUESTED" in types
        assert "SCRIPT_MARKS_UPDATED" not in types

    def test_event_types_for_categories_none(self):
        assert c.event_types_for_categories(None) is None
        assert c.event_types_for_categories([]) is None

    def test_key_governance_events_present(self):
        # The seven governance questions must be answerable.
        for et in (
            "SCRIPT_MARKS_UPDATED", "SCRIPT_BOARD_FINALISED",
            "SCRIPT_MODERATION_SUBMITTED", "REVALUATION_BOARD_RATIFIED",
            "BOARD_SESSION_APPROVED", "RESULTS_DECLARED",
        ):
            assert et in c.EXAM_EVENT_CATALOG


# ===========================================================================
# 2 — Timeline
# ===========================================================================

class TestTimeline:
    def _rows(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            {"id": "1", "event_type": "SCRIPT_MARKS_UPDATED", "actor_user_id": "u1",
             "actor_role": "EVALUATOR", "target_entity": "scanned_script", "target_id": "s1",
             "created_at": t0, "metadata": {"question_count": 3}},
            {"id": "2", "event_type": "AUTH_LOGIN_SUCCESS", "actor_user_id": "u1",
             "actor_role": "ADMIN", "target_entity": None, "target_id": None,
             "created_at": t0 + timedelta(hours=1), "metadata": {}},
            {"id": "3", "event_type": "RESULTS_DECLARED", "actor_user_id": "u2",
             "actor_role": "ADMIN", "target_entity": "exam_paper", "target_id": "p1",
             "created_at": t0 + timedelta(hours=2), "metadata": {}},
        ]

    def test_non_exam_events_filtered(self):
        entries = c.build_timeline(self._rows())
        assert len(entries) == 2  # login event dropped
        assert all(e.event_type != "AUTH_LOGIN_SUCCESS" for e in entries)

    def test_descending_order(self):
        entries = c.build_timeline(self._rows())
        assert entries[0].event_type == "RESULTS_DECLARED"  # latest first

    def test_ascending_order(self):
        entries = c.build_timeline(self._rows(), descending=False)
        assert entries[0].event_type == "SCRIPT_MARKS_UPDATED"

    def test_name_enrichment(self):
        entries = c.build_timeline(self._rows(), names={"u1": "Dr Rao"})
        marks = next(e for e in entries if e.event_type == "SCRIPT_MARKS_UPDATED")
        assert marks.actor_name == "Dr Rao"
        assert marks.category == c.Category.MARK_CHANGE
        assert marks.label == "Marks changed"

    def test_summarise_categories_zero_filled(self):
        entries = c.build_timeline(self._rows())
        counts = c.summarise_categories(entries)
        assert set(counts.keys()) == set(c.ALL_CATEGORIES)
        assert counts[c.Category.MARK_CHANGE] == 1
        assert counts[c.Category.PUBLICATION] == 1
        assert counts[c.Category.MODERATION] == 0

    def test_empty_rows(self):
        assert c.build_timeline([]) == []


# ===========================================================================
# 3 — Mark lineage
# ===========================================================================

class TestMarkLineage:
    def test_full_lineage_order(self):
        rows = [{
            "question_id": "q1", "question_type": "SHORT_ANSWER", "evaluation_round": "PRIMARY",
            "max_marks": 10, "ai_suggested_marks": 6, "ai_justification": "ai",
            "evaluator_marks": 7, "evaluator_note": "ok",
            "board_adjusted_marks": 8, "board_adjustment_note": "lenient",
            "final_marks": 8,
        }]
        hist = c.derive_question_lineage(rows)
        assert len(hist) == 1
        stages = [s.stage for s in hist[0].steps]
        assert stages == ["AI_SUGGESTED", "EVALUATOR", "BOARD_ADJUSTED", "FINAL"]
        assert hist[0].steps[1].marks == 7.0

    def test_moderation_round_stage(self):
        rows = [{
            "question_id": "q1", "evaluation_round": "MODERATION", "max_marks": 10,
            "evaluator_marks": 9, "evaluator_note": "moderated",
        }]
        hist = c.derive_question_lineage(rows)
        assert hist[0].steps[0].stage == "MODERATION"

    def test_rounds_merge_per_question(self):
        rows = [
            {"question_id": "q1", "evaluation_round": "PRIMARY", "max_marks": 10, "evaluator_marks": 5},
            {"question_id": "q1", "evaluation_round": "MODERATION", "max_marks": 10, "evaluator_marks": 8},
        ]
        hist = c.derive_question_lineage(rows)
        assert len(hist) == 1
        stages = [s.stage for s in hist[0].steps]
        assert stages == ["EVALUATOR", "MODERATION"]

    def test_compute_delta(self):
        assert c.compute_delta(5, 8) == 3
        assert c.compute_delta(None, 8) is None
        assert c.compute_delta(8, None) is None


# ===========================================================================
# 4 — CSV export
# ===========================================================================

class TestCsv:
    def test_header_always_emitted(self):
        out = c.to_csv([], ["a", "b"])
        assert out.splitlines()[0] == "a,b"

    def test_rows_and_none_and_types(self):
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = c.to_csv(
            [{"a": 1, "b": None, "ts": ts, "ok": True}],
            ["a", "b", "ts", "ok"],
        )
        lines = out.splitlines()
        assert lines[0] == "a,b,ts,ok"
        assert lines[1].startswith("1,,2026-01-01T00:00:00+00:00,true")

    def test_extra_keys_ignored(self):
        out = c.to_csv([{"a": 1, "zzz": 9}], ["a"])
        assert "zzz" not in out


# ===========================================================================
# 5 — Schemas
# ===========================================================================

class TestSchemas:
    def test_report_response(self):
        from app.modules.m09_paper_admin.compliance_schemas import ReportResponse
        r = ReportResponse(report="moderation", generated_at=datetime.now(timezone.utc),
                           row_count=0, rows=[])
        assert r.report == "moderation"

    def test_audit_trail_response(self):
        from app.modules.m09_paper_admin.compliance_schemas import AuditTrailResponse
        r = AuditTrailResponse(scope="SCRIPT", total=0, page=1, page_size=50)
        assert r.scope == "SCRIPT"

    def test_result_change_history_default_anonymous(self):
        from app.modules.m09_paper_admin.compliance_schemas import ResultChangeHistoryResponse
        r = ResultChangeHistoryResponse(script_id="s1")
        assert r.student_revealed is False
        assert r.student_user_id is None


# ===========================================================================
# 6 — Mark recorder payload shaping
# ===========================================================================

class TestMarkRecorder:
    async def _capture(self, monkeypatch):
        captured = {}

        async def fake_insert(rows, *, db):
            captured["rows"] = rows

        # Patch the repository insert and the session context so no real DB is hit.
        from app.modules.m09_paper_admin import compliance_service as svc

        class _FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            def begin(self): return self

        monkeypatch.setattr(svc.ComplianceRepository, "insert_mark_audit", fake_insert)
        monkeypatch.setattr(svc, "AsyncSessionLocal", lambda: _FakeSession())
        return captured, svc

    @pytest.mark.asyncio
    async def test_records_delta_and_keeps_identity_null(self, monkeypatch):
        captured, svc = await self._capture(monkeypatch)
        await svc.ExamMarkAuditService.record_changes(
            script_id="11111111-1111-1111-1111-111111111111",
            exam_paper_id="22222222-2222-2222-2222-222222222222",
            change_type="EVALUATOR_UPDATE",
            actor_user_id="33333333-3333-3333-3333-333333333333",
            actor_role="EVALUATOR",
            source_event="SCRIPT_MARKS_UPDATED",
            changes=[{"question_id": "44444444-4444-4444-4444-444444444444",
                      "previous_marks": 5, "new_marks": 8, "max_marks": 10, "reason": "ok"}],
            masked_id="SCRIPT-007",
        )
        row = captured["rows"][0]
        assert row["delta"] == 3.0
        assert row["student_user_id"] is None       # anonymity preserved
        assert row["masked_id"] == "SCRIPT-007"
        assert row["change_type"] == "EVALUATOR_UPDATE"

    @pytest.mark.asyncio
    async def test_empty_changes_no_write(self, monkeypatch):
        captured, svc = await self._capture(monkeypatch)
        await svc.ExamMarkAuditService.record_changes(
            script_id="1", exam_paper_id="2", change_type="EVALUATOR_UPDATE",
            actor_user_id="3", actor_role="EVALUATOR", source_event="X", changes=[],
        )
        assert "rows" not in captured


# ===========================================================================
# 7 — Router / wiring
# ===========================================================================

class TestWiring:
    def test_all_routes_present(self):
        from app.modules.m09_paper_admin.compliance_router import router
        paths = {r.path for r in router.routes}
        for p in (
            "/dashboard",
            "/audit-trail/student/{student_user_id}",
            "/audit-trail/script/{script_id}",
            "/audit-trail/exam/{exam_paper_id}",
            "/audit-trail/evaluator/{evaluator_id}",
            "/audit-trail",
            "/result-history/{script_id}",
            "/reports",
            "/reports/{report}",
            "/reports/{report}/export",
        ):
            assert p in paths

    def test_rbac_excludes_faculty(self):
        from app.modules.m09_paper_admin.compliance_router import _GOV
        from app.core.auth.models import TenantRole
        roles = {r.value for r in _GOV}
        assert roles == {"ADMIN", "DEAN", "BOARD"}
        assert TenantRole.FACULTY not in _GOV

    def test_six_reports_registered(self):
        from app.modules.m09_paper_admin.compliance_service import ComplianceService
        names = ComplianceService.report_names()
        # Original 5 + 3 OCR reports added by M09.7
        base = {
            "publication_approval", "moderation", "revaluation",
            "evaluator_activity", "board_approval",
        }
        ocr = {"ocr_correction_history", "ocr_reviewer_activity", "ocr_escalation"}
        assert base.issubset(set(names))
        assert ocr.issubset(set(names))
        # Every report has an ordered CSV column spec.
        for name in names:
            _method, cols = ComplianceService._REPORTS[name]
            assert isinstance(cols, list) and cols

    def test_mounted_in_main(self):
        import app.main as m
        paths = {getattr(r, "path", "") for r in m.app.routes}
        assert any(p.startswith("/exam-compliance") for p in paths)


# ===========================================================================
# 8 — Immutability guarantees
# ===========================================================================

class TestImmutability:
    def test_repository_has_no_update_or_delete(self):
        from app.modules.m09_paper_admin import compliance_repository as repo
        members = dir(repo.ComplianceRepository)
        assert "insert_mark_audit" in members
        assert not any("update" in m or "delete" in m for m in members)

    def test_model_is_exam_mark_audit(self):
        from app.modules.m09_paper_admin.compliance_models import ExamMarkAudit, MarkChangeType
        assert ExamMarkAudit.__tablename__ == "exam_mark_audit"
        assert {t.value for t in MarkChangeType} == {
            "EVALUATOR_UPDATE", "BOARD_ADJUSTMENT", "MODERATION", "REVALUATION",
        }

    def test_migration_declares_append_only_triggers(self):
        import pathlib
        mig = pathlib.Path(__file__).resolve().parents[3] / "alembic" / "tenant_versions" / "0048ten_compliance_audit.py"
        text = mig.read_text(encoding="utf-8")
        assert "exam_mark_audit_block_update" in text
        assert "exam_mark_audit_block_delete" in text
        assert "exam_mark_audit_block_truncate" in text
        assert "append-only" in text.lower()
