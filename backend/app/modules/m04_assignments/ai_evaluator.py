"""
M04 Coursework AI evaluator — ADVISORY orchestration only.

This module owns nothing but the coursework-specific *prompt* and the shape of
the AI's answer. It deliberately does NOT re-implement any AI machinery:

  * text extraction  -> app.modules.m06_labs_evaluator.text_extractor
  * internal similarity -> app.modules.m06_labs_evaluator.plagiarism
  * the LLM client   -> the same google-genai client m06 uses

"AI advises, humans decide": nothing here writes a mark anywhere. It returns a
structured suggestion the worker persists to assignment_evaluations, which the
evaluator reads and is free to accept, change, or ignore.

Future-proofing (no API change required to add):
  * OCR            -> extend the extractor; this module is unaffected.
  * external plagiarism -> fill plagiarism_status; the field already exists.
  * more providers -> add a branch in _call_llm; the return shape is stable.
  * faculty rubrics -> pass a rubric list instead of DEFAULT_RUBRIC.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.modules.m04_assignments.ai_providers import PermanentAIError, run_chain

logger = logging.getLogger("vidya.m04.ai_evaluator")

# A fixed default rubric until coursework gets a faculty-defined one. Advisory.
DEFAULT_RUBRIC: list[str] = [
    "Understanding",
    "Presentation",
    "Accuracy",
    "Completeness",
    "Critical Thinking",
    "Application",
    "Reasoning",
    "Evidence",
]


@dataclass
class EvalContext:
    """Everything the AI is given about one submission (all advisory input)."""
    assignment_title: str
    max_marks: float
    questions: list[dict] = field(default_factory=list)         # [{question_number, question_text, marks}]
    question_paper_text: str | None = None
    instructions: str | None = None
    # Academic context (resolved from the course; never hardcoded).
    institution: str | None = None
    department: str | None = None
    program: str | None = None
    course_title: str | None = None
    course_code: str | None = None
    semester: int | None = None
    course_outcomes: list[dict] = field(default_factory=list)   # [{co_code, description, bloom_level}]
    rubric: list[str] = field(default_factory=lambda: list(DEFAULT_RUBRIC))
    submission_text: str = ""


_SYSTEM = (
    "You are an experienced university examiner producing an ADVISORY evaluation "
    "of a student's coursework submission. You never assign final marks — a human "
    "evaluator decides. Be specific, fair, and grounded ONLY in the submitted "
    "text. If the submission is empty or irrelevant, say so and score low. "
    "Return ONE raw JSON object and NOTHING else: no markdown, no ``` fences, no "
    "commentary before or after, no trailing text. Numbers must be plain numbers."
)

# The exact JSON contract we ask the model for (kept in sync with the parser).
_SCHEMA_HINT = """
Return JSON with EXACTLY these keys:
{
  "per_question": [{"question_number": int, "suggested": number, "max": number, "reason": string}],
  "overall": {"total_suggested": number, "percentage": number, "confidence": "HIGH|MEDIUM|LOW"},
  "feedback": {
    "strengths": [string], "weaknesses": [string], "missing_concepts": [string],
    "writing_quality": string, "technical_correctness": string, "suggestions": [string]
  },
  "rubric": [{"criterion": string, "score": number, "max": 10, "comment": string}],
  "bloom": {"expected_level": string, "detected_level": string, "alignment_percent": number, "notes": string},
  "co": {"covered": [string], "weak": [string], "missing": [string], "notes": string}
}
"""


def _build_user_prompt(ctx: EvalContext) -> str:
    q_lines = "\n".join(
        f"  Q{q.get('question_number')}: {q.get('question_text', '')} "
        f"[max {q.get('marks', 0)} marks]"
        for q in (ctx.questions or [])
    ) or "  (No structured questions — see the question paper text below.)"

    co_lines = "\n".join(
        f"  {c.get('co_code', 'CO')}: {c.get('description', '')} "
        f"(expected Bloom: {c.get('bloom_level', 'N/A')})"
        for c in (ctx.course_outcomes or [])
    ) or "  (No course outcomes recorded for this course.)"

    return f"""ASSIGNMENT: {ctx.assignment_title}
Institution: {ctx.institution or 'N/A'}
Department: {ctx.department or 'N/A'}
Program: {ctx.program or 'N/A'}
Semester: {ctx.semester if ctx.semester is not None else 'N/A'}
Course: {ctx.course_code or 'N/A'} — {ctx.course_title or 'N/A'}
Maximum marks: {ctx.max_marks}
Instructions: {ctx.instructions or '(none)'}

QUESTIONS:
{q_lines}

QUESTION PAPER (if attached):
{(ctx.question_paper_text or '(none)')[:4000]}

COURSE OUTCOMES (ground truth — use for CO/Bloom analysis, advisory only):
{co_lines}

RUBRIC CRITERIA (score each 0..10): {", ".join(ctx.rubric)}

STUDENT SUBMISSION (evaluate ONLY this text):
\"\"\"
{ctx.submission_text[:20000]}
\"\"\"

Evaluate each question individually, then the whole assignment.
{_SCHEMA_HINT}"""


def _prompt_hash(user: str) -> str:
    return hashlib.sha256((_SYSTEM + user).encode("utf-8")).hexdigest()[:32]


def _extract_json(raw: str) -> dict[str, Any]:
    """Recover a JSON object from a possibly-messy model response.

    Handles: clean JSON; ```json … ``` fences; prose before and/or after the
    object ("Here is the result: {…} Thanks."). Strategy: try a direct parse,
    then strip code fences, then scan for the FIRST balanced {...} block (respecting
    strings/escapes). Raises PermanentAIError only if no JSON object exists at all
    — a malformed response is a permanent failure, never a crash and never a retry.
    """
    if not raw or not raw.strip():
        raise PermanentAIError("Empty model response — no JSON object found.")

    # 1. Direct parse (the happy path with response_mime_type=json).
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Strip markdown code fences and retry.
    fenced = raw.strip()
    if "```" in fenced:
        # take the content of the first fenced block
        parts = fenced.split("```")
        for chunk in parts:
            c = chunk.strip()
            if c.lower().startswith("json"):
                c = c[4:].strip()
            if c.startswith("{"):
                try:
                    obj = json.loads(c)
                    if isinstance(obj, dict):
                        return obj
                except (json.JSONDecodeError, ValueError):
                    continue

    # 3. Scan for the first balanced {...} object, ignoring braces inside strings.
    start = raw.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(raw)):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except (json.JSONDecodeError, ValueError):
                        break  # try the next '{'
        start = raw.find("{", start + 1)

    raise PermanentAIError("No valid JSON object could be extracted from the response.")


def _coerce(raw: str, ctx: EvalContext) -> dict[str, Any]:
    """Parse + defensively normalise the model's JSON. Missing fields fall back to
    safe defaults; marks are clamped so a bad model can never exceed the maximum."""
    data = _extract_json(raw)

    per_q = []
    for q in data.get("per_question", []) or []:
        try:
            qmax = float(q.get("max") or 0)
            sug = max(0.0, min(float(q.get("suggested") or 0), qmax or float(ctx.max_marks)))
            per_q.append({
                "question_number": int(q.get("question_number") or 0),
                "suggested": round(sug, 2),
                "max": round(qmax, 2),
                "reason": str(q.get("reason") or "")[:1000],
            })
        except (TypeError, ValueError):
            continue

    overall = data.get("overall") or {}
    total = overall.get("total_suggested")
    if total is None and per_q:
        total = sum(q["suggested"] for q in per_q)
    total = max(0.0, min(float(total or 0), float(ctx.max_marks)))
    pct = round((total / ctx.max_marks * 100), 2) if ctx.max_marks else 0.0
    conf = str(overall.get("confidence") or "MEDIUM").upper()
    if conf not in ("HIGH", "MEDIUM", "LOW"):
        conf = "MEDIUM"

    return {
        "suggested_marks": per_q,
        "overall_suggested_marks": round(total, 2),
        "percentage": pct,
        "confidence_level": conf,
        "feedback": data.get("feedback") or {},
        "rubric_scores": data.get("rubric") or [],
        "bloom_analysis": data.get("bloom") or {},
        "co_analysis": data.get("co") or {},
    }


async def evaluate(ctx: EvalContext) -> dict[str, Any]:
    """Run the advisory evaluation through the provider chain.

    Returns a dict ready to persist, including provider_used / model_used /
    fallback_chain / prompt_hash for reproducibility.

    Raises (for the worker to act on):
      TransientAIError  — every provider failed transiently → Celery autoretry.
      PermanentAIError  — no usable provider, or unparseable JSON → status FAILED.
    """
    user = _build_user_prompt(ctx)
    phash = _prompt_hash(user)
    chain = await run_chain(_SYSTEM, user)   # may raise TransientAIError/PermanentAIError
    result = _coerce(chain.raw, ctx)         # may raise PermanentAIError (no JSON)
    result["ai_model"] = chain.model_used
    result["provider_used"] = chain.provider_used
    result["fallback_chain"] = chain.fallback_chain
    result["prompt_hash"] = phash
    return result
