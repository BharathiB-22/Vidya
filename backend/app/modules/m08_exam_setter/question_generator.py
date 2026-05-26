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
# Marks per question type (defaults)
# ---------------------------------------------------------------------------

_DEFAULT_MARKS: dict[str, float] = {
    "MCQ":             2.0,
    "SHORT_ANSWER":    5.0,
    "LONG_ANSWER":    10.0,
    "PROBLEM_SOLVING": 8.0,
}

# ---------------------------------------------------------------------------
# Question templates for realistic mock generation
# ---------------------------------------------------------------------------

_Q_TEMPLATES: dict[tuple[str, str], str] = {
    ("MCQ", "REMEMBER"):   "Which of the following correctly defines {topic}?",
    ("MCQ", "UNDERSTAND"): "Which statement best explains {topic} in the context of {unit_title}?",
    ("MCQ", "APPLY"):      "When applying {topic} to a real-world scenario in {unit_title}, which approach is most appropriate?",
    ("MCQ", "ANALYSE"):    "Analysing {topic} in {unit_title}, which option correctly identifies its primary components?",
    ("MCQ", "EVALUATE"):   "Which criterion is most important when evaluating a {topic}-based solution?",
    ("MCQ", "CREATE"):     "To design a new system incorporating {topic}, what is the most effective first step?",

    ("SHORT_ANSWER", "REMEMBER"):   "Define {topic} and state its two most important properties.",
    ("SHORT_ANSWER", "UNDERSTAND"): "Explain the concept of {topic} and its significance in {unit_title}.",
    ("SHORT_ANSWER", "APPLY"):      "Describe how {topic} can be applied to solve a practical problem in {unit_title}.",
    ("SHORT_ANSWER", "ANALYSE"):    "Analyse the role of {topic} within {unit_title} and identify its key dependencies.",
    ("SHORT_ANSWER", "EVALUATE"):   "Evaluate the advantages and limitations of {topic} in real-world applications.",
    ("SHORT_ANSWER", "CREATE"):     "Propose a novel approach that uses {topic} to improve outcomes in {unit_title}.",

    ("LONG_ANSWER", "REMEMBER"):   (
        "Describe in detail the major aspects of {topic} as covered in {unit_title}. "
        "Include definitions, properties, and at least two illustrative examples."
    ),
    ("LONG_ANSWER", "UNDERSTAND"): (
        "Explain the concept of {topic} with suitable examples. "
        "Discuss its significance and typical use cases within {unit_title}."
    ),
    ("LONG_ANSWER", "APPLY"): (
        "Apply the principles of {topic} to the following scenario: a system in {unit_title} "
        "requires a structured solution. Provide a step-by-step answer with justification."
    ),
    ("LONG_ANSWER", "ANALYSE"): (
        "Critically analyse {topic} in the context of {unit_title}. "
        "Compare it with at least one alternative approach and identify strengths and limitations."
    ),
    ("LONG_ANSWER", "EVALUATE"): (
        "Evaluate two or more strategies for implementing {topic} within {unit_title}. "
        "Recommend the best approach with evidence-based justification."
    ),
    ("LONG_ANSWER", "CREATE"): (
        "Design a comprehensive solution that leverages {topic} to address a key challenge in {unit_title}. "
        "Include components, rationale, and expected outcomes."
    ),

    ("PROBLEM_SOLVING", "REMEMBER"):   "Using the standard procedure for {topic}, solve the following step-by-step problem related to {unit_title}.",
    ("PROBLEM_SOLVING", "UNDERSTAND"): "Interpret the following scenario involving {topic} in {unit_title} and provide a structured solution.",
    ("PROBLEM_SOLVING", "APPLY"):      "Apply the principles of {topic} to derive a solution for the following problem in {unit_title}. Show all working.",
    ("PROBLEM_SOLVING", "ANALYSE"):    "Analyse the following {topic} problem in {unit_title} using structured techniques and solve it with full justification.",
    ("PROBLEM_SOLVING", "EVALUATE"):   "A proposed solution for a {topic} problem in {unit_title} is given. Critically evaluate its correctness and suggest improvements.",
    ("PROBLEM_SOLVING", "CREATE"):     "Formulate and solve an original problem in {unit_title} that demonstrates your mastery of {topic}.",
}


def _make_mcq_options(topic: str) -> tuple[list[dict], str]:
    """Generate realistic MCQ options. Option A is always correct."""
    opts = [
        {"label": "A", "text": f"The formal definition and established principles of {topic}"},
        {"label": "B", "text": f"A broad approach that does not directly involve {topic}"},
        {"label": "C", "text": f"A method that partially applies {topic} but omits its core properties"},
        {"label": "D", "text": f"An alternative technique often confused with {topic}"},
    ]
    return opts, "A"


def _make_model_answer(qtype: str, bloom: str, topic: str, unit_title: str, marks: float) -> str:
    if qtype == "MCQ":
        return (
            f"Option A — {topic} is correctly characterized by its formal definition and "
            f"established principles within {unit_title}."
        )
    intros = {
        "REMEMBER": (
            f"{topic} is a core concept in {unit_title}. It is defined by its key properties "
            f"and standard terminology. Key points: (1) formal definition, (2) primary "
            f"characteristics, (3) standard use cases. [{marks:.0f} marks: award proportionally "
            f"for each key property with examples.]"
        ),
        "UNDERSTAND": (
            f"{topic} contributes to {unit_title} by enabling systematic problem-solving. "
            f"Its significance lies in connecting theoretical foundations to practical applications. "
            f"Relevant examples illustrate how {topic} is applied in standard scenarios."
        ),
        "APPLY": (
            f"Applying {topic} to the scenario — Step 1: identify relevant components. "
            f"Step 2: map {topic} principles to the problem context. "
            f"Step 3: derive and verify the solution. "
            f"Conclusion: {topic} provides a systematic approach for resolving challenges in {unit_title}."
        ),
        "ANALYSE": (
            f"Analysis of {topic} in {unit_title}: Primary components include its structural "
            f"elements, inter-dependencies, and operational constraints. "
            f"Compared with alternatives, {topic} offers greater consistency but requires "
            f"more setup. Key relationships and trade-offs should be identified with supporting evidence."
        ),
        "EVALUATE": (
            f"Evaluation of {topic}: Advantages include structured applicability and broad "
            f"industry adoption. Limitations include complexity in edge cases. "
            f"In {unit_title}, {topic} is most effective when applied to well-defined problems. "
            f"Recommended approach: [justify with domain-specific criteria]."
        ),
        "CREATE": (
            f"Proposed design using {topic}: Component 1 — core processing layer. "
            f"Component 2 — interface and integration module. "
            f"Rationale: leverages {topic} to address the primary challenge in {unit_title}. "
            f"Expected outcomes: improved efficiency and correctness. "
            f"Implementation steps: (1) define scope, (2) design components, (3) validate with test cases."
        ),
    }
    return intros.get(bloom, f"Model answer for {topic} in {unit_title}. Address all parts systematically.")


def _build_prompt(
    units: list[dict],
    bloom_targets: dict[str, float],
    question_format: dict[str, int],
    total_marks: int,
    special_instructions: str | None,
    course_title: str = "",
    course_code: str = "",
    exam_type: str = "END_SEM",
) -> str:
    """Build the LLM generation prompt."""
    course_header = ""
    if course_title:
        course_header = (
            f"Course: {course_code} — {course_title}\n"
            f"Exam type: {exam_type.replace('_', ' ')}\n\n"
        )

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

{course_header}SYLLABUS UNITS:
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
  question_text   (the full question text — specific, subject-relevant, no placeholders)
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
    Fallback question generation when no LLM key is configured.
    Produces structurally valid questions using actual unit/topic names.
    """
    import itertools

    bloom_cycle = itertools.cycle([
        lvl.upper() for lvl, pct in bloom_targets.items() if pct > 0
    ] or ["REMEMBER", "UNDERSTAND", "APPLY"])

    # Build flat (unit_dict, topic_str) pairs from all units
    topic_pairs: list[tuple[dict, str]] = []
    for unit in (units or []):
        unit_title = unit.get("title", "General Concepts")
        topics = unit.get("topics") or [unit_title]
        for topic in topics:
            topic_pairs.append((unit, str(topic)))

    if not topic_pairs:
        topic_pairs = [({"unit_no": 1, "title": "General Concepts"}, "Core Concepts")]

    topic_cycle = itertools.cycle(topic_pairs)
    sets_cycle  = itertools.cycle([["A", "B"], ["A", "B"], ["A"], ["B"]])

    def _make(qtype: str, marks: float) -> dict:
        unit, topic = next(topic_cycle)
        bloom       = next(bloom_cycle)
        sets        = next(sets_cycle)
        unit_no     = int(unit.get("unit_no") or unit.get("unit_number") or 1)
        unit_title  = unit.get("title", "General Concepts")

        key    = (qtype, bloom)
        q_text = _Q_TEMPLATES.get(key, "Answer the following on {topic} in {unit_title}.").format(
            topic=topic, unit_title=unit_title,
        )

        options, correct = None, None
        if qtype == "MCQ":
            options, correct = _make_mcq_options(topic)

        answer = _make_model_answer(qtype, bloom, topic, unit_title, marks)

        return {
            "unit_number":    unit_no,
            "co_code":        None,
            "bloom_level":    bloom,
            "question_type":  qtype,
            "question_text":  q_text,
            "marks":          marks,
            "model_answer":   answer,
            "marking_scheme": [
                {
                    "criterion":   "Accuracy",
                    "marks":       round(marks * 0.6, 1),
                    "description": "Correct and complete answer addressing all required points.",
                },
                {
                    "criterion":   "Explanation",
                    "marks":       round(marks * 0.3, 1),
                    "description": "Clear explanation with relevant examples.",
                },
                {
                    "criterion":   "Presentation",
                    "marks":       round(marks * 0.1, 1),
                    "description": "Well-organized and logically structured response.",
                },
            ],
            "set_membership": sets,
            "options":        options,
            "correct_option": correct,
        }

    questions: list[dict] = []
    for _ in range(question_format.get("mcq_count", 0)):
        questions.append(_make("MCQ", 2.0))
    for _ in range(question_format.get("short_count", 0)):
        questions.append(_make("SHORT_ANSWER", 5.0))
    for _ in range(question_format.get("long_count", 0)):
        questions.append(_make("LONG_ANSWER", 10.0))
    for _ in range(question_format.get("problem_count", 0)):
        questions.append(_make("PROBLEM_SOLVING", 8.0))

    return questions


async def generate_questions(
    units: list[dict],
    bloom_targets: dict[str, float],
    question_format: dict[str, int],
    total_marks: int,
    special_instructions: str | None = None,
    course_title: str = "",
    course_code: str = "",
    exam_type: str = "END_SEM",
) -> tuple[list[dict], str, str]:
    """
    Generate exam questions from syllabus units.

    Args:
        units:                list of unit dicts from syllabus JSONB
        bloom_targets:        {bloom_level → percentage}
        question_format:      {mcq_count, short_count, long_count, problem_count}
        total_marks:          target total marks for Set A
        special_instructions: optional faculty hint
        course_title:         course name for richer prompt context
        course_code:          course code (e.g. "CS301")
        exam_type:            exam type string (e.g. "END_SEM")

    Returns:
        (questions, ai_model, prompt_hash)
        questions is a list of normalised question dicts ready for bulk_create.
    """
    from app.config import settings

    no_keys = (not settings.GEMINI_API_KEY.strip()) and (not settings.GROQ_API_KEY.strip())

    if no_keys:
        logger.warning("No LLM API keys configured — using syllabus-aware fallback generation.")
        questions = _mock_questions(units, question_format, bloom_targets, total_marks)
        return questions, "mock", "mock"

    prompt = _build_prompt(
        units=units,
        bloom_targets=bloom_targets,
        question_format=question_format,
        total_marks=total_marks,
        special_instructions=special_instructions,
        course_title=course_title,
        course_code=course_code,
        exam_type=exam_type,
    )

    try:
        raw, model_name, prompt_hash = await _call_llm(prompt)
        raw_questions = _parse_questions(raw)
        questions = [_normalise_question(q) for q in raw_questions]
    except Exception as exc:
        logger.error("Question generation failed: %s — falling back to syllabus-aware generation.", exc)
        questions  = _mock_questions(units, question_format, bloom_targets, total_marks)
        model_name  = "mock-fallback"
        prompt_hash = "error"

    return questions, model_name, hashlib.sha256(
        json.dumps({"units": len(units), "format": question_format}).encode()
    ).hexdigest()[:16]
