"""
M06 Labs Evaluator — wiring and smoke tests (STEP-16).

Verifies (no live services required):
  1. All M06 modules import cleanly
  2. Config has all required M06 keys
  3. Celery task registered in include list
  4. Router mounted at /labs in FastAPI app
  5. Key endpoints present in OpenAPI route table
  6. All M06 AuditEventType values defined
"""
from __future__ import annotations


# ===========================================================================
# 1. Module imports
# ===========================================================================

def test_models_import():
    from app.modules.m06_labs_evaluator import models
    assert hasattr(models, "LabAssignment")
    assert hasattr(models, "LabSubmission")
    assert hasattr(models, "LabEvaluation")
    assert hasattr(models, "GradeLedger")


def test_schemas_import():
    from app.modules.m06_labs_evaluator import schemas
    assert hasattr(schemas, "AssignmentCreate")
    assert hasattr(schemas, "AssignmentResponse")
    assert hasattr(schemas, "SubmissionCreate")
    assert hasattr(schemas, "SubmissionResponse")
    assert hasattr(schemas, "ReviewPanelResponse")
    assert hasattr(schemas, "RatifyRequest")
    assert hasattr(schemas, "GradeLedgerResponse")


def test_repository_import():
    from app.modules.m06_labs_evaluator import repository
    assert hasattr(repository, "AssignmentRepository")
    assert hasattr(repository, "SubmissionRepository")
    assert hasattr(repository, "EvaluationRepository")
    assert hasattr(repository, "GradeLedgerRepository")


def test_service_import():
    from app.modules.m06_labs_evaluator import service
    assert hasattr(service, "AssignmentService")
    assert hasattr(service, "SubmissionService")
    assert hasattr(service, "ReviewService")
    assert hasattr(service, "LabServiceError")


def test_router_import():
    from app.modules.m06_labs_evaluator import router
    assert hasattr(router, "router")


def test_ai_scan_import():
    from app.modules.m06_labs_evaluator.ai_scan import scan, AIScanResult
    assert callable(scan)
    assert AIScanResult is not None


def test_plagiarism_import():
    from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism, PlagiarismResult
    assert callable(compute_plagiarism)
    assert PlagiarismResult is not None


def test_rubric_scorer_import():
    from app.modules.m06_labs_evaluator.rubric_scorer import score_submission, RubricScoringResult
    assert callable(score_submission)
    assert RubricScoringResult is not None


def test_code_sandbox_import():
    from app.modules.m06_labs_evaluator.code_sandbox import run, SandboxResult
    assert callable(run)
    assert SandboxResult is not None


def test_static_analyser_import():
    from app.modules.m06_labs_evaluator.static_analyser import analyse, StaticAnalysisResult
    assert callable(analyse)
    assert StaticAnalysisResult is not None


def test_ast_similarity_import():
    from app.modules.m06_labs_evaluator.ast_similarity import compute_ast_similarity
    assert callable(compute_ast_similarity)


def test_report_export_import():
    from app.modules.m06_labs_evaluator.report_export import generate_csv_report
    assert callable(generate_csv_report)


def test_evaluate_task_import():
    from app.workers.heavy.evaluate_lab_submission import evaluate_lab_submission
    assert callable(evaluate_lab_submission)


# ===========================================================================
# 2. Config keys
# ===========================================================================

def test_config_has_m06_keys():
    from app.config import settings
    assert isinstance(settings.M06_AI_SCAN_THRESHOLD, float)
    assert 0.0 < settings.M06_AI_SCAN_THRESHOLD <= 1.0
    assert isinstance(settings.M06_PLAGIARISM_THRESHOLD, float)
    assert 0.0 < settings.M06_PLAGIARISM_THRESHOLD <= 1.0
    assert isinstance(settings.M06_CODE_TIMEOUT_SECONDS, int)
    assert settings.M06_CODE_TIMEOUT_SECONDS > 0
    assert isinstance(settings.M06_MAX_CODE_OUTPUT_CHARS, int)
    assert settings.M06_MAX_CODE_OUTPUT_CHARS > 0


# ===========================================================================
# 3. Celery task registration
# ===========================================================================

def test_celery_includes_m06_task():
    from app.workers.celery_app import celery_app
    include = celery_app.conf.include
    assert "app.workers.heavy.evaluate_lab_submission" in include, (
        "evaluate_lab_submission not found in Celery include list"
    )


# ===========================================================================
# 4. Router mount in FastAPI app
# ===========================================================================

def test_labs_router_is_mounted():
    from app.main import app
    routes = [getattr(r, "path", "") for r in app.routes]
    m06_routes = [p for p in routes if p.startswith("/labs")]
    assert len(m06_routes) > 0, (
        f"/labs prefix not found in app routes. Found: {routes}"
    )


def test_key_endpoints_registered():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    expected = [
        "/labs/assignments",
        "/labs/assignments/{assignment_id}",
        "/labs/assignments/{assignment_id}/publish",
        "/labs/assignments/{assignment_id}/close",
        "/labs/assignments/{assignment_id}/submissions",
        "/labs/submissions/{submission_id}/review",
        "/labs/submissions/{submission_id}/scores",
        "/labs/submissions/{submission_id}/ratify",
        "/labs/submissions/{submission_id}/file-url",
        "/labs/assignments/{assignment_id}/report",
        "/labs/jobs/{job_id}",
        "/labs/student/assignments",
        "/labs/student/assignments/{assignment_id}",
        "/labs/student/assignments/{assignment_id}/submit",
        "/labs/student/submissions/my",
        "/labs/student/submissions/{submission_id}/result",
    ]
    for path in expected:
        assert path in paths, f"Expected route '{path}' not found in app routes"


# ===========================================================================
# 5. Audit event types
# ===========================================================================

def test_m06_audit_event_types_defined():
    from app.core.audit_log.models import AuditEventType
    expected = [
        "LAB_ASSIGNMENT_CREATED",
        "LAB_ASSIGNMENT_UPDATED",
        "LAB_ASSIGNMENT_PUBLISHED",
        "LAB_ASSIGNMENT_CLOSED",
        "LAB_SUBMISSION_RECEIVED",
        "LAB_SUBMISSION_FLAGGED",
        "LAB_EVAL_QUEUED",
        "LAB_EVAL_COMPLETED",
        "LAB_EVAL_FAILED",
        "LAB_SCORES_UPDATED",
        "LAB_SUBMISSION_RATIFIED",
        "LAB_REPORT_REQUESTED",
        "LAB_REPORT_COMPLETED",
    ]
    defined = {e.value for e in AuditEventType}
    for name in expected:
        assert name in defined, f"AuditEventType.{name} not defined"


# ===========================================================================
# 6. Grade ledger human-gate invariant (structural)
# ===========================================================================

def test_grade_ledger_has_submission_unique_constraint():
    """GradeLedger must have a UNIQUE constraint on submission_id."""
    from app.modules.m06_labs_evaluator.models import GradeLedger
    constraints = GradeLedger.__table_args__
    unique_cols = set()
    for c in constraints:
        from sqlalchemy import UniqueConstraint
        if isinstance(c, UniqueConstraint):
            for col in c.columns:
                unique_cols.add(col.name)
    assert "submission_id" in unique_cols, (
        "GradeLedger must have a UNIQUE constraint on submission_id to prevent double ratification"
    )


# ===========================================================================
# 7. Rubric scorer — dict-wrapped AI response parsing
# ===========================================================================

def test_parse_response_accepts_dict_wrapped_scores():
    """_parse_response must unwrap {"scores": [...]} without raising."""
    import json
    from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response

    rubric = [
        {"criterion_id": "c1", "name": "Quality", "max_marks": 10, "weight": 1.0},
        {"criterion_id": "c2", "name": "Clarity",  "max_marks": 5,  "weight": 0.5},
    ]
    # Simulate an LLM that wraps the array in {"scores": [...]}
    wrapped = json.dumps({
        "scores": [
            {"criterion_id": "c1", "ai_score": 8.0, "ai_justification": "Good work."},
            {"criterion_id": "c2", "ai_score": 4.0, "ai_justification": "Clear writing."},
        ]
    })

    result = _parse_response(wrapped, rubric)

    assert len(result) == 2
    assert result[0].criterion_id == "c1"
    assert result[0].ai_score == 8.0
    assert result[1].criterion_id == "c2"
    assert result[1].ai_score == 4.0


def test_parse_response_accepts_bare_array():
    """_parse_response still handles a bare JSON array (original format)."""
    import json
    from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response

    rubric = [
        {"criterion_id": "c1", "name": "Quality", "max_marks": 10, "weight": 1.0},
    ]
    bare = json.dumps([
        {"criterion_id": "c1", "ai_score": 7.5, "ai_justification": "Solid."},
    ])

    result = _parse_response(bare, rubric)

    assert len(result) == 1
    assert result[0].ai_score == 7.5


def test_parse_response_rejects_unrecognised_dict():
    """A dict with no recognised array key must still raise ValueError."""
    import json, pytest
    from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response

    rubric = [{"criterion_id": "c1", "name": "Q", "max_marks": 10, "weight": 1.0}]
    bad = json.dumps({"unknown_key": "not a list"})

    with pytest.raises(ValueError, match="Expected JSON array"):
        _parse_response(bad, rubric)


def test_parse_response_accepts_criteria_key():
    """Groq often wraps under 'criteria' — must not raise."""
    import json
    from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response

    rubric = [
        {"criterion_id": "c1", "name": "Q", "max_marks": 10, "weight": 1.0},
        {"criterion_id": "c2", "name": "C", "max_marks": 5,  "weight": 0.5},
    ]
    wrapped = json.dumps({
        "criteria": [
            {"criterion_id": "c1", "ai_score": 9.0, "ai_justification": "Strong."},
            {"criterion_id": "c2", "ai_score": 4.0, "ai_justification": "Clear."},
        ]
    })
    result = _parse_response(wrapped, rubric)
    assert len(result) == 2
    assert result[0].ai_score == 9.0


def test_parse_response_accepts_criterion_id_keyed_dict():
    """Groq may key the dict by criterion_id: {"c1": {ai_score:…}, …}."""
    import json
    from app.modules.m06_labs_evaluator.rubric_scorer import _parse_response

    rubric = [
        {"criterion_id": "c1", "name": "Q", "max_marks": 10, "weight": 1.0},
        {"criterion_id": "c2", "name": "C", "max_marks": 5,  "weight": 0.5},
    ]
    keyed = json.dumps({
        "c1": {"ai_score": 7.0, "ai_justification": "Adequate."},
        "c2": {"ai_score": 3.5, "ai_justification": "Needs work."},
    })
    result = _parse_response(keyed, rubric)
    assert len(result) == 2
    scores_by_id = {s.criterion_id: s for s in result}
    assert scores_by_id["c1"].ai_score == 7.0
    assert scores_by_id["c2"].ai_score == 3.5


def test_grade_ledger_submission_fk_is_restrict():
    """GradeLedger FK to submissions must use ondelete=RESTRICT."""
    from app.modules.m06_labs_evaluator.models import GradeLedger
    for col in GradeLedger.__table__.columns:
        for fk in col.foreign_keys:
            if "submissions" in fk.target_fullname:
                assert fk.ondelete and fk.ondelete.upper() == "RESTRICT", (
                    "GradeLedger FK to submissions must use ondelete=RESTRICT"
                )
                return
    raise AssertionError("No FK to submissions found in GradeLedger")


# ===========================================================================
# 8. M06-BUG-005 — Celery async event-loop fix smoke tests
# ===========================================================================

def test_worker_engine_uses_null_pool():
    """_make_async_engine must use NullPool.

    asyncpg binds pool objects to the event loop that created them.  Celery
    creates a new event loop per asyncio.run() call.  A pooled engine reused
    across invocations raises 'Future attached to a different loop'.  NullPool
    prevents this by never holding connections between tasks.
    """
    import asyncio
    from sqlalchemy.pool import NullPool
    from app.workers.heavy.evaluate_lab_submission import _make_async_engine

    engine = _make_async_engine()
    try:
        assert isinstance(engine.pool, NullPool), (
            f"Expected NullPool, got {type(engine.pool).__name__}. "
            "Without NullPool, Celery workers crash on the second task invocation."
        )
    finally:
        asyncio.run(engine.dispose())


def test_worker_has_no_cached_global_engine():
    """evaluate_lab_submission module must not expose a cached _async_engine global.

    A module-level engine cache is the root cause of M06-BUG-005: the cached
    engine's asyncpg pool is bound to the first invocation's event loop and
    raises RuntimeError on subsequent Celery task invocations.
    """
    import app.workers.heavy.evaluate_lab_submission as worker_mod
    assert not hasattr(worker_mod, "_async_engine"), (
        "_async_engine global found — remove it; use _make_async_engine() per invocation instead."
    )


def test_text_extractor_rejects_unsupported_extension():
    """extract_text must return ('', error_message) for unsupported types, not a placeholder."""
    from app.modules.m06_labs_evaluator.text_extractor import extract_text

    text, err = extract_text("tenant/submissions/file.xyz")
    assert text == "", "Expected empty string for unsupported file type"
    assert err is not None and len(err) > 0, "Expected a non-empty error message"
    assert "Unsupported" in err or "unsupported" in err.lower(), (
        f"Error message should mention unsupported type, got: {err!r}"
    )
