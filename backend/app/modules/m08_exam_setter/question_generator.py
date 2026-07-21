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
# Marks per question type (defaults when no section_config is supplied)
# ---------------------------------------------------------------------------

_DEFAULT_MARKS: dict[str, float] = {
    "MCQ":             2.0,
    "SHORT_ANSWER":    5.0,
    "LONG_ANSWER":    10.0,
    "PROBLEM_SOLVING": 8.0,
}

# Valid mark values used in section-based and custom generation (2, 5, 8, 10, 15)
_VALID_MARKS: frozenset[float] = frozenset({1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0})

# Question types allowed in mixed (non-MCQ-only) sections
_NON_MCQ_TYPES = ["SHORT_ANSWER", "LONG_ANSWER", "PROBLEM_SOLVING"]

# Board/final exam types that must never be MCQ-only
_BOARD_EXAM_TYPES: frozenset[str] = frozenset({
    "END_SEM", "BOARD_EXAM", "SUPPLEMENTARY", "REVALUATION",
})

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


def _type_for_marks(marks: float) -> str:
    """Infer a question type from a blueprint row's mark value (the blueprint
    specifies marks per question, not type). Low marks → short answer, higher
    marks → long answer."""
    if marks <= 2:
        return "SHORT_ANSWER"
    return "LONG_ANSWER"


def _type_for_row(category: str | None, marks: float) -> str:
    """Prefer an explicit blueprint category hint, else infer from marks."""
    cat = (category or "").lower()
    if "mcq" in cat or "objective" in cat or "multiple" in cat:
        return "MCQ"
    if "problem" in cat or "numeric" in cat:
        return "PROBLEM_SOLVING"
    if "long" in cat or "essay" in cat or "descriptive" in cat:
        return "LONG_ANSWER"
    if "short" in cat:
        return "SHORT_ANSWER"
    return _type_for_marks(marks)


# ---------------------------------------------------------------------------
# Template slots — the paper's structure as a flat, ordered list of positions
# ---------------------------------------------------------------------------

def _blueprint_slots(blueprint: list | None) -> list[dict]:
    """Expand a blueprint into one slot per question the paper must contain.

    A slot is a position in the printed paper: it fixes the unit, the marks, and
    the template block that owns the question. Generation fills slots rather than
    producing a loose bag of questions, which is what guarantees every question
    lands inside exactly one template block (no "Additional Questions" bucket).

    Slots are returned in printed-paper order: by the owning block's position
    first (blueprint rows are grouped by unit, so block order would otherwise be
    lost), then by the order rows appear within the blueprint.
    """
    slots: list[dict] = []
    # Choice-group ids for OR_CHOICE rows so the PDF pairs them. Start high to
    # avoid colliding with any LLM-assigned choice_group.
    or_group = 10000
    for entry in (blueprint or []):
        try:
            unit = int(entry.get("unit_number") or 1)
        except (TypeError, ValueError):
            unit = 1
        for row in (entry.get("rows") or []):
            count = int(row.get("count") or 0)
            marks = float(row.get("marks") or 0)
            if count <= 0 or marks <= 0:
                continue
            pattern = (row.get("choice_pattern") or "COMPULSORY").upper()
            cg: int | None = None
            if pattern == "OR_CHOICE":
                or_group += 1
                cg = or_group
            block_order = row.get("block_order")
            for _ in range(count):
                slots.append({
                    "unit_number":            unit,
                    "marks":                  marks,
                    "category":               row.get("category"),
                    "choice_group":           cg,
                    "block_id":      row.get("template_block_id"),
                    "subpart_index": row.get("subpart_index"),
                    "block_order":            10_000 if block_order is None else int(block_order),
                })

    # Stable sort by block position; rows without a block_order (legacy
    # blueprints) all share one sentinel and keep their original order.
    slots.sort(key=lambda s: s["block_order"])
    return slots


def _stamp_slot(q: dict, slot: dict) -> dict:
    """Pin a question onto its slot. The template is the contract: whatever the
    faculty asked for wins over whatever the model returned, so the printed
    structure and the mark totals always match the paper they designed.

    Only what the definition actually specified is forced — a Bloom's level or a
    difficulty the faculty left to inherit stays as the model chose it.
    """
    q["unit_number"]            = slot["unit_number"]
    q["unit_numbers"]           = slot.get("unit_numbers") or [slot["unit_number"]]
    q["marks"]                  = slot["marks"]
    q["choice_group"]           = slot["choice_group"]
    q["template_block_id"]      = slot.get("block_id")
    q["template_subpart_index"] = slot.get("subpart_index")

    if slot.get("question_type"):
        q["question_type"] = slot["question_type"]
    if slot.get("bloom"):
        q["bloom_level"] = str(slot["bloom"]).upper()
    if slot.get("difficulty"):
        q["difficulty"] = str(slot["difficulty"]).upper()
    # A definition that named its COs overrides the model's guess; AUTO leaves the
    # model's mapping alone.
    if slot.get("co_mode") == "SPECIFIC" and slot.get("co_ids"):
        q["co_ids"] = [str(c) for c in slot["co_ids"]]
    return q


def _bind_to_slots(questions: list[dict], slots: list[dict], fallback: list[dict]) -> list[dict]:
    """Assign generated questions to template slots, one per slot.

    Preference order per slot: a question already on the right unit AND marks,
    then any question on the right unit, then any remaining question. A slot the
    model under-delivered for is filled from `fallback` (slot-aligned mock
    questions), and questions the template has no room for are dropped — the
    paper contains exactly the questions the template asks for.
    """
    used: set[int] = set()

    def _pick(slot: dict) -> int | None:
        def _match(q: dict, exact: bool) -> bool:
            if int(q.get("unit_number") or 0) != int(slot["unit_number"]):
                return False
            return (not exact) or float(q.get("marks") or 0) == float(slot["marks"])

        for pred in (lambda q: _match(q, True), lambda q: _match(q, False), lambda _q: True):
            for i, q in enumerate(questions):
                if i not in used and pred(q):
                    return i
        return None

    bound: list[dict] = []
    filled = 0
    for i, slot in enumerate(slots):
        idx = _pick(slot)
        if idx is None:
            src = fallback[i] if i < len(fallback) else None
            if src is None:
                continue
            filled += 1
            bound.append(_stamp_slot(dict(src), slot))
            continue
        used.add(idx)
        bound.append(_stamp_slot(dict(questions[idx]), slot))

    if filled:
        logger.warning(
            "Model returned too few questions for the template — %d of %d slot(s) "
            "filled from fallback generation.", filled, len(slots),
        )
    surplus = len(questions) - len(used)
    if surplus > 0:
        logger.warning(
            "Model returned %d question(s) beyond the template's %d slot(s) — dropped.",
            surplus, len(slots),
        )
    return bound


def _build_prompt(
    units: list[dict],
    bloom_targets: dict[str, float],
    question_format: dict[str, int],
    total_marks: int,
    special_instructions: str | None,
    course_title: str = "",
    course_code: str = "",
    exam_type: str = "END_SEM",
    section_config: list | None = None,
    blueprint: list | None = None,
    course_outcomes: list | None = None,
    exam_workflow: str = "BOARD_EXAM",
    template_prompt: str | None = None,
    single_set: bool = False,
) -> str:
    """Build the LLM generation prompt with optional section and CO context."""
    course_header = ""
    if course_title:
        course_header = (
            f"Course: {course_code} — {course_title}\n"
            f"Exam type: {exam_type.replace('_', ' ')}\n"
            f"Workflow: {'Board Examination' if exam_workflow == 'BOARD_EXAM' else 'Internal Examination'}\n\n"
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

    # The template describes the paper position by position, so it outranks every
    # looser description below it.
    if template_prompt:
        format_block = template_prompt
    elif section_config:
        section_lines = []
        for s in sorted(section_config, key=lambda x: x.get("order", 0)):
            label      = s.get("label", "?")
            total_q    = s.get("total_q", 0)
            answer_q   = s.get("answer_q", total_q)
            marks_each = s.get("marks_each", 5.0)
            mcq_only   = s.get("mcq_only", False)
            instr      = s.get("instruction") or ""
            type_note  = "MCQ TYPE ONLY" if mcq_only else "mixed question types"
            answer_note = (
                f"Students answer all {total_q}"
                if answer_q == total_q
                else f"Students answer any {answer_q} of {total_q}"
            )
            section_lines.append(
                f"  Part {label} ({type_note}): {total_q} questions × {marks_each} marks each. "
                f"{answer_note}. {instr}"
                f"\n    → Set section_label=\"{label}\" on every question in this part."
            )
        format_block = (
            "SECTION STRUCTURE (generate exactly total_q questions per section):\n"
            + "\n".join(section_lines)
            + f"\n\nTotal marks for Set A: {total_marks}"
        )
    elif blueprint:
        bp_lines = []
        printed_total = 0.0
        evaluation_total = 0.0
        for entry in blueprint:
            unit_no = entry.get("unit_number", "?")
            for r in (entry.get("rows") or []):
                count = int(r.get("count", 0) or 0)
                marks = float(r.get("marks", 0) or 0)
                if count <= 0 or marks <= 0:
                    continue
                answer  = int(r.get("answer_count") or count)
                answer  = min(answer, count)
                pattern = (r.get("choice_pattern") or "COMPULSORY").upper()
                category = (r.get("category") or "").strip()
                printed_total    += count * marks
                evaluation_total += answer * marks
                if pattern == "OR_CHOICE":
                    ans_note = "students answer ANY ONE (either/or) — print as 'Q OR Q'"
                elif answer < count:
                    ans_note = f"students answer ANY {answer} of the {count}"
                else:
                    ans_note = "all compulsory"
                cat_note = f" [{category}]" if category else ""
                bp_lines.append(
                    f"  Unit {unit_no}{cat_note}: generate EXACTLY {count} unique "
                    f"question(s) of {marks:g} marks each; {ans_note}. "
                    f"Set unit_number={unit_no} and marks={marks:g} on each."
                )
        format_block = (
            "PAPER BLUEPRINT — generate the number of questions to GENERATE for "
            "each row (NOT the number the student answers). Optional and either/or "
            "questions must ALL be generated:\n"
            + "\n".join(bp_lines)
            + f"\n\nPrinted total (all generated questions): {printed_total:g} marks. "
            f"Evaluation total (maximum a student can score): {evaluation_total:g} marks.\n"
            "Generate TWO sets (Set A and Set B) that both satisfy this blueprint; "
            "most questions appear in both sets, vary at least 20% between sets."
        )
    else:
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
        format_block = (
            f"Question format: {format_text}\n"
            f"Total marks: {total_marks}\n"
            "Generate TWO sets (Set A and Set B) by varying question order and some variants.\n"
            "Most questions appear in both sets; vary at least 20% between sets."
        )

    # CO context block
    co_block = ""
    if course_outcomes:
        co_lines = "\n".join(
            f"  {co.get('co_code','CO?')} [id={co.get('id') or co.get('co_id','')}]: "
            f"{co.get('description') or co.get('co_description','')}"
            for co in course_outcomes
        )
        co_block = (
            f"\nCOURSE OUTCOMES (assign relevant CO UUIDs to each question via co_ids):\n"
            f"{co_lines}\n"
            "For each question, set co_ids to an array of relevant CO UUID strings.\n"
        )

    # Board exam guard
    board_note = ""
    if exam_workflow == "BOARD_EXAM" and exam_type.upper() in _BOARD_EXAM_TYPES:
        board_note = (
            "\nIMPORTANT: This is a Board Examination. The paper must NOT be MCQ-only. "
            "Include short-answer and/or long-answer questions as required by the section structure.\n"
        )

    extra = f"\nSpecial instructions: {special_instructions}" if special_instructions else ""

    # A template paper is ONE paper. Asking for two sets would make the model split
    # its questions between them, and neither set would then hold the structure the
    # template promised.
    if single_set:
        set_field_note = 'always exactly ["A"] — this paper has a single set'
        total_note = (
            "Write exactly one question for every position in the paper structure "
            "above — no more, no fewer."
        )
    else:
        set_field_note = 'array — ["A","B"] if in both sets, ["A"] or ["B"] if set-specific'
        total_note = f"Ensure total marks across all questions in Set A equals {total_marks}."

    return f"""You are an experienced university examiner. Generate an exam question paper.

{course_header}SYLLABUS UNITS:
{unit_text}

{format_block}
- Bloom's taxonomy distribution: {bloom_text}
{co_block}{board_note}{extra}

For EACH question output a JSON object with these fields:
  unit_number     (integer — which unit this question covers)
  bloom_level     (one of: REMEMBER, UNDERSTAND, APPLY, ANALYSE, EVALUATE, CREATE)
  question_type   (one of: MCQ, SHORT_ANSWER, LONG_ANSWER, PROBLEM_SOLVING, CASE_STUDY, PROGRAMMING)
  difficulty      (one of: EASY, MEDIUM, HARD — match the difficulty asked for at this position)
  question_text   (the full question text — specific, subject-relevant, no placeholders)
  marks           (number — marks allocated; use the section marks_each for section-based papers)
  model_answer    (clear, complete model answer)
  marking_scheme  (array of {{criterion: str, marks: number, description: str}})
  set_membership  ({set_field_note})
  section_label   (string — section label "A"/"B"/"C" if this is a section-based paper, else null)
  co_ids          (array of CO UUID strings this question addresses — empty array if not applicable)
  options         (array of {{label: str, text: str}} — only for MCQ questions)
  correct_option  (string "A"/"B"/... — only for MCQ questions)

Output a JSON array of question objects only. No extra text or markdown fences.
Ensure Bloom's distribution across questions matches the requested percentages within ±10%.
{total_note}
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
    bloom      = (q.get("bloom_level") or "REMEMBER").upper()
    qtype      = (q.get("question_type") or "SHORT_ANSWER").upper().replace(" ", "_")
    marks      = float(q.get("marks") or _DEFAULT_MARKS.get(qtype, 5.0))
    membership = q.get("set_membership") or ["A", "B"]

    # section_label — accept string or null
    section_label = q.get("section_label")
    if section_label is not None:
        section_label = str(section_label).strip().upper() or None

    # co_ids — must be a list of strings (UUIDs or CO codes)
    raw_co_ids = q.get("co_ids")
    co_ids: list[str] = []
    if isinstance(raw_co_ids, list):
        co_ids = [str(x) for x in raw_co_ids if x]

    raw_units = q.get("unit_numbers")
    unit_numbers = [int(u) for u in raw_units if str(u).strip().isdigit()] if isinstance(raw_units, list) else []

    difficulty = q.get("difficulty")
    if difficulty is not None:
        difficulty = str(difficulty).strip().upper() or None
        if difficulty not in ("EASY", "MEDIUM", "HARD"):
            difficulty = None

    result: dict = {
        "unit_number":    int(q.get("unit_number") or unit_number_fallback),
        "unit_numbers":   unit_numbers or None,
        "difficulty":     difficulty,
        "co_code":        q.get("co_code"),
        "bloom_level":    bloom,
        "question_type":  qtype,
        "question_text":  str(q.get("question_text") or "").strip(),
        "marks":          marks,
        "model_answer":   str(q.get("model_answer") or "").strip(),
        "marking_scheme": q.get("marking_scheme") or [],
        "set_membership": list(membership),
        "section_label":  section_label,
        "choice_group":   q.get("choice_group"),
        "co_ids":         co_ids,
        "options":        None,
        "correct_option": None,
    }

    if qtype == "MCQ":
        result["options"]        = q.get("options") or []
        result["correct_option"] = q.get("correct_option")

    return result


async def _call_llm(prompt: str) -> tuple[str, str, str]:
    """
    Call LLM with Gemini → Groq → DeepSeek fallback.
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

    async def _try_deepseek() -> str:
        # DeepSeek is OpenAI-compatible; reuse the existing config (key + model)
        # via the OpenAI SDK — no new provider framework, no duplicated AI code.
        from openai import OpenAI
        client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        resp   = client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.7,
        )
        return resp.choices[0].message.content

    if provider == "gemini":
        return await _try_gemini(), settings.GEMINI_MODEL, prompt_hash
    if provider == "groq":
        return await _try_groq(), settings.GROQ_MODEL, prompt_hash
    if provider == "deepseek":
        return await _try_deepseek(), settings.DEEPSEEK_MODEL, prompt_hash

    # Automatic fallback chain: Gemini → Groq → DeepSeek. DeepSeek only joins
    # when it is enabled and keyed (config already present). Mock remains the
    # ultimate fallback in generate_questions() if the whole chain fails.
    chain = [
        ("gemini", _try_gemini, settings.GEMINI_MODEL),
        ("groq",   _try_groq,   settings.GROQ_MODEL),
    ]
    if settings.AI_DEEPSEEK_ENABLED and settings.DEEPSEEK_API_KEY.strip():
        chain.append(("deepseek", _try_deepseek, settings.DEEPSEEK_MODEL))

    last_exc: Exception | None = None
    for name, fn, model_name in chain:
        try:
            return await fn(), model_name, prompt_hash
        except Exception as exc:
            last_exc = exc
            logger.warning("Provider %s failed (%s); trying next.", name, exc)
    raise last_exc or RuntimeError("All LLM providers failed")


def _mock_questions(
    units: list[dict],
    question_format: dict[str, int],
    bloom_targets: dict[str, float],
    total_marks: int,
    section_config: list | None = None,
    blueprint: list | None = None,
    exam_workflow: str = "BOARD_EXAM",
    course_outcomes: list | None = None,
    slots: list | None = None,
    single_set: bool = True,
) -> list[dict]:
    """
    Fallback question generation when no LLM key is configured.
    Produces structurally valid questions using actual unit/topic names.
    When section_config is provided, generates per-section respecting mcq_only
    and marks_each. Supports 2, 5, 8, 10, 15 mark questions via marks_each.

    slots      pre-compiled template slots — one question is written per slot,
               which is the only way the paper can match its template exactly.
    single_set every question belongs to Set A. Two-set generation splits the
               questions BETWEEN the sets, so neither set would then contain the
               full structure the template promised; template papers are always
               a single paper. Legacy blueprint/flat papers pass False and keep
               the original A/B behaviour untouched.
    """
    import itertools

    bloom_cycle = itertools.cycle([
        lvl.upper() for lvl, pct in bloom_targets.items() if pct > 0
    ] or ["REMEMBER", "UNDERSTAND", "APPLY"])

    # Build flat (unit_dict, topic_str) pairs
    topic_pairs: list[tuple[dict, str]] = []
    for unit in (units or []):
        unit_title = unit.get("title", "General Concepts")
        for topic in (unit.get("topics") or [unit_title]):
            topic_pairs.append((unit, str(topic)))
    if not topic_pairs:
        topic_pairs = [({"unit_no": 1, "title": "General Concepts"}, "Core Concepts")]

    topic_cycle = itertools.cycle(topic_pairs)
    sets_cycle  = (
        itertools.cycle([["A"]]) if single_set
        else itertools.cycle([["A", "B"], ["A", "B"], ["A"], ["B"]])
    )

    # CO assignment cycle
    co_cycle = itertools.cycle(course_outcomes) if course_outcomes else None

    # Non-MCQ type rotation for mixed sections
    non_mcq_cycle = itertools.cycle(_NON_MCQ_TYPES)

    def _make(
        qtype: str,
        marks: float,
        section_label: str | None = None,
        unit_topic: tuple[dict, str] | None = None,
    ) -> dict:
        unit, topic = unit_topic if unit_topic is not None else next(topic_cycle)
        bloom       = next(bloom_cycle)
        sets        = next(sets_cycle)
        unit_no     = int(unit.get("unit_no") or unit.get("unit_number") or 1)
        unit_title  = unit.get("title", "General Concepts")

        key    = (qtype, bloom)
        q_text = _Q_TEMPLATES.get(
            key, "Answer the following on {topic} in {unit_title}."
        ).format(topic=topic, unit_title=unit_title)

        options, correct = None, None
        if qtype == "MCQ":
            options, correct = _make_mcq_options(topic)

        answer = _make_model_answer(qtype, bloom, topic, unit_title, marks)

        # Assign CO if available
        co_code: str | None = None
        co_ids: list[str]   = []
        if co_cycle:
            co = next(co_cycle)
            co_code = co.get("co_code")
            co_id   = str(co.get("id") or co.get("co_id", ""))
            if co_id:
                co_ids = [co_id]

        return {
            "unit_number":    unit_no,
            "co_code":        co_code,
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
            "section_label":  section_label,
            "choice_group":   None,
            "co_ids":         co_ids,
            "unit_numbers":   [unit_no],
            "difficulty":     None,
            "options":        options,
            "correct_option": correct,
        }

    questions: list[dict] = []

    # ── Section-aware generation ────────────────────────────────────────────
    if section_config:
        for section in sorted(section_config, key=lambda s: s.get("order", 0)):
            label      = section.get("label", "A")
            total_q    = int(section.get("total_q", 5))
            marks_each = float(section.get("marks_each", 5.0))
            mcq_only   = bool(section.get("mcq_only", False))

            for _ in range(total_q):
                if mcq_only:
                    qtype = "MCQ"
                else:
                    qtype = next(non_mcq_cycle)
                questions.append(_make(qtype, marks_each, section_label=label))
        return questions

    # ── Slot-driven generation — exactly one question per slot ──────────────
    # Template papers pass compiled slots; legacy blueprint papers derive theirs
    # from the blueprint rows. Both then follow the identical path.
    effective_slots = slots if slots is not None else (_blueprint_slots(blueprint) if blueprint else None)
    if effective_slots:
        # Map each unit_number to a cycle of its own (unit_dict, topic) pairs so
        # each question stays on the unit its slot asked for.
        unit_cycles: dict[int, "itertools.cycle"] = {}
        for u in (units or []):
            un = int(u.get("unit_no") or u.get("unit_number") or 0)
            pairs = [(u, str(t)) for t in (u.get("topics") or [u.get("title", "General Concepts")])]
            unit_cycles[un] = itertools.cycle(pairs or [(u, "Core Concepts")])

        for slot in effective_slots:
            un = int(slot["unit_number"])
            cyc = unit_cycles.get(un) or itertools.cycle(
                [({"unit_no": un, "title": f"Unit {un}"}, "Core Concepts")]
            )
            # A template spec already says what type to write; only a legacy
            # blueprint row leaves it to be inferred from the category and marks.
            qtype = slot.get("question_type") or _type_for_row(slot.get("category"), slot["marks"])
            q = _make(qtype, slot["marks"], unit_topic=next(cyc))
            questions.append(_stamp_slot(q, slot))
        return questions

    # ── Board-exam guard — warn if only MCQs specified for a board exam ─────
    only_mcq = (
        question_format.get("mcq_count", 0) > 0
        and question_format.get("short_count", 0) == 0
        and question_format.get("long_count", 0) == 0
        and question_format.get("problem_count", 0) == 0
    )
    if only_mcq and exam_workflow == "BOARD_EXAM":
        logger.warning(
            "MCQ-only question_format requested for BOARD_EXAM workflow — "
            "this is unusual for a board/semester paper. Generating as requested."
        )

    # ── Flat format generation ───────────────────────────────────────────────
    for _ in range(question_format.get("mcq_count", 0)):
        questions.append(_make("MCQ", _DEFAULT_MARKS["MCQ"]))
    for _ in range(question_format.get("short_count", 0)):
        questions.append(_make("SHORT_ANSWER", _DEFAULT_MARKS["SHORT_ANSWER"]))
    for _ in range(question_format.get("long_count", 0)):
        questions.append(_make("LONG_ANSWER", _DEFAULT_MARKS["LONG_ANSWER"]))
    for _ in range(question_format.get("problem_count", 0)):
        questions.append(_make("PROBLEM_SOLVING", _DEFAULT_MARKS["PROBLEM_SOLVING"]))

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
    section_config: list | None = None,
    blueprint: list | None = None,
    course_outcomes: list | None = None,
    exam_workflow: str = "BOARD_EXAM",
    slots: list | None = None,
    template_prompt: str | None = None,
) -> tuple[list[dict], str, str]:
    """
    Generate exam questions from syllabus units.

    Args:
        units:                list of unit dicts from syllabus JSONB
        bloom_targets:        {bloom_level → percentage}
        question_format:      {mcq_count, short_count, long_count, problem_count}
        total_marks:          target total marks
        special_instructions: optional faculty hint
        course_title:         course name for richer prompt context
        course_code:          course code (e.g. "CS301")
        exam_type:            exam type string (e.g. "END_SEM")
        section_config:       list of section dicts (label, total_q, answer_q, marks_each, mcq_only)
        course_outcomes:      list of CO dicts (co_code, description/co_description, id/co_id)
        exam_workflow:        "BOARD_EXAM" or "INTERNAL"
        slots:                pre-compiled template slots (paper_template.compile_slots).
                              When present the template owns the structure: exactly one
                              question is written per slot and the paper is a single set.
        template_prompt:      the template's own description of the paper, block by
                              block (paper_template.describe_for_prompt).

    Returns:
        (questions, ai_model, prompt_hash)
        questions is a list of normalised question dicts ready for bulk_create.
        Template papers additionally carry template_block_id / template_subpart_index.
    """
    from app.config import settings

    no_keys = (
        (not settings.GEMINI_API_KEY.strip())
        and (not settings.GROQ_API_KEY.strip())
        and not (settings.AI_DEEPSEEK_ENABLED and settings.DEEPSEEK_API_KEY.strip())
    )

    # A template owns the paper's structure, so its slots drive generation and the
    # paper is a single set. Legacy blueprint/flat papers keep two-set behaviour.
    is_template = slots is not None
    single_set  = is_template

    def _fallback() -> list[dict]:
        return _mock_questions(
            units, question_format, bloom_targets, total_marks,
            section_config=section_config,
            blueprint=blueprint,
            exam_workflow=exam_workflow,
            course_outcomes=course_outcomes,
            slots=slots,
            single_set=single_set,
        )

    if no_keys:
        logger.warning("No LLM API keys configured — using syllabus-aware fallback generation.")
        return _fallback(), "mock", "mock"

    prompt = _build_prompt(
        units=units,
        bloom_targets=bloom_targets,
        question_format=question_format,
        total_marks=total_marks,
        special_instructions=special_instructions,
        course_title=course_title,
        course_code=course_code,
        exam_type=exam_type,
        section_config=section_config,
        blueprint=blueprint,
        course_outcomes=course_outcomes,
        exam_workflow=exam_workflow,
        template_prompt=template_prompt,
        single_set=single_set,
    )

    try:
        raw, model_name, prompt_hash = await _call_llm(prompt)
        raw_questions = _parse_questions(raw)
        questions = [_normalise_question(q) for q in raw_questions]

        bind_slots = slots if is_template else (
            _blueprint_slots(blueprint) if (blueprint and not section_config) else None
        )
        if bind_slots:
            # The template is the contract, and a model is free to ignore it: it
            # can return the wrong marks, the wrong unit, or the wrong count. Bind
            # its output onto the slots so the paper always reconstructs into the
            # faculty's structure instead of spilling into a loose bucket.
            questions = _bind_to_slots(questions, bind_slots, _fallback())
            if single_set:
                # One paper, one set — a question held back for "Set B" would be a
                # hole in the structure the template promised.
                for q in questions:
                    q["set_membership"] = ["A"]
    except Exception as exc:
        logger.error(
            "Question generation failed: %s — falling back to syllabus-aware generation.", exc
        )
        questions = _fallback()
        model_name  = "mock-fallback"

    return questions, model_name, hashlib.sha256(
        json.dumps({"units": len(units), "format": question_format}).encode()
    ).hexdigest()[:16]
