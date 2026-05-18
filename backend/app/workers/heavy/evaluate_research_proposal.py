"""
Celery heavy-queue task: evaluate a research problem proposal (M07).

Flow:
  1. Load ResearchProblem from tenant schema.
  2. Set status → PENDING_REVIEW (problem now under evaluation).
  3. Run novelty search (arXiv TF-IDF cosine similarity).
  4. Call LLM to score novelty, feasibility, clarity + recommendation.
  5. Write scores + recommendation to ResearchProblem; set status → PENDING_REVIEW.
  6. Commit. Audit RESEARCH_PROBLEM_AI_EVALUATED.

Human gate: status NEVER advances to ACCEPTED/REJECTED here.
Guide must call /problems/{id}/decide explicitly.
"""
import asyncio
import logging
import sys
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m07.evaluate_research_proposal")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _async_engine


@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.evaluate_research_proposal",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def evaluate_research_proposal(
    *,
    job_id: str,
    problem_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_proposal_evaluation(
            problem_id=UUID(problem_id),
            schema_name=schema_name,
        )
    )


async def _run_proposal_evaluation(problem_id: UUID, schema_name: str) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m07_research_supervision.models import (
        AIRecommendation,
        ProblemStatus,
        ResearchProblem,
    )
    from app.modules.m07_research_supervision.repository import ProblemRepository
    from app.modules.m07_research_supervision.novelty_search import compute_novelty
    from app.modules.m07_research_supervision.problem_generator import _call_llm
    import hashlib, json

    engine = _get_async_engine()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        problem = await ProblemRepository.get_by_id(problem_id, db=session)
        if problem is None:
            raise ValueError(f"ResearchProblem {problem_id} not found in {schema_name!r}.")

        # 1. Novelty search (zero-dep arXiv + TF-IDF)
        questions = [q.get("question", "") if isinstance(q, dict) else str(q)
                     for q in (problem.research_questions or [])]
        novelty = compute_novelty(problem.title, problem.abstract, questions)
        novelty_score = novelty.novelty_score

        # 2. LLM feasibility + clarity scoring
        prompt = (
            f"You are a senior research supervisor evaluating a student research proposal.\n\n"
            f"Title: {problem.title}\n\n"
            f"Abstract: {problem.abstract}\n\n"
            f"Research questions:\n"
            + "\n".join(f"- {q}" for q in questions)
            + f"\n\nNovelty pre-score: {novelty_score:.2f} (0=not novel, 1=very novel)\n\n"
            "Score FEASIBILITY (0-10): is the scope achievable in a graduate project?\n"
            "Score CLARITY (0-10): are the research questions well-defined and measurable?\n"
            "Give a RECOMMENDATION: ACCEPT, REVISE, or REJECT.\n"
            "Give brief REASONING (2-3 sentences).\n\n"
            'Respond in JSON: {"feasibility_score": float, "clarity_score": float, '
            '"recommendation": "ACCEPT|REVISE|REJECT", "reasoning": "..."}'
        )
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        raw, ai_model = await _call_llm(prompt)

        # Parse LLM JSON response
        try:
            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
        except Exception:
            data = {}

        feasibility_score = float(data.get("feasibility_score", 5.0))
        clarity_score = float(data.get("clarity_score", 5.0))
        raw_rec = str(data.get("recommendation", "REVISE")).upper()
        recommendation = raw_rec if raw_rec in ("ACCEPT", "REVISE", "REJECT") else "REVISE"
        reasoning = str(data.get("reasoning", ""))

        # 3. Write scores — status stays PENDING_REVIEW (human gate)
        await ProblemRepository.set_eval_scores(
            problem_id,
            novelty_score=novelty_score,
            feasibility_score=feasibility_score,
            clarity_score=clarity_score,
            ai_recommendation=recommendation,
            ai_reasoning=reasoning,
            ai_model=ai_model,
            prompt_hash=prompt_hash,
            new_status=ProblemStatus.PENDING_REVIEW.value,
            db=session,
        )
        await session.commit()

        # 4. Audit (AI-advisory only)
        await AuditService.log(
            AuditEventType.RESEARCH_PROBLEM_AI_EVALUATED,
            actor_user_id=None,
            actor_role="SYSTEM",
            tenant_id=None,
            schema_name=schema_name,
            target_entity="research_problem",
            target_id=str(problem_id),
            metadata={
                "novelty_score":    novelty_score,
                "feasibility_score": feasibility_score,
                "clarity_score":    clarity_score,
                "recommendation":   recommendation,
                "ai_model":         ai_model,
                "novelty_papers":   len(novelty.papers),
            },
        )

        logger.info(
            "Proposal evaluated: problem=%s novelty=%.2f feasibility=%.2f clarity=%.2f rec=%s",
            problem_id, novelty_score, feasibility_score, clarity_score, recommendation,
        )

        return {
            "problem_id":        str(problem_id),
            "novelty_score":     novelty_score,
            "feasibility_score": feasibility_score,
            "clarity_score":     clarity_score,
            "recommendation":    recommendation,
        }
