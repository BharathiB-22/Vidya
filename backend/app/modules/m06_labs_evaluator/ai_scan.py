"""
M06 AI Content Scan — perplexity + burstiness heuristics.

Detects AI-generated text using two lightweight, dependency-free signals:

  1. Burstiness (coefficient of variation of sentence lengths)
     Human writing is bursty — short and long sentences mixed.
     AI writing is uniformly distributed → low burstiness → high AI probability.

  2. Repetition score (proportion of repeated 5-gram token sequences)
     AI text tends to reuse the same phrase structures more than humans.

  3. Vocabulary richness (type/token ratio on a 100-token window)
     AI text uses a narrower effective vocabulary per unit of text.

Combined score: weighted mean (burstiness 0.4, repetition 0.4, vocab 0.2).
Score range: 0.0 (definitely human) → 1.0 (likely AI).

Threshold from settings.M06_AI_SCAN_THRESHOLD (default 0.75).

Note: This is a lightweight heuristic module. For production deployments,
replace or augment with a fine-tuned RoBERTa classifier (pluggable at the
`scan()` call site — same AIScanResult return type).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class AIScanResult:
    probability: float             # 0.0–1.0 composite AI probability
    confidence: float              # 0.0–1.0 confidence in the estimate
    burstiness_score: float        # raw burstiness signal (higher = more human)
    repetition_score: float        # raw repetition signal (higher = more AI)
    vocab_richness_score: float    # raw vocab richness (higher = more human)
    highlights: list[dict] = field(default_factory=list)  # [{start, end, score}]
    is_flagged: bool = False       # True if probability >= threshold


# ---------------------------------------------------------------------------
# Tokeniser (no NLTK required)
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"[.!?]+")
_WORD_SPLIT     = re.compile(r"\b[a-zA-Z]+\b")


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def _words(text: str) -> list[str]:
    return _WORD_SPLIT.findall(text.lower())


# ---------------------------------------------------------------------------
# Signal 1: burstiness (CV of sentence lengths)
# ---------------------------------------------------------------------------

def _burstiness_signal(text: str) -> float:
    """
    Returns a burstiness score 0–1 where 1 = maximally bursty (human-like).
    Coefficient of variation of sentence word counts, capped at 1.0.
    """
    sents = _sentences(text)
    if len(sents) < 3:
        return 0.5  # not enough data — neutral

    lengths = [len(_words(s)) for s in sents]
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.5
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    cv = (variance ** 0.5) / mean
    # Normalise: human text typically has CV > 0.5; AI text < 0.3
    return min(cv / 0.8, 1.0)


# ---------------------------------------------------------------------------
# Signal 2: repetition score (5-gram repetition ratio)
# ---------------------------------------------------------------------------

def _repetition_signal(text: str) -> float:
    """
    Returns 0–1 where 1 = highly repetitive (AI-like).
    Fraction of 5-grams that appear more than once.
    """
    words = _words(text)
    if len(words) < 10:
        return 0.0

    n = 5
    ngrams: list[tuple] = [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]
    seen: set[tuple] = set()
    repeated = 0
    for ng in ngrams:
        if ng in seen:
            repeated += 1
        seen.add(ng)

    return min(repeated / max(len(ngrams), 1), 1.0)


# ---------------------------------------------------------------------------
# Signal 3: vocabulary richness (type-token ratio on 100-token window)
# ---------------------------------------------------------------------------

def _vocab_richness_signal(text: str) -> float:
    """
    Returns 0–1 where 1 = rich vocabulary (human-like).
    Average TTR over sliding 100-token windows.
    """
    words = _words(text)
    if not words:
        return 0.5
    if len(words) < 20:
        return len(set(words)) / len(words)

    window = 100
    ttrs: list[float] = []
    for i in range(0, len(words) - window + 1, 50):
        chunk = words[i : i + window]
        ttrs.append(len(set(chunk)) / len(chunk))

    return sum(ttrs) / len(ttrs) if ttrs else 0.5


# ---------------------------------------------------------------------------
# Highlight spans — paragraphs with low burstiness
# ---------------------------------------------------------------------------

def _compute_highlights(text: str, threshold: float) -> list[dict]:
    """
    Mark paragraphs whose burstiness score is below the AI threshold.
    Returns list of {start, end, score} character offsets.
    """
    highlights: list[dict] = []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    offset = 0
    for para in paragraphs:
        b = _burstiness_signal(para)
        r = _repetition_signal(para)
        # Paragraph AI score: inverse burstiness + repetition
        para_ai_score = (1.0 - b) * 0.5 + r * 0.5
        if para_ai_score >= threshold:
            start = text.find(para, offset)
            end   = start + len(para)
            highlights.append({"start": start, "end": end, "score": round(para_ai_score, 3)})
        idx = text.find(para, offset)
        if idx >= 0:
            offset = idx + len(para)
    return highlights


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def scan(text: str, *, threshold: float = 0.75) -> AIScanResult:
    """
    Scan `text` for AI-generated content.

    Returns an AIScanResult with:
      - probability: 0.0–1.0 composite AI probability
      - is_flagged: True if probability >= threshold
      - highlights: paragraph spans that triggered the flag

    Handles empty/very short text gracefully (probability = 0.0).
    """
    if not text or len(text.strip()) < 50:
        return AIScanResult(
            probability=0.0,
            confidence=0.1,
            burstiness_score=0.5,
            repetition_score=0.0,
            vocab_richness_score=0.5,
        )

    b = _burstiness_signal(text)
    r = _repetition_signal(text)
    v = _vocab_richness_signal(text)

    # Probability of AI authorship:
    #   - low burstiness  → more likely AI
    #   - high repetition → more likely AI
    #   - low vocab       → more likely AI
    ai_prob = (1.0 - b) * 0.4 + r * 0.4 + (1.0 - v) * 0.2
    ai_prob = round(min(max(ai_prob, 0.0), 1.0), 4)

    # Confidence correlates with text length (more text → more reliable)
    word_count = len(_words(text))
    confidence = round(min(word_count / 200, 1.0), 3)

    highlights = _compute_highlights(text, threshold) if ai_prob >= threshold else []

    return AIScanResult(
        probability=ai_prob,
        confidence=confidence,
        burstiness_score=round(b, 4),
        repetition_score=round(r, 4),
        vocab_richness_score=round(v, 4),
        highlights=highlights,
        is_flagged=ai_prob >= threshold,
    )
