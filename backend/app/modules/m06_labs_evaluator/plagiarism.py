"""
M06 Plagiarism Service — cosine similarity across cohort submissions.

Approach:
  - Character n-gram TF-IDF vectors (n=3,4,5) computed in-memory with numpy.
  - Cosine similarity between the target submission and every other submission
    in the same assignment cohort.
  - Returns top-3 matches with similarity scores.
  - Flagged if max similarity >= threshold (from assignment.plagiarism_threshold).

No external services required (Qdrant, embeddings API). Works offline.
Suitable for cohorts up to ~500 submissions. For larger cohorts, replace
with Qdrant embedding search (plug in as an alternate implementation of
`compute_plagiarism`).

Returns a PlagiarismResult with:
  - max_similarity: highest cosine similarity found
  - matches: top-3 [{submission_id, similarity, student_user_id}]
  - is_flagged: True if max_similarity >= threshold
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class PlagiarismResult:
    max_similarity: float
    matches: list[dict] = field(default_factory=list)
    is_flagged: bool = False


# ---------------------------------------------------------------------------
# Character n-gram TF-IDF
# ---------------------------------------------------------------------------

def _char_ngrams(text: str, n: int) -> list[str]:
    t = re.sub(r"\s+", " ", text.lower().strip())
    return [t[i:i+n] for i in range(len(t) - n + 1)]


def _tfidf_vector(text: str, ngram_sizes: tuple[int, ...] = (3, 4, 5)) -> Counter:
    """Build a term frequency counter across multiple n-gram sizes."""
    counts: Counter = Counter()
    for n in ngram_sizes:
        counts.update(_char_ngrams(text, n))
    return counts


def _cosine_similarity(a: Counter, b: Counter) -> float:
    """Cosine similarity between two Counter-based TF-IDF vectors."""
    if not a or not b:
        return 0.0

    common_terms = set(a) & set(b)
    dot_product = sum(a[t] * b[t] for t in common_terms)

    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def compute_plagiarism(
    target_text: str,
    cohort: list[tuple[UUID, str]],     # [(submission_id, text), ...]
    *,
    threshold: float = 0.85,
    student_ids: dict[UUID, UUID] | None = None,   # submission_id → student_user_id
    top_k: int = 3,
) -> PlagiarismResult:
    """
    Compare `target_text` against all texts in `cohort`.

    cohort: list of (submission_id, text) tuples excluding the target submission.
    student_ids: optional map from submission_id to student_user_id for matches.
    threshold: flag if max_similarity >= this value.
    top_k: number of closest matches to return.

    Returns PlagiarismResult.
    """
    if not target_text or not target_text.strip() or not cohort:
        return PlagiarismResult(max_similarity=0.0, matches=[], is_flagged=False)

    target_vec = _tfidf_vector(target_text)
    scores: list[tuple[float, UUID]] = []

    for sub_id, text in cohort:
        if not text or not text.strip():
            continue
        vec = _tfidf_vector(text)
        sim = _cosine_similarity(target_vec, vec)
        scores.append((sim, sub_id))

    scores.sort(key=lambda x: x[0], reverse=True)
    top_matches = scores[:top_k]

    max_similarity = top_matches[0][0] if top_matches else 0.0

    matches = []
    for sim, sub_id in top_matches:
        match_dict: dict = {
            "submission_id": str(sub_id),
            "similarity": round(sim, 4),
        }
        if student_ids and sub_id in student_ids:
            match_dict["student_user_id"] = str(student_ids[sub_id])
        matches.append(match_dict)

    return PlagiarismResult(
        max_similarity=round(max_similarity, 4),
        matches=matches,
        is_flagged=max_similarity >= threshold,
    )
