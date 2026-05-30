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
# Response normaliser
# ---------------------------------------------------------------------------

# All known envelope keys LLMs use to wrap a scores array.
# Groq's json_object mode always returns a dict, so we must handle many shapes.
_ARRAY_ENVELOPE_KEYS = (
    "scores", "criteria_scores", "rubric_scores", "results",
    "criteria", "items", "data", "evaluations", "evaluation",
    "criterion_scores",
)


def _normalise_to_items(parsed: Any) -> list[dict]:
    """Convert any valid AI response shape to a flat list of score dicts.

    Handles:
      1. Bare JSON array                    → returned as-is
      2. Single criterion object            → wrapped in [...]
      3. Dict with a known array key        → array extracted
      4. Dict keyed by criterion_id         → converted to array
    Raises ValueError for unrecognised shapes so the caller can log clearly.
    """
    if isinstance(parsed, list):
        return parsed

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON array; got {type(parsed).__name__}")

    # Case A: the dict IS a single criterion score (Groq sometimes returns this
    # when the rubric has only one criterion or the model collapses the array).
    if "criterion_id" in parsed and "ai_score" in parsed:
        return [parsed]

    # Case B: dict with a recognised array envelope key
    for key in _ARRAY_ENVELOPE_KEYS:
        val = parsed.get(key)
        if isinstance(val, list):
            return val

    # Case C: dict keyed by criterion_id with score objects as values
    # e.g. {"c1": {"ai_score": 8, "ai_justification": "..."}, "c2": {...}}
    cid_keyed = [
        {"criterion_id": k, **v}
        for k, v in parsed.items()
        if isinstance(v, dict) and "ai_score" in v
    ]
    if cid_keyed:
        return cid_keyed

    raise ValueError(
        f"Expected JSON array; got dict with unrecognised shape "
        f"(keys: {list(parsed.keys())[:10]})"
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _resolve_to_canonical_id(
    ai_cid: str,
    rubric: list[dict],
    matched: set[str],
) -> str | None:
    """
    Resolve an AI-returned criterion_id string to a canonical rubric criterion_id.

    Stage 1 — exact match on criterion_id.
    Stage 2 — case-insensitive match on criterion name
               (LLMs sometimes return the criterion name as the id).
    Returns None when neither stage matches; caller applies positional fallback.
    """
    ai_lower = ai_cid.lower().strip()

    for c in rubric:
        if c["criterion_id"] in matched:
            continue
        if c["criterion_id"] == ai_cid:
            return c["criterion_id"]

    for c in rubric:
        if c["criterion_id"] in matched:
            continue
        cname = c.get("name", "").lower().strip()
        if cname and (ai_lower == cname or ai_lower in cname or cname in ai_lower):
            return c["criterion_id"]

    return None


def _parse_response(raw: str, rubric: list[dict]) -> list[CriterionScore]:
    """
    Parse the LLM JSON response into a list of CriterionScore objects.

    AI-returned criterion_ids are hints only; output always uses canonical ids
    from the rubric definition. Resolution order per item:
      1. Exact criterion_id match
      2. Criterion-name match (case-insensitive, partial containment)
      3. Positional fallback — i-th unresolved item maps to i-th unmatched rubric
         criterion (valid because the prompt requests SAME ORDER as the rubric)
    """
    rubric_map = {c["criterion_id"]: c for c in rubric}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI response is not valid JSON: {exc}\nRaw: {raw[:400]}") from exc

    items = _normalise_to_items(parsed)

    scores: list[CriterionScore] = []
    matched: set[str] = set()   # canonical ids already resolved
    deferred: list[dict] = []   # items that need positional fallback

    for item in items:
        ai_cid = str(item.get("criterion_id", ""))
        score  = float(item.get("ai_score", 0))
        just   = str(item.get("ai_justification", "")).strip()

        canonical = _resolve_to_canonical_id(ai_cid, rubric, matched)

        if canonical is not None:
            rubric_crit = rubric_map[canonical]
            max_m = int(rubric_crit["max_marks"])
            score = max(0.0, min(float(max_m), score))
            scores.append(CriterionScore(
                criterion_id=canonical,
                ai_score=round(score, 2),
                ai_justification=just or "No justification provided.",
                max_marks=max_m,
            ))
            matched.add(canonical)
        else:
            deferred.append({"score": score, "just": just})

    # Positional fallback: pair each deferred item with an unmatched rubric criterion
    unmatched_rubric = [c for c in rubric if c["criterion_id"] not in matched]
    for item_data, rubric_crit in zip(deferred, unmatched_rubric):
        max_m = int(rubric_crit["max_marks"])
        score = max(0.0, min(float(max_m), item_data["score"]))
        scores.append(CriterionScore(
            criterion_id=rubric_crit["criterion_id"],
            ai_score=round(score, 2),
            ai_justification=item_data["just"] or "No justification provided.",
            max_marks=max_m,
        ))
        matched.add(rubric_crit["criterion_id"])

    # Fill any rubric criteria the AI omitted entirely
    for c in rubric:
        if c["criterion_id"] not in matched:
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
