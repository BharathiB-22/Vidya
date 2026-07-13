import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m01")

# ---------------------------------------------------------------------------
# Module-level async engine — lazy, cached, one per worker process.
# Mirrors the _get_sync_engine() pattern in base_task.py.
# ---------------------------------------------------------------------------

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        from app.config import settings
        # NullPool: no connection caching between asyncio.run() calls.
        # Prevents "Future attached to a different loop" on Windows --pool=solo.
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return _async_engine


# ---------------------------------------------------------------------------
# Credit normalization — the finalized structure MUST total exactly the
# program's configured credits (Part 4.2 / final-sprint requirement: never 119,
# never 127). The AI is asked to hit the target but does not always; this
# deterministic pass rebalances credits ±1 at a time across the most flexible
# courses first (electives → labs → projects/internships → core theory), each
# kept inside its valid per-course credit range, until the sum matches.
# ---------------------------------------------------------------------------

def _course_credit_bounds(course: dict) -> tuple[int, int]:
    # Mirrors compliance._check_course_credit_range. A mini-project may be worth
    # as little as 2 credits, so rebalancing must not push it up to 6.
    if (course.get("course_type") or "") in ("PROJECT", "INTERNSHIP"):
        return 2, 20   # UGC project/internship flexibility
    return 1, 6


def _rebalance_priority(course: dict) -> int:
    ct = (course.get("course_type") or "")
    if course.get("is_elective"):
        return 0
    if ct == "LAB":
        return 1
    if ct in ("PROJECT", "INTERNSHIP"):
        return 2
    return 3


def _basket_key(course: dict):
    """Grouping key for the alternatives of one elective paper, or None for a
    standalone course. An elective paper (e.g. "Elective 1") offers several
    interchangeable alternatives of which a student takes exactly ONE — so the
    paper contributes its credits only ONCE toward the program total, not once
    per alternative. Papers themselves are independent: three 3-credit papers in
    one semester contribute 9 credits, not 3."""
    name = (course.get("elective_basket_name") or "").strip()
    if not name:
        return None
    return (course.get("semester"), name)


_PAPER_LABEL_RE = re.compile(r"^elective\s+(\d+)$", re.IGNORECASE)


def _is_paper_label(name: str) -> bool:
    """True for names the AI already gave in positional form ("Elective 2")."""
    return _PAPER_LABEL_RE.match(name.strip()) is not None


def _paper_sort_key(name: str) -> tuple[int, str]:
    """Order papers within a semester. "Elective 2" must precede "Elective 10",
    which a plain lexicographic sort gets wrong. Names that are not positional
    labels sort after the labelled ones, alphabetically."""
    m = _PAPER_LABEL_RE.match(name.strip())
    return (int(m.group(1)), "") if m else (1_000_000, name.lower())


def _rebalance_reps(reps: list[dict], target_total: int) -> int:
    """Adjust the credits of the representative courses in place (±1 at a time,
    most-flexible first, within per-course bounds) so their sum equals
    target_total. Returns the residual (0 = exact)."""
    if not reps:
        return target_total
    delta = target_total - sum(c["credits"] for c in reps)
    if delta == 0:
        return 0
    order = sorted(range(len(reps)), key=lambda i: _rebalance_priority(reps[i]))
    guard = 0
    while delta != 0 and guard < 100_000:
        progressed = False
        for i in order:
            if delta == 0:
                break
            lo, hi = _course_credit_bounds(reps[i])
            if delta > 0 and reps[i]["credits"] < hi:
                reps[i]["credits"] += 1
                delta -= 1
                progressed = True
            elif delta < 0 and reps[i]["credits"] > lo:
                reps[i]["credits"] -= 1
                delta += 1
                progressed = True
        if not progressed:
            break
        guard += 1
    return delta


def normalize_total_credits(courses: list[dict], target_total: int) -> int:
    """Adjust course credits in place so the program's EFFECTIVE total equals
    target_total, where each elective basket counts ONCE (a student takes one
    course from it) — not once per option.

    Returns the residual (target − achieved); 0 means an exact match. A nonzero
    residual only happens when per-course bounds make the target unreachable.
    """
    if not courses or target_total <= 0:
        return target_total - sum(c["credits"] for c in courses)

    # Split into standalone courses (core + basket-less electives) and baskets.
    baskets: dict[tuple, list[dict]] = {}
    singles: list[dict] = []
    for c in courses:
        key = _basket_key(c)
        if key is None:
            singles.append(c)
        else:
            baskets.setdefault(key, []).append(c)

    # One representative per basket carries that basket's credit weight.
    reps = singles + [members[0] for members in baskets.values()]
    residual = _rebalance_reps(reps, target_total)

    # Keep every option inside a basket at the representative's credit value so
    # the basket is internally consistent (all options are interchangeable).
    for members in baskets.values():
        rep_credits = members[0]["credits"]
        for m in members[1:]:
            m["credits"] = rep_credits

    return residual


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.generate_program_structure",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_program_structure(
    *,
    job_id: str,
    program_id: str,
    tenant_id: str,
    schema_name: str,
    prompt_hint: str | None = None,
    ai_instructions: str | None = None,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_generation(
            program_id=UUID(program_id),
            schema_name=schema_name,
            prompt_hint=prompt_hint,
            ai_instructions=ai_instructions,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_generation(
    program_id: UUID,
    schema_name: str,
    prompt_hint: str | None,
    ai_instructions: str | None = None,
) -> dict:
    from sqlalchemy import text, update as sql_update
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.m01_program_advisor.ai_provider import (
        ProgramGenerationContext,
        get_structure_provider,
    )
    from app.modules.m01_program_advisor.compliance import (
        CourseNode,
        detect_prerequisite_cycles,
    )
    from app.modules.m01_program_advisor.electives import is_basket_placeholder
    from app.modules.m01_program_advisor.models import Course as CourseModel, ProgramStatus
    from app.modules.m01_program_advisor.repository import (
        CoursePrerequisiteRepository,
        CourseRepository,
        ElectiveBasketRepository,
        ProgramOutcomeRepository,
        ProgramRepository,
    )
    from app.modules.m01_program_advisor.schemas import CourseCreate, ProgramOutcomeCreate

    engine = _get_async_engine()

    async with AsyncSession(engine, expire_on_commit=False) as session:

        # Tenant isolation — all repository queries are schema-less;
        # search_path resolves them to the correct tenant schema.
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        # ------------------------------------------------------------------
        # Load program
        # ------------------------------------------------------------------
        program = await ProgramRepository.get_by_id(program_id, db=session)
        if program is None:
            raise ValueError(f"Program {program_id} not found in schema {schema_name!r}.")

        # ------------------------------------------------------------------
        # Load existing outcomes — codes are preserved; only new codes added
        # ------------------------------------------------------------------
        existing_outcomes = await ProgramOutcomeRepository.list_by_program(
            program_id, db=session
        )
        existing_codes = {o.code for o in existing_outcomes}

        # ------------------------------------------------------------------
        # Build generation context and call Gemini
        # ------------------------------------------------------------------
        ctx = ProgramGenerationContext(
            degree_type=program.degree_type,
            department=program.department,
            duration_years=program.duration_years,
            total_credits=program.total_credits,
            prompt_hint=prompt_hint,
            ai_instructions=ai_instructions or program.ai_instructions,
            existing_outcome_codes=list(existing_codes),
        )

        provider = get_structure_provider()
        result = await provider.generate_structure(ctx)

        # ------------------------------------------------------------------
        # An elective basket is a SLOT, not a subject — drop any "course" that is
        # really the slot itself.
        #
        # Asked for an elective paper and its alternatives, a model will sometimes
        # return both: "Elective 1" as a course, AND Artificial Intelligence, Data
        # Mining, Cloud Computing as courses inside it. The slot then reaches the
        # curriculum with a course code and a course type, is handed an official
        # syllabus to generate, and stands in the approve gate blocking the whole
        # curriculum until somebody approves a syllabus for a subject nobody teaches.
        # Exactly this produced MCA305 "Elective 1" and MCA308 "Elective 2".
        #
        # Dropped HERE, before the credit rebalance and the prerequisite graph, so a
        # slot never counts toward the programme's credits and nothing is left
        # pointing at it. The basket itself is still created below, from
        # elective_basket_name — which is where a slot belongs.
        # ------------------------------------------------------------------
        slots = [
            c for c in result.courses
            if is_basket_placeholder(c.get("title"), c.get("elective_basket_name"))
        ]
        if slots:
            dropped = {id(c) for c in slots}
            result.courses = [c for c in result.courses if id(c) not in dropped]
            logger.info(
                "m01.generate: dropped %d elective-slot placeholder course(s) %s — a "
                "basket is not a subject (program=%s)",
                len(slots), [c.get("title") for c in slots], program_id,
            )

        # ------------------------------------------------------------------
        # Enforce exact total credits — rebalance the AI output so the program's
        # EFFECTIVE total (each elective basket counted once) equals
        # program.total_credits before anything is persisted or checked.
        # ------------------------------------------------------------------
        def _effective_total(cs: list[dict]) -> int:
            total, seen = 0, set()
            for c in cs:
                key = _basket_key(c)
                if key is not None:
                    if key in seen:
                        continue
                    seen.add(key)
                total += c["credits"]
            return total

        pre_eff = _effective_total(result.courses)
        residual = normalize_total_credits(result.courses, program.total_credits)
        post_eff = _effective_total(result.courses)
        if pre_eff != post_eff:
            logger.info(
                "m01.generate: rebalanced effective credits %d -> %d (target=%d, program=%s)",
                pre_eff, post_eff, program.total_credits, program_id,
            )
        if residual != 0:
            logger.warning(
                "m01.generate: could not reach exact total credits "
                "(target=%d, achieved=%d, residual=%d, program=%s)",
                program.total_credits, post_eff, residual, program_id,
            )

        # ------------------------------------------------------------------
        # Cycle detection on AI output — fail fast before any DB write
        # ------------------------------------------------------------------
        temp_ids = {c["code"]: UUID(int=i) for i, c in enumerate(result.courses)}
        ai_nodes = [
            CourseNode(
                id=temp_ids[c["code"]],
                code=c["code"],
                credits=c["credits"],
                semester=c["semester"],
                is_elective=c["is_elective"],
                prerequisite_course_ids=[
                    temp_ids[pc]
                    for pc in c.get("prerequisite_codes", [])
                    if pc in temp_ids
                ],
            )
            for c in result.courses
        ]
        cycle_violations = detect_prerequisite_cycles(ai_nodes)
        if cycle_violations:
            msgs = "; ".join(v.message for v in cycle_violations)
            raise ValueError(f"AI output contains circular prerequisites: {msgs}")

        # ------------------------------------------------------------------
        # Idempotency: delete stale AI-generated courses before re-inserting.
        # Human-authored courses (is_ai_generated=False) are never touched.
        # ------------------------------------------------------------------
        deleted = await CourseRepository.delete_ai_generated(program_id, db=session)
        if deleted:
            logger.info(
                "m01.generate: cleared %d stale ai courses (program=%s)",
                deleted, program_id,
            )

        # Baskets left with zero courses after that deletion are stale AI
        # output from a previous generation run -- clean them up too so
        # regeneration doesn't accumulate empty duplicate baskets.
        empty_basket_ids = (await session.execute(text(
            """
            SELECT b.id FROM elective_baskets b
            LEFT JOIN courses c ON c.elective_basket_id = b.id
            WHERE b.program_id = :pid
            GROUP BY b.id
            HAVING COUNT(c.id) = 0
            """
        ), {"pid": str(program_id)})).scalars().all()
        for basket_id in empty_basket_ids:
            await ElectiveBasketRepository.delete(basket_id, db=session)

        # ------------------------------------------------------------------
        # Elective papers. Each distinct elective_basket_name within a semester is
        # ONE curriculum course: Semester 3 holding Elective 1, Elective 2 and
        # Elective 3 contributes 3 + 3 + 3 = 9 credits, because the student takes
        # all three papers and chooses one alternative inside each. Collapsing the
        # alternatives under a single shared name would lose two thirds of that.
        #
        # Papers are named positionally — "Elective 1", "Elective 2" — since that
        # is what the curriculum shows. Ordering is by the AI's own name so the
        # numbering is stable rather than dependent on which alternative happened
        # to appear first in the course list. When the AI already labelled a paper
        # "Elective 2" the label is redundant as a description and dropped.
        #
        # A paper's credits come from its alternatives, which
        # normalize_total_credits has already equalized across the group.
        # ------------------------------------------------------------------
        papers: dict[int, dict[str, int]] = {}
        for c in result.courses:
            basket_name = (c.get("elective_basket_name") or "").strip()
            if not basket_name:
                continue
            papers.setdefault(c["semester"], {}).setdefault(basket_name, c["credits"])

        basket_name_to_id: dict[tuple[int, str], UUID] = {}
        for semester in sorted(papers):
            for position, ai_name in enumerate(sorted(papers[semester], key=_paper_sort_key), start=1):
                canonical = f"Elective {position}"
                basket = await ElectiveBasketRepository.create(
                    program_id, semester, canonical,
                    None if _is_paper_label(ai_name) else ai_name,
                    program.created_by_user_id,
                    credits=papers[semester][ai_name], db=session,
                )
                basket_name_to_id[(semester, ai_name)] = basket.id

        # ------------------------------------------------------------------
        # Bulk create new AI courses, then flag them as AI-generated.
        # Flagging is done via a targeted UPDATE on the new IDs only —
        # mark_all_ai_generated would incorrectly stamp human-authored courses.
        # ------------------------------------------------------------------
        course_creates = [
            CourseCreate(
                code=c["code"],
                title=c["title"],
                credits=c["credits"],
                semester=c["semester"],
                course_type=c.get("course_type"),
                is_elective=c["is_elective"],
                elective_basket_id=basket_name_to_id.get(
                    (c["semester"], (c.get("elective_basket_name") or "").strip())
                ) if c.get("elective_basket_name") else None,
                hours_lecture=c["hours_lecture"],
                hours_tutorial=c["hours_tutorial"],
                hours_practical=c["hours_practical"],
                description=c.get("description"),
            )
            for c in result.courses
        ]
        new_courses = await CourseRepository.bulk_create(program_id, course_creates, db=session)

        if new_courses:
            new_ids = [c.id for c in new_courses]
            await session.execute(
                sql_update(CourseModel)
                .where(CourseModel.id.in_(new_ids))
                .values(is_ai_generated=True)
            )

        logger.info(
            "m01.generate: created %d ai courses (program=%s)",
            len(new_courses), program_id,
        )

        # ------------------------------------------------------------------
        # Build full code→id map (human + AI) for prerequisite resolution
        # ------------------------------------------------------------------
        all_courses = await CourseRepository.list_by_program(program_id, db=session)
        code_to_id = {c.code: c.id for c in all_courses}

        # ------------------------------------------------------------------
        # Wire prerequisites
        # ------------------------------------------------------------------
        prereq_count = 0
        for ai_dict, db_course in zip(result.courses, new_courses):
            prereq_ids = [
                code_to_id[pc]
                for pc in ai_dict.get("prerequisite_codes", [])
                if pc in code_to_id and code_to_id[pc] != db_course.id
            ]
            if prereq_ids:
                await CoursePrerequisiteRepository.bulk_create(
                    db_course.id, prereq_ids, db=session
                )
                prereq_count += len(prereq_ids)

        # ------------------------------------------------------------------
        # Add new AI outcomes — skip codes already present (human-edited)
        # ------------------------------------------------------------------
        new_outcome_creates = [
            ProgramOutcomeCreate(
                code=o["code"],
                description=o["description"],
                bloom_level=o.get("bloom_level"),
                display_order=o.get("display_order", 0),
            )
            for o in result.outcomes
            if o["code"] not in existing_codes
        ]
        new_outcomes = []
        if new_outcome_creates:
            new_outcomes = await ProgramOutcomeRepository.bulk_create(
                program_id, new_outcome_creates, db=session
            )
        logger.info(
            "m01.generate: added %d new outcomes (program=%s)",
            len(new_outcomes), program_id,
        )

        # ------------------------------------------------------------------
        # Update program — record AI metadata and hand the draft BACK to the Dean
        #
        # Phase A: generation lands in DRAFT, never PENDING_APPROVAL. AI advises;
        # a human decides. The Dean reviews what the model produced and submits
        # it to the governance authority themselves — nothing reaches the review
        # queue without a person putting it there.
        # ------------------------------------------------------------------
        await ProgramRepository.update(
            program_id,
            {
                "ai_model":   result.model_used,
                "prompt_hash": result.prompt_hash,
                "status":     ProgramStatus.DRAFT,
                "updated_at": datetime.now(timezone.utc),
            },
            db=session,
        )

        await session.commit()

    return {
        "program_id":          str(program_id),
        "courses_created":     len(new_courses),
        "outcomes_added":      len(new_outcomes),
        "prerequisites_wired": prereq_count,
        "model_used":          result.model_used,
        "provider":            result.provider_name,
    }
