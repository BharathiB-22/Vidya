"""
M08 Exam Setter — Question generator.

Generates exam questions from syllabus unit data using an LLM.
Follows the same Gemini → Groq fallback pattern as M06 rubric_scorer.

Output structure per question:
  {
    unit_number:    int,
    co_code:        str | None,
    bloom_level:    str,          # REMEMBER / UNDERSTAND / ... / CREATE
    question_type:  str,          # MCQ / SHORT_ANSWER / LONG_ANSWER / PROBLEM_SOLVING
    question_text:  str,
    options:        list | None,  # [{label, text}] for MCQ only
    correct_option: str | None,   # "A"/"B"/... for MCQ
    marks:          float,
    model_answer:   str,
    marking_scheme: list,         # [{criterion, marks, description}]
    set_membership: list[str],    # ["A","B"] or ["A"] or ["B"]
  }
"""
from __future__ import annotations

import hashlib
import json
import logging
import re

logger = logging.getLogger("vidya.m08.question_generator")

# ---------------------------------------------------------------------------
# Marks per question type (defaults; adjusted to hit total_marks target)
# ---------------------------------------------------------------------------

_DEFAULT_MARKS: dict[str, float] = {
    "MCQ":             2.0,
    "SHORT_ANSWER":    5.0,
    "LONG_ANSWER":    10.0,
    "PROBLEM_SOLVING": 8.0,
}


def _build_prompt(
    units: list[dict],
    bloom_targets: dict[str, float],
    question_format: dict[str, int],
    total_marks: int,
    special_instructions: str | None,
) -> str:
    """Build the LLM generation prompt."""
    unit_text = "\n".join(
        f"Unit {u.get('unit_no', u.get('unit_number', '?'))}: {u.get('title','')}\n"
        f"Topics: {', '.join(u.get('topics', []))}"
        for u in units
    )

    bloom_text = ", ".join(
        f"{lvl}: {pct:.0f}%"
        for lvl, pct in bloom_targets.items()
        if pct > 0
    )

    format_text = ", ".join(
        f"{qtype.replace('_',' ').title()}: {cnt}"
        for qtype, cnt in {
            "MCQ":             question_format.get("mcq_count", 0),
            "SHORT_ANSWER":    question_format.get("short_count", 0),
            "LONG_ANSWER":     question_format.get("long_count", 0),
            "PROBLEM_SOLVING": question_format.get("problem_count", 0),
        }.items()
        if cnt > 0
    )

    extra = f"\nSpecial instructions: {special_instructions}" if special_instructions else ""

    return f"""You are an experienced university examiner. Generate an exam question paper.

SYLLABUS UNITS:
{unit_text}

REQUIREMENTS:
- Total marks: {total_marks}
- Question format: {format_text}
- Bloom's taxonomy distribution: {bloom_text}
- Generate TWO sets (Set A and Set B) by varying question order and some question variants.
  Most questions can appear in both sets; vary at least 20% of questions between sets.{extra}

For EACH question output a JSON object with these fields:
  unit_number     (integer — which unit this question covers)
  bloom_level     (one of: REMEMBER, UNDERSTAND, APPLY, ANALYSE, EVALUATE, CREATE)
  question_type   (one of: MCQ, SHORT_ANSWER, LONG_ANSWER, PROBLEM_SOLVING)
  question_text   (the full question text)
  marks           (number — marks allocated to this question)
  model_answer    (clear, complete model answer)
  marking_scheme  (array of {{criterion: str, marks: number, description: str}})
  set_membership  (array — ["A","B"] if in both sets, ["A"] or ["B"] if set-specific)
  options         (array of {{label: str, text: str}} — only for MCQ questions)
  correct_option  (string "A"/"B"/... — only for MCQ questions)

Output a JSON array of question objects only. No extra text or markdown fences.
Ensure Bloom's distribution across questions matches the requested percentages within ±10%.
Ensure total marks across all questions in Set A equals {total_marks}.
"""


def _parse_questions(raw: str) -> list[dict]:
    """Extract and parse JSON array from LLM output."""
    raw = raw.strip()

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$",          "", raw)

    # Find first [ and last ] to isolate the array
    start = raw.find("[")
    end   = raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("LLM output does not contain a JSON array.")

    return json.loads(raw[start : end + 1])


def _normalise_question(q: dict, unit_number_fallback: int = 1) -> dict:
    """Normalise and validate a raw question dict from the LLM."""
    bloom   = (q.get("bloom_level") or "REMEMBER").upper()
    qtype   = (q.get("question_type") or "SHORT_ANSWER").upper().replace(" ", "_")
    marks   = float(q.get("marks") or _DEFAULT_MARKS.get(qtype, 5.0))
    membership = q.get("set_membership") or ["A", "B"]

    result: dict = {
        "unit_number":    int(q.get("unit_number") or unit_number_fallback),
        "co_code":        q.get("co_code"),
        "bloom_level":    bloom,
        "question_type":  qtype,
        "question_text":  str(q.get("question_text") or "").strip(),
        "marks":          marks,
        "model_answer":   str(q.get("model_answer") or "").strip(),
        "marking_scheme": q.get("marking_scheme") or [],
        "set_membership": list(membership),
        "options":        None,
        "correct_option": None,
    }

    if qtype == "MCQ":
        result["options"]        = q.get("options") or []
        result["correct_option"] = q.get("correct_option")

    return result


async def _call_llm(prompt: str) -> tuple[str, str, str]:
    """
    Call LLM with Gemini → Groq fallback.
    Returns (raw_text, model_name, prompt_hash).
    """
    from app.config import settings

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    provider    = settings.AI_PROVIDER

    async def _try_gemini() -> str:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        resp  = model.generate_content(prompt)
        return resp.text

    async def _try_groq() -> str:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        resp   = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.7,
        )
        return resp.choices[0].message.content

    if provider == "gemini":
        text = await _try_gemini()
        return text, settings.GEMINI_MODEL, prompt_hash

    if provider == "groq":
        text = await _try_groq()
        return text, settings.GROQ_MODEL, prompt_hash

    # fallback: Gemini first, then Groq
    try:
        text = await _try_gemini()
        return text, settings.GEMINI_MODEL, prompt_hash
    except Exception as gem_exc:
        logger.warning("Gemini failed (%s), falling back to Groq.", gem_exc)
        text = await _try_groq()
        return text, settings.GROQ_MODEL, prompt_hash


def _mock_questions(
    units: list[dict],
    question_format: dict[str, int],
    bloom_targets: dict[str, float],
    total_marks: int,
) -> list[dict]:
    """
    Mock question generation for dev/test when no LLM key is configured.
    Produces structurally valid but placeholder questions.
    """
    import itertools

    bloom_cycle = itertools.cycle([
        lvl for lvl, pct in bloom_targets.items()
        if pct > 0
    ] or ["REMEMBER", "UNDERSTAND", "APPLY"])

    questions = []
    mark_per_q = max(2.0, total_marks / max(
        1,
        question_format.get("mcq_count", 0) +
        question_format.get("short_count", 0) +
        question_format.get("long_count", 0) +
        question_format.get("problem_count", 0),
    ))

    def _make(qtype: str, unit: dict, bloom: str, marks: float, sets: list[str]) -> dict:
        unit_no = int(unit.get("unit_no") or unit.get("unit_number") or 1)
        title   = unit.get("title", "Topic")
        return {
            "unit_number":    unit_no,
            "co_code":        None,
            "bloom_level":    bloom.upper().strip(),
            "question_type":  qtype.upper().replace(" ", "_").strip(),
            "question_text":  f"[Mock] {qtype} question on {title} ({bloom})",
            "marks":          marks,
            "model_answer":   f"[Mock] Model answer for {title}",
            "marking_scheme": [{"criterion": "Accuracy", "marks": marks, "description": "Full marks for correct answer"}],
            "set_membership": sets,
            "options":        [{"label": l, "text": f"Option {l}"} for l in ["A","B","C","D"]] if qtype == "MCQ" else None,
            "correct_option": "A" if qtype == "MCQ" else None,
        }

    unit_cycle = itertools.cycle(units or [{"unit_no": 1, "title": "General", "topics": []}])
    sets_cycle = itertools.cycle([["A","B"], ["A","B"], ["A"], ["B"]])

    for _ in range(question_format.get("mcq_count", 0)):
        questions.append(_make("MCQ", next(unit_cycle), next(bloom_cycle), 2.0, next(sets_cycle)))
    for _ in range(question_format.get("short_count", 0)):
        questions.append(_make("SHORT_ANSWER", next(unit_cycle), next(bloom_cycle), 5.0, next(sets_cycle)))
    for _ in range(question_format.get("long_count", 0)):
        questions.append(_make("LONG_ANSWER", next(unit_cycle), next(bloom_cycle), 10.0, next(sets_cycle)))
    for _ in range(question_format.get("problem_count", 0)):
        questions.append(_make("PROBLEM_SOLVING", next(unit_cycle), next(bloom_cycle), 8.0, next(sets_cycle)))

    return questions


async def generate_questions(
    units: list[dict],
    bloom_targets: dict[str, float],
    question_format: dict[str, int],
    total_marks: int,
    special_instructions: str | None = None,
) -> tuple[list[dict], str, str]:
    """
    Generate exam questions from syllabus units.

    Args:
        units:                list of unit dicts from syllabus JSONB
        bloom_targets:        {bloom_level → percentage}
        question_format:      {mcq_count, short_count, long_count, problem_count}
        total_marks:          target total marks for Set A
        special_instructions: optional faculty hint

    Returns:
        (questions, ai_model, prompt_hash)
        questions is a list of normalised question dicts ready for bulk_create.
    """
    from app.config import settings

    no_keys = (not settings.GEMINI_API_KEY.strip()) and (not settings.GROQ_API_KEY.strip())

    if no_keys:
        logger.warning("No LLM API keys configured — using mock question generation.")
        questions = _mock_questions(units, question_format, bloom_targets, total_marks)
        return questions, "mock", "mock"

    prompt = _build_prompt(
        units=units,
        bloom_targets=bloom_targets,
        question_format=question_format,
        total_marks=total_marks,
        special_instructions=special_instructions,
    )

    try:
        raw, model_name, prompt_hash = await _call_llm(prompt)
        raw_questions = _parse_questions(raw)
        questions = [_normalise_question(q) for q in raw_questions]
    except Exception as exc:
        logger.error("Question generation failed: %s — falling back to mock.", exc)
        questions = _mock_questions(units, question_format, bloom_targets, total_marks)
        model_name  = "mock-fallback"
        prompt_hash = "error"

    return questions, model_name, hashlib.sha256(
        json.dumps({"units": len(units), "format": question_format}).encode()
    ).hexdigest()[:16]
