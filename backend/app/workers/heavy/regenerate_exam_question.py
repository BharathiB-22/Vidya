"""
Celery heavy-queue task: regenerate a single exam question in-place (M08).

Flow:
  1. Load ExamPaper + target ExamQuestion from DB.
  2. Validate paper is in an editable state (GENERATED or BOARD_RETURNED).
  3. Fetch course info, syllabus units (single unit), and course outcomes.
  4. Call question_generator.generate_questions() for 1 question of the same type.
  5. Update ExamQuestion in-place — preserve section_label; set is_edited=True.
  6. Audit EXAM_PAPER_QUESTION_REGENERATED with old/new text summary.
  7. Return {question_id, paper_id, status: "REGENERATED"}.

On failure:
  - The question row is untouched (no partial update committed).
  - VidyaTask.on_failure writes FAILED to task_jobs automatically.
  - Re-raise so Celery marks the task FAILED.
"""
import asyncio
import logging
import sys

from app.database import tenant_schema_scope
from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m08.regenerate_exam_question")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        # Re-apply the schema at the START OF EVERY TRANSACTION, not once per
        # session. A commit hands this connection back — NullPool closes it, a pool
        # recycles it — so anything after the first commit would otherwise run with
        # search_path = public, and a pooled connection could arrive still carrying
        # ANOTHER tenant's search_path. A commit cannot undo a per-BEGIN SET LOCAL.
        from app.database import bind_tenant_search_path
        bind_tenant_search_path(_async_engine)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.regenerate_exam_question",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def regenerate_exam_question(
    *,
    job_id:      str,
    paper_id:    str,
    question_id: str,
    schema_name: str,
    instruction: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Which tenant every transaction in this task belongs to. Held for the whole
    # run and dropped at the end of it: a worker process is long-lived and serves
    # every tenant in turn, and a schema left set is one the next task inherits.
    with tenant_schema_scope(schema_name):
        return asyncio.run(
            _run_regeneration(
                paper_id=paper_id,
                question_id=question_id,
                schema_name=schema_name,
                instruction=instruction,
            )
        )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_regeneration(
    *,
    paper_id:    str,
    question_id: str,
    schema_name: str,
    instruction: str | None,
) -> dict:
    from uuid import UUID
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m08_exam_setter.models import ExamPaperStatus
    from app.modules.m08_exam_setter.question_generator import generate_questions
    from app.modules.m08_exam_setter.repository import (
        ExamPaperRepository,
        ExamQuestionRepository,
    )

    engine       = _get_async_engine()
    paper_uuid   = UUID(paper_id)
    question_uuid = UUID(question_id)

    _EDITABLE = {ExamPaperStatus.GENERATED.value, ExamPaperStatus.BOARD_RETURNED.value}

    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            # 1. Load paper and question
            paper = await ExamPaperRepository.get_by_id(paper_uuid, db=session)
            if paper is None:
                raise ValueError(
                    f"ExamPaper {paper_id} not found in schema {schema_name!r}."
                )

            question = await ExamQuestionRepository.get_by_id(question_uuid, db=session)
            if question is None:
                raise ValueError(
                    f"ExamQuestion {question_id} not found."
                )
            if question.exam_paper_id != paper_uuid:
                raise ValueError(
                    f"ExamQuestion {question_id} does not belong to paper {paper_id}."
                )

            # 2. Validate editable state
            if paper.status not in _EDITABLE:
                raise ValueError(
                    f"Paper {paper_id} is in status {paper.status!r} — "
                    f"regeneration only allowed when GENERATED or BOARD_RETURNED."
                )

            old_text = (question.question_text or "")[:120]

            # 3. Fetch course info, syllabus units, and course outcomes
            from app.workers.heavy.generate_exam_paper import (
                _fetch_course_info,
                _fetch_course_outcomes,
                _fetch_syllabus_units,
            )

            course_info     = await _fetch_course_info(
                course_id=paper.course_id, session=session
            )
            course_outcomes = await _fetch_course_outcomes(
                course_id=paper.course_id, session=session
            )
            all_units = await _fetch_syllabus_units(
                course_id=paper.course_id,
                units_included=[question.unit_number],
                session=session,
            )

            # Narrow to just the target unit (fallback: keep all returned)
            target_units = [
                u for u in all_units
                if int(u.get("unit_no") or u.get("unit_number") or 0) == question.unit_number
            ] or all_units

            # 4. Generate 1 question of the same type
            q_type = (question.question_type or "SHORT_ANSWER").upper().replace(" ", "_")
            q_marks = question.marks or 2
            q_format = {q_type: 1}
            bloom_targets = dict(paper.requested_dist or {})
            exam_workflow = paper.exam_workflow or "BOARD_EXAM"

            merged_instruction = (
                instruction
                if instruction
                else (paper.special_instructions or "")
            )
            if instruction and paper.special_instructions:
                merged_instruction = f"{paper.special_instructions}\n{instruction}"

            questions_raw, ai_model, _ = await generate_questions(
                units=target_units,
                bloom_targets=bloom_targets,
                question_format=q_format,
                total_marks=q_marks,
                special_instructions=merged_instruction or None,
                course_title=course_info.get("title", ""),
                course_code=course_info.get("code", ""),
                exam_type=paper.exam_type or "END_SEM",
                section_config=None,          # no section constraint for single regen
                course_outcomes=course_outcomes,
                exam_workflow=exam_workflow,
            )

            if not questions_raw:
                raise ValueError(
                    "Question generator returned no questions during regeneration."
                )

            new_q = questions_raw[0]
            new_text = (new_q.get("question_text") or "")[:120]

            # 5. Update in-place — preserve section_label from original question
            updates = {
                "question_text":  new_q.get("question_text") or question.question_text,
                "options":        new_q.get("options"),
                "correct_option": new_q.get("correct_option"),
                "model_answer":   new_q.get("model_answer"),
                "marking_scheme": new_q.get("marking_scheme"),
                "bloom_level":    (new_q.get("bloom_level") or question.bloom_level or "REMEMBER").upper().strip(),
                "marks":          new_q.get("marks") or question.marks,
                "co_ids":         new_q.get("co_ids") or [],
                # section_label preserved: do NOT overwrite
                "is_edited":      True,
                "ai_generated":   True,
            }

            await ExamQuestionRepository.update_question(
                question_uuid, updates=updates, db=session
            )
            await session.commit()

            logger.info(
                "Regenerated question %s in paper %s via %s",
                question_id, paper_id, ai_model,
            )

            # 6. Audit
            await AuditService.log(
                AuditEventType.EXAM_PAPER_QUESTION_REGENERATED,
                actor_user_id=None,
                actor_role="SYSTEM",
                tenant_id=None,
                schema_name=schema_name,
                target_entity="exam_question",
                target_id=question_id,
                metadata={
                    "exam_paper_id": paper_id,
                    "ai_model":      ai_model,
                    "old_text":      old_text,
                    "new_text":      new_text,
                    "unit_number":   question.unit_number,
                    "question_type": q_type,
                    "instruction":   instruction,
                },
            )

            return {
                "question_id": question_id,
                "paper_id":    paper_id,
                "status":      "REGENERATED",
                "ai_model":    ai_model,
            }

        except Exception as exc:
            logger.error(
                "Regeneration failed for question %s in paper %s: %s",
                question_id, paper_id, exc, exc_info=True,
            )
            try:
                await session.rollback()
            except Exception:
                pass
            raise
