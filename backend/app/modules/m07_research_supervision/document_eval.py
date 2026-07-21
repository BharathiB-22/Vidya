"""
M07 Document Evaluator — comprehensive evaluation of uploaded research documents.

Pipeline:
  1. Format compliance check (rule-based): section headers, word count, citations.
  2. AI content scan: reuse M06 ai_scan.scan() — no modification.
  3. Plagiarism check: reuse M06 plagiarism.compute_plagiarism() on corpus texts.
  4. Clarity scoring: LLM (Gemini → Groq fallback) rates overall clarity.

Returns a DocumentEvalResult with per-dimension scores and a structured
evaluation_report for storage in research_documents.evaluation_report.

All scores are 0.0–1.0 (1.0 = best / most compliant).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import re

from app.config import settings

logger = logging.getLogger("vidya.m07.document_eval")

# ---------------------------------------------------------------------------
# Reuse M06 components — import only, never modify
# ---------------------------------------------------------------------------
from app.modules.m06_labs_evaluator.ai_scan import scan as ai_scan
from app.modules.m06_labs_evaluator.plagiarism import compute_plagiarism


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class FormatIssue:
    section: str
    issue:   str


@dataclasses.dataclass
class DocumentEvalResult:
    plagiarism_score:  float              # max cosine similarity (0–1)
    ai_content_score:  float              # AI probability (0–1)
    format_score:      float              # compliance fraction (0–1)
    clarity_score:     float              # LLM clarity rating (0–1)
    evaluation_report: dict               # structured for DB storage
    ai_model:          str
    prompt_hash:       str


# ---------------------------------------------------------------------------
# 1. Format compliance (rule-based)
# ---------------------------------------------------------------------------

_REQUIRED_SECTIONS = [
    "introduction",
    "literature review",
    "methodology",
    "objectives",
    "references",
]

_CITATION_PATTERN = re.compile(
    r"(\[\d+\]|\(\w[\w\s,]+,\s*\d{4}\))"
)


def _check_format(text: str) -> tuple[float, list[FormatIssue]]:
    """
    Check for required section headers and minimum citations.
    Returns (format_score, issues).
    """
    text_lower = text.lower()
    issues: list[FormatIssue] = []

    present = sum(1 for s in _REQUIRED_SECTIONS if s in text_lower)
    for s in _REQUIRED_SECTIONS:
        if s not in text_lower:
            issues.append(FormatIssue(section=s, issue=f"Missing section: '{s}'"))

    # Word count check (research docs expected > 500 words)
    word_count = len(text.split())
    if word_count < 500:
        issues.append(FormatIssue(section="length", issue=f"Too short: {word_count} words (min 500)"))

    # Citation presence check
    citations = _CITATION_PATTERN.findall(text)
    if len(citations) < 3:
        issues.append(FormatIssue(
            section="references",
            issue=f"Only {len(citations)} inline citation(s) found (expected ≥ 3)",
        ))

    total_checks = len(_REQUIRED_SECTIONS) + 2  # sections + word count + citations
    passed = present + (1 if word_count >= 500 else 0) + (1 if len(citations) >= 3 else 0)
    score = round(passed / total_checks, 3)
    return score, issues


# ---------------------------------------------------------------------------
# 4. Clarity scoring via LLM
# ---------------------------------------------------------------------------

def _build_clarity_prompt(title: str, text_excerpt: str) -> str:
    excerpt = text_excerpt[:3000]
    return f"""You are an academic research evaluator. Rate the clarity and quality of the following research document excerpt.

Document title: {title}

Excerpt:
---
{excerpt}
---

Evaluate on a scale of 0.0 to 1.0 where:
  0.0 = very unclear, poorly written, vague objectives
  0.5 = adequate, some clarity issues
  1.0 = excellent clarity, well-structured, precise language

Respond ONLY with a JSON object:
{{"clarity_score": <float 0.0-1.0>, "notes": "<1-2 sentence explanation>"}}"""


async def _score_clarity_gemini(prompt: str) -> tuple[float, str, str]:
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    response = model.generate_content(prompt)
    return _parse_clarity_response(response.text), response.text, settings.GEMINI_MODEL


async def _score_clarity_groq(prompt: str) -> tuple[float, str, str]:
    import httpx
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 256,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload
        )
        resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return _parse_clarity_response(text), text, settings.GROQ_MODEL


def _parse_clarity_response(raw: str) -> float:
    raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
    try:
        data = json.loads(raw)
        score = float(data.get("clarity_score", 0.5))
        return max(0.0, min(1.0, score))
    except Exception:
        m = re.search(r'"clarity_score"\s*:\s*([0-9.]+)', raw)
        if m:
            return max(0.0, min(1.0, float(m.group(1))))
        return 0.5


async def _score_clarity(
    title: str,
    text: str,
) -> tuple[float, str, str, str]:
    """Returns (score, notes, model_name, prompt_hash)."""
    prompt = _build_clarity_prompt(title, text)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

    provider = settings.AI_PROVIDER
    try:
        if provider == "groq":
            score, raw, model = await _score_clarity_groq(prompt)
        elif provider == "gemini":
            score, raw, model = await _score_clarity_gemini(prompt)
        else:
            try:
                score, raw, model = await _score_clarity_gemini(prompt)
            except Exception:
                score, raw, model = await _score_clarity_groq(prompt)
    except Exception as exc:
        logger.warning("LLM clarity scoring failed: %s — defaulting to 0.5", exc)
        score, raw, model = 0.5, str(exc), "fallback"

    # Extract notes from raw
    notes = "Clarity assessment unavailable."
    try:
        clean = re.sub(r"```json\s*|\s*```", "", raw).strip()
        data = json.loads(clean)
        notes = data.get("notes", notes)
    except Exception:
        pass

    return score, notes, model, prompt_hash


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def evaluate_document(
    title: str,
    content_text: str,
    corpus_texts: list[tuple[str, str]],  # [(doc_id, text), ...]
    *,
    ai_threshold: float | None = None,
    plagiarism_threshold: float | None = None,
) -> DocumentEvalResult:
    """
    Run full evaluation pipeline on a research document.

    Args:
        title: document title (for LLM context)
        content_text: full extracted text of the document
        corpus_texts: other documents to check plagiarism against — [(id, text)]
        ai_threshold: override M07_AI_CONTENT_THRESHOLD
        plagiarism_threshold: override M07_PLAGIARISM_THRESHOLD
    """
    ai_thresh   = ai_threshold   or settings.M07_AI_CONTENT_THRESHOLD
    plag_thresh = plagiarism_threshold or settings.M07_PLAGIARISM_THRESHOLD

    # 1. Format compliance
    format_score, format_issues = _check_format(content_text)

    # 2. AI content scan (reuse M06)
    ai_result = ai_scan(content_text, threshold=ai_thresh)

    # 3. Plagiarism (reuse M06 pattern)
    plag_result = compute_plagiarism(
        content_text,
        corpus_texts,
        threshold=plag_thresh,
    )

    # 4. Clarity scoring
    clarity_score, clarity_notes, model_name, prompt_hash = await _score_clarity(
        title, content_text
    )

    evaluation_report: dict = {
        "format_issues": [
            {"section": fi.section, "issue": fi.issue}
            for fi in format_issues
        ],
        "plagiarism_matches": plag_result.matches,
        "ai_highlights":     ai_result.highlights,
        "clarity_notes":     clarity_notes,
        "word_count":        len(content_text.split()),
        "ai_scan": {
            "probability":         ai_result.probability,
            "confidence":          ai_result.confidence,
            "burstiness_score":    ai_result.burstiness_score,
            "repetition_score":    ai_result.repetition_score,
            "vocab_richness_score": ai_result.vocab_richness_score,
        },
    }

    logger.info(
        "Document eval complete: format=%.2f ai=%.2f plagiarism=%.2f clarity=%.2f",
        format_score, ai_result.probability, plag_result.max_similarity, clarity_score
    )

    return DocumentEvalResult(
        plagiarism_score=round(plag_result.max_similarity, 3),
        ai_content_score=round(ai_result.probability, 3),
        format_score=format_score,
        clarity_score=round(clarity_score, 3),
        evaluation_report=evaluation_report,
        ai_model=model_name,
        prompt_hash=prompt_hash,
    )
