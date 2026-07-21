"""
M07 Viva Engine — AI orchestration for async video viva sessions.

Responsibilities:
  1. generate_base_questions()  — LLM generates 5–8 structured questions from document.
  2. generate_followup()        — LLM generates one follow-up given a base Q + response.
  3. evaluate_responses()       — LLM scores each response (coherence, accuracy, depth).
  4. transcribe_audio()         — Whisper ASR call; raises TranscriptionUnavailable
                                  when the endpoint is not configured. It never
                                  fabricates a transcript.

All LLM calls use Gemini → Groq fallback (same pattern as M06).
Whisper endpoint is configured via settings.M07_WHISPER_ENDPOINT.
If it is blank, transcription FAILS — see TranscriptionUnavailable below.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import uuid
from typing import Any

from app.config import settings

logger = logging.getLogger("vidya.m07.viva_engine")


class TranscriptionUnavailable(RuntimeError):
    """ASR could not produce a transcript for a viva recording.

    Raised instead of returning placeholder text. A viva evaluation built on an
    invented transcript would be an academic record of an event that never
    happened, so the absence of ASR is surfaced as a failure the guide is told
    about — never papered over.
    """


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class VivaQuestion:
    id:          str
    text:        str
    source:      str   # "base" | "followup"
    based_on_qid: str | None
    order:       int


@dataclasses.dataclass
class ResponseEval:
    question_id: str
    coherence:   float   # 0–10
    accuracy:    float   # 0–10
    depth:       float   # 0–10
    comment:     str


@dataclasses.dataclass
class VivaEvaluationResult:
    per_question:    list[ResponseEval]
    overall_score:   float
    ai_model:        str


# ---------------------------------------------------------------------------
# LLM call helper (shared with problem_generator pattern)
# ---------------------------------------------------------------------------

async def _call_gemini(prompt: str) -> tuple[str, str]:
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text, settings.GEMINI_MODEL


async def _call_groq(prompt: str) -> tuple[str, str]:
    import httpx
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 2048,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload,
        )
        resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"], settings.GROQ_MODEL


async def _call_llm(prompt: str, temperature: float = 0.4) -> tuple[str, str]:
    provider = settings.AI_PROVIDER
    if provider == "groq":
        return await _call_groq(prompt)
    if provider == "gemini":
        return await _call_gemini(prompt)
    try:
        return await _call_gemini(prompt)
    except Exception as err:
        logger.warning("Gemini failed (%s), falling back to Groq", err)
        return await _call_groq(prompt)


# ---------------------------------------------------------------------------
# 1. Base question generation
# ---------------------------------------------------------------------------

def _build_questions_prompt(document_excerpt: str, num_questions: int) -> str:
    excerpt = document_excerpt[:4000]
    return f"""You are a doctoral examination board member conducting a viva voce.

Based on the following research document excerpt, generate exactly {num_questions} viva examination questions.
Questions should test: understanding of the problem, methodology justification, expected contributions, and limitations.

Document excerpt:
---
{excerpt}
---

Respond ONLY with a JSON array of exactly {num_questions} question strings.
Example: ["Question 1?", "Question 2?", ...]

Generate {num_questions} questions now:"""


async def generate_base_questions(
    document_text: str,
    *,
    num_questions: int = 6,
) -> list[VivaQuestion]:
    """Generate base viva questions from the research document."""
    prompt = _build_questions_prompt(document_text, num_questions)
    raw, model = await _call_llm(prompt)

    # Parse JSON array
    raw_clean = re.sub(r"```json\s*|\s*```", "", raw).strip()
    try:
        questions_raw = json.loads(raw_clean)
        if not isinstance(questions_raw, list):
            raise ValueError("Not a list")
    except Exception:
        m = re.search(r"\[.*?\]", raw_clean, re.DOTALL)
        questions_raw = json.loads(m.group(0)) if m else [raw_clean]

    questions: list[VivaQuestion] = []
    for i, q_text in enumerate(questions_raw[:num_questions]):
        questions.append(VivaQuestion(
            id=str(uuid.uuid4()),
            text=str(q_text).strip(),
            source="base",
            based_on_qid=None,
            order=i + 1,
        ))
    return questions


# ---------------------------------------------------------------------------
# 2. Follow-up question generation
# ---------------------------------------------------------------------------

def _build_followup_prompt(question: str, response: str) -> str:
    return f"""You are a doctoral examination board member.

The student was asked: "{question}"
The student responded: "{response[:800]}"

Generate ONE focused follow-up question that probes deeper into the student's answer.
If the response is unclear or incomplete, ask for clarification.
If the response is correct, ask them to elaborate on implications or limitations.

Respond ONLY with the follow-up question text (no JSON, no explanation):"""


async def generate_followup(
    base_question: str,
    student_response: str,
    base_question_id: str,
    order: int,
) -> VivaQuestion:
    """Generate one follow-up question based on student's response."""
    prompt = _build_followup_prompt(base_question, student_response)
    raw, _ = await _call_llm(prompt)
    followup_text = raw.strip().strip('"').strip("'")

    return VivaQuestion(
        id=str(uuid.uuid4()),
        text=followup_text,
        source="followup",
        based_on_qid=base_question_id,
        order=order,
    )


# ---------------------------------------------------------------------------
# 3. Response evaluation
# ---------------------------------------------------------------------------

def _build_eval_prompt(qa_pairs: list[dict]) -> str:
    qa_text = ""
    for i, pair in enumerate(qa_pairs, 1):
        qa_text += f"\nQ{i}: {pair['question']}\nA{i}: {pair['response'][:600]}\n"

    return f"""You are an expert academic evaluator assessing a research viva.

Evaluate each answer on three dimensions (scale 0–10):
  - coherence: Is the answer logically structured and clear?
  - accuracy: Is the answer factually and technically correct?
  - depth: Does the answer demonstrate deep understanding?

Q&A pairs:
{qa_text}

Respond ONLY with a JSON array, one object per Q&A pair:
[
  {{"question_id": "<id>", "coherence": <0-10>, "accuracy": <0-10>, "depth": <0-10>, "comment": "<1 sentence>"}},
  ...
]"""


# Envelope keys that LLMs use to wrap arrays (mirrors M06 rubric_scorer pattern).
_EVAL_ENVELOPE_KEYS = (
    "evaluations", "evaluation", "scores", "responses",
    "results", "items", "data", "criteria",
)


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences from AI response."""
    cleaned = re.sub(r"```(?:json|python|text)?\s*", "", raw)
    return re.sub(r"```", "", cleaned).strip()


def _normalise_eval_to_list(parsed: Any) -> list[dict]:
    """Convert any valid AI response shape to a flat list of eval dicts."""
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        # Single-item collapsed response
        if "coherence" in parsed or "accuracy" in parsed or "depth" in parsed:
            return [parsed]
        # Known envelope key
        for key in _EVAL_ENVELOPE_KEYS:
            val = parsed.get(key)
            if isinstance(val, list):
                return val
    raise ValueError(f"Cannot normalise parsed value: type={type(parsed).__name__}")


def _extract_balanced(text: str, open_ch: str, close_ch: str) -> list[str]:
    """Return all top-level balanced open_ch…close_ch spans from text."""
    spans: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == open_ch:
            if depth == 0:
                start = i
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0 and start != -1:
                spans.append(text[start : i + 1])
                start = -1
    return spans


def _parse_eval_json(raw: str) -> list[dict]:
    """
    Robustly extract a JSON array from an AI response.

    Stages:
      1. Strip markdown fences, try direct json.loads.
      2. Balanced bracket extraction of all [...] blocks (largest-first),
         so preamble prose like "[listed above]" does not fool the parser.
      3. Balanced brace extraction of all {...} blocks (largest-first)
         for object-envelope responses.

    Raises ValueError when all stages fail so the caller can apply fallback.
    """
    clean = _strip_fences(raw)

    # Stage 1 — direct parse
    try:
        return _normalise_eval_to_list(json.loads(clean))
    except (json.JSONDecodeError, ValueError):
        pass

    # Stage 2 — all balanced [...] spans, largest first
    arrays = sorted(_extract_balanced(clean, "[", "]"), key=len, reverse=True)
    for candidate in arrays:
        try:
            return _normalise_eval_to_list(json.loads(candidate))
        except (json.JSONDecodeError, ValueError):
            pass

    # Stage 3 — all balanced {...} spans (envelope keys), largest first
    objects = sorted(_extract_balanced(clean, "{", "}"), key=len, reverse=True)
    for candidate in objects:
        try:
            return _normalise_eval_to_list(json.loads(candidate))
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(f"No valid JSON found in AI response: {raw[:300]!r}")


def _default_evals(qa_pairs: list[dict]) -> list[dict]:
    """Conservative 5/5/5 fallback when the AI response cannot be parsed."""
    return [
        {
            "question_id": pair.get("question_id", str(i)),
            "coherence":   5.0,
            "accuracy":    5.0,
            "depth":       5.0,
            "comment":     "AI evaluation unavailable — default score applied.",
        }
        for i, pair in enumerate(qa_pairs)
    ]


async def evaluate_responses(
    qa_pairs: list[dict],  # [{question_id, question, response}]
) -> VivaEvaluationResult:
    """LLM evaluation of all viva responses. Never raises — falls back to defaults."""
    if not qa_pairs:
        return VivaEvaluationResult(per_question=[], overall_score=0.0, ai_model="none")

    prompt = _build_eval_prompt(qa_pairs)
    raw, model = await _call_llm(prompt)

    try:
        items = _parse_eval_json(raw)
    except Exception as exc:
        logger.warning(
            "evaluate_responses: JSON parse failed (%s) — applying default scores. "
            "Raw snippet: %r",
            exc, raw[:200],
        )
        items = _default_evals(qa_pairs)
        model = f"{model}+fallback"

    evals: list[ResponseEval] = []
    # Pair parsed items with qa_pairs positionally; unpaired questions get defaults.
    for i, pair in enumerate(qa_pairs):
        item = items[i] if i < len(items) else {}
        evals.append(ResponseEval(
            question_id=pair.get("question_id", str(i)),
            coherence=max(0.0, min(10.0, float(item.get("coherence", 5.0)))),
            accuracy=max(0.0, min(10.0, float(item.get("accuracy", 5.0)))),
            depth=max(0.0, min(10.0, float(item.get("depth", 5.0)))),
            comment=str(item.get("comment", "")).strip(),
        ))

    overall = sum((e.coherence + e.accuracy + e.depth) / 3 for e in evals) / len(evals)
    return VivaEvaluationResult(
        per_question=evals,
        overall_score=round(overall, 2),
        ai_model=model,
    )


# ---------------------------------------------------------------------------
# 4. Whisper ASR transcription
# ---------------------------------------------------------------------------

async def transcribe_audio(audio_url: str) -> str:
    """
    Call Whisper ASR to transcribe a viva recording.

    Raises TranscriptionUnavailable if M07_WHISPER_ENDPOINT is blank. It never
    returns placeholder text — see the exception's docstring.
    Production: POST audio file to the Whisper endpoint.
    """
    if not settings.M07_WHISPER_ENDPOINT:
        # Never fabricate a transcript. This text used to be invented wholesale
        # ("50 participants from one region") and then flowed into the AI
        # evaluation, into the report, and into something a guide could ratify —
        # an academic record about a viva nobody gave. A missing transcript must
        # fail loudly and leave the guide to proceed manually.
        raise TranscriptionUnavailable(
            "ASR is not configured (M07_WHISPER_ENDPOINT is unset), so this viva "
            "could not be transcribed. No transcript has been recorded."
        )

    import httpx
    async with httpx.AsyncClient(timeout=300.0) as client:
        # Download audio
        audio_resp = await client.get(audio_url)
        audio_resp.raise_for_status()
        audio_bytes = audio_resp.content

        # POST to Whisper endpoint
        files = {"audio_file": ("viva.webm", audio_bytes, "audio/webm")}
        resp = await client.post(
            f"{settings.M07_WHISPER_ENDPOINT.rstrip('/')}/asr",
            files=files,
            params={"output": "txt"},
        )
        resp.raise_for_status()
        return resp.text.strip()
