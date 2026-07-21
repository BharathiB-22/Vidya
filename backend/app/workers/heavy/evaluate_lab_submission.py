"""
Celery heavy-queue task: evaluate a lab submission (M06).

Flow for WRITTEN submissions:
  1. Load submission + assignment from DB.
  2. Transition submission status → EVALUATING.
  3. Run AI content scan (perplexity + burstiness).
  4. Run text plagiarism check (cosine similarity across cohort).
  5. Run LLM rubric scoring (per-criterion score + justification).
  6. Classify confidence (HIGH / MEDIUM / LOW).
  7. Write LabEvaluation row; update LabSubmission status → EVALUATED.
  8. Commit. Audit LAB_EVAL_COMPLETED.
  9. Notify faculty (fire-and-forget).

Flow for CODE submissions (additional steps):
  3b. Run code sandbox (subprocess, timeout).
  4b. Run static analysis (radon + pyflakes).
  5b. Run AST plagiarism check (normalised AST cosine similarity).
  6b. Run LLM rubric scoring on code + test results summary.
  (Steps 3, 4 for AI content scan of code also run.)

On failure:
  - Revert submission status → SUBMITTED (allows re-queue).
  - Audit LAB_EVAL_FAILED.
  - Re-raise so Celery marks the task FAILED.
"""
import asyncio
import logging
import sys
from uuid import UUID

from app.database import tenant_schema_scope
from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m06.evaluate_lab_submission")


def _make_async_engine():
    """Create a fresh async engine with NullPool for this task invocation.

    asyncpg binds connection-pool objects to the event loop that created them.
    Celery calls asyncio.run() per task, which creates and then closes a new
    event loop each time.  A pooled engine from a prior invocation holds
    Futures bound to the closed loop — accessing it from the next invocation's
    loop raises 'RuntimeError: Task got Future attached to a different loop'.
    NullPool avoids this entirely: connections are never held between tasks.
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.config import settings
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    # Re-apply the schema at the START OF EVERY TRANSACTION, not once per
    # session. A commit hands this connection back — NullPool closes it, a pool
    # recycles it — so anything after the first commit would otherwise run with
    # search_path = public, and a pooled connection could arrive still carrying
    # ANOTHER tenant's search_path. A commit cannot undo a per-BEGIN SET LOCAL.
    from app.database import bind_tenant_search_path
    bind_tenant_search_path(engine)
    return engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.evaluate_lab_submission",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def evaluate_lab_submission(
    *,
    job_id: str,
    submission_id: str,
    assignment_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Which tenant every transaction in this task belongs to. Held for the whole
    # run and dropped at the end of it: a worker process is long-lived and serves
    # every tenant in turn, and a schema left set is one the next task inherits.
    with tenant_schema_scope(schema_name):
        return asyncio.run(
            _run_evaluation(
                submission_id=UUID(submission_id),
                assignment_id=UUID(assignment_id),
                schema_name=schema_name,
            )
        )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_evaluation(
    submission_id: UUID,
    assignment_id: UUID,
    schema_name: str,
) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import settings
    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m06_labs_evaluator.models import (
        AIScanStatus,
        ConfidenceLevel,
        SubmissionStatus,
        SubmissionType,
    )
    from app.modules.m06_labs_evaluator.repository import (
        EvaluationRepository,
        SubmissionRepository,
    )

    engine = _make_async_engine()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            try:
                # 1. Load submission
                sub = await SubmissionRepository.get_by_id(submission_id, db=session)
                if sub is None:
                    raise ValueError(f"Submission {submission_id} not found in {schema_name!r}.")

                # Load assignment via direct query (no relationship loaded)
                from sqlalchemy import select
                from app.modules.m06_labs_evaluator.models import LabAssignment
                assignment_row = (
                    await session.execute(select(LabAssignment).where(LabAssignment.id == assignment_id))
                ).scalar_one_or_none()
                if assignment_row is None:
                    raise ValueError(f"Assignment {assignment_id} not found.")

                # 2. Transition → EVALUATING so UI shows in-progress state
                await SubmissionRepository.set_status(
                    submission_id, SubmissionStatus.EVALUATING, db=session
                )
                await session.commit()

                sub_type = sub.submission_type

                # 3. Get content to evaluate
                extraction_error: str | None = None
                content = sub.content_text or ""
                if not content and sub.content_url:
                    from app.modules.m06_labs_evaluator.text_extractor import extract_text
                    content, extraction_error = await asyncio.get_running_loop().run_in_executor(
                        None, lambda: extract_text(sub.content_url)
                    )
                    if extraction_error:
                        logger.warning(
                            "File extraction failed for submission %s: %s",
                            submission_id, extraction_error,
                        )

                # 4. AI content scan
                from app.modules.m06_labs_evaluator.ai_scan import scan as ai_scan
                scan_result = ai_scan(content, threshold=float(settings.M06_AI_SCAN_THRESHOLD))

                ai_scan_status = AIScanStatus.FLAGGED if scan_result.is_flagged else AIScanStatus.CLEAN
                await SubmissionRepository.set_ai_scan(
                    submission_id,
                    ai_scan_status,
                    {
                        "probability": scan_result.probability,
                        "confidence":  scan_result.confidence,
                        "highlights":  scan_result.highlights,
                    },
                    db=session,
                )
                await session.commit()

                # 4. Plagiarism check
                cohort_raw = await SubmissionRepository.get_cohort_texts(
                    assignment_id, submission_id, db=session
                )
                plagiarism_score: float = 0.0
                plagiarism_matches: list[dict] = []

                if sub_type == SubmissionType.CODE:
                    from app.modules.m06_labs_evaluator.ast_similarity import compute_ast_similarity
                    plag_result = compute_ast_similarity(
                        content,
                        cohort_raw,
                        threshold=float(assignment_row.plagiarism_threshold),
                    )
                else:
                    from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism
                    plag_result = compute_plagiarism(
                        content,
                        cohort_raw,
                        threshold=float(assignment_row.plagiarism_threshold),
                    )

                plagiarism_score   = plag_result.max_similarity
                plagiarism_matches = plag_result.matches

                # 5 (CODE only). Sandbox + static analysis + test cases
                test_results: list[dict] = []
                static_analysis: dict | None = None

                if sub_type == SubmissionType.CODE:
                    test_results, static_analysis = await _run_code_evaluation(
                        code=content,
                        test_cases=assignment_row.test_cases or [],
                        language=assignment_row.language or "python",
                    )

                # 6. LLM rubric scoring
                from app.modules.m06_labs_evaluator.rubric_scorer import (
                    CriterionScore, RubricScoringResult, score_submission,
                )

                if extraction_error:
                    # File could not be extracted — build advisory zero result so evaluators
                    # know this submission needs manual review.
                    rubric_def = assignment_row.rubric or []
                    extraction_note = f"File extraction failed — manual review required. ({extraction_error})"
                    scoring_result = RubricScoringResult(
                        criteria_scores=[
                            CriterionScore(
                                criterion_id=c["criterion_id"],
                                ai_score=0.0,
                                ai_justification=extraction_note,
                                max_marks=int(c["max_marks"]),
                            )
                            for c in rubric_def
                        ],
                        overall_ai_score=0.0,
                        confidence_level="LOW",
                        ai_model="extraction_failed",
                        prompt_hash="",
                    )
                else:
                    # Build question context for the LLM
                    question_ctx = assignment_row.description or assignment_row.title
                    if sub_type == SubmissionType.CODE and test_results:
                        pass_count = sum(1 for t in test_results if t.get("passed"))
                        total_tc   = len(test_results)
                        question_ctx += (
                            f"\n\n[Code evaluation: {pass_count}/{total_tc} test cases passed. "
                            f"Static analysis: complexity={static_analysis.get('complexity_score') if static_analysis else 'N/A'}]"
                        )

                    scoring_result = await score_submission(
                        question=question_ctx,
                        submission_text=content,
                        rubric=assignment_row.rubric or [],
                    )

                # 7. Build rubric_scores list for storage
                rubric_scores: list[dict] = [
                    {
                        "criterion_id":      cs.criterion_id,
                        "ai_score":          cs.ai_score,
                        "ai_justification":  cs.ai_justification,
                        "human_score":       None,
                        "human_note":        None,
                    }
                    for cs in scoring_result.criteria_scores
                ]

                # 8. Write LabEvaluation row
                await EvaluationRepository.create(
                    submission_id=submission_id,
                    rubric_scores=rubric_scores,
                    overall_ai_score=float(scoring_result.overall_ai_score),
                    confidence_level=ConfidenceLevel(scoring_result.confidence_level),
                    test_results=test_results if test_results else None,
                    static_analysis=static_analysis,
                    plagiarism_score=plagiarism_score,
                    plagiarism_matches=plagiarism_matches if plagiarism_matches else None,
                    ai_model=scoring_result.ai_model,
                    prompt_hash=scoring_result.prompt_hash,
                    db=session,
                )

                # 9. Update submission status → EVALUATED
                await SubmissionRepository.set_status(
                    submission_id, SubmissionStatus.EVALUATED, db=session
                )
                await session.commit()

                # 10. Audit
                await AuditService.log(
                    AuditEventType.LAB_EVAL_COMPLETED,
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    tenant_id=None,
                    schema_name=schema_name,
                    target_entity="lab_submission",
                    target_id=str(submission_id),
                    metadata={
                        "overall_ai_score": float(scoring_result.overall_ai_score),
                        "confidence":       scoring_result.confidence_level,
                        "ai_scan_status":   ai_scan_status.value,
                        "plagiarism_score": plagiarism_score,
                        "ai_model":         scoring_result.ai_model,
                    },
                )

                logger.info(
                    "Evaluation complete: submission=%s score=%.2f confidence=%s",
                    submission_id, scoring_result.overall_ai_score, scoring_result.confidence_level
                )

                return {
                    "submission_id":    str(submission_id),
                    "overall_ai_score": float(scoring_result.overall_ai_score),
                    "confidence_level": scoring_result.confidence_level,
                    "ai_scan_status":   ai_scan_status.value,
                    "plagiarism_score": plagiarism_score,
                }

            except Exception as exc:
                failure_reason = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "Lab evaluation failed for submission %s: %s",
                    submission_id, failure_reason, exc_info=True,
                )

                # Revert submission to SUBMITTED so it can be re-queued.
                # session.rollback() keeps the same connection; SET search_path persists.
                try:
                    await session.rollback()
                    await SubmissionRepository.set_status(
                        submission_id, SubmissionStatus.SUBMITTED, db=session
                    )
                    await session.commit()
                except Exception as mark_exc:
                    logger.error(
                        "Could not revert submission %s to SUBMITTED: %s",
                        submission_id, mark_exc,
                    )

                try:
                    await AuditService.log(
                        AuditEventType.LAB_EVAL_FAILED,
                        actor_user_id=None,
                        actor_role="SYSTEM",
                        tenant_id=None,
                        schema_name=schema_name,
                        target_entity="lab_submission",
                        target_id=str(submission_id),
                        metadata={"error": failure_reason},
                    )
                except Exception:
                    pass

                raise

    finally:
        await engine.dispose()


async def _run_code_evaluation(
    code: str,
    test_cases: list[dict],
    language: str,
) -> tuple[list[dict], dict]:
    """
    Run code sandbox against test cases + static analysis.
    Returns (test_results, static_analysis).
    All execution is synchronous (subprocess) but called from async context.
    """
    import asyncio
    from app.modules.m06_labs_evaluator.code_sandbox import run as sandbox_run
    from app.modules.m06_labs_evaluator.static_analyser import analyse as static_analyse

    test_results: list[dict] = []

    # Run test cases sequentially (subprocess calls are CPU/IO bound)
    loop = asyncio.get_running_loop()

    for tc in test_cases:
        tc_id   = tc.get("id", "")
        tc_name = tc.get("name", tc_id)
        stdin   = tc.get("stdin", "")
        expected = str(tc.get("expected_stdout", "")).strip()
        points  = int(tc.get("points", 0))

        result = await loop.run_in_executor(
            None,
            lambda: sandbox_run(language, code, stdin)
        )

        actual = result.stdout.strip()
        passed = (not result.timed_out and result.exit_code == 0 and actual == expected)

        test_results.append({
            "id":             tc_id,
            "name":           tc_name,
            "passed":         passed,
            "actual_stdout":  result.stdout[:500],
            "error":          result.error or (result.stderr[:500] if result.stderr else None),
            "points_awarded": points if passed else 0,
            "timed_out":      result.timed_out,
        })

    # Static analysis (sync, fast)
    sa = await loop.run_in_executor(None, lambda: static_analyse(code))
    static_analysis_dict = {
        "complexity_score": sa.complexity_score,
        "complexity_label": sa.complexity_label,
        "issues": sa.issues,
        "parse_error": sa.parse_error,
    }

    return test_results, static_analysis_dict
