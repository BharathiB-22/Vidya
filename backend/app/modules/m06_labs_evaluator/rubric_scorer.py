"""
M06 Rubric Scorer — LLM-based per-criterion scoring for written submissions.

Given:
  - Student submission text
  - Assignment rubric (list of criteria with name, description, max_marks, weight)
  - Assignment question/description

Produces for each criterion:
  - ai_score: float (0 to max_marks)
  - ai_justification: 1–3 sentence explanation
  - Overall weighted score across all criteria

Confidence classification:
  HIGH   — all criterion score variances < 10 % of max_marks range
  LOW    — any criterion score > 25 % of max_marks away from mean expected
  MEDIUM — everything else

Uses Gemini Flash (primary) → Groq fallback via same pattern as M03.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger("vidya.m06.rubric_scorer")


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class CriterionScore:
    criterion_id: str
    ai_score: float
    ai_justification: str
    max_marks: int


@dataclasses.dataclass
class RubricScoringResult:
    criteria_scores: list[CriterionScore]
    overall_ai_score: float
    confidence_level: str    # HIGH | MEDIUM | LOW
    ai_model: str
    prompt_hash: str


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(
    question: str,
    submission_text: str,
    rubric: list[dict],
) -> tuple[str, str]:
    rubric_lines = "\n".join(
        f"  - [{c['criterion_id']}] {c['name']} (max {c['max_marks']} marks, "
        f"weight {c.get('weight', 0):.2f}): {c.get('description', '')}"
        for c in rubric
    )

    system = (
        "You are an expert academic evaluator for university assignments. "
        "Your task is to score a student submission against a given rubric. "
        "Be objective, consistent, and provide clear 1–3 sentence justifications. "
        "Return only a JSON array matching the schema provided — no prose, no markdown."
    )

    user = (
        f"Assignment question:\n{question}\n\n"
        f"Rubric criteria:\n{rubric_lines}\n\n"
        f"Student submission:\n---\n{submission_text[:8000]}\n---\n\n"
        "For each rubric criterion, output a JSON object with:\n"
        "  criterion_id: string (from rubric)\n"
        "  ai_score: float (0 to max_marks; may be fractional)\n"
        "  ai_justification: string (1–3 sentences explaining the score)\n\n"
        "Return a JSON array of these objects in the SAME ORDER as the rubric. "
        "Do not add any fields beyond criterion_id, ai_score, ai_justification."
    )

    return system, user


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Confidence classification
# ---------------------------------------------------------------------------

def _classify_confidence(
    criteria_scores: list[CriterionScore],
    rubric: list[dict],
) -> str:
    if not criteria_scores:
        return "LOW"

    issues = 0
    for cs in criteria_scores:
        max_m = float(cs.max_marks)
        if max_m == 0:
            continue
        # Flag if score is unreasonably extreme (too high or low relative to midpoint)
        midpoint = max_m / 2
        deviation = abs(cs.ai_score - midpoint) / max_m
        if deviation > 0.25:
            issues += 1

    total = len(criteria_scores)
    if issues == 0:
        return "HIGH"
    elif issues <= total // 3:
        return "MEDIUM"
    else:
        return "LOW"


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(raw: str, rubric: list[dict]) -> list[CriterionScore]:
    rubric_map = {c["criterion_id"]: c for c in rubric}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI response is not valid JSON: {exc}\nRaw: {raw[:400]}") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array; got {type(parsed).__name__}")

    scores: list[CriterionScore] = []
    seen_ids: set[str] = set()

    for item in parsed:
        cid   = str(item.get("criterion_id", ""))
        score = float(item.get("ai_score", 0))
        just  = str(item.get("ai_justification", "")).strip()

        if cid in rubric_map:
            max_m = int(rubric_map[cid]["max_marks"])
            score = max(0.0, min(float(max_m), score))  # clamp to [0, max_marks]
        else:
            max_m = 10  # fallback

        if cid not in seen_ids:
            scores.append(CriterionScore(
                criterion_id=cid,
                ai_score=round(score, 2),
                ai_justification=just or "No justification provided.",
                max_marks=max_m,
            ))
            seen_ids.add(cid)

    # Fill in any rubric criteria the AI missed
    for c in rubric:
        if c["criterion_id"] not in seen_ids:
            scores.append(CriterionScore(
                criterion_id=c["criterion_id"],
                ai_score=0.0,
                ai_justification="Not scored by AI — criterion may not be addressed.",
                max_marks=int(c["max_marks"]),
            ))

    return scores


def _weighted_total(criteria_scores: list[CriterionScore], rubric: list[dict]) -> float:
    """Sum of (ai_score * weight) across all criteria."""
    weight_map = {c["criterion_id"]: float(c.get("weight", 0)) for c in rubric}
    total = sum(cs.ai_score * weight_map.get(cs.criterion_id, 0) for cs in criteria_scores)
    return round(total, 2)


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------

async def _score_with_gemini(
    system: str,
    user: str,
    rubric: list[dict],
    phash: str,
) -> RubricScoringResult:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
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

    scores = _parse_response(raw, rubric)
    return RubricScoringResult(
        criteria_scores=scores,
        overall_ai_score=_weighted_total(scores, rubric),
        confidence_level=_classify_confidence(scores, rubric),
        ai_model=settings.GEMINI_MODEL,
        prompt_hash=phash,
    )


# ---------------------------------------------------------------------------
# Groq implementation
# ---------------------------------------------------------------------------

async def _score_with_groq(
    system: str,
    user: str,
    rubric: list[dict],
    phash: str,
) -> RubricScoringResult:
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
        temperature=0.2,
    )
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ValueError("Groq returned empty response.")

    # Groq may return {"scores": [...]} instead of bare array
    try:
        parsed_outer = json.loads(raw)
        if isinstance(parsed_outer, dict):
            for key in ("scores", "criteria_scores", "rubric_scores", "results"):
                if key in parsed_outer and isinstance(parsed_outer[key], list):
                    raw = json.dumps(parsed_outer[key])
                    break
    except json.JSONDecodeError:
        pass

    scores = _parse_response(raw, rubric)
    return RubricScoringResult(
        criteria_scores=scores,
        overall_ai_score=_weighted_total(scores, rubric),
        confidence_level=_classify_confidence(scores, rubric),
        ai_model=settings.GROQ_MODEL,
        prompt_hash=phash,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_QUOTA_SIGNALS = ("resource_exhausted", "429", "quota", "rate_limit", "rate limit")


async def score_submission(
    question: str,
    submission_text: str,
    rubric: list[dict],
) -> RubricScoringResult:
    """
    Score `submission_text` against `rubric` criteria.

    Tries Gemini first; falls back to Groq on quota errors.
    On any scoring failure, returns a LOW-confidence all-zero result.
    """
    if not submission_text or not submission_text.strip():
        zero_scores = [
            CriterionScore(
                criterion_id=c["criterion_id"],
                ai_score=0.0,
                ai_justification="No submission content to evaluate.",
                max_marks=int(c["max_marks"]),
            )
            for c in rubric
        ]
        return RubricScoringResult(
            criteria_scores=zero_scores,
            overall_ai_score=0.0,
            confidence_level="LOW",
            ai_model="none",
            prompt_hash="",
        )

    system, user = _build_prompt(question, submission_text, rubric)
    phash = _prompt_hash(system, user)

    # Try Gemini
    try:
        result = await _score_with_gemini(system, user, rubric, phash)
        logger.info("Rubric scored with Gemini (prompt_hash=%s)", phash)
        return result
    except Exception as exc:
        msg = str(exc).lower()
        if not any(s in msg for s in _QUOTA_SIGNALS):
            logger.warning("Gemini rubric scoring failed (non-quota): %s", exc)
        else:
            logger.warning("Gemini quota hit — falling back to Groq.")

    # Groq fallback
    try:
        result = await _score_with_groq(system, user, rubric, phash)
        logger.info("Rubric scored with Groq (prompt_hash=%s)", phash)
        return result
    except Exception as exc:
        logger.error("Rubric scoring failed on both Gemini and Groq: %s", exc)
        # Return LOW-confidence all-zero result so the task doesn't fail completely
        zero_scores = [
            CriterionScore(
                criterion_id=c["criterion_id"],
                ai_score=0.0,
                ai_justification=f"Scoring failed: {exc!s:.100}",
                max_marks=int(c["max_marks"]),
            )
            for c in rubric
        ]
        return RubricScoringResult(
            criteria_scores=zero_scores,
            overall_ai_score=0.0,
            confidence_level="LOW",
            ai_model="error",
            prompt_hash=phash,
        )
