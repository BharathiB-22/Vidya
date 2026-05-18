"""
M09 Script Scorer — per-question AI scoring for scanned answer scripts.

MCQ questions:
  Tries to extract the student's chosen option from ocr_text using regex heuristics.
  Returns ai_suggested_marks = full marks or 0 with a confidence note.
  If the option cannot be detected, ai_suggested_marks is None.

Subjective questions (SHORT_ANSWER, LONG_ANSWER, PROBLEM_SOLVING):
  Calls Gemini → Groq fallback with question text, model answer, marking scheme,
  and the full OCR text as context.  Returns marks in [0, max_marks] + justification.

If ocr_text is None or empty:
  All questions get ai_suggested_marks=None with a note that OCR text is unavailable.
  The Celery task caller then sets script status → REVIEW_REQUIRED.

Human-gate invariant:
  This module NEVER writes evaluator_marks.  Only ai_suggested_marks is set here.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import re
from uuid import UUID

from app.config import settings

logger = logging.getLogger("vidya.m09.script_scorer")


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class QuestionScore:
    question_id: UUID
    question_type: str
    max_marks: float
    ai_suggested_marks: float | None   # None means evaluator must enter manually
    ai_justification: str | None
    ai_model: str
    prompt_hash: str


@dataclasses.dataclass
class ScriptScoringResult:
    scores: list[QuestionScore]
    objective_auto_score: float  # sum of MCQ ai_suggested_marks (where not None)
    had_ocr: bool                # False when ocr_text was empty/None


# ---------------------------------------------------------------------------
# MCQ answer extraction
# ---------------------------------------------------------------------------

# Patterns ordered by specificity — first match wins
_MCQ_PATTERNS = [
    re.compile(r"(?:answer|ans)[.:\s]+([A-Da-d])", re.IGNORECASE),
    re.compile(r"[\(\[]\s*([A-Da-d])\s*[\)\]]"),
    re.compile(r"\b([A-Da-d])[.)]\s"),
]


def _extract_mcq_option(ocr_text: str, question_number: int) -> str | None:
    """Return the detected option letter (upper-case) near question_number, or None."""
    context = ocr_text

    # Try to isolate text near this question's number to reduce cross-question noise
    q_re = re.compile(
        rf"(?:Q\.?\s*{question_number}|[Qq]uestion\s+{question_number}"
        rf"|^\s*{question_number}[.)]\s)(.{{0,300}})",
        re.MULTILINE,
    )
    m = q_re.search(ocr_text)
    if m:
        context = m.group(1)

    for pattern in _MCQ_PATTERNS:
        hit = pattern.search(context)
        if hit:
            return hit.group(1).upper()
    return None


# ---------------------------------------------------------------------------
# Subjective scoring prompts
# ---------------------------------------------------------------------------

def _build_subjective_prompt(
    question_text: str,
    question_type: str,
    max_marks: float,
    model_answer: str | None,
    marking_scheme: list | None,
    ocr_text: str,
) -> tuple[str, str]:
    scheme_block = ""
    if marking_scheme:
        scheme_block = "\nMarking scheme:\n" + "\n".join(
            f"  - {c.get('criterion', 'Point')} "
            f"({c.get('marks', '?')} marks): {c.get('description', '')}"
            for c in marking_scheme
        )

    model_ans_block = ""
    if model_answer:
        model_ans_block = f"\nModel answer:\n{model_answer[:1000]}"

    system = (
        "You are an expert academic examiner scoring an Indian university answer script. "
        "Score objectively based on subject knowledge and the marking scheme. "
        "Return ONLY valid JSON — no markdown, no prose."
    )

    user = (
        f"Question ({question_type}, max {max_marks} marks):\n{question_text}"
        f"{model_ans_block}"
        f"{scheme_block}\n\n"
        "Student's answer (full OCR text from scanned script):\n"
        f"---\n{ocr_text[:6000]}\n---\n\n"
        f"Score the student's answer from 0 to {max_marks} "
        "(fractional marks allowed in 0.5 increments).\n"
        'Return JSON exactly: {"marks": <float>, "justification": "<1-3 sentences>"}'
    )

    return system, user


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# LLM calls — Gemini primary, Groq fallback
# ---------------------------------------------------------------------------

async def _score_gemini(system: str, user: str, max_marks: float) -> tuple[float, str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.15,
        system_instruction=system,
    )
    response = await client.aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=user,
        config=config,
    )
    raw = getattr(response, "text", "") or ""
    if not raw:
        raise ValueError("Gemini returned empty response.")
    parsed = json.loads(raw)
    marks = max(0.0, min(float(max_marks), float(parsed.get("marks", 0))))
    justification = str(parsed.get("justification", "")).strip() or "No justification provided."
    return marks, justification


async def _score_groq(system: str, user: str, max_marks: float) -> tuple[float, str]:
    from openai import AsyncOpenAI

    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not configured.")

    client = AsyncOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    response = await client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.15,
    )
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ValueError("Groq returned empty response.")
    parsed = json.loads(raw)
    # Groq sometimes wraps the result
    if isinstance(parsed, dict) and "marks" not in parsed:
        for key in ("result", "score", "evaluation", "answer"):
            if key in parsed and isinstance(parsed[key], dict):
                parsed = parsed[key]
                break
    marks = max(0.0, min(float(max_marks), float(parsed.get("marks", 0))))
    justification = str(parsed.get("justification", "")).strip() or "No justification provided."
    return marks, justification


_QUOTA_SIGNALS = ("resource_exhausted", "429", "quota", "rate_limit", "rate limit")


async def _llm_score_question(
    system: str,
    user: str,
    max_marks: float,
) -> tuple[float | None, str, str]:
    """Returns (marks | None, justification, model_name). None marks = both providers failed."""
    try:
        marks, just = await _score_gemini(system, user, max_marks)
        return marks, just, settings.GEMINI_MODEL
    except Exception as exc:
        if any(s in str(exc).lower() for s in _QUOTA_SIGNALS):
            logger.warning("Gemini quota hit — falling back to Groq.")
        else:
            logger.warning("Gemini scoring failed: %s", exc)

    try:
        marks, just = await _score_groq(system, user, max_marks)
        return marks, just, settings.GROQ_MODEL
    except Exception as exc:
        logger.error("Both Gemini and Groq scoring failed: %s", exc)
        return None, f"AI scoring failed: {exc!s:.120}", "error"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def score_script(
    questions: list,          # list of ExamQuestion ORM objects
    ocr_text: str | None,
    *,
    question_number_offset: int = 1,
) -> ScriptScoringResult:
    """
    Score a scanned answer script.

    questions:              ExamQuestion ORM rows for the exam paper (in creation order).
    ocr_text:               Raw OCR text from the uploaded scan; None = not yet extracted.
    question_number_offset: 1-based question number of the first item in `questions`.
    """
    scores: list[QuestionScore] = []
    objective_auto_score: float = 0.0
    had_ocr = bool(ocr_text and ocr_text.strip())

    for idx, q in enumerate(questions):
        q_num = question_number_offset + idx
        max_m = float(q.marks)
        qtype = str(q.question_type)

        if not had_ocr:
            scores.append(QuestionScore(
                question_id=q.id,
                question_type=qtype,
                max_marks=max_m,
                ai_suggested_marks=None,
                ai_justification=(
                    "OCR text not yet available — evaluator must enter marks manually."
                ),
                ai_model="none",
                prompt_hash="",
            ))
            continue

        if qtype == "MCQ":
            detected = _extract_mcq_option(ocr_text, q_num)
            correct = (q.correct_option or "").strip().upper()

            if detected and correct:
                matched = detected == correct
                marks = max_m if matched else 0.0
                just = (
                    f"Student selected option {detected}; "
                    f"correct answer is {correct}. "
                    + ("Full marks awarded." if matched else "No marks awarded.")
                )
                objective_auto_score += marks
            else:
                marks = None
                just = (
                    f"Could not reliably detect MCQ answer for Q{q_num} "
                    "from OCR text. Evaluator should verify and enter marks."
                )

            scores.append(QuestionScore(
                question_id=q.id,
                question_type=qtype,
                max_marks=max_m,
                ai_suggested_marks=marks,
                ai_justification=just,
                ai_model="auto",
                prompt_hash="",
            ))

        else:
            system, user = _build_subjective_prompt(
                question_text=q.question_text,
                question_type=qtype,
                max_marks=max_m,
                model_answer=q.model_answer,
                marking_scheme=list(q.marking_scheme or []),
                ocr_text=ocr_text,
            )
            phash = _prompt_hash(system, user)
            marks, just, model_name = await _llm_score_question(system, user, max_m)

            scores.append(QuestionScore(
                question_id=q.id,
                question_type=qtype,
                max_marks=max_m,
                ai_suggested_marks=marks,
                ai_justification=just,
                ai_model=model_name,
                prompt_hash=phash,
            ))

    return ScriptScoringResult(
        scores=scores,
        objective_auto_score=round(objective_auto_score, 2),
        had_ocr=had_ocr,
    )
